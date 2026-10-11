import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from types import SimpleNamespace
from ed_companion.phase14.controller_commodities import CommoditiesMixin
from ed_companion.navigation.commodity_search import (
    fetch_commodity_catalog, fetch_commodity_offers, commodity_reference,
    is_trade_commodity, describe_commodity_offers,
    commodity_search_region,
)
from ed_companion.navigation.mining_market import MiningMarketError


class CommoditySearchTests(unittest.TestCase):
    def test_requested_sort_is_sent_and_must_be_confirmed_by_server(self):
        for key in ("PRICE", "DISTANCE", "AGE"):
            payload = self.payload(); payload["sortBy"] = key
            get = self.get(payload)
            self.assertEqual(len(fetch_commodity_offers(commodity="gold", direction="BUY",
                origin=[0,0,0], sort_by=key, get=get)["results"]), 1)
            self.assertEqual(get.call_args.kwargs["params"]["sort_by"], key)
        with self.assertRaisesRegex(MiningMarketError, "sorting"):
            fetch_commodity_offers(commodity="gold", direction="BUY", origin=[0,0,0],
                sort_by="DISTANCE", get=self.get(self.payload()))
        get = Mock()
        with self.assertRaises(MiningMarketError):
            fetch_commodity_offers(commodity="gold", direction="BUY", origin=[0,0,0], sort_by="bad", get=get)
        get.assert_not_called()

    def test_manual_origin_resolution_runs_only_inside_network_worker(self):
        shell = self.shell()
        shell.commodityCatalog = []
        shell._launch_commodity_request = Mock()
        shell._state["system"] = "Sol"
        CommoditiesMixin.searchCommodities(shell, "gold", "BUY", 500, 10, 72, "L", False, " Cubeo ", "DISTANCE")
        kind, params = shell._launch_commodity_request.call_args.args
        self.assertIsNone(params["origin"])
        self.assertEqual((params["origin_system"], params["origin_mode"]), ("Cubeo", "MANUAL"))
        shell.commodityBusy = False
        shell.commoditiesFinished = Mock()
        shell._start_network_worker = Mock(return_value=True)
        with patch("ed_companion.phase14.controller_commodities.fetch_edframe_system_coordinates") as resolve, \
                patch("ed_companion.phase14.controller_commodities.fetch_commodity_offers") as offers:
            resolve.return_value = dict(system="Cubeo", coordinates=[10,20,30])
            offers.return_value = dict(results=[], hasMore=False)
            CommoditiesMixin._launch_commodity_request(shell, kind, params)
            resolve.assert_not_called(); offers.assert_not_called()
            shell._start_network_worker.call_args.args[0]()
            resolve.assert_called_once()
            self.assertEqual(offers.call_args.kwargs["origin"], [10,20,30])
            self.assertEqual(offers.call_args.kwargs["sort_by"], "DISTANCE")
        shell._state["currentPosition"] = [999,0,0]
        CommoditiesMixin._finish_commodities(shell, shell.commoditiesFinished.emit.call_args.args[0])
        self.assertEqual(shell._commodity_last_search["system"], "Cubeo")
        self.assertEqual(shell._commodity_last_search["quantity"], 10)
        self.assertEqual(shell._commodity_last_search["count"], 0)
        self.assertNotIn("Previous location", CommoditiesMixin.commodityStatus.fget(shell))
        shell._launch_commodity_request.reset_mock()
        CommoditiesMixin.searchCommodities(shell, "gold", "BUY", 0, 1, 24, "ANY", False, "cubeo", "AGE")
        cached = shell._launch_commodity_request.call_args.args[1]
        self.assertEqual(cached["region"], dict(origin=[10,20,30], radiusLy=None))

    def test_manual_origin_without_journal_is_allowed_but_journal_mode_needs_position(self):
        shell = self.shell(); shell._state = {}; shell.commodityCatalog = []
        shell._launch_commodity_request = Mock()
        CommoditiesMixin.searchCommodities(shell, "gold", "BUY", 100, 1, 24, "ANY", False)
        shell._launch_commodity_request.assert_not_called()
        CommoditiesMixin.searchCommodities(shell, "gold", "BUY", 100, 1, 24, "ANY", False, "Sol")
        self.assertEqual(shell._launch_commodity_request.call_args.args[1]["origin_mode"], "MANUAL")

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

    def test_known_trade_goods_catalog_deduplicates_and_ignores_unknowns(self):
        rows = fetch_commodity_catalog(get=self.get(dict(results=["gold","water","brandnew","gold"])))
        self.assertEqual({r["id"] for r in rows}, {"gold","water"})

    def test_mining_and_reward_goods_are_selectable_but_unclassified_cargo_is_not(self):
        reference = commodity_reference()
        for symbol in ("usscargoblackbox", "ancientrelic", "drones", "brandnew"):
            self.assertFalse(is_trade_commodity(symbol, reference), symbol)
        rows=fetch_commodity_catalog(get=self.get(dict(results=["gold","water","platinum","osmium",
            "painite","lithiumhydroxide","bromellite","usscargoblackbox","ancientrelic",
            "drones","brandnew","modularterminals"])))
        self.assertEqual({r["id"] for r in rows},{"gold","water","platinum","osmium",
            "painite","lithiumhydroxide","bromellite","modularterminals"})

    def test_rare_purchases_have_own_category_even_if_salvage_label(self):
        rows=fetch_commodity_catalog(get=self.get(dict(results=["lavianbrandy","eraninpearlwhisky","crystallinespheres"])))
        self.assertEqual(len(rows),3)
        self.assertTrue(all(r["category"]=="Rare Goods" and r["rare"] for r in rows))
        self.assertEqual(next(r for r in rows if r["id"]=="lavianbrandy")["tradeCategory"], "Legal Drugs")

    def test_carrier_only_purchases_survive_fetch_and_display_by_default(self):
        for symbol in ("lithiumhydroxide", "bromellite", "modularterminals", "platinum", "painite"):
            with self.subTest(symbol=symbol):
                payload = self.payload()
                payload["commodity"] = symbol
                payload["results"][0].update(commodity=symbol, fleetCarrier=True, system="Sol")
                get = self.get(payload)
                rows = fetch_commodity_offers(commodity=symbol, direction="BUY", origin=[0,0,0], get=get)["results"]
                self.assertFalse(get.call_args.kwargs["params"]["exclude_fleet_carriers"])
                shown = describe_commodity_offers(rows)
                self.assertEqual(len(shown), 1)
                self.assertEqual(shown[0]["commodityName"], commodity_reference()[symbol]["name"])
                self.assertEqual((shown[0]["price"], shown[0]["quantity"]), (100, 50))
                self.assertTrue(shown[0]["carrierWarning"])
                self.assertEqual(fetch_commodity_offers(commodity=symbol, direction="BUY", origin=[0,0,0],
                    exclude_carriers=True, get=get)["results"], [])
                self.assertTrue(get.call_args.kwargs["params"]["exclude_fleet_carriers"])

    def test_mined_goods_can_be_sold_to_normal_stations_with_carriers_excluded(self):
        payload = self.payload("SELL")
        payload["commodity"] = "lithiumhydroxide"
        payload["results"][0]["commodity"] = "lithiumhydroxide"
        rows = fetch_commodity_offers(commodity="lithiumhydroxide", direction="SELL", origin=[0,0,0],
            exclude_carriers=True, get=self.get(payload))["results"]
        self.assertEqual((rows[0]["price"], rows[0]["quantity"]), (200, 70))
        self.assertEqual(len(describe_commodity_offers(rows)), 1)

    def test_non_trade_cargo_cannot_be_requested_or_retained_as_result(self):
        for symbol in ("brandnew", "drones", "usscargoblackbox", "ancientrelic"):
            get = Mock()
            with self.subTest(symbol=symbol), self.assertRaises(MiningMarketError):
                fetch_commodity_offers(commodity=symbol, direction="BUY", origin=[0,0,0], get=get)
            get.assert_not_called()
            self.assertEqual(describe_commodity_offers([dict(commodity=symbol, system="Sol")]), [])


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
                pad="M",exclude_carriers=True,get=self.get(payload))["results"],[])

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

    def test_unlimited_accepts_distant_quotes_but_still_checks_offer_quality(self):
        payload = self.payload()
        payload["region"]["radiusLy"] = None
        payload["results"][0]["distanceLy"] = 90000
        get = self.get(payload)
        rows = fetch_commodity_offers(commodity="gold", direction="BUY", origin=[0,0,0], radius=0, get=get)["results"]
        self.assertEqual(rows[0]["distanceLy"], 90000)
        self.assertEqual(get.call_args.kwargs["params"]["max_distance"], 0)
        for change in ({"distanceLy":float("inf")}, {"distanceLy":-1}, {"buyPrice":0},
                       {"stock":0}, {"observedAt":"2020-01-01T00:00:00Z"}, {"commodity":"water"}):
            with self.subTest(change=change):
                invalid = {**payload, "results":[{**payload["results"][0], **change}]}
                self.assertEqual(fetch_commodity_offers(commodity="gold", direction="BUY", origin=[0,0,0],
                    radius=0, get=self.get(invalid))["results"], [])

    def test_unlimited_rare_group_preserves_confirmation(self):
        payload = self.payload()
        payload.update(commodity="all_rare_goods", commodities=["lavianbrandy"])
        payload["region"]["radiusLy"] = None
        payload["results"][0].update(commodity="lavianbrandy", distanceLy=22000)
        rows = fetch_commodity_offers(commodity="ALL_RARE_GOODS", commodities=["lavianbrandy"],
            direction="BUY", origin=[0,0,0], radius=0, get=self.get(payload))["results"]
        self.assertEqual(len(rows), 1)

    def test_unlimited_cannot_silently_accept_a_finite_response_from_an_old_server(self):
        get = self.get(self.payload())
        with self.assertRaisesRegex(MiningMarketError, "confirm"):
            fetch_commodity_offers(commodity="gold", direction="BUY", origin=[0,0,0], radius=0, get=get)
        get.return_value.status_code = 422
        with self.assertRaisesRegex(MiningMarketError, "server update"):
            fetch_commodity_offers(commodity="gold", direction="BUY", origin=[0,0,0], radius=0, get=get)

    def test_unlimited_is_explicit_and_still_needs_a_valid_origin(self):
        self.assertEqual(commodity_search_region([1,2,3], 0), {"origin":[1,2,3], "radiusLy":None})
        for radius in (-1, None, float("inf"), float("nan"), 2001):
            get = Mock()
            with self.subTest(radius=radius), self.assertRaises(MiningMarketError):
                fetch_commodity_offers(commodity="gold", direction="BUY", origin=[0,0,0], radius=radius, get=get)
            get.assert_not_called()
        self.assertIsNone(commodity_search_region([float("nan"),0,0], 0))

    def test_unlimited_retains_origin_guards_and_describes_the_scope(self):
        shell = self.shell()
        shell._commodity_request["params"]["region"]["radiusLy"] = None
        CommoditiesMixin._finish_commodities(shell, dict(id="job", generation=1, success=True,
            payload=dict(results=[{"station":"far away"}], hasMore=True)))
        self.assertEqual(shell._commodity_rows, [{"station":"far away"}])
        self.assertIn("unlimited", shell._commodity_status)
        self.assertIn("first 100", shell._commodity_status)
        self.assertNotIn("Previous location", CommoditiesMixin.commodityStatus.fget(shell))
        shell._state["currentPosition"] = [50,0,0]
        self.assertIn("Previous location", CommoditiesMixin.commodityStatus.fget(shell))
        shell = self.shell()
        shell._commodity_request["params"]["region"]["radiusLy"] = None
        shell._state["currentPosition"] = [50,0,0]
        CommoditiesMixin._finish_commodities(shell, dict(id="job", generation=1, success=True,
            payload=dict(results=[{"station":"wrong origin"}])))
        self.assertEqual(shell._commodity_rows, [{"station":"previous"}])

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
