"""Independent prospective challenger cohorts; never edits the original ledger."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import os

import numpy as np

from prospective_strategy_ledger import apply_close, next_fill, schedule
from stress_budget_challenger import allocate, trade_decision, finalize_target
from strategy_integrity import fingerprint, canonical
from strategy_training_data import usable_session


def advance(
    database, prices, feature, history, cov, config, variant, source, *, now=None
):
    now = now or datetime.now(timezone.utc)
    session = str(prices.index[-1].date())
    if now.tzinfo is None or session != str(usable_session(now).date()):
        raise ValueError("Current completed-session snapshot required")
    name, fallback, cost_aware = variant
    protocol = fingerprint(
        {"config": config, "variant": variant, "sources": source["policy_sources"]}
    )
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sqlite3.connect(database, timeout=5) as db:
        os.chmod(database, 0o600)
        db.execute("PRAGMA synchronous=FULL")
        db.execute(
            "CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, session TEXT UNIQUE, body TEXT, sha TEXT)"
        )
        db.execute(
            "CREATE TRIGGER IF NOT EXISTS immutable_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'Immutable'); END"
        )
        db.execute(
            "CREATE TRIGGER IF NOT EXISTS immutable_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'Immutable'); END"
        )
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute("SELECT body,sha FROM events ORDER BY seq").fetchall()
        previous = None
        head = None
        import json

        for body, h in rows:
            event = json.loads(body)
            if fingerprint(event) != h or event["previous_hash"] != head:
                raise ValueError("Challenger chain mismatch")
            previous = event
            head = h
        if previous and previous["protocol"] != protocol:
            raise ValueError("Changed challenger protocol requires new explicit cohort")
        if previous and previous["session"] == session:
            if previous["source"] != source:
                raise ValueError("Conflicting same-session source")
            return {
                "status": "ALREADY_REGISTERED",
                "variant": name,
                "forward_return_sessions": previous["return_sessions"],
                "nav": previous["state"]["nav"],
            }
        if previous and previous["session"] > session:
            raise ValueError("Backfill forbidden")
        state = (
            previous["state"]
            if previous
            else {
                "nav": 1.0,
                "peak": 1.0,
                "weights": {},
                "locked": False,
                "drawdown_controls": config.get("cash_lock") is not None,
                "maximum_drawdown": 0.0,
                "pending": None,
            }
        )
        marks = []
        dates = []
        prior = previous["session"] if previous else session
        if previous:
            dates = [
                str(d.date())
                for d in schedule(prior, session).index
                if str(d.date()) > prior
            ]
            for date in dates:
                returns = {
                    s: float(prices.loc[date, s] / prices.loc[prior, s] - 1)
                    for s, w in state["weights"].items()
                    if w > 0
                }
                if not all(np.isfinite(x) and x > -1 for x in returns.values()):
                    raise ValueError("Held prices missing")
                state, mark = apply_close(state, returns, date)
                marks.append(mark)
                prior = date
        valid = bool(feature and feature.get("macro_valid", True))
        dd = state["nav"] / state["peak"] - 1
        target = allocate(
            history,
            cov,
            config,
            current=state["weights"],
            drawdown=dd,
            macro_valid=valid,
            market_fallback=fallback,
            locked=state["locked"],
        )
        from portfolio_objectives import drawdown_factor

        factor = drawdown_factor(
            dd,
            config.get("protective_start"),
            config.get("cash_lock"),
            locked=state["locked"],
        )
        target = finalize_target(
            target,
            cov,
            list(history),
            config,
            factor=factor,
            drawdown=dd,
            degraded=not valid,
        )
        last_trade = previous.get("last_trade_session") if previous else None
        for mark in marks:
            if mark["fill"]:
                last_trade = mark["session"]
        elapsed = len(schedule(last_trade, session)) - 1 if last_trade else 999
        decision = trade_decision(
            state["weights"],
            target,
            cov,
            history,
            config,
            drawdown=dd,
            macro_valid=valid,
            market_fallback=fallback,
            sessions_since_trade=elapsed,
            cost_aware=cost_aware,
            locked=state["locked"],
        )
        target.pop("calculation_id", None)
        target["calculation_id"] = fingerprint(target)
        if decision["trade"]:
            state["pending"] = {
                "decision_session": session,
                "recorded_at": now.isoformat(),
                "fill_session": next_fill(session, now),
                "weights": target["weights"],
            }
        event = {
            "schema_version": 1,
            "session": session,
            "registered_at": now.isoformat(),
            "protocol": protocol,
            "variant": name,
            "previous_hash": head,
            "state": state,
            "marks": marks,
            "decision": decision,
            "proposal": target,
            "source": source,
            "return_sessions": (previous["return_sessions"] if previous else 0)
            + len(dates),
            "last_trade_session": last_trade,
            "missed_decision_sessions": dates[:-1],
            "execution_enabled": False,
            "promotion_enabled": False,
        }
        h = fingerprint(event)
        db.execute(
            "INSERT INTO events(session,body,sha) VALUES (?,?,?)",
            (session, canonical(event), h),
        )
        db.commit()
        return {
            "status": "NEW_SHADOW_COHORT" if not previous else "ADVANCED_SHADOW_COHORT",
            "variant": name,
            "nav": state["nav"],
            "forward_return_sessions": event["return_sessions"],
            "pending_fill": state["pending"],
            "chain_head": h,
            "promotion_enabled": False,
        }
