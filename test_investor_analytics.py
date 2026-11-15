"""Tests of point-in-time macro outlooks and honest portfolio diagnostics."""

from copy import deepcopy
import json

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
import pytest

from investor_analytics import (
    REGIMES,
    build_context,
    macro_context,
    portfolio_diagnostics,
)


def features(periods=48):
    rows = []
    for j, date in enumerate(pd.date_range("2019-01-31", periods=periods, freq="ME")):
        rows.append(
            {
                "date": str(date.date()),
                "as_of": str(date.date()) + "T21:00:00+00:00",
                "ip_growth": float(np.sin(j / 5) * 3),
                "inflation_yoy": 2 + float(np.cos(j / 5)),
                "inflation_change": float(np.sin(j / 3) / 3),
                "unemployment_change": float(np.cos(j / 4) / 5),
                "yield_curve": float(np.sin(j / 6)),
                "probabilities": dict(zip(REGIMES, [0.4, 0.3, 0.2, 0.1])),
                "observation_dates": {
                    k: str(date.date())
                    for k in ["INDPRO", "CPIAUCSL", "UNRATE", "DGS10", "DGS3MO"]
                },
            }
        )
    return rows


def result():
    return {
        "recommendation_id": "test",
        "allocation": {"weights": {"SPY": 0.5, "USD_CASH": 0.5}},
        "mandate": {"base_currency": "USD"},
        "price_session": "2022-12-30",
        "as_of": "2022-12-30T21:00:00+00:00",
    }


def test_future_features_cannot_change_outlook_and_forecasts_are_deterministic():
    rows = features()
    cutoff = rows[-1]["as_of"]
    a = macro_context(rows, cutoff, paths=100)
    future = deepcopy(rows[-1])
    future.update(date="2025-01-01", as_of="2025-01-01T21:00:00+00:00", ip_growth=1000)
    b = macro_context(rows + [future], cutoff, paths=100)
    assert a == b
    assert len(a["quarterly"]) == 4
    assert a["quarterly"][0]["quarter"] == "2023Q1"
    for quarter in a["quarterly"]:
        assert pd.Timestamp(quarter["end_date"]).date() > pd.Timestamp(cutoff).date()
        assert sum(quarter["regime_frequencies"].values()) == pytest.approx(1)
        for variable in quarter["variables"].values():
            assert variable["p05"] <= variable["median"] <= variable["p95"]
    assert "unvalidated" in " ".join(a["limitations"])
    assert "100 paths" in a["method"]


def test_short_missing_and_stale_history_never_get_invented_forecasts():
    rows = features()
    assert macro_context(rows[:20], rows[19]["as_of"], paths=100)["quarterly"] == []
    assert (
        macro_context(rows[:20] + rows[21:], rows[-1]["as_of"], paths=100)["quarterly"]
        == []
    )
    assert (
        macro_context(rows, "2023-06-01T21:00:00+00:00", paths=100)["quarterly"] == []
    )
    assert macro_context([], "2023-01-01T00:00:00+00:00")["status"] == "UNAVAILABLE"


def test_future_observation_date_and_invalid_regime_scores_rejected():
    rows = features()
    rows[-1]["observation_dates"]["INDPRO"] = "2099-01-01"
    with pytest.raises(ValueError, match="Future"):
        macro_context(rows, rows[-1]["as_of"], paths=100)
    rows = features()
    rows[-1]["probabilities"][REGIMES[0]] = 3
    with pytest.raises(ValueError, match="scores"):
        macro_context(rows, rows[-1]["as_of"], paths=100)


def price_frame():
    sessions = mcal.get_calendar("NYSE").schedule("2020-01-01", "2022-12-30").index
    returns = np.sin(np.arange(len(sessions)) * 0.2) * 0.005 + 0.0001
    return pd.DataFrame({"SPY": 100 * np.cumprod(1 + returns)}, index=sessions)


def test_fixed_weight_returns_use_observed_data_without_cash_yield_or_future_leakage():
    r = result()
    prices = price_frame()
    d = portfolio_diagnostics(r, prices, features())
    daily = prices.SPY.pct_change(fill_method=None).dropna() * 0.5
    assert d["status"] == "RETROSPECTIVE_FIXED_WEIGHT_DIAGNOSTIC"
    assert d["metrics"]["total_return"] == pytest.approx((1 + daily).prod() - 1)
    assert (
        "gross of trading costs" in d["assumptions"] and "hindsight" in d["assumptions"]
    )
    future = pd.DataFrame({"SPY": [99999.0]}, index=pd.to_datetime(["2023-01-03"]))
    assert portfolio_diagnostics(r, pd.concat([prices, future]), features()) == d
    assert all(
        q["feature_date"] < str(pd.Period(q["quarter"]).start_time.date())
        for q in d["quarterly"]
    )


