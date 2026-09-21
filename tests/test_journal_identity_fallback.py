import unittest
from pathlib import Path
from unittest import mock

from ed_companion.phase14 import state_core


class JournalProfileIdentityFallbackTests(unittest.TestCase):
    """Keep a stable profile through a transient empty identity lookup."""

    def setUp(self):
        state_core._LAST_KNOWN_IDENTITY = None

    def tearDown(self):
        state_core._LAST_KNOWN_IDENTITY = None

    def test_first_ever_empty_result_is_returned_as_is(self):
        with mock.patch.object(
            state_core, "_resolve_journal_profile_identity",
            return_value=("", ""),
        ):
            result = state_core._journal_profile_identity()

        self.assertEqual(result, ("", ""))

    def test_a_real_identity_is_cached_and_survives_a_later_empty_read(self):
        with mock.patch.object(
            state_core, "_resolve_journal_profile_identity",
            return_value=("F123456", "CMDR Test"),
        ):
            first = state_core._journal_profile_identity()
        self.assertEqual(first, ("F123456", "CMDR Test"))

        with mock.patch.object(
            state_core, "_resolve_journal_profile_identity",
            return_value=("", ""),
        ):
            second = state_core._journal_profile_identity()

        self.assertEqual(
            second, ("F123456", "CMDR Test"),
            "A momentary empty lookup must fall back to the last real "
            "identity instead of resolving to the generic 'unidentified' "
            "profile bucket.",
        )

    def test_a_genuine_identity_change_still_takes_effect_immediately(self):
        with mock.patch.object(
            state_core, "_resolve_journal_profile_identity",
            return_value=("F111111", "CMDR One"),
        ):
            state_core._journal_profile_identity()

        with mock.patch.object(
            state_core, "_resolve_journal_profile_identity",
            return_value=("F222222", "CMDR Two"),
        ):
            switched = state_core._journal_profile_identity()

        self.assertEqual(switched, ("F222222", "CMDR Two"))

        with mock.patch.object(
            state_core, "_resolve_journal_profile_identity",
            return_value=("", ""),
        ):
            after_glitch = state_core._journal_profile_identity()

        self.assertEqual(after_glitch, ("F222222", "CMDR Two"))

    def test_cache_is_not_reused_for_another_journal_directory(self):
        with mock.patch.object(
            state_core, "journal_dir", return_value=Path("journal-one"),
        ), mock.patch.object(
            state_core, "_resolve_journal_profile_identity",
            return_value=("F111111", "CMDR One"),
        ):
            state_core._journal_profile_identity()

        with mock.patch.object(
            state_core, "journal_dir", return_value=Path("journal-two"),
        ), mock.patch.object(
            state_core, "_resolve_journal_profile_identity",
            return_value=("", ""),
        ):
            result = state_core._journal_profile_identity()

        self.assertEqual(result, ("", ""))


if __name__ == "__main__":
    unittest.main()
