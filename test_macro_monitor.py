import numpy as np
import pandas as pd
import pytest

from macro_monitor import aggregate, as_known, SERIES
from macrovintage import MacroVintageData


def row(date, value, market_return, valid=True):
    return dict(date=date, quarter=str(pd.Period(date, freq="Q")),
                series={key: dict(value=value, observation_date="2026-01-01", available_at="2026-02-02T05:00:00+00:00") for key in SERIES},
                spy_return=market_return, yield_curve=value, macro_valid=valid,
                regime="disinflationary_growth" if valid else "UNAVAILABLE")


def test_daily_to_quarter_means_compounding_coverage_and_missing_values():
    rows = [row("2026-02-02", 4., .1), row("2026-02-03", None, -.1, False)]
    result = aggregate(rows, ["2026-02-02", "2026-02-03"], "2026-02-03")[0]
    assert result["daily_context_means"]["UNRATE"] == 4.
    assert result["available_sessions"]["UNRATE"] == 1
    assert result["macro_coverage"] == .5
    assert np.isclose(result["spy_compounded_return"], -.01)
    assert result["valid_regime_frequencies"] == {"disinflationary_growth": 1.}
    assert result["period_status"] == "QUARTER_TO_DATE"
    assert result["complete"]


def test_missing_session_blocks_full_quarter_return_and_counts_coverage():
    result = aggregate([row("2026-02-02", 4., .01)], ["2026-02-02", "2026-02-03"], "2026-02-03")[0]
    assert result["missing_sessions"] == ["2026-02-03"]
    assert result["macro_coverage"] == .5
    assert result["spy_compounded_return"] is None
    assert not result["complete"]


def test_quarter_boundary_and_all_unavailable_never_become_zero():
    result = aggregate([row("2026-03-31", None, None, False), row("2026-04-01", 3., .02)],
                       ["2026-03-31", "2026-04-01"], "2026-04-01")
    assert [q["quarter"] for q in result] == ["2026Q2", "2026Q1"]
    assert result[1]["daily_context_means"]["CPIAUCSL"] is None
    assert result[1]["spy_compounded_return"] is None
    assert result[1]["valid_regime_frequencies"] == {}
    assert result[1]["period_status"] == "HISTORICAL_QUARTER"


def test_causal_release_and_revision_availability_next_ny_midnight():
    vintages = MacroVintageData(pd.DataFrame([
        dict(date="2026-01-01", realtime_start="2026-02-02", value=3.),
        dict(date="2026-01-01", realtime_start="2026-02-04", value=4.),
    ]))
    assert as_known(vintages, "2026-02-02T21:00:00Z", "UNRATE")["value"] is None
    assert as_known(vintages, "2026-02-03T21:00:00Z", "UNRATE")["value"] == 3.
    assert as_known(vintages, "2026-02-04T21:00:00Z", "UNRATE")["value"] == 3.
    assert as_known(vintages, "2026-02-05T21:00:00Z", "UNRATE")["value"] == 4.


@pytest.mark.parametrize("key,stamp", [("UNRATE", "2026-05-05T20:00:00Z"), ("DGS10", "2026-02-17T21:00:00Z")])
def test_stale_series_remain_unavailable_with_original_date(key, stamp):
    data = MacroVintageData(pd.DataFrame([dict(date="2026-01-01", realtime_start="2026-01-02", value=4.)]))
    item = as_known(data, stamp, key)
    assert item["value"] is None and item["status"] == "STALE"
    assert item["observation_date"] == "2026-01-01"
