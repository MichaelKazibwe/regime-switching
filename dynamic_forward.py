"""Separate, forward-only dynamic paper cohort. Never orders or promotion."""

from datetime import datetime, timezone
from pathlib import Path
from copy import deepcopy
import os
import sqlite3
import numpy as np

from dynamic_portfolio import refresh
from institutional_return_engines import context, validate_weights
from portfolio_contract import extended_prices
from prospective_strategy_ledger import apply_close, schedule, next_fill
from strategy_monthly_report import read_events
from strategy_integrity import strict_json, file_hash, fingerprint, canonical

KEY = "Dynamic_Growth_Resilience"


def advance(bundle, database, *, now=None):
    from tempfile import TemporaryDirectory

    now = now or datetime.now(timezone.utc)
    with TemporaryDirectory() as root:
        snapshot = refresh(bundle, Path(root) / "snapshot.json", now=now)
    b = strict_json(bundle)
    prices = extended_prices(b["capture"], b["benchmark_extension"]).drop(
        columns=["XLV"]
    )
    features = {
        r["date"]: r
        for r in strict_json(Path(b["training_report"]).parent / "features.json")
    }
    ctx = context(prices, len(prices) - 1, features)
    protocol = fingerprint(
        {
            p: file_hash(p)
            for p in (
                __file__,
                "dynamic_portfolio.py",
                "institutional_return_engines.py",
                "prospective_strategy_ledger.py",
            )
        }
    )
    path = Path(database)
    if path.is_symlink():
        raise ValueError("Regular isolated cohort database required")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sqlite3.connect(path, timeout=10) as db:
        os.chmod(path, 0o600)
        db.execute("PRAGMA synchronous=FULL")
        db.executescript("""
          CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY,session TEXT UNIQUE,body TEXT NOT NULL,sha TEXT NOT NULL);
          CREATE TRIGGER IF NOT EXISTS immutable_dynamic_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'Immutable'); END;
          CREATE TRIGGER IF NOT EXISTS immutable_dynamic_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'Immutable'); END;
        """)
        db.execute("BEGIN IMMEDIATE")
        events = read_events(path)
        old = events[-1][0] if events else None
        session = snapshot["decision_session"]
        if old and old["protocol"] != protocol:
            raise ValueError("Changed dynamic policy requires a new cohort")
        if old and old["session"] == session:
            if old["snapshot_id"] != snapshot["snapshot_id"]:
                raise ValueError("Session already sealed with another dynamic snapshot")
            return dict(
                status="ALREADY_REGISTERED",
                observed_sessions=len(events),
                return_sessions=old["return_sessions"],
                release_approved=False,
            )
        if old and old["session"] > session:
            raise ValueError("Prospective backfill prohibited")
        state = (
            deepcopy(old["states"][KEY])
            if old
            else dict(
                nav=1.0,
                peak=1.0,
                weights={},
                locked=False,
                maximum_drawdown=0.0,
                pending=None,
                drawdown_controls=False,
            )
        )
        dates = (
            []
            if not old
            else [
                str(d.date())
                for d in schedule(old["session"], session).index
                if str(d.date()) > old["session"]
            ]
        )
        marks = []
        previous = old["session"] if old else session
        for date in dates:
            returns = {
                s: float(prices.loc[date, s] / prices.loc[previous, s] - 1)
                for s, w in state["weights"].items()
                if w > 0
            }
            if not all(np.isfinite(v) and v > -1 for v in returns.values()):
                raise ValueError("Missing held mark")
            state, mark = apply_close(state, returns, date)
            marks.append(mark)
            previous = date
        w = np.array([state["weights"].get(s, 0) for s in ctx["symbols"]])
        urgent = not validate_weights(w, "economic_balance", ctx)
        last = state.get("last_fill_session")
        due = not last or len(schedule(last, session)) - 1 >= 21
        distance = sum(
            abs(snapshot["weights"].get(s, 0) - state["weights"].get(s, 0))
            for s in set(snapshot["weights"]) | set(state["weights"])
        )
        if not state.get("pending") and (
            urgent or due and (not last or distance >= 0.04)
        ):
            state["pending"] = dict(
                decision_session=session,
                recorded_at=now.isoformat(),
                fill_session=next_fill(session, now),
                weights=snapshot["weights"],
                run_id=snapshot["version"],
                contract_id=snapshot["contract"]["contract_id"],
            )
        event = dict(
            schema_version=1,
            session=session,
            recorded_at=now.isoformat(),
            protocol=protocol,
            previous_hash=events[-1][1] if events else None,
            snapshot_id=snapshot["snapshot_id"],
            portfolio_contracts={KEY: snapshot["contract"]},
            states={KEY: state},
            marks={KEY: marks},
            return_sessions=(old["return_sessions"] if old else 0) + len(dates),
            missed_decision_sessions=dates[:-1],
            forecasts=[],
            release_approved=False,
        )
        digest = fingerprint(event)
        db.execute(
            "INSERT INTO events(session,body,sha) VALUES (?,?,?)",
            (session, canonical(event), digest),
        )
    return dict(
        status="UNAPPROVED_DYNAMIC_COHORT",
        observed_sessions=len(events) + 1,
        return_sessions=event["return_sessions"],
        next_fill_session=state.get("pending", {}).get("fill_session")
        if state.get("pending")
        else None,
        release_approved=False,
    )
