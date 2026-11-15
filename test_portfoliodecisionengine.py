
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
        drawdown_risk_engine=None,
    )


def test_decision_engine_forwards_tail_risk():
    optimizer = _Optimizer()

    engine = _build_engine(optimizer)

    tail_risk = {
        "aggregate_tail_loss": 8_000.0,
        "aggregate_tail_loss_pct": 0.08,
        "tail_loss_source": "historical_stress",
    }

    decision = engine.decide(
        portfolio={"weights": {"SPY": 0.5, "TLT": 0.5}},
        expected_returns={"SPY": 0.05, "TLT": 0.03},
        covariance=np.diag([1e-6, 1e-6]),
        tail_risk=tail_risk,
    )

    assert decision.approved is True
    assert optimizer.received_tail_risk == tail_risk
    assert decision.diagnostics["tail_risk_supplied"] is True


def test_decision_engine_remains_backward_compatible():
    optimizer = _Optimizer()

    engine = _build_engine(optimizer)

    decision = engine.decide(
        portfolio={"weights": {"SPY": 0.5, "TLT": 0.5}},
        expected_returns={"SPY": 0.05, "TLT": 0.03},
        covariance=np.diag([1e-6, 1e-6]),
    )

    assert decision.approved is True
    assert optimizer.received_tail_risk is None
    assert decision.diagnostics["tail_risk_supplied"] is False


def test_risk_governor_reduction_survives_decision_boundary():
    """
    R3E.9 integration boundary:

    If the optimizer/risk-governor layer deliberately reduces total
    invested exposure from 100% to 80%, the PortfolioDecisionEngine
    must not silently normalize the weights back to 100%.

    Expected governed result:
        SPY = 0.40
        TLT = 0.40
        Total invested exposure = 0.80
    """

    optimizer = _GovernedReduceOptimizer()

    engine = _build_engine(optimizer)

    decision = engine.decide(
        portfolio={"weights": {"SPY": 0.5, "TLT": 0.5}},
        expected_returns={"SPY": 0.05, "TLT": 0.03},
        covariance=np.diag([1e-6, 1e-6]),
    )

    assert decision.approved is True

    # The risk-governor reduction must survive the decision boundary.
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

    # Confirm the governance decision is still visible at the
    # PortfolioDecision boundary.
    assert decision.diagnostics["risk_governance_action"] == "REDUCE"

    assert np.isclose(
        decision.diagnostics["risk_governance_scale"],
        0.80,
        atol=1e-10,
    )


def run_tests():
    tests = [
        test_decision_engine_forwards_tail_risk,
        test_decision_engine_remains_backward_compatible,
        test_risk_governor_reduction_survives_decision_boundary,
    ]

    for test in tests:
        test()

    print(
        f"PortfolioDecisionEngine R3E.9 tests: "
        f"{len(tests)}/{len(tests)} passed."
    )
    print("R3E.9 STATUS: PASS")


if __name__ == "__main__":
    run_tests()
