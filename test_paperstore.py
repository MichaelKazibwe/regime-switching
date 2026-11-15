from __future__ import annotations

import sqlite3

import pytest

from paperstore import (
    IdempotencyConflictError,
    PaperStoreError,
    SQLitePaperStore,
    SnapshotConflictError,
)


def test_snapshot_revision_compare_and_swap(tmp_path) -> None:
    store = SQLitePaperStore(tmp_path / "paper.sqlite3")

    first = store.save_snapshot(
        "account",
        {"cash": 100.0},
        schema_version=1,
        expected_revision=0,
    )
    assert first.revision == 1
    assert store.load_snapshot("account") == first

    second = store.save_snapshot(
        "account",
        {"cash": 90.0},
        schema_version=1,
        expected_revision=first.revision,
    )
    assert second.revision == 2
    with pytest.raises(SnapshotConflictError):
        store.save_snapshot(
            "account",
            {"cash": 80.0},
            schema_version=1,
            expected_revision=first.revision,
        )


def test_event_append_is_idempotent_and_hash_chained(tmp_path) -> None:
    store = SQLitePaperStore(tmp_path / "paper.sqlite3")
    first = store.append_event("cycle-1", "DECISION", {"status": "APPROVED"})
    retry = store.append_event("cycle-1", "DECISION", {"status": "APPROVED"})

    assert retry == first
    assert len(store.read_events()) == 1
    assert store.verify_event_chain()

    with pytest.raises(IdempotencyConflictError):
        store.append_event("cycle-1", "DECISION", {"status": "FAILED"})


def test_event_chain_detects_database_tampering(tmp_path) -> None:
    database = tmp_path / "paper.sqlite3"
    store = SQLitePaperStore(database)
    store.append_event("cycle-1", "DECISION", {"status": "APPROVED"})

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE paper_events SET payload_json = ? WHERE event_id = ?",
            ('{"status":"FAILED"}', "cycle-1"),
        )

    assert store.verify_event_chain() is False


def test_store_rejects_non_json_and_non_finite_payloads(tmp_path) -> None:
    store = SQLitePaperStore(tmp_path / "paper.sqlite3")
    with pytest.raises(PaperStoreError):
        store.append_event("bad-1", "DECISION", {"value": float("nan")})


def test_store_backup_is_consistent_and_verifiable(tmp_path) -> None:
    store = SQLitePaperStore(tmp_path / "paper.sqlite3")
    store.append_event("cycle-1", "DECISION", {"status": "APPROVED"})
    backup_path = store.backup_to(tmp_path / "backup" / "paper-copy.sqlite3")

    backup = SQLitePaperStore(backup_path)
    assert backup.integrity_check() == {
        "sqlite_integrity": "ok",
        "event_chain_valid": True,
        "healthy": True,
    }
    with pytest.raises(ValueError, match="differ"):
        store.backup_to(store.path)
