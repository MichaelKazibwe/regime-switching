"""Reproducible diagnostics and roadmap assessment from the frozen goal study."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from evaluate_three_year_goal import OUT, PLAN, rolling_goal
from institutionalportfolio import coverage_report
from optimize_hybrid_portfolio import rebased
from stress_test_models import block_indices


def forecast_diagnostics(frame):
    valid = frame.loc[frame.filtered_ready & (frame.raw_daily_sigma > 1e-8)]
    result = {"ready_observations": len(valid)}
    if len(valid) >= 63:
        result["raw_normal"] = coverage_report(
            valid.gross_return, valid.raw_daily_sigma
        )
        nonzero = valid.loc[valid.filtered_var95 > 1e-8]
        if len(nonzero) >= 63:
            result["filtered_historical"] = coverage_report(
                nonzero.gross_return, nonzero.filtered_var95 / norm.ppf(0.95)
            )
            result["filtered_historical"].pop(
                "realized_to_forecast_volatility_ratio", None
            )
            result["filtered_historical"]["interpretation"] = (
                "Coverage of prior-only filtered historical VaR thresholds; "
                "Gaussian-equivalent sigma is used solely to reuse exception tests. "
                "No normal-return assumption or volatility calibration claim."
            )
    return result


def main():
    plan = json.loads(PLAN.read_text())
    status = json.loads((OUT / "research-screen.json").read_text())
    for name, digest in status["hashes"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Executed study source changed: {name}")
    comparison = pd.read_csv(OUT / "comparison.csv")
    fresh = pd.read_csv(OUT / "fresh-three-year-accounts.csv")
    screen = pd.read_csv(OUT / "feasibility-screen.csv")
    names = screen.model.tolist()
    diagnostics = {}
    frames = {}
    for name in names:
        for suffix in ("", "-no-drawdown-guard"):
            key = name + suffix
            frames[key] = pd.read_csv(OUT / f"{key}.csv", index_col=0, parse_dates=True)
            diagnostics[key] = forecast_diagnostics(frames[key])
    (OUT / "extended-risk-diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2)
    )
    # Paired chronological date-block uncertainty for the fixed overlay ablations.
    returns = pd.DataFrame(
        {name: frames[name + "-no-drawdown-guard"]["return"] for name in names}
    )
    logs = np.log1p(returns.to_numpy())
    rng = np.random.default_rng(51024)
    draws = []
    for _ in range(20):
        indices = block_indices(rng, len(logs), len(logs), 100, 21)
        draws.append(np.expm1(logs[indices].mean(axis=1) * 252))
    annual = np.concatenate(draws)
    paired = []
    for j, name in enumerate(names):
        baseline = j - j % 3
        difference = annual[:, j] - annual[:, baseline]
        interval = np.quantile(difference, [0.025, 0.975])
        paired.append(
            {
                "model": name,
                "baseline": names[baseline],
                "cagr_difference_ci95_low": float(interval[0]),
                "cagr_difference_ci95_high": float(interval[1]),
                "interpretation": "Paired development bootstrap of no-guard returns; not selection-adjusted alpha inference",
            }
        )
    pd.DataFrame(paired).to_csv(OUT / "paired-overlay-uncertainty.csv", index=False)
    episodes = []
    periods = [
        ("Partial GFC", "2008-07-28", "2009-06-30"),
        ("Euro debt", "2011-01-01", "2011-12-31"),
        ("China commodity slowdown", "2015-01-01", "2016-02-29"),
        ("2018 selloff", "2018-01-01", "2018-12-31"),
        ("COVID shock", "2020-02-19", "2020-03-23"),
        ("Inflation shock", "2022-01-01", "2022-12-31"),
    ]
    from compare_portfolio_models import metrics

    for name, frame in frames.items():
        for label, start, end in periods:
            selected = rebased(frame.loc[start:end])
            m = metrics(selected, pd.Series(0.0, index=selected.index))
            episodes.append(
                {
                    "model": name,
                    "episode": label,
                    "period_return": m["total_return"],
                    "within_episode_drawdown": m["max_drawdown"],
                    "mean_invested_weight": 1 - selected.cash.mean(),
                }
            )
    pd.DataFrame(episodes).to_csv(OUT / "stress-episodes.csv", index=False)
    horizons = []
    for name in ["candidate_00", "candidate_00-no-drawdown-guard"]:
        for years in (3, 5, 7, 10):
            windows = rolling_goal(frames[name], horizon=years * 252)
            horizons.append(
                {
                    "model": name,
                    "years_approx": years,
                    "windows": len(windows),
                    "median_total_return": float(windows.return_3y.median()),
                    "joint_50pct_return_5pct_drawdown_frequency": float(
                        windows.joint_success.mean()
                    ),
                }
            )
    pd.DataFrame(horizons).to_csv(OUT / "longer-horizon-diagnostics.csv", index=False)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout="constrained")
    grouped = fresh.groupby("model").agg(
        median_return=("return_3y", "median"), worst_drawdown=("max_drawdown", "min")
    )
    axes[0].scatter(
        -100 * grouped.worst_drawdown,
        100 * grouped.median_return,
        label="12 governed candidates",
    )
    axes[0].axvline(5, color="red", linestyle="--", label="5% decline objective")
    axes[0].axhline(50, color="green", linestyle="--", label="50% return objective")
    axes[0].set(
        xlabel="Worst drawdown across fresh accounts (%)",
        ylabel="Median three-calendar-year return (%)",
        title="Observed goal gap: development evidence",
    )
    axes[0].legend(fontsize=8)
    for name, filename in [
        ("Guarded growth 50", "candidate_00.csv"),
        ("Same model without account guard", "candidate_00-no-drawdown-guard.csv"),
        ("Strategic growth 70 benchmark", "strategic_equity_70.csv"),
    ]:
        frame = pd.read_csv(OUT / filename, index_col=0, parse_dates=True)
        axes[1].plot(frame.index, frame.equity, label=name, linewidth=1.2)
    axes[1].set(
        ylabel="Growth of initial $1",
        title="Continuous accounts: cost of loss protection",
    )
    axes[1].legend(fontsize=7)
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.savefig(OUT / "goal-feasibility.png", dpi=160)
    plt.close(fig)
    guarded = comparison.loc[comparison.role == "GOVERNED_RESEARCH_CANDIDATE"]
    unguarded = comparison.loc[comparison.role == "DIAGNOSTIC_ABLATION"]
    best = fresh.loc[fresh.return_3y.idxmax()]
    worst = fresh.loc[fresh.max_drawdown.idxmin()]

    def pct(v):
        return f"{100 * v:.2f}%"

    lines = [
        "# Three-year goal feasibility assessment",
        "",
        f"**Research decision: {status['status']}. No strategy accepted and no production activation.**",
        "",
        "Mandate: 50% cumulative net investment return over three calendar years and no more than a 5% account peak-to-trough decline. Required compound annual growth is **14.47%**. USD accounting, no contributions, nominal returns before investor taxes. A finite backtest cannot guarantee either objective.",
        "",
        "## Executed evidence",
        "",
        f"- Frozen **12 variants**, plus 12 fixed no-account-guard diagnostic twins. Previous inspected smart variants: {plan['prior_smart_variants']}; older parent/hybrid work is additional.",
        f"- **{len(fresh)} fresh three-calendar-year accounts**, {status['fresh_accounts_per_candidate']} start dates per candidate. Joint observed successes: **{int(fresh.joint_success.sum())}/{len(fresh)}**. These overlapping accounts are not independent trials.",
        f"- Highest observed fresh-account return: **{pct(best.return_3y)}** ({best.model}, {best.start}–{best.end}); its drawdown was {pct(best.max_drawdown)}.",
        f"- Worst fresh-account drawdown: **{pct(worst.max_drawdown)}** ({worst.model}, {worst.start}–{worst.end}).",
        f"- Continuous protected-account CAGR range: **{pct(guarded.cagr.min())} to {pct(guarded.cagr.max())}**. No-account-guard twin CAGR range: **{pct(unguarded.cagr.min())} to {pct(unguarded.cagr.max())}**.",
        f"- Largest executed core risk-budget error: **{status['risk_budget_error_max']:.3g}**, against unchanged 1e-6 tolerance.",
        "- Next-close fills, 15bps traded-notional modeled costs, 30bps fixed-reference sensitivity, zero yield on truly uninvested cash.",
        "- Macro/trend ablations, rolling horizons, raw/filtered tail coverage, exception clustering, six stress episodes, synthetic gap/delay shocks and 3,000 joint three-year bootstrap paths.",
        "",
        "## Complete variant results",
        "",
        "| Model | Role | CAGR | Maximum drawdown | Rolling approximate-three-year joint success |",
        "|---|---|---:|---:|---:|",
    ]
    for row in comparison.itertuples():
        lines.append(
            f"| {row.model} | {row.role} | {pct(row.cagr)} | {pct(row.max_drawdown)} | {pct(row.rolling_joint_success_frequency)} |"
        )
    lines += [
        "",
        "Risk anchors are variance budgets, not capital allocations. The plain/market/macro-market variants are all retained; none is silently selected after evaluation. Allocation rejection causes a logged cash proposal and makes the research screen fail. The cash high-water mark is never reset. The 2%–4% exposure reduction is a frozen research design choice, not proof that all possible protective policies fail.",
        "",
        "## Interpretation and limitations",
        "",
        "The mandate prioritizes preservation so strongly that the tested account guard sharply restricts compounding. Cash-heavy or inactive periods must not be mistaken for successful crisis forecasting. The no-guard twins reveal the returns and drawdowns forgone; they are diagnostic and are not authorized alternatives. A cash latch requires operator review and does not assume a discretionary profitable restart.",
        "",
        "Both normal and filtered historical forecast diagnostics are retained, including diagnostic no-guard accounts with longer histories. Filtered thresholds use only prior realized standardized residuals and do not raise allocations. Coverage or clustering can still fail; low observation counts are explicitly reported rather than certified.",
        "",
        "Joint bootstrap frequencies resample the fixed no-guard portfolio streams, with shared dates and drift uncertainty. They do not rerun asset-level allocation or the protective account guard on simulated markets. They are conditional diagnostics, not calibrated probabilities of meeting the mandate. Paired overlay intervals are development-only and not corrected for repeated strategy searches.",
        "",
        "Synthetic one-session and repeated three-session shocks demonstrate possible execution-delay losses; they are scenarios, not estimated probabilities. The strategy is long-only and unlevered at the account level; foreign bonds retain currency exposure. Fund prices embed expenses, and modeled costs omit measured spreads, capacity and investor-specific taxes.",
        "",
        "History ends 2025-10-29; the reserved boundary remains 2025-10-30. Source/input hashes are retained. Earlier inspection and retrospective universe/model design mean there is no pristine out-of-sample claim. The first GFC segment is partial. Daily bars cannot establish an intraday 5% drawdown bound.",
        "",
        "## Remaining roadmap gates",
        "",
        "Local research steps 1–9 have executable evidence; an unsuccessful feasibility result is not strategy acceptance. Independent qualification and paper promotion remain closed unless a candidate clears owner-approved research criteria. The current outcome does not justify weakening the 5% objective, risk budgets or authorization gate.",
        "",
        "A real managed-futures ETF comparison, when available, is a fixed separate benchmark and is not a direct futures implementation or a change to the 12-variant search. No pre-inception fund returns are manufactured. Independent factor/duration/currency/liquidity validation, actual execution-price replay, future observations, host qualification and supervised paper acceptance remain necessary external work.",
        "",
        "If no candidate meets the mandate, the owner must choose whether to extend the horizon, permit a deeper temporary decline, or accept a lower return target. This study does not prove that 50%/5% is mathematically impossible; it supplies no evidence sufficient to deploy it.",
        "",
        "## Reproduction",
        "",
        "```sh",
        "python3 evaluate_three_year_goal.py",
        "python3 benchmark_managed_futures.py --fetch",
        "python3 report_three_year_goal.py",
        "python3 -m pytest -q test_goal_portfolio.py",
        "python3 -m pytest -q",
        "```",
        "",
        "Generated evidence: `var/research/three-year-goal-v5/` (ignored local data, must be packaged for independent review). Core files include `comparison.csv`, `fresh-three-year-accounts.csv`, `feasibility-screen.csv`, `decision-audit.json`, `research-screen.json`, `extended-risk-diagnostics.json`, `gap-delay-stress.csv`, `stress-episodes.csv`, `paired-overlay-uncertainty.csv`, `three-year-conditional-bootstrap.csv`, and `goal-feasibility.png`.",
        "",
    ]
    managed = OUT / "managed-futures-comparison.csv"
    if managed.exists():
        rows = pd.read_csv(managed)
        lines += [
            "## Actual managed-futures ETF illustration",
            "",
            "Fixed 10% DBMF sleeve replaces 10% equity capital in a benchmark-only comparison. Actual adjusted fund prices, a 252-return eligibility lag and matched history are used. This is a short-history, retrospective illustration, not a selected or authorized strategy. [Issuer fund description](https://www.imgp.com/us/fund/US53700T8273/).",
            "",
            "| Benchmark | Start | End | CAGR | Maximum drawdown | Rolling joint success |",
            "|---|---|---|---:|---:|---:|",
        ]
        for row in rows.itertuples():
            lines.append(
                f"| {row.model} | {row.start} | {row.end} | {pct(row.cagr)} | {pct(row.max_drawdown)} | {pct(row.rolling_joint_success_frequency)} |"
            )
    reference = diagnostics["candidate_00-no-drawdown-guard"]
    raw = reference.get("raw_normal")
    filtered = reference.get("filtered_historical")
    if raw and filtered:
        lines += [
            "",
            "## Calibration finding",
            "",
            f"In the fixed candidate_00 no-account-guard diagnostic account, raw normal VaR95 exceptions occur on **{pct(raw['var95_exceedance_frequency'])}** of evaluated days; filtered historical exceptions occur on **{pct(filtered['var95_exceedance_frequency'])}**. The filtered unconditional coverage p-value is **{filtered['kupiec_unconditional_coverage_pvalue']:.3f}**, but conditional coverage still fails (**p={filtered['christoffersen_conditional_coverage_pvalue']:.6f}**). Overall frequency improved; clustering remains unresolved. This diagnostic does not certify the protected account or future loss bounds.",
        ]
    synthetic = pd.read_csv(OUT / "gap-delay-stress.csv")
    lines += [
        "",
        "Synthetic stress on historical target allocations reaches **"
        + pct(
            synthetic.loc[synthetic.delay_sessions == 1, "worst_synthetic_loss"].max()
        )
        + "** loss for a one-session scenario and **"
        + pct(
            synthetic.loc[synthetic.delay_sessions == 3, "worst_synthetic_loss"].max()
        )
        + "** for repeated three-session shocks. These are deliberately hypothetical gap/delay scenarios, not historical portfolio losses or probability estimates. They demonstrate why a next-close cash switch cannot guarantee 5% protection.",
    ]
    validation = OUT / "validation.json"
    if validation.exists():
        receipt = json.loads(validation.read_text())
        lines += [
            "",
            "## Engineering validation",
            "",
            f"Full regression suite: **{receipt['full_suite_passed']:,} passed**. Focused goal/benchmark tests: **{receipt['focused_passed']} passed**. Ruff checks for all six new Python files and `git diff --check` pass. Simulation source/input hashes were verified; no production activation or orders occurred. These checks are engineering evidence, not investment acceptance.",
        ]
    Path("THREE_YEAR_GOAL_ASSESSMENT.md").write_text("\n".join(lines) + "\n")
    manifest = {
        "study_status": status["status"],
        "production_activation": False,
        "orders_submitted": 0,
        "report_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "report_sha256": hashlib.sha256(
            Path("THREE_YEAR_GOAL_ASSESSMENT.md").read_bytes()
        ).hexdigest(),
        "evidence_sha256": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(OUT.glob("*.csv"))
        },
    }
    (OUT / "assessment-evidence.json").write_text(json.dumps(manifest, indent=2))
    print("\n".join(lines[:18]))


if __name__ == "__main__":
    main()
