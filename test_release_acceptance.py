"""Release gate evidence, isolation, locking and no-delivery boundaries."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import fcntl
import json
import pytest
import release_acceptance as release
from strategy_integrity import file_hash, fingerprint
from strategy_receipts import atomic_json
from portfolio_contract import make_contract
from test_integrated_portfolio import fixture_bundle  # noqa: F401
from prospective_strategy_ledger import advance_from_bundle

NOW = datetime(2026, 10, 31, 3, tzinfo=timezone.utc)


def row(name, status="PASS", category="engineering"):
    return {"id": name, "status": status, "category": category}


def test_results_cannot_turn_missing_evidence_into_release_approval():
    s = release.summarize([row("local"), row("host", "BLOCKED", "release")])
    assert (
        s["engineering_status"] == "PASS"
        and s["exit_code"] == 2
        and not s["release_approved"]
    )
    ready = release.summarize([row("local"), row("host", "PASS", "release")])
    assert ready["status"] == "READY_FOR_OPERATOR_REVIEW" and ready["exit_code"] == 0
    assert (
        not ready["execution_enabled"]
        and not ready["email_sent"]
        and not ready["release_approved"]
    )
    assert release.summarize([row("broken", "FAIL")])["exit_code"] == 1
    with pytest.raises(ValueError):
        release.summarize([])
    with pytest.raises(ValueError):
        release.summarize([row("typo", "PASSED")])


def test_stage_exception_does_not_hide_other_failures_or_prerequisites(tmp_path):
    a = release.Audit(release.Config(output=tmp_path), tmp_path, NOW)
    a.stage("bad", lambda: (_ for _ in ()).throw(ValueError("bad snapshot")))
    called = []
    a.stage("dependent", lambda: called.append(True), requires=["bad"])
    a.stage("independent", lambda: release.result())
    a.stage("invalid_result", lambda: {"status": "UNKNOWN"})
    assert [r["status"] for r in a.rows] == [
        "FAIL",
        "BLOCKED",
        "PASS",
        "FAIL",
    ] and not called


@pytest.mark.parametrize(
    "tests,failures,errors,skips,code,expected",
    [
        (20, 0, 0, 0, 0, "PASS"),
        (0, 0, 0, 0, 0, "FAIL"),
        (20, 0, 0, 1, 0, "FAIL"),
        (20, 1, 0, 0, 0, "FAIL"),
        (20, 0, 1, 0, 0, "FAIL"),
        (20, 0, 0, 0, 1, "FAIL"),
    ],
)
def test_fresh_regression_requires_nonempty_clean_execution(
    tmp_path, tests, failures, errors, skips, code, expected
):
    a = release.Audit(release.Config(output=tmp_path), tmp_path, NOW)

    def command(*args, **kwargs):
        (tmp_path / "regression.xml").write_text(
            f'<testsuites><testsuite tests="{tests}" failures="{failures}" errors="{errors}" skipped="{skips}"/></testsuites>'
        )
        return code, {"log": "synthetic unit-test result"}

    a.command = command
    assert release.check_regression(a)["status"] == expected
    a.c.run_tests = False
    assert release.check_regression(a)["status"] == "BLOCKED"


def make_ledger(path, *, pending_override=None):
    import sqlite3

    c = make_contract(
        "portfolio",
        {"SPY": 0.5},
        "2026-10-30",
        "unit",
        basis="TEST_ONLY",
        performance="NO_ACTUAL_FORWARD_EVIDENCE",
    )
    pending = {
        "decision_session": "2026-10-30",
        "fill_session": "2026-11-02",
        "weights": {"SPY": 0.5},
        "contract_id": c["contract_id"],
    }
    if pending_override:
        pending.update(pending_override)
    e = {
        "session": "2026-10-30",
        "recorded_at": "2026-10-30T22:00:00+00:00",
        "portfolio_contracts": {"portfolio": c},
        "previous_hash": None,
        "release_approved": False,
        "states": {"portfolio": {"pending": pending}},
        "marks": {"portfolio": []},
        "return_sessions": 0,
        "report_sha256": "unit-report",
        "assessment_sha256": "unit-assessment",
    }
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY,body TEXT,sha TEXT)")
        db.execute(
            "INSERT INTO events(body,sha) VALUES(?,?)", (json.dumps(e), fingerprint(e))
        )
    return c


def test_ledger_acceptance_binds_display_and_registered_decision(tmp_path):
    p = tmp_path / "ledger.sqlite3"
    c = make_ledger(p)
    before = file_hash(p)
    assert (
        release.inspect_ledger(
            p,
            "2026-10-30",
            NOW,
            contract_map={"portfolio": c},
            report_sha256="unit-report",
        )["status"]
        == "PASS"
    )
    assert (
        release.inspect_ledger(p, "2026-10-30", NOW, report_sha256="other")["status"]
        == "BLOCKED"
    )
    assert release.inspect_ledger(p, "2026-11-02", NOW)["status"] == "BLOCKED"
    changed = {**c, "contract_id": "different"}
    assert (
        release.inspect_ledger(
            p, "2026-10-30", NOW, contract_map={"portfolio": changed}
        )["status"]
        == "BLOCKED"
    )
    assert file_hash(p) == before


@pytest.mark.parametrize(
    "override",
    [
        {"fill_session": "2026-10-30"},
        {"weights": {"SPY": 0.6}},
        {"contract_id": "not-registered"},
    ],
)
def test_even_a_resigned_ledger_cannot_hide_invalid_pending_decisions(
    tmp_path, override
):
    p = tmp_path / "ledger.sqlite3"
    make_ledger(p, pending_override=override)
    with pytest.raises(ValueError):
        release.inspect_ledger(p, "2026-10-30", NOW)


def test_browser_receipt_requires_exact_sources_inputs_and_artifacts(
    tmp_path, monkeypatch
):
    dashboard = tmp_path / "dashboard.html"
    dashboard.write_text("test")
    bundle = tmp_path / "bundle.json"
    bundle.write_text("{}")
    screenshot = tmp_path / "review.png"
    screenshot.write_bytes(b"unit fixture, not actual visual evidence")
    receipt = tmp_path / "browser.json"
    sources = {"source.py": "unit"}
    monkeypatch.setattr(release, "source_snapshot", lambda: sources)
    c = release.Config(bundle=bundle, dashboard=dashboard, browser_evidence=receipt)
    a = release.Audit(c, tmp_path, NOW)
    doc = {
        "schema_version": 1,
        "status": "PASS",
        "reviewer": "Synthetic unit test",
        "reviewed_at": (NOW - timedelta(hours=1)).isoformat(),
        "expires_at": (NOW + timedelta(days=1)).isoformat(),
        "source_snapshot_id": fingerprint(sources),
        "bundle_sha256": file_hash(bundle),
        "dashboard_sha256": file_hash(dashboard),
        "checks": dict.fromkeys(release.BROWSER_CHECKS, True),
        "artifacts": [{"path": screenshot.name, "sha256": file_hash(screenshot)}],
    }
    atomic_json(receipt, doc)
    assert release.check_browser(a)["status"] == "PASS"
    screenshot.write_bytes(b"changed")
    with pytest.raises(ValueError):
        release.check_browser(a)
    c.browser_evidence = None
    assert release.check_browser(a)["status"] == "BLOCKED"


def fake_stages(monkeypatch, protected):
    (protected.parent / "index.json").write_text(
        json.dumps({"assessment": str(protected)})
    )
    monkeypatch.setattr(
        release, "tracked_inputs", lambda c: {str(protected): file_hash(protected)}
    )

    def inputs(a):
        a.training = {"market_session": "2026-10-30"}
        a.bundle = {
            "training_report": str(protected),
            "portfolio_contracts": str(protected),
        }
        return release.result()

    monkeypatch.setattr(release, "check_inputs", inputs)
    for name in [
        "check_dashboard",
        "check_benchmark",
        "check_challengers",
        "check_recovery",
        "check_financial",
        "check_host",
        "check_product",
        "check_style",
        "check_js",
        "check_api",
        "check_runtime",
    ]:
        monkeypatch.setattr(release, name, lambda a: release.result())

    def monthly(a):
        a.monthly_summary = {"coverage": "NO_DATA"}
        return release.result()

    monkeypatch.setattr(release, "check_monthly", monthly)
    monkeypatch.setattr(
        release,
        "inspect_ledger",
        lambda *args, **kwargs: release.result(observations=1, return_sessions=0),
    )
    import strategy_healthcheck

    monkeypatch.setattr(
        strategy_healthcheck, "health", lambda *args: {"status": "HEALTHY_SHADOW_JOB"}
    )


def test_audit_writes_actionable_blockers_and_does_not_touch_inputs(
    tmp_path, monkeypatch
):
    protected = tmp_path / "input.json"
    protected.write_text("{}")
    before = file_hash(protected)
    fake_stages(monkeypatch, protected)
    c = release.Config(
        output=tmp_path / "reports",
        operations=tmp_path / "ops",
        challenger_index=tmp_path / "index.json",
        run_tests=False,
    )
    report = release.run_acceptance(c, now=NOW)
    assert report["exit_code"] == 2 and "regression" in report["blocked_checks"]
    assert (
        "completed_month_coverage" in report["blocked_checks"]
        and "prospective_observation" in report["blocked_checks"]
    )
    assert not report["release_approved"] and file_hash(protected) == before
    latest = json.loads((c.output / "latest.json").read_text())
    assert latest["report_sha256"] == file_hash(latest["report"])
    assert (Path(latest["run"]) / "acceptance.md").is_file()


def test_changed_source_blocks_an_otherwise_successful_run(tmp_path, monkeypatch):
    protected = tmp_path / "input.json"
    protected.write_text("{}")
    fake_stages(monkeypatch, protected)
    versions = iter([{"module.py": "before"}, {"module.py": "after"}])
    monkeypatch.setattr(release, "source_snapshot", lambda: next(versions))
    c = release.Config(
        output=tmp_path / "reports",
        operations=tmp_path / "ops",
        challenger_index=tmp_path / "index.json",
        run_tests=False,
    )
    report = release.run_acceptance(c, now=NOW)
    assert (
        "source_and_input_stability" in report["failed_checks"]
        and report["exit_code"] == 1
    )


def test_busy_audit_preserves_existing_latest_report(tmp_path):
    output = tmp_path / "reports"
    output.mkdir()
    latest = output / "latest.json"
    latest.write_text('{"existing":true}')
    with (output / "acceptance.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            release.run_acceptance(release.Config(output=output), now=NOW)
    assert latest.read_text() == '{"existing":true}' and not (output / "runs").exists()


def test_monthly_mime_exercise_uses_real_pdf_without_smtp(
    fixture_bundle,  # noqa: F811
    tmp_path,
    monkeypatch,
):  # noqa: F811
    _, capture = fixture_bundle
    b, e = capture("2026-10-30")
    ops = tmp_path / "ops"
    ops.mkdir()
    db = ops / "prospective.sqlite3"
    advance_from_bundle(b, db, e, now=datetime(2026, 10, 30, 22, tzinfo=timezone.utc))
    import smtplib

    monkeypatch.setattr(
        smtplib,
        "SMTP",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("No network email in acceptance")
        ),
    )
    c = release.Config(operations=ops, output=tmp_path / "out")
    c.output.mkdir()
    a = release.Audit(c, c.output, NOW)
    proof = release.check_monthly(a)
    assert (
        proof["status"] == "PASS"
        and proof["details"]["coverage"] == "NO_DATA"
        and not proof["details"]["email_sent"]
    )
    assert Path(proof["details"]["pdf"]).read_bytes().startswith(b"%PDF-")
    assert (c.output / "monthly-preview.eml").is_file()


def test_artifact_path_normalization_keeps_exact_numeric_evidence(tmp_path):
    import os

    p = tmp_path / "report.json"
    p.write_text("unit")
    relative = os.path.relpath(p)
    original = {
        "assessment": relative,
        "source_artifacts": {relative: file_hash(p)},
        "strategies": [{"return": 0.0123}],
    }
    absolute = {
        "assessment": str(p),
        "source_artifacts": {str(p): file_hash(p)},
        "strategies": [{"return": 0.0123}],
    }
    assert release.normalized_replay_evidence(
        original
    ) == release.normalized_replay_evidence(absolute)
    absolute["strategies"][0]["return"] += 1e-8
    assert release.normalized_replay_evidence(
        original
    ) != release.normalized_replay_evidence(absolute)
    original["source_artifacts"][str(p)] = file_hash(p)
    with pytest.raises(ValueError):
        release.normalized_replay_evidence(original)


def test_authenticated_api_serves_only_the_audited_payload(tmp_path):
    a = release.Audit(release.Config(output=tmp_path), tmp_path, NOW)
    a.payload = {"portfolio_contracts": {"test": "unit"}, "release_approved": False}
    assert release.check_api(a)["status"] == "PASS"


def test_missing_monthly_sender_is_a_blocker_without_attempting_delivery(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("PAPER_SMTP_HOST", raising=False)
    monkeypatch.delenv("PAPER_SMTP_SENDER", raising=False)
    a = release.Audit(release.Config(output=tmp_path), tmp_path, NOW)
    a.monthly_summary = {"coverage": "COMPLETE"}
    proof = release.check_monthly_delivery(a)
    assert proof["status"] == "BLOCKED" and "SMTP" in proof["reason"]


def test_cli_initialization_failure_is_structured_and_preserves_existing_file(
    tmp_path, capsys
):
    output = tmp_path / "not-a-directory"
    output.write_text("preserve")
    assert release.main(["--output", str(output), "--skip-tests"]) == 1
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "INITIALIZATION_FAILED" and not value["release_approved"]
    assert output.read_text() == "preserve"


@pytest.mark.parametrize(
    "version,mismatches,expected",
    [
        ("3.12.16 (synthetic compiler details)", {}, "PASS"),
        ("3.14.3 (synthetic compiler details)", {}, "BLOCKED"),
        (
            "3.12.16 (synthetic compiler details)",
            {"package": {"locked": "1", "installed": "2"}},
            "BLOCKED",
        ),
    ],
)
def test_runtime_version_compares_version_not_compiler_description(
    tmp_path, monkeypatch, version, mismatches, expected
):
    (tmp_path / "Dockerfile").write_text("FROM python:3.12.16-slim-bookworm\n")
    monkeypatch.setattr(release, "ROOT", tmp_path)
    from researchdatastore import ResearchDataStore

    monkeypatch.setattr(
        ResearchDataStore,
        "runtime_provenance",
        lambda: {"python_version": version, "dependency_mismatches": mismatches},
    )
    a = release.Audit(release.Config(output=tmp_path), tmp_path, NOW)
    assert release.check_runtime(a)["status"] == expected
