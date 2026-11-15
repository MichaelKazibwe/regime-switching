"""Purged chronological, finite calibration trials; no incumbent model changes."""

from copy import deepcopy
import numpy as np
from fourregimestrategies import FEATURES, quadrant
from live_strategy_training import fit_classifier


def reliability(probabilities, actual):
    p, y = np.asarray(probabilities), np.asarray(actual)
    confidence, predicted = p.max(axis=1), p.argmax(axis=1)
    bins = []
    for low, high in zip([0, 0.4, 0.6, 0.8], [0.4, 0.6, 0.8, 1.000001]):
        mask = (confidence >= low) & (confidence < high)
        if mask.any():
            bins.append(
                dict(
                    low=low,
                    high=min(high, 1),
                    count=int(mask.sum()),
                    confidence=float(confidence[mask].mean()),
                    accuracy=float((predicted[mask] == y[mask]).mean()),
                )
            )
    return bins


def evaluate(features, settings, *, freeze, origins, regularization, shrink):
    spec = {**deepcopy(settings), "regularization_C": regularization}
    model, baseline, metadata = fit_classifier(features[: freeze + 1], freeze, spec)
    probabilities, actual, dates = [], [], []
    for i in origins:
        end = i + spec["horizon_sessions"]
        if (
            end >= len(features)
            or not features[i].get("macro_valid", False)
            or not features[end].get("macro_valid", False)
        ):
            continue
        learned = baseline.copy()
        if model is not None:
            learned = np.zeros(4)
            learned[model[-1].classes_] = model.predict_proba(
                [[features[i][k] for k in FEATURES]]
            )[0]
        probabilities.append((1 - shrink) * baseline + shrink * learned)
        actual.append(quadrant(features[end]))
        dates.append(features[end]["date"])
    if not actual:
        return dict(
            status="BLOCKED_NO_MATURED_OUTCOMES",
            regularization=regularization,
            shrink=shrink,
            outcomes=0,
            model_brier=None,
            baseline_brier=None,
            improvement_lower_95=None,
            reliability=[],
            last_training_label=metadata["last_training_label_date"],
            freeze_date=features[freeze]["date"],
            outcome_dates=[],
            trained=model is not None,
        )
    p, target = np.asarray(probabilities), np.eye(4)[actual]
    losses = np.square(p - target).sum(axis=1)
    base = np.square(baseline - target).sum(axis=1)
    # Origins are horizon-spaced: the quarterly labels do not overlap.
    improvement = base - losses
    rng = np.random.default_rng(842)
    lower = None
    if len(improvement) >= 12:
        starts = rng.integers(
            0, len(improvement) - 1, size=(2000, int(np.ceil(len(improvement) / 2)))
        )
        ids = (starts[:, :, None] + np.arange(2)).reshape(2000, -1)[
            :, : len(improvement)
        ]
        lower = float(np.quantile(improvement[ids].mean(axis=1), 0.05))
    return dict(
        regularization=regularization,
        shrink=shrink,
        outcomes=len(actual),
        model_brier=float(losses.mean()),
        baseline_brier=float(base.mean()),
        improvement_lower_95=lower,
        reliability=reliability(p, actual),
        last_training_label=metadata["last_training_label_date"],
        freeze_date=features[freeze]["date"],
        outcome_dates=dates,
        trained=model is not None,
        confidence_status="TWO_QUARTER_BLOCK_DIAGNOSTIC"
        if lower is not None
        else "INSUFFICIENT_NONOVERLAPPING_OUTCOMES",
    )


def nonoverlap_origins(features, start, stop, horizon):
    result = []
    i = start
    while i < stop and i + horizon < len(features):
        if features[i].get("macro_valid", False) and features[i + horizon].get(
            "macro_valid", False
        ):
            result.append(i)
            i += horizon
        else:
            i += 1
    return result


def study(features, settings, *, test_sessions=1260):
    h = settings["horizon_sessions"]
    if test_sessions < 12 * h:
        raise ValueError("Calibration test must allow twelve nonoverlapping horizons")
    test_start = len(features) - test_sessions - h
    validation_start = test_start - 504 - h
    if validation_start <= settings["minimum_training"] + h:
        raise ValueError("Insufficient separate calibration history")
    # Every validation label strictly predates the final test freeze.
    origins = nonoverlap_origins(features, validation_start, test_start - h, h)
    trials = [
        evaluate(
            features,
            settings,
            freeze=validation_start,
            origins=origins,
            regularization=c,
            shrink=s,
        )
        for c in (0.01, 0.1, 1.0)
        for s in (0.0, 0.25, 0.5)
    ]
    available = [r for r in trials if r["outcomes"]]
    selected = (
        min(available, key=lambda r: r["model_brier"]) if available else trials[0]
    )
    result = evaluate(
        features,
        settings,
        freeze=test_start,
        origins=nonoverlap_origins(features, test_start, len(features) - h, h),
        regularization=selected["regularization"],
        shrink=selected["shrink"],
    )
    return dict(
        status="REVIEW_ONLY_BASELINE_RETAINED",
        trials=trials,
        selected_on_validation=selected,
        historical_test=result,
        candidate_gate_passed=bool(
            result["trained"]
            and result["outcomes"] >= 12
            and result["improvement_lower_95"] > 0
        ),
        feature_names=list(FEATURES),
        test_sessions=test_sessions,
        labels_overlap=False,
        automatic_promotion=False,
        limitation="Repeatedly observed historical data, not pristine forward evidence; small nonoverlapping quarterly samples block activation.",
    )
