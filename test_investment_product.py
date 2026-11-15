from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from assetuniverse import AssetUniverse, PRODUCTION_ASSETS
from clientmandate import CashRate, ClientMandate
from investmentcatalog import catalogue
from productallocation import (
    PlanningCosts,
    allocate_plan,
    base_currency_prices,
    estimate_inputs,
    stress_matrix,
)
from productexecutioncost import MarketQuote, conservative_sale_tax_fraction
from productrelease import PRODUCT_CHECKS, readiness, release_manifest
from productreport import private_write, render_report
from productsimulation import simulate_plans
from recommendationrisk import RecommendationRiskState
from recommendationservice import recommend


STAMP = "2025-10-29T21:00:00+00:00"


def mandate(profile="balanced", **changes):
    value = ClientMandate(
        "unit-client",
        profile,
        "USD",
        "TEST",
        "TEST",
        7.0,
        100000.0,
        0.20,
        0.20,
        investment_experience="experienced",
        allow_alternatives=True,
        tax_account_type="tax_exempt",
    )
    return replace(value, **changes)


def prices():
    dates = pd.bdate_range(end="2025-10-29", periods=600)
    symbols = list(catalogue())
    rng = np.random.default_rng(3105)
    common = rng.normal(0, 0.004, (len(dates), 1))
    values = rng.normal(0.0001, 0.003, (len(dates), len(symbols))) + common
    for symbol, scale in [("SGOV", 0.01), ("SHY", 0.10), ("IEF", 0.4)]:
        values[:, symbols.index(symbol)] *= scale
    return pd.DataFrame(
        100 * np.cumprod(1 + values, axis=0), index=dates, columns=symbols
    )


def inputs(profile="balanced", **changes):
    m = mandate(profile, **changes)
    rate = CashRate("USD", 0.02, STAMP, "synthetic-test-source", False)
    r, mu, u, c, excluded = estimate_inputs(prices(), m, rate, STAMP)
    return m, rate, r, mu, u, c, excluded


def test_28_menu_is_separate_from_14_execution_universe():
    assert len(catalogue()) == len(AssetUniverse.product_menu()) == 28
    assert catalogue()["ALLW"].benchmark_only
    assert not catalogue()["DBMF"].legacy_paper_eligible
    assert set(AssetUniverse.production().tickers) == set(PRODUCTION_ASSETS)
    assert AssetUniverse.production().size == 14


def test_original_goal_and_low_financial_capacity_are_not_silently_approved():
    m = mandate(
        horizon_years=3.0,
        target_total_return=0.5,
        drawdown_preference=0.05,
        financial_loss_capacity=0.05,
    )
    result = m.assessment()
    assert result["required_annual_return"] is None
    assert (
        "RETURN_LOSS_COMBINATION_NOT_SUPPORTED_BY_PROJECT_EVIDENCE"
        not in result["planning_reasons"]
    )
    assert not result["loss_bound_guaranteed"]
    with pytest.raises(ValueError):
        mandate(financial_loss_capacity=float("nan")).validate()
    with pytest.raises(ValueError):
        mandate(account_value=True).validate()


def test_currency_conversion_is_explicit_and_not_double_counted():
    p = prices()
    fx = pd.Series(np.linspace(0.9, 1.0, len(p)), index=p.index)
    result = base_currency_prices(p, "EUR", fx)
    assert result.iloc[-1, 0] == pytest.approx(p.iloc[-1, 0])
    assert result.iloc[0, 0] == pytest.approx(p.iloc[0, 0] * 0.9)
    with pytest.raises(ValueError):
        base_currency_prices(p, "EUR", fx.iloc[1:])
    with pytest.raises(ValueError):
        base_currency_prices(p, "USD", fx)


