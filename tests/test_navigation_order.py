import unittest

from ed_companion.phase14.controller import (
    NAVIGATION_IDS,
    initial_navigation_order,
)


class NavigationOrderTests(unittest.TestCase):
    def test_default_navigation_matches_product_order(self):
        self.assertEqual(
            NAVIGATION_IDS,
            (
                "operations", "engineering", "wishlist", "engineers", "materials",
                "mining-finder", "state-finds", "powerplay", "cmdr", "logbook",
                "exploration", "exobiology", "missions", "nav", "settings",
            ),
        )

    def test_previous_default_is_migrated(self):
        previous_default = [
            "operations", "engineering", "wishlist", "engineers", "materials",
            "state-finds", "mining-finder", "cmdr", "logbook", "settings",
            "powerplay",
        ]
        self.assertEqual(initial_navigation_order(previous_default), list(NAVIGATION_IDS))

    def test_previous_release_default_places_nav_before_settings(self):
        previous_default = [
            "operations", "engineering", "wishlist", "engineers", "materials",
            "mining-finder", "state-finds", "powerplay", "cmdr", "logbook",
            "exobiology", "missions", "settings",
        ]
        self.assertEqual(initial_navigation_order(previous_default), list(NAVIGATION_IDS))

    def test_custom_navigation_order_is_preserved(self):
        custom = list(reversed(NAVIGATION_IDS))
        self.assertEqual(initial_navigation_order(custom), custom)

    def test_new_exploration_page_is_inserted_next_to_exobiology(self):
        custom = [
            "operations", "engineering", "wishlist", "engineers", "materials",
            "exobiology", "missions", "settings",
        ]
        migrated = initial_navigation_order(custom)
        self.assertEqual(
            migrated.index("exploration"), migrated.index("exobiology") - 1
        )
        self.assertEqual(
            [item for item in migrated if item in custom], custom
        )

if __name__ == "__main__":
    unittest.main()
