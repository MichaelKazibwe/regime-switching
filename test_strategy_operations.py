from datetime import datetime, timezone
import json

import pytest

from strategy_operations import observe


@pytest.fixture
def isolated_dashboard_template(tmp_path, monkeypatch):
    template = tmp_path / "var/investor-dashboard"
    template.mkdir(parents=True)
    (template / "investor-dashboard.html").write_text("Synthetic wrapper-test template")
    monkeypatch.chdir(tmp_path)
    return template


def test_forward_cohort_selection_preserves_legacy_and_rejects_paths(tmp_path):
    from forward_cohort import database
    from strategy_receipts import atomic_json

    legacy = tmp_path / "prospective.sqlite3"
    legacy.write_bytes(b"preserve historical evidence")
    assert database(tmp_path) == legacy
    record = dict(
        database="prospective-quarantine-v2.sqlite3",
        execution_enabled=False,
        promotion_enabled=False,
    )
    atomic_json(tmp_path / "active-cohort.json", record)
    assert database(tmp_path) == tmp_path / record["database"]
    assert legacy.read_bytes() == b"preserve historical evidence"
    for name in ["../prospective-other.sqlite3", "prospective.sqlite3", "/tmp/x"]:
        atomic_json(tmp_path / "active-cohort.json", {**record, "database": name})
        with pytest.raises(ValueError):
            database(tmp_path)


def test_missing_macro_requires_exact_cash_quarantine():
    from strategy_operations import macro_availability_handled
    from copy import deepcopy

    report = dict(
        latest_macro_available=False,
        classifier=dict(latest_forecast=dict(input_valid=False, enabled=False)),
        strategies=[
            dict(
                candidate=dict(
                    status="DATA_QUARANTINE_CASH_ONLY", cash=1.0, weights={"SPY": 0.0}
                )
            )
        ],
    )
    assert macro_availability_handled(report, [{"macro_valid": False}])
    for field, value in [
        ("cash", 0.9),
        ("weights", {"SPY": 0.1}),
        ("status", "ALLOCATED"),
    ]:
        bad = deepcopy(report)
        bad["strategies"][0]["candidate"][field] = value
        assert not macro_availability_handled(bad, [{"macro_valid": False}])
    report["classifier"]["latest_forecast"]["enabled"] = True
    assert not macro_availability_handled(report, [{"macro_valid": False}])


def test_missing_overlay_omits_only_unavailable_quarter_scenarios():
    from strategy_operations import scenario_modes_valid

    macro = {"status": "UNAVAILABLE"}
    results = {str(i): {"latest_model": {}} for i in range(4)}
    payload = dict(
        plans=[{"id": "saved"}],
        context={"plans": {"saved": {"latest_macro": macro}}},
        allocation_lab={"results": results},
    )
    assert scenario_modes_valid(payload)
    results["0"]["Q1"] = {}
    assert not scenario_modes_valid(payload)
    macro.update(
        status="LATEST_AVAILABLE_FRED_CONTEXT",
        quarterly=[{"quarter": f"Q{i}"} for i in range(1, 5)],
    )
    assert not scenario_modes_valid(payload)
    for rows in results.values():
        rows.update({f"Q{i}": {} for i in range(1, 5)})
    assert scenario_modes_valid(payload)


def evidence(session="2026-10-30", sha="a" * 64, status="LOCAL_ACCEPTANCE_PASSED"):
    return {
        "schema_version": 2,
        "checks": {"verified": True},
        "status": status,
        "market_session": session,
        "report_sha256": sha,
        "artifact_manifest_sha256": "b" * 64,
    }


def test_observation_is_idempotent_and_cannot_promote(tmp_path):
    now = datetime(2026, 10, 30, 22, tzinfo=timezone.utc)
    first = observe(evidence(), tmp_path, now=now)
    again = observe(evidence(), tmp_path, now=now)
    assert first == again
    assert first["observed_sessions"] == 1
    assert not first["observation_window_complete"]
    assert not first["release_approved"] and not first["automatic_promotion"]
    assert len(list(tmp_path.glob("????-??-??.json"))) == 1


def test_observation_rejects_backfill_failure_and_rewrite(tmp_path):
    now = datetime(2026, 10, 30, 22, tzinfo=timezone.utc)
    for item in [evidence("2026-10-29"), evidence(status="BLOCKED")]:
        with pytest.raises(ValueError):
            observe(item, tmp_path, now=now)
    observe(evidence(), tmp_path, now=now)
    with pytest.raises(ValueError, match="different training run"):
        observe(evidence(sha="changed"), tmp_path, now=now)
    assert (
        json.loads((tmp_path / "2026-10-30.json").read_text())["evidence"][
            "report_sha256"
        ]
        == "a" * 64
    )