def test_rate_provenance_freshness_and_history_eligibility():
    rate = CashRate("USD", 0.02, STAMP, "test")
    assert (1 + rate.daily_rate(STAMP)) ** 252 - 1 == pytest.approx(0.02)
    with pytest.raises(ValueError):
        rate.daily_rate("2025-11-20T21:00:00Z")
    with pytest.raises(ValueError):
        rate.daily_rate("2025-10-28T21:00:00Z")
    with pytest.raises(ValueError):
        replace(rate, verified="false").daily_rate(STAMP)
    m, _, r, _, _, _, excluded = inputs(allow_alternatives=False)
    assert "ALLW" not in r and "DBMF" not in r
    assert excluded["DBMF"] == "ALTERNATIVES_NOT_PERMITTED"
    p = prices()
    p.loc[p.index[30], "SPY"] = np.nan
    with pytest.raises(ValueError, match="Interior"):
        estimate_inputs(p, m, rate, STAMP)


@pytest.mark.parametrize("profile", ["preservation", "balanced", "growth"])
def test_optimizer_and_reference_reconcile_capital_stress_and_liquidity(profile):
    m, _, r, mu, u, c, _ = inputs(profile)
    result = allocate_plan(r, mu, u, c, m)
    assert result["status"] == "PLANNING_PREVIEW"
    assert result["executable"] is False
    assert result["constraint_residual"] <= 1e-6
    for key in ("weights", "strategic_reference"):
        weights = np.array([result[key][s] for s in r])
        assert weights.sum() == pytest.approx(1)
        assert weights.min() >= -1e-8
        assert weights[:-1].max() <= 0.25 + 1e-8
        assert weights[-1] >= result["cash_floor"] - 1e-8
        assert max(-stress_matrix(list(r)) @ weights) <= m.drawdown_preference + 1e-8
    assert sum(result["variance_contributions"].values()) == pytest.approx(1)
    assert result["macro_alpha_enabled"] is False


def test_conflicting_growth_and_loss_constraints_block_instead_of_loosen():
    m, _, r, mu, u, c, _ = inputs(
        "growth", drawdown_preference=0.01, financial_loss_capacity=0.01
    )
    result = allocate_plan(r, mu, u, c, m)
    assert result["status"] == "BLOCKED_INFEASIBLE_MANDATE"
    assert result["weights"] is None


def test_full_liquidity_reserve_produces_cash_only_and_zero_variance():
    m, _, r, mu, u, c, _ = inputs(near_term_liquidity=100000.0)
    result = allocate_plan(r, mu, u, c, m)
    assert result["weights"]["USD_CASH"] == pytest.approx(1)
    assert result["planning_annual_volatility"] == pytest.approx(0)
    assert result["estimated_rebalance_cost_fraction"] == pytest.approx(0)


def test_rebalancing_existing_optimum_holds_without_charging_spurious_costs():
    m, _, r, mu, u, c, _ = inputs()
    first = allocate_plan(r, mu, u, c, m)
    current = np.array([first["weights"][s] for s in r])
    second = allocate_plan(r, mu, u, c, m, current=current)
    assert second["recommendation_action"] == "HOLD"
    assert second["estimated_rebalance_cost_fraction"] == 0
    assert second["weights"] == pytest.approx(first["weights"])


def test_optimizer_rejects_invalid_inputs_and_cash_is_not_charged_as_an_etf():
    m, _, r, mu, u, c, _ = inputs()
    with pytest.raises(ValueError):
        allocate_plan(r, mu, u, c, m, current=np.ones(len(r.columns)))
    with pytest.raises(ValueError):
        allocate_plan(r, mu, u, c, m, costs=PlanningCosts(commission=-0.01))
    bad = c.copy()
    bad[0, 0] = -1
    with pytest.raises(ValueError):
        allocate_plan(r, mu, u, bad, m)


