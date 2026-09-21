from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from ed_companion.persistence import atomic_write


class AtomicWriteRetryTests(unittest.TestCase):
    def test_transient_permission_error_on_replace_is_retried_and_succeeds(self):
        # On Windows, antivirus/indexer/OneDrive can briefly hold a file
        # open right after it changes, making os.replace() raise
        # PermissionError (WinError 32) even though nothing in ED-Frame
        # is still holding it. This reproduced a real crash
        # (controller_eddn.py's _save_eddn -> atomic_write) where the
        # lock had already cleared a moment later - a couple of retries
        # should absorb it instead of crashing the app.
        with TemporaryDirectory() as directory:
            path = Path(directory) / "eddn_config.json"
            real_replace = __import__("os").replace
            calls = []

            def flaky_replace(src, dst):
                calls.append(1)
                if len(calls) < 3:
                    raise PermissionError(32, "used by another process")
                return real_replace(src, dst)

            with mock.patch("ed_companion.persistence.os.replace", side_effect=flaky_replace), \
                 mock.patch("ed_companion.persistence.time.sleep", return_value=None):
                result = atomic_write(path, '{"ok": true}')

            self.assertTrue(result)
            self.assertEqual(len(calls), 3)
            self.assertEqual(path.read_text(encoding="utf-8"), '{"ok": true}')

    def test_permanent_permission_error_on_replace_still_raises(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "eddn_config.json"

            def always_locked(src, dst):
                raise PermissionError(32, "used by another process")

            with mock.patch("ed_companion.persistence.os.replace", side_effect=always_locked), \
                 mock.patch("ed_companion.persistence.time.sleep", return_value=None):
                with self.assertRaises(PermissionError):
                    atomic_write(path, '{"ok": true}')


if __name__ == "__main__":
    unittest.main()
