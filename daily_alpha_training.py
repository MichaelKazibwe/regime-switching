"""Daily, source-bound alpha research fits; no activation, orders or ledger edits."""

import argparse
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from live_strategy_training import fit_classifier
from fourregimestrategies import FEATURES
from observation_process import run_bounded, install_cancellation
from performance_forecast_calendar import run as evaluate
from strategy_integrity import strict_json, file_hash, fingerprint
from strategy_receipts import atomic_json
from strategy_report import load_training_report
from strategy_training_data import usable_session

ROOT = Path(__file__).resolve().parent
SOURCES = ("daily_alpha_training.py", "macro_alpha.py", "performance_forecast_calendar.py", "performance_forecasts.py",
           "global_asset_registry.py", "research/global_asset_registry.json",
           "live_strategy_training.py", "forecast_calibration.py", "fourregimestrategies.py",
           "research/four_macro_strategies.json")


def fit_latest(features, settings, choice):
    if not features:
        raise ValueError("Daily feature history required")
    model, baseline, metadata = fit_classifier(features, len(features) - 1,
                                              {**settings, "regularization_C": choice["regularization"]})
    origin = features[-1]["date"]
    if metadata["last_training_label_date"] and metadata["last_training_label_date"] >= origin:
        raise ValueError("Mature training labels must predate the decision session")
    available = bool(features[-1].get("macro_valid", False))
    probability = None
    if available:
        learned = baseline.copy()
        if model is not None:
            learned = np.zeros(4)
            learned[model[-1].classes_] = model.predict_proba([[features[-1][k] for k in FEATURES]])[0]
        probability = (1 - choice["shrink"]) * baseline + choice["shrink"] * learned
        if not np.isfinite(probability).all() or (probability < 0).any() or not np.isclose(probability.sum(), 1):
            raise ValueError("Invalid daily research probabilities")
        probability = probability.tolist()
    return dict(trained=model is not None, model_parameters=metadata,
                current_inputs_available=available, research_probabilities=probability,
                current_forecast_status="RESEARCH_ONLY" if available else "UNAVAILABLE_CURRENT_MACRO_INPUTS",
                baseline=baseline.tolist(), selected_on_prior_validation=choice,
                activation_enabled=False, execution_enabled=False)


def train(bundle, output):
    bundle, output = Path(bundle).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    sources = {p: file_hash(p) for p in SOURCES}
    b = strict_json(bundle)
    report = load_training_report(b["training_report"])
    if not report["current_numerical_source_match"]:
        raise ValueError("Current source-matched training bundle required")
    features_path = Path(b["training_report"]).parent / "features.json"
    features = strict_json(features_path)
    if features[-1]["date"] != report["market_session"]:
        raise ValueError("Feature/decision session mismatch")
    evaluation = evaluate(bundle, output / "fixed-calendar-evaluation.json")
    if "selected_on_validation" not in evaluation:
        raise ValueError("No validated research configuration available")
    settings = strict_json("research/four_macro_strategies.json")["macro_forecast"]
    model = fit_latest(features, settings, evaluation["selected_on_validation"])
    atomic_json(output / "model.json", model, exclusive=True)
    from macro_alpha import build as macro_build
    macro_monitor = macro_build(b['capture'], b['training_report'])
    atomic_json(output / 'macro-alpha.json', macro_monitor, exclusive=True)
    if any(file_hash(p) != h for p, h in sources.items()):
        raise ValueError("Training source changed during run")
    result = dict(status="COMPLETED_DAILY_RESEARCH_TRAINING", completed_at=datetime.now(timezone.utc).isoformat(),
                  market_session=report["market_session"], bundle_sha256=file_hash(bundle),
                  features_sha256=file_hash(features_path), source_hashes=sources,
                  trained=model["trained"], training_examples=model["model_parameters"]["training_examples"],
                  current_forecast_status=model["current_forecast_status"],
                  macro_alpha_monitoring_enabled=True, macro_alpha_status=macro_monitor['status'],
                  historical_screen_passed=evaluation["candidate_gate_passed"],
                  prospective_confirmation_required=True, promotion_enabled=False, execution_enabled=False,
                  artifacts={p.name: file_hash(p) for p in output.iterdir() if p.is_file()})
    atomic_json(output / "assessment.json", result, exclusive=True)
    return result


