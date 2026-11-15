"""Fixed-origin forecasting evidence; future availability never moves origins."""

import argparse
from pathlib import Path

from performance_forecasts import evaluate
from strategy_integrity import strict_json, file_hash
from strategy_receipts import atomic_json
from strategy_report import load_training_report


def calendar_evaluation(features, settings, origins, c, shrink, cache=None):
    result = evaluate(features, settings, origins, c, shrink, cache)
    h = settings["horizon_sessions"]
    result["fixed_calendar"] = [dict(
        origin=features[i]["date"], outcome=features[i + h]["date"],
        status="ORIGIN_UNAVAILABLE" if not features[i].get("macro_valid", False)
        else "OUTCOME_UNAVAILABLE" if not features[i + h].get("macro_valid", False)
        else "SCORED") for i in origins]
    return result


def study(features, settings, *, test_sessions=1260):
    h = settings["horizon_sessions"]
    test_start = len(features) - test_sessions - h
    validation_start = test_start - 504 - h
    if test_sessions < 12 * h or validation_start <= settings["minimum_training"] + h:
        raise ValueError("Insufficient fixed-calendar forecasting history")
    validation_origins = list(range(validation_start, test_start - h, h))
    test_origins = list(range(test_start, len(features) - h, h))
    cache = {}
    trials = [calendar_evaluation(features, settings, validation_origins, c, s, cache)
              for c in (0.01, 0.1, 1.0) for s in (0.0, 0.25, 0.5)]
    available = [r for r in trials if r["outcomes"]]
    if not available:
        return dict(status="BLOCKED_NO_VALIDATION_OUTCOMES", trials=trials,
                    candidate_gate_passed=False, promotion_enabled=False)
    selected = min(available, key=lambda r: (r["candidate"]["brier"],
                                           r["candidate"]["log_loss"], r["shrink"]))
    test = calendar_evaluation(features, settings, test_origins,
                               selected["regularization"], selected["shrink"])
    passed = bool(test["outcomes"] >= 12 and selected["shrink"] > 0
                  and all(b["trained"] for b in test.get("bindings", []))
                  and all(v["lower_bound"] is not None and v["lower_bound"] > 0
                          for comparison in test.get("comparisons", {}).values()
                          for v in comparison.values()))
    return dict(status="COMPLETED_FIXED_CALENDAR_RESEARCH", trials=trials,
                selected_on_validation=dict(regularization=selected["regularization"],
                                            shrink=selected["shrink"]),
                historical_test=test, candidate_gate_passed=passed,
                protocol=dict(horizon_sessions=h, future_availability_moves_origins=False,
                              labels_overlap=False, lower_bound_alpha=0.05 / 6,
                              validation_last_outcome_before=features[test_start]["date"],
                              scored_outcomes_conditioned_on_observed_availability=True,
                              limitation="Retrospective history; unavailable outcomes disclosed; prospective confirmation required"),
                execution_enabled=False, promotion_enabled=False)


def run(bundle, output):
    bundle, output = Path(bundle).resolve(), Path(output).resolve()
    b = strict_json(bundle)
    report = load_training_report(b["training_report"])
    if not report["current_numerical_source_match"]:
        raise ValueError("Source-matched training required")
    features_path = Path(b["training_report"]).parent / "features.json"
    settings = strict_json("research/four_macro_strategies.json")["macro_forecast"]
    sources = {p: file_hash(p) for p in [__file__, "performance_forecasts.py",
                                       "live_strategy_training.py", "forecast_calibration.py",
                                       "fourregimestrategies.py", "research/four_macro_strategies.json"]}
    result = study(strict_json(features_path), settings)
    if any(file_hash(p) != h for p, h in sources.items()):
        raise ValueError("Forecast sources changed during evaluation")
    result.update(market_session=report["market_session"], source_hashes=sources,
                  bundle_sha256=file_hash(bundle), features_sha256=file_hash(features_path))
    atomic_json(output, result, exclusive=True)
    print("Authoritative fixed-calendar forecast evidence:", output, flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(args.bundle, args.output)
