"""Small redaction helpers for operational logs and reports."""

from __future__ import annotations

import re


def redact_sensitive_message(message: str, secrets: tuple[str, ...] = ()) -> str:
    """Redact configured secret values and common credential query fields."""
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return re.sub(
        r"(?i)(api[_-]?key|password|token)(=|%3D)[^&\s]+",
        r"\1\2[REDACTED]",
        message,
    )
