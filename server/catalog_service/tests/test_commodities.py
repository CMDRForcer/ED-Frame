import unittest
import asyncio
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit
from unittest.mock import MagicMock, patch
import requests
from fastapi import HTTPException
from psycopg.errors import QueryCanceled, LockNotAvailable
from edframe_catalog.api import app, catalog_commodities, commodity_offers
from ed_companion.navigation.commodity_search import fetch_commodity_offers, describe_commodity_offers


def api_get(params, path="/v1/markets/commodity-offers"):
    """Drive HTTP validation and JSON output without a listening HTTP server."""
    messages = []
    async def request():
        scope = dict(type="http", method="GET", path=path,
            raw_path=path.encode(), query_string=urlencode(params).encode(),
            headers=[], http_version="1.1", scheme="http", root_path="",
            server=("test",80), client=("127.0.0.1",1234))
        async def receive():
            return {"type":"http.request", "body":b"", "more_body":False}
        async def send(message):
            messages.append(message)
        await asyncio.wait_for(app(scope, receive, send), timeout=5)
    asyncio.run(request())
    response = requests.Response()
    response.status_code = next(m["status"] for m in messages if m["type"] == "http.response.start")
    response._content = b"".join(m.get("body",b"") for m in messages if m["type"] == "http.response.body")
    response.url = "http://test/v1/markets/commodity-offers"
    return response


