"""Execute the finite improvement protocol without modifying active strategies."""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from performance_forecasts import study as forecast_study
from performance_portfolios import (
    Experiments, VARIANTS, GROUP_RISK_CAPS, summarize, objective, reconciliation,
    cash_attribution, paired, risk_diagnostics,
)
from institutional_return_engines import NAMES
from portfolio_contract import extended_prices
from strategy_integrity import strict_json, file_hash, fingerprint
from strategy_receipts import atomic_json
from strategy_report import load_training_report
from prospective_strategy_ledger import next_fill
from strategy_training_data import usable_session
from economic_design_assessment import replay

VERSION = "PERFORMANCE_IMPROVEMENTS_V1"
SOURCES = (
    "run_performance_improvements.py", "performance_forecasts.py",
    "performance_portfolios.py", "forecast_calibration.py", "live_strategy_training.py",
    "evaluate_institutional_engines.py", "institutional_return_engines.py",
    "institutionalportfolio.py", "portfolio_risk_envelope.py", "portfolio_contract.py",
    "compare_portfolio_models.py", "growth_resilience.py", "economic_design_assessment.py",
    "fourregimestrategies.py", "prospective_strategy_ledger.py",
    "research/four_macro_strategies.json", "requirements-paper.hashed.lock",
)


def cash_inputs(path, evidence, dates):
    if path is None and evidence is None:
        return None, dict(status="BLOCKED_NO_VERIFIED_ACCOUNT_CASH_INPUT",
                          assumption="Zero account cash yield; SGOV is a separately invested ETF")
    if path is None or evidence is None:
        raise ValueError("Cash returns and evidence must both be supplied")
    record = strict_json(evidence)
    stamp = datetime.fromisoformat(record["reviewed_at"])
    if (record.get("currency") != "USD" or not str(record.get("reviewer", "")).strip()
            or record.get("returns_sha256") != file_hash(path) or stamp.tzinfo is None
            or stamp > datetime.now(timezone.utc)
            or not str(record.get("source", "")).strip()):
        raise ValueError("Bound dated reviewer/source evidence required for account cash")
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    if (list(frame) != ["cash_return"] or not frame.index.is_unique
            or not frame.index.is_monotonic_increasing):
        raise ValueError("Ordered cash_return series required")
    series = frame.cash_return.reindex(dates)
    if not np.isfinite(series).all() or (series <= -1).any():
        raise ValueError("Complete finite account cash returns required")
    return series, dict(status="SUPPLIED_REVIEWER_ATTESTED_INPUT_NOT_INDEPENDENTLY_VERIFIED",
                        returns_sha256=file_hash(path), evidence_sha256=file_hash(evidence),
                        currency="USD")


def write_report(result, root):
    f = result["forecast"]
    t = f.get("historical_test", {})
    lines = ["# Executed performance improvement study", "",
             f"Market session: {result['market_session']}. {VERSION}.", "",
             "All historical results are retrospective. Selection uses preceding validation windows; "
             "test results do not select variants. No active model, order gate or existing cohort changed.",
             "", "## Forecasting", ""]
    if t.get("outcomes"):
        lines += [f"{t['outcomes']} horizon-spaced quarterly outcomes. Validation choice: "
                  f"{f['selected_on_validation']}. Historical gate: {f['candidate_gate_passed']}.", "",
                  "| Predictor | Brier | Log loss |", "|---|---:|---:|"]
        for name, values in [("Selected challenger", t["candidate"]), *t["benchmarks"].items()]:
            lines.append(f"| {name} | {values['brier']:.4f} | {values['log_loss']:.4f} |")
    lines += ["", "## Portfolio walk-forward tests", "",
              "Three successive 252-session tests, each selected on the preceding 252 sessions. "
              "Continuous selected replay charges actual switching costs. Cash yields zero unless "
              "separately supplied reviewer-attested observations are provided.", "",
              "| Strategy | Cost | Selected return | Incumbent return | Selected drawdown | "
              "Turnover | Historical screen |", "|---|---:|---:|---:|---:|---:|---|"]
    for name, row in result["portfolios"].items():
        for cost, values in row["costs"].items():
            s, b = values["selected"], values["incumbent"]
            lines.append(f"| {name} | {float(cost)*10000:.0f} bps | {s['total_return']:.2%} | "
                         f"{b['total_return']:.2%} | {s['maximum_drawdown']:.2%} | "
                         f"{s['annual_turnover']:.2f} | {values['historical_screen_passed']} |")
    lines += ["", "## Coverage and constraints", "",
              "Executed: frequency/persistence/transition benchmarks; regularization and shrinkage; "
              "Brier/log-loss/reliability; availability-based cash attribution; observed SGOV reserve "
              "allocation at unchanged risk limits; wider trading bands and partial rebalancing; "
              "normal/stress covariance; asset and aggregate group risk checks; 15/30 bps replays; "
              "independent numerical reconciliation; frozen prospective research registrations.", "",
              f"Account cash inputs: {result['account_cash']['status']}.", "",
              "No hypothetical cash rate was substituted. Missing macro periods remain missing. "
              "There is no automatic promotion: historical screens do not establish prospective "
              "superiority, suitability or executable capacity. Data licensing, fees, taxes and "
              "actual account cash/exposures remain separately evidenced requirements.", "",
              "See assessment.json for every validation trial, cost result, source hash, risk weight, "
              "confidence diagnostic, and original-strategy quarantine attribution."]
    (root / "report.md").write_text("\n".join(lines) + "\n")


