"""Synthetic integration probe; require a separate disposable PostgreSQL database."""
from datetime import datetime, timedelta, timezone
import json
import os

from edframe_catalog.collector import _project_and_commit
from edframe_catalog.collector_transactions import retry_transaction
from edframe_catalog.database import connection, ensure_schema, record_state
from edframe_catalog.query_performance import read_query_performance
from psycopg.errors import DeadlockDetected


def emit(**fields):
    print(json.dumps(fields), flush=True)


class AbortAtCommit:
    def __init__(self, conn, sqlstate, failures):
        self.conn, self.sqlstate, self.remaining = conn, sqlstate, failures
        self.attempts = 0

    def __getattr__(self, name):
        return getattr(self.conn, name)

    def commit(self):
        self.attempts += 1
        if self.remaining:
            self.remaining -= 1
            self.conn.execute("DO $$ BEGIN RAISE EXCEPTION 'synthetic transaction abort' USING ERRCODE = '" + self.sqlstate + "'; END $$")
        else:
            self.conn.commit()


def payload(stamp, price):
    return {"$schemaRef":"https://eddn.edcd.io/schemas/commodity/3", "message":{
        "systemName":"Retry Synthetic System", "stationName":"Retry Synthetic Port",
        "marketId":987654321, "timestamp":stamp,
        "commodities":[{"name":"gold", "meanPrice":100, "buyPrice":90,
                        "stock":123, "stockBracket":3, "sellPrice":price,
                        "demand":456, "demandBracket":3, "statusFlags":[]}]}}


def main():
    with connection() as conn:
        name = conn.execute("SELECT current_database() AS name").fetchone()["name"]
        assert name.startswith("edframe_retry_probe_"), "Refuse to touch a retained catalog database"
    ensure_schema()
    with connection() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
        conn.commit()
        base = datetime.now(timezone.utc) - timedelta(minutes=2)
        for index, state, failures in ((0,"40P01",1),(1,"40001",2)):
            stamp = (base+timedelta(seconds=index)).isoformat()
            receipt = (base+timedelta(seconds=index+10)).isoformat()
            frame = payload(stamp, 1000+index)
            wrapped = AbortAtCommit(conn,state,failures)
            retry_transaction(wrapped,lambda:_project_and_commit(wrapped,frame,"commodity/3",receipt,123),schema="commodity/3",received_at=receipt)
            market = conn.execute("SELECT sell_price, observed_at, received_at FROM markets WHERE market_id=987654321 AND commodity='gold'").fetchone()
            metrics = conn.execute("SELECT messages_total,errors_total FROM collector_state WHERE source='EDDN'").fetchone()
            assert market["sell_price"]==1000+index
            assert market["observed_at"]==datetime.fromisoformat(stamp)
            assert market["received_at"]==datetime.fromisoformat(receipt)
            assert metrics["messages_total"]==index+1 and metrics["errors_total"]==0
            assert wrapped.attempts==failures+1
            conn.commit()
            emit(sqlstate=state,attempts=wrapped.attempts,committedMessages=metrics["messages_total"],timestampsPreserved=True,result="PASS")
        receipt=(base+timedelta(seconds=30)).isoformat()
        wrapped=AbortAtCommit(conn,"40P01",10)
        try:
            retry_transaction(wrapped,lambda:_project_and_commit(wrapped,payload((base+timedelta(seconds=20)).isoformat(),9999),"commodity/3",receipt,123),schema="commodity/3",received_at=receipt)
        except DeadlockDetected:
            conn.rollback()
            record_state(conn,schema="commodity/3",received_at=receipt,errors=1,message_bytes=123)
            conn.commit()
        else:
            raise AssertionError("Persistent conflict was hidden")
        market=conn.execute("SELECT sell_price FROM markets WHERE market_id=987654321 AND commodity='gold'").fetchone()
        metrics=conn.execute("SELECT messages_total,errors_total FROM collector_state WHERE source='EDDN'").fetchone()
        assert wrapped.attempts==4 and market["sell_price"]==1001
        assert metrics["messages_total"]==3 and metrics["errors_total"]==1
        conn.commit()
        emit(persistentConflict="reported once",attempts=wrapped.attempts,previousFactsRetained=True,result="PASS")
        for value in (1,2,3):
            conn.execute("SELECT pg_sleep(0.01), %s::int AS measurement_probe",(value,)).fetchone()
        conn.commit()
        report=read_query_performance(conn,limit=50,include_sql=True)
        samples=[row for row in report["statements"] if row["sql"] and "measurement_probe" in row["sql"]]
        assert samples and samples[0]["calls"]>=3 and samples[0]["mean_ms"]>5
        assert "$" in samples[0]["sql"], "Test literal was not normalized"
        assert report["collection"]["io_timing"]=="on"
        emit(queryMeasurement="normalized calls and execution time",calls=samples[0]["calls"],meanMs=round(samples[0]["mean_ms"],3),result="PASS")


if __name__ == "__main__":
    main()