def test_daily_wrapper_records_success_and_failure(
    tmp_path, monkeypatch, isolated_dashboard_template
):
    import scheduled_strategy_validation as jobs

    import prospective_strategy_ledger

    monkeypatch.setattr(
        prospective_strategy_ledger, "advance_from_bundle", lambda *args: {}
    )
    monkeypatch.setattr(prospective_strategy_ledger, "summary", lambda *args: {})
    monkeypatch.setattr(jobs, "audit", lambda *args: evidence())
    monkeypatch.setattr(jobs, "observe", lambda *args: {"observed_sessions": 1})
    root = tmp_path / "operations"
    assert jobs.run(root)["status"] == "PASSED_SHADOW_ONLY"
    assert json.loads((root / "latest-job.json").read_text())["promotion"] == "NONE"

    def fail(*args):
        raise ValueError("Bad inputs")

    monkeypatch.setattr(jobs, "audit", fail)
    with pytest.raises(ValueError):
        jobs.run(root)
    latest = json.loads((root / "latest-job.json").read_text())
    assert latest["status"] == "FAILED" and latest["error_type"] == "ValueError"
    assert (root / "job.lock").stat().st_mode & 0o777 == 0o600


def test_refresh_passes_repository_cwd_to_bounded_worker(
    tmp_path, monkeypatch, isolated_dashboard_template
):
    import scheduled_strategy_validation as jobs
    from pathlib import Path

    class WorkerReached(Exception):
        pass

    def worker(command, *, cwd, stdout, stderr, timeout):
        assert cwd == Path(jobs.__file__).resolve().parent
        assert (cwd / command[1]).is_file()
        assert timeout == 7200
        raise WorkerReached

    monkeypatch.setattr(jobs, "run_bounded", worker)
    with pytest.raises(WorkerReached):
        jobs.run(tmp_path / "operations", refresh=True)


def test_watchdog_rejects_missing_receipt_and_failed_latest_job(tmp_path):
    from strategy_healthcheck import health

    now = datetime(2026, 10, 30, 22, tzinfo=timezone.utc)
    assert health(tmp_path, now)["status"] in {"ALERT_REQUIRED", "PENDING_SHADOW_JOB"}
    observe(evidence(), tmp_path / "observations", now=now)
    job = tmp_path / "latest-job.json"
    from strategy_receipts import atomic_json

    bundle = tmp_path / "bundle.json"
    bundle.write_text("{}")
    receipt = tmp_path / "observations" / "2026-10-30.json"
    data = json.loads(receipt.read_text())
    from strategy_integrity import file_hash

    data["evidence"]["bundle"] = str(bundle)
    data["evidence"]["bundle_sha256"] = file_hash(bundle)
    data["evidence"]["training_report_path"] = str(bundle)
    data["evidence"]["artifact_manifest_path"] = str(bundle)
    data["evidence"]["report_sha256"] = file_hash(bundle)
    data["evidence"]["artifact_manifest_sha256"] = file_hash(bundle)
    from strategy_integrity import fingerprint

    data["receipt_sha256"] = fingerprint(
        {k: v for k, v in data.items() if k != "receipt_sha256"}
    )
    atomic_json(receipt, data)
    folder = tmp_path / "runs" / "test"
    folder.mkdir(parents=True)
    status = {
        "schema_version": 2,
        "status": "PASSED_SHADOW_ONLY",
        "market_session": "2026-10-30",
        "started_at": "2026-10-30T21:00:00+00:00",
        "finished_at": "2026-10-30T21:30:00+00:00",
        "report_sha256": file_hash(bundle),
        "artifact_manifest_sha256": file_hash(bundle),
    }
    atomic_json(folder / "status.json", status)
    atomic_json(job, {"job": str(folder), **status})
    assert health(tmp_path, now)["status"] == "HEALTHY_SHADOW_JOB"
    job.write_text(json.dumps({"status": "FAILED", "market_session": "2026-10-30"}))
    assert health(tmp_path, now)["status"] == "ALERT_REQUIRED"


def test_observation_window_restarts_for_changed_source_universe_protocol(tmp_path):
    old = {**evidence(), "observation_protocol": "old-contract"}
    observe(old, tmp_path, now=datetime(2026, 10, 30, 22, tzinfo=timezone.utc))
    original = (tmp_path / "2026-10-30.json").read_bytes()
    new = {
        **evidence("2026-11-02", sha="c" * 64),
        "observation_protocol": "global-contract",
    }
    result = observe(new, tmp_path, now=datetime(2026, 11, 2, 22, tzinfo=timezone.utc))
    assert result["observed_sessions"] == 1
    assert not result["observation_window_complete"]
    assert len(list(tmp_path.glob("????-??-??.json"))) == 2
    assert (tmp_path / "2026-10-30.json").read_bytes() == original


def test_explicit_observation_stream_preserves_original_receipts(tmp_path):
    from forward_cohort import observations
    from strategy_receipts import atomic_json

    assert observations(tmp_path) == tmp_path / "observations"
    atomic_json(
        tmp_path / "active-cohort.json",
        dict(observation_directory="observations-global-v2"),
    )
    assert observations(tmp_path) == tmp_path / "observations-global-v2"
    for value in ["../observations", "/observations", "other"]:
        atomic_json(tmp_path / "active-cohort.json", dict(observation_directory=value))
        with pytest.raises(ValueError):
            observations(tmp_path)
