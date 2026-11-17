import pytest

from portfolio_exposures import assess_exposures


def test_overlapping_stock_and_fund_are_aggregated_and_unknown_is_not_zero_risk():
    holding = dict(
        issuer="MSFT", country="US", currency="USD", sector="Technology", weight=1.0
    )
    records = {
        s: dict(
            as_of="2026-11-16",
            source_sha256="a" * 64,
            reviewer="Synthetic fixture",
            constituents=[holding],
        )
        for s in ["MSFT", "ETF"]
    }
    result = assess_exposures(
        {"MSFT": 0.1, "ETF": 0.2, "USD_CASH": 0.7}, records, "2026-11-17"
    )
    assert result["exposures"]["issuer"]["MSFT"] == pytest.approx(0.3)
    assert any(b["dimension"] == "issuer" for b in result["breaches"])
    missing = assess_exposures({"OTHER": 0.2, "USD_CASH": 0.8}, records, "2026-11-17")
    assert (
        missing["status"] == "REJECT_OR_REVIEW"
        and missing["covered_risky_fraction"] == 0
    )


def test_macro_mask_evaluation_preserves_temporal_purge():
    from macro_alpha_research import evaluate_masks
    from test_macro_alpha import history

    report = evaluate_masks(
        history(160),
        settings=dict(
            horizon_sessions=5,
            training_sessions=60,
            minimum_training=20,
            regularization_C=1.0,
            probability_shrink=0.25,
        ),
        minimum_outcomes=2,
    )
    assert len(report["masks"]) == 11
    assert all(r["chronology_verified"] for r in report["masks"])
    assert (
        not report["mask_selection_enabled"] and not report["prospective_qualification"]
    )


def test_migrated_forecast_keeps_original_issued_identity_and_rejects_real_changes(
    tmp_path,
):
    from macro_forecast_store import retain_issued
    from strategy_integrity import fingerprint
    from strategy_receipts import atomic_json

    prior = dict(
        market_session="2026-11-16",
        protocol_id="a" * 64,
        provenance={"capture_sha256": "b" * 64},
        prediction={"probabilities": [0.4, 0.3, 0.2, 0.1]},
    )
    prior["forecast_id"] = fingerprint(prior)
    path = tmp_path / (prior["market_session"] + "-" + prior["protocol_id"] + ".json")
    atomic_json(path, dict(issued_at="2026-11-16T23:00:00Z", forecast=prior))
    import copy

    changed = copy.deepcopy(prior)
    changed["prediction"]["probabilities"][0] += 1e-15
    changed["forecast_id"] = fingerprint(
        {k: v for k, v in changed.items() if k != "forecast_id"}
    )
    before = path.read_bytes()
    assert retain_issued(changed, tmp_path) == prior and path.read_bytes() == before
    changed["provenance"]["capture_sha256"] = "c" * 64
    changed["forecast_id"] = fingerprint(
        {k: v for k, v in changed.items() if k != "forecast_id"}
    )
    with pytest.raises(ValueError, match="migration"):
        retain_issued(changed, tmp_path)


def test_review_binds_exact_revision_and_never_authorizes_execution(tmp_path):
    from review_workflow import record_decision
    from strategy_integrity import fingerprint

    result = dict(
        recommendation_id="synthetic",
        mandate={"risk": "moderate"},
        as_of="2026-11-17",
        release={"release_id": "synthetic"},
        allocation={"USD_CASH": 1.0},
    )
    args = dict(
        reviewer="synthetic-test",
        decision="ACCEPTED_FOR_RESEARCH",
        rationale="Review research risk assumptions",
        expected_revision=fingerprint(result),
    )
    decision = record_decision(tmp_path, result, **args)
    assert (
        not decision["execution_enabled"]
        and not decision["public_recommendation_approval"]
    )
    assert record_decision(tmp_path, result, **args) == decision
    with pytest.raises(ValueError):
        record_decision(tmp_path, {**result, "as_of": "2026-11-18"}, **args)
    from strategy_receipts import atomic_json

    atomic_json(
        tmp_path / (decision["review_id"] + ".json"),
        {**decision, "execution_enabled": True},
    )
    with pytest.raises(ValueError, match="integrity"):
        record_decision(tmp_path, result, **args)


def test_encrypted_backup_restores_sqlite_and_rejects_tampering(tmp_path):
    import sqlite3

    pytest.importorskip("cryptography")
    from cryptography.exceptions import InvalidTag
    from pilot_recovery import init_key, backup, restore

    key = tmp_path / "key"
    init_key(key)
    source = tmp_path / "state"
    source.mkdir()
    with sqlite3.connect(source / "auth.sqlite3") as db:
        db.execute("CREATE TABLE users(name TEXT)")
        db.execute("INSERT INTO users VALUES('synthetic')")
    archive = tmp_path / "backup.enc"
    receipt = backup(
        {"state": source}, archive, key, quiescence_receipt="synthetic writers stopped"
    )
    assert not receipt["off_host_recovery_proven"]
    restored = restore(archive, tmp_path / "restored", key)
    assert restored["status"] == "ISOLATED_LOCAL_RESTORE_VERIFIED"
    with sqlite3.connect(tmp_path / "restored/state/auth.sqlite3") as db:
        assert db.execute("SELECT name FROM users").fetchone()[0] == "synthetic"
    data = bytearray(archive.read_bytes())
    data[-1] ^= 1
    archive.write_bytes(data)
    with pytest.raises(InvalidTag):
        restore(archive, tmp_path / "tampered", key)
    assert not (tmp_path / "tampered").exists()


