from copy import deepcopy
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from economic_evidence import verify
from stress_budget_challenger import (
    allocate,
    checks,
    shock_matrix,
    trade_decision,
    reviewed_unlock,
)
from strategy_integrity import strict_json, fingerprint


@pytest.fixture
def cfg():
    return strict_json("research/stress_budget_challenger_v2.json")


@pytest.fixture
def market():
    symbols = ["SPY", "VEA", "IEF", "TIP", "GLD", "DBC", "SGOV"]
    rng = np.random.default_rng(42)
    values = rng.normal(0, 0.005, (252, len(symbols)))
    values[:, -1] *= 0.02
    h = pd.DataFrame(
        values, index=pd.bdate_range("2023-01-01", periods=252), columns=symbols
    )
    return h, h.cov().to_numpy() * 252


def test_strict_missing_macro_is_cash_and_degraded_is_bounded(cfg, market):
    h, cov = market
    strict = allocate(h, cov, cfg, macro_valid=False)
    assert strict["cash"] == 1 and strict["reason"] == "STRICT_MACRO_QUARANTINE"
    degraded = allocate(h, cov, cfg, macro_valid=False, market_fallback=True)
    if degraded["status"].startswith("BLOCKED"):
        assert degraded["cash"] == 1
    else:
        assert degraded["mode"] == "MARKET_ONLY_DEGRADED"
        assert sum(degraded["weights"].values()) <= 0.1500001
        assert max(degraded["validation"]["shock_losses"]) <= 0.0150001
        assert degraded["validation"]["passed"]


def test_new_solver_cannot_relax_original_caps_or_promote(cfg, market):
    h, cov = market
    r = allocate(h, cov, cfg)
    assert r["cash"] >= 0.05 and not r["execution_enabled"]
    if r["status"] == "UNAPPROVED_STRESS_BUDGET_SHADOW":
        assert r["validation"]["passed"] and not r["promotion_enabled"]
        assert max(r["weights"].values()) <= 0.245001
        assert (
            max(x for x in r["validation"]["risk_shares"].values() if x is not None)
            <= 0.250001
        )
    with pytest.raises(ValueError):
        shock_matrix(["ALLW"])
    with pytest.raises(ValueError):
        allocate(h.iloc[:-1], cov, cfg)


def test_aggregate_shock_rejection_despite_asset_caps(cfg, market):
    h, cov = market
    w = np.array([0.2, 0.2, 0.2, 0.1, 0.1, 0.1, 0])
    result = checks(w, cov, list(h), cfg)
    assert result["checks"]["capital"]
    assert not result["checks"]["shock_budget"]
    assert not result["passed"]


def test_huge_cost_hurdle_never_blocks_protective_exit(cfg, market):
    h, cov = market
    cfg["cost_hurdle_multiplier"] = 1e9
    current = {"SPY": 0.2}
    target = allocate(h, cov, cfg, macro_valid=False)
    decision = trade_decision(
        current, target, cov, h, cfg, macro_valid=False, sessions_since_trade=0
    )
    assert decision["urgent"] and decision["trade"]
    assert decision["reason"] == "PROTECTIVE_OVERRIDE"


def test_cost_rejection_of_unnecessary_discretionary_trade(cfg, market):
    h, cov = market
    target = {
        "status": "UNAPPROVED_STRESS_BUDGET_SHADOW",
        "weights": {"SPY": 0.01},
        "expected_returns": {"SPY": 0.0},
    }
    d = trade_decision({}, target, cov, h, cfg, sessions_since_trade=100)
    assert not d["trade"] and not d["urgent"]


def test_review_cannot_reset_peak_ignore_lock_or_be_reused(cfg):
    now = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
    state = {"nav": 0.99, "peak": 1.0, "locked": True}
    receipt = {
        "status": "APPROVED_SHADOW_RECOVERY",
        "cohort": "test",
        "session": "2026-10-30",
        "state_sha256": fingerprint(state),
        "config_sha256": fingerprint(cfg),
        "reviewer": "unit-test reviewer",
        "evidence_sha256": "a" * 64,
        "reuse_allowed": False,
        "recorded_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "valid_market_sessions": 10,
    }
    result = reviewed_unlock(
        state, receipt, cohort="test", session="2026-10-30", config=cfg, now=now
    )
    assert not result["locked"] and result["peak"] == 1 and result["nav"] == 0.99
    assert result["recovery_exposure_ceiling"] == 0.1
    bad = deepcopy(state)
    bad["nav"] = 0.95
    receipt["state_sha256"] = fingerprint(bad)
    with pytest.raises(ValueError):
        reviewed_unlock(
            bad, receipt, cohort="test", session="2026-10-30", config=cfg, now=now
        )
    receipt["state_sha256"] = fingerprint(state)
    receipt["cohort"] = "wrong"
    with pytest.raises(ValueError):
        reviewed_unlock(
            state, receipt, cohort="test", session="2026-10-30", config=cfg, now=now
        )