def test_risk_state_survives_restart_reenters_gradually_and_remembers_breaches():
    s = RecommendationRiskState()
    s.update(0.97, "2025-01-01", loss_preference=0.05, trend_confirmed=False)
    before = s.exposure_multiplier
    restored = RecommendationRiskState.restore(s.payload())
    for day in range(2, 7):
        restored.update(
            0.97, f"2025-01-{day:02}", loss_preference=0.05, trend_confirmed=True
        )
    assert restored.peak == 1
    assert restored.exposure_multiplier == pytest.approx(before + 0.05)
    restored.update(0.93, "2025-01-07", loss_preference=0.05, trend_confirmed=True)
    assert restored.review_required and restored.prior_breach
    restored.update(1.1, "2025-01-08", loss_preference=0.05, trend_confirmed=True)
    assert restored.review_required and restored.peak == 1.1
    restored.acknowledge_review(
        "unit-reviewer", "a" * 64, "2025-01-08", loss_preference=0.05
    )
    assert (
        not restored.review_required and restored.prior_breach and restored.peak == 1.1
    )
    restored.update(1.1, "2025-01-09", loss_preference=0.05, trend_confirmed=True)
    assert not restored.review_required
    with pytest.raises(ValueError, match="Conflicting"):
        restored.update(1.2, "2025-01-09", loss_preference=0.05, trend_confirmed=True)


def test_observed_quotes_block_stale_future_and_excessive_capacity():
    q = MarketQuote(99.0, 101.0, 1e7, 0.01, STAMP, "USD", "test-source")
    result = q.estimate(1000.0, STAMP)
    assert result["cost"] > 10 and not result["executable"]
    assert q.estimate(1e6, STAMP)["status"] == "BLOCKED_CAPACITY"
    with pytest.raises(ValueError):
        q.estimate(1000.0, "2025-10-29T21:02:00Z")
    with pytest.raises(ValueError):
        replace(q, bid=102.0).estimate(1000.0, STAMP)
    assert conservative_sale_tax_fraction(
        [{"basis": 80.0, "market_value": 100.0}], 0.25
    ) == pytest.approx(0.05)


def test_joint_simulation_pairs_targets_and_compounds_cash_exactly():
    _, _, r, mu, _, _, _ = inputs()
    w = np.zeros(len(r.columns))
    w[-1] = 1
    result = simulate_plans(r, {"first": w, "same": w}, mu, years=1, paths=100)
    assert result["summary"]["first"] == result["summary"]["same"]
    assert result["summary"]["first"]["median_total_return"] == pytest.approx(mu[-1])
    assert result["summary"]["first"]["p95_drawdown_magnitude"] == pytest.approx(0)
    assert result["fan"]["first"] == result["fan"]["same"]


def test_qualification_default_is_closed_and_missing_metadata_is_visible():
    m = mandate(jurisdiction="", tax_residence="")
    result = readiness(release_manifest(), m, ["SPY"], now=STAMP)
    assert not result["public_recommendations_enabled"]
    assert result["unapproved_instruments"] == ["SPY"]
    assert all(v == "BLOCKED" for v in result["checks"].values())


def test_release_scoped_receipts_verify_artifacts_and_instrument_coverage(tmp_path):
    m = mandate()
    manifest = release_manifest()
    artifact = tmp_path / "review.txt"
    artifact.write_text("human-review-fixture")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    (tmp_path / "records").mkdir()
    for check in PRODUCT_CHECKS:
        receipt = {
            "release_id": manifest["release_id"],
            "jurisdiction": "TEST",
            "service_mode": manifest["service_mode"],
            "check": check,
            "status": "PASS",
            "reviewer": "unit-test-reviewer",
            "recorded_at": STAMP,
            "artifacts": [{"path": "review.txt", "sha256": digest}],
            "instruments": ["SPY"],
            "mandate_sha256": hashlib.sha256(
                json.dumps(asdict(m), sort_keys=True).encode()
            ).hexdigest(),
        }
        (tmp_path / "records" / f"{check}.json").write_text(json.dumps(receipt))
    approved = readiness(manifest, m, ["SPY"], now=STAMP, root=tmp_path)
    assert (
        approved["public_recommendations_enabled"]
        and not approved["broker_submission_enabled"]
    )
    assert not readiness(manifest, m, ["SPY", "VEA"], now=STAMP, root=tmp_path)[
        "public_recommendations_enabled"
    ]
    artifact.write_text("changed")
    with pytest.raises(ValueError, match="Changed"):
        readiness(manifest, m, ["SPY"], now=STAMP, root=tmp_path)