def test_regime_null_validation_failure_is_not_silently_accepted():
    from productionintegration import ProductionIntegration, ProductionIntegrationError

    class Broken:
        def __len__(self):
            return 3

        def isna(self):
            raise RuntimeError("Synthetic provider failure")

    with pytest.raises(ProductionIntegrationError, match="Unable to validate"):
        ProductionIntegration._validate_regimes(Broken())


def test_legacy_harness_uses_canonical_annualization_and_module_coverage():
    import regression_suite as canonical
    import regression_suite_r3b as legacy

    assert legacy.FullSystemRegression is canonical.FullSystemRegression
    assert {"atr.py", "positionsizing.py"} <= set(legacy.REQUIRED_MODULES)


def test_legacy_harness_propagates_canonical_failure_exit(monkeypatch):
    import runpy
    import regression_suite

    monkeypatch.setattr(regression_suite, "main", lambda: 1)
    with pytest.raises(SystemExit) as result:
        runpy.run_module("regression_suite_r3b", run_name="__main__")
    assert result.value.code == 1


def test_import_cycle_audit_distinguishes_eager_and_deferred_dependencies():
    import ast
    from final_regression import imported_local_modules, detect_cycles

    tree = ast.parse("import first\ndef later():\n    import deferred\n")
    assert imported_local_modules(tree, {"first", "deferred"}) == {"first"}
    assert detect_cycles({"a": {"b"}, "b": {"a"}})


def test_synthetic_snapshot_requires_explicit_qa_mode(tmp_path, monkeypatch):
    import json
    from strategy_dashboard_server import Application
    from live_strategy_training import train

    monkeypatch.delenv("PILOT_ALLOW_SYNTHETIC_QA", raising=False)
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps({"synthetic_fixture": True}))
    with pytest.raises(ValueError, match="Synthetic"):
        Application(
            tmp_path / "missing.html",
            capture,
            tmp_path / "missing-training",
            tmp_path / "output",
        )
    with pytest.raises(ValueError, match="Synthetic"):
        train(capture, tmp_path / "training")


def test_interval_coverage_waits_for_post_issuance_execution_and_complete_horizon(
    tmp_path,
):
    from datetime import datetime, timezone
    import pandas as pd
    from forecast_coverage import issue, evaluate

    research = dict(
        research_id="synthetic",
        market_session="2026-11-13",
        candidates={
            "balanced": dict(
                allocations=[
                    dict(symbol="MSFT", weight=0.5),
                    dict(symbol="USD_CASH", weight=0.5),
                ],
                projections={
                    "4": dict(p05_return=-0.1, median_return=0.02, p95_return=0.1)
                },
            )
        },
    )
    issue(research, tmp_path, now=datetime(2026, 11, 17, 10, tzinfo=timezone.utc))
    dates = pd.bdate_range("2026-11-20", "2026-12-18")
    prices = pd.DataFrame(
        {"MSFT": 100.0 * 1.001 ** __import__("numpy").arange(len(dates))}, index=dates
    )
    early = evaluate(tmp_path, prices, as_of="2026-11-23T22:00:00Z")
    assert early["groups"][0]["pending"] == 1 and early["groups"][0]["matured"] == 0
    assert (
        evaluate(tmp_path, prices, as_of="2026-12-14T22:00:00Z")["groups"][0]["pending"]
        == 1
    )
    result = evaluate(tmp_path, prices, as_of="2026-12-18T22:00:00Z")
    assert (
        result["groups"][0]["matured"] == 1
        and result["groups"][0]["empirical_coverage"] == 1.0
    )
    assert not result["calibrated_intervals_established"]
    assert result["outcomes"][0]["realized_return"] < 0.5 * (
        prices.MSFT.iloc[-1] / prices.MSFT.iloc[0] - 1
    )


def test_point_in_time_membership_does_not_use_future_admissions_or_delistings():
    from point_in_time_universe import eligible_at, corporate_action_return

    event = dict(
        permanent_id="synthetic-id",
        symbol="SYN",
        action="ADMIT",
        effective_date="2020-01-01",
        available_at="2020-01-01T00:00:00Z",
        source="Synthetic fixture",
        source_sha256="a" * 64,
        rights_reviewed=True,
    )
    remove = {
        **event,
        "action": "REMOVE",
        "effective_date": "2021-01-01",
        "available_at": "2021-01-01T00:00:00Z",
    }
    assert eligible_at([event, remove], "2020-06-01", "2020-06-01T21:00:00Z")[
        "eligible_symbols"
    ] == ["SYN"]
    assert (
        eligible_at([event, remove], "2021-01-02", "2021-01-02T21:00:00Z")[
            "eligible_symbols"
        ]
        == []
    )
    assert corporate_action_return(100.0, 50.0, shares_per_old_share=2.0) == 0.0
    assert corporate_action_return(100.0, 0.0, cash_per_old_share=25.0) == -0.75
