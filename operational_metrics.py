"""Durable bounded-cardinality metrics and incident history; no public listener."""

from pathlib import Path
import os
import sqlite3
import math
from strategy_integrity import canonical


class MetricStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise ValueError("Regular metrics database required")
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS samples(ts TEXT,name TEXT,value REAL,PRIMARY KEY(ts,name))"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,ts TEXT,body TEXT)"
            )
        os.chmod(self.path, 0o600)

    def record(self, stamp, metrics, record_id, record):
        if stamp.tzinfo is None:
            raise ValueError("Aware metrics clock required")
        if len(metrics) > 64 or any(
            not k.replace("_", "").isalnum()
            or not k.startswith("regime_")
            or isinstance(v, bool)
            or not math.isfinite(v)
            for k, v in metrics.items()
        ):
            raise ValueError("Bounded finite metric names/values required")
        body = canonical(record)
        with sqlite3.connect(self.path) as db:
            existing = db.execute(
                "SELECT body FROM records WHERE id=?", (record_id,)
            ).fetchone()
            if existing and existing[0] != body:
                raise ValueError("Conflicting operational record")
            db.execute(
                "INSERT OR IGNORE INTO records VALUES(?,?,?)",
                (record_id, stamp.isoformat(), body),
            )
            for name, value in metrics.items():
                old = db.execute(
                    "SELECT value FROM samples WHERE ts=? AND name=?",
                    (stamp.isoformat(), name),
                ).fetchone()
                if old and old[0] != value:
                    raise ValueError("Conflicting metric sample")
                db.execute(
                    "INSERT OR IGNORE INTO samples VALUES(?,?,?)",
                    (stamp.isoformat(), name, value),
                )

    def prometheus(self):
        with sqlite3.connect(self.path) as db:
            rows = db.execute(
                "SELECT name,value FROM samples WHERE ts=(SELECT MAX(ts) FROM samples) ORDER BY name"
            ).fetchall()
        return "".join(f"{name} {value:.12g}\n" for name, value in rows)
