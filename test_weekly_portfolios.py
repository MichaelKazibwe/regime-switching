from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from weekly_portfolios import (
    POLICIES,
    SOURCES,
    allocate,
    observations,
    projections,
    replay,
    weekly_session,
    published,
    verify,
)
from strategy_integrity import file_hash, fingerprint
from strategy_receipts import atomic_json


def history():
    symbols = ["SPY", "VEA", "VWO", "QQQ", "IEF", "SHY", "TLT", "GLD", "DBC", "LQD"]
    rng = np.random.default_rng(12)
    return pd.DataFrame(
        rng.normal(0.0015, 0.02, (156, len(symbols))),
        columns=symbols,
        index=pd.date_range("2023-11-24", periods=156, freq="W-FRI"),
    )


def test_optional_support_solver_failure_retains_verified_market_optimum(monkeypatch):
    import weekly_portfolios as module
    from types import SimpleNamespace
    real_minimize = module.minimize
    dense = []
    def solver(*args, **kwargs):
        if dense:
            return SimpleNamespace(success=False, x=np.full(len(dense[0]),np.nan))
        fit = real_minimize(*args, **kwargs)
        dense.append(fit.x.copy())
        return fit
    monkeypatch.setattr(module, 'minimize', solver)
    weights, covariance, _ = module.allocate(history(), POLICIES['medium'])
    assert (dense[0] < .0025).any() and (dense[0] >= .0025).any()
    assert np.allclose(weights,dense[0],atol=1e-7)
    assert weights.sum() <= 1-POLICIES['medium']['cash']+1e-7
    assert max(weights*(covariance@weights)/(weights@covariance@weights)) <= .35001


def test_nonfinite_primary_solution_is_never_published(monkeypatch):
    import weekly_portfolios as module
    from types import SimpleNamespace
    monkeypatch.setattr(module,'minimize',lambda *a,**kw:SimpleNamespace(
        success=True,x=np.full(history().shape[1],np.nan),message='unusable result'))
    with pytest.raises(ValueError,match='Constrained allocation failed'):
        module.allocate(history(),POLICIES['medium'])


def test_empty_support_is_cash_before_relative_risk_validation(monkeypatch):
    import weekly_portfolios as module
    from types import SimpleNamespace
    dust = np.zeros(history().shape[1])
    dust[0] = 3e-6  # Numerical cash solution, but a 100% relative risk share.
    monkeypatch.setattr(module, 'minimize', lambda *a, **kw: SimpleNamespace(
        success=True, x=dust, message='Optimization terminated successfully'))
    weights, covariance, _ = module.allocate(history(), POLICIES['short'])
    assert np.array_equal(weights, np.zeros_like(dust))
    module.verify_risk_concentration(weights, covariance)


@pytest.mark.parametrize("key", list(POLICIES))
def test_allocation_caps_risk_and_no_borrowing(key):
    h = history()
    w, cov, expected = allocate(h, POLICIES[key])
    assert (
        np.isfinite(w).all() and np.isfinite(cov).all() and np.isfinite(expected).all()
    )
    assert min(w) >= 0 and max(w) <= 0.20 + 1e-8
    assert w.sum() <= 1 - POLICIES[key]["cash"] + 1e-7
    assert w[:4].sum() <= POLICIES[key]["equity"] + 1e-7
    assert np.isclose(sum(w * (cov @ w) / (w @ cov @ w)), 1)
    assert max(w * (cov @ w) / (w @ cov @ w)) <= .35001


@pytest.mark.parametrize(
    "stamp,expected",
    [
        ("2026-11-13T21:14:00+00:00", "2026-11-06"),
        ("2026-11-13T21:16:00+00:00", "2026-11-13"),
        ("2026-04-03T22:00:00+00:00", "2026-04-02"),
        ("2026-11-27T18:16:00+00:00", "2026-11-27"),
        ("2026-11-16T22:00:00+00:00", "2026-11-13"),
    ],
)
def test_completed_week_including_holiday_and_early_close(stamp, expected):
    assert weekly_session(datetime.fromisoformat(stamp)) == expected


def test_projection_quantiles_costs_and_zero_risk_case():
    h = history()
    p = projections(h, np.zeros(len(h.columns)))
    assert set(p) == {"4", "13", "52", "156"}
    assert all(
        row["median_return"] == row["p95_drawdown"] == row["loss_frequency"] == 0
        for row in p.values()
    )
    w = np.full(len(h.columns), 0.08)
    assert projections(h, w) == projections(h, w)
    for row in projections(h, w).values():
        assert row["p05_return"] <= row["median_return"] <= row["p95_return"]
        assert 0 <= row["loss_frequency"] <= 1
        assert 0 <= row["p95_drawdown"] < 1


def test_replay_next_week_fill_deducts_exact_initial_cost():
    h = history() * 0
    fixed = np.zeros(h.shape[1])
    fixed[0] = 0.6
    result = replay(h, POLICIES["medium"], fixed)
    assert np.isclose(result["total_return"], 1 / (1 + 0.0015 * 0.6) - 1)
    assert result["weeks"] == 52


