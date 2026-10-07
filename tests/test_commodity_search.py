import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
from types import SimpleNamespace
from ed_companion.phase14.controller_commodities import CommoditiesMixin
from ed_companion.navigation.commodity_search import (
    fetch_commodity_catalog, fetch_commodity_offers, commodity_reference,
    is_standard_market_commodity, NON_PURCHASABLE_CARGO, describe_commodity_offers,
)
from ed_companion.navigation.mining_market import MiningMarketError


class CommoditySearchTests(unittest.TestCase):
    def test_all_rare_goods_single_request_and_group_confirmation(self):
        symbols = ["eraninpearlwhisky", "lavianbrandy"]
        payload = self.payload()
        payload.update(commodity="all_rare_goods", commodities=symbols)
        payload["results"][0]["commodity"] = "lavianbrandy"
        get = self.get(payload)
        result = fetch_commodity_offers(commodity="ALL_RARE_GOODS", commodities=symbols,
            direction="BUY", origin=[0, 0, 0], get=get)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.kwargs["params"]["commodities"], ",".join(symbols))
        payload["commodities"] = None
        with self.assertRaises(MiningMarketError):
            fetch_commodity_offers(commodity="ALL_RARE_GOODS", commodities=symbols,
                direction="BUY", origin=[0, 0, 0], get=self.get(payload))

    def test_all_rare_goods_rejects_normal_and_excluded_cargo(self):
        for symbols in (["gold"], ["platinum"], []):
            get = Mock()
            with self.assertRaises(MiningMarketError):
                fetch_commodity_offers(commodity="ALL_RARE_GOODS", commodities=symbols,
                    direction="BUY", origin=[0, 0, 0], get=get)
            get.assert_not_called()

    def get(self, payload):
        response = Mock()
        response.json.return_value = payload
        return Mock(return_value=response)

    def payload(self, direction="BUY"):
        return dict(direction=direction, commodity="gold", region=dict(origin=[0,0,0],radiusLy=100),
            results=[dict(commodity="gold", buyPrice=100, sellPrice=200, meanPrice=999,
                stock=50, demand=70, distanceLy=5, landingPadSize="L", fleetCarrier=False,
                observedAt=datetime.now(timezone.utc).isoformat())])

    def test_only_normal_market_goods_and_rare_goods(self):
        rows = fetch_commodity_catalog(get=self.get(dict(results=["gold","water","brandnew","gold"])))
        self.assertEqual({r["id"] for r in rows}, {"gold","water"})

    def test_mining_salvage_mission_limpets_and_unknown_removed(self):
        reference = commodity_reference()
        for symbol in NON_PURCHASABLE_CARGO | {"usscargoblackbox", "ancientrelic", "drones", "brandnew"}:
            self.assertFalse(is_standard_market_commodity(symbol, reference), symbol)
        rows=fetch_commodity_catalog(get=self.get(dict(results=["gold","water","platinum","osmium",
            "painite","usscargoblackbox","ancientrelic","drones","brandnew","modularterminals"])))
        self.assertEqual({r["id"] for r in rows},{"gold","water"})

    def test_rare_purchases_have_own_category_even_if_salvage_label(self):
        rows=fetch_commodity_catalog(get=self.get(dict(results=["lavianbrandy","eraninpearlwhisky","crystallinespheres"])))
        self.assertEqual(len(rows),3)
        self.assertTrue(all(r["category"]=="Rare Goods" and r["rare"] for r in rows))
        self.assertEqual(next(r for r in rows if r["id"]=="lavianbrandy")["tradeCategory"], "Legal Drugs")

    def test_excluded_symbol_cannot_be_requested_or_retained_as_result(self):
        get=Mock()
        with self.assertRaises(MiningMarketError):
            fetch_commodity_offers(commodity="platinum",direction="SELL",origin=[0,0,0],get=get)
        get.assert_not_called()
        self.assertEqual(describe_commodity_offers([dict(commodity="platinum",system="Sol")]),[])


    def test_buy_stock_sell_demand_not_mean(self):
        for direction, price, amount in (("BUY",100,50),("SELL",200,70)):
            rows = fetch_commodity_offers(commodity="gold", direction=direction, origin=[0,0,0],
                get=self.get(self.payload(direction)))["results"]
            self.assertEqual((rows[0]["price"],rows[0]["quantity"]),(price,amount))

    def test_invalid_unknown_stale_pad_carrier_excluded(self):
        for change in ({"buyPrice":None},{"stock":None},{"observedAt":"bad"},
                       {"observedAt":"2020-01-01T00:00:00Z"},{"landingPadSize":"S"},
                       {"fleetCarrier":True},{"distanceLy":101},{"distanceLy":float("nan")}):
            payload=self.payload(); payload["results"][0].update(change)
            self.assertEqual(fetch_commodity_offers(commodity="gold",direction="BUY",origin=[0,0,0],
                pad="M",get=self.get(payload))["results"],[])

    def test_region_and_direction_must_be_confirmed(self):
        for change in ({"region":None},{"direction":"SELL"},{"commodity":"water"}):
            payload=self.payload(); payload.update(change)
            with self.assertRaises(MiningMarketError):
                fetch_commodity_offers(commodity="gold",direction="BUY",origin=[0,0,0],get=self.get(payload))

    def test_invalid_search_does_not_request(self):
        get=Mock()
        with self.assertRaises(MiningMarketError):
            fetch_commodity_offers(commodity="gold",direction="BUY",origin=[],get=get)
        get.assert_not_called()

    def shell(self):
        region = dict(origin=[0,0,0],radiusLy=100)
        return SimpleNamespace(_commodity_request=dict(id="job",kind="offers",generation=1,
            params=dict(region=region,commodity="gold",direction="BUY"),system="Sol"),
            _profile_generation=1,_state=dict(currentPosition=[0,0,0]),_edframe_catalog_enabled=True,
            _commodity_rows=[{"station":"previous"}],commoditiesChanged=Mock())

    def test_failure_retains_rows_and_stale_request_is_ignored(self):
        shell=self.shell()
        CommoditiesMixin._finish_commodities(shell,dict(id="other",generation=1))
        self.assertIsNotNone(shell._commodity_request)
        CommoditiesMixin._finish_commodities(shell,dict(id="job",generation=1,success=False,error="timeout"))
        self.assertEqual(shell._commodity_rows,[{"station":"previous"}])
        self.assertIn("retained",shell._commodity_status)

    def test_changed_profile_or_location_does_not_merge(self):
        for change in ("profile","location","disabled"):
            shell=self.shell()
            if change=="profile": shell._profile_generation=2
            elif change=="location": shell._state["currentPosition"]=[50,0,0]
            else: shell._edframe_catalog_enabled=False
            CommoditiesMixin._finish_commodities(shell,dict(id="job",generation=1,success=True,
                payload=dict(results=[{"station":"wrong"}])))
            self.assertEqual(shell._commodity_rows,[{"station":"previous"}])

    def test_zero_price_and_zero_stock_are_not_offers(self):
        for field in ("buyPrice","stock"):
            payload=self.payload(); payload["results"][0][field]=0
            self.assertEqual(fetch_commodity_offers(commodity="gold",direction="BUY",origin=[0,0,0],
                get=self.get(payload))["results"],[])
