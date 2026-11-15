"""
audittrail.py
=============
Phase 5C — Append-only, hash-chained operational audit trail.

Each record contains:
    sequence
    event
    previous_hash
    record_hash

The hash chain makes accidental modification, truncation, insertion, or
reordering detectable by verify(). This module records events only; it does
not authorize, route, submit, execute, cancel, or modify trading state.

Version: 1.0.0
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from operationalevent import OperationalEvent

API_VERSION = "1.0.0"

PUBLIC_METHODS = (
    "append",
    "read",
    "verify",
    "count",
    "metadata",
    "health_check",
)

_GENESIS_HASH = "0" * 64


@dataclass(frozen=True)
class AuditRecord:
    """Immutable persisted audit record."""

    sequence: int
    event: dict[str, Any]
    previous_hash: str
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event": json.loads(
                json.dumps(self.event, sort_keys=True, default=str)
            ),
            "previous_hash": self.previous_hash,
            "record_hash": self.record_hash,
        }


class OperationalAuditTrail:
    """Append-only JSONL audit trail with a SHA-256 hash chain."""

    API_VERSION = API_VERSION

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()
        self._records: list[AuditRecord] = []

        self._path.parent.mkdir(parents=True, exist_ok=True)

        if self._path.exists():
            self._load_existing()

    def append(self, event: OperationalEvent) -> AuditRecord:
        """Append one event and return its immutable audit record."""
        if not isinstance(event, OperationalEvent):
            raise TypeError("event must be an OperationalEvent")

        with self._lock:
            sequence = len(self._records) + 1
            previous_hash = (
                self._records[-1].record_hash
                if self._records
                else _GENESIS_HASH
            )

            event_payload = event.to_dict()
            canonical = _canonical_payload(
                sequence,
                event_payload,
                previous_hash,
            )
            record_hash = hashlib.sha256(canonical).hexdigest()

            record = AuditRecord(
                sequence=sequence,
                event=event_payload,
                previous_hash=previous_hash,
                record_hash=record_hash,
            )

            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        record.to_dict(),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                handle.flush()

            self._records.append(record)
            return record

    def read(self) -> tuple[AuditRecord, ...]:
        """Return the currently loaded immutable audit records."""
        with self._lock:
            return tuple(self._records)

    def verify(self) -> dict[str, Any]:
        """Verify sequence integrity and the complete hash chain."""
        with self._lock:
            previous_hash = _GENESIS_HASH

            for expected_sequence, record in enumerate(
                self._records,
                start=1,
            ):
                if record.sequence != expected_sequence:
                    return {
                        "healthy": False,
                        "reason": "SEQUENCE_MISMATCH",
                        "sequence": record.sequence,
                    }

                if record.previous_hash != previous_hash:
                    return {
                        "healthy": False,
                        "reason": "PREVIOUS_HASH_MISMATCH",
                        "sequence": record.sequence,
                    }

                expected_hash = hashlib.sha256(
                    _canonical_payload(
                        record.sequence,
                        record.event,
                        record.previous_hash,
                    )
                ).hexdigest()

                if record.record_hash != expected_hash:
                    return {
                        "healthy": False,
                        "reason": "RECORD_HASH_MISMATCH",
                        "sequence": record.sequence,
                    }

                previous_hash = record.record_hash

            return {
                "healthy": True,
                "records": len(self._records),
                "last_hash": previous_hash,
            }

    def count(self) -> int:
        with self._lock:
            return len(self._records)

    def metadata(self) -> dict[str, Any]:
        return metadata()

    def health_check(self) -> dict[str, Any]:
        result = self.verify()
        result.update(
            {
                "module": "audittrail",
                "api_version": API_VERSION,
                "path": str(self._path),
            }
        )
        return result

    def _load_existing(self) -> None:
        """Load and validate an existing trail before accepting new writes."""
        with self._path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue

                try:
                    payload = json.loads(line)
                    record = AuditRecord(
                        sequence=int(payload["sequence"]),
                        event=dict(payload["event"]),
                        previous_hash=str(payload["previous_hash"]),
                        record_hash=str(payload["record_hash"]),
                    )
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ValueError(
                        f"Invalid audit record at line {line_number}"
                    ) from exc

                self._records.append(record)

        result = self.verify()
        if not result["healthy"]:
            raise ValueError(
                f"Audit trail integrity failure: {result['reason']}"
            )


def _canonical_payload(
    sequence: int,
    event: dict[str, Any],
    previous_hash: str,
) -> bytes:
    payload = {
        "sequence": sequence,
        "event": event,
        "previous_hash": previous_hash,
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def metadata() -> dict[str, Any]:
    return {
        "module": "audittrail",
        "api_version": API_VERSION,
        "public_methods": PUBLIC_METHODS,
        "storage_format": "JSONL",
        "integrity": "SHA256_HASH_CHAIN",
        "execution_side_effects": False,
    }


def health_check() -> dict[str, Any]:
    return {
        "module": "audittrail",
        "api_version": API_VERSION,
        "healthy": True,
        "storage_format": "JSONL",
        "integrity": "SHA256_HASH_CHAIN",
    }
