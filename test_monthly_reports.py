from dataclasses import replace
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
import fcntl
import json

import pytest
import monthlydelivery

from monthlydelivery import DeliveryLedger, Subscriber, deliver, load_subscribers, make_message
from monthlyreport import MonthlyReportError, build_summary, create_pdf, previous_month
from paperconfig import PaperRuntimeConfig
from paperstore import SQLitePaperStore
from tradingcalendar import TradingCalendar

NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


@pytest.fixture
def saved_reports(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    database = tmp_path / "state.sqlite3"
    store = SQLitePaperStore(database)

    def save(day, nav, benchmark, costs, turnover):
        close = TradingCalendar().session(day)["market_close"].isoformat()
        metric = {"portfolio_value": nav, "cash": nav-100_000, "benchmark": "SPY",
                  "benchmark_return_since_first_observation": benchmark,
                  "cumulative_return_since_start": .75, "cumulative_transaction_costs": costs,
                  "cumulative_turnover": turnover,
                  "positions_by_market_value": {"SPY": {"shares": 1000, "market_value": 100_000, "weight": 100_000/nav}}}
        decision = {"status": "APPROVED", "regime": "EXPANSION", "paper_execution": {"status": "EXECUTED", "operator_metrics": metric,
                    "orders": [{"reconciliation": {"approved": True}}]}}
        payload = {"cycle_id": day, "result": decision, "data_as_of": close}
        event = store.append_event(f"paper-cycle:{day}", "PAPER_DECISION_CYCLE", payload)
        report = {"cycle_id": day, "status": "APPROVED", "data_as_of": close, "updated_at": close,
                  "event_id": event.event_id, "event_hash": event.event_hash, "decision": decision}
        (reports / f"{day}.json").write_text(json.dumps(report))

    save("2026-08-31", 1_000_000, .20, 100, .20)
    save("2026-09-01", 1_020_000, .22, 200, .30)
    save("2026-09-15", 900_000, .21, 300, .40)
    save("2026-09-30", 1_100_000, .26, 350, .50)
    return reports, database, save


def test_monthly_returns_use_month_boundaries_and_counter_deltas(saved_reports):
    reports, database, _ = saved_reports
    summary = build_summary(reports, "2026-09", database=database, now=NOW)
    assert summary["database_verified"] is True
    assert summary["monthly_return"] == pytest.approx(.10)
    assert summary["benchmark_return"] == pytest.approx(.05)
    assert summary["active_return"] == pytest.approx(.05)
    assert summary["monthly_costs"] == 250
    assert summary["monthly_turnover"] == pytest.approx(.30)
    assert summary["observed_drawdown"] == pytest.approx(900_000 / 1_020_000 - 1)
    assert summary["coverage"] == "PARTIAL"
    assert summary["observed_sessions"] == 3
    assert summary["missing_sessions"]


def test_complete_coverage_requires_every_session_and_both_boundaries(saved_reports):
    reports, database, save = saved_reports
    calendar = TradingCalendar()
    for day in range(1,31):
        date = f"2026-09-{day:02d}"
        if calendar.is_trading_day(date) and not (reports / f"{date}.json").exists():
            save(date,1_050_000,.23,250,.35)
    summary = build_summary(reports,"2026-09",database=database,now=NOW)
    assert summary["coverage"] == "COMPLETE"
    assert summary["missing_sessions"] == []
    assert summary["observed_sessions"] == summary["expected_sessions"]


@pytest.mark.parametrize("remove", ["2026-08-31", "2026-09-30"])
def test_missing_month_boundary_never_fabricates_a_monthly_return(saved_reports, remove):
    reports, database, _ = saved_reports
    (reports / f"{remove}.json").unlink()
    summary = build_summary(reports, "2026-09", database=database, now=NOW)
    assert summary["monthly_return"] is None
    assert summary["benchmark_return"] is None
    assert summary["monthly_costs"] is None
    assert summary["coverage"] == "PARTIAL"


def test_current_month_rejected_and_scheduler_uses_new_york_month(saved_reports):
    reports, database, _ = saved_reports
    with pytest.raises(MonthlyReportError, match="completed months"):
        build_summary(reports, "2026-10", database=database, now=NOW)
    assert previous_month(datetime(2026,11,1,2,tzinfo=timezone.utc)) == "2026-09"
    assert previous_month(datetime(2026,11,1,8,tzinfo=timezone.utc)) == "2026-10"


def test_tampered_financial_report_is_rejected_before_pdf_or_email(saved_reports):
    reports, database, _ = saved_reports
    path = reports / "2026-09-30.json"
    item = json.loads(path.read_text())
    item["decision"]["paper_execution"]["operator_metrics"]["portfolio_value"] = 99_000_000
    path.write_text(json.dumps(item))
    with pytest.raises(MonthlyReportError, match="does not match database"):
        build_summary(reports, "2026-09", database=database, now=NOW)


def test_edited_cycle_status_does_not_qualify_as_verified_operational_history(saved_reports):
    reports, database, _ = saved_reports
    path = reports / "2026-09-30.json"
    item = json.loads(path.read_text())
    item["status"] = "REJECTED"
    path.write_text(json.dumps(item))
    with pytest.raises(MonthlyReportError, match="does not match database"):
        build_summary(reports, "2026-09", database=database, now=NOW)


def test_no_data_report_has_no_invented_financial_results(tmp_path):
    summary = build_summary(tmp_path, "2026-09", now=NOW)
    assert summary["coverage"] == "NO_DATA"
    assert summary["closing_nav"] is None
    assert summary["monthly_return"] is None
    assert summary["nav_history"] == []


@pytest.fixture
def package(saved_reports, tmp_path):
    reports, database, _ = saved_reports
    summary = build_summary(reports, "2026-09", database=database, now=NOW)
    user = Subscriber("michael", "Michael Kazibwe", "michael@example.com", "2026-01", True)
    artifact = create_pdf(summary,user_id=user.user_id,name=user.name,output_directory=tmp_path / "pdfs")
    config = PaperRuntimeConfig(smtp_host="smtp.example.com",smtp_sender="reports@example.com",
                               smtp_recipient="operator@example.com",smtp_username="sender",smtp_password="test-secret")
    ledger = DeliveryLedger(tmp_path / "delivery.sqlite3")
    return summary, user, artifact, config, ledger


def test_pdf_is_immutable_and_attachment_is_personal_and_integrity_checked(package, tmp_path):
    summary, user, artifact, config, _ = package
    assert artifact["pdf"].read_bytes().startswith(b"%PDF-")
    assert create_pdf(summary,user_id=user.user_id,name=user.name,output_directory=tmp_path / "pdfs")["pdf_sha256"] == artifact["pdf_sha256"]
    message = BytesParser(policy=policy.default).parsebytes(make_message(config,user,summary,artifact).as_bytes())
    assert str(message["To"]) == user.email
    assert message["Bcc"] is None
    attachments = list(message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == "application/pdf"
    assert attachments[0].get_payload(decode=True) == artifact["pdf"].read_bytes()
    with pytest.raises(MonthlyReportError, match="does not belong"):
        make_message(config,replace(user,user_id="another-user"),summary,artifact)
    artifact["pdf"].write_bytes(b"tampered")
    with pytest.raises(MonthlyReportError, match="integrity"):
        make_message(config,user,summary,artifact)


class FakeSMTP:
    messages = []
    ambiguous = False
    quit_fails = False

    def __init__(self, *args, **kwargs):
        pass

    def starttls(self, **kwargs):
        pass

    def login(self, *args):
        pass

    def send_message(self, message, **kwargs):
        self.messages.append((message, kwargs))
        if self.ambiguous:
            raise OSError("connection lost after DATA")
        return {}

    def quit(self):
        if self.quit_fails:
            raise OSError("QUIT failed after acceptance")

    def close(self):
        pass


def test_sent_delivery_is_not_repeated_even_if_quit_fails(package, monkeypatch):
    summary, user, artifact, config, ledger = package
    monkeypatch.setattr(FakeSMTP,"messages",[])
    monkeypatch.setattr(FakeSMTP,"quit_fails",True)
    assert deliver(config,user,summary,artifact,ledger,smtp_factory=FakeSMTP)["status"] == "SENT"
    assert deliver(config,user,summary,artifact,ledger,smtp_factory=FakeSMTP)["status"] == "ALREADY_SENT"
    assert len(FakeSMTP.messages) == 1
    assert FakeSMTP.messages[0][1]["to_addrs"] == [user.email]


def test_ambiguous_delivery_blocks_retry_until_operator_resolution(package, monkeypatch):
    summary, user, artifact, config, ledger = package
    monkeypatch.setattr(FakeSMTP,"messages",[])
    monkeypatch.setattr(FakeSMTP,"ambiguous",True)
    assert deliver(config,user,summary,artifact,ledger,smtp_factory=FakeSMTP)["status"] == "UNKNOWN"
    assert deliver(config,user,summary,artifact,ledger,retry_failed=True,smtp_factory=FakeSMTP)["status"] == "NEEDS_REVIEW"
    assert len(FakeSMTP.messages) == 1
    ledger.resolve("paper-default","2026-09",user.user_id,"FAILED","Operator","Provider logs confirm the message was not accepted")
    monkeypatch.setattr(FakeSMTP,"ambiguous",False)
    assert deliver(config,user,summary,artifact,ledger,retry_failed=True,smtp_factory=FakeSMTP)["status"] == "SENT"


def test_inactive_and_unverified_users_are_not_sent_reports(package):
    summary, user, artifact, config, ledger = package
    assert deliver(config,replace(user,active=False),summary,artifact,ledger)["status"] == "SKIPPED_NOT_ENROLLED"
    with pytest.raises(MonthlyReportError, match="verified source"):
        deliver(config,user,{**summary,"database_verified":False},artifact,ledger)


def test_connection_failure_is_safe_to_retry_only_when_requested(package):
    summary, user, artifact, config, ledger = package

    def fail_connect(*args,**kwargs):
        raise OSError("Connection unavailable")

    assert deliver(config,user,summary,artifact,ledger,smtp_factory=fail_connect)["status"] == "FAILED"
    assert deliver(config,user,summary,artifact,ledger,smtp_factory=FakeSMTP)["status"] == "FAILED_PREVIOUSLY"
    assert deliver(config,user,summary,artifact,ledger,retry_failed=True,smtp_factory=FakeSMTP)["status"] == "SENT"


def test_generate_only_cli_never_delivers_and_worker_lock_blocks_overlap(saved_reports, package, tmp_path, monkeypatch):
    reports, database, _ = saved_reports
    _, user, _, config, ledger = package
    config = replace(config,state_database=database,report_directory=reports)
    monkeypatch.setattr(monthlydelivery.PaperRuntimeConfig,"from_env",lambda:config)
    monkeypatch.setattr(monthlydelivery,"deliver",lambda *args,**kwargs:pytest.fail("Generate-only must not deliver"))
    recipients=tmp_path / "users.json"
    recipients.write_text(json.dumps({"schema_version":1,"users":[user.__dict__]}))
    output=tmp_path / "generated"
    args=["--recipients",str(recipients),"--output",str(output),"run","--month","2026-09"]
    assert monthlydelivery.main(args) == 0
    result=json.loads((output / "last-run.json").read_text())
    assert result["recipients"][0]["status"] == "GENERATED"
    with database.with_suffix(".sqlite3.lock").open("a+") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert monthlydelivery.main(args) == 2
        assert json.loads((output / "last-run.json").read_text())["status"] == "BLOCKED"


def test_recipient_config_rejects_multiple_addresses_and_duplicates(tmp_path):
    path = tmp_path / "users.json"
    user = {"user_id":"one","name":"Example","email":"one@example.com","active":True,"start_month":"2026-01"}
    path.write_text(json.dumps({"schema_version":1,"users":[user,{**user,"user_id":"two"}]}))
    with pytest.raises(MonthlyReportError,match="Duplicate"):
        load_subscribers(path)
    path.write_text(json.dumps({"schema_version":1,"users":[{**user,"email":"one@example.com,two@example.com"}]}))
    with pytest.raises(MonthlyReportError,match="exactly one"):
        load_subscribers(path)


def test_monthly_macro_context_excludes_releases_after_report_period(saved_reports):
    from test_investor_analytics import features

    reports, database, _ = saved_reports
    rows=features()
    last=rows[-1].copy()
    last.update(date='2026-09-30',as_of='2026-09-30T20:00:00+00:00',observation_dates={})
    future=last.copy()
    future.update(date='2026-10-01',as_of='2026-10-01T20:00:00+00:00',ip_growth=999)
    summary=build_summary(reports,'2026-09',database=database,now=NOW,macro_features=[last,future])
    context=summary['macro_context']
    assert context['feature_date']=='2026-09-30'
    assert context['indicators'][0]['value']!=999
    assert context['quarterly']==[]
