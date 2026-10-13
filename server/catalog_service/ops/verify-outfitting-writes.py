"""Disposable replay against the previous writer and reader; production reads only."""
import argparse
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import importlib.util
import json,os,time
from pathlib import Path
from unittest.mock import patch

from edframe_catalog import api,database
from edframe_catalog.database import connection
from ed_companion.navigation.mining_commodities import MINING_COMMODITIES


def emit(**data):print(json.dumps(data,default=str),flush=True)


def load(name,path):
    spec=importlib.util.spec_from_file_location("edframe_catalog."+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@contextmanager
def borrowed(conn):yield conn


def call(conn,api_module,name,**kwargs):
    with patch.object(api_module,"connection",side_effect=lambda:borrowed(conn)):
        value=getattr(api_module,name)(**kwargs)
    value.pop("generatedAt",None)
    return value


def synthetic(legacy_dir):
    old=load("_baseline_database",legacy_dir/"database.py")
    old_api=load("_baseline_api",legacy_dir/"api.py")
    with connection() as conn:
        name=conn.execute("SELECT current_database() AS name").fetchone()["name"]
        if not name.startswith("edframe_write_probe_"):
            raise RuntimeError("Refuse to write a retained catalog database")
        for schema in ("baseline","optimized"):
            conn.execute("CREATE SCHEMA "+schema)
            conn.execute("SET search_path="+schema+",public")
            with patch.object(database,"connection",side_effect=lambda:borrowed(conn)):
                database.ensure_schema()
        conn.commit()
        base=datetime(2026,10,12,tzinfo=timezone.utc)
        os.environ["EDFRAME_SHARED_OUTFITTING_FRESHNESS"]="1"
        steps=[];compared=0
        def row(items,*,second=0,source="EDDN outfitting/2",kind="OUTFITTING",market_id=42):
            return dict(kind=kind,market_id=market_id,system_name="Synthetic System",
                        station_name="Synthetic Port",items=json.dumps(items),
                        horizons=True,odyssey=True,observed_at=(base+timedelta(seconds=second)).isoformat(),
                        received_at=(base+timedelta(seconds=second+1)).isoformat(),source=source)
        def normalized(schema,market_id):
            conn.execute("SET search_path="+schema+",public")
            # Parent owns last complete inventory availability. Item price proof
            # stays independent, including priced observations predating v2.
            stamp="m.observed_at" if schema=="baseline" else "GREATEST(m.observed_at,p.observed_at)"
            source="m.availability_source" if schema=="baseline" else "COALESCE(p.source,m.availability_source)"
            return conn.execute(f"""SELECT m.market_id,m.module_symbol,m.module_id,
                m.buy_price,m.buy_merc_coins_price,m.price_observed_at,m.price_source,
                {stamp} AS observed_at,{source} AS availability_source
                FROM station_module_offers m LEFT JOIN station_outfitting p USING(market_id)
                WHERE m.market_id=%s ORDER BY m.module_symbol""",(market_id,)).fetchall()
        def locations(schema,market_id):
            conn.execute("SET search_path="+schema+",public")
            return {r["module_symbol"]:r["ctid"] for r in conn.execute(
                "SELECT module_symbol,ctid::text FROM station_module_offers WHERE market_id=%s",(market_id,))}
        def replay(label,payload,unchanged=False):
            nonlocal compared
            elapsed=[];changed=[]
            for schema,writer in (("baseline",old),("optimized",database)):
                before=locations(schema,payload["market_id"])
                start=time.monotonic()
                writer.upsert_station_offer_batch(conn,[payload])
                elapsed.append(round((time.monotonic()-start)*1000,3))
                after=locations(schema,payload["market_id"])
                changed.append(sum(before.get(k)!=after.get(k) for k in set(before)|set(after)))
            assert normalized("baseline",payload["market_id"])==normalized("optimized",payload["market_id"]),label
            parents=[]
            for schema in ("baseline","optimized"):
                conn.execute("SET search_path="+schema+",public")
                parents.append(conn.execute("SELECT * FROM station_outfitting ORDER BY market_id").fetchall())
            assert parents[0]==parents[1],(label,"Parent snapshots changed")
            for function,kwargs in (
                ("search_station_offers",dict(module="int_test_a",ship=None,system=None,limit=100)),
                ("sync_station_offers",dict(cursor=None,limit=1000)),
            ):
                conn.execute("SET search_path=baseline,public")
                expected=call(conn,old_api,function,**kwargs)
                conn.execute("SET search_path=optimized,public")
                actual=call(conn,api,function,**kwargs)
                assert actual==expected,(label,function)
                compared+=1
            if unchanged:
                assert changed[1]==0,(label,"Unchanged normalized rows were rewritten")
            conn.commit()
            steps.append(dict(case=label,legacyMs=elapsed[0],optimizedMs=elapsed[1],
                              legacyChangedRows=changed[0],optimizedChangedRows=changed[1]))
        replay("initial",row(["int_test_a","int_test_b","int_test_c"]))
        replay("new_observation_same_inventory",row(["int_test_a","int_test_b","int_test_c"],second=1),True)
        priced=[dict(name="int_test_a",id=1,buyPrice=100,buyMercCoinsPrice=3,
                     priceObservedAt=(base+timedelta(seconds=2)).isoformat(),priceSource="exact"),
                "int_test_b","int_test_c"]
        replay("exact_prices",row(priced,second=2,source="EDDN outfitting/3"))
        replay("v2_preserves_exact_price_proof",row(["int_test_a","int_test_b","int_test_c"],second=3),True)
        replay("older_inventory_ignored",row(["int_test_b"],second=1),True)
        replay("same_observation_new_receipt",row(["int_test_a","int_test_b","int_test_c"],second=3),True)
        revised=[dict(name="int_test_a",id=2,buyPrice=125,
                      priceObservedAt=(base+timedelta(seconds=3)).isoformat(),priceSource="corrected"),
                 "int_test_b","int_test_c"]
        replay("equal_timestamp_price_correction",row(revised,second=3,source="EDDN outfitting/3"))
        stale=[dict(name="int_test_a",id=2,buyPrice=1,
                    priceObservedAt=base.isoformat(),priceSource="old"),"int_test_b"]
        replay("stale_price_and_removed_item",row(stale,second=4,source="EDDN outfitting/3"))
        replay("removed_item_reappears",row(["int_test_a","int_test_b","int_test_c"],second=5))
        replay("missing_id_does_not_erase_known_id",row(["int_test_a","int_test_b","int_test_c"],second=6),True)
        replay("newer_same_price_is_fresh_price_proof",row([{**item,"priceObservedAt":(base+timedelta(seconds=7)).isoformat()} if isinstance(item,dict) else item for item in revised],second=7,source="EDDN outfitting/3"))
        # Duplicate retained names must preserve the first object, as LIMIT 1 did.
        for schema in ("baseline","optimized"):
            conn.execute("SET search_path="+schema+",public")
            conn.execute("UPDATE station_outfitting SET modules = modules || %s::jsonb WHERE market_id=42",
                         (json.dumps([dict(name="INT_TEST_A",id=999,buyPrice=999)]),))
        replay("first_retained_object_wins",row(["int_test_a","int_test_b","int_test_c"],second=8),True)
        for schema in ("baseline","optimized"):
            conn.execute("SET search_path="+schema+",public")
            conn.execute("UPDATE station_outfitting SET modules = modules || '[null, {\"other\":\"field\"}]'::jsonb WHERE market_id=42")
        replay("unknown_retained_entries",row(["int_test_a","int_test_b","int_test_c"],second=9),True)
        replay("empty_inventory",row([],second=10))
        replay("after_empty",row(["int_test_a"],second=11))
        large=[dict(name=f"int_benchmark_{i:04}",id=i,buyPrice=100+i,
                    priceObservedAt=base.isoformat(),priceSource="exact") for i in range(1200)]
        replay("large_exact_inventory",row(large,second=0,source="EDDN outfitting/3",market_id=9000))
        replay("large_availability_refresh",row([r["name"] for r in large],second=1,market_id=9000),True)
        # Shipyard and partial purchases retain their existing per-item model.
        for schema,writer in (("baseline",old),("optimized",database)):
            conn.execute("SET search_path="+schema+",public")
            writer.upsert_station_offer_batch(conn,[row(["anaconda","python"],kind="SHIPYARD",second=0)])
            purchase=row([dict(name="python",buyPrice=12345)],kind="SHIPYARD",second=1,
                         source="ED-Frame Journal Ã‚Â· ShipyardBuy")
            purchase["partial_inventory"]=True;purchase["station_type"]="Orbis";purchase["fleet_carrier"]=False
            writer.upsert_station_offer_batch(conn,[purchase])
        snapshots=[]
        for schema in ("baseline","optimized"):
            conn.execute("SET search_path="+schema+",public")
            snapshots.append(conn.execute("SELECT * FROM station_ship_offers ORDER BY market_id,ship_symbol").fetchall())
        assert snapshots[0]==snapshots[1],"Partial ship purchase changed"
        emit(mode="synthetic",endpointComparisons=compared,steps=steps,
             fullLogicalDataIdentical=True,shipyardPartialPurchase="PASS",result="PASS")


def same_offer_page(actual,expected):
    # The existing ORDER BY has no tie-breaker for equally fresh stations.
    # Compare every row/field including duplicate joins, and the entire ordered
    # freshness sequence; don't turn unspecified ties into a false data failure.
    ar,er=actual["results"],expected["results"]
    assert {k:v for k,v in actual.items() if k!="results"}=={k:v for k,v in expected.items() if k!="results"}
    encode=lambda row:json.dumps(row,sort_keys=True,default=str)
    assert sorted(map(encode,ar))==sorted(map(encode,er)), "Offer facts or selected stations changed"
    def freshness(row):
        return max(row.get("outfittingObservedAt") or datetime.min.replace(tzinfo=timezone.utc),
                   row.get("shipyardObservedAt") or datetime.min.replace(tzinfo=timezone.utc))
    assert list(map(freshness,ar))==list(map(freshness,er)), "Freshness ordering changed"


def live_readonly(legacy_dir):
    old_api=load("_baseline_api",legacy_dir/"api.py")
    with connection() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        conn.execute("SET LOCAL statement_timeout='20s'")
        conn.execute("SET LOCAL lock_timeout='2s'")
        symbols=[r["module_symbol"] for r in conn.execute("""
            SELECT module_symbol FROM station_module_offers
            WHERE market_id=(SELECT market_id FROM station_outfitting ORDER BY received_at DESC LIMIT 1)
            ORDER BY module_symbol LIMIT 4""").fetchall()]
        assert symbols
        for symbol in symbols:
            kwargs=dict(module=symbol,ship=None,system=None,limit=200)
            start=time.monotonic();expected=call(conn,old_api,"search_station_offers",**kwargs);legacy_ms=(time.monotonic()-start)*1000
            start=time.monotonic();actual=call(conn,api,"search_station_offers",**kwargs);new_ms=(time.monotonic()-start)*1000
            # Equal-time ties have never had a tie-breaker; compare row identities
            # and every field when an entire equal-time group fits the page.
            same_offer_page(actual,expected)
            emit(case="module_reader",rows=len(actual["results"]),legacyMs=round(legacy_ms,3),
                 optimizedMs=round(new_ms,3),identical=True)
        for kwargs in (dict(module=None,ship="anaconda",system=None,limit=100),
                       dict(module=symbols[0],ship="anaconda",system=None,limit=100)):
            same_offer_page(call(conn,api,"search_station_offers",**kwargs),call(conn,old_api,"search_station_offers",**kwargs))
        emit(mode="live-readonly",comparisons=len(symbols)+2,result="PASS")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--synthetic",action="store_true")
    modes.add_argument("--live-readonly",action="store_true")
    parser.add_argument("--legacy-dir",type=Path,default=Path("/baseline"))
    args=parser.parse_args()
    synthetic(args.legacy_dir) if args.synthetic else live_readonly(args.legacy_dir)
