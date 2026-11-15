import json

import pytest

import paper_admin
import paper_service
from paperconfig import PaperRuntimeConfig
from paperstore import PaperStoreError


def test_alert_test_requires_smtp_and_does_not_create_state(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(paper_admin.PaperRuntimeConfig, "from_env", lambda: PaperRuntimeConfig())
    assert paper_admin.main(["alert-test"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "BLOCKED"
    assert result["human_receipt_confirmed"] is False
    assert not (tmp_path / "var").exists()


def test_alert_test_reports_transport_result_without_claiming_human_receipt(monkeypatch, capsys):
    monkeypatch.setattr(paper_admin.PaperRuntimeConfig, "from_env", lambda: PaperRuntimeConfig())
    monkeypatch.setattr(paper_admin, "notify_operator", lambda *args, **kwargs: {"delivered": True, "status": "SENT"})
    assert paper_admin.main(["alert-test"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "SENT"
    assert result["human_receipt_confirmed"] is False


def test_verify_does_not_create_missing_database(tmp_path):
    database = tmp_path / "does-not-exist.sqlite3"
    with pytest.raises(PaperStoreError, match="does not exist"):
        paper_admin.main(["--database", str(database), "verify"])
    assert not database.exists()


def test_scheduled_cli_skips_non_trading_day(monkeypatch, capsys):
    class HolidayCalendar:
        def is_trading_day(self, _):
            return False

    monkeypatch.setattr(paper_service, "TradingCalendar", HolidayCalendar)
    monkeypatch.setattr(paper_service.PaperRuntimeConfig, "from_env", lambda: PaperRuntimeConfig())
    monkeypatch.setattr(paper_service, "run_once", lambda *_: pytest.fail("Holiday must not run a decision"))
    assert paper_service.main([]) == 0
    assert json.loads(capsys.readouterr().out)["reason"] == "NYSE_NON_TRADING_DAY"
