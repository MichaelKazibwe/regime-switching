from copy import deepcopy
import numpy as np
import pandas as pd
import pytest

from live_strategy_training import fit_classifier, walk_forward_forecasts
from strategy_training_data import usable_session
from training_macro import TrainingMacro
from macrovintage import MacroVintageData
from diversifiedregimepolicy import AllocationError
from test_four_macro_strategies import features, settings


@pytest.mark.parametrize(
    "stamp,expected",
    [
        ("2026-10-30T19:59:00Z", "2026-10-29"),
        ("2026-10-30T20:05:00Z", "2026-10-29"),
        ("2026-10-30T20:20:00Z", "2026-10-30"),
        ("2026-10-31T12:00:00Z", "2026-10-30"),
    ],
)
def test_completed_session_publication_buffer(stamp, expected):
    assert str(usable_session(pd.Timestamp(stamp).to_pydatetime()).date()) == expected


def test_frozen_scaler_labels_and_coefficients_ignore_later_data():
    rows = features(240)
    spec = settings()
    a, base, meta = fit_classifier(rows, 160, spec)
    changed = deepcopy(rows)
    for row in changed[161:]:
        for k in [
            "ip_growth",
            "unemployment_change",
            "inflation_change",
            "yield_curve",
            "trend",
            "breadth",
            "volatility",
            "credit_relative",
        ]:
            row[k] = 99999.0
    b, other, again = fit_classifier(changed, 160, spec)
    assert meta == again and np.allclose(base, other)
    assert meta["last_training_label_date"] < meta["freeze_date"]
    assert np.allclose(a[0].mean_, b[0].mean_)
    assert np.allclose(a[-1].coef_, b[-1].coef_)


def test_missing_macro_sessions_are_not_compressed_or_labeled():
    rows = features(120)
    rows[60]["macro_valid"] = False
    for key in ["ip_growth", "unemployment_change", "inflation_change", "yield_curve"]:
        rows[60][key] = None
    forecasts, scores = walk_forward_forecasts(rows, settings())
    assert not forecasts[pd.Timestamp(rows[60]["date"])]["input_valid"]
    assert not forecasts[pd.Timestamp(rows[60]["date"])]["enabled"]
    assert all(
        s["date"] != rows[60]["date"] and s["outcome_date"] != rows[60]["date"]
        for s in scores
    )
    for row in rows:
        p = forecasts[pd.Timestamp(row["date"])]
        assert np.isclose(sum(p["used"]), 1)
        if p["training_last_label_date"]:
            assert p["training_last_label_date"] < p["as_of"][:10]


def macro_fixture(drop_cpi=None, drop_u=None):
    m = object.__new__(TrainingMacro)
    m.data = {}
    m.times = {}
    m.cache = {}
    dates = pd.date_range("2024-01-01", "2026-09-01", freq="MS")
    for key in ["UNRATE", "CPIAUCSL", "INDPRO"]:
        values = 100 + np.arange(len(dates)) * 0.1
        frame = pd.DataFrame(
            {
                "date": dates,
                "realtime_start": dates + pd.Timedelta(days=35),
                "value": values,
            }
        )
        if key in {"UNRATE", "CPIAUCSL"}:
            frame = frame[frame.date != pd.Timestamp("2025-10-01")]
        if key == "CPIAUCSL" and drop_cpi:
            frame = frame[frame.date != pd.Timestamp(drop_cpi)]
        if key == "UNRATE" and drop_u:
            frame = frame[frame.date != pd.Timestamp(drop_u)]
        m.data[key] = MacroVintageData(frame)
    daily = pd.bdate_range("2024-01-01", "2026-10-28")
    for key, level in [("DGS10", 4.0), ("DGS3MO", 3.5)]:
        m.data[key] = MacroVintageData(
            pd.DataFrame(
                {
                    "date": daily,
                    "realtime_start": daily + pd.Timedelta(days=1),
                    "value": level,
                }
            )
        )
    for key, data in m.data.items():
        m.times[key] = (
            pd.DatetimeIndex(sorted(data.releases.available_at.unique()))
            .as_unit("ns")
            .asi8
        )
    return m


def test_exact_period_features_do_not_fill_unneeded_missing_month():
    f = macro_fixture().features("2026-10-29T20:00:00Z")
    assert f["observation_dates"]["UNRATE"] == "2026-09-01"
    assert f["yield_curve"] == pytest.approx(0.5)
    assert np.isfinite(f["inflation_yoy"])


@pytest.mark.parametrize(
    "kwargs", [{"drop_cpi": "2025-09-01"}, {"drop_u": "2026-05-01"}]
)
def test_required_missing_macro_period_is_fail_closed(kwargs):
    with pytest.raises(AllocationError, match="Missing required"):
        macro_fixture(**kwargs).features("2026-10-29T20:00:00Z")


def test_unavailable_macro_quarantines_strategy_to_cash_without_fabricated_labels():
    from test_goal_portfolio import inputs
    from fourregimestrategies import FourMacroStrategies
    from fourstrategysimulation import simulate_strategy

    _, prices, daily, states = inputs()
    for state in states.values():
        state["macro_unavailable"] = True
        state["signal"]["macro_unavailable"] = True
        state["signal"]["macro_forecast"] = {
            "as_of": state["signal"]["as_of"],
            "used": [0.25] * 4,
        }
    frame, _, audit = simulate_strategy(
        prices,
        daily,
        states,
        FourMacroStrategies(),
        {"strategy": "economic_balance", "volatility_ceiling": 0.06},
    )
    assert (frame.cash == 1).all() and (frame["return"] == 0).all()
    assert set(frame.macro_quadrant) == {"DATA_UNAVAILABLE"}
    assert audit["rejections"] == []
