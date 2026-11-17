"""Bounded feasibility study for 50% growth / 5% drawdown. Research only."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from assetuniverse import DIVERSIFIED_ASSETS
from compare_portfolio_models import metrics, rebalance_fee
from diversifiedregimepolicy import AllocationError
from goalportfolio import (
    AccountDrawdownGuard,
    FilteredHistoricalRisk,
    goal_proposal,
    research_parameters,
)
from institutionalportfolio import InstitutionalPortfolio, coverage_report
from optimize_smart_portfolio import regime_report
from refine_institutional_portfolio import prepare
from stress_test_models import monte_carlo

# Versioned historical policy, independent of one operator's ignored var tree.
PLAN = Path(__file__).resolve().parent / "research/three_year_goal_plan_frozen_20261031.json"
OUT = Path("var/research/three-year-goal-v5")


def goal_success(total_return, drawdown):
    """Roundoff tolerance only; not a relaxation of the investment mandate."""
    if not np.isfinite(total_return) or not np.isfinite(drawdown):
        return False
    return bool(total_return >= 0.5 - 1e-12 and drawdown >= -0.05 - 1e-12)


def prepare_inputs(policy):
    for name, digest in policy.config["frozen_inputs"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Frozen input changed: {name}")
    prices, daily, states = prepare(policy)
    # Features known at the decision close; no future or pre-inception fills.
    for date, state in states.items():
        i = state["i"]
        state["trends"] = {
            s: float(
                np.mean(
                    [prices[s].iloc[i] > prices[s].iloc[i - h] for h in (63, 126, 252)]
                )
            )
            for s in state["symbols"]
        }
    return prices, daily, states


def simulate(
    prices,
    daily,
    states,
    policy,
    parameters,
    *,
    cost_rate=0.0015,
    protect=True,
    start=None,
    end=None,
):
    symbols = list(DIVERSIFIED_ASSETS)
    start = next(iter(states)) if start is None else pd.Timestamp(start)
    end = prices.index[-1] if end is None else pd.Timestamp(end)
    if start not in states or end <= start or end not in prices.index:
        raise ValueError("Invalid simulated account period")
    dates = prices.loc[start:end].index
    weights = np.zeros(len(symbols))
    cash = nav = 1.0
    guard = AccountDrawdownGuard(
        policy.config["protective_drawdown_start"],
        policy.config["protective_cash_lock"],
    )
    filtered = FilteredHistoricalRisk()
    pending = None
    previous_forecast = None
    rows = []
    trades = []
    rejections = []
    lock_date = None
    for number, date in enumerate(dates):
        if number:
            values = daily.loc[date].reindex(symbols).to_numpy()
            held = weights > 0
            if not np.isfinite(values[held]).all():
                raise ValueError("Unpriceable held instrument")
            dollars = np.zeros(len(weights))
            dollars[held] = weights[held] * (1 + values[held])
            growth = float(cash + dollars.sum())
            gross = growth - 1
            weights = dollars / growth
            cash /= growth
            filtered.observe(gross, previous_forecast["sigma"])
            fee = turnover = 0.0
            if pending is not None:
                target = np.array([pending["weights"].get(s, 0.0) for s in symbols])
                fee = rebalance_fee(weights, target, cost_rate)
                turnover = float(np.abs(target * (1 - fee) - weights).sum())
                weights = target
                cash = float(1 - weights.sum())
                trades.append({"date": str(date.date()), **pending})
            cost = nav * growth * fee
            net = growth * (1 - fee) - 1
            nav *= 1 + net
            drawdown, factor = guard.update(nav)
            if guard.locked and lock_date is None:
                lock_date = str(date.date())
            signal = states[dates[number - 1]]["signal"]
            rows.append(
                {
                    "date": date,
                    "return": net,
                    "gross_return": gross,
                    "equity": nav,
                    "cash": cash,
                    "turnover": turnover,
                    "cost_as_initial_capital": cost,
                    "account_drawdown": drawdown,
                    "cash_locked": guard.locked if protect else False,
                    "raw_daily_sigma": previous_forecast["sigma"],
                    "filtered_var95": previous_forecast["var95"],
                    "filtered_es95": previous_forecast["es95"],
                    "filtered_ready": previous_forecast["ready"],
                    "regime": signal["regime"],
                    "macro_quadrant": max(
                        signal["probabilities"], key=signal["probabilities"].get
                    ),
                }
            )
        else:
            drawdown, factor = guard.update(nav)
        if not protect:
            factor = 1.0
        pending = None
        if date == end:
            break
        state = states[date]
        active = state["symbols"]
        ids = [symbols.index(s) for s in active]
        if any(weights[j] > 0 for j, s in enumerate(symbols) if s not in active):
            raise ValueError("Held instrument is ineligible for risk estimation")
        w = weights[ids]
        variance = float(w @ state["covariance"] @ w)
        sigma = np.sqrt(variance / 252)
        previous_forecast = {"sigma": sigma, **filtered.forecast(sigma)}
        rc = (
            w * (state["covariance"] @ w) / variance
            if variance > 1e-15
            else np.zeros(len(active))
        )
        exposure = (0.4 if state["signal"]["stress"] else 0.95) * factor
        ceiling = (
            min(parameters["volatility_ceiling"], 0.05)
            if state["signal"]["stress"]
            else parameters["volatility_ceiling"]
        )
        if protect and drawdown <= -0.05:
            ceiling = min(ceiling, 0.04)
        breach = (
            weights.sum() > exposure + 1e-8
            or weights.max() > 0.25 + 1e-8
            or np.sqrt(variance) > ceiling * factor + 1e-8
            or rc.max() > 0.25 + 1e-6
        )
        if number % 21 == 0 or breach:
            try:
                i = state["i"]
                proposal = goal_proposal(
                    policy,
                    daily.iloc[i - 251 : i + 1][active],
                    state["covariance"],
                    state["signal"],
                    parameters,
                    state["trends"],
                    reserve_symbol=state["reserve"],
                    drawdown=drawdown if protect else 0.0,
                    factor=factor,
                )
            except AllocationError as exc:
                rejections.append({"date": str(date.date()), "reason": str(exc)})
                proposal = {
                    "weights": {s: 0.0 for s in symbols},
                    "cash": 1.0,
                    "rejected": True,
                    "decision_time": state["signal"]["as_of"],
                }
            target = np.array([proposal["weights"].get(s, 0.0) for s in symbols])
            proposal["decision_time"] = state["signal"]["as_of"]
            if breach or np.abs(target - weights).sum() >= 0.04:
                pending = proposal
    frame = pd.DataFrame(rows).set_index("date")
    return (
        frame,
        trades,
        {"rejections": rejections, "lock_date": lock_date if protect else None},
    )


def rolling_goal(frame, horizon=756):
    values = frame["return"].to_numpy()
    rows = []
    for j in range(horizon, len(values) + 1):
        r = values[j - horizon : j]
        curve = np.cumprod(1 + r)
        peak = np.maximum.accumulate(np.r_[1.0, curve])[1:]
        total = float(curve[-1] - 1)
        dd = float((curve / peak - 1).min())
        rows.append(
            {
                "start": str(frame.index[j - horizon].date()),
                "end": str(frame.index[j - 1].date()),
                "return_3y": total,
                "max_drawdown": dd,
                "joint_success": goal_success(total, dd),
            }
        )
    return pd.DataFrame(rows)


def summarize(frame):
    result = metrics(frame, pd.Series(0.0, index=frame.index))
    result["sharpe_over_zero_cash"] = result.pop("sharpe_over_sgov")
    windows = rolling_goal(frame)
    result.update(
        rolling_windows=len(windows),
        median_rolling_3y_return=float(windows.return_3y.median()),
        worst_rolling_3y_return=float(windows.return_3y.min()),
        rolling_target_frequency=float((windows.return_3y >= 0.5 - 1e-12).mean()),
        rolling_joint_success_frequency=float(windows.joint_success.mean()),
        full_account_drawdown_pass=result["max_drawdown"] >= -0.05 - 1e-12,
    )
    return result


def benchmark(prices, daily, states, equity_weight, cost_rate=0.0015):
    from compare_portfolio_models import simulate as simple_simulate

    symbols = list(DIVERSIFIED_ASSETS)
    target = np.zeros(len(symbols))
    allocations = {
        "SPY": equity_weight / 3,
        "VEA": equity_weight / 3,
        "VWO": equity_weight / 3,
        "IEF": (0.85 - equity_weight) * 0.6,
        "TLT": (0.85 - equity_weight) * 0.4,
        "GLD": 0.10,
    }
    for s, w in allocations.items():
        target[symbols.index(s)] = w
    first = next(iter(states))
    dates = prices.loc[first:].index
    targets = {dates[i + 1]: target for i in range(0, len(dates) - 1, 21)}
    # Zero only unused returns; missing held prices still reject above.
    r = daily.loc[dates[1:]].copy()
    for s in symbols:
        if allocations.get(s, 0) == 0:
            r[s] = 0.0
        elif not np.isfinite(r[s]).all():
            raise ValueError("Missing benchmark return")
    return simple_simulate(
        r, targets, cost_rate=cost_rate, cash_returns=pd.Series(0.0, index=r.index)
    )


def cohorts(prices, states):
    first = next(iter(states))
    starts = [first]
    for year in range(first.year + 1, prices.index[-1].year):
        available = prices.index[prices.index >= pd.Timestamp(f"{year}-01-01")]
        if len(available):
            starts.append(available[0])
    result = []
    for start in starts:
        anniversary = start + pd.DateOffset(years=3)
        if anniversary > prices.index[-1]:
            continue
        end = prices.index[prices.index <= anniversary][-1]
        result.append((start, end))
    return result


def gap_scenarios(trades):
    scenarios = {
        "Risk-off gap": {
            "equity": -0.12,
            "bond": 0.03,
            "TIP": -0.02,
            "GLD": -0.03,
            "DBC": -0.15,
            "SHY": -0.002,
            "SGOV": -0.001,
        },
        "Inflation gap": {
            "equity": -0.08,
            "bond": -0.10,
            "TIP": -0.06,
            "GLD": 0.03,
            "DBC": 0.10,
            "SHY": -0.015,
            "SGOV": -0.001,
        },
        "Liquidity gap": {
            "equity": -0.15,
            "bond": -0.08,
            "TIP": -0.06,
            "GLD": -0.08,
            "DBC": -0.18,
            "SHY": -0.02,
            "SGOV": -0.002,
        },
    }
    rows = []
    equities = {"SPY", "VEA", "VWO"}
    bonds = {"TLT", "IEF", "IGOV"}
    for name, shock in scenarios.items():
        losses = []
        for trade in trades:
            weights = trade["weights"]
            r = sum(
                w * shock["equity" if s in equities else "bond" if s in bonds else s]
                for s, w in weights.items()
                if w and s in equities | bonds | {"TIP", "GLD", "DBC", "SHY", "SGOV"}
            )
            exposure = sum(weights.values())
            # Three repeated synthetic gaps model a two-extra-session control delay.
            for days in (1, 3):
                value = (
                    1
                    - exposure
                    + sum(
                        w
                        * (
                            1
                            + shock[
                                "equity"
                                if s in equities
                                else "bond"
                                if s in bonds
                                else s
                            ]
                        )
                        ** days
                        for s, w in weights.items()
                        if w
                        and s in equities | bonds | {"TIP", "GLD", "DBC", "SHY", "SGOV"}
                    )
                )
                losses.append((days, 1 - value, r))
        for days in (1, 3):
            loss = max([v[1] for v in losses if v[0] == days], default=0.0)
            rows.append(
                {
                    "scenario": name,
                    "delay_sessions": days,
                    "worst_synthetic_loss": loss,
                    "breaches_5pct": loss > 0.05,
                    "interpretation": "Hypothetical repeated shocks on historical targets, not estimated probabilities",
                }
            )
    return rows


def reanalyze_cached():
    """Reuse hash-verified, unchanged simulation code/inputs; recompute metrics."""
    cache = json.loads((OUT / "simulation-cache.json").read_text())
    for name, digest in cache["file_hashes"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Cached simulation input or output changed: {name}")
    for name, digest in cache["function_hashes"].items():
        if (
            hashlib.sha256(inspect.getsource(globals()[name]).encode()).hexdigest()
            != digest
        ):
            raise ValueError(
                f"Simulation function changed: {name}; full rerun required"
            )
    original = json.loads((OUT / "original-research-screen.json").read_text())
    plan = json.loads(PLAN.read_text())
    for name, digest in plan["frozen_inputs"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Frozen market input changed: {name}")
    table = pd.read_csv(OUT / "comparison.csv")
    for index, row in table.iterrows():
        name = row["model"]
        filename = (
            name.replace("_no_guard", "-no-drawdown-guard")
            if name.endswith("_no_guard")
            else name
        )
        frame = pd.read_csv(OUT / f"{filename}.csv", index_col=0, parse_dates=True)
        for key, value in summarize(frame).items():
            table.loc[index, key] = value
    table.to_csv(OUT / "comparison.csv", index=False)
    fresh = pd.read_csv(OUT / "simulation-cohorts.csv")
    fresh["joint_success"] = [
        goal_success(r.return_3y, r.max_drawdown) and r.rejected_proposals == 0
        for r in fresh.itertuples()
    ]
    fresh.to_csv(OUT / "fresh-three-year-accounts.csv", index=False)
    screen = []
    for row in table.loc[table.role == "GOVERNED_RESEARCH_CANDIDATE"].itertuples():
        sample = fresh.loc[fresh.model == row.model]
        passed = bool(
            row.full_account_drawdown_pass
            and row.rejected_proposals == 0
            and len(sample)
            and sample.joint_success.all()
        )
        screen.append(
            {
                "model": row.model,
                "research_screen_pass": passed,
                "fresh_account_joint_frequency": float(sample.joint_success.mean()),
                "fresh_account_return_max": float(sample.return_3y.max()),
                "fresh_account_drawdown_worst": float(sample.max_drawdown.min()),
            }
        )
    pd.DataFrame(screen).to_csv(OUT / "feasibility-screen.csv", index=False)
    updated = {
        **original,
        "status": "PASS_RESEARCH_SCREEN_ONLY"
        if any(r["research_screen_pass"] for r in screen)
        else "FAIL_TARGET_FEASIBILITY_SCREEN",
        "metric_reanalysis": "Unchanged hash-verified simulation outputs reused; numerical goal boundary tolerance 1e-12",
        "original_executed_source_hashes": original["hashes"],
        "hashes": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                PLAN,
                Path(__file__),
                Path("goalportfolio.py"),
                Path("institutionalportfolio.py"),
                Path("refine_institutional_portfolio.py"),
            ]
        },
    }
    (OUT / "research-screen.json").write_text(json.dumps(updated, indent=2))
    print(pd.DataFrame(screen).to_string(index=False))
    print(updated["status"], "No changed allocation or simulation assumptions.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reuse-simulations",
        action="store_true",
        help="Recompute goal metrics from verified unchanged account simulations",
    )
    args = parser.parse_args()
    if args.reuse_simulations:
        reanalyze_cached()
        return
    policy = InstitutionalPortfolio(PLAN)
    parameters = research_parameters(policy.config)
    OUT.mkdir(parents=True, exist_ok=True)
    print(
        f"Frozen search: {len(parameters)} research variants; 50% / 3 years, 5% drawdown. No orders.",
        flush=True,
    )
    prices, daily, states = prepare_inputs(policy)
    accounts = cohorts(prices, states)
    frames = {}
    records = []
    cohort_rows = []
    all_audits = {}
    risk_diagnostics = {}
    shocks = []
    ablations = {}
    for j, p in enumerate(parameters):
        name = f"candidate_{j:02d}"
        print(
            f"{name}: {p}; {len(accounts)} fresh three-calendar-year accounts",
            flush=True,
        )
        frame, trades, audit = simulate(prices, daily, states, policy, p)
        frames[name] = frame
        all_audits[name] = {"parameters": p, **audit, "trades": trades}
        frame.to_csv(OUT / f"{name}.csv")
        records.append(
            {
                "model": name,
                "role": "GOVERNED_RESEARCH_CANDIDATE",
                "parameters": json.dumps(p),
                **summarize(frame),
                "rejected_proposals": len(audit["rejections"]),
                "cash_lock_date": audit["lock_date"],
            }
        )
        unprotected, _, unprotected_audit = simulate(
            prices, daily, states, policy, p, protect=False
        )
        ablations[name] = unprotected
        unprotected.to_csv(OUT / f"{name}-no-drawdown-guard.csv")
        records.append(
            {
                "model": name + "_no_guard",
                "role": "DIAGNOSTIC_ABLATION",
                "parameters": json.dumps(p),
                **summarize(unprotected),
                "rejected_proposals": len(unprotected_audit["rejections"]),
            }
        )
        for start, end in accounts:
            cohort, _, info = simulate(
                prices, daily, states, policy, p, start=start, end=end
            )
            m = metrics(cohort, pd.Series(0.0, index=cohort.index))
            cohort_rows.append(
                {
                    "model": name,
                    "start": str(start.date()),
                    "end": str(end.date()),
                    "sessions": len(cohort),
                    "return_3y": m["total_return"],
                    "max_drawdown": m["max_drawdown"],
                    "lock_date": info["lock_date"],
                    "rejected_proposals": len(info["rejections"]),
                    "joint_success": goal_success(m["total_return"], m["max_drawdown"])
                    and not info["rejections"],
                }
            )
        valid = frame.loc[frame.filtered_ready & (frame.raw_daily_sigma > 1e-8)]
        risk_diagnostics[name] = {"ready_observations": len(valid)}
        if len(valid) >= 63:
            risk_diagnostics[name]["raw_normal"] = coverage_report(
                valid.gross_return, valid.raw_daily_sigma
            )
            risk_diagnostics[name]["filtered_historical"] = coverage_report(
                valid.gross_return, valid.filtered_var95 / norm.ppf(0.95)
            )
        shocks.extend({"model": name, **r} for r in gap_scenarios(trades))
        pd.concat([regime_report(frame).assign(model=name)]).to_csv(
            OUT / f"{name}-cycles.csv", index=False
        )
    for weight in (0.5, 0.7):
        name = f"strategic_equity_{int(weight * 100)}"
        frames[name] = benchmark(prices, daily, states, weight)
    for name, filename in [
        ("prior_v3", "var/research/smart-portfolio-v3/daily-results.csv"),
        ("prior_v4", "var/research/institutional-refinement-v4/refined-v4.csv"),
        (
            "all_weather_proxy",
            "var/research/institutional-refinement-v4/all-weather-inspired-proxy.csv",
        ),
    ]:
        frames[name] = pd.read_csv(filename, index_col=0, parse_dates=True)
    for name, frame in frames.items():
        if not name.startswith("candidate_"):
            records.append(
                {"model": name, "role": "BENCHMARK_ONLY", **summarize(frame)}
            )
            frame.to_csv(OUT / f"{name}.csv")
    results = pd.DataFrame(records)
    cohort_table = pd.DataFrame(cohort_rows)
    results.to_csv(OUT / "comparison.csv", index=False)
    cohort_table.to_csv(OUT / "fresh-three-year-accounts.csv", index=False)
    pd.DataFrame(shocks).to_csv(OUT / "gap-delay-stress.csv", index=False)
    (OUT / "risk-calibration.json").write_text(json.dumps(risk_diagnostics, indent=2))
    (OUT / "decision-audit.json").write_text(json.dumps(all_audits, indent=2))
    # No winner selection unless the observed return AND preservation screen clears.
    screen = []
    for name in ablations:
        row = results.loc[results.model == name].iloc[0]
        sample = cohort_table.loc[cohort_table.model == name]
        passed = bool(
            row.full_account_drawdown_pass
            and row.rejected_proposals == 0
            and sample.joint_success.all()
            and len(sample) > 0
        )
        screen.append(
            {
                "model": name,
                "research_screen_pass": passed,
                "fresh_account_joint_frequency": float(sample.joint_success.mean()),
                "fresh_account_return_max": float(sample.return_3y.max()),
                "fresh_account_drawdown_worst": float(sample.max_drawdown.min()),
            }
        )
    pd.DataFrame(screen).to_csv(OUT / "feasibility-screen.csv", index=False)
    # Joint bootstrap of unguarded fixed-strategy return streams: diagnostic only.
    # The account guard and asset-level allocation are not rerun on these paths.
    returns = pd.DataFrame({name: frame["return"] for name, frame in ablations.items()})
    mc, details = monte_carlo(returns, paths=3000, years=3, seed=51023)
    success = (
        details.assign(
            joint=(details.terminal_factor >= 1.5) & (details.max_drawdown >= -0.05)
        )
        .groupby("model")
        .joint.mean()
    )
    mc["conditional_joint_50pct_5pct_frequency"] = mc.model.map(success)
    mc.to_csv(OUT / "three-year-conditional-bootstrap.csv", index=False)
    # Fixed conservative reference, not a newly selected winner.
    doubled, _, double_audit = simulate(
        prices, daily, states, policy, parameters[0], cost_rate=0.003
    )
    doubled.to_csv(OUT / "candidate_00-double-cost.csv")
    status = {
        "status": "PASS_RESEARCH_SCREEN_ONLY"
        if any(r["research_screen_pass"] for r in screen)
        else "FAIL_TARGET_FEASIBILITY_SCREEN",
        "production_activation": False,
        "orders_submitted": 0,
        "candidate_count": len(parameters),
        "diagnostic_no_guard_twins": len(parameters),
        "prior_smart_variants": 24,
        "start": str(next(iter(states)).date()),
        "end": str(prices.index[-1].date()),
        "reserved_start": policy.config["reserved_start"],
        "target_return": 0.5,
        "maximum_drawdown": 0.05,
        "annual_return_required": 1.5 ** (1 / 3) - 1,
        "fresh_accounts_per_candidate": len(accounts),
        "double_cost_reference": summarize(doubled),
        "double_cost_rejections": len(double_audit["rejections"]),
        "risk_budget_error_max": max(
            (
                t.get("risk_budget_error", 0.0)
                for a in all_audits.values()
                for t in a["trades"]
            ),
            default=0.0,
        ),
        "hashes": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                PLAN,
                Path(__file__),
                Path("goalportfolio.py"),
                Path("institutionalportfolio.py"),
                Path("refine_institutional_portfolio.py"),
            ]
        },
        "limitations": [
            "No finite backtest proves a future 5% loss bound or 50% return.",
            "Retrospectively chosen universe; reused development history; overlapping windows dependent.",
            "USD nominal returns net of modeled trading costs, before investor taxes; cash earns zero.",
            "756-session rolling windows/bootstrap approximate three years; fresh cohorts use calendar anniversaries.",
            "Adjusted-close execution proxy; gaps and execution delays can breach the objective.",
            "Bootstrap resamples diagnostic no-guard portfolio returns, not underlying asset paths or the guarded strategy.",
            "No managed-futures returns fabricated; actual derivative implementation/data remain separately gated.",
            "Protective cash lock needs operator review; no automated high-water reset or discretionary recovery assumption.",
        ],
    }
    (OUT / "research-screen.json").write_text(json.dumps(status, indent=2))
    print(
        results[
            [
                "model",
                "role",
                "cagr",
                "max_drawdown",
                "rolling_target_frequency",
                "rolling_joint_success_frequency",
            ]
        ].to_string(index=False),
        flush=True,
    )
    print(pd.DataFrame(screen).to_string(index=False), flush=True)
    print(
        "DECISION:",
        status["status"],
        "No strategy accepted; no production changes.",
        flush=True,
    )


if __name__ == "__main__":
    main()
