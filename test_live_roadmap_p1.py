from copy import deepcopy
from datetime import timedelta
import json
import sqlite3

import pytest

from test_managed_execution import system, NOW, adapter, prepare  # noqa: F401
from writer_fencing import claim, renew, FencedOut
from operational_escalation import EscalationStore
from operational_metrics import MetricStore
from execution_degradation import analyze
from managed_disaster_recovery import backup, restore
from strategy_integrity import file_hash


def test_epoch_takeover_denies_stale_owner_and_wrong_account(system):  # noqa: F811
    e, _, scope, *_ = system
    old = claim(e.store, scope, "worker-a", now=NOW, seconds=1)
    with pytest.raises(FencedOut):
        claim(e.store, scope, "worker-b", now=NOW)
    new = claim(e.store, scope, "worker-b", now=NOW + timedelta(seconds=2))
    assert new.epoch == old.epoch + 1
    with e.store.connect() as db:
        with pytest.raises(FencedOut):
            old.check(db, scope, NOW + timedelta(seconds=2))
        new.check(db, scope, NOW + timedelta(seconds=2))
    with pytest.raises(FencedOut):
        renew(e.store, old, scope, now=NOW + timedelta(seconds=2))


def test_inflight_dispatch_blocks_takeover_until_quarantined(system):  # noqa: F811
    e, _, a, *_ = system
    prepare(system)
    old = claim(e.store, a, "worker-a", now=NOW, seconds=1)
    with e.store.connect() as db:
        db.execute("UPDATE outbox SET state='DISPATCHING'")
    with pytest.raises(FencedOut, match="ambiguous"):
        claim(e.store, a, "worker-b", now=NOW + timedelta(seconds=2))
    e.recover()
    assert (
        claim(e.store, a, "worker-b", now=NOW + timedelta(seconds=2)).epoch
        == old.epoch + 1
    )


def test_lease_expiring_during_send_quarantines_ack_instead_of_resubmitting(
    system,  # noqa: F811
    monkeypatch,  # noqa: F811
):  # noqa: F811
    e, t, a, c, q, p, sig = system
    e.simulation_only = False
    monkeypatch.setattr(e, "_production_risk", lambda *_: "synthetic-risk-boundary")
    monkeypatch.setattr(e, "_portfolio_envelope", lambda *_: None)
    e.writer_lease = claim(e.store, a, "worker", now=NOW, seconds=1)
    assert e.prepare(t, a, "one", c, q, "2", p, sig) == "PAPER_QUEUED"
    calls = []

    def send(*_):
        calls.append(True)
        e.clock = lambda: NOW + timedelta(seconds=2)
        return [dict(order_id="99")]

    with pytest.raises(FencedOut):
        e.dispatch(t, a, "one", adapter(send))
    assert calls == [True]
    with e.store.connect() as db:
        assert db.execute("SELECT state FROM outbox").fetchone()[0] == "UNKNOWN"
        assert db.execute("SELECT frozen FROM accounts").fetchone()[0] == 1


def test_delivery_ambiguity_never_retries_same_notification(tmp_path):
    alerts = EscalationStore(tmp_path / "alerts.sqlite3")
    alerts.reconcile(["SLO_BREACH"], now=NOW)
    assert alerts.dispatch(now=NOW)["status"].startswith("BLOCKED")
    calls = []

    def lost(_):
        calls.append(True)
        raise TimeoutError("may already have been accepted")

    alerts.dispatch(lost, now=NOW)
    alerts.dispatch(lost, now=NOW + timedelta(seconds=1))
    assert calls == [True]
    with alerts.connect() as db:
        assert db.execute("SELECT state FROM delivery").fetchone()[0] == "UNKNOWN"
    alerts.dispatch(
        lambda record: calls.append(record["level"]) or dict(accepted=True),
        now=NOW + timedelta(minutes=16),
    )
    assert calls == [True, 1]
    with alerts.connect() as db:
        incident = db.execute("SELECT id FROM incidents").fetchone()[0]
    alerts.acknowledge(incident, "unit-operator", now=NOW + timedelta(minutes=17))
    alerts.dispatch(lost, now=NOW + timedelta(minutes=18))
    assert calls == [True, 1]


def test_metrics_are_retained_and_conflicting_samples_rejected(tmp_path):
    m = MetricStore(tmp_path / "metrics.sqlite3")
    m.record(NOW, {"regime_slo_breach": 1}, "event", {"status": "breach"})
    m.record(NOW, {"regime_slo_breach": 1}, "event", {"status": "breach"})
    assert m.prometheus() == "regime_slo_breach 1\n"
    with pytest.raises(ValueError):
        m.record(NOW, {"regime_slo_breach": 0}, "event", {"status": "healthy"})


