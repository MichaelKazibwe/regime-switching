"""Regression tests for exact calendar endpoints and missing-aware outlooks."""

import numpy as np
import pandas as pd
import pytest
from pathlib import Path

from investor_macro_feed import current_features
from macro_feature_contract import calculate_macro_features
from test_live_strategy_training import macro_fixture
from investor_analytics import macro_context


def observations():
    months = pd.date_range("2010-01-01", "2026-09-01", freq="MS")
    daily = pd.bdate_range("2010-01-01", "2026-10-29")
    return {
        "CPIAUCSL": pd.Series(100 + np.arange(len(months)) * 0.2, index=months),
        "UNRATE": pd.Series(5 + np.sin(np.arange(len(months))) * 0.1, index=months),
        "INDPRO": pd.Series(80 + np.arange(len(months)) * 0.3, index=months),
        "DGS10": pd.Series(4.0, index=daily),
        "DGS3MO": pd.Series(3.5, index=daily),
    }


def test_missing_unneeded_month_does_not_shift_cpi_calendar_endpoints():
    obs = observations()
    obs["CPIAUCSL"] = obs["CPIAUCSL"].drop(pd.Timestamp("2025-10-01"))
    latest = current_features(obs, "2026-10-30T21:00:00Z")[-1]
    cpi = obs["CPIAUCSL"]
    yoy = 100 * (cpi["2026-09-01"] / cpi["2025-09-01"] - 1)
    prior = 100 * (cpi["2026-06-01"] / cpi["2025-06-01"] - 1)
    assert latest["inflation_yoy"] == pytest.approx(yoy)
    assert latest["inflation_change"] == pytest.approx(yoy - prior)
    assert latest["required_observation_periods"]["CPIAUCSL"] == [
        "2026-09",
        "2025-09",
        "2026-06",
        "2025-06",
    ]


@pytest.mark.parametrize(
    "key,date",
    [
        ("CPIAUCSL", "2025-09-01"),
        ("CPIAUCSL", "2025-06-01"),
        ("UNRATE", "2026-05-01"),
        ("INDPRO", "2026-03-01"),
    ],
)
def test_current_missing_required_period_rejected(key, date):
    obs = observations()
    obs[key] = obs[key].drop(pd.Timestamp(date))
    with pytest.raises(ValueError, match="Missing required calendar period"):
        current_features(obs, "2026-10-30T21:00:00Z")


def test_current_duplicate_month_rejected():
    obs = observations()
    obs["CPIAUCSL"] = pd.concat(
        [obs["CPIAUCSL"], pd.Series([150.0], index=pd.to_datetime(["2026-09-15"]))]
    ).sort_index()
    with pytest.raises(ValueError, match="Ambiguous monthly"):
        current_features(obs, "2026-10-30T21:00:00Z")


def test_aligned_yields_cannot_be_stale_despite_fresh_individual_series():
    obs = observations()
    obs["DGS10"] = obs["DGS10"].loc[:"2026-10-01"]
    obs["DGS10"].loc[pd.Timestamp("2026-10-29")] = 4
    obs["DGS3MO"] = obs["DGS3MO"].loc[:"2026-10-01"]
    obs["DGS3MO"].loc[pd.Timestamp("2026-10-28")] = 3.5
    with pytest.raises(ValueError, match="aligned Treasury"):
        calculate_macro_features(obs, "2026-10-30")


def test_current_and_release_aware_features_share_same_contract():
    macro = macro_fixture()
    stamp = pd.Timestamp("2026-10-29T20:00:00Z")
    views = {key: data.as_of(stamp).dropna() for key, data in macro.data.items()}
    current = calculate_macro_features(views, stamp)
    vintage = macro.features(stamp)
    for key, value in current.items():
        assert vintage[key] == value


def test_quarter_model_never_bridges_missing_feature_months():
    obs = observations()
    for key in ("CPIAUCSL", "UNRATE"):
        obs[key] = obs[key].drop(pd.Timestamp("2025-10-01"))
    rows = current_features(obs, "2026-10-30T21:00:00Z")
    ctx = macro_context(rows, "2026-10-30T21:00:00Z")
    assert len(ctx["quarterly"]) == 4
    assert ctx["missing_training_months"]
    assert ctx["residual_calendar_blocks"] > 0
    for a, b in ctx["fitting_pair_months"]:
        assert pd.Period(b, freq="M") - 1 == pd.Period(a, freq="M")
        assert a not in ctx["missing_training_months"]
        assert b not in ctx["missing_training_months"]
    assert ctx["monthly_training_count"] < 120


def test_capture_discloses_unavailable_overlay_without_filling(tmp_path, monkeypatch):
    import io
    import json
    import investor_macro_feed as feed
    from core_constants import settings
    from macro_feature_contract import MacroFeatureUnavailable

    monkeypatch.setattr(settings, "fred_api_key", "test-only")
    monkeypatch.setattr(feed, "urlopen", lambda *a, **k: io.StringIO(
        json.dumps({"observations": [{"date": "2026-09-01", "value": "100"}]})))

    def unavailable(root):
        raise MacroFeatureUnavailable("Missing required calendar period: CPIAUCSL")

    monkeypatch.setattr(feed, "features_from_directory", unavailable)
    result = feed.refresh(tmp_path)
    assert result["status"] == "INFORMATIONAL_MACRO_UNAVAILABLE"
    path = Path(result["features"])
    assert json.loads(path.read_text()) == []
    manifest = json.loads((path.parent / "manifest.json").read_text())
    assert manifest["feature_status"] == "UNAVAILABLE"
    assert "CPIAUCSL" in manifest["feature_reason"]
    assert len(manifest["series"]) == 5


def test_capture_does_not_swallow_invalid_data(tmp_path, monkeypatch):
    import io
    import json
    import investor_macro_feed as feed
    from core_constants import settings

    monkeypatch.setattr(settings, "fred_api_key", "test-only")
    monkeypatch.setattr(feed, "urlopen", lambda *a, **k: io.StringIO(
        json.dumps({"observations": [{"date": "2026-09-01", "value": "100"}]})))

    def invalid(root):
        raise ValueError("Current macro file checksum mismatch")

    monkeypatch.setattr(feed, "features_from_directory", invalid)
    with pytest.raises(ValueError, match="checksum"):
        feed.refresh(tmp_path)