def run(bundle, output, *, cash_returns=None, cash_evidence=None):
    bundle, root = Path(bundle).resolve(), Path(output).resolve()
    b = strict_json(bundle)
    report = load_training_report(b["training_report"])
    if not report["current_numerical_source_match"]:
        raise ValueError("Current source-matched verified training required")
    prices = extended_prices(b["capture"], b["benchmark_extension"]).drop(columns=["XLV"])
    feature_rows = strict_json(Path(b["training_report"]).parent / "features.json")
    features = {r["date"]: r for r in feature_rows}
    if len(prices) < 1262:
        raise ValueError("Observed warmup plus 1008 evaluation sessions required")
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    sources = {p: file_hash(p) for p in SOURCES}
    protocol = dict(version=VERSION, declared_at=datetime.now(timezone.utc).isoformat(),
                    bundle_sha256=file_hash(bundle), source_hashes=sources,
                    variants=VARIANTS, group_positive_risk_caps=GROUP_RISK_CAPS,
                    capital_caps="Existing frozen engine asset/bucket/volatility/exposure limits retained",
                    validation_sessions=252, test_folds=3, test_sessions_per_fold=252,
                    costs=[0.0015, 0.003],
                    selection="Validation CAGR - 0.5 variance + 0.2 maximum drawdown; ties favor incumbent",
                    screen="Positive paired lower bound, no worse drawdown or expected shortfall at both costs",
                    cash_rate="Zero unless complete observed reviewer-attested account inputs supplied",
                    limitation="Previously inspected historical data; prospective confirmation required",
                    execution_enabled=False, promotion_enabled=False)
    atomic_json(root / "protocol.json", protocol)
    print("Protocol frozen before evaluation:", root / "protocol.json", flush=True)
    settings = strict_json("research/four_macro_strategies.json")["macro_forecast"]
    forecasts = forecast_study(feature_rows, settings)
    atomic_json(root / "forecast.json", forecasts)
    print("Forecast study completed; historical gate:", forecasts["candidate_gate_passed"], flush=True)
    engine = Experiments(prices, features)
    start, end = len(prices) - 1008, len(prices) - 1
    test_start = start + 252
    cash, cash_status = cash_inputs(cash_returns, cash_evidence, prices.index[start:])
    results, registrations = {}, {}
    for name in NAMES:
        trials, frames = {}, {}
        for variant in VARIANTS:
            frame, trades = engine.run(name, variant, start, end)
            frame.to_csv(root / f"{name}-{variant}-15bps.csv")
            atomic_json(root / f"{name}-{variant}-trades.json", trades)
            reconciliation(prices, frame, trades, 0.0015)
            frames[variant] = frame
            trials[variant] = dict(
                full_history=summarize(frame), cash_attribution=cash_attribution(frame),
                target_failures=int((frame.target_status == "BLOCKED_RISK_CASH_ONLY").sum()))
            print(name, variant, "reconciled", flush=True)
        folds, selection = [], {}
        for fold in range(3):
            lo, hi = test_start + fold * 252, test_start + (fold + 1) * 252
            val_dates = prices.index[lo - 252:lo]
            scores = {v: summarize(f.loc[val_dates]) for v, f in frames.items()}
            selected = max(VARIANTS, key=lambda v: objective(scores[v]))
            selection.update(dict.fromkeys(range(lo, hi), selected))
            folds.append(dict(validation_start=str(val_dates[0].date()),
                              validation_end=str(val_dates[-1].date()),
                              test_start=str(prices.index[lo].date()),
                              test_end=str(prices.index[hi - 1].date()),
                              selected=selected, validation_trials=scores))
        costs = {}
        for cost in protocol["costs"]:
            chosen, trades = engine.run(name, None, test_start, end, cost=cost, selection=selection)
            baseline, base_trades = engine.run(name, "incumbent", test_start, end, cost=cost)
            chosen.to_csv(root / f"selected-{name}-{cost}.csv")
            baseline.to_csv(root / f"baseline-{name}-{cost}.csv")
            atomic_json(root / f"selected-{name}-{cost}-trades.json", trades)
            atomic_json(root / f"baseline-{name}-{cost}-trades.json", base_trades)
            checks = dict(selected=reconciliation(prices, chosen, trades, cost),
                          incumbent=reconciliation(prices, baseline, base_trades, cost))
            sm, bm = summarize(chosen), summarize(baseline)
            interval = paired(chosen, baseline)
            passed = bool(interval["p025"] > 0 and sm["maximum_drawdown"] >= bm["maximum_drawdown"]
                          and sm["daily_expected_shortfall95"] <= bm["daily_expected_shortfall95"])
            entry = dict(selected=sm, incumbent=bm, paired_interval=interval,
                         reconciliation=checks, historical_screen_passed=passed,
                         selected_cash_attribution=cash_attribution(chosen))
            if cash is not None:
                targets = {pd.Timestamp(t["date"]): t["weights"] for t in trades}
                actual_cash = replay(engine.daily.loc[chosen.index], targets, cash,
                                     cost_rate=cost)
                actual_cash.to_csv(root / f"cash-sensitivity-{name}-{cost}.csv")
                entry["account_cash_sensitivity"] = dict(
                    total_return=float(actual_cash.equity.iloc[-1] - 1),
                    interpretation="Fixed decisions; observed account cash returns, not a reoptimized strategy")
            costs[str(cost)] = entry
        latest_variant = folds[-1]["selected"]
        latest = {}
        for variant in VARIANTS:
            candidate = engine.target(end, name, variant)
            ctx = engine.runner.ctx(end)
            w = np.array([candidate["weights"][s] for s in ctx["symbols"]])
            latest[variant] = dict(**candidate,
                                   diagnostics={k: risk_diagnostics(w, cov, ctx["symbols"])
                                                for k, cov in engine.covariances_at(end).items()})
            registrations[f"{name}:{variant}"] = candidate
        results[name] = dict(trials=trials, folds=folds, costs=costs,
                             latest_validation_selected=latest_variant, latest_candidates=latest,
                             historical_screen_passed=all(c["historical_screen_passed"] for c in costs.values()),
                             promotion_enabled=False)
        atomic_json(root / f"{name}-assessment.json", results[name])
    # Original strict-map outputs remain untouched; attribute actual saved cash by decision availability.
    original = {}
    for strategy in report["strategies"]:
        frame = pd.read_csv(Path(b["training_report"]).parent / (strategy["name"] + ".csv"),
                            index_col=0, parse_dates=True)
        session_ids = {d: i for i, d in enumerate(prices.index)}
        frame["macro_valid"] = [features.get(str(prices.index[session_ids[d] - 1].date()), {})
                                 .get("macro_valid", False) for d in frame.index]
        original[strategy["name"]] = cash_attribution(frame)
    now = datetime.now(timezone.utc)
    registration = dict(version=VERSION, registered_at=now.isoformat(),
                         decision_session=report["market_session"],
                         status="FROZEN_RESEARCH_CANDIDATES_NOT_FORWARD_RETURNS",
                         earliest_fill_session=next_fill(report["market_session"], now),
                         candidates=registrations, source_hashes=sources,
                         actual_registration_not_backdated=True,
                         execution_enabled=False, promotion_enabled=False)
    if report["market_session"] != str(usable_session(now).date()):
        registration["status"] = "HISTORICAL_CANDIDATES_NOT_CURRENT_REGISTRATION"
        registration["earliest_fill_session"] = None
    registration["identity"] = fingerprint(registration)
    atomic_json(root / "prospective-registration.json", registration, exclusive=True)
    if any(file_hash(p) != h for p, h in sources.items()):
        raise ValueError("Research source changed during run")
    result = dict(version=VERSION, status="COMPLETED_RESEARCH_ONLY",
                  generated_at=now.isoformat(), market_session=report["market_session"],
                  protocol=protocol, forecast=forecasts, portfolios=results,
                  original_strategy_cash_attribution=original, account_cash=cash_status,
                  candidate_registration_sha256=file_hash(root / "prospective-registration.json"),
                  source_hashes=sources, bundle_sha256=file_hash(bundle),
                  execution_enabled=False, promotion_enabled=False)
    write_report(result, root)
    result["artifacts"] = {p.name: file_hash(p) for p in root.iterdir() if p.is_file()}
    atomic_json(root / "assessment.json", result)
    atomic_json(root.parent / "latest.json", dict(assessment=str(root / "assessment.json"),
                assessment_sha256=file_hash(root / "assessment.json"),
                status=result["status"], execution_enabled=False, promotion_enabled=False))
    print("Completed:", root / "report.md", flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cash-returns", type=Path)
    parser.add_argument("--cash-evidence", type=Path)
    args = parser.parse_args()
    bundle = args.bundle or Path(strict_json("var/dashboard-live/latest.json")["bundle"])
    output = args.output or Path("var/performance-improvements") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run(bundle, output, cash_returns=args.cash_returns, cash_evidence=args.cash_evidence)
