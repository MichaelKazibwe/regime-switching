"""Dedicated regression tests for R3E.7 TailAggregationEngine."""

from __future__ import annotations

import numpy as np
import pytest

from tailaggregation import TailAggregationEngine, TailAggregationError


def test_probability_tail_is_converted_to_pnl() -> None:
    engine = TailAggregationEngine()

    result = engine.aggregate(
        initial_equity=200_000.0,
        tail_risk={
            "confidence": 0.95,
            "var": 0.025,
            "cvar": 0.05,
        },
    )

    assert np.isclose(result.var_loss, 5_000.0)
    assert np.isclose(result.cvar_loss, 10_000.0)
    assert np.isclose(result.aggregate_tail_loss, 10_000.0)
    assert result.tail_loss_source == "historical_cvar"


def test_scenario_envelope_uses_maximum_not_sum() -> None:
    engine = TailAggregationEngine()

    result = engine.aggregate_scenario_losses(
        deterministic_stress={"portfolio_loss": 4_000.0},
        historical_stress={"worst_loss": 9_000.0},
        factor_stress={"portfolio_loss": 7_000.0},
    )

    assert np.isclose(result["scenario_loss_envelope"], 9_000.0)
    assert result["tail_loss_source"] == "historical_stress"
    assert not np.isclose(
        result["scenario_loss_envelope"],
        20_000.0,
    )


def test_cvar_and_scenario_are_not_double_counted() -> None:
    engine = TailAggregationEngine()

    result = engine.aggregate(
        initial_equity=100_000.0,
        tail_risk={
            "confidence": 0.95,
            "var": 0.04,
            "cvar": 0.08,
        },
        deterministic_stress={"portfolio_loss": 6_000.0},
        historical_stress={"worst_loss": 5_000.0},
        factor_stress={"portfolio_loss": 4_000.0},
    )

    assert np.isclose(result.cvar_loss, 8_000.0)
    assert np.isclose(result.scenario_loss_envelope, 6_000.0)
    assert np.isclose(result.aggregate_tail_loss, 8_000.0)
    assert result.tail_loss_source == "historical_cvar"


def test_volatility_stress_is_reported_but_not_fabricated_as_loss() -> None:
    engine = TailAggregationEngine()

    result = engine.aggregate(
        initial_equity=100_000.0,
        volatility_correlation_stress={
            "baseline_volatility": 0.12,
            "stressed_volatility": 0.20,
            "volatility_change_pct": 2.0 / 3.0,
        },
    )

    assert np.isclose(result.baseline_volatility, 0.12)
    assert np.isclose(result.stressed_volatility, 0.20)
    assert np.isclose(result.volatility_change_pct, 2.0 / 3.0)
    assert result.aggregate_tail_loss is None


def test_exposure_and_component_provenance() -> None:
    engine = TailAggregationEngine()

    result = engine.aggregate(
        initial_equity=100_000.0,
        deterministic_stress={
            "portfolio_loss": 1_000.0,
            "gross_exposure": 1.4,
            "net_exposure": 0.8,
        },
    )

    assert np.isclose(result.gross_exposure, 1.4)
    assert np.isclose(result.net_exposure, 0.8)
    assert result.available_components == ("deterministic_stress",)


def test_invalid_negative_loss_is_rejected() -> None:
    engine = TailAggregationEngine()

    with pytest.raises(TailAggregationError):
        engine.aggregate(
            initial_equity=100_000.0,
            deterministic_stress={"portfolio_loss": -1.0},
        )


def test_invalid_tail_order_is_rejected() -> None:
    engine = TailAggregationEngine()

    with pytest.raises(TailAggregationError):
        engine.aggregate(
            initial_equity=100_000.0,
            tail_risk={
                "confidence": 0.95,
                "var": 0.08,
                "cvar": 0.05,
            },
        )


def test_dataclass_results_are_supported() -> None:
    from dataclasses import dataclass

    @dataclass
    class ResultObject:
        confidence: float = 0.95
        var: float = 0.02
        cvar: float = 0.04

    engine = TailAggregationEngine()

    result = engine.aggregate(
        initial_equity=100_000.0,
        tail_risk=ResultObject(),
    )

    assert np.isclose(result.cvar_loss, 4_000.0)


def test_contract_health_and_serialization() -> None:
    engine = TailAggregationEngine()

    assert engine.API_VERSION == "1.0.0"
    assert engine.PHASE == "R3E.7"
    assert engine.COMPONENT == "TailAggregationEngine"
    assert engine.validate()["valid"] is True
    assert engine.health_check()["healthy"] is True
    assert engine.metadata["analytics_only"] is True
    assert engine.metadata["governance"] is False
    assert engine.metadata["execution"] is False
    assert engine.metadata["double_counting_control"] is True
    assert set(engine.PUBLIC_METHODS) == {
        "aggregate",
        "aggregate_scenario_losses",
        "summary",
        "metadata",
        "validate",
        "health_check",
        "to_dict",
        "save_json",
    }


def test_empty_aggregation_is_valid_but_contains_no_loss() -> None:
    engine = TailAggregationEngine()

    result = engine.aggregate(initial_equity=100_000.0)

    assert result.aggregate_tail_loss is None
    assert result.aggregate_tail_loss_pct is None
    assert result.tail_loss_source is None
    assert result.available_components == ()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
