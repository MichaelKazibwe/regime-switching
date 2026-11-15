"""R3E.9 deterministic PortfolioOptimizer tail-risk governance tests."""

import numpy as np

from core_constants import REGIME_VOL_TARGETS
from portfoliooptimizer import PortfolioOptimizer
from riskgovernor import PortfolioRiskGovernor, RiskGovernorAction


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


def _regime() -> str:
    return next(iter(REGIME_VOL_TARGETS))


def _build(governor):
    return PortfolioOptimizer(
        risk_budget_engine=_RiskBudgetEngine(),
        constraints=_Constraints(),
        vol_target_engine=_VolatilityTargeting(),
        risk_governor=governor,
    )


def test_optimizer_passes_tail_risk_to_governor():
    governor = PortfolioRiskGovernor(
        max_annual_volatility=10.0,
        max_leverage=2.0,
        max_position_weight=1.0,
        max_risk_contribution_pct=1.0,
        max_aggregate_tail_loss_pct=0.05,
    )
    optimizer = _build(governor)

    result = optimizer.optimize(
        covariance=np.diag([1e-6, 1e-6]),
        regime=_regime(),
        asset_order=("SPY", "TLT"),
        tail_risk={
            "aggregate_tail_loss": 12_000.0,
            "aggregate_tail_loss_pct": 0.12,
            "tail_loss_source": "historical_stress",
        },
    )

    governance = result["risk_governance"]
    assert governance["action"] == RiskGovernorAction.REDUCE.value
    assert governance["approved"] is True
    assert np.isclose(governance["scale"], 0.05 / 0.12)
    assert np.isclose(governance["governed_aggregate_tail_loss_pct"], 0.05)
    assert result["tail_risk_supplied"] is True
    assert result["tail_risk_governance_enabled"] is True


def test_optimizer_remains_backward_compatible_without_tail_risk():
    governor = PortfolioRiskGovernor(
        max_annual_volatility=10.0,
        max_leverage=2.0,
        max_position_weight=1.0,
        max_risk_contribution_pct=1.0,
    )
    optimizer = _build(governor)

    result = optimizer.optimize(
        covariance=np.diag([1e-6, 1e-6]),
        regime=_regime(),
        asset_order=("SPY", "TLT"),
    )

    assert result["risk_governance"]["action"] == RiskGovernorAction.PASS.value
    assert result["tail_risk_supplied"] is False
    assert result["tail_risk_governance_enabled"] is False


def test_optimizer_tail_governance_never_increases_weights():
    governor = PortfolioRiskGovernor(
        max_annual_volatility=10.0,
        max_leverage=2.0,
        max_position_weight=1.0,
        max_risk_contribution_pct=1.0,
        max_aggregate_tail_loss_pct=0.05,
    )
    optimizer = _build(governor)

    result = optimizer.optimize(
        covariance=np.diag([1e-6, 1e-6]),
        regime=_regime(),
        asset_order=("SPY", "TLT"),
        tail_risk={"aggregate_tail_loss_pct": 0.20},
    )

    governed = np.asarray(result["risk_governed_weights"], dtype=float)
    candidate = np.asarray(result["atr_sized_weights"], dtype=float)
    assert np.all(governed <= candidate + 1e-10)
    assert result["risk_governance"]["scale"] <= 1.0


def test_optimizer_configuration_accepts_tail_limit():
    governor = PortfolioRiskGovernor(
        max_annual_volatility=0.20,
        max_leverage=1.0,
        max_position_weight=0.50,
        max_risk_contribution_pct=0.50,
        max_aggregate_tail_loss_pct=0.10,
    )
    optimizer = _build(governor)
    assert optimizer.API_VERSION == "2.4.0"
    assert optimizer.health_check()["healthy"] is True


def run_tests():
    tests = [
        test_optimizer_passes_tail_risk_to_governor,
        test_optimizer_remains_backward_compatible_without_tail_risk,
        test_optimizer_tail_governance_never_increases_weights,
        test_optimizer_configuration_accepts_tail_limit,
    ]
    for test in tests:
        test()
    print(f"PortfolioOptimizer R3E.9 tests: {len(tests)}/{len(tests)} passed.")
    print("R3E.9 STATUS: PASS")


if __name__ == "__main__":
    run_tests()
