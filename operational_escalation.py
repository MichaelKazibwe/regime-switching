"""Durable incident/escalation delivery outbox. Ambiguous delivery is never retried."""

from pathlib import Path
from datetime import datetime
import sqlite3
import os
import json
import fcntl
from strategy_integrity import fingerprint, canonical


class EscalationStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise ValueError("Regular escalation database required")
        with self.connect() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS incidents(id TEXT PRIMARY KEY,opened TEXT,signal TEXT,ack TEXT,resolved TEXT); CREATE TABLE IF NOT EXISTS delivery(id TEXT PRIMARY KEY,incident TEXT,level INTEGER,state TEXT,receipt TEXT);"
            )
        os.chmod(self.path, 0o600)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def reconcile(self, signals, *, now):
        """Stable incident per open signal; resolution does not erase its history."""
        if now.tzinfo is None:
            raise ValueError("Aware incident clock required")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for incident, signal in db.execute(
                "SELECT id,signal FROM incidents WHERE resolved IS NULL"
            ).fetchall():
                if signal not in signals:
                    db.execute(
                        "UPDATE incidents SET resolved=? WHERE id=?",
                        (now.isoformat(), incident),
                    )
            for signal in sorted(set(signals)):
                row = db.execute(
                    "SELECT id FROM incidents WHERE signal=? AND resolved IS NULL",
                    (signal,),
                ).fetchone()
                if not row:
                    key = fingerprint(dict(signal=signal, opened=now.isoformat()))
                    db.execute(
                        "INSERT INTO incidents VALUES(?,?,?,NULL,NULL)",
                        (key, now.isoformat(), signal),
                    )

    def acknowledge(self, incident, actor, *, now):
        if not actor or not actor.strip() or now.tzinfo is None:
            raise ValueError("Named authenticated operator acknowledgement required")
        with self.connect() as db:
            if (
                db.execute(
                    "SELECT id FROM incidents WHERE id=?", (incident,)
                ).fetchone()
                is None
            ):
                raise ValueError("Unknown incident")
            db.execute(
                "UPDATE incidents SET ack=? WHERE id=?",
                (canonical(dict(actor=actor, at=now.isoformat())), incident),
            )

    def dispatch(self, sender=None, *, now, escalate_seconds=900):
        with self.path.with_suffix(".dispatch.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return self._dispatch(sender, now=now, escalate_seconds=escalate_seconds)

    def _dispatch(self, sender=None, *, now, escalate_seconds=900):
        if not 60 <= escalate_seconds <= 86400:
            raise ValueError("Bounded escalation deadline required")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE delivery SET state='UNKNOWN' WHERE state='SENDING'")
            for key, opened in db.execute(
                "SELECT id,opened FROM incidents WHERE resolved IS NULL AND ack IS NULL"
            ).fetchall():
                level = int(
                    (now - datetime.fromisoformat(opened)).total_seconds()
                    >= escalate_seconds
                )
                # An ambiguous primary is not automatically retried. A separately
                # configured escalation destination may receive its own notification.
                db.execute(
                    "INSERT OR IGNORE INTO delivery VALUES(?,?,?,?,NULL)",
                    (f"{key}:{level}", key, level, "PENDING"),
                )
        if sender is None:
            return dict(status="BLOCKED_EXTERNAL_DELIVERY_UNCONFIGURED", sent=0)
        sent = 0
        while True:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT d.id,d.incident,d.level,i.signal FROM delivery d JOIN incidents i ON d.incident=i.id WHERE d.state='PENDING' AND i.resolved IS NULL AND i.ack IS NULL ORDER BY d.id LIMIT 1"
                ).fetchone()
                if not row:
                    break
                db.execute("UPDATE delivery SET state='SENDING' WHERE id=?", (row[0],))
            try:
                receipt = sender(
                    dict(
                        notification_id=row[0],
                        incident_id=row[1],
                        level=row[2],
                        signal=row[3],
                    )
                )
                state = (
                    "ACCEPTED_BY_TRANSPORT"
                    if receipt.get("accepted") is True
                    else "UNKNOWN"
                )
                safe = dict(
                    accepted=receipt.get("accepted") is True,
                    reference=receipt.get("reference"),
                )
            except Exception as exc:
                state = "UNKNOWN"
                safe = dict(error_type=type(exc).__name__)
            with self.connect() as db:
                db.execute(
                    "UPDATE delivery SET state=?,receipt=? WHERE id=?",
                    (state, json.dumps(safe), row[0]),
                )
            sent += int(state == "ACCEPTED_BY_TRANSPORT")
        return dict(
            status="TRANSPORT_ATTEMPTS_RECORDED",
            sent=sent,
            human_receipt_verified=False,
        )