def tick(root=ROOT, *, now=None):
    root = Path(root).resolve()
    now = now or datetime.now(timezone.utc)
    state = root / "var/daily-alpha-training"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    session = str(usable_session(now).date())
    heartbeat = dict(checked_at=now.isoformat(), expected_session=session,
                     promotion_enabled=False, execution_enabled=False)
    with (state / "training.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return dict(**heartbeat, status="TRAINING_ALREADY_RUNNING")
        job_path = root / "var/strategy-operations-integrated-v1/latest-job.json"
        job = strict_json(job_path) if job_path.exists() else {}
        if job.get("status") != "PASSED_SHADOW_ONLY" or job.get("market_session") != session:
            result = dict(**heartbeat, status="WAITING_FOR_VALIDATED_CURRENT_SESSION")
            atomic_json(state / "heartbeat.json", result)
            return result
        bundle = Path(job["job"]) / "dashboard/latest-strategy-run.json"
        seal = bundle.parent / "artifact-manifest.json"
        if file_hash(seal) != job["artifact_manifest_sha256"]:
            raise ValueError("Completed session artifact identity mismatch")
        sources = {p: file_hash(root / p) for p in SOURCES}
        key = fingerprint(dict(session=session, bundle_sha256=file_hash(bundle), sources=sources))
        last = strict_json(state / "latest.json") if (state / "latest.json").exists() else {}
        if last.get("key") == key and (last.get("status") == "COMPLETED_DAILY_RESEARCH_TRAINING" or last.get("attempt", 0) >= 2):
            if last.get("status") == "COMPLETED_DAILY_RESEARCH_TRAINING":
                assessment_path = Path(last["assessment"])
                if file_hash(assessment_path) != last["assessment_sha256"]:
                    raise ValueError("Previously trained model receipt changed")
                for name, digest in strict_json(assessment_path)["artifacts"].items():
                    if Path(name).name != name or file_hash(assessment_path.parent / name) != digest:
                        raise ValueError("Previously trained model artifact changed")
            result = dict(**heartbeat, status="ALREADY_TRAINED_OR_RETRY_LIMIT", assessment=last.get("assessment"))
            atomic_json(state / "heartbeat.json", result)
            return result
        attempt = last.get("attempt", 0) + 1 if last.get("key") == key else 1
        output = state / "runs" / (now.strftime("%Y%m%dT%H%M%S%fZ") + f"-{key[:12]}-a{attempt}")
        record = dict(**heartbeat, key=key, attempt=attempt, status="RUNNING", output=str(output))
        atomic_json(state / "latest.json", record)
        try:
            with (state / (output.name + ".log")).open("x") as log:
                (state / (output.name + ".log")).chmod(0o600)
                result = run_bounded([sys.executable, str(root / "daily_alpha_training.py"), "--bundle", str(bundle),
                                      "--output", str(output)], cwd=root, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
            if result.returncode:
                raise RuntimeError("Daily alpha worker failed; inspect private log")
            assessment = strict_json(output / "assessment.json")
            if (assessment["status"] != "COMPLETED_DAILY_RESEARCH_TRAINING"
                    or assessment["bundle_sha256"] != file_hash(bundle)
                    or assessment["source_hashes"] != sources
                    or assessment["promotion_enabled"] is not False or assessment["execution_enabled"] is not False):
                raise ValueError("Daily worker lineage/authority mismatch")
            for name, digest in assessment["artifacts"].items():
                if Path(name).name != name or file_hash(output / name) != digest:
                    raise ValueError("Daily model artifact mismatch")
            record.update(status=assessment["status"], assessment=str(output / "assessment.json"),
                          assessment_sha256=file_hash(output / "assessment.json"), trained=assessment["trained"],
                          current_forecast_status=assessment["current_forecast_status"])
        except Exception as error:
            record.update(status="FAILED", error_type=type(error).__name__)
            raise
        finally:
            record["finished_at"] = datetime.now(timezone.utc).isoformat()
            atomic_json(state / "latest.json", record)
            atomic_json(state / "heartbeat.json", record)
        return record


if __name__ == "__main__":
    install_cancellation()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if bool(args.bundle) != bool(args.output):
        parser.error("Use both --bundle and --output, or neither for a scheduler tick")
    print(json.dumps(train(args.bundle, args.output) if args.bundle else tick(), indent=2))
