"""Isolated forward-only registration for frozen return-engine challengers.

No order or promotion capability. Incumbent cohorts are never opened for writes.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sqlite3
from copy import deepcopy
import numpy as np
from institutional_return_engines import (
    context,
    proposal,
    validate_weights,
    limits,
    NAMES,
    VERSION,
    PROTOCOL,
)
from portfolio_contract import extended_prices, make_contract
from prospective_strategy_ledger import apply_close, next_fill, schedule
from strategy_monthly_report import read_events
from strategy_training_data import usable_session
from strategy_report import load_training_report
from strategy_integrity import file_hash, fingerprint, canonical


def advance(bundle, assessment, robustness, database, *, now=None):
    now = now or datetime.now(timezone.utc)
    b = json.loads(Path(bundle).read_text())
    a = json.loads(Path(assessment).read_text())
    check = json.loads(Path(robustness).read_text())
    if (
        now.tzinfo is None
        or check["assessment_sha256"] != file_hash(assessment)
        or any(file_hash(p) != h for p, h in a["source_hashes"].items())
        or any(file_hash(p) != h for p, h in check["source_artifacts"].items())
    ):
        raise ValueError(
            "Frozen evaluated challenger and reconciled artifacts required"
        )
    report = load_training_report(b["training_report"])
    if (
        not report["current_numerical_source_match"]
        or file_hash(bundle) != a["inputs"]["bundle_sha256"]
        or report["market_session"] != str(usable_session(now).date())
    ):
        raise ValueError("Fresh source-matched challenger inputs required")
    prices = extended_prices(b["capture"], b["benchmark_extension"]).drop(
        columns=["XLV"]
    )
    features = {
        r["date"]: r
        for r in json.loads(
            (Path(b["training_report"]).parent / "features.json").read_text()
        )
    }
    session = report["market_session"]
    ctx = context(prices, len(prices) - 1, features)
    candidates = {n: proposal(n, ctx) for n in NAMES}
    contracts = {
        f"institutional_v1_{n}": make_contract(
            f"institutional_v1_{n}",
            r["weights"],
            session,
            VERSION,
            basis="FROZEN_INSTITUTIONAL_METHOD_CHALLENGER",
            performance="UNAPPROVED_PROSPECTIVE_SHADOW",
            policy=VERSION,
        )
        for n, r in candidates.items()
    }
    protocol = fingerprint(
        {
            "engine": file_hash("institutional_return_engines.py"),
            "ledger": file_hash(__file__),
            "marking_code": file_hash("prospective_strategy_ledger.py"),
            "parameters": PROTOCOL,
        }
    )
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if database.is_symlink():
        raise ValueError("Regular isolated ledger required")
    with sqlite3.connect(database, timeout=10) as db:
        os.chmod(database, 0o600)
        db.execute("PRAGMA synchronous=FULL")
        db.execute(
            "CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY,session TEXT UNIQUE,body TEXT NOT NULL,sha TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TRIGGER IF NOT EXISTS no_updates BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'Immutable ledger'); END"
        )
        db.execute(
            "CREATE TRIGGER IF NOT EXISTS no_deletes BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'Immutable ledger'); END"
        )
        db.execute("BEGIN IMMEDIATE")
        events = read_events(database)
        old = events[-1][0] if events else None
        if old and old["protocol"] != protocol:
            raise ValueError("Changed engine requires a separately reviewed new cohort")
        if old and old["session"] == session:
            if old["assessment_sha256"] != file_hash(assessment):
                raise ValueError("Session already sealed with another evaluation")
            return {
                "status": "ALREADY_REGISTERED",
                "observed_sessions": len(events),
                "return_sessions": old["return_sessions"],
                "release_approved": False,
            }
        if old and old["session"] >= session:
            raise ValueError("Prospective backfill prohibited")
        states = (
            deepcopy(old["states"])
            if old
            else {
                k: {
                    "nav": 1.0,
                    "peak": 1.0,
                    "weights": {},
                    "locked": False,
                    "maximum_drawdown": 0.0,
                    "pending": None,
                    "drawdown_controls": False,
                }
                for k in contracts
            }
        )
        marks = {k: [] for k in states}
        dates = (
            []
            if not old
            else [
                str(d.date())
                for d in schedule(old["session"], session).index
                if str(d.date()) > old["session"]
            ]
        )
        previous = old["session"] if old else session
        for date in dates:
            for key, state in list(states.items()):
                returns = {
                    s: float(prices.loc[date, s] / prices.loc[previous, s] - 1)
                    for s, w in state["weights"].items()
                    if w > 0
                }
                if not all(np.isfinite(v) and v > -1 for v in returns.values()):
                    raise ValueError("Missing held price")
                states[key], mark = apply_close(state, returns, date)
                marks[key].append(mark)
            previous = date
        fill = next_fill(session, now)
        for n, r in candidates.items():
            key = f"institutional_v1_{n}"
            state = states[key]
            last = state.get("last_fill_session")
            current = np.array([state["weights"].get(s, 0.0) for s in ctx["symbols"]])
            ceiling, exposure = limits(n, ctx)
            variance = float(current @ ctx["cov"] @ current)
            shares = (
                current * (ctx["cov"] @ current) / variance
                if variance > 1e-15
                else np.zeros(len(current))
            )
            urgent = (
                current.sum() > exposure + 0.01
                or current.max(initial=0) > 0.26
                or variance > (ceiling * 1.10) ** 2
                or shares.max(initial=0) > 0.30
            )
            due = not last or len(schedule(last, session)) - 1 >= 20
            if state.get("pending"):
                continue
            target = dict(r["weights"])
            distance = sum(
                abs(target.get(s, 0) - state["weights"].get(s, 0))
                for s in set(target) | set(state["weights"])
            )
            if not urgent and (
                not due or last and distance < PROTOCOL["discretionary_trade_band"]
            ):
                continue
            if last and not urgent:
                half = {
                    s: (target.get(s, 0) + state["weights"].get(s, 0)) / 2
                    for s in set(target) | set(state["weights"])
                }
                if validate_weights(
                    np.array([half.get(s, 0) for s in ctx["symbols"]]), n, ctx
                ) and not (set(half) - set(ctx["symbols"])):
                    target = half
            contract = make_contract(
                key,
                target,
                session,
                VERSION,
                basis="REGISTERED_NEXT_CLOSE_CHALLENGER_TARGET",
                performance="UNAPPROVED_PROSPECTIVE_SHADOW",
                policy=VERSION,
            )
            contracts[key] = contract
            state["pending"] = {
                "decision_session": session,
                "recorded_at": now.isoformat(),
                "fill_session": fill,
                "weights": target,
                "run_id": VERSION,
                "contract_id": contract["contract_id"],
            }
        event = {
            "schema_version": 1,
            "session": session,
            "recorded_at": now.isoformat(),
            "protocol": protocol,
            "previous_hash": events[-1][1] if events else None,
            "assessment_sha256": file_hash(assessment),
            "report_sha256": file_hash(b["training_report"]),
            "portfolio_contracts": contracts,
            "states": states,
            "marks": marks,
            "return_sessions": (old["return_sessions"] if old else 0) + len(dates),
            "missed_decision_sessions": dates[:-1],
            "forecasts": [],
            "release_approved": False,
            "assumptions": [
                "Synthetic adjusted-return notionals, not orders or broker shares.",
                "15 bps actual risky-asset dollars traded; zero unverified cash interest; no tax or platform-fee assumption.",
                "Separate unapproved challenger cohort; no alteration or promotion of incumbents.",
            ],
        }
        digest = fingerprint(event)
        db.execute(
            "INSERT INTO events(session,body,sha) VALUES (?,?,?)",
            (session, canonical(event), digest),
        )
        db.commit()
    return {
        "status": "UNAPPROVED_FORWARD_CHALLENGERS_REGISTERED",
        "observed_sessions": len(events) + 1,
        "return_sessions": event["return_sessions"],
        "next_fill_session": fill,
        "chain_head": digest,
        "release_approved": False,
    }


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--bundle", default="var/investor-dashboard/latest-strategy-run.json"
    )
    p.add_argument(
        "--assessment",
        default="var/institutional-return-engines/v1-validated/assessment.json",
    )
    p.add_argument(
        "--robustness",
        default="var/institutional-return-engines/v1-validated/robustness.json",
    )
    p.add_argument(
        "--database", default="var/return-engine-shadow-v1/prospective.sqlite3"
    )
    a = p.parse_args()
    print(
        json.dumps(advance(a.bundle, a.assessment, a.robustness, a.database), indent=2)
    )
