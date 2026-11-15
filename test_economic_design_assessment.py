import json

import numpy as np
import pandas as pd
import pytest

from economic_design_assessment import (
    replay,
    risk_targets,
    paired_interval,
    load_cash_history,
    stress_review,
    economic_gate,
)
from strategy_integrity import file_hash


def test_cash_and_asset_profit_reconcile_with_self_financing_fees():
    dates = pd.bdate_range("2020-01-01", periods=4)
    returns = pd.DataFrame({"A": [0.1, 0.1, -0.1, 0.01]}, index=dates)
    frame = replay(
        returns,
        {dates[0]: {"A": 0.5}, dates[2]: {"A": 0}},
        pd.Series(0.001, index=dates),
    )
    assert frame.iloc[0]["gross_return"] == pytest.approx(
        0.001
    )  # cash held before first close fill
    assert frame.iloc[0]["return"] < 0.001
    profit = (
        frame.pnl_A.sum()
        + frame.cash_profit_initial.sum()
        - frame.cost_as_initial_capital.sum()
    )
    assert profit == pytest.approx(frame.equity.iloc[-1] - 1)
    assert frame.iloc[-1]["cash"] == 1


def test_guard_is_next_close_and_lock_cannot_recover_automatically():
    dates = pd.bdate_range("2020-01-01", periods=5)
    r = pd.DataFrame({"A": [0, -0.2, 1, 1, 1]}, index=dates)
    path = replay(r, {d: {"A": 0.5} for d in dates}, protect=True)
    assert path.iloc[1]["account_drawdown"] < -0.05  # threshold is not a gap guarantee
    assert path.iloc[1]["cash_locked"]
    assert path.iloc[2]["cash"] == 1
    assert path.iloc[3]["equity"] == path.iloc[2]["equity"]


def test_reference_risk_estimates_never_consume_current_or_future_returns():
    dates = pd.bdate_range("2020-01-01", periods=300)
    r = pd.DataFrame({"A": np.sin(np.arange(300)) * 0.01}, index=dates)
    targets = risk_targets(r, dates[260:], {"A": 1}, 0.04)
    altered = r.copy()
    altered.loc[dates[260] :, "A"] = 0.9
    again = risk_targets(altered, dates[260:], {"A": 1}, 0.04)
    assert targets[dates[260]] == again[dates[260]]
    with pytest.raises(ValueError):
        risk_targets(r, dates[:3], {"A": 1}, 0.04)


def test_block_interval_is_paired_reproducible_and_cannot_invent_advantage():
    a = pd.Series(np.sin(np.arange(252)) * 0.01)
    first = paired_interval(a, a, block=21, paths=100)
    assert first == paired_interval(a, a, block=21, paths=100)
    assert first["p025"] == 0 and first["p975"] == 0
    with pytest.raises(ValueError):
        paired_interval(a, a.iloc[1:], block=21)


def test_unverified_cash_examples_are_rejected_and_missing_actual_dates_fail(tmp_path):
    path = tmp_path / "cash.json"
    path.write_text(json.dumps({"verified": False}))
    dates = pd.bdate_range("2020-01-01", periods=3)
    with pytest.raises(ValueError):
        load_cash_history(path, dates)
    returns = tmp_path / "returns.csv"
    pd.DataFrame({"date": dates[:2], "net_return": [0.0001, 0.0002]}).to_csv(
        returns, index=False
    )
    proof = tmp_path / "statement.txt"
    proof.write_text("Synthetic fixture evidence, not an actual account")
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "currency": "USD",
                "verified": True,
                "reviewer": "test fixture",
                "source": "SYNTHETIC UNIT TEST",
                "returns": {"file": returns.name, "sha256": file_hash(returns)},
                "evidence": [{"file": proof.name, "sha256": file_hash(proof)}],
            }
        )
    )
    actual, meta = load_cash_history(path, dates[:2])
    assert np.allclose(actual, [0.0001, 0.0002])
    assert meta["status"] == "OPERATOR_ATTESTED_OBSERVED_CASH_HISTORY"
    with pytest.raises(ValueError):
        load_cash_history(path, dates)
    proof.write_text("Changed")
    with pytest.raises(ValueError):
        load_cash_history(path, dates[:2])


def test_missing_held_prices_never_forward_filled():
    dates = pd.bdate_range("2020-01-01", periods=3)
    r = pd.DataFrame({"A": [0, np.nan, 0.01]}, index=dates)
    with pytest.raises(ValueError):
        replay(r, {dates[0]: {"A": 0.5}})
    # An unavailable unheld asset does not create a fictional holding or return.
    assert replay(r, {})["equity"].tolist() == [1.0, 1.0, 1.0]


def test_stress_limits_do_not_confuse_asset_caps_with_aggregate_loss():
    result = stress_review(
        {"SPY": 0.25, "TLT": 0.25, "IEF": 0.25, "TIP": 0.20},
        np.eye(4),
        ["SPY", "TLT", "IEF", "TIP"],
    )
    assert result["per_asset_capital_pass"]
    assert not result["five_percent_stress_review_pass"]
    assert result["duration_dv01_fx_limits"] == "UNVERIFIED_EXPOSURE_METADATA_REQUIRED"


def test_economic_screen_never_grants_promotion_from_backtests():
    result = {
        "cash_baseline": {"status": "BLOCKED_NO_VERIFIED_USER_CASH_HISTORY"},
        "strategies": [
            {
                "name": "test",
                "archived_metrics": {"total_return": -0.01},
                "stress_review": {"five_percent_stress_review_pass": False},
                "matched_references": [
                    {"paired_block_intervals": {"21": {"p025": -0.1}}}
                ],
            }
        ],
    }
    gate = economic_gate(result)
    assert gate["status"] == "BLOCKED"
    assert not gate["strategies"][0]["promotion_enabled"]
    assert not any(gate["strategies"][0]["checks"].values())


def test_stress_bound_preserves_carried_peak_and_reserves_costs():
    from economic_design_report import stress_exposure_bound

    b = stress_exposure_bound({"SPY": 0.2, "IEF": 0.2, "TIP": 0.2}, -0.02, 0.12)
    assert 0 < b["exposure_multiplier_ceiling"] < 0.05 / 0.12
    assert b["cash_fraction_at_ceiling"] > 0.6
    assert b["modeled_drawdown_in_worst_declared_shock"] == pytest.approx(0.05)
    assert not b["execution_enabled"] and not b["release_approved"]


def test_already_breached_account_cannot_be_repaired_by_claiming_cash_guarantee():
    from economic_design_report import stress_exposure_bound

    b = stress_exposure_bound({"SPY": 0.2}, -0.06, 0.1)
    assert b["exposure_multiplier_ceiling"] == 0
    assert not b["declared_case_meets_five_percent"]
    with pytest.raises(ValueError):
        stress_exposure_bound({"SPY": 1.2}, 0, 0.1)
