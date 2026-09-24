import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys
import unittest
from unittest import mock

import phase14_main


class DiagnosticsSecurityTests(unittest.TestCase):
    def test_crash_and_qml_diagnostics_redact_secrets(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            qt_handlers = []
            smoke_messages = []
            stderr = io.StringIO()
            previous_hook = sys.excepthook
            try:
                with mock.patch.object(
                    phase14_main, "diagnostics_dir", return_value=root
                ), mock.patch.object(
                    phase14_main,
                    "qInstallMessageHandler",
                    side_effect=lambda handler: qt_handlers.append(handler),
                ), mock.patch.object(sys, "stderr", stderr):
                    phase14_main.install_diagnostics(smoke_messages)
                    try:
                        raise RuntimeError(
                            "crash token=CRASH-SECRET-123456"
                        )
                    except RuntimeError:
                        sys.excepthook(*sys.exc_info())
                    qt_handlers[0](
                        0,
                        SimpleNamespace(file="Secret.qml", line=42),
                        "binding failed api_key=QML-SECRET-123456",
                    )
            finally:
                sys.excepthook = previous_hook

            crash_text = next((root / "crashes").glob("crash-*.log")).read_text(
                encoding="utf-8"
            )
            qml_text = (root / "phase14.log").read_text(encoding="utf-8")
            combined = crash_text + qml_text + stderr.getvalue()
            self.assertIn("[REDACTED]", combined)
            self.assertIn("RuntimeError", crash_text)
            self.assertIn("Secret.qml:42", qml_text)
            self.assertNotIn("CRASH-SECRET-123456", combined)
            self.assertNotIn("QML-SECRET-123456", combined)
            self.assertNotIn("QML-SECRET-123456", str(smoke_messages))


if __name__ == "__main__":
    unittest.main()