def test_missing_evidence_stays_blocked_as_user_requested(tmp_path, market):
    h, _ = market
    empty = verify(None, list(h), h.index)
    assert not any(empty["checks"].values())
    invalid = verify(tmp_path, list(h), h.index)
    assert invalid["status"] == "BLOCKED_MISSING_OR_INVALID_EVIDENCE"
    assert not any(invalid["checks"].values())


def test_exposure_and_cost_examples_cannot_be_verified_by_flag_alone(tmp_path, market):
    import json

    h, _ = market
    for name in ["exposures", "execution-costs"]:
        doc = strict_json(f"config/economics/{name}.example.json")
        doc["verified"] = True
        doc["reviewer"] = "unit test"
        (tmp_path / f"{name}.json").write_text(json.dumps(doc))
    r = verify(tmp_path, list(h), h.index)
    assert not r["checks"]["fund_exposure_metadata"]
    assert not r["checks"]["transaction_cost_evidence"]
    assert not r["release_approved"]


def test_corrupt_covariance_is_rejected(cfg, market):
    h, cov = market
    bad = cov.copy()
    bad[0, 0] = -1
    with pytest.raises(ValueError):
        checks(np.zeros(len(h.columns)), bad, list(h), cfg)


def test_independent_challenger_ledger_initializes_without_returns_and_rejects_change(
    tmp_path, cfg, market
):
    from stress_challenger_ledger import advance

    h, cov = market
    # This current-date fixture is synthetic and never written to the real cohort.
    prices = pd.DataFrame({s: [100.0] for s in h}, index=pd.to_datetime(["2026-10-30"]))
    source = {
        "policy_sources": {"test": "fixed"},
        "capture_sha256": "test",
        "report_sha256": "test",
    }
    now = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
    args = (
        tmp_path / "test.sqlite3",
        prices,
        {"macro_valid": True},
        h,
        cov,
        cfg,
        ("strict_cost_aware", False, True),
        source,
    )
    first = advance(*args, now=now)
    assert first["forward_return_sessions"] == 0 and first["nav"] == 1
    assert not first["promotion_enabled"]
    assert advance(*args, now=now)["status"] == "ALREADY_REGISTERED"
    source["policy_sources"]["test"] = "changed"
    with pytest.raises(ValueError):
        advance(*args, now=now)


def test_official_delay_corroboration_is_limited_to_exact_periods_and_dates():
    from macro_availability_diagnosis import release_delay_evidence

    assert release_delay_evidence("UNRATE", "2025-09", "2025-12-16")
    assert not release_delay_evidence("UNRATE", "2025-09", "2025-12-17")
    assert release_delay_evidence("INDPRO", "2025-08", "2025-12-03")
    assert not release_delay_evidence("INDPRO", "2025-08", "2025-12-04")
    assert not release_delay_evidence("INDPRO", "2024-08", "2025-12-03")


def test_daily_handoff_rejects_pending_job_and_mismatched_bundle(tmp_path, monkeypatch):
    import run_economic_shadow_cycle as cycle
    from strategy_integrity import file_hash

    job = tmp_path / "runs" / "case"
    (job / "dashboard").mkdir(parents=True)
    bundle = job / "dashboard" / "latest-strategy-run.json"
    bundle.write_text("{}")
    monkeypatch.setattr(cycle, "health", lambda root: {"status": "PENDING_SHADOW_JOB"})
    with pytest.raises(ValueError):
        cycle.current_bundle(tmp_path)
    monkeypatch.setattr(cycle, "health", lambda root: {"status": "HEALTHY_SHADOW_JOB"})
    monkeypatch.setattr(
        cycle,
        "strict_json",
        lambda path: {"job": str(job), "market_session": "2026-10-30"},
    )
    monkeypatch.setattr(
        cycle,
        "read_observation",
        lambda path: {"evidence": {"bundle_sha256": file_hash(bundle)}},
    )
    assert cycle.current_bundle(tmp_path) == bundle
    monkeypatch.setattr(
        cycle, "read_observation", lambda path: {"evidence": {"bundle_sha256": "wrong"}}
    )
    with pytest.raises(ValueError):
        cycle.current_bundle(tmp_path)


def test_protective_scaling_recomputes_metrics_and_calculation_id(cfg, market):
    from stress_budget_challenger import finalize_target

    h, cov = market
    target = allocate(h, cov, cfg)
    if target["status"] != "UNAPPROVED_STRESS_BUDGET_SHADOW":
        pytest.skip("No feasible solver point in fixture")
    scaled = finalize_target(
        target, cov, list(h), cfg, factor=0.5, drawdown=-0.02, degraded=False
    )
    assert scaled["validation"]["volatility"] == pytest.approx(
        target["validation"]["volatility"] * 0.5
    )
    assert scaled["cash"] == pytest.approx(1 - 0.5 * (1 - target["cash"]))
    assert scaled["calculation_id"] == fingerprint(
        {k: v for k, v in scaled.items() if k != "calculation_id"}
    )
