"""
structuredlogging.py
====================
Phase 5C — Structured Operational Logging.

Responsibilities
----------------
- Convert OperationalEvent objects into structured JSON log records.
- Preserve event identity and correlation fields.
- Route severity to the standard-library logging subsystem.
- Avoid order submission, broker interaction, authorization, or risk decisions.

Version: 1.0.0
"""

from __future__ import annotations

import json
import logging
from typing import Any

from operationalevent import OperationalEvent, OperationalSeverity

API_VERSION = "1.0.0"

PUBLIC_METHODS = (
    "emit",
    "metadata",
    "health_check",
)


class OperationalJSONFormatter(logging.Formatter):
    """Serialize OperationalEvent records as deterministic JSON."""

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "operational_event", None)

        if isinstance(event, OperationalEvent):
            payload = event.to_dict()
        else:
            payload = {
                "event_type": "LOG_MESSAGE",
                "severity": record.levelname,
                "source": "SYSTEM",
                "timestamp": record.created,
                "message": record.getMessage(),
            }

        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )


class OperationalLogger:
    """Small adapter from OperationalEvent to standard logging."""

    API_VERSION = API_VERSION

    _LEVEL_MAP = {
        OperationalSeverity.INFO: logging.INFO,
        OperationalSeverity.WARNING: logging.WARNING,
        OperationalSeverity.ERROR: logging.ERROR,
        OperationalSeverity.CRITICAL: logging.CRITICAL,
    }

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("regime_switching.operational")

    def emit(self, event: OperationalEvent) -> None:
        """Emit one immutable OperationalEvent through the logging subsystem."""
        if not isinstance(event, OperationalEvent):
            raise TypeError("event must be an OperationalEvent")

        level = self._LEVEL_MAP.get(
            event.severity,
            logging.INFO,
        )

        self._logger.log(
            level,
            event.message,
            extra={"operational_event": event},
        )

    def metadata(self) -> dict[str, Any]:
        return metadata()

    def health_check(self) -> dict[str, Any]:
        return health_check()


def metadata() -> dict[str, Any]:
    """Return public module metadata."""
    return {
        "module": "structuredlogging",
        "api_version": API_VERSION,
        "public_methods": PUBLIC_METHODS,
        "side_effects": "logging_only",
    }


def health_check() -> dict[str, Any]:
    """Return deterministic module health information."""
    return {
        "module": "structuredlogging",
        "api_version": API_VERSION,
        "healthy": True,
        "logging_backend": "python_standard_library",
    }
