from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from weekly_portfolios import POLICIES, SOURCES, allocate, observations, projections, replay, weekly_session, published, verify
from strategy_integrity import file_hash, fingerprint
from strategy_receipts import atomic_json


def history():
    symbols = ["SPY", "VEA", "VWO", "QQQ", "IEF", "SHY", "TLT", "GLD", "DBC", "LQD"]
    rng = np.random.default_rng(12)
    return pd.DataFrame(rng.normal(.0015, .02, (156, len(symbols))),
                        columns=symbols, index=pd.date_range("2023-11-24", periods=156, freq="W-FRI"))


@pytest.mark.parametrize("key", list(POLICIES))
def test_allocation_caps_risk_and_no_borrowing(key):
    h = history()
    w, cov, expected = allocate(h, POLICIES[key])
    assert np.isfinite(w).all() and np.isfinite(cov).all() and np.isfinite(expected).all()
    assert min(w) >= 0 and max(w) <= .20 + 1e-8
    assert w.sum() <= 1 - POLICIES[key]["cash"] + 1e-7
    assert w[:4].sum() <= POLICIES[key]["equity"] + 1e-7
    assert np.isclose(sum(w * (cov @ w) / (w @ cov @ w)), 1)


@pytest.mark.parametrize("stamp,expected", [
    ("2026-11-13T21:14:00+00:00", "2026-11-06"),
    ("2026-11-13T21:16:00+00:00", "2026-11-13"),
    ("2026-04-03T22:00:00+00:00", "2026-04-02"),
    ("2026-11-27T18:16:00+00:00", "2026-11-27"),
    ("2026-11-16T22:00:00+00:00", "2026-11-13"),
])
def test_completed_week_including_holiday_and_early_close(stamp, expected):
    assert weekly_session(datetime.fromisoformat(stamp)) == expected


def test_projection_quantiles_costs_and_zero_risk_case():
    h = history()
    p = projections(h, np.zeros(len(h.columns)))
    assert set(p) == {"4", "13", "52", "156"}
    assert all(row["median_return"] == row["p95_drawdown"] == row["loss_frequency"] == 0 for row in p.values())
    w = np.full(len(h.columns), .08)
    assert projections(h, w) == projections(h, w)
    for row in projections(h, w).values():
        assert row["p05_return"] <= row["median_return"] <= row["p95_return"]
        assert 0 <= row["loss_frequency"] <= 1
        assert 0 <= row["p95_drawdown"] < 1


def test_replay_next_week_fill_deducts_exact_initial_cost():
    h = history() * 0
    fixed = np.zeros(h.shape[1])
    fixed[0] = .6
    result = replay(h, POLICIES["medium"], fixed)
    assert np.isclose(result["total_return"], 1 / (1 + .0015 * .6) - 1)
    assert result["weeks"] == 52


def test_missing_asset_history_is_excluded_without_filling():
    h = history()
    prices = (1 + h).cumprod()
    prices = pd.concat([prices.iloc[:1].set_axis([prices.index[0] - pd.Timedelta(days=7)]) * 0 + 1, prices])
    prices.iloc[20, 0] = np.nan
    observations_, excluded = observations(prices, str(prices.index[-1].date()))
    assert "SPY" in excluded and "SPY" not in observations_
    with pytest.raises(ValueError):
        observations(prices.iloc[::-1], str(prices.index[-1].date()))


def test_publication_rejects_traversal_before_opening_artifacts(tmp_path):
    atomic_json(tmp_path / "latest.json", {"research_id": "../private"})
    with pytest.raises(ValueError, match="revision"):
        published(tmp_path)


def test_manifest_requires_full_sources_and_rejects_rehashed_data_tampering(tmp_path):
    data = dict(schema_version=1, status="REVIEW_REQUIRED", execution_enabled=False, promotion_enabled=False,
                candidates={key: dict(allocations=[dict(weight=1., risk_share=1.)]) for key in POLICIES})
    data["research_id"] = fingerprint(data)
    atomic_json(tmp_path / "recommendations.json", data)
    (tmp_path / "dashboard-report.pdf").write_bytes(b"%PDF-test")
    manifest = dict(schema_version=1, source_hashes={s: file_hash(s) for s in SOURCES},
                    files={s: file_hash(tmp_path / s) for s in ("recommendations.json", "dashboard-report.pdf")})
    atomic_json(tmp_path / "manifest.json", manifest)
    assert verify(tmp_path)["research_id"] == data["research_id"]
    data["status"] = "APPROVED"
    atomic_json(tmp_path / "recommendations.json", data)
    manifest["files"]["recommendations.json"] = file_hash(tmp_path / "recommendations.json")
    atomic_json(tmp_path / "manifest.json", manifest)
    with pytest.raises(ValueError, match="identity"):
        verify(tmp_path)
    manifest["source_hashes"] = {}
    atomic_json(tmp_path / "manifest.json", manifest)
    with pytest.raises(ValueError, match="source"):
        verify(tmp_path)
