"""Frozen eight-variant, chronological research refinement. Never submits orders."""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from assetuniverse import DIVERSIFIED_ASSETS, PRODUCTION_ASSETS
from compare_portfolio_models import metrics, rebalance_fee
from diversifiedregimepolicy import AllocationError
from institutionalportfolio import (
    DEFAULT_PLAN,
    ForecastCalibration,
    InstitutionalPortfolio,
    calibrated_covariance,
    coverage_report,
)
from optimize_hybrid_portfolio import rebased
from optimize_smart_portfolio import regime_report
from stress_test_models import common_history, monte_carlo

ROOT = Path("var/research")
OLD = ROOT / "smart-portfolio-v3"
OUT = ROOT / "institutional-refinement-v4"


def prepare(policy):
    provenance = json.loads((OLD / "research-model.json").read_text())
    for name, digest in provenance["hashes"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Frozen V3 input/source changed: {name}")
    raw = pd.read_csv(
        ROOT / "horizon-analysis/observed-history.csv", index_col=0, parse_dates=True
    )
    base = common_history(
        raw, PRODUCTION_ASSETS, end_before=pd.Timestamp(policy.config["reserved_start"])
    )
    prices = raw.loc[base.index, list(DIVERSIFIED_ASSETS)]
    daily = prices.pct_change(fill_method=None)
    features = {
        pd.Timestamp(r["date"]): r
        for r in json.loads((OLD / "features.json").read_text())
    }
    risk_symbols = set(
        s for group in policy.config["sleeves"].values() for s in group
    ) | {"SHY", "SGOV"}
    spy_vol = daily.SPY.rolling(20).std() * np.sqrt(252)
    states = {}
    for i in range(252, len(prices) - 1):
        date = prices.index[i]
        history = daily.iloc[i - 251 : i + 1]
        symbols = [
            s
            for s in DIVERSIFIED_ASSETS
            if s in risk_symbols and np.isfinite(history[s]).all()
        ]
        past = daily.iloc[max(1, i - 1259) : i + 1][symbols]
        stressed = past.loc[spy_vol.reindex(past.index) > 0.25].dropna()
        cov, used = calibrated_covariance(
            history[symbols],
            stressed,
            half_life=policy.config["volatility_half_life"],
            stress_weight=policy.config["stress_correlation_weight"],
        )
        signal = features[date].copy()
        if (
            pd.Timestamp(signal["as_of"]).tz_convert("America/New_York").date()
            != date.date()
        ):
            raise ValueError("Feature date does not match decision date")
        signal["trend_weak"] = signal["trend"] < 0 and signal["breadth"] < 0.4
        states[date] = {
            "i": i,
            "symbols": symbols,
            "covariance": cov,
            "signal": signal,
            "stress_covariance": used,
            "reserve": "SGOV" if "SGOV" in symbols else "SHY",
        }
    return prices, daily, states


def run(
    prices,
    daily,
    states,
    policy,
    schedule,
    *,
    cost_rate=0.0015,
    use_trend=True,
    reserve_enabled=True,
):
    symbols = list(DIVERSIFIED_ASSETS)
    w = np.zeros(len(symbols))
    cash = nav = 1.0
    navs = [1.0]
    pending = None
    forecast = None
    rows = []
    trades = []
    calibrator = ForecastCalibration(
        policy.config["calibration_half_life"],
        policy.config["calibration_warmup"],
        policy.config["maximum_calibration_multiplier"],
    )
    for i in range(252, len(prices)):
        date = prices.index[i]
        if i > 252:
            observed = daily.iloc[i].reindex(symbols).to_numpy()
            held = w > 0
            if not np.isfinite(observed[held]).all():
                raise ValueError("Missing held-instrument valuation")
            dollars = np.zeros(len(w))
            dollars[held] = w[held] * (1 + observed[held])
            growth = float(cash + dollars.sum())
            gross = growth - 1
            w = dollars / growth
            cash /= growth
            raw_sigma, calibrated_sigma = forecast
            # The prior close forecast is scored before today's new close fill.
            calibrator.observe(gross, raw_sigma**2)
            fee = turnover = 0.0
            if pending is not None:
                target = np.array([pending["weights"][s] for s in symbols])
                fee = rebalance_fee(w, target, cost_rate)
                turnover = float(np.abs(target * (1 - fee) - w).sum())
                w = target
                cash = float(1 - w.sum())
                trades.append({"execution_date": str(date.date()), **pending})
            cost = nav * growth * fee
            net = growth * (1 - fee) - 1
            nav *= 1 + net
            navs.append(nav)
            prior_signal = states[prices.index[i - 1]]["signal"]
            rows.append(
                {
                    "date": date,
                    "return": net,
                    "gross_return": gross,
                    "equity": nav,
                    "cash": cash,
                    "turnover": turnover,
                    "cost_as_initial_capital": cost,
                    "raw_daily_sigma": raw_sigma,
                    "calibrated_daily_sigma": calibrated_sigma,
                    "regime": prior_signal["regime"],
                    "macro_quadrant": max(
                        prior_signal["probabilities"],
                        key=prior_signal["probabilities"].get,
                    ),
                }
            )
        pending = None
        if date not in states:
            continue
        state = states[date]
        active = state["symbols"]
        ids = [symbols.index(s) for s in active]
        if any(w[j] > 0 for j, s in enumerate(symbols) if s not in active):
            raise ValueError("Held instrument missing from risk estimate")
        current = w[ids]
        variance = float(current @ state["covariance"] @ current)
        multiplier = calibrator.multiplier
        forecast = (np.sqrt(variance / 252), np.sqrt(variance / 252) * multiplier)
        params = schedule(date)
        drawdown = nav / max(navs[-126:]) - 1
        ceiling = params["volatility_ceiling"]
        exposure = 0.4 if state["signal"]["stress"] else 0.95
        if state["signal"]["stress"]:
            ceiling = min(ceiling, 0.05)
        if policy.config.get("maximum_drawdown") is not None and drawdown <= -0.05:
            ceiling = min(ceiling, 0.04)
        if policy.config.get("maximum_drawdown") is not None and drawdown <= -0.08:
            ceiling = min(ceiling, 0.03)
            exposure = min(exposure, 0.25)
        rc = (
            current * (state["covariance"] @ current) / variance
            if variance > 1e-15
            else np.zeros(len(active))
        )
        breach = (
            w.sum() > exposure + 1e-8
            or w.max() > 0.25 + 1e-8
            or np.sqrt(variance) * multiplier > ceiling + 1e-8
            or rc.max() > 0.25 + 1e-6
        )
        if (i - 252) % policy.config["rebalance_sessions"] == 0 or breach:
            try:
                proposal = policy.allocate(
                    daily.iloc[i - 251 : i + 1][active],
                    state["covariance"],
                    state["signal"],
                    params,
                    reserve_symbol=state["reserve"] if reserve_enabled else None,
                    account_drawdown=drawdown,
                    calibration_multiplier=multiplier,
                    decision_time=state["signal"]["as_of"],
                    use_trend=use_trend,
                )
            except AllocationError as exc:
                raise AllocationError(f"{date.date()} {params}: {exc}") from exc
            target = np.array([proposal["weights"][s] for s in symbols])
            if (
                breach
                or np.abs(target - w).sum() >= policy.config["minimum_trade_notional"]
            ):
                pending = proposal
    return pd.DataFrame(rows).set_index("date"), trades


def select(bank, candidates, policy):
    dates = bank[0].index
    c = policy.config
    selections = []
    trials = []
    for boundary in range(
        c["training_sessions"], len(dates), c["selection_interval_sessions"]
    ):
        rows = []
        for j, frame in bank.items():
            window = rebased(frame.iloc[boundary - c["training_sessions"] : boundary])
            m = metrics(window, pd.Series(0.0, index=window.index))
            row = {
                "candidate": j,
                "parameters": candidates[j],
                "training_end": str(window.index[-1].date()),
                "evaluation_start": str(dates[boundary].date()),
                **m,
            }
            row["eligible"] = (
                c.get("training_drawdown_ceiling") is None
                or m["max_drawdown"] >= -c["training_drawdown_ceiling"]
            ) and m["volatility"] <= c["training_volatility_ceiling"]
            trials.append(row)
            if row["eligible"]:
                rows.append(row)
        selections.append(
            max(
                rows,
                key=lambda r: (
                    r["cagr"],
                    -r["annual_traded_notional"],
                    -r["candidate"],
                ),
            )
            if rows
            else {
                "candidate": None,
                "parameters": c["proxy_parameters"],
                "training_end": str(dates[boundary - 1].date()),
                "evaluation_start": str(dates[boundary].date()),
                "fallback": True,
            }
        )
    return selections, trials


def main():
    policy = InstitutionalPortfolio()
    print(
        "Verifying frozen inputs and preparing strictly historical risk states.",
        flush=True,
    )
    prices, daily, states = prepare(policy)
    grid = policy.config["candidate_grid"]
    candidates = [dict(zip(grid, v)) for v in itertools.product(*grid.values())]
    bank = {}
    for j, p in enumerate(candidates):
        print(f"Frozen trial {j + 1}/8 at doubled costs: {p}", flush=True)
        bank[j], _ = run(
            prices, daily, states, policy, lambda date, p=p: p, cost_rate=0.003
        )
    selections, trials = select(bank, candidates, policy)

    def schedule(date):
        available = [r for r in selections if pd.Timestamp(r["training_end"]) <= date]
        return (
            available[-1]["parameters"]
            if available
            else policy.config["proxy_parameters"]
        )

    result, trades = run(prices, daily, states, policy, schedule)
    doubled, _ = run(prices, daily, states, policy, schedule, cost_rate=0.003)
    proxy, _ = run(
        prices,
        daily,
        states,
        policy,
        lambda date: policy.config["proxy_parameters"],
        use_trend=False,
    )
    no_macro, _ = run(
        prices,
        daily,
        states,
        policy,
        lambda date: {**schedule(date), "macro_view_weight": 0.0},
    )
    no_reserve, _ = run(prices, daily, states, policy, schedule, reserve_enabled=False)
    old = pd.read_csv(OLD / "daily-results.csv", index_col=0, parse_dates=True)
    frames = {
        "Refined V4": result,
        "V4 doubled costs": doubled,
        "All Weather-inspired proxy": proxy,
        "V4 no macro tilt": no_macro,
        "V4 no reserve": no_reserve,
        "Prior macro V3": old,
    }
    for name, filename in [
        ("SPY reference", "spy-reference.csv"),
        ("60-40 reference", "60-40-reference.csv"),
    ]:
        frames[name] = pd.read_csv(OLD / filename, index_col=0, parse_dates=True)
    table = []
    for period, start in [
        ("Full development", result.index[0]),
        ("After initial training", pd.Timestamp(selections[0]["evaluation_start"])),
        ("Recent common window", pd.Timestamp("2022-06-01")),
    ]:
        for name, frame in frames.items():
            selected = rebased(
                frame.loc[(frame.index >= start) & (frame.index <= result.index[-1])]
            )
            m = metrics(selected, pd.Series(0.0, index=selected.index))
            m["sharpe_over_zero_cash"] = m.pop("sharpe_over_sgov")
            table.append(
                {
                    "period": period,
                    "model": name,
                    "start": str(selected.index[0].date()),
                    "end": str(selected.index[-1].date()),
                    **m,
                }
            )
    OUT.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        frame.to_csv(OUT / (name.lower().replace(" ", "-") + ".csv"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True, layout="constrained")
    for name in ["Refined V4", "Prior macro V3", "All Weather-inspired proxy"]:
        frame = frames[name]
        axes[0].plot(frame.index, frame.equity, label=name, linewidth=1.4)
        peak = np.maximum.accumulate(np.r_[1.0, frame.equity.to_numpy()])[1:]
        axes[1].plot(
            frame.index, 100 * (frame.equity / peak - 1), label=name, linewidth=1.0
        )
    axes[0].set_title(
        "Development comparison: net of modeled trading costs, not accepted for deployment"
    )
    axes[0].set_ylabel("Growth of initial $1")
    axes[1].set_ylabel("Account drawdown (%)")
    axes[0].legend(loc="upper left")
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.savefig(OUT / "performance-and-drawdown.png", dpi=160)
    plt.close(fig)
    pd.DataFrame(table).to_csv(OUT / "comparison.csv", index=False)
    regime_report(result).to_csv(OUT / "regime-cycle-results.csv", index=False)
    episodes = []
    for label, start, end in [
        ("GFC partial", "2008-07-28", "2009-06-30"),
        ("Euro debt", "2011-01-01", "2011-12-31"),
        ("China commodity slowdown", "2015-01-01", "2016-02-29"),
        ("2018 selloff", "2018-01-01", "2018-12-31"),
        ("COVID shock", "2020-02-19", "2020-03-23"),
        ("Inflation rate shock", "2022-01-01", "2022-12-31"),
    ]:
        for name, frame in frames.items():
            window = rebased(frame.loc[start:end])
            m = metrics(window, pd.Series(0.0, index=window.index))
            episodes.append(
                {
                    "episode": label,
                    "model": name,
                    "sessions": len(window),
                    "period_return": m["total_return"],
                    "within_episode_drawdown": m["max_drawdown"],
                }
            )
    pd.DataFrame(episodes).to_csv(OUT / "stress-episodes.csv", index=False)
    simulation_input = pd.DataFrame(
        {
            name: frames[name]["return"]
            for name in ["Refined V4", "Prior macro V3", "All Weather-inspired proxy"]
        }
    )
    simulation, _ = monte_carlo(simulation_input, paths=5000, years=1, seed=19073)
    simulation.to_csv(OUT / "conditional-one-year-bootstrap.csv", index=False)
    # Paired date blocks preserve cross-strategy dependence. Development uncertainty
    # only: these intervals do not adjust for repeated model search.
    from stress_test_models import block_indices

    values = np.log1p(simulation_input.to_numpy())
    rng = np.random.default_rng(19074)
    differences = []
    for _ in range(20):
        indices = block_indices(rng, len(values), len(values), 100, 21)
        annual = np.expm1(values[indices].mean(axis=1) * 252)
        differences.extend((annual[:, 0] - annual[:, 1]).tolist())
    uncertainty = {
        "v4_minus_v3_cagr_paired_block_ci95": list(
            map(float, np.quantile(differences, [0.025, 0.975]))
        ),
        "interpretation": "Conditional development bootstrap; not selection-adjusted inference or a future loss guarantee",
    }
    (OUT / "development-uncertainty.json").write_text(json.dumps(uncertainty, indent=2))
    for name, value in [
        ("selections", selections),
        ("trials", trials),
        ("trade-audit", trades),
    ]:
        (OUT / f"{name}.json").write_text(json.dumps(value, indent=2))
    diagnostics = {
        key: coverage_report(result.gross_return, result[column])
        for key, column in [
            ("raw", "raw_daily_sigma"),
            ("calibrated", "calibrated_daily_sigma"),
        ]
    }
    audit = {
        "status": "RESEARCH_CANDIDATE_NOT_ACCEPTED",
        "production_activation": False,
        "orders_submitted": 0,
        "candidate_count": 8,
        "prior_smart_variant_runs": 16,
        "strict_budget_tolerance": 1e-6,
        "max_budget_error": max(t["risk_budget_error"] for t in trades),
        "trade_events": len(trades),
        "coverage": diagnostics,
        "last_selection": selections[-1],
        "hashes": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                DEFAULT_PLAN,
                Path(__file__),
                Path("institutionalportfolio.py"),
                Path("test_institutional_portfolio.py"),
                Path("compare_portfolio_models.py"),
                Path("stress_test_models.py"),
                OLD / "features.json",
                ROOT / "horizon-analysis/observed-history.csv",
                ROOT / "smart-macro-vintages/manifest.json",
            ]
        },
        "limitations": [
            "Retrospective universe and development reuse; selection is chronological but not pristine out of sample.",
            "Reserved dates from 2025-10-30 excluded. Prior inspection prevents pristine holdout claims.",
            "All Weather-inspired unlevered proxy is not an official Bridgewater allocation or fund return.",
            "Adjusted-close fills, 15bps traded-notional costs, zero yield on truly uninvested cash.",
            "Risk limits are forecasts and next-close controls; gaps can exceed them before execution.",
            "Macro quadrant weights are allocation scores, not calibrated event/loss probabilities.",
            "New hierarchical risk contract requires independent acceptance and runtime integration.",
        ],
    }
    (OUT / "research-model.json").write_text(json.dumps(audit, indent=2))
    display = pd.DataFrame(table)[
        [
            "period",
            "model",
            "cagr",
            "volatility",
            "max_drawdown",
            "annual_traded_notional",
        ]
    ]
    print(display.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print(json.dumps(diagnostics, indent=2))
    print(simulation.to_string(index=False))
    print(json.dumps(uncertainty))
    print("RESEARCH ONLY. No production activation or broker orders. Outputs:", OUT)


if __name__ == "__main__":
    main()
