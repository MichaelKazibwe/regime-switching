"""Account database backup/restore: restored accounts always start frozen."""

from pathlib import Path
from datetime import datetime, timezone
from time import monotonic
import sqlite3
import os
from strategy_integrity import strict_json, file_hash, fingerprint
from strategy_receipts import atomic_json


def validate(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Regular managed state required")
    counts = {}
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Managed database corruption")
        tables = {
            r[0]
            for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not {"accounts", "journals", "outbox", "writer_leases"} <= tables:
            raise ValueError("Complete managed database required")
        for table in sorted(tables):
            if table.startswith("sqlite_"):
                continue
            counts[table] = db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            columns = {r[1] for r in db.execute(f'PRAGMA table_info("{table}")')}
            if {"body", "sha"} <= columns:
                import json

                for body, digest in db.execute(f'SELECT body,sha FROM "{table}"'):
                    if fingerprint(json.loads(body)) != digest:
                        raise ValueError("Managed record hash mismatch")
    return counts


def backup(source, destination):
    source, destination = Path(source), Path(destination)
    validate(source)
    if destination.exists():
        raise ValueError("New protected backup directory required")
    destination.mkdir(parents=True, mode=0o700)
    target = destination / "managed.sqlite3"
    with (
        sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as original,
        sqlite3.connect(target) as copied,
    ):
        original.backup(copied)
    os.chmod(target, 0o600)
    report = dict(
        created_at=datetime.now(timezone.utc).isoformat(),
        sha256=file_hash(target),
        counts=validate(target),
        off_host_verified=False,
        execution_enabled=False,
    )
    atomic_json(destination / "managed-backup.json", report, exclusive=True)
    return report


def restore(source, destination, *, rto_seconds=900):
    import shutil

    source, destination = Path(source), Path(destination)
    start = monotonic()
    report = strict_json(source / "managed-backup.json")
    if (
        destination.exists()
        or file_hash(source / "managed.sqlite3") != report["sha256"]
    ):
        raise ValueError("New restore target and valid backup required")
    if validate(source / "managed.sqlite3") != report["counts"]:
        raise ValueError("Managed backup inventory mismatch")
    destination.mkdir(parents=True, mode=0o700)
    target = destination / "managed.sqlite3"
    shutil.copyfile(source / "managed.sqlite3", target)
    os.chmod(target, 0o600)
    with sqlite3.connect(target) as db:
        db.execute("UPDATE accounts SET frozen=1")
        db.execute("UPDATE outbox SET state='UNKNOWN' WHERE state='DISPATCHING'")
        db.execute(
            "UPDATE writer_leases SET epoch=epoch+1,owner='RESTORE_REVIEW_REQUIRED',expires=?",
            (datetime.now(timezone.utc).isoformat(),),
        )
        if "account_reconciliation" in {
            r[0]
            for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }:
            db.execute("DELETE FROM account_reconciliation")
    result = dict(
        status="LOCAL_MANAGED_RESTORE_PASS"
        if monotonic() - start <= rto_seconds
        else "RTO_BREACH",
        elapsed_seconds=monotonic() - start,
        counts=validate(target),
        all_accounts_frozen=True,
        writer_epochs_invalidated=True,
        execution_enabled=False,
        off_host_verified=False,
    )
    atomic_json(destination / "restore-proof.json", result, exclusive=True)
    return result
