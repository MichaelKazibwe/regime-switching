"""Read-only numerical audit of the portable dashboard, separate from user accounts."""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from growth_resilience import WEIGHTS, backtest
from pilot_release import verify_context, verify_snapshot, materialize_snapshot
from strategy_dashboard_server import Application
from strategy_integrity import strict_json, file_hash
from strategy_receipts import atomic_json
from strategy_training_data import usable_session


def statistics(nav, returns):
    nav, returns = np.asarray(nav), np.asarray(returns)
    peak = np.maximum.accumulate(np.concatenate(([1.0], nav)))[1:]
    return dict(total_return=float(nav[-1] - 1),
                cagr=float(nav[-1] ** (252 / len(nav)) - 1),
                annual_volatility=float(np.std(returns, ddof=1) * np.sqrt(252)),
                maximum_drawdown=float(np.min(nav / peak - 1)),
                daily_expected_shortfall95=float(-returns[returns <= np.quantile(returns, .05)].mean()))


def audit(root, state, cycle_curve):
    root, state = Path(root), Path(state)
    source = verify_context(Path.cwd())
    verify_snapshot(root)
    launch = strict_json(root / "launch.json")
    app = Application(materialize_snapshot(root, state), root / launch["capture"],
                      root / launch["training_report"], state / "pdfs")
    p, checks = app.payload, {}

    def check(name, passed):
        checks[name] = bool(passed)

    def compare(name, actual, expected):
        check(name, np.isfinite(actual) and np.isclose(actual, expected, rtol=1e-8, atol=1e-10))

    def allocation(name, weights, cash=None, risk=None):
        values = list(weights.values()) + ([] if cash is None else [cash])
        check(name + ": finite nonnegative capital", all(np.isfinite(v) and v >= -1e-10 for v in values))
        compare(name + ": capital reconciles", sum(values), 1)
        if risk:
            compare(name + ": signed risk reconciles", sum(risk.values()), 1 if any(abs(v) > 1e-10 for v in risk.values()) else 0)

    session = p["training"]["market_session"]
    check("current completed market session", session == str(usable_session(datetime.now(timezone.utc)).date()))
    check("price and training date agree", p["latest_market"]["session"] == session)
    prices = pd.read_csv(root / "market/prices.csv", index_col=0, parse_dates=True)
    check("captured final price date", str(prices.index[-1].date()) == session)
    for symbol, displayed in p["latest_market"]["instruments"].items():
        compare(symbol + ": displayed close matches captured price", displayed["close"], prices.loc[session, symbol])
        check(symbol + ": history ends on displayed session", displayed["history"][-1][0] == session)
        compare(symbol + ": chart endpoint matches displayed close", displayed["history"][-1][1], displayed["close"])
    for plan in p["plans"]:
        allocation(plan["title"], plan["allocation"]["weights"], risk=plan["allocation"]["variance_contributions"])
        check(plan["title"] + ": archive date not newer than market", plan["price_session"] <= session)
        check(plan["title"] + ": no executable recommendation", plan["allocation"]["executable"] is False)
    for strategy, presets in p["allocation_lab"]["results"].items():
        for preset, result in presets.items():
            allocation(strategy + ":" + preset, result["weights"], result["cash"])
            check(strategy + ": dated scenario", result["market_session"] == session)
    g = p["growth_resilience"]
    allocation("Growth reference", g["weights"], risk={a["symbol"]: a["variance_share"] for a in g["assets"]})
    prices["XLV"] = pd.read_csv(root / "extension/XLV-adjusted.csv", index_col=0, parse_dates=True)["XLV"]
    symbols = [s for s in WEIGHTS if s != "USD_CASH"]
    first = max(prices[s].first_valid_index() for s in symbols)
    daily = prices.loc[first:, symbols].pct_change(fill_method=None).iloc[1:]
    check("Growth common history contains no filled gaps", np.isfinite(daily.to_numpy()).all())
    check("Growth history date and sample count", len(daily) == g["sessions"] and str(daily.index[-1].date()) == g["end"])
    refs = {"Growth & Resilience": WEIGHTS, "US equity": {"SPY": 1}, "60/40 US": {"SPY": .6, "IEF": .4},
            "All Weather-style proxy": {"SPY": .3, "TLT": .4, "IEF": .15, "GLD": .075, "DBC": .075}}
    for name, weights in refs.items():
        nav, returns, _ = backtest(daily, weights)
        for key, value in statistics(nav, returns).items():
            compare(name + ": independent " + key, g["metrics"][name][key], value)
        compare(name + ": plotted terminal return", g["chart"]["series"][name][-1] - 1, g["metrics"][name]["total_return"])
    d = p["dynamic_portfolio"]
    allocation("Dynamic", d["snapshot"]["weights"], d["snapshot"]["cash"], d["snapshot"]["risk_shares"])
    compare("Dynamic plotted terminal return", d["history"][-1]["equity"] - 1, d["assessment"]["metrics"]["15bps"]["total_return"])
    for row in p["return_engines"]["assessment"]["strategies"]:
        a = row["candidate"]
        allocation("Return engine " + row["name"], a["weights"], a["cash"], a["risk_shares"])
    b = strict_json(root / "benchmark.json")
    allocation("Cycle reference", b["latest"]["weights"], b["latest"]["cash"], b["latest"]["risk_shares"])
    frame = pd.read_csv(cycle_curve)
    for key, value in statistics(frame.equity, frame["return"]).items():
        compare("Cycle held-out independent " + key, b["test"][key], value)
    check("Cycle held-out start", frame.date.iloc[0] == b["protocol"]["test_start"])
    check("Cycle latest date explicitly separate", b["market_session"] <= session)
    for name, result in b["scenarios"].items():
        fan = np.asarray(result["fan"])
        check(name + ": ordered finite simulated fan", result["status"] == "SIMULATED" and np.isfinite(fan).all() and (np.diff(fan, axis=0) >= -1e-12).all())
        compare(name + ": median reconciles to fan", fan[1, -1] - 1, result["median_return"])
    return dict(status="PASSED_NUMERICAL_DASHBOARD_AUDIT" if all(checks.values()) else "FAILED_NUMERICAL_DASHBOARD_AUDIT",
                checked_at=datetime.now(timezone.utc).isoformat(), source_release_id=source["release_id"],
                snapshot_manifest_sha256=file_hash(root / "snapshot-manifest.json"), market_session=session,
                benchmark_session=b["market_session"], passed=sum(checks.values()), total=len(checks), checks=checks,
                boundaries=["Agreement with captured inputs is not independent verification of the upstream vendor",
                            "Historical performance and simulated scenarios do not establish future returns",
                            "No user credentials, sessions or portfolios were modified"], execution_enabled=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--cycle-curve", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.snapshot_root, args.state, args.cycle_curve)
    atomic_json(args.output, result)
    print({k: result[k] for k in ["status", "passed", "total", "market_session", "benchmark_session"]})
    if not all(result["checks"].values()):
        print([k for k, v in result["checks"].items() if not v])
        raise SystemExit(1)
