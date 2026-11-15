import json

import pytest

from productstate import ProductState, account_lock


def result(key="a" * 64, peak=1.2):
    return dict(
        recommendation_id=key,
        mandate=dict(base_currency="USD"),
        risk_state=dict(peak=peak),
    )


def test_crash_during_export_recovers_committed_result_and_peak(tmp_path, monkeypatch):
    import productstate

    original = productstate.private_write
    with ProductState(tmp_path) as store:
        monkeypatch.setattr(
            productstate,
            "private_write",
            lambda *_: (_ for _ in ()).throw(OSError("disk full")),
        )
        with pytest.raises(OSError, match="disk full"):
            store.commit(result())
    monkeypatch.setattr(productstate, "private_write", original)
    with ProductState(tmp_path) as recovered:
        assert recovered.state()["state"]["peak"] == 1.2
        recovered.recover()
    assert json.loads((tmp_path / "state.json").read_text())["state"]["peak"] == 1.2
    assert json.loads((tmp_path / ("a" * 64 + ".json")).read_text()) == result()


def test_failed_database_commit_cannot_advance_risk_state(tmp_path):
    import sqlite3

    with ProductState(tmp_path) as store:
        store.commit(result())
        store.db.execute(
            "CREATE TRIGGER reject_update BEFORE INSERT ON account BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
        )
        store.db.commit()
        with pytest.raises(sqlite3.IntegrityError):
            store.commit(result("b" * 64, 2.0))
        assert store.get("b" * 64) is None
        assert store.state()["state"]["peak"] == 1.2


def test_concurrent_planner_cannot_take_account_lock(tmp_path):
    with account_lock(tmp_path / "state.json"):
        with pytest.raises(ValueError, match="already active"):
            with account_lock(tmp_path / "state.json"):
                pytest.fail("Second writer acquired account")


def test_database_and_exports_are_private_and_account_scoped(tmp_path):
    with ProductState(tmp_path / "one") as first:
        first.commit(result())
    with ProductState(tmp_path / "two") as second:
        assert second.state() is None and second.get("a" * 64) is None
    for path in (tmp_path / "one").iterdir():
        assert path.stat().st_mode & 0o777 == 0o600


def test_symlink_database_is_rejected(tmp_path):
    target = tmp_path / "target"
    target.write_text("private")
    (tmp_path / "product-state.sqlite3").symlink_to(target)
    with pytest.raises(ValueError, match="Regular"):
        ProductState(tmp_path)
    assert target.read_text() == "private"
