from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import daily_alpha_training as daily
from strategy_integrity import file_hash
from strategy_receipts import atomic_json
from test_four_macro_strategies import features


def test_daily_fit_uses_only_mature_labels_and_serializable_parameters():
    rows = features(180)
    for row in rows:
        row["macro_valid"] = True
    settings = dict(horizon_sessions=5, training_sessions=120, minimum_training=20)
    result = daily.fit_latest(rows, settings, dict(regularization=.1, shrink=.5))
    meta = result["model_parameters"]
    assert result["trained"] and meta["last_training_label_date"] < rows[-1]["date"]
    assert sum(result["research_probabilities"]) == pytest.approx(1)
    x = np.array([rows[-1][k] for k in daily.FEATURES])
    z = (x - meta["scaler_mean"]) / meta["scaler_scale"]
    logits = np.array(meta["coefficients"]) @ z + meta["intercepts"]
    if len(meta["classes"]) == 2:
        learned = np.array([1 / (1 + np.exp(logits[0])), 1 / (1 + np.exp(-logits[0]))])
    else:
        learned = np.exp(logits - max(logits))
        learned /= learned.sum()
    probability = np.array(result["baseline"]) * .5
    probability[meta["classes"]] += .5 * learned
    assert np.allclose(probability, result["research_probabilities"])
    assert result["activation_enabled"] is False


def test_missing_current_macro_does_not_invent_alpha():
    rows = features(180)
    rows[-1]["macro_valid"] = False
    result = daily.fit_latest(rows, dict(horizon_sessions=5, training_sessions=120, minimum_training=20),
                              dict(regularization=.1, shrink=.5))
    assert result["research_probabilities"] is None
    assert result["current_forecast_status"] == "UNAVAILABLE_CURRENT_MACRO_INPUTS"


def fixture_job(tmp_path, monkeypatch):
    monkeypatch.setattr(daily, "usable_session", lambda _: pd.Timestamp("2026-11-13"))
    monkeypatch.setattr(daily, "SOURCES", ())
    job = tmp_path / "job/dashboard"
    job.mkdir(parents=True)
    atomic_json(job / "artifact-manifest.json", {})
    atomic_json(job / "latest-strategy-run.json", {})
    atomic_json(tmp_path / "var/strategy-operations-integrated-v1/latest-job.json",
                dict(status="PASSED_SHADOW_ONLY", market_session="2026-11-13", job=str(job.parent),
                     artifact_manifest_sha256=file_hash(job / "artifact-manifest.json")))
    return datetime(2026, 11, 15, tzinfo=timezone.utc)


def test_scheduler_waits_for_fresh_validated_data(tmp_path, monkeypatch):
    monkeypatch.setattr(daily, "usable_session", lambda _: pd.Timestamp("2026-11-13"))
    monkeypatch.setattr(daily, "run_bounded", lambda *a, **kw: pytest.fail("Stale inputs must not start training"))
    assert daily.tick(tmp_path)["status"] == "WAITING_FOR_VALIDATED_CURRENT_SESSION"


def test_scheduler_trains_once_per_source_bound_session(tmp_path, monkeypatch):
    now = fixture_job(tmp_path, monkeypatch)
    calls = []
    def worker(command, **kwargs):
        calls.append(command)
        output = Path(command[-1])
        output.mkdir(parents=True)
        atomic_json(output / "model.json", {})
        atomic_json(output / "assessment.json", dict(status="COMPLETED_DAILY_RESEARCH_TRAINING",
                    bundle_sha256=file_hash(command[-3]), source_hashes={}, promotion_enabled=False,
                    execution_enabled=False, trained=True, current_forecast_status="RESEARCH_ONLY",
                    artifacts={"model.json": file_hash(output / "model.json")}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(daily, "run_bounded", worker)
    assert daily.tick(tmp_path, now=now)["status"] == "COMPLETED_DAILY_RESEARCH_TRAINING"
    assert daily.tick(tmp_path, now=now)["status"] == "ALREADY_TRAINED_OR_RETRY_LIMIT"
    assert len(calls) == 1


def test_scheduler_limits_failed_attempts(tmp_path, monkeypatch):
    now = fixture_job(tmp_path, monkeypatch)
    monkeypatch.setattr(daily, "run_bounded", lambda *a, **kw: SimpleNamespace(returncode=1))
    for _ in range(2):
        with pytest.raises(RuntimeError):
            daily.tick(tmp_path, now=now)
    assert daily.tick(tmp_path, now=now)["status"] == "ALREADY_TRAINED_OR_RETRY_LIMIT"
