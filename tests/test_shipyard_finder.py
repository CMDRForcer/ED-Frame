import unittest
from pathlib import Path

from ed_companion.navigation.shipyard_finder import (
    build_module_catalog,
    build_module_families,
    build_permit_rules,
    build_ship_catalog,
    catalog_suggestions,
    evaluate_ship_access,
    evaluate_station_access,
    module_catalog_with_ship_fit,
    rank_station_offers,
    ship_catalog_with_access,
)


class ShipyardFinderTests(unittest.TestCase):
    def test_static_ship_reference_dump_covers_the_full_local_catalog(self):
        import json

        ships = json.loads(Path("ed_data/ships.json").read_text(encoding="utf-8"))
        prices = json.loads(Path(
            "ed_data/ship_reference_prices.json"
        ).read_text(encoding="utf-8"))
        expected = {
            str(row["symbol"]).casefold() for row in ships
            if isinstance(row, dict) and row.get("symbol")
        }
        actual = set(prices["ships"])
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 48)
        self.assertTrue(all(
            isinstance(row.get("referencePrice"), int)
            and row["referencePrice"] > 0
            and row.get("source")
            for row in prices["ships"].values()
        ))
        self.assertEqual(prices["ships"]["mandalay"]["referencePrice"], 17639220)
        self.assertEqual(
            prices["ships"]["mediumtransport01"]["referencePrice"], 69289470,
        )

    def test_catalog_suggestions_match_names_symbols_and_manufacturers(self):
        modules = build_module_catalog({"modules": {
            "hpt_fragcannon_fixed_medium": ["FRAGMENT CANNON", "2A"],
        }})
        self.assertEqual(catalog_suggestions(modules, "frag")[0]["sizeRating"], "2A")
        self.assertEqual(catalog_suggestions(modules, "frag")[0]["mount"], "FIXED")
        self.assertEqual(modules[0]["moduleClass"], "2")
        self.assertEqual(modules[0]["moduleRating"], "A")
        self.assertEqual(modules[0]["schematicKind"], "FRAGMENT")
        self.assertEqual(modules[0]["moduleGroup"], "HARDPOINTS")
        ships = build_ship_catalog([{
            "symbol": "CobraMkIII", "name": "Cobra Mk III",
            "manufacturer": "Faulcon DeLacy", "size": "small",
        }], {"capturedAt": "2026-10-06", "ships": {
            "cobramkiii": {
                "referencePrice": 349718, "source": "EDCD/coriolis-data",
            },
        }})
        self.assertEqual(catalog_suggestions(ships, "faulcon")[0]["symbol"], "cobramkiii")
        self.assertEqual(ships[0]["schematicSource"], "assets/ships/CobraMkIII.svg")
        self.assertEqual(ships[0]["referencePrice"], 349718)
        page = Path("qml/pages/ShipyardPage.qml").read_text(encoding="utf-8")
        self.assertIn('Qt.resolvedUrl("../../" + path)', page)

    def test_result_rows_declare_the_qml_index_they_use(self):
        page = Path("qml/pages/ShipyardPage.qml").read_text(encoding="utf-8")
        self.assertIn(
            "required property var modelData\n"
            "                                    required property int index",
            page,
        )

    def test_commander_subpages_only_materialize_the_visible_model(self):
        page = Path("Main.qml").read_text(encoding="utf-8")
        self.assertIn(
            "property var fleetRows: activeSection === 2 ? "
            "(cockpit.commanderFleet || []) : []",
            page,
        )
        self.assertIn("model: visible ? commanderPage.cardOrder : []", page)
        self.assertIn("model: visible ? commanderPage.fleetRows : []", page)
        self.assertIn("property bool commanderPagePrimed: false", page)
        self.assertIn("active: window.commanderPagePrimed || smokeTest", page)
        self.assertIn("asynchronous: true", page)

    def test_module_shop_groups_and_families_match_outfitting_structure(self):
        modules = build_module_catalog({"modules": {
            "hpt_fragcannon_fixed_medium": ["FRAGMENT CANNON", "2A"],
            "hpt_fragcannon_gimbal_large": ["FRAGMENT CANNON", "3C"],
            "hpt_chafflauncher_tiny": ["CHAFF LAUNCHER", "0I"],
            "int_powerplant_size4_class5": ["POWER PLANT", "4A"],
            "int_cargorack_size4_class1": ["CARGO RACK", "4E"],
        }})
        groups = {row["displayName"]: row["moduleGroup"] for row in modules}
        self.assertEqual(groups["FRAGMENT CANNON"], "HARDPOINTS")
        self.assertEqual(groups["CHAFF LAUNCHER"], "UTILITY")
        self.assertEqual(groups["POWER PLANT"], "CORE")
        self.assertEqual(groups["CARGO RACK"], "OPTIONAL")
        departments = {
            row["displayName"]: row["moduleDepartment"] for row in modules
        }
        self.assertEqual(departments["FRAGMENT CANNON"], "KINETIC")
        self.assertEqual(departments["CHAFF LAUNCHER"], "DEFENCE")
        self.assertEqual(departments["POWER PLANT"], "POWER")
        self.assertEqual(departments["CARGO RACK"], "CARGO")
        families = build_module_families(modules)
        fragment = next(
            row for row in families if row["moduleFamily"] == "FRAGMENT CANNON"
        )
        self.assertEqual(fragment["variantCount"], 2)
        self.assertEqual(fragment["classLabel"], "CLASS 2–3")
        self.assertIn("FIXED", fragment["mountLabel"])

    def test_current_ship_fit_uses_physical_group_size_and_core_slot(self):
        modules = build_module_catalog({"modules": {
            "hpt_fragcannon_fixed_medium": ["FRAGMENT CANNON", "2A"],
            "hpt_fragcannon_fixed_large": ["FRAGMENT CANNON", "3A"],
            "int_powerplant_size4_class5": ["POWER PLANT", "4A"],
            "int_powerplant_size5_class5": ["POWER PLANT", "5A"],
        }})
        annotated = module_catalog_with_ship_fit(modules, [
            {"group": "HARDPOINTS", "slot": "MediumHardpoint1", "slotSize": 2},
            {"group": "CORE INTERNALS", "slot": "PowerPlant", "slotSize": 4},
        ])
        states = {row["symbol"]: row["currentShipFitStatus"] for row in annotated}
        self.assertEqual(states["hpt_fragcannon_fixed_medium"], "FITS")
        self.assertEqual(states["hpt_fragcannon_fixed_large"], "INCOMPATIBLE")
        self.assertEqual(states["int_powerplant_size4_class5"], "FITS")
        self.assertEqual(states["int_powerplant_size5_class5"], "INCOMPATIBLE")

    def test_rank_locked_hulls_are_red_ready_and_explain_the_requirement(self):
        item = {"symbol": "Federation_Corvette", "displayName": "Federal Corvette"}
        missing = evaluate_ship_access(item, {"ranks": [
            {"key": "Federation", "known": True, "rank": 7},
        ]})
        self.assertEqual(missing["purchaseStatus"], "RANK REQUIRED")
        self.assertEqual(missing["purchaseTone"], "LOCKED")
        self.assertIn("Rear Admiral", missing["purchaseReason"])
        self.assertIn("rank 7", missing["purchaseReason"])

        confirmed = ship_catalog_with_access([item], {"ranks": [
            {"key": "Federation", "known": True, "rank": 12},
        ]})[0]
        self.assertEqual(confirmed["purchaseStatus"], "RANK CONFIRMED")
        self.assertEqual(confirmed["purchaseTone"], "CONFIRMED")

        unknown = evaluate_ship_access(item, {})
        self.assertEqual(unknown["purchaseStatus"], "RANK UNCONFIRMED")
        self.assertEqual(unknown["purchaseTone"], "UNKNOWN")

    def test_ship_catalog_matches_purchase_carousel_price_order(self):
        ships = build_ship_catalog([
            {"symbol": "Expensive", "name": "Expensive"},
            {"symbol": "Unknown", "name": "Unknown"},
            {"symbol": "Affordable", "name": "Affordable"},
        ], {"ships": {
            "expensive": {"referencePrice": 9000000, "source": "test"},
            "affordable": {"referencePrice": 100000, "source": "test"},
        }})
        self.assertEqual(
            [row["symbol"] for row in ships],
            ["affordable", "expensive", "unknown"],
        )

    def test_ship_catalog_places_known_rank_locks_at_the_right_end(self):
        ships = ship_catalog_with_access([
            {"symbol": "federation_dropship", "displayName": "Dropship",
             "referencePrice": 100000},
            {"symbol": "cobra_mk_iii", "displayName": "Cobra",
             "referencePrice": 9000000},
            {"symbol": "empire_courier", "displayName": "Courier",
             "referencePrice": 200000},
        ], {"ranks": [
            {"key": "Federation", "known": True, "rank": 0},
        ]})
        self.assertEqual(
            [row["symbol"] for row in ships],
            ["cobra_mk_iii", "empire_courier", "federation_dropship"],
        )
        self.assertEqual(
            [row["purchaseTone"] for row in ships],
            ["OPEN", "UNKNOWN", "LOCKED"],
        )

    def test_permit_evaluation_uses_journal_visit_explicit_permit_and_rank(self):
        rules = build_permit_rules({
            "Engineer": {"permit": {
                "name": "Founders World permit", "system": "Shinrarta Dezhra",
                "method": "Reach Elite rank.",
                "rule": {"type": "anyRank", "fields": ["Combat", "Trade"], "minimum": 8},
            }},
        })
        visited = evaluate_station_access(
            "Shinrarta Dezhra", {"visitedSystems": ["Shinrarta Dezhra"]}, rules,
        )
        self.assertEqual(visited["accessStatus"], "CONFIRMED")
        explicit = evaluate_station_access(
            "Shinrarta Dezhra", {"permits": ["Founders World permit"]}, rules,
        )
        self.assertEqual(explicit["accessStatus"], "CONFIRMED")
        ranked = evaluate_station_access("Shinrarta Dezhra", {"ranks": [
            {"key": "Combat", "known": True, "rank": 8},
            {"key": "Trade", "known": True, "rank": 2},
        ]}, rules)
        self.assertEqual(ranked["accessStatus"], "CONFIRMED")
        missing = evaluate_station_access("Shinrarta Dezhra", {"ranks": [
            {"key": "Combat", "known": True, "rank": 7},
            {"key": "Trade", "known": True, "rank": 7},
        ]}, rules)
        self.assertEqual(missing["accessTone"], "LOCKED")
        unconfirmed = evaluate_station_access(
            "Shinrarta Dezhra", {}, rules,
        )
        self.assertEqual(unconfirmed["accessTone"], "LOCKED")
        self.assertEqual(unconfirmed["accessStatus"], "PERMIT NOT CONFIRMED")
        self.assertIn("No Journal proof", unconfirmed["accessReason"])
        self.assertEqual(
            evaluate_station_access("Sol", {}, rules)["accessStatus"], "OPEN",
        )

    def test_confirmed_only_filter_keeps_open_and_confirmed_access(self):
        rows = [
            {"system": "Open", "station": "Port", "coordinates": [1, 0, 0],
             "landingPadSize": "L", "shipOffer": {}},
            {"system": "Locked", "station": "Port", "coordinates": [2, 0, 0],
             "landingPadSize": "L", "shipOffer": {}},
        ]
        rules = {"locked": {"name": "Locked permit", "method": "Mission", "rule": {"type": "faction"}}}
        result = rank_station_offers(
            rows, kind="SHIPS", origin_coordinates=[0, 0, 0],
            access_filter="CONFIRMED ONLY", permit_rules=rules,
        )
        self.assertEqual([row["system"] for row in result], ["Open"])

    def test_ship_rank_and_system_permit_reasons_remain_separate(self):
        rows = [{
            "system": "Shinrarta Dezhra", "station": "Jameson Memorial",
            "coordinates": [1, 0, 0], "landingPadSize": "L",
            "shipOffer": {}, "observedAt": "2026-10-06T19:00:00Z",
            "distanceToArrivalLs": 684,
        }]
        permits = {"shinrarta dezhra": {
            "name": "Founders World permit", "method": "Reach Elite rank",
            "rule": {"type": "anyRank", "fields": ["Combat"], "minimum": 8},
        }}
        result = rank_station_offers(
            rows, kind="SHIPS", origin_coordinates=[0, 0, 0],
            item={"symbol": "federation_corvette", "size": "large"},
            commander_overview={"ranks": [
                {"key": "Combat", "known": True, "rank": 7},
                {"key": "Federation", "known": True, "rank": 7},
            ]}, permit_rules=permits,
        )[0]
        self.assertEqual(result["systemAccessStatus"], "PERMIT MISSING")
        self.assertEqual(result["purchaseStatus"], "RANK REQUIRED")
        self.assertEqual(result["accessTone"], "LOCKED")
        self.assertIn("PAD", result["recommendationReason"])
        self.assertIn("684 LS", result["recommendationReason"])

        filtered = rank_station_offers(
            rows, kind="SHIPS", origin_coordinates=[0, 0, 0],
            item={"symbol": "federation_corvette", "size": "large"},
            commander_overview={"ranks": [
                {"key": "Combat", "known": True, "rank": 7},
                {"key": "Federation", "known": True, "rank": 7},
            ]}, permit_rules=permits, access_filter="ACCESSIBLE ONLY",
        )
        self.assertEqual(filtered, [])

    def test_ship_ranking_uses_fixed_reference_not_untrusted_observations(self):
        rows = [
            {"marketId": 1, "system": "A", "station": "One", "coordinates": [2, 0, 0],
             "landingPadSize": "L", "shipOffer": {"buyPrice": 100, "priceType": "BASE_PRICE"}},
            {"marketId": 2, "system": "B", "station": "Two", "coordinates": [3, 0, 0],
             "landingPadSize": "L", "shipOffer": {"buyPrice": 120, "priceObservedAt": "2026-10-06T10:00:00Z"}},
            {"marketId": 3, "system": "C", "station": "Three", "coordinates": [1, 0, 0],
             "landingPadSize": "L", "shipOffer": {}},
        ]
        result = rank_station_offers(
            rows, kind="SHIPS", origin_coordinates=[0, 0, 0],
            max_distance_ly=10,
            item={"size": "large", "referencePrice": 150},
        )
        self.assertEqual([row["priceStatus"] for row in result], [
            "REFERENCE", "REFERENCE", "REFERENCE",
        ])
        self.assertTrue(all(row["price"] == 150 for row in result))

    def test_reference_station_rule_and_purchase_form_price_hierarchy(self):
        rows = [{
            "marketId": 1, "system": "A", "station": "One",
            "coordinates": [1, 0, 0], "landingPadSize": "M",
            "shipOffer": {},
        }]
        item = {
            "size": "medium", "referencePrice": 17639220,
            "referencePriceSource": "EDCD/coriolis-data",
        }
        reference = rank_station_offers(
            rows, kind="SHIPS", origin_coordinates=[0, 0, 0], item=item,
        )[0]
        self.assertEqual(reference["price"], 17639220)
        self.assertEqual(reference["priceStatus"], "REFERENCE")

        discounted = rank_station_offers(
            [{**rows[0], "system": "Shinrarta Dezhra",
              "station": "Jameson Memorial"}],
            kind="SHIPS", origin_coordinates=[0, 0, 0], item=item,
            price_rules={"rules": [{
                "system": "Shinrarta Dezhra",
                "station": "Jameson Memorial",
                "priceAdjustmentBps": -1000,
                "label": "10% Founders World discount",
            }]},
        )[0]
        self.assertEqual(discounted["price"], 15875298)
        self.assertEqual(discounted["priceStatus"], "DISCOUNTED")

        rows[0]["shipOffer"] = {
            "buyPrice": 17000001,
            "priceObservedAt": "2026-10-06T20:00:00Z",
            "priceSource": "ED-Frame Journal · ShipyardBuy",
        }
        observed = rank_station_offers(
            rows, kind="SHIPS", origin_coordinates=[0, 0, 0], item=item,
        )[0]
        self.assertEqual(observed["price"], 17000001)
        self.assertEqual(observed["priceStatus"], "PURCHASE CONFIRMED")

    def test_range_and_required_ship_pad_are_hard_filters(self):
        rows = [
            {"system": "Near", "station": "Small", "coordinates": [1, 0, 0],
             "landingPadSize": "S", "shipOffer": {}},
            {"system": "Far", "station": "Large", "coordinates": [20, 0, 0],
             "landingPadSize": "L", "shipOffer": {}},
            {"system": "Near", "station": "Large", "coordinates": [2, 0, 0],
             "landingPadSize": "L", "shipOffer": {}},
        ]
        result = rank_station_offers(
            rows, kind="SHIPS", origin_coordinates=[0, 0, 0],
            max_distance_ly=10, item={"size": "large"},
        )
        self.assertEqual([(row["system"], row["station"]) for row in result], [
            ("Near", "Large"),
        ])


if __name__ == "__main__":
    unittest.main()
