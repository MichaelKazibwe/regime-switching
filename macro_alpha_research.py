"""Predeclared complete-case mask ablations; retrospective evidence, no promotion."""

from itertools import combinations
import numpy as np

from macro_alpha import SETTINGS, predict
from fourregimestrategies import quadrant
from performance_forecasts import score, improvement_bound

FEATURES = ("ip_growth", "unemployment_change", "inflation_change", "yield_curve")


def evaluate_masks(features, *, settings=None, minimum_outcomes=12):
    settings = settings or SETTINGS
    h = settings["horizon_sessions"]
    masks = [tuple(c) for n in (2, 3, 4) for c in combinations(FEATURES, n)]
    results = []
    for mask in masks:
        rows = []
        for i in range(settings["minimum_training"] + h + 1, len(features) - h, h):
            if not features[i].get("macro_valid", False) or not features[i + h].get(
                "macro_valid", False
            ):
                continue
            prediction = predict(
                features[: i + 1], {k: features[i][k] for k in mask}, settings
            )
            if prediction["probabilities"] is None:
                continue
            actual = quadrant(features[i + h])
            persistence = (
                0.05 * np.array(prediction["baseline"])
                + 0.95 * np.eye(4)[quadrant(features[i])]
            )
            rows.append(
                dict(
                    origin=features[i]["date"],
                    outcome=features[i + h]["date"],
                    actual=actual,
                    model=prediction["probabilities"],
                    frequency=prediction["baseline"],
                    persistence=persistence.tolist(),
                    training_last_label=prediction["last_training_label_date"],
                )
            )
        split = int(len(rows) * 0.6)
        validation, test = rows[:split], rows[split:]
        enough = len(test) >= minimum_outcomes
        metrics = {}
        if test:
            target = np.array([r["actual"] for r in test])
            for name in ("model", "frequency", "persistence"):
                metrics[name] = score([r[name] for r in test], target)
        bounds = {}
        if enough:
            y = np.eye(4)[[r["actual"] for r in test]]
            model = ((np.array([r["model"] for r in test]) - y) ** 2).sum(axis=1)
            for name in ("frequency", "persistence"):
                baseline = ((np.array([r[name] for r in test]) - y) ** 2).sum(axis=1)
                bounds[name] = improvement_bound(
                    baseline, model, alpha=0.05 / len(masks)
                )
        results.append(
            dict(
                features=list(mask),
                validation_origins=len(validation),
                test_origins=len(test),
                status="RETROSPECTIVE_SCREEN"
                if enough
                else "INSUFFICIENT_NONOVERLAPPING_OUTCOMES",
                metrics=metrics,
                paired_improvement_lower_bounds=bounds,
                screen_passed=bool(
                    enough and all(v is not None and v > 0 for v in bounds.values())
                ),
                first_test_origin=test[0]["origin"] if test else None,
                last_test_outcome=test[-1]["outcome"] if test else None,
                chronology_verified=all(
                    r["training_last_label"] < r["origin"] < r["outcome"] for r in rows
                ),
            )
        )
    return dict(
        schema_version=1,
        status="RESEARCH_EVALUATION",
        masks=results,
        horizon_sessions=h,
        mask_selection_enabled=False,
        parameters_optimized_on_test=False,
        prospective_qualification=False,
        execution_enabled=False,
        methodology="Fixed model parameters; 60/40 chronological evaluation-origin split; nonoverlapping horizon origins; two-origin block bootstrap with family-wise alpha .05 across declared masks.",
        limitations=[
            "Retrospective design, not untouched prospective evidence.",
            "Complete-case origins and labels only; missingness selection bias remains disclosed.",
            "Regime predictive scores do not establish net portfolio alpha.",
        ],
    )
