"""Small durable SQLite store for paper-run state and audit events.

The store is intentionally limited to JSON-compatible snapshots and events.
Callers own domain serialization and must use stable, versioned payloads. No
broker action or execution authorization is performed here.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PaperStoreError(RuntimeError):
    """Base error for persistence failures."""


class SnapshotConflictError(PaperStoreError):
    """Raised when a snapshot revision changed since it was read."""


class IdempotencyConflictError(PaperStoreError):
    """Raised when an idempotency key is reused with different content."""


@dataclass(frozen=True)
class StoredSnapshot:
    key: str
    schema_version: int
    revision: int
    payload: dict[str, Any]
    updated_at: str


@dataclass(frozen=True)
class StoredEvent:
    sequence: int
    event_id: str
    event_type: str
    occurred_at: str
    payload: dict[str, Any]
    previous_hash: str
    event_hash: str


_GENESIS_HASH = "0" * 64


def _json_bytes(payload: dict[str, Any]) -> bytes:
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dictionary")
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PaperStoreError(f"Payload is not strict JSON: {exc}") from exc


class SQLitePaperStore:
    """Transactional snapshots and an append-only hash-chained event log."""

    API_VERSION = "1.0.0"

    def __init__(
        self,
        path: str | Path,
        *,
        timeout_seconds: float = 10.0,
        read_only: bool = False,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.path = Path(path)
        self.timeout_seconds = float(timeout_seconds)
        self.read_only = bool(read_only)
        if self.read_only:
            if not self.path.is_file():
                raise PaperStoreError(f"Paper database does not exist: {self.path}")
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self.read_only:
            connection = sqlite3.connect(
                f"{self.path.resolve().as_uri()}?mode=ro",
                timeout=self.timeout_seconds,
                isolation_level=None,
                uri=True,
            )
        else:
            connection = sqlite3.connect(
                self.path,
                timeout=self.timeout_seconds,
                isolation_level=None,
            )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        try:
            with closing(self._connect()) as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS paper_snapshots (
                        snapshot_key TEXT PRIMARY KEY,
                        schema_version INTEGER NOT NULL CHECK(schema_version > 0),
                        revision INTEGER NOT NULL CHECK(revision > 0),
                        payload_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )"""
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS paper_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT NOT NULL UNIQUE,
                        event_type TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        previous_hash TEXT NOT NULL,
                        event_hash TEXT NOT NULL
                    )"""
                )
        except sqlite3.Error as exc:
            raise PaperStoreError(f"Unable to initialize paper store: {exc}") from exc

    def load_snapshot(self, key: str) -> StoredSnapshot | None:
        if not key:
            raise ValueError("snapshot key cannot be empty")
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT * FROM paper_snapshots WHERE snapshot_key = ?",
                    (key,),
                ).fetchone()
            if row is None:
                return None
            return StoredSnapshot(
                key=row["snapshot_key"],
                schema_version=int(row["schema_version"]),
                revision=int(row["revision"]),
                payload=json.loads(row["payload_json"]),
                updated_at=row["updated_at"],
            )
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise PaperStoreError(f"Unable to load snapshot {key!r}: {exc}") from exc

    def backup_to(self, destination: str | Path) -> Path:
        """Create a consistent SQLite backup, including committed WAL data."""
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.resolve() == self.path.resolve():
            raise ValueError("Backup destination must differ from the source database.")
        try:
            with closing(self._connect()) as source:
                with closing(sqlite3.connect(target)) as backup:
                    source.backup(backup)
                    result = backup.execute("PRAGMA integrity_check").fetchone()
            if result is None or result[0] != "ok":
                raise PaperStoreError(f"SQLite backup integrity check failed: {result}")
            return target
        except sqlite3.Error as exc:
            raise PaperStoreError(f"Unable to back up paper database: {exc}") from exc

    def integrity_check(self) -> dict[str, Any]:
        """Check SQLite page integrity and the append-only event hash chain."""
        try:
            with closing(self._connect()) as connection:
                result = connection.execute("PRAGMA integrity_check").fetchone()
            sqlite_status = "ok" if result is not None else "missing result"
            if result is not None:
                sqlite_status = str(result[0])
            chain_valid = self.verify_event_chain()
            return {
                "sqlite_integrity": sqlite_status,
                "event_chain_valid": chain_valid,
                "healthy": sqlite_status == "ok" and chain_valid,
            }
        except sqlite3.Error as exc:
            raise PaperStoreError(f"Unable to check paper database: {exc}") from exc

    def save_snapshot(
        self,
        key: str,
        payload: dict[str, Any],
        *,
        schema_version: int,
        expected_revision: int | None,
    ) -> StoredSnapshot:
        """Insert/update a snapshot using optimistic revision checking.

        Use ``expected_revision=0`` to create a new key. For updates pass the
        revision returned by ``load_snapshot``. A missing expected revision is
        rejected so concurrent writers cannot silently overwrite state.
        """
        if not key:
            raise ValueError("snapshot key cannot be empty")
        if schema_version <= 0:
            raise ValueError("schema_version must be positive")
        if expected_revision is None or expected_revision < 0:
            raise ValueError("expected_revision must be a non-negative integer")
        payload_json = _json_bytes(payload).decode("utf-8")
        updated_at = datetime.now(timezone.utc).isoformat()
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT revision FROM paper_snapshots WHERE snapshot_key = ?",
                    (key,),
                ).fetchone()
                actual_revision = 0 if row is None else int(row["revision"])
                if actual_revision != expected_revision:
                    raise SnapshotConflictError(
                        f"Snapshot {key!r} revision is {actual_revision}; "
                        f"expected {expected_revision}."
                    )
                next_revision = actual_revision + 1
                connection.execute(
                    """INSERT INTO paper_snapshots
                       (snapshot_key, schema_version, revision, payload_json, updated_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(snapshot_key) DO UPDATE SET
                         schema_version = excluded.schema_version,
                         revision = excluded.revision,
                         payload_json = excluded.payload_json,
                         updated_at = excluded.updated_at""",
                    (key, schema_version, next_revision, payload_json, updated_at),
                )
                connection.commit()
            return StoredSnapshot(
                key=key,
                schema_version=schema_version,
                revision=next_revision,
                payload=json.loads(payload_json),
                updated_at=updated_at,
            )
        except SnapshotConflictError:
            raise
        except sqlite3.Error as exc:
            raise PaperStoreError(f"Unable to save snapshot {key!r}: {exc}") from exc

    def append_event(
        self,
        event_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        occurred_at: str | None = None,
    ) -> StoredEvent:
        """Append an immutable event; identical retries are idempotent."""
        if not event_id or not event_type:
            raise ValueError("event_id and event_type cannot be empty")
        payload_json = _json_bytes(payload).decode("utf-8")
        timestamp = occurred_at or datetime.now(timezone.utc).isoformat()
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT * FROM paper_events WHERE event_id = ?",
                    (event_id,),
                ).fetchone()
                if existing is not None:
                    if (
                        existing["event_type"] != event_type
                        or existing["payload_json"] != payload_json
                        or (
                            occurred_at is not None
                            and existing["occurred_at"] != timestamp
                        )
                    ):
                        raise IdempotencyConflictError(
                            f"Event id {event_id!r} was reused with different content."
                        )
                    connection.commit()
                    return self._event_from_row(existing)

                previous = connection.execute(
                    "SELECT event_hash FROM paper_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = _GENESIS_HASH if previous is None else previous["event_hash"]
                canonical = "\n".join(
                    (event_id, event_type, timestamp, payload_json, previous_hash)
                ).encode("utf-8")
                event_hash = hashlib.sha256(canonical).hexdigest()
                cursor = connection.execute(
                    """INSERT INTO paper_events
                       (event_id, event_type, occurred_at, payload_json, previous_hash, event_hash)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (event_id, event_type, timestamp, payload_json, previous_hash, event_hash),
                )
                row = connection.execute(
                    "SELECT * FROM paper_events WHERE sequence = ?",
                    (cursor.lastrowid,),
                ).fetchone()
                connection.commit()
            return self._event_from_row(row)
        except (IdempotencyConflictError, PaperStoreError):
            raise
        except sqlite3.Error as exc:
            raise PaperStoreError(f"Unable to append paper event: {exc}") from exc

    def get_event(self, event_id: str) -> StoredEvent | None:
        """Return an event by id for safe cycle retry handling."""
        if not event_id:
            raise ValueError("event_id cannot be empty")
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT * FROM paper_events WHERE event_id = ?",
                    (event_id,),
                ).fetchone()
            return None if row is None else self._event_from_row(row)
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise PaperStoreError(f"Unable to load event {event_id!r}: {exc}") from exc

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> StoredEvent:
        return StoredEvent(
            sequence=int(row["sequence"]),
            event_id=row["event_id"],
            event_type=row["event_type"],
            occurred_at=row["occurred_at"],
            payload=json.loads(row["payload_json"]),
            previous_hash=row["previous_hash"],
            event_hash=row["event_hash"],
        )

    def read_events(self, *, after_sequence: int = 0) -> tuple[StoredEvent, ...]:
        if after_sequence < 0:
            raise ValueError("after_sequence must be non-negative")
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    "SELECT * FROM paper_events WHERE sequence > ? ORDER BY sequence",
                    (after_sequence,),
                ).fetchall()
            return tuple(self._event_from_row(row) for row in rows)
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise PaperStoreError(f"Unable to read paper events: {exc}") from exc

    def verify_event_chain(self) -> bool:
        previous_hash = _GENESIS_HASH
        for event in self.read_events():
            canonical = "\n".join(
                (
                    event.event_id,
                    event.event_type,
                    event.occurred_at,
                    _json_bytes(event.payload).decode("utf-8"),
                    previous_hash,
                )
            ).encode("utf-8")
            expected_hash = hashlib.sha256(canonical).hexdigest()
            if event.previous_hash != previous_hash or event.event_hash != expected_hash:
                return False
            previous_hash = event.event_hash
        return True
