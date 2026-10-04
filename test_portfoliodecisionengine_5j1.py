
"""R3E.9 decision-boundary tests for forwarding aggregated tail risk."""

import numpy as np

from portfoliodecisionengine import PortfolioDecisionEngine


class _RegimeModel:
    def classify(self, unemployment, yield_spread, inflation):
        return "expansion"


class _Forecaster:
    def forecast(self, prices):
        return {"SPY": 0.05, "TLT": 0.03}


class _Covariance:
    def estimate(self, **kwargs):
        return np.diag([1e-6, 1e-6])


class _RiskModel:
    def risk_contributions(self, weights, covariance, tickers):
        return {ticker: 0.01 for ticker in tickers}


class _Optimizer:
    def __init__(self):
        self.received_tail_risk = None
        self.last_volatility_diagnostics = {}

    def optimize(
        self,
        covariance,
        regime,
        asset_order,
        prices=None,
        tail_risk=None,
    ):
        self.received_tail_risk = tail_risk
        return {"weights": np.array([0.50, 0.50])}


class _GovernedReduceOptimizer:
    """
    Test double representing an optimizer whose risk-governor stage
    has already reduced total invested exposure to 80%.
    """

    def __init__(self):
        self.received_tail_risk = None
        self.last_volatility_diagnostics = {
            "risk_governance": {
                "action": "REDUCE",
                "approved": True,
                "scale": 0.80,
            },
            "risk_governance_action": "REDUCE",
            "risk_governance_scale": 0.80,
        }

    def optimize(
        self,
        covariance,
        regime,
        asset_order,
        prices=None,
        tail_risk=None,
    ):
        self.received_tail_risk = tail_risk

        return {
            "weights": np.array([0.40, 0.40]),
        }


class _Constraints:
    def enforce(self, weights=None, **kwargs):
        return dict(weights)


def _build_engine(optimizer):
    return PortfolioDecisionEngine(
        regime_model=_RegimeModel(),
        expected_return_forecaster=_Forecaster(),
        covariance_engine=_Covariance(),
        regime_covariance=None,
        ensemble_covariance=None,
        black_litterman=None,
        optimizer=optimizer,
        constraints=_Constraints(),
        risk_model=_RiskModel(),
        risk_contribution_analyzer=None,
        scenario_engine=None,
    )



def test_risk_governor_reduction_survives_decision_boundary():
    """
    5J.1 integration boundary:

    If the optimizer/risk-governor layer deliberately reduces total
    invested exposure from 100% to 80%, the PortfolioDecisionEngine
    must not silently normalize the weights back to 100%.
    """
    optimizer = _GovernedReduceOptimizer()
    engine = _build_engine(optimizer)

    decision = engine.decide(
        portfolio={"weights": {"SPY": 0.5, "TLT": 0.5}},
        expected_returns={"SPY": 0.05, "TLT": 0.03},
        covariance=np.diag([1e-6, 1e-6]),
    )

    assert decision.approved is True

    # The Risk Governor reduction must survive both normalization
    # boundaries inside PortfolioDecisionEngine.
    assert np.isclose(
        sum(decision.weights.values()),
        0.80,
        atol=1e-10,
    )
    assert np.isclose(
        decision.weights["SPY"],
        0.40,
        atol=1e-10,
    )
    assert np.isclose(
        decision.weights["TLT"],
        0.40,
        atol=1e-10,
    )
