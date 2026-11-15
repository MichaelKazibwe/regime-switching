"""Same-date, same-cost diagnostics; no model selection or automatic promotion."""

from pathlib import Path
import json
import numpy as np
import pandas as pd
from growth_resilience import WEIGHTS, metrics
from portfolio_contract import extended_prices
from economic_design_assessment import replay, paired_interval
from strategy_report import load_training_report
from strategy_integrity import file_hash
from strategy_receipts import atomic_json


def compare(bundle, output):
    bundle = Path(bundle)
    b = json.loads(bundle.read_text())
    report = load_training_report(b["training_report"])
    if not report["current_numerical_source_match"]:
        raise ValueError("Current numerical sources required")
    prices = extended_prices(b["capture"], b["benchmark_extension"])
    daily = prices.pct_change(fill_method=None)
    start, end = report["evaluation"]["start"], report["evaluation"]["end"]
    selected = daily.loc[start:end].drop(columns=["ALLW"], errors="ignore")
    weights = {s: w for s, w in WEIGHTS.items() if s != "USD_CASH"}
    prior_vol = daily[list(weights)].mul(pd.Series(weights)).sum(
        axis=1, min_count=len(weights)
    ).rolling(252, min_periods=252).std().shift(1) * np.sqrt(252)
    root = Path(b["training_report"]).parent
    results = []
    for strategy in report["strategies"]:
        name = strategy["name"]
        original = pd.read_csv(root / f"{name}.csv", index_col=0, parse_dates=True)
        if not original.index.equals(selected.index):
            raise ValueError("Comparison session mismatch")
        audit = json.loads((root / f"{name}-audit.json").read_text())
        targets = {pd.Timestamp(t["date"]): t["weights"] for t in audit["trades"]}
        reference = {}
        budgets = {}
        for t in audit["trades"]:
            date = pd.Timestamp(t["date"])
            decision = pd.Timestamp(t["decision_time"])
            # Trade decision must be recorded before execution-date close; training uses prior-close decisions.
            if (
                decision.tzinfo is None
                or decision.tz_convert("America/New_York").date() >= date.date()
            ):
                raise ValueError("Reference schedule contains same-close decision")
            budget = (
                float(t.get("volatility_ceiling", 0.0))
                if sum(t["weights"].values()) > 0
                else 0.0
            )
            sigma = float(prior_vol.loc[date])
            if not np.isfinite(sigma) or sigma <= 0:
                raise ValueError("Prior benchmark covariance unavailable")
            scale = min(1.0, budget / sigma)
            reference[date] = {s: w * scale for s, w in weights.items()}
            budgets[str(date.date())] = budget
        rows = []
        for cost in [0.0, 0.0015, 0.003]:
            active = replay(selected, targets, cost_rate=cost, protect=False)
            passive = replay(selected, reference, cost_rate=cost, protect=False)
            if cost == 0.0015 and not np.allclose(
                active["return"], original["return"], atol=1e-10, rtol=0
            ):
                raise ValueError("Strategy replay failed reconciliation")
            intervals = [
                paired_interval(active["return"], passive["return"], block=block)
                for block in [21, 63]
            ]
            rows.append(
                {
                    "cost_rate": cost,
                    "strategy": metrics(
                        active.equity.to_numpy(), active["return"].to_numpy()
                    ),
                    "risk_matched_reference": metrics(
                        passive.equity.to_numpy(), passive["return"].to_numpy()
                    ),
                    "paired_intervals": intervals,
                    "robust_positive_lower_bound": all(
                        i["p025"] > 0 for i in intervals
                    ),
                }
            )
        results.append(
            {
                "strategy": name,
                "comparisons": rows,
                "prior_decision_volatility_budgets": budgets,
            }
        )
    result = {
        "schema_version": 1,
        "status": "DESCRIPTIVE_COMPARISON_NOT_PROMOTION",
        "start": start,
        "end": end,
        "strategies": results,
        "bundle_sha256": file_hash(bundle),
        "report_sha256": file_hash(b["training_report"]),
        "limitations": [
            "Fixed-decision cost sensitivities, not adaptive retraining at alternate fees.",
            "Reference shares strategy trade dates and quarantine decisions, with prior 252-session reference volatility and declared decision-time budgets; this is a diagnostic control, not an independently deployable reference.",
            "Retrospective strategies and correlated overlapping observations; intervals are not multiple-testing-adjusted evidence of alpha.",
            "Zero unverified cash yield; no measured broker slippage, taxes or capacity. No return target or account drawdown lock.",
        ],
        "economic_approval": False,
        "execution_enabled": False,
    }
    atomic_json(output, result)
    return result


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--bundle", default="var/investor-dashboard/latest-strategy-run.json"
    )
    p.add_argument(
        "--output", default="var/integrated-deployment/strategy-comparison.json"
    )
    a = p.parse_args()
    x = compare(a.bundle, a.output)
    for row in x["strategies"]:
        r = row["comparisons"][1]
        print(
            row["strategy"],
            f"strategy {r['strategy']['total_return']:.2%}; matched reference {r['risk_matched_reference']['total_return']:.2%}; positive lower bound {r['robust_positive_lower_bound']}",
        )
