"""Synthetic fixtures for identity, forward registration and recovery boundaries."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import numpy as np
import pandas as pd
import pytest
from portfolio_contract import make_contract, validate_contract, normalized_weights
from growth_resilience import WEIGHTS, backtest
from compare_portfolio_models import rebalance_fee
from strategy_integrity import file_hash
from prospective_strategy_ledger import advance_from_bundle, summary
from strategy_monthly_report import build_strategy_summary, read_events
from monthlyreport import MonthlyReportError
from shadow_bundle_backup import create_backup, restore_backup, verify_backup


def test_contract_detects_mutation_and_preserves_performance_basis():
    c = make_contract(
        "test",
        {"SPY": 0.6},
        "2026-10-30",
        "model-v1",
        basis="TEST",
        performance="HISTORICAL_NOT_CURRENT_WEIGHTS",
    )
    assert c["weights"]["USD_CASH"] == pytest.approx(0.4)
    assert validate_contract(c)
    changed = deepcopy(c)
    changed["valuation_session"] = "2026-11-02"
    with pytest.raises(ValueError):
        validate_contract(changed)
    with pytest.raises(ValueError):
        normalized_weights({"SPY": 1.1})


def test_benchmark_costs_match_ledger_actual_risky_trades():
    daily = pd.DataFrame({"SPY": [0.0], "IEF": [0.0]})
    curve, _, turn = backtest(daily, {"SPY": 0.6, "IEF": 0.35, "USD_CASH": 0.05})
    fee = rebalance_fee(np.zeros(2), np.array([0.6, 0.35]), 0.0015)
    assert curve[0] == pytest.approx(1 - fee)
    assert turn[0] * 0.0015 == pytest.approx(fee)


@pytest.fixture
def fixture_bundle(tmp_path, monkeypatch):
    import prospective_strategy_ledger as ledger

    monkeypatch.setattr(
        ledger, "load_training_report", lambda p: json.loads(Path(p).read_text())
    )
    root = tmp_path / "inputs"
    root.mkdir()
    ext = root / "extension"
    ext.mkdir()
    symbols = [s for s in WEIGHTS if s != "USD_CASH"]

    def capture(session):
        prices = pd.DataFrame(
            {s: [100.0, 101.0, 102.0] for s in symbols},
            index=pd.to_datetime(["2026-10-29", "2026-10-30", "2026-11-02"]),
        )
        prices = prices.loc[:session]
        prices.drop(columns=["XLV"]).to_csv(root / "prices.csv")
        prices[["XLV"]].to_csv(ext / "XLV-adjusted.csv")
        (ext / "news.json").write_text("{}")
        (ext / "capture.json").write_text(
            json.dumps(
                {
                    "market_session": session,
                    "prices_sha256": file_hash(ext / "XLV-adjusted.csv"),
                }
            )
        )
        cm = {
            "price_session": session,
            "files": {"prices.csv": file_hash(root / "prices.csv")},
        }
        (root / "capture.json").write_text(json.dumps(cm))
        forecast = {
            "model": {"growth": 1.0},
            "baseline": {"growth": 1.0},
            "used": {"growth": 1.0},
            "enabled": False,
        }
        report = {
            "market_session": session,
            "run_id": "unit-" + session,
            "source_hashes": {"fixture": "stable"},
            "capture_sha256": file_hash(root / "capture.json"),
            "strategies": [
                {
                    "name": "economic_balance",
                    "candidate": {"weights": {"SPY": 0.6, "IEF": 0.35}, "cash": 0.05},
                }
            ],
            "classifier": {"latest_forecast": forecast},
            "artifacts": {},
        }
        (root / "training-report.json").write_text(json.dumps(report))
        (root / "features.json").write_text("[]")
        contracts = {
            key: make_contract(
                key,
                w,
                session,
                report["run_id"],
                basis="SYNTHETIC_TEST_ONLY",
                performance="NO_REAL_FORWARD_EVIDENCE",
            )
            for key, w in [
                ("economic_balance", {"SPY": 0.6, "IEF": 0.35}),
                ("Growth_Resilience_reference", WEIGHTS),
            ]
        }
        (root / "contracts.json").write_text(json.dumps(contracts))
        b = {
            "capture": str(root / "capture.json"),
            "training_report": str(root / "training-report.json"),
            "portfolio_contracts": str(root / "contracts.json"),
            "contract_map_sha256": file_hash(root / "contracts.json"),
            "benchmark_extension": str(ext),
        }
        (root / "bundle.json").write_text(json.dumps(b))
        e = {
            "schema_version": 2,
            "status": "LOCAL_ACCEPTANCE_PASSED",
            "report_sha256": file_hash(root / "training-report.json"),
        }
        return root / "bundle.json", e

    return root, capture


def test_cash_only_contract_advances_and_cash_mismatch_is_rejected(fixture_bundle, tmp_path):
    root, capture = fixture_bundle
    bundle, evidence = capture("2026-10-30")
    report_path = root / "training-report.json"
    report = json.loads(report_path.read_text())
    report["strategies"][0]["candidate"] = {"weights": {"SPY": 0.0}, "cash": 1.0}
    report_path.write_text(json.dumps(report))
    evidence["report_sha256"] = file_hash(report_path)
    contracts_path = root / "contracts.json"
    contracts = json.loads(contracts_path.read_text())
    contracts["economic_balance"] = make_contract(
        "economic_balance", {"USD_CASH": 1.0}, "2026-10-30", report["run_id"],
        basis="SYNTHETIC_TEST_ONLY", performance="NO_REAL_FORWARD_EVIDENCE")
    contracts_path.write_text(json.dumps(contracts))
    b = json.loads(bundle.read_text())
    b["contract_map_sha256"] = file_hash(contracts_path)
    bundle.write_text(json.dumps(b))
    now = datetime(2026, 10, 30, 22, tzinfo=timezone.utc)
    first = advance_from_bundle(bundle, tmp_path / "cash.sqlite3", evidence, now=now)
    assert first["prospective_return_sessions"] == 0
    report["strategies"][0]["candidate"]["cash"] = 0.9
    report_path.write_text(json.dumps(report))
    evidence["report_sha256"] = file_hash(report_path)
    with pytest.raises(ValueError, match="capital"):
        advance_from_bundle(bundle, tmp_path / "invalid.sqlite3", evidence, now=now)


def test_prospective_benchmark_fills_later_and_rebalances_monthly(
    fixture_bundle, tmp_path
):
    _, capture = fixture_bundle
    db = tmp_path / "ledger.sqlite3"
    b, e = capture("2026-10-30")
    first = advance_from_bundle(
        b, db, e, now=datetime(2026, 10, 30, 22, tzinfo=timezone.utc)
    )
    assert (
        first["prospective_return_sessions"] == 0
        and first["next_fill_session"] == "2026-11-02"
    )
    event = read_events(db)[-1][0]
    assert event["states"]["Growth_Resilience_reference"]["weights"] == {}
    b, e = capture("2026-11-02")
    advance_from_bundle(b, db, e, now=datetime(2026, 11, 2, 22, tzinfo=timezone.utc))
    event = read_events(db)[-1][0]
    state = event["states"]["Growth_Resilience_reference"]
    assert state["last_fill_session"] == "2026-11-02" and state["pending"] is None
    assert state["nav"] < 1 and not state["drawdown_controls"]
    assert summary(db)["return_sessions"] == 1


def test_contract_tamper_cannot_advance_ledger(fixture_bundle, tmp_path):
    root, capture = fixture_bundle
    b, e = capture("2026-10-30")
    db = tmp_path / "ledger.sqlite3"
    advance_from_bundle(b, db, e, now=datetime(2026, 10, 30, 22, tzinfo=timezone.utc))
    before = file_hash(db)
    (root / "contracts.json").write_text("{}")
    with pytest.raises(ValueError):
        advance_from_bundle(
            b, db, e, now=datetime(2026, 10, 30, 22, tzinfo=timezone.utc)
        )
    assert file_hash(db) == before


def test_monthly_report_does_not_invent_missing_boundaries(fixture_bundle, tmp_path):
    _, capture = fixture_bundle
    db = tmp_path / "ledger.sqlite3"
    b, e = capture("2026-10-30")
    advance_from_bundle(b, db, e, now=datetime(2026, 10, 30, 22, tzinfo=timezone.utc))
    b, e = capture("2026-11-02")
    advance_from_bundle(b, db, e, now=datetime(2026, 11, 2, 22, tzinfo=timezone.utc))
    r = build_strategy_summary(
        db,
        "2026-11",
        "Growth_Resilience_reference",
        now=datetime(2026, 12, 2, tzinfo=timezone.utc),
    )
    assert (
        r["coverage"] == "PARTIAL"
        and r["monthly_return"] is None
        and r["observed_sessions"] == 1
    )
    assert r["portfolio_contracts"][0]["portfolio_key"] == "Growth_Resilience_reference"
    with pytest.raises(MonthlyReportError):
        build_strategy_summary(
            db,
            "2026-11",
            "Growth_Resilience_reference",
            now=datetime(2026, 11, 3, tzinfo=timezone.utc),
        )


def test_backup_restore_and_rollback_preserve_original_chain(fixture_bundle, tmp_path):
    _, capture = fixture_bundle
    b, e = capture("2026-10-30")
    db = tmp_path / "ledger.sqlite3"
    advance_from_bundle(b, db, e, now=datetime(2026, 10, 30, 22, tzinfo=timezone.utc))
    before = file_hash(db)
    backup = tmp_path / "backup"
    restored = tmp_path / "restored"
    a = create_backup(db, b, backup)
    restore_backup(backup, restored)
    assert verify_backup(restored) == a
    with sqlite3.connect(restored / "ledger.sqlite3") as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM events")
    assert read_events(restored / "ledger.sqlite3") == read_events(db)
    item = json.loads((restored / "backup-manifest.json").read_text())["files"][1]
    (restored / item["stored"]).write_text("corrupt")
    with pytest.raises(ValueError):
        verify_backup(restored)
    assert file_hash(db) == before