def test_missing_asset_history_is_excluded_without_filling():
    h = history()
    prices = (1 + h).cumprod()
    prices = pd.concat(
        [
            prices.iloc[:1].set_axis([prices.index[0] - pd.Timedelta(days=7)]) * 0 + 1,
            prices,
        ]
    )
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
    data = dict(
        schema_version=1,
        status="REVIEW_REQUIRED",
        execution_enabled=False,
        promotion_enabled=False,
        candidates={
            key: dict(allocations=[dict(weight=1.0, risk_share=1.0)])
            for key in POLICIES
        },
    )
    data["research_id"] = fingerprint(data)
    atomic_json(tmp_path / "recommendations.json", data)
    (tmp_path / "dashboard-report.pdf").write_bytes(b"%PDF-test")
    manifest = dict(
        schema_version=1,
        source_hashes={s: file_hash(s) for s in SOURCES},
        files={
            s: file_hash(tmp_path / s)
            for s in ("recommendations.json", "dashboard-report.pdf")
        },
    )
    atomic_json(tmp_path / "manifest.json", manifest)
    assert verify(tmp_path)["research_id"] == data["research_id"]
    data["status"] = "APPROVED"
    atomic_json(tmp_path / "recommendations.json", data)
    manifest["files"]["recommendations.json"] = file_hash(
        tmp_path / "recommendations.json"
    )
    atomic_json(tmp_path / "manifest.json", manifest)
    with pytest.raises(ValueError, match="identity"):
        verify(tmp_path)
    manifest["source_hashes"] = {}
    atomic_json(tmp_path / "manifest.json", manifest)
    with pytest.raises(ValueError, match="source"):
        verify(tmp_path)


def test_expected_shortfall_is_loss_positive_and_tail_return_is_separate():
    from weekly_portfolios import statistics

    metrics = statistics([-0.2, 0.1, 0.05, 0.02])
    assert metrics["weekly_expected_shortfall"] == pytest.approx(0.2)
    assert metrics["weekly_tail_mean_return"] == pytest.approx(-0.2)
    assert statistics([0.01, 0.02])["weekly_expected_shortfall"] == 0.0


def test_analytic_utility_gradient_matches_independent_central_differences(monkeypatch):
    import weekly_portfolios as module

    original = module.minimize
    checked = []

    def audited(fun, x0, *args, **kwargs):
        w = np.linspace(0.001, 0.003, len(x0))
        _, gradient = fun(w)
        step = 1e-6
        numerical = np.empty(len(w))
        for i in range(len(w)):
            bump = np.zeros(len(w))
            bump[i] = step
            numerical[i] = (fun(w + bump)[0] - fun(w - bump)[0]) / (2 * step)
        assert np.allclose(gradient, numerical, rtol=1e-4, atol=1e-6)
        constraint = kwargs["constraints"]
        analytical = constraint["jac"](w)
        numerical_constraints = np.column_stack([
            (constraint["fun"](w + np.eye(len(w))[i]*step)
             - constraint["fun"](w - np.eye(len(w))[i]*step))/(2*step)
            for i in range(len(w))
        ])
        assert np.allclose(analytical, numerical_constraints, rtol=1e-4, atol=1e-6)
        checked.append(True)
        return original(fun, x0, *args, **kwargs)

    monkeypatch.setattr(module, "minimize", audited)
    h = history()
    allocate(h, POLICIES["medium"])
    assert checked


def test_aggregate_mix_is_data_derived_and_reconciles_to_underlying_holdings():
    from weekly_portfolios import aggregate_fit
    h = history()
    w, cov, expected, mix = aggregate_fit(h)
    assert set(mix) == {'short', 'medium', 'long', 'cash_reserve'}
    assert sum(mix.values()) == pytest.approx(1)
    independently = sum(mix[k] * allocate(h, POLICIES[k])[0] for k in mix if k != 'cash_reserve')
    assert np.allclose(w, independently)
    assert np.isfinite(cov).all() and np.isfinite(expected).all()
    changed = h.copy()
    changed.loc[:, ['SPY', 'VEA', 'VWO', 'QQQ']] -= .015
    changed.loc[:, ['IEF', 'SHY', 'TLT']] += .003
    other = aggregate_fit(changed)
    assert not np.allclose(w, other[0])
    assert not np.allclose(list(mix.values()), list(other[3].values()))


def test_variable_asset_support_and_sampling_uncertainty():
    h = history()
    a = allocate(h, POLICIES['medium'])[0]
    changed = h.copy()
    changed['DBC'] = -.02 + changed['DBC'] * .05
    changed['GLD'] += .008
    b = allocate(changed, POLICIES['medium'])[0]
    assert not np.allclose(a, b)
    assert b[list(h).index('DBC')] == 0
    assert np.count_nonzero(b) <= h.shape[1]
    _, _, shrunk = allocate(h, POLICIES['medium'])
    _, _, raw = allocate(h, POLICIES['medium'], return_estimator='incumbent')
    assert (np.abs(shrunk) <= np.abs(raw)+1e-12).all()


def test_optimizer_rejects_nonfinite_and_insolvent_market_data():
    h = history()
    for bad in [np.inf, np.nan, -1.]:
        corrupted = h.copy()
        corrupted.iloc[-1, 0] = bad
        with pytest.raises(ValueError, match='finite weekly'):
            allocate(corrupted, POLICIES['aggregate'])


def test_asset_count_can_fall_to_cash_without_borrowing_or_forced_holdings():
    h = history()
    normal = allocate(h, POLICIES['medium'])[0]
    deteriorating = h * 0 - .01
    defensive = allocate(deteriorating, POLICIES['medium'])[0]
    assert np.count_nonzero(normal) > np.count_nonzero(defensive)
    assert np.count_nonzero(defensive) == 0
    assert defensive.sum() == 0
    from weekly_portfolios import aggregate_fit
    assert np.count_nonzero(aggregate_fit(deteriorating)[0]) == 0


def test_cash_does_not_dilute_signed_risk_concentration_guard():
    from weekly_portfolios import verify_risk_concentration
    covariance = np.eye(2)*.04
    for exposure in [1., .001]:
        with pytest.raises(ValueError, match='35% safeguard'):
            verify_risk_concentration(np.array([.9, .1])*exposure, covariance)
    verify_risk_concentration(np.zeros(2), covariance)
