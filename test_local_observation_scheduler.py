import json

import local_observation_scheduler as scheduler


def test_current_session_skips_job_and_writes_heartbeat(tmp_path, monkeypatch):
    import dashboard_publication

    published = []
    monkeypatch.setattr(
        dashboard_publication, "publish", lambda *args: published.append(args)
    )
    monkeypatch.setattr(
        scheduler,
        "usable_session",
        lambda _: __import__("datetime").datetime(2026, 10, 30),
    )
    path = tmp_path / "var/live-observation-cycle/latest.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(dict(status="PASSED_SHADOW_ONLY", market_session="2026-10-30"))
    )
    monkeypatch.setattr(
        scheduler,
        "run_bounded",
        lambda *_, **__: (_ for _ in ()).throw(AssertionError("duplicate")),
    )
    assert scheduler.tick(tmp_path) == 0
    assert len(published) == 1
    report = json.loads(
        (tmp_path / "var/local-observation-scheduler/heartbeat.json").read_text()
    )
    assert report["status"] == "CURRENT_SESSION_ALREADY_VALIDATED"
    assert not report["execution_enabled"]


def test_job_failure_is_retained(tmp_path, monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "usable_session",
        lambda _: __import__("datetime").datetime(2026, 10, 30),
    )
    monkeypatch.setattr(
        scheduler,
        "run_bounded",
        lambda *_, **__: __import__("types").SimpleNamespace(returncode=2),
    )
    assert scheduler.tick(tmp_path) == 2
    report = json.loads(
        (tmp_path / "var/local-observation-scheduler/heartbeat.json").read_text()
    )
    assert report["status"] == "FAILED"
    assert report["exit_code"] == 2
