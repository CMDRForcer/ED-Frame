import unittest
from unittest.mock import MagicMock, patch
from edframe_catalog.api import catalog_commodities, commodity_offers


class CommodityApiTests(unittest.TestCase):
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