@pytest.fixture
def execution_file(tmp_path):
    raw = tmp_path / "broker.csv"
    raw.write_text("synthetic broker fixture only")
    o = dict(
        tenant="test",
        account="paper",
        order_id="buy",
        currency="USD",
        side="BUY",
        quantity=10,
        arrival_price=100,
        arrival_at=(NOW - timedelta(seconds=5)).isoformat(),
        submitted_at=(NOW - timedelta(seconds=4)).isoformat(),
        ack_at=(NOW - timedelta(seconds=3)).isoformat(),
        modeled_cost_bps=15,
    )
    fills = [
        dict(
            tenant="test",
            account="paper",
            order_id="buy",
            fill_id=str(i),
            currency="USD",
            quantity=5,
            price=price,
            fee=1,
            executed_at=(NOW - timedelta(seconds=2)).isoformat(),
            received_at=(NOW - timedelta(seconds=1)).isoformat(),
        )
        for i, price in enumerate((99, 101))
    ]
    d = dict(
        mode="BROKER_PAPER",
        verified=True,
        reviewer="synthetic-test-review",
        reconciliation_status="MATCHED",
        as_of=NOW.isoformat(),
        raw_files=[dict(file=raw.name, sha256=file_hash(raw))],
        orders=[o],
        fills=fills,
    )
    path = tmp_path / "execution.json"
    path.write_text(json.dumps(d))
    return path, d


def test_shortfall_includes_fees_and_deduplicates_execution_ids(execution_file):
    path, d = execution_file
    d["fills"].append(deepcopy(d["fills"][0]))
    path.write_text(json.dumps(d))
    result = analyze(path, now=NOW)
    assert result["rows"][0]["vwap"] == 100
    assert result["rows"][0]["shortfall_bps"] == 20
    assert result["rows"][0]["fill_ratio"] == 1
    assert not result["live_performance_verified"]


def test_conflicting_or_future_fills_are_denied(execution_file):
    path, d = execution_file
    f = deepcopy(d["fills"][0])
    f["price"] = 102
    d["fills"].append(f)
    path.write_text(json.dumps(d))
    with pytest.raises(ValueError, match="Conflicting"):
        analyze(path, now=NOW)


def test_missing_broker_records_do_not_become_zero_shortfall():
    result = analyze(now=NOW)
    assert result["status"].startswith("UNAVAILABLE") and "currencies" not in result


def test_managed_restore_preserves_journals_and_invalidates_authority(system, tmp_path):  # noqa: F811
    e, _, scope, *_ = system
    lease = claim(e.store, scope, "worker", now=NOW)
    with e.store.connect() as db:
        db.execute("UPDATE accounts SET frozen=0")
    before = file_hash(e.store.path)
    backup(e.store.path, tmp_path / "backup")
    proof = restore(tmp_path / "backup", tmp_path / "restore")
    assert proof["all_accounts_frozen"] and proof["writer_epochs_invalidated"]
    assert file_hash(e.store.path) == before
    with sqlite3.connect(tmp_path / "restore/managed.sqlite3") as db:
        assert db.execute("SELECT frozen FROM accounts").fetchone()[0] == 1
        with pytest.raises(FencedOut):
            lease.check(db, scope, NOW)


def test_short_history_risk_and_calibration_remain_unavailable(monkeypatch):
    import strategy_degradation as monitor

    event = dict(
        session="2026-11-02",
        states={"test": dict(nav=1.0, maximum_drawdown=0.0)},
        marks={"test": []},
        forecasts=[],
    )
    monkeypatch.setattr(monitor, "read_events", lambda _: [(event, "head")])
    result = monitor.analyze("unused")
    assert result["strategies"]["test"]["realized_annual_volatility"] is None
    assert result["calibration"]["status"] == "NO_REGISTERED_PROBABILISTIC_FORECASTS"
    assert result["automatic_refit"] is False and result["automatic_promotion"] is False


def test_future_risk_forecast_is_not_used_as_prior_prediction(monkeypatch):
    import strategy_degradation as monitor

    event = dict(
        session="2026-11-02",
        states={"test": dict(nav=1.0, maximum_drawdown=0.0)},
        marks={"test": []},
        forecasts=[],
    )
    monkeypatch.setattr(monitor, "read_events", lambda _: [(event, "head")])
    with pytest.raises(ValueError, match="precede"):
        monitor.analyze(
            "unused",
            risk_forecasts=[
                dict(
                    strategy="test",
                    issued_at="2026-11-03T10:00:00+00:00",
                    first_session="2026-11-02",
                    last_session="2026-11-30",
                    sessions=21,
                    id="bad",
                )
            ],
        )


def test_model_review_cannot_apply_refit_or_grant_live_authority(tmp_path):
    from operational_model_review import record

    (tmp_path / "latest.json").write_text(json.dumps(dict(degradation={})))
    with pytest.raises(ValueError):
        record(tmp_path, "APPROVE_LIVE", "not permitted")
    with pytest.raises(ValueError):
        record(tmp_path, "REQUEST_REFIT", "reviewed")
    request = record(
        tmp_path,
        "REQUEST_REFIT",
        "synthetic unit request",
        candidate_version="isolated-test-v2",
    )
    assert not request["applied_to_trading"] and not request["release_approved"]
