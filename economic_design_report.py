"""Verified repair-5 summary, stress exposure bounds and a standalone figure."""

import argparse
from pathlib import Path

import numpy as np

from strategy_integrity import file_hash, strict_json
from strategy_receipts import atomic_json


def stress_exposure_bound(weights, drawdown, worst_shock_loss, *, cost_allowance=0.003):
    """Illustrative bound for declared shocks, not a loss guarantee or order."""
    values = [drawdown, worst_shock_loss, cost_allowance, *weights.values()]
    if (
        not np.isfinite(values).all()
        or not -1 < drawdown <= 0
        or not 0 <= worst_shock_loss < 1
        or not 0 <= cost_allowance <= 0.01
        or min(weights.values(), default=0) < 0
        or sum(weights.values()) > 1 + 1e-8
    ):
        raise ValueError("Invalid unlevered stress bound inputs")
    remaining = 1 - 0.95 / ((1 + drawdown) * (1 - cost_allowance))
    scale = float(np.clip(remaining / max(worst_shock_loss, 1e-12), 0, 1))
    decline = 1 - (1 + drawdown) * (1 - cost_allowance) * (1 - scale * worst_shock_loss)
    return {
        "role": "ILLUSTRATIVE_STRESS_BOUND_NOT_APPROVED_ALLOCATION",
        "exposure_multiplier_ceiling": scale,
        "cash_fraction_at_ceiling": 1 - scale * sum(weights.values()),
        "carried_drawdown": drawdown,
        "assumed_cost_allowance": cost_allowance,
        "modeled_drawdown_in_worst_declared_shock": decline,
        "declared_case_meets_five_percent": decline <= 0.05 + 1e-12,
        "limitations": "Assumed four-shock set and cost allowance only; no future return, gap protection, investor suitability or execution guarantee.",
        "execution_enabled": False,
        "release_approved": False,
    }


def build(assessment, training, output):
    r = strict_json(assessment)
    t = strict_json(training)
    if r["sources"]["training_report"] != file_hash(training) or r["sources"][
        "module"
    ] != file_hash("economic_design_assessment.py"):
        raise ValueError("Economic source mismatch")
    root = Path(assessment).parent
    for name, h in r["artifacts"].items():
        if Path(name).name != name or file_hash(root / name) != h:
            raise ValueError("Economic artifact mismatch")
    for name, h in r["sources"]["dependencies"].items():
        if file_hash(name) != h:
            raise ValueError("Economic dependency changed")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    bounds = {}
    for s in r["strategies"]:
        candidate = next(
            x["candidate"] for x in t["strategies"] if x["name"] == s["name"]
        )
        bounds[s["name"]] = stress_exposure_bound(
            candidate["weights"],
            candidate["drawdown"],
            s["stress_review"]["maximum_hypothetical_loss"],
        )
    atomic_json(
        output / "stress-exposure-review.json",
        {
            "status": "UNAPPROVED_REVIEW_ONLY",
            "bounds": bounds,
            "basis": "Up to two full-notional trades at the existing modeled 15 bps; not a stressed spread estimate.",
            "assessment_sha256": file_hash(assessment),
            "release_approved": False,
        },
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 6))
    fig.subplots_adjust(bottom=0.22, top=0.91, left=0.08, right=0.68)
    colors = {
        "All_Weather_style_proxy": "#237b75",
        "Balanced_reference": "#315eaa",
        "SPY_reference": "#ab7342",
    }
    for name, color in colors.items():
        for protect in [True, False]:
            rows = [
                x
                for x in r["frontier"]
                if x["reference"] == name and x["protect"] == protect
            ]
            ax.plot(
                [-100 * x["worst_drawdown"] for x in rows],
                [100 * x["median_three_year_return"] for x in rows],
                "-o" if protect else "--s",
                color=color,
                alpha=1 if protect else 0.65,
                label=name.replace("_", " ")
                + (" / guarded" if protect else " / unprotected diagnostic"),
            )
    ax.axvline(5, color="#b04444", linestyle=":", label="5% drawdown preference")
    ax.axhline(50, color="#6d4d8d", linestyle=":", label="50% three-year target")
    ax.set(
        xlabel="Worst observed account drawdown across cohorts (%)",
        ylabel="Median observed three-year return (%)",
        title="Declared reference frontier: return versus drawdown",
    )
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8, loc="upper left", bbox_to_anchor=(1.01, 1))
    fig.text(
        0.015,
        0.025,
        "29 overlapping cohorts per configuration; zero cash yield; 15 bps costs.\nHistorical reference diagnostics; no mandate approval, calibrated probability or future performance guarantee.",
        fontsize=8,
    )
    fig.savefig(output / "economic-frontier.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    atomic_json(
        output / "report-output-manifest.json",
        {
            "assessment": str(Path(assessment).resolve()),
            "assessment_sha256": file_hash(assessment),
            "training_sha256": file_hash(training),
            "generator_sha256": file_hash(__file__),
            "outputs": {
                n: file_hash(output / n)
                for n in ["stress-exposure-review.json", "economic-frontier.png"]
            },
            "release_approved": False,
        },
    )
    print("Generated verified frontier and unapproved stress exposure review:", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment", type=Path, required=True)
    parser.add_argument("--training-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("output/economic-design"))
    args = parser.parse_args()
    build(args.assessment, args.training_report, args.output)
