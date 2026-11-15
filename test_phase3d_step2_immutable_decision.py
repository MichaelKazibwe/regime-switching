"""Phase 3D Step 2 regression tests: immutable portfolio decisions."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from portfoliodecisionengine import PortfolioDecision


def _decision_payload() -> dict:
    return {
        "decision_id": "PDEC-IMMUTABLE-00000001",
        "status": "APPROVED",
        "approved": True,
        "regime": "EXPANSION",
        "tickers": ["SPY", "TLT"],
        "weights": {"SPY": 0.6, "TLT": 0.4},
        "expected_returns": {"SPY": 0.08, "TLT": 0.03},
        "covariance": {
            "SPY": {"SPY": 0.04, "TLT": 0.01},
            "TLT": {"SPY": 0.01, "TLT": 0.02},
        },
        "portfolio_return": 0.06,
        "portfolio_volatility": 0.17,
        "portfolio_variance": 0.0289,
        "gross_exposure": 1.0,
        "net_exposure": 1.0,
        "number_of_positions": 2,
        "risk_contributions": {"SPY": 0.02, "TLT": 0.0089},
        "risk_contribution_pct": {"SPY": 0.69, "TLT": 0.31},
        "scenario_results": {
            "BASE": {"return": 0.06, "metrics": {"drawdown": 0.05}},
            "RECESSION": {"return": -0.02},
        },
        "diagnostics": {"model": {"name": "test", "version": 1}},
        "warnings": ["example warning"],
        "errors": [],
        "timestamp": "2026-09-07T00:00:00+00:00",
        "api_version": "1.0.0",
    }


def test_top_level_decision_is_frozen() -> None:
    decision = PortfolioDecision.from_dict(_decision_payload())

    with pytest.raises(FrozenInstanceError):
        decision.status = "REJECTED"  # type: ignore[misc]


def test_weights_are_immutable() -> None:
    decision = PortfolioDecision.from_dict(_decision_payload())

    with pytest.raises(TypeError):
        decision.weights["SPY"] = 0.1  # type: ignore[index]


def test_nested_covariance_is_immutable() -> None:
    decision = PortfolioDecision.from_dict(_decision_payload())

    with pytest.raises(TypeError):
        decision.covariance["SPY"]["TLT"] = 0.99  # type: ignore[index]


def test_nested_diagnostics_and_scenarios_are_immutable() -> None:
    decision = PortfolioDecision.from_dict(_decision_payload())

    with pytest.raises(TypeError):
        decision.diagnostics["model"]["version"] = 99  # type: ignore[index]

    with pytest.raises(TypeError):
        decision.scenario_results["BASE"]["metrics"]["drawdown"] = 0.99  # type: ignore[index]


def test_constructor_defensively_copies_mutable_inputs() -> None:
    payload = _decision_payload()
    weights = payload["weights"]
    diagnostics = payload["diagnostics"]
    decision = PortfolioDecision.from_dict(payload)

    weights["SPY"] = 0.01
    diagnostics["model"]["version"] = 99

    assert decision.weights["SPY"] == 0.6
    assert decision.diagnostics["model"]["version"] == 1


def test_to_dict_returns_fresh_mutable_serialization_state() -> None:
    decision = PortfolioDecision.from_dict(_decision_payload())

    first = decision.to_dict()
    first["weights"]["SPY"] = 0.01
    first["diagnostics"]["model"]["version"] = 99

    second = decision.to_dict()
    assert second["weights"]["SPY"] == 0.6
    assert second["diagnostics"]["model"]["version"] == 1


def test_serialization_round_trip_preserves_decision_value() -> None:
    decision = PortfolioDecision.from_dict(_decision_payload())
    restored = PortfolioDecision.from_dict(decision.to_dict())

    assert restored == decision
    assert restored.to_dict() == decision.to_dict()
