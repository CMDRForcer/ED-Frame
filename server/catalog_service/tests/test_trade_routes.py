import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from psycopg.errors import QueryCanceled
from edframe_catalog.api import trade_routes
from edframe_catalog import trade_routes as service
from ed_companion.navigation.trade_route_model import search_filters
from ed_companion.navigation.trade_routes import validate_trade_routes
from test_commodities import api_get


def data():
    stations=[dict(marketId=1,station="A",system="Sol",coordinates=[0,0,0],landingPadSize="L",fleetCarrier=False,
        distanceLy=0,availableStations=2,availableStarts=2),
        dict(marketId=2,station="B",system="Other",coordinates=[10,0,0],landingPadSize="L",fleetCarrier=False,
            distanceLy=10,availableStations=2,availableStarts=2)]
    now=datetime.now(timezone.utc)
    quotes=[dict(marketId=1,commodity="gold",buyPrice=10,sellPrice=5,stock=10,demand=10,observedAt=now),
        dict(marketId=2,commodity="gold",buyPrice=30,sellPrice=20,stock=10,demand=10,observedAt=now),
        dict(marketId=1,commodity="water",buyPrice=40,sellPrice=30,stock=10,demand=10,observedAt=now),
        dict(marketId=2,commodity="water",buyPrice=20,sellPrice=10,stock=10,demand=10,observedAt=now)]
    return stations,quotes


class TradeRouteApiTests(unittest.TestCase):
    def setUp(self):
        with service._cache_lock:service._cache.clear()

    def connection(self):
        stations,quotes=data()
        conn=MagicMock()
        def execute(sql,*args):
            result=MagicMock()
            if "pg_try_advisory" in sql:result.fetchone.return_value=dict(acquired=True)
            elif "WITH nearby" in sql:result.fetchall.return_value=[dict(row) for row in stations]
            elif 'SELECT market_id AS "marketId"' in sql:result.fetchall.return_value=[dict(row) for row in quotes]
            return result
        conn.execute.side_effect=execute
        return conn

    def test_readonly_snapshot_limits_all_quotes_and_sorts_complete_loops(self):
        conn=self.connection()
        with patch("edframe_catalog.trade_routes.connection") as factory:
            factory.return_value.__enter__.return_value=conn
            result=trade_routes(0,0,0,cargo_tonnes=10,budget_cr=50,landing_pad="L")
        self.assertEqual(len(result["results"]),2)
        self.assertFalse(result["coverage"]["sampled"])
        sqls=[call.args[0] for call in conn.execute.call_args_list]
        self.assertEqual(sqls[:3],["SET TRANSACTION READ ONLY","SET LOCAL statement_timeout = '10s'","SET LOCAL lock_timeout = '2s'"])
        self.assertTrue(all(sql.lstrip().startswith(("SET","SELECT","WITH")) for sql in sqls))
        self.assertIn("market_id=ANY(%s)",sqls[-1])
        self.assertEqual(conn.execute.call_args.args[1][-1],120001)
        self.assertEqual(len(validate_trade_routes(result,result["filters"])["results"]),2)

    def test_recent_cache_does_not_requery_and_refresh_bypasses_it(self):
        conn=self.connection()
        with patch("edframe_catalog.trade_routes.connection") as factory:
            factory.return_value.__enter__.return_value=conn
            first=trade_routes(0,0,0,cargo_tonnes=10,budget_cr=50,landing_pad="L")
            second=trade_routes(0,0,0,cargo_tonnes=10,budget_cr=50,landing_pad="L")
            self.assertEqual(factory.call_count,1)
            self.assertTrue(second["cached"])
            self.assertEqual(first["generatedAt"],second["generatedAt"])
            trade_routes(0,0,0,cargo_tonnes=10,budget_cr=50,landing_pad="L",refresh=True)
            self.assertEqual(factory.call_count,2)

    def test_busy_and_timeouts_are_retryable_and_release_gate(self):
        filters=search_filters([0,0,0],50,100,10,50,24,"L",False)
        service._gate.acquire()
        try:
            with self.assertRaises(HTTPException) as raised:service.search_trade_routes(filters)
            self.assertEqual(raised.exception.status_code,503)
        finally:service._gate.release()
        conn=self.connection();original=conn.execute.side_effect
        def timeout(sql,*args):
            if "WITH nearby" in sql:raise QueryCanceled("synthetic")
            return original(sql,*args)
        conn.execute.side_effect=timeout
        with patch("edframe_catalog.trade_routes.connection") as factory:
            factory.return_value.__enter__.return_value=conn
            with self.assertRaises(HTTPException) as raised:service.search_trade_routes(filters)
            self.assertEqual(raised.exception.status_code,503)
        self.assertTrue(service._gate.acquire(blocking=False));service._gate.release()

    def test_large_regions_explicitly_mark_station_sampling(self):
        conn=self.connection();original=conn.execute.side_effect
        def sample(sql,*args):
            result=original(sql,*args)
            if "WITH nearby" in sql:
                stations,_=data()
                for row in stations:row.update(availableStations=500,availableStarts=100)
                result.fetchall.return_value=stations
            return result
        conn.execute.side_effect=sample
        with patch("edframe_catalog.trade_routes.connection") as factory:
            factory.return_value.__enter__.return_value=conn
            result=trade_routes(0,0,0,cargo_tonnes=10,budget_cr=50)
        self.assertTrue(result["coverage"]["sampled"])
        self.assertEqual(result["coverage"]["availableStations"],500)

    def test_real_http_validation_and_client_contract(self):
        params=dict(x=0,y=0,z=0,cargo_tonnes=10,budget_cr=50,landing_pad="L")
        with patch("edframe_catalog.trade_routes.connection") as factory:
            factory.return_value.__enter__.return_value=self.connection()
            response=api_get(params,path="/v1/markets/trade-routes")
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(validate_trade_routes(response.json(),response.json()["filters"])["results"]),2)
        for invalid in (dict(cargo_tonnes=0),dict(budget_cr=0),dict(max_distance=0),dict(max_leg_distance=501),dict(sort_by="bad"),dict(commodity="unknown")):
            with patch("edframe_catalog.trade_routes.connection") as factory:
                response=api_get(dict(params,**invalid),path="/v1/markets/trade-routes")
                self.assertEqual(response.status_code,422);factory.assert_not_called()
