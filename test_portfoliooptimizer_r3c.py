"""
======================================================================
PORTFOLIO OPTIMIZER R3C.3 INTEGRATION TESTS
======================================================================

Deterministic tests for PortfolioRiskGovernor integration into the
production PortfolioOptimizer.
======================================================================
"""

import numpy as np

from core_constants import REGIME_VOL_TARGETS
from portfoliooptimizer import PortfolioOptimizer
from riskgovernor import PortfolioRiskGovernor, RiskGovernorAction


def _regime() -> str:
    """Return one configured production portfolio regime."""
    return next(iter(REGIME_VOL_TARGETS))


class _RiskBudgetEngine:
    def get_target_budgets(self, regime, assets):
        return {asset: 1.0 for asset in assets}

    def optimize(self, covariance, risk_budget):
        values = np.asarray(risk_budget, dtype=float)
        return values / values.sum()


class _Constraints:
    MAX_WEIGHT = 1.0

    def enforce(self, weights):
        values = np.asarray(weights, dtype=float)
        return {"weights": values.copy(), "cash": 0.0}


class _VolatilityTargeting:
    def scale_weights(
        self,
        weights,
        covariance,
        target_vol,
        max_leverage=None,
        annualize=False,
        periods_per_year=252,
    ):
        return np.asarray(weights, dtype=float).copy()


def _build_optimizer(governor: PortfolioRiskGovernor) -> PortfolioOptimizer:
    return PortfolioOptimizer(
        risk_budget_engine=_RiskBudgetEngine(),
        constraints=_Constraints(),
        vol_target_engine=_VolatilityTargeting(),
        risk_governor=governor,
    )


def test_risk_governor_reduction_is_applied() -> None:
    governor = PortfolioRiskGovernor(
        max_annual_volatility=0.10,
        max_leverage=1.00,
        max_position_weight=1.00,
        max_risk_contribution_pct=1.00,
        tolerance=1e-10,
        periods_per_year=252,
    )

    optimizer = _build_optimizer(governor)

    result = optimizer.optimize(
        covariance=np.diag([0.0004, 0.0004]),
        regime=_regime(),
        asset_order=("SPY", "TLT"),
    )

    governance = result["risk_governance"]

    assert governance["action"] == RiskGovernorAction.REDUCE.value
    assert governance["approved"] is True
    assert governance["scale"] < 1.0
    assert np.isclose(
        governance["governed_annualized_volatility"],
        0.10,
        atol=1e-10,
    )

    governed = np.asarray(result["risk_governed_weights"], dtype=float)
    final = np.asarray(result["weights"], dtype=float)

    assert np.all(governed <= 0.50 + 1e-10)
    assert np.all(final <= governed + 1e-10)
    assert result["risk_governance_enabled"] is True


def test_risk_governor_pass_is_preserved() -> None:
    governor = PortfolioRiskGovernor(
        max_annual_volatility=0.50,
        max_leverage=2.00,
        max_position_weight=1.00,
        max_risk_contribution_pct=1.00,
    )

    optimizer = _build_optimizer(governor)

    result = optimizer.optimize(
        covariance=np.diag([0.000025, 0.000025]),
        regime=_regime(),
        asset_order=("SPY", "TLT"),
    )

    governance = result["risk_governance"]

    assert governance["action"] == RiskGovernorAction.PASS.value
    assert governance["approved"] is True
    assert np.isclose(governance["scale"], 1.0)


def test_risk_governor_rejection_fails_optimizer_closed() -> None:
    governor = PortfolioRiskGovernor(
        max_annual_volatility=10.0,
        max_leverage=2.00,
        max_position_weight=0.40,
        max_risk_contribution_pct=1.00,
    )

    optimizer = _build_optimizer(governor)

    try:
        optimizer.optimize(
            covariance=np.diag([0.000001, 0.000001]),
            regime=_regime(),
            asset_order=("SPY", "TLT"),
        )
    except Exception as exc:
        assert "Risk Governor rejected" in str(exc)
        return

    raise AssertionError(
        "PortfolioOptimizer must fail closed when the Risk Governor rejects."
    )


def test_risk_governor_cannot_increase_exposure() -> None:
    governor = PortfolioRiskGovernor(
        max_annual_volatility=0.10,
        max_leverage=1.00,
        max_position_weight=1.00,
        max_risk_contribution_pct=1.00,
    )

    optimizer = _build_optimizer(governor)

    result = optimizer.optimize(
        covariance=np.diag([0.0004, 0.0004]),
        regime=_regime(),
        asset_order=("SPY", "TLT"),
    )

    governed = np.asarray(result["risk_governed_weights"], dtype=float)
    candidate = np.asarray(result["atr_sized_weights"], dtype=float)

    assert np.all(governed <= candidate + 1e-10)


def run_tests() -> None:
    tests = [
        test_risk_governor_reduction_is_applied,
        test_risk_governor_pass_is_preserved,
        test_risk_governor_rejection_fails_optimizer_closed,
        test_risk_governor_cannot_increase_exposure,
    ]

    passed = 0
    for test in tests:
        test()
        passed += 1

    print(f"PortfolioOptimizer R3C.3 tests: {passed}/{len(tests)} passed.")
    print("R3C.3 STATUS: PASS")


if __name__ == "__main__":
    run_tests()
