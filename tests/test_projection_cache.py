import unittest

from ed_companion.phase14.state_core import _PROJECTION_CACHE, memoize_projection


class MemoizeProjectionTests(unittest.TestCase):
    def setUp(self):
        _PROJECTION_CACHE.clear()

    def test_same_key_reuses_the_cached_result_without_recomputing(self):
        calls = []

        def compute():
            calls.append(1)
            return "result"

        first = memoize_projection("demo", ("k", 1), compute)
        second = memoize_projection("demo", ("k", 1), compute)

        self.assertEqual(first, "result")
        self.assertEqual(second, "result")
        self.assertEqual(len(calls), 1)

    def test_a_changed_key_recomputes_and_replaces_the_cached_result(self):
        results = iter(["first", "second"])
        calls = []

        def compute():
            calls.append(1)
            return next(results)

        first = memoize_projection("demo", ("k", 1), compute)
        second = memoize_projection("demo", ("k", 2), compute)

        self.assertEqual(first, "first")
        self.assertEqual(second, "second")
        self.assertEqual(len(calls), 2)

    def test_different_names_do_not_share_a_cache_slot(self):
        a = memoize_projection("name-a", ("k", 1), lambda: "A")
        b = memoize_projection("name-b", ("k", 1), lambda: "B")
        self.assertEqual(a, "A")
        self.assertEqual(b, "B")

    def test_reverting_to_a_previously_seen_key_recomputes_rather_than_reusing_stale_history(self):
        # Only the single most recent result per name is kept - going back
        # to an older key must not resurrect an old cached value as if it
        # were still fresh; it must be treated as a fresh computation.
        calls = []

        def compute():
            calls.append(1)
            return f"call-{len(calls)}"

        first = memoize_projection("demo", ("k", 1), compute)
        memoize_projection("demo", ("k", 2), compute)
        third = memoize_projection("demo", ("k", 1), compute)

        self.assertEqual(len(calls), 3)
        self.assertNotEqual(first, third)


if __name__ == "__main__":
    unittest.main()
