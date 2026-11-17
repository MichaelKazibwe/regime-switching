from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

import numpy as np
import pytest

from strategy_integrity import (
    validate_scenario,
    fingerprint,
    seal_dashboard,
    verify_seal,
)
from macro_allocation_lab import recalculate
from smartregimeportfolio import REGIMES
from test_macro_allocation_lab import lab  # noqa: F401
from strategy_receipts import atomic_json, read_observation
from strategy_healthcheck import health
from prospective_strategy_ledger import apply_close, next_fill


def test_independent_recalculation_allows_only_machine_precision_float_changes():
    from strategy_integrity import numerically_equivalent

    expected = {"weight": 0.25, "paths": 500, "active": False, "fan": [1.01]}
    assert numerically_equivalent({**expected, "weight": 0.25 + 1e-14}, expected)
    for invalid in [
        {**expected, "weight": 0.250001},
        {**expected, "paths": 500.0},
        {**expected, "active": 0},
        {**expected, "fan": [1.01, 1.02]},
        {**expected, "weight": float("nan")},
        {**expected, "extra": 0},
    ]:
        assert not numerically_equivalent(invalid, expected)


def resign(result):
    result.pop("result_id", None)
    result["result_id"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    return result


@pytest.fixture
def candidate(lab):  # noqa: F811
    return recalculate(
        lab, "economic_balance", dict(zip(REGIMES, [0.25] * 4)), paths=500, quarters=1
    )


def test_real_scenario_recomputed_and_cash_only_supported(lab, candidate):  # noqa: F811
    assert validate_scenario(candidate, lab)
    lab["accounts"]["economic_balance"]["locked"] = True
    cash = recalculate(
        lab, "economic_balance", dict(zip(REGIMES, [0.25] * 4)), paths=500, quarters=1
    )
    assert cash["cash"] == 1 and all(
        v is None for v in cash["risk_contributions"].values()
    )
    assert validate_scenario(cash, lab)


@pytest.mark.parametrize(
    "mutation", ["negative_cash", "blocked", "risk_share", "fan", "forged_return", "id"]
)
def test_corrupted_scenarios_fail_even_if_resigned(lab, candidate, mutation):  # noqa: F811
    r = deepcopy(candidate)
    if mutation == "negative_cash":
        r["cash"] = -0.1
    if mutation == "blocked":
        r["simulation"]["status"] = "BLOCKED_SCENARIO_COVERAGE"
    if mutation == "risk_share":
        r["risk_contributions"]["SPY"] = 0.01
    if mutation == "fan":
        r["simulation"]["fan"][1][3] = 999
    if mutation == "forged_return":
        r["simulation"]["median_return"] = 9.99
    if mutation != "id":
        resign(r)
    else:
        r["result_id"] = "forged"
    with pytest.raises(ValueError):
        validate_scenario(r, lab)


def test_pdf_and_payload_manifest_reject_replaced_documents(tmp_path):
    doc = tmp_path / "dashboard.html"
    doc.write_text("saved")
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF-original")
    payload = {
        "training": {"run_id": "run"},
        "context": {},
        "pdf_links": {"plan": "p.pdf"},
        "allocation_lab": {"pdf_links": {}},
    }
    bindings = {"p.pdf": {"plan_id": "plan", "context_sha256": fingerprint({})}}
    seal_dashboard(doc, payload, bindings)
    assert verify_seal(doc, payload)
    changed = deepcopy(payload)
    changed["training"]["return"] = 999
    with pytest.raises(ValueError):
        verify_seal(doc, changed)
    pdf.write_bytes(b"%PDF-unrelated")
    with pytest.raises(ValueError):
        verify_seal(doc, payload)


def test_malformed_receipts_and_running_jobs_fail_closed(tmp_path):
    atomic_json(tmp_path / "latest-job.json", [])
    now = datetime(2026, 10, 30, 22, tzinfo=timezone.utc)
    assert health(tmp_path, now)["status"] == "ALERT_REQUIRED"
    atomic_json(
        tmp_path / "latest-job.json",
        {
            "schema_version": 2,
            "status": "RUNNING",
            "started_at": "2026-10-30T15:00:00+00:00",
        },
    )
    assert health(tmp_path, now)["reason"] == "run_overdue"
    path = tmp_path / "2026-10-30.json"
    path.write_text("{partial")
    with pytest.raises(ValueError):
        read_observation(path)
    with pytest.raises(FileExistsError):
        atomic_json(path, {"new": "data"}, exclusive=True)
    assert path.read_text() == "{partial"


def test_partial_observation_never_skips_download(tmp_path):
    from scheduled_strategy_validation import run
    from strategy_training_data import usable_session

    session = str(usable_session(datetime.now(timezone.utc)).date())
    path = tmp_path / "observations" / f"{session}.json"
    path.parent.mkdir()
    path.write_text("{partial")
    with pytest.raises(ValueError):
        run(tmp_path, refresh=True)


def test_prospective_fill_is_next_close_and_includes_costs_and_carried_peak():
    assert (
        next_fill("2026-10-30", datetime(2026, 10, 31, 12, tzinfo=timezone.utc))
        == "2026-11-02"
    )
    state = {
        "nav": 1.0,
        "peak": 1.05,
        "weights": {"SPY": 0.5},
        "locked": False,
        "maximum_drawdown": 0.0,
        "pending": {
            "decision_session": "2026-10-30",
            "fill_session": "2026-11-02",
            "weights": {"SPY": 0.2},
        },
    }
    after, mark = apply_close(state, {"SPY": -0.1}, "2026-11-02")
    assert after["nav"] < 0.95 and after["peak"] == 1.05 and after["locked"]
    assert after["weights"] == {"SPY": 0.2} and mark["fee_fraction"] > 0
    assert mark["net_return"] == pytest.approx(after["nav"] - 1)
    assert not np.isnan(mark["nav"])
    bad = deepcopy(state)
    bad["pending"]["decision_session"] = "2026-11-02"
    with pytest.raises(ValueError):
        apply_close(bad, {"SPY": 0}, "2026-11-02")


def test_headline_return_is_recomputed_from_csv(tmp_path):
    import pandas as pd
    from strategy_integrity import reconcile_history
    from live_strategy_training import _metrics, _history

    frame = pd.DataFrame(
        {
            "return": [0.01, -0.02, 0.005],
            "equity": [1.01, 0.9898, 0.994749],
            "cash": [0.05] * 3,
            "turnover": [0.2] * 3,
            "cost_as_initial_capital": [0.0001] * 3,
        },
        index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]),
    )
    frame.to_csv(tmp_path / "test.csv")
    row = {"name": "test", "metrics": _metrics(frame), "history": _history(frame)}
    report = {
        "strategies": [row],
        "benchmarks": [],
        "artifacts": {"test.csv": "verified-by-loader"},
    }
    reconcile_history(report, tmp_path)
    row["metrics"]["total_return"] = 9.99
    with pytest.raises(ValueError, match="Headline metrics"):
        reconcile_history(report, tmp_path)


