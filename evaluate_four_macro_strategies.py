"""Point-in-time, fixed four-strategy comparison. Research only, no orders."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from compare_portfolio_models import metrics, rebalance_fee
from evaluate_three_year_goal import cohorts, goal_success, prepare_inputs, summarize
from fourregimestrategies import (
    PLAN,
    FourMacroStrategies,
    macro_forecasts,
    strategy_proposal,
)
from fourstrategysimulation import simulate_strategy
from optimize_hybrid_portfolio import rebased
from optimize_smart_portfolio import regime_report
from report_three_year_goal import forecast_diagnostics
from stress_test_models import monte_carlo

OUT = Path("var/research/four-macro-strategies-v6")


def align_benchmark_labels(frame, labels):
    aligned = frame.drop(columns=["regime", "macro_quadrant"], errors="ignore").join(
        labels, validate="one_to_one"
    )
    if aligned[["regime", "macro_quadrant"]].isna().any().any():
        raise ValueError("Benchmark dates lack prior-close regime labels")
    return aligned


def run_research():
    policy = FourMacroStrategies()
    paths = [
        PLAN,
        Path(__file__),
        Path("fourregimestrategies.py"),
        Path("fourstrategysimulation.py"),
        Path("institutionalportfolio.py"),
        Path("goalportfolio.py"),
    ]
    source_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    print(
        "Four fixed designs. Point-in-time macro forecasts; previous goal and safety gates retained.",
        flush=True,
    )
    prices, daily, states = prepare_inputs(policy)
    features = json.loads(
        Path("var/research/smart-portfolio-v3/features.json").read_text()
    )
    predictions, scores = macro_forecasts(features, policy.config["macro_forecast"])
    for date, state in states.items():
        state["signal"] = {**state["signal"], "macro_forecast": predictions[date]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "macro-forecasts.json").write_text(
        json.dumps({str(d.date()): p for d, p in predictions.items()}, indent=2)
    )
    pd.DataFrame(scores).to_csv(OUT / "macro-forecast-validation.csv", index=False)
    frames = {}
    audits = {}
    rows = []
    fresh = []
    target_rows = []
    diagnostics = {}
    cycles = []
    accounts = cohorts(prices, states)
    latest = next(reversed(states.values()))
    for name, spec in policy.config["strategies"].items():
        params = {
            "strategy": name,
            "volatility_ceiling": max(spec["volatility_ceilings"].values()),
        }
        print(
            f"{name}: governed account, diagnostic twin, doubled costs, {len(accounts)} fresh accounts",
            flush=True,
        )
        for suffix, protect, cost in [
            ("", True, 0.0015),
            ("_no_guard", False, 0.0015),
            ("_double_cost", True, 0.003),
        ]:
            key = name + suffix
            frame, trades, info = simulate_strategy(
                prices, daily, states, policy, params, protect=protect, cost_rate=cost
            )
            frames[key] = frame
            audits[key] = {"parameters": params, **info, "trades": trades}
            frame.to_csv(OUT / f"{key}.csv")
            rows.append(
                {
                    "model": key,
                    "role": "MANDATE_CANDIDATE"
                    if not suffix
                    else "DIAGNOSTIC"
                    if not protect
                    else "COST_SENSITIVITY",
                    **summarize(frame),
                    "rejected_proposals": len(info["rejections"]),
                }
            )
            diagnostics[key] = forecast_diagnostics(frame)
            report = regime_report(frame).assign(model=key)
            cycles.append(report)
        for start, end in accounts:
            frame, _, info = simulate_strategy(
                prices, daily, states, policy, params, start=start, end=end
            )
            m = metrics(frame, pd.Series(0.0, index=frame.index))
            fresh.append(
                {
                    "model": name,
                    "start": str(start.date()),
                    "end": str(end.date()),
                    "total_return": m["total_return"],
                    "max_drawdown": m["max_drawdown"],
                    "rejected_proposals": len(info["rejections"]),
                    "joint_success": goal_success(m["total_return"], m["max_drawdown"])
                    and not info["rejections"],
                }
            )
        i = latest["i"]
        h = daily.iloc[i - 251 : i + 1][latest["symbols"]]
        proposal = strategy_proposal(
            policy,
            h,
            latest["covariance"],
            latest["signal"],
            params,
            latest["trends"],
            reserve_symbol=latest["reserve"],
            drawdown=0.0,
            factor=1.0,
        )
        (OUT / f"{name}-reference-proposal.json").write_text(
            json.dumps(proposal, indent=2)
        )
        for symbol, weight in proposal["weights"].items():
            if weight:
                target_rows.append(
                    {
                        "model": name,
                        "as_of": latest["signal"]["as_of"],
                        "symbol": symbol,
                        "capital_weight": weight,
                        "whole_account_risk_share": proposal[
                            "full_account_risk_shares"
                        ].get(symbol, 0.0),
                        "conditional_core_risk_target": proposal[
                            "core_risk_targets"
                        ].get(symbol, np.nan),
                    }
                )
        target_rows.append(
            {
                "model": name,
                "as_of": latest["signal"]["as_of"],
                "symbol": "USD_CASH",
                "capital_weight": proposal["cash"],
                "whole_account_risk_share": 0.0,
            }
        )
    references = {
        "v3": "var/research/smart-portfolio-v3/daily-results.csv",
        "v4": "var/research/institutional-refinement-v4/refined-v4.csv",
        "all_weather_proxy": "var/research/institutional-refinement-v4/all-weather-inspired-proxy.csv",
        "strategic_50": "var/research/three-year-goal-v5/strategic_equity_50.csv",
        "strategic_70": "var/research/three-year-goal-v5/strategic_equity_70.csv",
    }
    for name, path in references.items():
        frames[name] = pd.read_csv(path, index_col=0, parse_dates=True)
        frames[name].to_csv(OUT / f"{name}.csv")
        rows.append(
            {"model": name, "role": "BENCHMARK_ONLY", **summarize(frames[name])}
        )
    # Regime and business cycle attribution for benchmarks uses identical prior-close labels.
    first = next(iter(policy.config["strategies"]))
    labels = frames[first][["regime", "macro_quadrant"]]
    for name in references:
        cycles.append(
            regime_report(align_benchmark_labels(frames[name], labels)).assign(
                model=name
            )
        )
    comparison = pd.DataFrame(rows)
    comparison.to_csv(OUT / "comparison.csv", index=False)
    pd.concat(cycles, ignore_index=True).to_csv(
        OUT / "macro-business-cycle-attribution.csv", index=False
    )
    pd.DataFrame(fresh).to_csv(OUT / "fresh-three-year-accounts.csv", index=False)
    pd.DataFrame(target_rows).to_csv(
        OUT / "last-historical-reference-targets.csv", index=False
    )
    (OUT / "decision-audit.json").write_text(json.dumps(audits, indent=2))
    (OUT / "risk-forecast-diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2)
    )
    # Actual ALLW, matched observed overlap. No official private-fund history invented.
    observed = pd.read_csv(
        "var/research/institutional-refinement-v4/allw-observed-prices.csv",
        index_col=0,
        parse_dates=True,
    ).ALLW
    r = observed.pct_change(fill_method=None).dropna()
    fee = rebalance_fee(np.array([0.0]), np.array([1.0]), 0.0015)
    actual = pd.DataFrame(
        {"return": r, "cash": 0.0, "turnover": 0.0, "cost_as_initial_capital": 0.0}
    )
    actual.iloc[0, actual.columns.get_loc("return")] = (1 + r.iloc[0]) * (1 - fee) - 1
    actual.iloc[0, actual.columns.get_loc("turnover")] = 1 - fee
    actual.iloc[0, actual.columns.get_loc("cost_as_initial_capital")] = (
        1 + r.iloc[0]
    ) * fee
    actual["equity"] = (1 + actual["return"]).cumprod()
    overlap = []
    for name, frame in {"actual_ALLW": actual, **frames}.items():
        selected = rebased(frame.loc[r.index])
        overlap.append(
            {
                "model": name,
                "start": str(r.index[0].date()),
                "end": str(r.index[-1].date()),
                **metrics(selected, pd.Series(0.0, index=selected.index)),
            }
        )
    pd.DataFrame(overlap).to_csv(OUT / "actual-allw-overlap.csv", index=False)
    streams = pd.DataFrame(
        {
            name: frames[name]["return"]
            for name in [n + "_no_guard" for n in policy.config["strategies"]]
            + ["all_weather_proxy"]
        }
    )
    simulation, paths_mc = monte_carlo(streams, paths=5000, years=3, seed=61031)
    joint = (
        paths_mc.assign(
            joint=(paths_mc.terminal_factor >= 1.5) & (paths_mc.max_drawdown >= -0.05)
        )
        .groupby("model")
        .joint.mean()
    )
    simulation["conditional_joint_goal_frequency"] = simulation.model.map(joint)
    simulation["median_total_return"] = simulation.median_final_1m / 1e6 - 1
    simulation["p05_total_return"] = simulation.p05_final_1m / 1e6 - 1
    simulation["p95_total_return"] = simulation.p95_final_1m / 1e6 - 1
    simulation.to_csv(OUT / "three-year-return-drawdown-scenarios.csv", index=False)
    # A paired comparison uses shared bootstrap dates, preserving strategy dependence.
    pivot = paths_mc.pivot(index="path", columns="model", values="terminal_factor")
    uncertainty = []
    for name in streams:
        difference = pivot[name] - pivot["all_weather_proxy"]
        uncertainty.append(
            {
                "model": name,
                "three_year_return_difference_vs_proxy_ci95_low": float(
                    difference.quantile(0.025)
                ),
                "three_year_return_difference_vs_proxy_ci95_high": float(
                    difference.quantile(0.975)
                ),
                "interpretation": "Conditional development scenario difference, not selection-adjusted alpha inference",
            }
        )
    pd.DataFrame(uncertainty).to_csv(
        OUT / "paired-benchmark-scenarios.csv", index=False
    )
    # Track empirical diversification; ETF count alone is not factor diversification.
    diversification = []
    for name in policy.config["strategies"]:
        p = json.loads((OUT / f"{name}-reference-proposal.json").read_text())
        positive = np.array(
            [v for v in p["full_account_risk_shares"].values() if v > 0]
        )
        positive /= positive.sum()
        diversification.append(
            {
                "model": name,
                "invested_instruments": sum(w > 0 for w in p["weights"].values()),
                "cash_weight": p["cash"],
                "effective_positive_risk_positions": float(
                    1 / np.square(positive).sum()
                ),
                "maximum_asset_risk_share": max(p["full_account_risk_shares"].values()),
                "forecast_annual_volatility": p["calibrated_estimated_volatility"],
            }
        )
    pd.DataFrame(diversification).to_csv(
        OUT / "diversification-diagnostics.csv", index=False
    )
    fresh_table = pd.DataFrame(fresh)
    screen = []
    for name in policy.config["strategies"]:
        sample = fresh_table.loc[fresh_table.model == name]
        row = comparison.loc[comparison.model == name].iloc[0]
        screen.append(
            {
                "model": name,
                "fresh_accounts": len(sample),
                "joint_successes": int(sample.joint_success.sum()),
                "research_screen_pass": bool(
                    sample.joint_success.all()
                    and row.full_account_drawdown_pass
                    and row.rejected_proposals == 0
                ),
            }
        )
    for path, digest in source_hashes.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Executed source changed during study: {path}")
    status = {
        "status": "RESEARCH_ONLY_NOT_ACCEPTED",
        "production_activation": False,
        "orders_submitted": 0,
        "strategies": screen,
        "source_hashes": source_hashes,
        "prior_smart_variants": 36,
        "new_fixed_strategies": 4,
        "start": str(next(iter(states)).date()),
        "end": str(prices.index[-1].date()),
        "reserved_start": "2025-10-30",
        "largest_core_budget_error": max(
            (
                t.get("risk_budget_error", 0.0)
                for a in audits.values()
                for t in a["trades"]
            ),
            default=0.0,
        ),
        "limitations": [
            "Development reuse and retrospective universe; no pristine out-of-sample performance claim.",
            "Future macro-condition forecasts are not calibrated recession or loss probabilities.",
            "Conditional bootstrap is not an asset-path rerun or calibrated prediction of future strategy returns.",
            "Full account guard retained; diagnostic twins do not satisfy owner risk authorization.",
            "All Weather proxy differs from official ALLW derivatives and from private Bridgewater funds.",
            "Adjusted-close next-close fills; 15bps costs; zero uninvested cash yield; USD before investor taxes.",
            "No finite data set establishes a guaranteed 5% drawdown bound.",
        ],
    }
    (OUT / "research-screen.json").write_text(json.dumps(status, indent=2))
    print(
        comparison[["model", "role", "cagr", "volatility", "max_drawdown"]].to_string(
            index=False
        )
    )
    print(pd.DataFrame(screen).to_string(index=False))
    return policy, frames, status


if __name__ == "__main__":
    run_research()