def test_service_is_non_executable_audits_inputs_and_preserves_original_goal(tmp_path):
    m = mandate(
        "preservation",
        horizon_years=3.0,
        target_total_return=0.5,
        drawdown_preference=0.05,
        financial_loss_capacity=0.05,
    )
    rate = CashRate("USD", 0.0, STAMP, "unit-rate")
    result = recommend(
        m, prices(), rate, decision_time=STAMP, historical_preview=True, paths=100
    )
    assert not result["qualification"]["public_recommendations_enabled"]
    assert result["kind"] == "NON_EXECUTABLE_PORTFOLIO_RECOMMENDATION"
    assert (
        "RETURN_LOSS_COMBINATION_NOT_SUPPORTED_BY_PROJECT_EVIDENCE"
        not in result["mandate_assessment"]["planning_reasons"]
    )
    second = recommend(
        m,
        prices(),
        replace(rate, annual_effective_net_rate=0.02),
        decision_time=STAMP,
        historical_preview=True,
        paths=100,
    )
    assert result["recommendation_id"] != second["recommendation_id"]
    path = tmp_path / "index.html"
    render_report(result, path)
    html = path.read_text()
    assert "OPERATOR_PREVIEW_ONLY" in html and "<canvas" in html and "sha256-" in html
    assert "https://" not in html
    assert path.stat().st_mode & 0o777 == 0o600
    private_write(tmp_path / "result.json", json.dumps(result, allow_nan=False))


def test_current_mode_rejects_backdated_decisions():
    m = mandate()
    with pytest.raises(ValueError, match="historical preview"):
        recommend(
            m,
            prices(),
            CashRate("USD", 0.0, STAMP, "unit"),
            decision_time=STAMP,
            clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
            paths=100,
        )


def test_annual_tax_drag_and_fx_are_required_explicitly_for_relevant_clients():
    m = mandate(tax_account_type="taxable")
    result = recommend(
        m,
        prices(),
        CashRate("USD", 0.0, STAMP, "unit"),
        decision_time=STAMP,
        historical_preview=True,
        paths=100,
    )
    assert "ANNUAL_TAX_DRAG_UNAVAILABLE" in result["hard_blocks"]
    with pytest.raises(ValueError, match="base-currency"):
        recommend(
            replace(m, base_currency="EUR"),
            prices(),
            CashRate("EUR", 0.0, STAMP, "unit"),
            decision_time=STAMP,
            historical_preview=True,
            paths=100,
        )


def test_cash_liquidity_and_stress_preferences_include_initial_costs():
    m, _, r, mu, u, c, _ = inputs(near_term_liquidity=20000.0)
    result = allocate_plan(r, mu, u, c, m)
    assert result["weights"] is not None
    net_cash = (
        result["weights"]["USD_CASH"]
        * (1 - result["estimated_rebalance_cost_fraction"])
        * m.account_value
    )
    assert net_cash >= m.near_term_liquidity - 1e-6
    assert (
        max(result["hypothetical_stress_losses_including_costs"])
        <= m.drawdown_preference + 1e-8
    )


def test_platform_fee_and_fund_expense_inputs_are_explicit_and_audited():
    m = mandate("preservation", near_term_liquidity=100000.0, annual_platform_fee=0.01)
    rate = CashRate("USD", 0.02, STAMP, "unit-rate")
    result = recommend(
        m, prices(), rate, decision_time=STAMP, historical_preview=True, paths=100
    )
    assert result["simulations"]["summary"]["proposed"][
        "median_total_return"
    ] == pytest.approx(((1.02) * 0.99) ** 7 - 1)
    assert "FUND_EXPENSE_INPUTS_UNVERIFIED" in result["hard_blocks"]
