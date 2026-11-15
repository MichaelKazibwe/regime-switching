"""Durable operator recommendation/state commit and recoverable private exports."""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3

from productreport import private_write


@contextmanager
def account_lock(state_path):
    path = Path(str(state_path) + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Account planning is already active") from None
        yield


class ProductState:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        path = self.root / "product-state.sqlite3"
        if path.is_symlink():
            raise ValueError("Regular account state database required")
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        os.close(fd)
        path.chmod(0o600)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS recommendations (
                id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS account (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                state TEXT NOT NULL, recommendation_id TEXT NOT NULL
                REFERENCES recommendations(id));
        """)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.db.close()

    def get(self, key):
        row = self.db.execute(
            "SELECT body FROM recommendations WHERE id=?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def state(self):
        row = self.db.execute("SELECT state FROM account WHERE singleton=1").fetchone()
        if row:
            return json.loads(row[0])
        legacy = self.root / "state.json"
        if legacy.is_symlink():
            raise ValueError("Regular account state required")
        return json.loads(legacy.read_text()) if legacy.exists() else None

    def commit(self, result):
        key = result["recommendation_id"]
        if not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValueError("Invalid recommendation identity")
        state = dict(
            base_currency=result["mandate"]["base_currency"], state=result["risk_state"]
        )
        with self.db:
            self.db.execute(
                "INSERT INTO recommendations VALUES (?,?)",
                (key, json.dumps(result, allow_nan=False)),
            )
            self.db.execute(
                "INSERT OR REPLACE INTO account VALUES (1,?,?)",
                (json.dumps(state, allow_nan=False), key),
            )
        # These files are derived exports. A crash here leaves the authoritative
        # result and high-water state committed together and recoverable.
        self.recover()

    def recover(self):
        row = self.db.execute(
            "SELECT state,recommendation_id FROM account WHERE singleton=1"
        ).fetchone()
        if row:
            result = self.get(row[1])
            private_write(
                self.root / (row[1] + ".json"), json.dumps(result, allow_nan=False)
            )
            private_write(self.root / "state.json", row[0])