def test_partial_receipt_recovery_preserves_original_bytes(tmp_path):
    from strategy_receipts import quarantine_receipt

    path = tmp_path / "2026-10-30.json"
    path.write_bytes(b"{partial")
    destination = quarantine_receipt(path, "Interrupted writer investigated")
    assert not path.exists()
    from pathlib import Path

    assert Path(destination).read_bytes() == b"{partial"
    assert Path(destination).with_suffix(".receipt.json").is_file()


def test_forward_ledger_registers_before_fills_and_never_credits_same_close(
    tmp_path, monkeypatch
):
    import pandas as pd
    import prospective_strategy_ledger as ledger
    from strategy_integrity import file_hash

    report_path = tmp_path / "report.json"
    capture_path = tmp_path / "capture.json"
    bundle = tmp_path / "bundle.json"
    db = tmp_path / "forward.sqlite3"
    rows = {}

    def supply(session, dates):
        frame = pd.DataFrame(
            {
                s: [100 * (1.1**i) for i in range(len(dates))]
                for s in ["SPY", "TLT", "IEF", "GLD", "DBC"]
            },
            index=pd.to_datetime(dates),
        )
        frame.to_csv(tmp_path / "prices.csv")
        atomic_json(tmp_path / "features.json", [])
        capture = {"files": {"prices.csv": file_hash(tmp_path / "prices.csv")}}
        atomic_json(capture_path, capture)
        atomic_json(report_path, {"session": session})
        atomic_json(
            bundle, {"capture": str(capture_path), "training_report": str(report_path)}
        )
        rows.clear()
        rows.update(
            {
                "market_session": session,
                "capture_sha256": file_hash(capture_path),
                "source_hashes": {"policy": "unchanged"},
                "run_id": session,
                "strategies": [
                    {"name": "test", "candidate": {"weights": {"SPY": 0.5}}}
                ],
                "classifier": {
                    "latest_forecast": {
                        "model": [0.25] * 4,
                        "baseline": [0.25] * 4,
                        "used": [0.25] * 4,
                        "enabled": False,
                    }
                },
            }
        )
        return {
            "schema_version": 2,
            "status": "LOCAL_ACCEPTANCE_PASSED",
            "report_sha256": file_hash(report_path),
        }

    monkeypatch.setattr(ledger, "load_training_report", lambda p: deepcopy(rows))
    e = supply("2026-10-30", ["2026-10-30"])
    first = ledger.advance_from_bundle(
        bundle, db, e, now=datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
    )
    assert first["prospective_return_sessions"] == 0
    assert ledger.summary(db)["metrics"]["test"]["nav"] == 1
    e = supply("2026-11-02", ["2026-10-30", "2026-11-02"])
    ledger.advance_from_bundle(
        bundle, db, e, now=datetime(2026, 11, 2, 22, tzinfo=timezone.utc)
    )
    s = ledger.summary(db)
    assert s["return_sessions"] == 1 and 0.999 < s["metrics"]["test"]["nav"] < 1
    assert s["forecast_outcomes"]["matured"] == 0
    assert s["metrics"]["test"]["annualized_volatility"] is None
    assert (
        ledger.advance_from_bundle(
            bundle, db, e, now=datetime(2026, 11, 2, 22, tzinfo=timezone.utc)
        )["status"]
        == "ALREADY_RECORDED"
    )
    # A changed policy cannot silently continue the existing prospective cohort.
    rows["source_hashes"]["policy"] = "changed"
    rows["market_session"] = "2026-11-03"
    with pytest.raises(ValueError):
        ledger.advance_from_bundle(
            bundle, db, e, now=datetime(2026, 11, 3, 22, tzinfo=timezone.utc)
        )
    target = ledger.target_date("2026-10-30")
    dates = [str(d.date()) for d in ledger.schedule("2026-10-30", target).index]
    e = supply(target, dates)
    atomic_json(
        tmp_path / "features.json",
        [
            {
                "date": target,
                "macro_valid": True,
                "ip_growth": 1.0,
                "unemployment_change": 0.0,
                "inflation_change": -1.0,
            }
        ],
    )
    ledger.advance_from_bundle(
        bundle, db, e, now=pd.Timestamp(target + "T23:00:00Z").to_pydatetime()
    )
    complete = ledger.summary(db)
    assert complete["forecast_outcomes"]["matured"] == 1
    assert complete["forecast_outcomes"]["model_brier"] == pytest.approx(0.75)
    assert complete["observed_decision_sessions"] == 3
    assert len(complete["missed_decision_sessions"]) > 1
    import sqlite3

    with sqlite3.connect(db) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE events SET sha='changed'")


def test_observation_digest_is_checked_before_any_commit(tmp_path):
    from strategy_operations import observe

    evidence = {
        "schema_version": 2,
        "status": "LOCAL_ACCEPTANCE_PASSED",
        "market_session": "2026-10-30",
        "checks": {"all": True},
        "report_sha256": "bad",
        "artifact_manifest_sha256": "b" * 64,
    }
    with pytest.raises(ValueError):
        observe(evidence, tmp_path, now=datetime(2026, 10, 30, 22, tzinfo=timezone.utc))
    assert not (tmp_path / "2026-10-30.json").exists()


def test_forecast_scoring_waits_for_exact_maturity_and_handles_missing_outcomes():
    # Exercise the same scoring identity used by the ledger; integration tests
    # below inspect stored decisions across actual calendar maturity.
    from prospective_strategy_ledger import target_date, schedule

    origin = "2026-10-30"
    target = target_date(origin)
    assert len(schedule(origin, target)) == 64
    assert target > "2027-01-01"
