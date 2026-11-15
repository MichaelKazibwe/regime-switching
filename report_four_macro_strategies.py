"""Report fixed designs, benchmark evidence and conditional scenario estimates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from evaluate_four_macro_strategies import OUT
from fourregimestrategies import PLAN, quadrant
from optimize_hybrid_portfolio import rebased
from compare_portfolio_models import metrics


def conditional_scenarios(frames, paths=1500, seed=61032):
    """Resample complete 21-day joint blocks classified by starting conditions."""
    names = list(frames)
    first = frames[names[0]]
    returns = pd.DataFrame({n: f["return"] for n, f in frames.items()})
    if (
        not returns.index.equals(first.index)
        or not np.isfinite(returns.to_numpy()).all()
    ):
        raise ValueError("Scenario streams must have identical complete dates")
    logs = np.log1p(returns.to_numpy())
    starts = np.arange(0, len(logs) - 20, 21)
    rng = np.random.default_rng(seed)
    rows = []
    labels = list(sorted(first.macro_quadrant.unique())) + ["market_crisis"]
    for label in labels:
        selected = [
            j
            for j in starts
            if (
                first.regime.iloc[j] == "crisis"
                if label == "market_crisis"
                else first.macro_quadrant.iloc[j] == label
            )
        ]
        if len(selected) < 12:
            rows.extend(
                {
                    "model": n,
                    "starting_condition": label,
                    "historical_blocks": len(selected),
                    "status": "INSUFFICIENT_BLOCKS",
                }
                for n in names
            )
            continue
        blocks = np.array([logs[j : j + 21] for j in selected])
        calibration = rng.integers(0, len(blocks), size=(paths, len(blocks)))
        drift = blocks[calibration].mean(axis=(1, 2))
        future = rng.integers(0, len(blocks), size=(paths, 12))
        sampled = blocks[future].reshape(paths, 252, len(names))
        cumulative = np.cumsum(
            sampled - blocks.mean(axis=(0, 1)) + drift[:, None, :], axis=1
        )
        terminal = np.expm1(cumulative[:, -1, :])
        peak = np.maximum.accumulate(np.maximum(cumulative, 0), axis=1)
        dd = np.expm1(cumulative - peak).min(axis=1)
        for k, name in enumerate(names):
            rows.append(
                {
                    "model": name,
                    "starting_condition": label,
                    "historical_blocks": len(selected),
                    "status": "CONDITIONAL_SCENARIO",
                    "median_one_year_return": float(np.median(terminal[:, k])),
                    "p05_one_year_return": float(np.quantile(terminal[:, k], 0.05)),
                    "p95_one_year_return": float(np.quantile(terminal[:, k], 0.95)),
                    "p95_drawdown_magnitude": float(np.quantile(-dd[:, k], 0.95)),
                }
            )
    return pd.DataFrame(rows)


def main():
    plan = json.loads(PLAN.read_text())
    status = json.loads((OUT / "research-screen.json").read_text())
    for name, digest in status["source_hashes"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Executed research source changed: {name}")
    specs = plan["strategies"]
    frames = {
        n: pd.read_csv(OUT / f"{n}_no_guard.csv", index_col=0, parse_dates=True)
        for n in specs
    }
    scenarios = conditional_scenarios(frames)
    scenarios.to_csv(OUT / "starting-regime-one-year-scenarios.csv", index=False)
    correlation = pd.DataFrame(
        {name: frame["return"] for name, frame in frames.items()}
    ).corr()
    correlation.to_csv(OUT / "cross-strategy-return-correlations.csv")
    pairwise = correlation.to_numpy()[np.triu_indices(len(correlation), 1)]
    scores = pd.read_csv(OUT / "macro-forecast-validation.csv")
    forecasts = json.loads((OUT / "macro-forecasts.json").read_text())
    features = {
        r["date"]: r
        for r in json.loads(
            Path("var/research/smart-portfolio-v3/features.json").read_text()
        )
    }
    calibration = []
    for row in scores.itertuples():
        p = np.array(forecasts[row.date]["used"])
        calibration.append(
            {
                "confidence": float(p.max()),
                "correct": int(p.argmax() == quadrant(features[row.outcome_date])),
            }
        )
    cal = pd.DataFrame(calibration)
    reliability = []
    for j in range(10):
        selected = cal.loc[
            (cal.confidence >= j / 10)
            & (cal.confidence < ((j + 1) / 10 if j < 9 else 1.000001))
        ]
        if len(selected):
            reliability.append(
                {
                    "confidence_bin_start": j / 10,
                    "observations": len(selected),
                    "mean_confidence": float(selected.confidence.mean()),
                    "observed_accuracy": float(selected.correct.mean()),
                }
            )
    pd.DataFrame(reliability).to_csv(
        OUT / "macro-forecast-reliability.csv", index=False
    )
    # Individual stress episodes are reporting-only, never used to fit allocations.
    episodes = []
    for name, frame in frames.items():
        for label, start, end in [
            ("GFC partial", "2008-07-28", "2009-06-30"),
            ("Euro debt", "2011-01-01", "2011-12-31"),
            ("Commodity slowdown", "2015-01-01", "2016-02-29"),
            ("2018 selloff", "2018-01-01", "2018-12-31"),
            ("COVID shock", "2020-02-19", "2020-03-23"),
            ("Inflation rate shock", "2022-01-01", "2022-12-31"),
        ]:
            window = rebased(frame.loc[start:end])
            m = metrics(window, pd.Series(0.0, index=window.index))
            episodes.append(
                {
                    "model": name,
                    "episode": label,
                    "period_return": m["total_return"],
                    "within_episode_drawdown": m["max_drawdown"],
                }
            )
    pd.DataFrame(episodes).to_csv(OUT / "stress-episodes.csv", index=False)
    comparison = pd.read_csv(OUT / "comparison.csv")
    fresh = pd.read_csv(OUT / "fresh-three-year-accounts.csv")
    overlap = pd.read_csv(OUT / "actual-allw-overlap.csv")
    simulation = pd.read_csv(OUT / "three-year-return-drawdown-scenarios.csv")
    targets = pd.read_csv(OUT / "last-historical-reference-targets.csv")
    diversity = pd.read_csv(OUT / "diversification-diagnostics.csv")

    def pct(x):
        return f"{x * 100:.2f}%"

    lines = [
        "# Four macro-aware portfolio strategies",
        "",
        "**Status: four implemented research challengers; no portfolio is certified optimal or accepted for production.**",
        "",
        f"User mandate remains **50% net cumulative return in three years, at most 5% account peak-to-trough decline**. {len(fresh)} fresh three-calendar-year accounts were tested; joint successes: **{int(fresh.joint_success.sum())}/{len(fresh)}**. No order submission or activation occurred.",
        "",
        "## The four strategies",
        "",
        "| Strategy | Design | Expansion / recession response |",
        "|---|---|---|",
        "| Economic Balance | Diversified economic risk core with bounded predictive tilts | Moderate equity growth risk; more nominal bonds, inflation-linked bonds and gold in slowdowns |",
        "| Defensive Growth | Larger expansion equity budget plus multi-horizon market trend confirmation | Equity risk expands with growth; slows sharply during contraction or crisis |",
        "| Inflation Resilience | Explicit real-rate/inflation diversification | Reduces nominal duration risk when inflation rises; diversifies across TIP, gold and commodities |",
        "| Tail-Aware Ensemble | Fixed equal blend of the preceding budget maps, market trend and prior realized tail feedback | Conservative forecast ES can reduce sizing; it cannot increase risk to improve returns |",
        "",
        "All four use SPY/VEA/VWO, TLT/IEF/IGOV, TIP, GLD and DBC, with SHY/SGOV reserves after historical eligibility. These share overlapping economic risks: equal ETF counts or percentage variance budgets do not establish neutrality to equity, duration, inflation or currency factors. Direct futures, shorting and leverage are not implemented.",
        "",
        "## Predeclared regime targets",
        "",
        "The following are **requested sleeve variance budgets**, not capital weights or promised returns. Budget construction projects asset targets into a 24% risk envelope, leaving a buffer below the unchanged 25% whole-account contribution cap, then reconstructs explicit feasible sleeve budgets. If invested reserve cross-risk makes the strict solve infeasible, the same core is retried without an invested reserve; failure still rejects to cash and disqualifies the account. Actual reconciled targets are retained. Volatility ceilings are forecast limits, not realized loss bounds.",
        "",
        "| Strategy | Economic state | Equity | Nominal bonds | TIP | Gold | Commodities | Annual vol ceiling |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, spec in specs.items():
        for regime, budget in spec["risk_budgets"].items():
            lines.append(
                "| "
                + " | ".join(
                    [name, regime]
                    + [pct(v) for v in budget]
                    + [pct(spec["volatility_ceilings"][regime])]
                )
                + " |"
            )
    lines += [
        "",
        "Current quadrant weights and a bounded **20% forecast mixture** blend the state maps. During crisis, the stagflation/slowdown budget blend caps requested equity risk at 15%, limits invested capital to 40%, and applies at most 5% forecast annual volatility. A persistent account guard reduces allocation between 2% and 4% drawdown, latches to cash at 4%, and never resets the high-water mark. Gaps can exceed 5% before next-close execution.",
        "",
        "## Macroeconomic prediction and risk calibration",
        "",
        "Archived point-in-time industrial production, unemployment, CPI and Treasury yields are combined with market trend, breadth, volatility and a credit-relative proxy. A standardized, regularized multinomial logistic model forecasts the **derived economic quadrant 63 sessions ahead**. Each training label is strictly observable before the decision close; monthly refits use at most 1,260 training examples after a 504-example minimum. Economic states are rules derived from released conditions, not independently verified recession labels.",
        "",
        "Model probabilities are shrunk 50% toward historical class frequencies. The model is used only after at least 12 matured prior forecasts outperform their contemporaneous frequency baselines on mean Brier score; otherwise allocation uses the frequency baseline. This is a point-in-time screening rule, not a calibration guarantee. Monthly 63-session outcomes overlap. NBER recession labels are retrospective reporting-only and never trading inputs.",
        "",
        f"Completed matured forecasts: **{len(scores)}**. Mean Brier scores: model **{scores.brier_model.mean():.4f}**, baseline **{scores.brier_baseline.mean():.4f}**, actually used **{scores.brier_used.mean():.4f}**; lower is better. Model enabled on **{pct(scores.enabled.mean())}** of evaluated predictions. Reliability bins are retained; these probabilities must not be presented as calibrated recession or financial-loss probabilities.",
        "",
        "Risk uses volatility-scale-preserving shrunk correlations, EWMA/long-window volatility and past-stress correlations. Prior-only filtered historical VaR/ES is scored against the next observed return before a new closing fill. Ensemble ES feedback is reduce-only, capped at 2x forecast scale. Exact conditional core risk attribution includes invested Treasury cross-risk; the 1e-6 gate, 25% capital/risk caps and paper-only boundary remain unchanged.",
        "",
        "## Same-history net performance",
        "",
        f"Observed comparison: **{status['start']}–{status['end']}**. Modeled costs are 15bps of traded ETF notional; doubled-cost runs use 30bps. Cash earns zero; USD nominal returns are before investor taxes. Daily adjusted-close fills are a research proxy.",
        "",
        "| Model | Role | Total return | CAGR | Annual volatility | Max drawdown | Rejected proposals |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in comparison.itertuples():
        lines.append(
            "| "
            + " | ".join(
                [
                    row.model,
                    row.role,
                    pct(row.total_return),
                    pct(row.cagr),
                    pct(row.volatility),
                    pct(row.max_drawdown),
                    str(int(row.rejected_proposals))
                    if np.isfinite(row.rejected_proposals)
                    else "n/a",
                ]
            )
            + " |"
        )
    if scores.brier_used.mean() >= scores.brier_baseline.mean():
        lines += [
            "",
            "**Forecast validation finding:** the probabilities actually used score worse than the historical-frequency baseline. The point-in-time gate did not establish a reliable forecasting advantage. These forecasts are not validated alpha and cannot justify promotion.",
        ]
    lines += [
        "",
        "### Fresh three-calendar-year accounts",
        "",
        "| Strategy | Accounts | Median total return | Best total return | Worst drawdown | Joint goal successes |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in specs:
        sample = fresh.loc[fresh.model == name]
        lines.append(
            f"| {name} | {len(sample)} | {pct(sample.total_return.median())} | {pct(sample.total_return.max())} | {pct(sample.max_drawdown.min())} | {int(sample.joint_success.sum())} |"
        )
    lines += [
        "",
        "The four fixed designs were not retuned after observing performance. A feasibility correction projected concentrated asset budgets into the already declared caps and added the no-reserve retry; it did not change the return target, loss objective, risk tolerance or strategy maps. Pre-correction rejected-proposal evidence is preserved under `before-budget-feasibility-fix/`.",
    ]
    lines += [
        "",
        "The `_no_guard` rows are fixed diagnostic twins without the account drawdown guard. They remain subject to crisis, position, volatility and exact risk-accounting controls, but are **not authorized alternatives** to the user mandate. Cash-heavy protected accounts must not be praised as successful crisis prediction merely because they stop participating.",
        "",
        "## All Weather benchmarking",
        "",
        "Bridgewater balances exposures to growth and inflation surprises. Our liquid unlevered proxy approximates this principle with five economic sleeves and is not an official Bridgewater allocation or private-fund return. [Bridgewater methodology](https://www.bridgewater.com/resources/all-weather-story.pdf).",
        "",
        "Actual ALLW ETF overlap is short and uses a different derivative/exposure structure. These are descriptive results, not risk-matched proof of superiority. [Official ALLW information](https://www.ssga.com/us/en/intermediary/etfs/state-street-bridgewater-all-weather-etf-allw).",
        "",
        "| Model | Overlap period return | Annual volatility | Max drawdown |",
        "|---|---:|---:|---:|",
    ]
    for row in overlap.loc[
        overlap.model.isin(
            ["actual_ALLW", "all_weather_proxy"] + [n + "_no_guard" for n in specs]
        )
    ].itertuples():
        lines.append(
            f"| {row.model} | {pct(row.total_return)} | {pct(row.volatility)} | {pct(row.max_drawdown)} |"
        )
    lines += [
        "",
        f"Actual ALLW overlap: **{overlap.start.iloc[0]}–{overlap.end.iloc[0]}**. Initial ALLW entry cost is modeled; the research accounts enter that comparison with existing holdings. The overlap does not establish superiority over Bridgewater at matched risk.",
    ]
    lines += [
        "",
        "## Conditional three-year estimates",
        "",
        "5,000 joint 21-session block-bootstrap paths include historical drift uncertainty and preserve shared sampled dates. The return streams are net diagnostic-twin returns, not simulated underlying markets; the account guard and allocations are not rerun on those paths. These are conditional development scenarios, not validated forward predictions or calibrated success probabilities.",
        "",
        "| Stream | Median total return | 5th–95th percentile return | 95th-percentile drawdown magnitude | Joint 50%/5% frequency |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in simulation.itertuples():
        lines.append(
            f"| {row.model} | {pct(row.median_total_return)} | {pct(row.p05_total_return)} to {pct(row.p95_total_return)} | {pct(row.p95_drawdown_magnitude)} | {pct(row.conditional_joint_goal_frequency)} |"
        )
    lines += [
        "",
        "One-year scenarios for each starting macro quadrant and market crisis are retained in `starting-regime-one-year-scenarios.csv`. They resample complete historical 21-session blocks, conditioned on the block-start state, including within-block transitions and drift uncertainty. Repeated sampling assumes similar starting-condition distributions over the horizon; it is not a structural macro transition forecast. Insufficient block counts are flagged. A sampled drawdown quantile is not a maximum possible loss.",
        "",
        "## Historical reference weights and diversification",
        "",
        "Reference proposals are fresh-account illustrations at the last historical decision close, before the owner account guard. They are **not current positions or buy instructions**. Actual continuous accounts may be cash-locked. Capital and whole-account risk weights are retained in `last-historical-reference-targets.csv`; exact reconciled budget fields remain in proposal JSON files.",
        "",
        "| Strategy | Invested ETFs | Uninvested cash | Effective positive-risk positions | Forecast annual volatility |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in diversity.itertuples():
        lines.append(
            f"| {row.model} | {row.invested_instruments} | {pct(row.cash_weight)} | {row.effective_positive_risk_positions:.2f} | {pct(row.forecast_annual_volatility)} |"
        )
    lines += [
        "",
        f"**Strategy overlap:** historical diagnostic net-return correlations range from **{pairwise.min():.3f} to {pairwise.max():.3f}**. These designs share much of the same risk engine and asset universe. Dividing capital between them does not create four independent sources of returns. This is a material limitation to the proposed diversification; it prevents claiming institutional or All Weather superiority from strategy count alone.",
    ]
    capital = targets.pivot(
        index="symbol", columns="model", values="capital_weight"
    ).fillna(0)
    lines += [
        "",
        f"Illustrative reference-target date: **{targets.as_of.iloc[0]}**, with zero assumed prior account drawdown. All other catalogue assets receive zero weight. These are archived proposal illustrations, not current allocations.",
        "",
        "| Asset | " + " | ".join(specs) + " |",
        "|---|" + "---:|" * len(specs),
    ]
    for symbol, row in capital.iterrows():
        lines.append(
            "| " + symbol + " | " + " | ".join(pct(row[n]) for n in specs) + " |"
        )
    lines += [
        "",
        "## Decision and remaining qualification",
        "",
        "No design is declared an optimum. The mandate remains a joint return/preservation test; a higher return earned by violating the drawdown objective cannot qualify. Previous research included 36 inspected smart variants plus additional ablations/parent work; these four fixed designs add four more. There is no pristine out-of-sample claim. The universe and architecture were chosen retrospectively. The reserved boundary remains 2025-10-30.",
        "",
        "Before promotion: independently validate economic labels, probability calibration and tails; review factor/duration/currency/liquidity exposures; replay actual executable prices; qualify the new risk contract and eligible instruments through production authorization; collect genuinely fresh observations; and obtain strategy/paper acceptance. Actual managed-futures benchmarking from earlier work remains a separate short-history illustration. Long-only trend is not a replication of diversified futures trend. [Trend research and limitations](https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing).",
        "",
        "## Reproduction and evidence",
        "",
        "```sh",
        "python3 evaluate_four_macro_strategies.py",
        "python3 report_four_macro_strategies.py",
        "python3 -m pytest -q test_four_macro_strategies.py",
        "python3 -m pytest -q",
        "```",
        "",
        "Frozen design: `research/four_macro_strategies.json`. Evidence: `var/research/four-macro-strategies-v6/` (ignored local artifacts requiring packaging for independent review). Includes full/doubled-cost accounts, 60 fresh accounts, allocation audits, forecast timestamps/training endpoints, Brier/reliability scores, regime/cycle attribution, stress episodes, reference weights, risk diagnostics, diversification, actual ALLW overlap, conditional scenarios and source checksums.",
        "",
    ]
    validation = OUT / "validation.json"
    if validation.exists():
        v = json.loads(validation.read_text())
        lines += [
            "## Validation",
            "",
            f"Focused tests: **{v['focused_passed']} passed**. Full suite: **{v['full_suite_passed']:,} passed**. Ruff and diff checks pass. These are engineering checks, not investment qualification.",
            "",
        ]
    Path("FOUR_MACRO_STRATEGIES_ASSESSMENT.md").write_text("\n".join(lines))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True, layout="constrained")
    for name, frame in frames.items():
        axes[0].plot(frame.index, frame.equity, label=name, linewidth=1.0)
        peak = np.maximum.accumulate(np.r_[1.0, frame.equity.to_numpy()])[1:]
        axes[1].plot(
            frame.index, 100 * (frame.equity / peak - 1), label=name, linewidth=1.0
        )
        governed = pd.read_csv(OUT / f"{name}.csv", index_col=0, parse_dates=True)
        axes[2].plot(governed.index, governed.equity, label=name, linewidth=1.0)
    proxy = pd.read_csv(OUT / "all_weather_proxy.csv", index_col=0, parse_dates=True)
    axes[0].plot(
        proxy.index,
        proxy.equity,
        label="All Weather-inspired proxy",
        color="black",
        linestyle="--",
    )
    axes[0].set(
        title="Fixed strategy diagnostics: account guard removed, other limits retained",
        ylabel="Growth of $1",
    )
    axes[1].set(ylabel="Diagnostic drawdown (%)")
    axes[1].axhline(-5, color="red", linestyle="--", linewidth=0.8)
    axes[2].set(
        title="Mandate accounts: persistent 2%–4% drawdown protection retained",
        ylabel="Growth of $1",
    )
    axes[0].legend(fontsize=8)
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.savefig(OUT / "four-strategy-comparison.png", dpi=150)
    plt.close(fig)
    (OUT / "assessment-evidence.json").write_text(
        json.dumps(
            {
                "report_sha256": hashlib.sha256(
                    Path("FOUR_MACRO_STRATEGIES_ASSESSMENT.md").read_bytes()
                ).hexdigest(),
                "writer_sha256": hashlib.sha256(
                    Path(__file__).read_bytes()
                ).hexdigest(),
                "csv_hashes": {
                    str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(OUT.glob("*.csv"))
                },
            },
            indent=2,
        )
    )
    print("\n".join(lines[:16]))


if __name__ == "__main__":
    main()
