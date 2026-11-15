"""Transactional prospective shadow NAV and frozen-forecast outcome ledger.

Synthetic adjusted-price total-return notionals, not broker shares or orders.
Only previously registered decisions can fill at a later NYSE close.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

from compare_portfolio_models import rebalance_fee
from fourregimestrategies import quadrant
from strategy_integrity import canonical, fingerprint, strict_json, file_hash
from strategy_report import load_training_report
from strategy_training_data import usable_session

REFERENCES = {
    "SPY_reference": {"SPY": 1.0},
    "All_Weather_style_proxy": {
        "SPY": 0.3,
        "TLT": 0.4,
        "IEF": 0.15,
        "GLD": 0.075,
        "DBC": 0.075,
    },
    "Balanced_reference": {"SPY": 0.6, "IEF": 0.4},
}


def schedule(start, end):
    return mcal.get_calendar("NYSE").schedule(start, end)


def next_fill(session, now):
    future = schedule(session, pd.Timestamp(session) + pd.Timedelta(days=15))
    closes = future.market_close[future.market_close > pd.Timestamp(now)]
    if closes.empty:
        raise ValueError("No future execution session")
    return str(closes.index[0].date())


def target_date(session):
    future = schedule(session, pd.Timestamp(session) + pd.Timedelta(days=400)).index
    return str(future[63].date())


def apply_close(state, returns, session):
    """Mark held notionals, then execute a strictly earlier registered decision."""
    state = dict(state)
    old_nav = state["nav"]
    held = state["weights"]
    gross = {s: w * (1 + returns[s]) for s, w in held.items() if w > 0}
    growth = 1 - sum(held.values()) + sum(gross.values())
    if not np.isfinite(growth) or growth <= 0:
        raise ValueError("Invalid prospective account growth")
    weights = {s: v / growth for s, v in gross.items()}
    nav = state["nav"] * growth
    fee = turnover = 0.0
    fill = None
    pending = state.get("pending")
    if pending and pending["fill_session"] == session:
        if pending["decision_session"] >= session:
            raise ValueError("Same-close lookahead fill forbidden")
        target = pending["weights"]
        symbols = sorted(set(weights) | set(target))
        before = np.array([weights.get(s, 0) for s in symbols])
        after = np.array([target.get(s, 0) for s in symbols])
        fee = rebalance_fee(before, after, 0.0015)
        turnover = float(np.abs(after * (1 - fee) - before).sum())
        nav *= 1 - fee
        weights = target
        state["last_fill_session"] = session
        fill = pending
        pending = None
    peak = max(state["peak"], nav)
    dd = nav / peak - 1
    locked = (
        (state["locked"] or dd <= -0.04)
        if state.get("drawdown_controls", True)
        else state["locked"]
    )
    state.update(
        nav=float(nav),
        peak=float(peak),
        weights=weights,
        locked=locked,
        pending=pending,
        maximum_drawdown=min(state["maximum_drawdown"], float(dd)),
    )
    return state, {
        "session": session,
        "net_return": nav / old_nav - 1,
        "nav": nav,
        "drawdown": dd,
        "cash": 1 - sum(weights.values()),
        "fee_fraction": fee,
        "cost_as_initial_capital": old_nav * growth * fee,
        "traded_notional_fraction": turnover,
        "fill": fill,
    }


def advance_from_bundle(bundle, database, evidence, *, now=None):
    now = now or datetime.now(timezone.utc)
    if (
        now.tzinfo is None
        or evidence.get("schema_version") != 2
        or evidence.get("status") != "LOCAL_ACCEPTANCE_PASSED"
    ):
        raise ValueError("Current validated v2 evidence required")
    b = strict_json(bundle)
    report = load_training_report(b["training_report"])
    session = report["market_session"]
    if session != str(usable_session(now).date()) or evidence[
        "report_sha256"
    ] != file_hash(b["training_report"]):
        raise ValueError("Current verified training evidence required")
    capture = strict_json(b["capture"])
    if file_hash(b["capture"]) != report["capture_sha256"]:
        raise ValueError("Capture mismatch")
    capture_root = Path(b["capture"]).parent
    for name, h in capture["files"].items():
        if Path(name).name != name or file_hash(capture_root / name) != h:
            raise ValueError("Capture artifact mismatch")
    prices = pd.read_csv(capture_root / "prices.csv", index_col=0, parse_dates=True)
    contracts = (
        strict_json(b["portfolio_contracts"]) if b.get("portfolio_contracts") else {}
    )
    references = dict(REFERENCES)
    if contracts:
        from portfolio_contract import (
            validate_contract,
            extended_prices,
            normalized_weights,
        )
        from growth_resilience import WEIGHTS

        if file_hash(b["portfolio_contracts"]) != b["contract_map_sha256"]:
            raise ValueError("Contract map changed")
        for key, contract in contracts.items():
            validate_contract(contract)
            if (
                contract["portfolio_key"] != key
                or contract["valuation_session"] != session
            ):
                raise ValueError("Current portfolio identity required")
        benchmark = contracts.get("Growth_Resilience_reference")
        if not benchmark or benchmark["weights"] != dict(sorted(WEIGHTS.items())):
            raise ValueError("Frozen benchmark contract required")
        prices = extended_prices(b["capture"], b["benchmark_extension"])
        references["Growth_Resilience_reference"] = {
            s: w for s, w in WEIGHTS.items() if s != "USD_CASH"
        }
        for row in report["strategies"]:
            c = contracts[row["name"]]
            candidate_weights = normalized_weights({
                **row["candidate"]["weights"],
                "USD_CASH": row["candidate"]["cash"],
            })
            if (
                set(c["weights"])
                != set(candidate_weights)
                or any(
                    abs(c["weights"][s] - w) > 1e-10
                    for s, w in candidate_weights.items()
                )
                or c["model_run_id"] != report["run_id"]
            ):
                raise ValueError("Training candidate and allocation contract disagree")
    features = strict_json(Path(b["training_report"]).parent / "features.json")
    features = {r["date"]: r for r in features}
    protocol = fingerprint(
        {
            "sources": report["source_hashes"],
            "fee_bps": 15,
            "cash_yield": 0.0,
            "fill": "next_NYSE_close_after_registration",
            "version": 2,
            "contracts_enabled": bool(contracts),
            "benchmark_weights": references.get("Growth_Resilience_reference"),
            "contract_code_sha256": file_hash("portfolio_contract.py"),
            "ledger_code_sha256": file_hash(__file__),
        }
    )
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sqlite3.connect(database, timeout=5) as db:
        os.chmod(database, 0o600)
        db.execute("PRAGMA synchronous=FULL")
        db.execute(
            "CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, session TEXT UNIQUE NOT NULL, body TEXT NOT NULL, sha TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TRIGGER IF NOT EXISTS no_updates BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'Immutable ledger'); END"
        )
        db.execute(
            "CREATE TRIGGER IF NOT EXISTS no_deletes BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'Immutable ledger'); END"
        )
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute("SELECT body,sha FROM events ORDER BY seq").fetchall()
        previous_hash = None
        previous = None
        import json

        for body, h in rows:
            event = json.loads(body)
            if fingerprint(event) != h or event["previous_hash"] != previous_hash:
                raise ValueError("Prospective ledger chain mismatch")
            previous, previous_hash = event, h
        if previous and previous["session"] == session:
            if (
                previous["report_sha256"] != evidence["report_sha256"]
                or previous["protocol"] != protocol
            ):
                raise ValueError(
                    "Prospective session already sealed by a different run"
                )
            return {
                "status": "ALREADY_RECORDED",
                "sessions": len(rows),
                "prospective_return_sessions": previous["return_sessions"],
            }
        if previous and (
            previous["session"] >= session or previous["protocol"] != protocol
        ):
            raise ValueError(
                "Chronology or strategy source change requires a new reviewed cohort"
            )
        states = (
            previous["states"]
            if previous
            else {
                n: {
                    "nav": 1.0,
                    "peak": 1.0,
                    "weights": {},
                    "locked": False,
                    "maximum_drawdown": 0.0,
                    "pending": None,
                    "drawdown_controls": False,
                }
                for n in [*[r["name"] for r in report["strategies"]], *references]
            }
        )
        marks = {n: [] for n in states}
        dates = (
            []
            if not previous
            else [
                str(d.date())
                for d in schedule(previous["session"], session).index
                if str(d.date()) > previous["session"]
            ]
        )
        prior = previous["session"] if previous else session
        for date in dates:
            for name, state in states.items():
                held = {s: w for s, w in state["weights"].items() if w > 0}
                returns = {
                    s: float(prices.loc[date, s] / prices.loc[prior, s] - 1)
                    for s in held
                }
                if not all(np.isfinite(v) and v > -1 for v in returns.values()):
                    raise ValueError("Missing held-asset price; no filling allowed")
                old_nav = state["nav"]
                states[name], mark = apply_close(state, returns, date)
                mark["net_return"] = states[name]["nav"] / old_nav - 1
                marks[name].append(mark)
            prior = date
        decision_fill = next_fill(session, now)
        proposals = {r["name"]: r["candidate"]["weights"] for r in report["strategies"]}
        if contracts:
            proposals = {
                key: {
                    s: w
                    for s, w in contracts[key]["weights"].items()
                    if s != "USD_CASH"
                }
                for key in proposals
            }
        proposals.update(references)
        for name, state in states.items():
            # Orders already registered for a future close remain authoritative;
            # a same-session refresh cannot retrospectively replace their fill.
            if name == "Growth_Resilience_reference":
                last = state.get("last_fill_session")
                if state.get("pending") or (
                    last and len(schedule(last, session)) - 1 < 20
                ):
                    continue
            target = dict(proposals[name])
            if name not in references:
                dd = state["nav"] / state["peak"] - 1
                factor = (
                    0.0
                    if state["locked"]
                    else 1.0
                    if not state.get("drawdown_controls", True)
                    else float(np.clip((0.04 + dd) / 0.02, 0, 1))
                )
                target = {s: w * factor for s, w in target.items()}
            if (
                not all(np.isfinite(w) and w >= 0 for w in target.values())
                or sum(target.values()) > 1 + 1e-8
            ):
                raise ValueError("Invalid prospective target")
            state["pending"] = {
                "decision_session": session,
                "recorded_at": now.isoformat(),
                "fill_session": decision_fill,
                "weights": target,
                "run_id": report["run_id"],
                "contract_id": contracts.get(name, {}).get("contract_id"),
            }
        forecasts = [] if not previous else previous["forecasts"]
        for item in forecasts:
            if item["status"] == "PENDING" and item["target_session"] <= session:
                actual = features.get(item["target_session"])
                if not actual or not actual.get("macro_valid", True):
                    item["status"] = "OUTCOME_UNAVAILABLE"
                else:
                    label = quadrant(actual)
                    onehot = np.eye(4)[label]
                    item.update(
                        status="MATURED",
                        outcome_quadrant=int(label),
                        brier_model=float(
                            np.square(np.array(item["model"]) - onehot).sum()
                        ),
                        brier_baseline=float(
                            np.square(np.array(item["baseline"]) - onehot).sum()
                        ),
                        scored_at=now.isoformat(),
                        outcome_source_sha256=evidence["report_sha256"],
                    )
        forecast = report["classifier"]["latest_forecast"]
        forecasts.append(
            {
                "origin_session": session,
                "registered_at": now.isoformat(),
                "target_session": target_date(session),
                "model": forecast["model"],
                "baseline": forecast["baseline"],
                "used": forecast["used"],
                "enabled": forecast["enabled"],
                "run_id": report["run_id"],
                "status": "PENDING",
            }
        )
        event = {
            "schema_version": 1,
            "session": session,
            "recorded_at": now.isoformat(),
            "previous_hash": previous_hash,
            "protocol": protocol,
            "report_sha256": evidence["report_sha256"],
            "capture_sha256": report["capture_sha256"],
            "portfolio_contracts": contracts,
            "benchmark_extension_sha256": file_hash(
                Path(b["benchmark_extension"]) / "capture.json"
            )
            if contracts
            else None,
            "states": states,
            "marks": marks,
            "forecasts": forecasts,
            "return_sessions": (previous["return_sessions"] if previous else 0)
            + len(dates),
            "missed_decision_sessions": dates[:-1],
            "release_approved": False,
            "assumptions": [
                "Synthetic adjusted total-return notionals; not broker fills.",
                "15 bps traded notional; zero cash yield; before user taxes/platform fees.",
                "Gap catch-up values existing positions/previously registered fills only; no invented historical decisions.",
            ],
        }
        h = fingerprint(event)
        db.execute(
            "INSERT INTO events(session,body,sha) VALUES (?,?,?)",
            (session, canonical(event), h),
        )
        db.commit()
        return {
            "status": "PROSPECTIVE_BOOTSTRAP"
            if not previous
            else "PROSPECTIVE_ADVANCE",
            "sessions": len(rows) + 1,
            "prospective_return_sessions": event["return_sessions"],
            "next_fill_session": decision_fill,
            "chain_head": h,
            "nav": {n: s["nav"] for n, s in states.items()},
            "release_approved": False,
        }


def summary(database):
    import json

    with sqlite3.connect(f"file:{Path(database).resolve()}?mode=ro", uri=True) as db:
        rows = db.execute("SELECT body,sha FROM events ORDER BY seq").fetchall()
    previous = None
    events = []
    for body, h in rows:
        event = json.loads(body)
        if fingerprint(event) != h or event["previous_hash"] != previous:
            raise ValueError("Prospective chain integrity failure")
        previous = h
        events.append(event)
    if not events:
        return {"status": "NOT_STARTED", "release_approved": False}
    last = events[-1]
    metrics = {}
    for name, state in last["states"].items():
        marks = [m for e in events for m in e["marks"][name]]
        returns = np.array([m["net_return"] for m in marks])
        metrics[name] = {
            "nav": state["nav"],
            "total_return": state["nav"] - 1,
            "maximum_drawdown": state["maximum_drawdown"],
            "annualized_volatility": float(returns.std(ddof=1) * np.sqrt(252))
            if len(returns) > 1
            else None,
            "cagr": float(state["nav"] ** (252 / len(returns)) - 1)
            if len(returns) >= 252
            else None,
            "cost_as_initial_capital": sum(m["cost_as_initial_capital"] for m in marks),
            "return_sessions": len(marks),
            "cash": 1 - sum(state["weights"].values()),
            "cash_locked": state["locked"],
        }
    matured = [f for f in last["forecasts"] if f["status"] == "MATURED"]
    return {
        "schema_version": 1,
        "status": "PROSPECTIVE_BOOTSTRAP"
        if last["return_sessions"] == 0
        else "PROSPECTIVE_SHADOW_TRACK_RECORD",
        "first_registered_at": events[0]["recorded_at"],
        "last_session": last["session"],
        "observed_decision_sessions": len(events),
        "return_sessions": last["return_sessions"],
        "missed_decision_sessions": [
            d for e in events for d in e["missed_decision_sessions"]
        ],
        "metrics": metrics,
        "forecast_outcomes": {
            "registered": len(last["forecasts"]),
            "matured": len(matured),
            "unavailable": sum(
                f["status"] == "OUTCOME_UNAVAILABLE" for f in last["forecasts"]
            ),
            "model_brier": float(np.mean([f["brier_model"] for f in matured]))
            if matured
            else None,
            "baseline_brier": float(np.mean([f["brier_baseline"] for f in matured]))
            if matured
            else None,
        },
        "chain_head": previous,
        "release_approved": False,
        "assumptions": last["assumptions"],
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("var/strategy-operations-integrated-v1/prospective.sqlite3"),
    )
    args = parser.parse_args()
    print(json.dumps(summary(args.database), indent=2, allow_nan=False))
