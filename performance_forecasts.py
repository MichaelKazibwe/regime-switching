"""Isolated forecasting challengers with as-of refits and persistence benchmarks."""

import numpy as np

from forecast_calibration import nonoverlap_origins, reliability
from fourregimestrategies import FEATURES, quadrant
from live_strategy_training import fit_classifier

BENCHMARKS = ("frequency", "persistence", "transition")


def losses(probabilities, actual):
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(actual, dtype=int)
    if (p.shape != (len(y), 4) or not len(y) or not np.isfinite(p).all()
            or (p < 0).any() or not np.allclose(p.sum(axis=1), 1)
            or (y < 0).any() or (y > 3).any()):
        raise ValueError("Finite four-class probabilities and outcomes required")
    return dict(brier=((p - np.eye(4)[y]) ** 2).sum(axis=1),
                log_loss=-np.log(np.maximum(p[np.arange(len(y)), y], 1e-12)))


def score(probabilities, actual):
    p, y = np.asarray(probabilities), np.asarray(actual)
    values = losses(p, y)
    return dict(
        outcomes=len(y), **{k: float(v.mean()) for k, v in values.items()},
        reliability=reliability(p, y),
        by_outcome_regime={str(k): dict(count=int((y == k).sum()),
                                      **{m: float(v[y == k].mean())
                                         for m, v in values.items()})
                           for k in range(4) if (y == k).any()},
        one_vs_rest=[dict(regime=k, brier=float(((p[:, k] - (y == k)) ** 2).mean()))
                     for k in range(4)],
    )


def improvement_bound(a, b, *, alpha=0.05, paths=4000):
    """Two-origin blocks preserve adjacent quarterly dependence."""
    delta = np.asarray(a) - np.asarray(b)
    if len(delta) < 12:
        return None
    rng = np.random.default_rng(120126)
    starts = rng.integers(0, len(delta) - 1,
                         size=(paths, int(np.ceil(len(delta) / 2))))
    ids = (starts[:, :, None] + np.arange(2)).reshape(paths, -1)[:, :len(delta)]
    return float(np.quantile(delta[ids].mean(axis=1), alpha))


def persistence_probabilities(features, origin, horizon, frequency):
    state = quadrant(features[origin])
    # Smoothed current-state persistence is fixed before inspecting outcomes.
    persistence = 0.10 * frequency + 0.90 * np.eye(4)[state]
    counts = np.ones((4, 4))
    for i in range(max(0, origin - horizon)):
        if (features[i].get("macro_valid", False)
                and features[i + horizon].get("macro_valid", False)):
            counts[quadrant(features[i]), quadrant(features[i + horizon])] += 1
    transition = counts[state] / counts[state].sum()
    return persistence, transition


def evaluate(features, settings, origins, regularization, shrink, cache=None):
    cache = {} if cache is None else cache
    probabilities, actual, dates, bindings = [], [], [], []
    benchmark = {k: [] for k in BENCHMARKS}
    for i in origins:
        end = i + settings["horizon_sessions"]
        if (end >= len(features) or not features[i].get("macro_valid", False)
                or not features[end].get("macro_valid", False)):
            continue
        key = (i, regularization)
        if key not in cache:
            model, frequency, metadata = fit_classifier(
                features[:i + 1], i, {**settings, "regularization_C": regularization})
            learned = frequency.copy()
            if model is not None:
                learned = np.zeros(4)
                learned[model[-1].classes_] = model.predict_proba(
                    [[features[i][k] for k in FEATURES]])[0]
            persistence, transition = persistence_probabilities(
                features, i, settings["horizon_sessions"], frequency)
            cache[key] = (learned, frequency, persistence, transition, metadata)
        learned, frequency, persistence, transition, metadata = cache[key]
        last_label = metadata["last_training_label_date"]
        if last_label is not None and last_label >= features[i]["date"]:
            raise ValueError("Forecast training label must strictly predate origin")
        probabilities.append((1 - shrink) * frequency + shrink * learned)
        for k, value in zip(BENCHMARKS, [frequency, persistence, transition]):
            benchmark[k].append(value)
        actual.append(quadrant(features[end]))
        dates.append(features[end]["date"])
        bindings.append(dict(origin=features[i]["date"], outcome=dates[-1],
                             last_training_label=last_label, trained=metadata["trained"]))
    if not actual:
        return dict(status="BLOCKED_NO_OUTCOMES", outcomes=0)
    candidate_losses = losses(probabilities, actual)
    comparisons = {}
    # Simultaneous one-sided diagnostic across three baselines and two scores.
    for k in BENCHMARKS:
        base_losses = losses(benchmark[k], actual)
        comparisons[k] = {
            m: dict(mean_improvement=float((base_losses[m] - candidate_losses[m]).mean()),
                    lower_bound=improvement_bound(base_losses[m], candidate_losses[m],
                                                  alpha=0.05 / 6))
            for m in candidate_losses
        }
    return dict(status="RETROSPECTIVE_ASOF_FORECASTS", outcomes=len(actual),
                regularization=regularization, shrink=shrink,
                candidate=score(probabilities, actual),
                benchmarks={k: score(v, actual) for k, v in benchmark.items()},
                comparisons=comparisons, bindings=bindings,
                probabilities=np.asarray(probabilities).tolist(), actual=actual,
                outcome_dates=dates)


def study(features, settings, *, test_sessions=1260):
    h = settings["horizon_sessions"]
    test_start = len(features) - test_sessions - h
    validation_start = test_start - 504 - h
    if test_sessions < 12 * h or validation_start <= settings["minimum_training"] + h:
        raise ValueError("Insufficient chronological forecast history")
    validation_origins = nonoverlap_origins(features, validation_start, test_start - h, h)
    cache = {}
    trials = [evaluate(features, settings, validation_origins, c, s, cache)
              for c in (0.01, 0.1, 1.0) for s in (0.0, 0.25, 0.5)]
    available = [r for r in trials if r["outcomes"]]
    if not available:
        return dict(status="BLOCKED_NO_VALIDATION_OUTCOMES", trials=trials,
                    candidate_gate_passed=False, promotion_enabled=False)
    selected = min(available, key=lambda r: (r["candidate"]["brier"],
                                           r["candidate"]["log_loss"], r["shrink"]))
    test = evaluate(features, settings,
                    nonoverlap_origins(features, test_start, len(features) - h, h),
                    selected["regularization"], selected["shrink"])
    passed = bool(test["outcomes"] >= 12 and selected["shrink"] > 0
                  and all(b["trained"] for b in test.get("bindings", []))
                  and all(v["lower_bound"] is not None and v["lower_bound"] > 0
                          for c in test.get("comparisons", {}).values()
                          for v in c.values()))
    return dict(status="COMPLETED_RESEARCH_ONLY", trials=trials,
                selected_on_validation=dict(regularization=selected["regularization"],
                                            shrink=selected["shrink"]),
                historical_test=test, candidate_gate_passed=passed,
                prospective_confirmation_required=True, promotion_enabled=False,
                execution_enabled=False,
                protocol=dict(refit="Configured rolling training window refit as-of each origin; labels strictly before origin",
                              label_horizon_sessions=h, overlapping_test_labels=False,
                              validation_last_outcome_before=features[test_start]["date"],
                              lower_bound_alpha=0.05 / 6,
                              limitation="Previously inspected history; retrospective evidence only"))
