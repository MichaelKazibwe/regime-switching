from pathlib import Path
from types import SimpleNamespace

import pytest

import pilot_daily
from strategy_integrity import fingerprint
from strategy_receipts import atomic_json


def test_revision_rejects_traversal_and_manifest_mismatch(tmp_path, monkeypatch):
    atomic_json(tmp_path / "latest.json", dict(revision="../outside"))
    with pytest.raises(ValueError, match="revision"):
        pilot_daily.revision_directory(tmp_path)
    atomic_json(tmp_path / "latest.json", dict(revision="a" * 64))
    monkeypatch.setattr(pilot_daily, "verify_snapshot", lambda _: {"market_session": "2026-11-13"})
    with pytest.raises(ValueError, match="mismatch"):
        pilot_daily.revision_directory(tmp_path)


def test_atomic_refresh_preserves_state_on_failure_and_rejects_rollback(monkeypatch):
    app = SimpleNamespace(payload={"training": {"market_session": "2026-11-13"}}, document="original")
    monkeypatch.setattr(pilot_daily, "revision_directory", lambda _: ("new", Path("snapshot")))
    def invalid(*_):
        raise ValueError("Bad PDF binding")
    monkeypatch.setattr(pilot_daily, "candidate", invalid)
    with pytest.raises(ValueError, match="PDF"):
        pilot_daily.refresh(app, "daily", "state", None)
    assert app.document == "original"
    monkeypatch.setattr(pilot_daily, "candidate", lambda *_: SimpleNamespace(payload={"training": {"market_session": "2026-11-12"}}))
    with pytest.raises(ValueError, match="rollback"):
        pilot_daily.refresh(app, "daily", "state", None)
    assert app.document == "original"


def test_refresh_swaps_all_bindings_and_deduplicates(monkeypatch):
    updated = SimpleNamespace(**{field: field for field in pilot_daily.FIELDS})
    updated.payload = {"training": {"market_session": "2026-11-16"}}
    app = SimpleNamespace(payload={"training": {"market_session": "2026-11-13"}})
    monkeypatch.setattr(pilot_daily, "revision_directory", lambda _: ("new", Path("snapshot")))
    calls = []
    def build(*args):
        calls.append(args)
        return updated
    monkeypatch.setattr(pilot_daily, "candidate", build)
    assert pilot_daily.refresh(app, "daily", "state", None) == "new"
    assert all(getattr(app, field) == getattr(updated, field) for field in pilot_daily.FIELDS)
    assert pilot_daily.refresh(app, "daily", "state", "new") == "new"
    assert len(calls) == 1


def test_daily_tick_waits_for_current_capture(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = Path("var/dashboard-live")
    root.mkdir(parents=True)
    atomic_json(root / "latest.json", dict(market_session="2026-11-12"))
    monkeypatch.setattr(pilot_daily, "usable_session", lambda _: __import__("pandas").Timestamp("2026-11-13"))
    result = pilot_daily.tick(Path("state"))
    assert result["status"] == "WAITING_FOR_VERIFIED_DAILY_CAPTURE"


def test_revision_binds_the_complete_manifest(tmp_path, monkeypatch):
    manifest = dict(schema_version=1, market_session="2026-11-13", files={"prices.csv": "hash"})
    revision = fingerprint(manifest)
    atomic_json(tmp_path / "latest.json", dict(revision=revision))
    monkeypatch.setattr(pilot_daily, "verify_snapshot", lambda _: manifest)
    assert pilot_daily.revision_directory(tmp_path) == (revision, tmp_path / revision)


def test_frozen_green_heartbeat_expires_without_republishing():
    from datetime import datetime, timezone
    from dashboard_runtime import age_runtime
    original=dict(scheduler=dict(status='COMPLETED',checked_at='2026-11-16T20:00:00+00:00',heartbeat_recent=True))
    result=age_runtime(original,now=datetime(2026,11,17,0,tzinfo=timezone.utc))
    assert not result['scheduler']['heartbeat_recent']
    assert not result['scheduler']['healthy']
    assert original['scheduler']['heartbeat_recent']


def test_failed_daily_publish_keeps_revision_and_writes_failure(tmp_path, monkeypatch):
    atomic_json(tmp_path/'heartbeat.json',dict(status='PUBLISHED',revision='a'*64))
    def fail(*args, **kwargs):
        raise RuntimeError('Synthetic failure')
    monkeypatch.setattr(pilot_daily,'_tick',fail)
    with pytest.raises(RuntimeError):
        pilot_daily.tick(tmp_path)
    data=__import__('json').loads((tmp_path/'heartbeat.json').read_text())
    assert data['status']=='FAILED' and data['retained_revision']=='a'*64


def test_linux_filesystem_publication_is_verified_before_pointer(tmp_path, monkeypatch):
    from research_publisher import filesystem_publish
    import research_publisher
    monkeypatch.setattr(research_publisher,'historical_weekly_session',lambda _: '2026-11-13')
    import weekly_portfolios
    source=tmp_path/'source'
    source.mkdir()
    (source/'sample').write_text('verified')
    monkeypatch.setattr(weekly_portfolios,'verify',lambda _:dict(research_id='b'*64,market_session='2026-11-13'))
    result=filesystem_publish(source,tmp_path/'published',kind='weekly')
    assert result=='b'*64
    assert (tmp_path/'published'/result/'sample').read_text()=='verified'
    assert __import__('json').loads((tmp_path/'published/latest.json').read_text())['research_id']==result
    assert filesystem_publish(source,tmp_path/'published',kind='weekly')==result


def test_readiness_distinguishes_missing_capabilities(tmp_path):
    from pilot_readiness import inspect_features
    result=inspect_features(tmp_path)
    assert not result['ready']
    assert set(result['capabilities'])=={'research_snapshot','cycle_benchmark','macro_alpha','weekly_portfolios'}
    assert not result['production_approval'] and not result['execution_enabled']
