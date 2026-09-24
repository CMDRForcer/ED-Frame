"""Windows-user-bound storage for the INARA API key."""

from __future__ import annotations

import base64
from pathlib import Path

from ed_companion.integrations.frontier_credentials import (
    FrontierCredentialError,
    protect_for_current_user,
    unprotect_for_current_user,
)
from ed_companion.persistence import atomic_write


class InaraCredentialError(RuntimeError):
    """INARA credential storage failed without exposing the API key."""


class InaraCredentialStore:
    """Persist one INARA API key encrypted for the current Windows user."""

    def __init__(self, path, *, protect=None, unprotect=None):
        self.path = Path(path)
        self._protect = protect or protect_for_current_user
        self._unprotect = unprotect or unprotect_for_current_user

    def save(self, api_key):
        value = str(api_key or "").strip()
        if not value:
            raise InaraCredentialError("An INARA API key is required.")
        try:
            protected = self._protect(value.encode("utf-8"))
            encoded = base64.b64encode(protected).decode("ascii")
            if not atomic_write(self.path, encoded):
                raise OSError("atomic write rejected")
        except (OSError, ValueError, FrontierCredentialError) as exc:
            raise InaraCredentialError(
                "The INARA API key could not be stored securely."
            ) from exc

    def load(self):
        try:
            encoded = self.path.read_text(encoding="ascii").strip()
        except FileNotFoundError:
            return ""
        except OSError as exc:
            raise InaraCredentialError(
                "The INARA API key could not be read securely."
            ) from exc
        try:
            value = self._unprotect(
                base64.b64decode(encoded, validate=True)
            ).decode("utf-8").strip()
            if not value:
                raise ValueError("empty credential")
            return value
        except (
            ValueError,
            TypeError,
            UnicodeError,
            FrontierCredentialError,
        ) as exc:
            raise InaraCredentialError(
                "The stored INARA API key could not be decrypted."
            ) from exc

    def clear(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise InaraCredentialError(
                "The INARA API key could not be removed."
            ) from exc