class CommodityApiTests(unittest.TestCase):
    def test_sorting_is_in_sql_before_page_limit_and_confirmed(self):
        for direction, price, order in (("BUY", "buy_price", "ASC"), ("SELL", "sell_price", "DESC")):
            for sorting, prefix in (("PRICE", f"m.{price} {order}"),
                    ("DISTANCE", '"distanceLy"'), ("AGE", "m.observed_at DESC")):
                conn = MagicMock(); conn.execute.return_value.fetchall.return_value = []
                with patch("edframe_catalog.api.connection") as factory:
                    factory.return_value.__enter__.return_value = conn
                    payload = commodity_offers("gold", direction, 0,0,0, sort_by=sorting)
                sql = conn.execute.call_args.args[0]
                self.assertIn("ORDER BY " + prefix, sql)
                self.assertLess(sql.rfind("ORDER BY " + prefix), sql.rfind("LIMIT %s"))
                self.assertEqual(payload["sortBy"], sorting)
        with patch("edframe_catalog.api.connection") as factory:
            self.assertEqual(api_get(dict(commodity="gold",direction="BUY",x=0,y=0,z=0,sort_by="bad")).status_code,422)
            factory.assert_not_called()

    def test_group_uses_one_bounded_query(self):
        conn=MagicMock(); conn.execute.return_value.fetchall.return_value=[]
        with patch("edframe_catalog.api.connection") as factory:
            factory.return_value.__enter__.return_value=conn
            result=commodity_offers("all_rare_goods","BUY",0,0,0,
                commodities="lavianbrandy,eraninpearlwhisky",limit=100)
        sql,values=conn.execute.call_args.args
        self.assertIn("m.commodity = ANY(%s)",sql)
        self.assertEqual(values[3],["eraninpearlwhisky","lavianbrandy"])
        self.assertEqual(result["commodities"],values[3])
        self.assertEqual(conn.execute.call_count,1)
    def test_catalog_index_walk_no_whitelist(self):
        conn=MagicMock(); conn.execute.return_value.fetchall.return_value=[{"commodity":"new"}]
        with patch("edframe_catalog.api.connection") as factory:
            factory.return_value.__enter__.return_value=conn
            self.assertEqual(catalog_commodities()["results"],["new"])
        self.assertIn("WITH RECURSIVE",conn.execute.call_args.args[0])

    def test_buy_sell_bounded_filters_and_pads(self):
        for direction,price,quantity,order in (("BUY","buy_price","stock","ASC"),("SELL","sell_price","demand","DESC")):
            conn=MagicMock(); conn.execute.return_value.fetchall.return_value=[{},{}]
            with patch("edframe_catalog.api.connection") as factory:
                factory.return_value.__enter__.return_value=conn
                result=commodity_offers("platinum",direction,0,0,0,landing_pad="M",limit=1)
            sql,values=conn.execute.call_args.args
            self.assertIn(f"m.{price} AS price",sql)
            self.assertIn(f"m.{quantity} >= %s",sql)
            self.assertIn(f"ORDER BY m.{price} {order}",sql)
            self.assertIn("st.fleet_carrier IS NOT TRUE",sql)
            self.assertEqual(values[-2:],(["M","L"],2))
            self.assertTrue(result["hasMore"])

    def test_unlimited_has_no_radius_clause_but_retains_filters_order_and_result_limit(self):
        for direction,price,quantity,order in (("BUY","buy_price","stock","ASC"),("SELL","sell_price","demand","DESC")):
            conn=MagicMock(); conn.execute.return_value.fetchall.return_value=[{"distanceLy":90000}]*101
            with patch("edframe_catalog.api.connection") as factory:
                factory.return_value.__enter__.return_value=conn
                result=commodity_offers("lithiumhydroxide",direction,1,2,3,max_distance=0,
                    min_quantity=10,max_age_hours=72,landing_pad="L",exclude_fleet_carriers=False)
            sql,values=conn.execute.call_args.args
            self.assertNotIn("<= POWER(%s, 2)",sql)
            self.assertIn("SQRT(POWER(s.x - %s",sql)
            self.assertIn(f"m.{quantity} >= %s",sql)
            self.assertIn("m.observed_at >= NOW()",sql)
            self.assertIn("st.landing_pad_size = ANY(%s)",sql)
            self.assertNotIn("st.fleet_carrier IS NOT TRUE",sql)
            self.assertIn(f"ORDER BY m.{price} {order}",sql)
            self.assertEqual(values,(1,2,3,"lithiumhydroxide",10,72,["L"],101))
            self.assertEqual(len(result["results"]),100)
            self.assertTrue(result["hasMore"])
            self.assertEqual(result["region"],{"origin":[1,2,3],"radiusLy":None})
            self.assertEqual([call.args[0] for call in conn.execute.call_args_list[:3]],[
                "SET TRANSACTION READ ONLY", "SET LOCAL statement_timeout = '10s'",
                "SET LOCAL lock_timeout = '2s'"])

    def test_unlimited_rare_group_and_explicit_carrier_exclusion_are_supported(self):
        conn=MagicMock(); conn.execute.return_value.fetchall.return_value=[]
        with patch("edframe_catalog.api.connection") as factory:
            factory.return_value.__enter__.return_value=conn
            result=commodity_offers("all_rare_goods","BUY",0,0,0,max_distance=0,
                commodities="lavianbrandy,eraninpearlwhisky")
        sql,values=conn.execute.call_args.args
        self.assertIn("m.commodity = ANY(%s)",sql)
        self.assertIn("st.fleet_carrier IS NOT TRUE",sql)
        self.assertEqual(values[3],["eraninpearlwhisky","lavianbrandy"])
        self.assertEqual(result["commodities"],values[3])
        self.assertIsNone(result["region"]["radiusLy"])

    def test_global_timeouts_return_retryable_error(self):
        for error in (QueryCanceled,LockNotAvailable):
            conn=MagicMock()
            def execute(sql,*args):
                if sql.lstrip().startswith("SELECT m.market_id"):
                    raise error("synthetic timeout")
                return MagicMock()
            conn.execute.side_effect=execute
            with self.subTest(error=error), patch("edframe_catalog.api.connection") as factory:
                factory.return_value.__enter__.return_value=conn
                with self.assertRaises(HTTPException) as raised:
                    commodity_offers("gold","BUY",0,0,0,max_distance=0)
                self.assertEqual(raised.exception.status_code,503)

    def test_actual_http_validation_and_app_parser_agree_on_unlimited(self):
        conn=MagicMock(); conn.execute.return_value.fetchall.return_value=[dict(
            commodity="lithiumhydroxide", buyPrice=100, sellPrice=90, stock=50, demand=30,
            fleetCarrier=True, landingPadSize="L", station="TEST-01", system="Distant test system",
            distanceLy=40000, observedAt=datetime.now(timezone.utc))]
        def get(url, *, params, timeout):
            self.assertEqual(urlsplit(url).path,"/v1/markets/commodity-offers")
            return api_get(params)
        with patch("edframe_catalog.api.connection") as factory:
            factory.return_value.__enter__.return_value=conn
            result=fetch_commodity_offers(commodity="lithiumhydroxide",direction="BUY",
                origin=[0,0,0],radius=0,pad="L",get=get)
        shown=describe_commodity_offers(result["results"])
        self.assertEqual(len(shown),1)
        self.assertEqual(shown[0]["distanceLy"],40000)
        self.assertTrue(shown[0]["carrierWarning"])
        for radius in (-1,2001,"inf"):
            with self.subTest(radius=radius), patch("edframe_catalog.api.connection") as factory:
                response=api_get(dict(commodity="gold",direction="BUY",x=0,y=0,z=0,max_distance=radius))
                self.assertEqual(response.status_code,422)
                factory.assert_not_called()