def test_missing_sessions_and_currency_cannot_be_silently_filled():
    prices = price_frame()
    prices.iloc[400, 0] = np.nan
    assert (
        portfolio_diagnostics(result(), prices, features())["status"] == "UNAVAILABLE"
    )
    r = result()
    r["mandate"]["base_currency"] = "EUR"
    assert (
        portfolio_diagnostics(r, price_frame(), features())["status"] == "UNAVAILABLE"
    )


def test_research_allocation_is_separate_and_reconciled(tmp_path):
    p = tmp_path / "audit.json"
    p.write_text(
        json.dumps(
            [{"execution_date": "2022-12-29", "weights": {"SPY": 0.9}, "cash": 0.1}]
        )
    )
    r = result()
    before = deepcopy(r)
    c = build_context([r], research_allocation_path=p)
    assert len(c["core_symbols"]) == 26
    assert c["research_allocation"]["weights"]["SPY"] == 0.9
    assert r == before
    p.write_text(
        json.dumps(
            [{"execution_date": "2022-12-29", "weights": {"SPY": 0.9}, "cash": 0.5}]
        )
    )
    with pytest.raises(ValueError, match="reconcile"):
        build_context([r], research_allocation_path=p)


def test_pdf_generation_contains_private_local_artifact_without_mutating_plan(tmp_path):
    from investor_pdf import render_investor_pdf
    from test_investor_dashboard import saved_plan

    r = saved_plan()
    r["allocation"]["variance_contributions"] = {}
    before = deepcopy(r)
    path = render_investor_pdf(r, {}, tmp_path / "report.pdf")
    assert path.read_bytes().startswith(b"%PDF-")
    assert path.stat().st_mode & 0o777 == 0o600
    assert r == before


def test_rendered_dashboard_has_26_core_symbols_and_macroeconomic_sections(tmp_path):
    from investor_dashboard import render_dashboard
    from test_investor_dashboard import saved_plan, payload

    path = tmp_path / "index.html"
    render_dashboard([saved_plan()], path, context={"plans": {}})
    html = path.read_text()
    assert len(payload(path)["core_symbols"]) == 26
    assert all(
        text in html
        for text in [
            "26-ETF allocation map",
            "Macroeconomic dashboard",
            "Four-quarter indicator outlook",
            "Performance and macro sensitivity",
            "Drawdown history",
        ]
    )


def test_latest_overlay_never_replaces_plan_time_macro_or_relabels_portfolio(tmp_path):
    from datetime import datetime, timezone

    root = tmp_path / "historical"
    root.mkdir()
    historical = root / "features.json"
    historical.write_text(json.dumps(features()))
    live = tmp_path / "features.json"
    rows = features()
    now = datetime.now(timezone.utc)
    for row in rows:
        row["as_of"] = now.isoformat()
        row["source_kind"] = "CURRENT_REVISED_FRED_NOT_HISTORICAL_VINTAGES"
    # Keep feature dates contemporaneous for the live outlook; availability is retrieval time.
    rows[-1]["date"] = str(now.date())
    live.write_text(json.dumps(rows))
    r = result()
    before = deepcopy(r)
    context = build_context([r], features_path=historical, latest_features_path=live)
    entry = context["plans"][r["recommendation_id"]]
    assert entry["macro"]["as_of"] < r["as_of"]
    assert entry["latest_macro"]["as_of"] == now.isoformat()
    assert r == before
    assert set(context["source_hashes"]) == {"plan_features", "latest_features"}


def test_current_fred_features_are_revised_now_not_historical_availability():
    from investor_macro_feed import SERIES, current_features

    months = pd.date_range("2010-01-01", "2026-09-01", freq="MS")
    daily = pd.bdate_range("2010-01-01", "2026-10-29")
    observations = {
        key: pd.Series(100 + np.arange(len(months)) * 0.1, index=months)
        for key in SERIES
        if key not in {"DGS10", "DGS3MO"}
    }
    for key, level in [("DGS10", 4.0), ("DGS3MO", 3.5)]:
        observations[key] = pd.Series(level, index=daily)
    rows = current_features(observations, "2026-10-30T21:00:00+00:00")
    assert len(rows) > 120
    assert all(r["as_of"] == "2026-10-30T21:00:00+00:00" for r in rows)
    assert rows[-1]["date"] == "2026-10-30"
    assert rows[-1]["yield_curve"] == pytest.approx(0.5)
    assert macro_context(rows, "2025-10-29T21:00:00+00:00")["status"] == "UNAVAILABLE"
    with pytest.raises(ValueError, match="stale"):
        current_features(observations, "2027-10-30T21:00:00+00:00")
