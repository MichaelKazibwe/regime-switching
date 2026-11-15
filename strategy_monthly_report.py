"""Completed-month reports from immutable contract-bound shadow events.

No live-account balance or missing monthly boundary is inferred.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import numpy as np
from monthlyreport import build_summary, period_bounds, MonthlyReportError
from portfolio_contract import validate_contract
from strategy_integrity import fingerprint
from prospective_strategy_ledger import schedule


def read_events(database):
    database = Path(database)
    if database.is_symlink() or not database.is_file():
        raise ValueError("Regular shadow ledger required")
    with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Corrupt shadow database")
        rows = db.execute("SELECT body,sha FROM events ORDER BY seq").fetchall()
    previous = None
    events = []
    for body, digest in rows:
        e = json.loads(body)
        if fingerprint(e) != digest or e["previous_hash"] != previous:
            raise ValueError("Shadow event chain mismatch")
        for key, c in e.get("portfolio_contracts", {}).items():
            validate_contract(c)
            if c["portfolio_key"] != key or c["valuation_session"] != e["session"]:
                raise ValueError("Wrong event portfolio contract")
        events.append((e, digest))
        previous = digest
    return events


def build_strategy_summary(
    database, month, portfolio_id, *, now=None, notional=100000.0
):
    now = now or datetime.now(timezone.utc)
    start, end = period_bounds(month)
    if now.tzinfo is None or end > now or not np.isfinite(notional) or notional <= 0:
        raise MonthlyReportError(
            "Completed month and positive illustrative notional required"
        )
    # Reuse report schema without crawling another portfolio's records.
    summary = build_summary(
        Path("/__no_strategy_report_directory__"),
        month,
        now=now,
        portfolio_id=portfolio_id,
    )
    history = []
    sources = []
    identities = []
    last_state = None
    for e, digest in read_events(database):
        if datetime.fromisoformat(e["recorded_at"]) >= end:
            continue
        c = e.get("portfolio_contracts", {}).get(portfolio_id)
        if not c:
            continue
        if e["states"].get(portfolio_id) is None:
            raise ValueError("Contract has no matching account")
        for mark in e["marks"][portfolio_id]:
            if mark["session"] > e["session"]:
                raise ValueError("Future mark in ledger")
            history.append(mark)
        last_state = e["states"][portfolio_id]
        if start.date().isoformat() <= e["session"]:
            identities.append(c)
            sources.append({"session": e["session"], "sha256": digest})
    history.sort(key=lambda m: m["session"])
    if len({m["session"] for m in history}) != len(history):
        raise ValueError("Duplicate monthly valuation")
    opening_dates = schedule(start.date().isoformat(), end.date().isoformat()).index
    expected = [
        str(d.date()) for d in opening_dates if start.date() <= d.date() < end.date()
    ]
    from tradingcalendar import TradingCalendar

    open_session = str(TradingCalendar().latest_completed_session(start).date())
    close_session = str(TradingCalendar().latest_completed_session(end).date())
    before = next((m for m in reversed(history) if m["session"] == open_session), None)
    selected = [m for m in history if m["session"] in expected]
    close = next((m for m in reversed(selected) if m["session"] == close_session), None)
    observed = {m["session"] for m in selected}
    missing = sorted(set(expected) - observed)
    first = before["nav"] if before else None
    last = selected[-1] if selected else None
    valid = before is not None and close is not None and not missing
    peak = first or (selected[0]["nav"] if selected else 1.0)
    worst = 0.0
    for m in selected:
        peak = max(peak, m["nav"])
        worst = min(worst, m["nav"] / peak - 1)
    summary.update(
        kind="CONTRACT_BOUND_PROSPECTIVE_SHADOW",
        valuation_basis="USD_ILLUSTRATIVE_NOTIONAL_NOT_BROKER_ASSETS",
        notional_capital=notional,
        portfolio_contracts=identities,
        database_verified=True,
        sources=sources,
        source_fingerprint=fingerprint(
            {"sources": sources, "contracts": identities, "portfolio_key": portfolio_id}
        ),
        coverage="NO_DATA" if not selected else "COMPLETE" if valid else "PARTIAL",
        observed_sessions=len(observed),
        expected_sessions=len(expected),
        missing_sessions=missing,
        opening_boundary_available=before is not None,
        closing_boundary_available=close is not None,
        opening_nav=first * notional if first else None,
        closing_nav=last["nav"] * notional if last else None,
        monthly_return=close["nav"] / first - 1 if valid else None,
        benchmark_return=None,
        active_return=None,
        benchmark="Separate benchmark account; no inferred monthly comparison",
        observed_drawdown=-worst if selected else None,
        monthly_costs=sum(m["cost_as_initial_capital"] for m in selected) * notional
        if selected
        else None,
        monthly_turnover=sum(m["traded_notional_fraction"] for m in selected)
        if selected
        else None,
        cycle_count=len(selected),
        rebalances=sum(bool(m["fill"]) for m in selected),
        orders=0,
        cash=last["cash"] * last["nav"] * notional if last else None,
        last_observation=last["session"] if last else None,
        nav_history=[
            {"date": m["session"], "nav": m["nav"] * notional}
            for m in (([before] if before else []) + selected)
        ],
        holdings={
            s: {"shares": None, "market_value": w * last["nav"] * notional, "weight": w}
            for s, w in (last_state or {}).get("weights", {}).items()
        }
        if last
        else {},
        status_counts={"VERIFIED_SHADOW_MARK": len(selected)},
        regime_counts={},
    )
    return summary
