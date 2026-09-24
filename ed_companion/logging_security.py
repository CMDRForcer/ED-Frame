"""Privacy-safe helpers for logging connector failures.

Network libraries and remote services occasionally include request details in
exception messages.  Those details must not make OAuth tokens or API keys part
of a local log, crash report, or user-visible status string.
"""

from __future__ import annotations

import logging
import re
import traceback
from collections.abc import Iterable


REDACTED = "[REDACTED]"

_AUTHORIZATION_PATTERN = re.compile(
    r"(?i)(\b(?:proxy-)?authorization\b[\"']?\s*[:=]\s*[\"']?"
    r"(?:(?:bearer|basic)\s+)?)([^\s,;&}\]\"']+)"
)
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(\b(?:access[_-]?token|refresh[_-]?token|id[_-]?token|token|"
    r"api[_-]?key|apikey|client[_-]?secret|password|passwd|secret)"
    r"\b[\"']?\s*[:=]\s*[\"']?)([^\s,;&}\]\"']+)"
)
_HIGH_ENTROPY_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."
        r"[A-Za-z0-9_-]{10,}\b"
    ),
)


def redact_secrets(value: object, *, extra_secrets: Iterable[object] = ()) -> str:
    """Return text with credential-shaped values and known secrets masked."""

    text = str(value)
    known = sorted(
        {
            str(secret)
            for secret in extra_secrets
            if secret is not None and len(str(secret)) >= 8
        },
        key=len,
        reverse=True,
    )
    for secret in known:
        text = text.replace(secret, REDACTED)
    text = _AUTHORIZATION_PATTERN.sub(rf"\1{REDACTED}", text)
    text = _SECRET_ASSIGNMENT_PATTERN.sub(rf"\1{REDACTED}", text)
    for pattern in _HIGH_ENTROPY_SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def safe_exception_text(
    exc: BaseException, *, extra_secrets: Iterable[object] = ()
) -> str:
    """Describe an exception without exposing credentials from its message."""

    detail = redact_secrets(exc, extra_secrets=extra_secrets)
    return f"{type(exc).__name__}: {detail}"


def log_exception_safely(
    logger: logging.Logger,
    message: str,
    exc: BaseException,
    *,
    extra_secrets: Iterable[object] = (),
) -> None:
    """Log useful exception context without formatting the raw exception.

    ``logger.exception`` delegates exception rendering to the logging
    formatter, which appends the unsanitized exception message.  Formatting
    only the traceback frames keeps the source locations while allowing the
    exception text to pass through the credential redactor first.
    """

    known_secrets = tuple(extra_secrets)
    safe_message = redact_secrets(message, extra_secrets=known_secrets)
    safe_detail = safe_exception_text(exc, extra_secrets=known_secrets)
    frames = "".join(traceback.format_tb(exc.__traceback__)).rstrip()
    if frames:
        safe_frames = redact_secrets(frames, extra_secrets=known_secrets)
        logger.error(
            "%s\nTraceback (most recent call last):\n%s\n%s",
            safe_message,
            safe_frames,
            safe_detail,
        )
        return
    logger.error("%s: %s", safe_message, safe_detail)
