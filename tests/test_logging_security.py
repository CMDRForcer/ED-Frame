import logging
import unittest

from ed_companion.logging_security import (
    REDACTED,
    log_exception_safely,
    redact_secrets,
    safe_exception_text,
)


class LoggingSecurityTests(unittest.TestCase):
    def test_redacts_supported_credential_shapes(self):
        secrets = (
            "TOKEN-VALUE-123456",
            "ACCESS-VALUE-123456",
            "REFRESH-VALUE-123456",
            "API-KEY-VALUE-123456",
            "BEARER-VALUE-123456",
            "PASSWORD-VALUE-123456",
        )
        value = (
            "token=TOKEN-VALUE-123456 "
            '\"access_token\": \"ACCESS-VALUE-123456\" '
            "refresh-token='REFRESH-VALUE-123456' "
            "api_key=API-KEY-VALUE-123456&next=true "
            "Authorization: Bearer BEARER-VALUE-123456 "
            "password=PASSWORD-VALUE-123456"
        )

        redacted = redact_secrets(value)

        self.assertGreaterEqual(redacted.count(REDACTED), len(secrets))
        for secret in secrets:
            self.assertNotIn(secret, redacted)
        self.assertIn("next=true", redacted)

    def test_redacts_unlabelled_known_connector_secret(self):
        secret = "frontier-access-value-123456"

        redacted = redact_secrets(
            f"transport echoed {secret}", extra_secrets=(secret,)
        )

        self.assertEqual(redacted, f"transport echoed {REDACTED}")

    def test_safe_exception_log_keeps_diagnostics_without_secret(self):
        logger = logging.getLogger("tests.logging-security")
        try:
            raise RuntimeError("request failed api_key=API-KEY-VALUE-123456")
        except RuntimeError as exc:
            with self.assertLogs(logger, level="ERROR") as captured:
                log_exception_safely(logger, "Connector failed", exc)
            safe_text = safe_exception_text(exc)

        output = "\n".join(captured.output)
        self.assertIn("Connector failed", output)
        self.assertIn("RuntimeError", output)
        self.assertIn("test_safe_exception_log_keeps_diagnostics", output)
        self.assertIn(REDACTED, output)
        self.assertNotIn("API-KEY-VALUE-123456", output)
        self.assertNotIn("API-KEY-VALUE-123456", safe_text)


if __name__ == "__main__":
    unittest.main()
