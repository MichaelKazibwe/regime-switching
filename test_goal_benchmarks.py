import numpy as np
import pandas as pd
import pytest

from benchmark_managed_futures import build_comparison
from report_three_year_goal import forecast_diagnostics


def prices():
    dates = pd.bdate_range("2019-06-01", periods=1100)
    rng = np.random.default_rng(171)
    raw = pd.DataFrame(
        np.cumprod(1 + rng.normal(0.0003, 0.005, (len(dates), 6)), axis=0),
        index=dates,
        columns=["SPY", "VEA", "VWO", "IEF", "TLT", "GLD"],
    )
    managed = pd.Series(
        np.cumprod(1 + rng.normal(0.0001, 0.004, len(dates))), index=dates, name="DBMF"
    )
    return raw, managed


def test_actual_managed_futures_benchmark_has_eligibility_lag_and_constant_cash():
    raw, managed = prices()
    table, frames = build_comparison(raw, managed)
    assert len(table) == 2
    assert all(frame.index[0] == raw.index[253] for frame in frames.values())
    assert all(frame.iloc[0]["return"] < 0 for frame in frames.values())
    assert all(frame.cash.min() > 0 for frame in frames.values())
    assert set(table.model) == {"growth_reference", "10pct_actual_DBMF"}


def test_managed_futures_benchmark_rejects_reserved_and_missing_observations():
    raw, managed = prices()
    managed.iloc[260] = np.nan
    with pytest.raises(ValueError):
        build_comparison(raw, managed)
    managed = managed.dropna()
    managed.loc[pd.Timestamp("2025-10-30")] = 1.0
    with pytest.raises(ValueError):
        build_comparison(raw, managed)


def test_insufficient_calibration_history_is_reported_without_a_pass_claim():
    frame = pd.DataFrame(
        {
            "filtered_ready": False,
            "raw_daily_sigma": 0.01,
            "gross_return": 0.0,
            "filtered_var95": 0.02,
        },
        index=range(100),
    )
    assert forecast_diagnostics(frame) == {"ready_observations": 0}


def test_filtered_diagnostics_use_realized_outcomes_and_detect_clustering():
    r = np.full(1000, 0.0001)
    r[100:150] = -0.03
    frame = pd.DataFrame(
        {
            "filtered_ready": True,
            "raw_daily_sigma": 0.01,
            "gross_return": r,
            "filtered_var95": 0.01645,
        }
    )
    report = forecast_diagnostics(frame)
    assert report["ready_observations"] == 1000
    assert report["filtered_historical"]["christoffersen_independence_pvalue"] < 0.001
