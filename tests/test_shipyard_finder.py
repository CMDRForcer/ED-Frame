import unittest
from pathlib import Path

from ed_companion.navigation.shipyard_finder import (
    build_module_catalog,
    build_permit_rules,
    build_ship_catalog,
    catalog_suggestions,
    evaluate_station_access,
    rank_station_offers,
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

    def test_ranking_preserves_unknown_price_and_prefers_observed(self):
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
            max_distance_ly=10, item={"size": "large"},
        )
        self.assertEqual([row["priceStatus"] for row in result], [
            "OBSERVED", "UNKNOWN", "UNKNOWN",
        ])
        self.assertFalse(result[-1]["priceKnown"])

    def test_catalog_reference_is_not_presented_as_a_station_price(self):
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
        self.assertIsNone(reference["price"])
        self.assertEqual(reference["priceStatus"], "UNKNOWN")

        rows[0]["shipOffer"] = {
            "buyPrice": 17000000,
            "priceObservedAt": "2026-10-06T20:00:00Z",
        }
        observed = rank_station_offers(
            rows, kind="SHIPS", origin_coordinates=[0, 0, 0], item=item,
        )[0]
        self.assertEqual(observed["price"], 17000000)
        self.assertEqual(observed["priceStatus"], "OBSERVED")

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
