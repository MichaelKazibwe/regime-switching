"""
===============================================================================
TAIL AGGREGATION ENGINE
===============================================================================

R3E.7 — canonical aggregation of independently generated tail-risk analytics.

Purpose
-------
This module combines outputs from the already locked R3E stress/tail engines:

* historical VaR / CVaR / Expected Shortfall;
* deterministic asset-level stress;
* historical cross-sectional stress;
* factor stress;
* volatility / correlation stress.

The aggregator does NOT recalculate any underlying risk measure. It normalizes
and combines supplied results into a single, auditable tail-risk envelope.

Important design rule
---------------------
Tail scenarios are generally overlapping views of the same portfolio risk.
Therefore scenario losses are NOT summed.  The canonical aggregate loss is the
maximum comparable loss across supplied scenario engines.  Historical CVaR is
reported separately as a probabilistic tail-loss measure.

This module is analytics-only. It does not optimize, approve, reject, govern,
or execute portfolios.
===============================================================================
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np


class TailAggregationError(ValueError):
    """Raised when tail aggregation inputs are invalid."""


@dataclass(frozen=True)
class TailAggregationResult:
    """Immutable R3E.7 aggregated tail-risk result."""

    initial_equity: float
    confidence: float | None
    var_return: float | None
    cvar_return: float | None
    var_loss: float | None
    cvar_loss: float | None
    deterministic_stress_loss: float | None
    historical_stress_loss: float | None
    factor_stress_loss: float | None
    scenario_loss_envelope: float | None
    aggregate_tail_loss: float | None
    aggregate_tail_loss_pct: float | None
    tail_loss_source: str | None
    baseline_volatility: float | None
    stressed_volatility: float | None
    volatility_change_pct: float | None
    gross_exposure: float | None
    net_exposure: float | None
    available_components: tuple[str, ...]
    method: str


class TailAggregationEngine:
    """Aggregate independently produced R3E tail-risk results."""

    API_VERSION = "1.0.0"
    PHASE = "R3E.7"
    COMPONENT = "TailAggregationEngine"
    PUBLIC_METHODS = (
        "aggregate",
        "aggregate_scenario_losses",
        "summary",
        "metadata",
        "validate",
        "health_check",
        "to_dict",
        "save_json",
    )

    TOLERANCE = 1e-12

    def __init__(self) -> None:
        self.analysis_count = 0
        self.last_result: TailAggregationResult | None = None

    # ------------------------------------------------------------------
    # VALIDATION / NORMALIZATION
    # ------------------------------------------------------------------

    @staticmethod
    def _as_mapping(value: Any, name: str) -> Mapping[str, Any] | None:
        if value is None:
            return None
        if isinstance(value, Mapping):
            return value
        if is_dataclass(value):
            return asdict(value)
        if hasattr(value, "__dict__"):
            return vars(value)
        raise TailAggregationError(
            f"{name} must be a mapping, dataclass result, or result object."
        )

    @staticmethod
    def _finite_number(value: Any, name: str) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise TailAggregationError(f"{name} must be numeric.") from exc
        if not np.isfinite(result):
            raise TailAggregationError(f"{name} must be finite.")
        return result

    @classmethod
    def _optional_loss(
        cls,
        value: Any,
        name: str,
    ) -> float | None:
        if value is None:
            return None
        result = cls._finite_number(value, name)
        if result < -cls.TOLERANCE:
            raise TailAggregationError(
                f"{name} must be a non-negative loss magnitude."
            )
        return float(max(0.0, result))

    @classmethod
    def _optional_return(
        cls,
        value: Any,
        name: str,
    ) -> float | None:
        if value is None:
            return None
        return cls._finite_number(value, name)

    @classmethod
    def _extract_initial_equity(cls, value: Any) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise TailAggregationError(
                "initial_equity must be numeric."
            ) from exc
        if not np.isfinite(result) or result <= 0.0:
            raise TailAggregationError(
                "initial_equity must be finite and positive."
            )
        return result

    @staticmethod
    def _extract_confidence(result: Mapping[str, Any] | None) -> float | None:
        if result is None or result.get("confidence") is None:
            return None
        try:
            confidence = float(result["confidence"])
        except (TypeError, ValueError) as exc:
            raise TailAggregationError(
                "confidence must be numeric."
            ) from exc
        if not np.isfinite(confidence) or not 0.0 < confidence < 1.0:
            raise TailAggregationError(
                "confidence must satisfy 0 < confidence < 1."
            )
        return confidence

    @classmethod
    def _extract_var_cvar(
        cls,
        tail_result: Mapping[str, Any] | None,
    ) -> tuple[float | None, float | None, float | None]:
        if tail_result is None:
            return None, None, None

        confidence = cls._extract_confidence(tail_result)
        var_return = cls._optional_loss(
            tail_result.get("var"),
            "tail_result.var",
        )
        cvar_return = cls._optional_loss(
            tail_result.get("cvar", tail_result.get("expected_shortfall")),
            "tail_result.cvar",
        )

        if var_return is not None and cvar_return is not None:
            if cvar_return + cls.TOLERANCE < var_return:
                raise TailAggregationError(
                    "tail_result.cvar cannot be smaller than tail_result.var."
                )

        return confidence, var_return, cvar_return

    @classmethod
    def _extract_stress_loss(
        cls,
        result: Mapping[str, Any] | None,
        name: str,
    ) -> float | None:
        if result is None:
            return None

        for key in (
            "portfolio_loss",
            "worst_loss",
            "aggregate_loss",
            "loss",
        ):
            if key in result and result[key] is not None:
                return cls._optional_loss(
                    result[key],
                    f"{name}.{key}",
                )
        return None

    @classmethod
    def _extract_volatility(
        cls,
        result: Mapping[str, Any] | None,
    ) -> tuple[float | None, float | None, float | None]:
        if result is None:
            return None, None, None

        baseline = cls._optional_return(
            result.get("baseline_volatility"),
            "volatility_stress.baseline_volatility",
        )
        stressed = cls._optional_return(
            result.get("stressed_volatility"),
            "volatility_stress.stressed_volatility",
        )
        change_pct = cls._optional_return(
            result.get("volatility_change_pct"),
            "volatility_stress.volatility_change_pct",
        )
        return baseline, stressed, change_pct

    @classmethod
    def _extract_exposure(
        cls,
        *results: Mapping[str, Any] | None,
    ) -> tuple[float | None, float | None]:
        gross: float | None = None
        net: float | None = None

        for result in results:
            if result is None:
                continue
            if gross is None and result.get("gross_exposure") is not None:
                gross = cls._finite_number(
                    result["gross_exposure"],
                    "gross_exposure",
                )
            if net is None and result.get("net_exposure") is not None:
                net = cls._finite_number(
                    result["net_exposure"],
                    "net_exposure",
                )

        return gross, net

    # ------------------------------------------------------------------
    # SCENARIO LOSS ENVELOPE
    # ------------------------------------------------------------------

    @classmethod
    def aggregate_scenario_losses(
        cls,
        deterministic_stress: Any = None,
        historical_stress: Any = None,
        factor_stress: Any = None,
    ) -> dict[str, Any]:
        """
        Build the comparable scenario-loss envelope.

        Scenario losses are not additive because deterministic, historical,
        and factor stresses can represent overlapping manifestations of the
        same underlying portfolio tail risk.  The envelope therefore uses the
        maximum supplied loss magnitude.
        """

        deterministic = cls._as_mapping(
            deterministic_stress,
            "deterministic_stress",
        )
        historical = cls._as_mapping(
            historical_stress,
            "historical_stress",
        )
        factor = cls._as_mapping(
            factor_stress,
            "factor_stress",
        )

        losses = {
            "deterministic_stress": cls._extract_stress_loss(
                deterministic,
                "deterministic_stress",
            ),
            "historical_stress": cls._extract_stress_loss(
                historical,
                "historical_stress",
            ),
            "factor_stress": cls._extract_stress_loss(
                factor,
                "factor_stress",
            ),
        }

        available = {
            key: value
            for key, value in losses.items()
            if value is not None
        }

        if not available:
            envelope = None
            source = None
        else:
            source, envelope = max(
                available.items(),
                key=lambda item: item[1],
            )

        return {
            **losses,
            "scenario_loss_envelope": (
                None if envelope is None else float(envelope)
            ),
            "tail_loss_source": source,
            "method": "maximum_overlapping_scenario_losses",
        }

    # ------------------------------------------------------------------
    # MAIN AGGREGATION
    # ------------------------------------------------------------------

    def aggregate(
        self,
        initial_equity: float,
        tail_risk: Any = None,
        deterministic_stress: Any = None,
        historical_stress: Any = None,
        factor_stress: Any = None,
        volatility_correlation_stress: Any = None,
    ) -> TailAggregationResult:
        """Aggregate supplied R3E.2–R3E.6 outputs."""

        equity = self._extract_initial_equity(initial_equity)

        tail = self._as_mapping(tail_risk, "tail_risk")
        deterministic = self._as_mapping(
            deterministic_stress,
            "deterministic_stress",
        )
        historical = self._as_mapping(
            historical_stress,
            "historical_stress",
        )
        factor = self._as_mapping(
            factor_stress,
            "factor_stress",
        )
        volatility = self._as_mapping(
            volatility_correlation_stress,
            "volatility_correlation_stress",
        )

        confidence, var_return, cvar_return = self._extract_var_cvar(tail)
        var_loss = None if var_return is None else float(var_return * equity)
        cvar_loss = (
            None if cvar_return is None else float(cvar_return * equity)
        )

        scenario = self.aggregate_scenario_losses(
            deterministic_stress=deterministic,
            historical_stress=historical,
            factor_stress=factor,
        )
        scenario_envelope = scenario["scenario_loss_envelope"]

        comparable_losses = {
            "historical_cvar": cvar_loss,
            "scenario_loss_envelope": scenario_envelope,
        }
        comparable_losses = {
            key: value
            for key, value in comparable_losses.items()
            if value is not None
        }

        if comparable_losses:
            source, aggregate_loss = max(
                comparable_losses.items(),
                key=lambda item: item[1],
            )
        else:
            source = None
            aggregate_loss = None

        # If the scenario envelope exceeds CVaR, preserve its source.
        # Otherwise historical CVaR remains the probabilistic aggregate.
        if source == "scenario_loss_envelope":
            tail_loss_source = scenario["tail_loss_source"]
        else:
            tail_loss_source = source

        baseline_volatility, stressed_volatility, volatility_change_pct = (
            self._extract_volatility(volatility)
        )
        gross_exposure, net_exposure = self._extract_exposure(
            deterministic,
            historical,
            factor,
        )

        result = TailAggregationResult(
            initial_equity=equity,
            confidence=confidence,
            var_return=var_return,
            cvar_return=cvar_return,
            var_loss=var_loss,
            cvar_loss=cvar_loss,
            deterministic_stress_loss=scenario[
                "deterministic_stress"
            ],
            historical_stress_loss=scenario[
                "historical_stress"
            ],
            factor_stress_loss=scenario[
                "factor_stress"
            ],
            scenario_loss_envelope=scenario_envelope,
            aggregate_tail_loss=(
                None if aggregate_loss is None else float(aggregate_loss)
            ),
            aggregate_tail_loss_pct=(
                None
                if aggregate_loss is None
                else float(aggregate_loss / equity)
            ),
            tail_loss_source=tail_loss_source,
            baseline_volatility=baseline_volatility,
            stressed_volatility=stressed_volatility,
            volatility_change_pct=volatility_change_pct,
            gross_exposure=gross_exposure,
            net_exposure=net_exposure,
            available_components=tuple(
                key
                for key, value in (
                    ("tail_risk", tail),
                    ("deterministic_stress", deterministic),
                    ("historical_stress", historical),
                    ("factor_stress", factor),
                    ("volatility_correlation_stress", volatility),
                )
                if value is not None
            ),
            method="historical_tail_plus_max_scenario_envelope",
        )

        self.analysis_count += 1
        self.last_result = result
        return result

    # ------------------------------------------------------------------
    # REPORTING / SERIALIZATION
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return the latest aggregated tail-risk result."""
        if self.last_result is None:
            return {
                "component": self.COMPONENT,
                "api_version": self.API_VERSION,
                "phase": self.PHASE,
                "analysis_count": self.analysis_count,
                "result": None,
            }
        return asdict(self.last_result)

    @property
    def metadata(self) -> dict[str, Any]:
        """Return the R3E.7 method and governance metadata."""
        return {
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "method": "historical_tail_plus_max_scenario_envelope",
            "historical_tail_definition": (
                "VaR/CVaR are supplied historical tail measures; "
                "they are not recomputed by the aggregator."
            ),
            "scenario_aggregation_definition": (
                "Comparable deterministic, historical, and factor stress "
                "losses are aggregated by maximum loss rather than summed "
                "because scenarios may overlap."
            ),
            "volatility_correlation_definition": (
                "Volatility/correlation stress is reported as a volatility "
                "change and is not converted into a synthetic P&L loss."
            ),
            "double_counting_control": True,
            "analytics_only": True,
            "governance": False,
            "execution": False,
        }

    def validate(self) -> dict[str, Any]:
        """Validate static engine configuration."""
        errors: list[str] = []
        if not isinstance(self.analysis_count, int) or self.analysis_count < 0:
            errors.append("analysis_count must be a non-negative integer.")
        return {
            "valid": not errors,
            "errors": errors,
        }

    def health_check(self) -> dict[str, Any]:
        """Return engine health status."""
        validation = self.validate()
        return {
            "healthy": validation["valid"],
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "analysis_count": self.analysis_count,
            "errors": validation["errors"],
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable engine state."""
        return {
            "metadata": self.metadata,
            "health": self.health_check(),
            "summary": self.summary(),
        }

    def save_json(self, path: str | Path) -> Path:
        """Persist engine state as JSON."""
        target = Path(path)
        with target.open("w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, default=str)
        return target


# ============================================================================
# SELF TEST
# ============================================================================


def test_tail_aggregation() -> None:
    """Deterministic R3E.7 module tests."""

    engine = TailAggregationEngine()

    tail = {
        "confidence": 0.95,
        "var": 0.02,
        "cvar": 0.04,
        "expected_shortfall": 0.04,
    }
    deterministic = {
        "portfolio_loss": 5_000.0,
        "gross_exposure": 1.0,
        "net_exposure": 1.0,
    }
    historical = {
        "worst_loss": 7_500.0,
        "gross_exposure": 1.0,
        "net_exposure": 1.0,
    }
    factor = {
        "portfolio_loss": 6_000.0,
    }
    volatility = {
        "baseline_volatility": 0.10,
        "stressed_volatility": 0.16,
        "volatility_change_pct": 0.60,
    }

    result = engine.aggregate(
        initial_equity=100_000.0,
        tail_risk=tail,
        deterministic_stress=deterministic,
        historical_stress=historical,
        factor_stress=factor,
        volatility_correlation_stress=volatility,
    )

    assert np.isclose(result.var_loss, 2_000.0)
    assert np.isclose(result.cvar_loss, 4_000.0)
    assert np.isclose(result.scenario_loss_envelope, 7_500.0)
    assert np.isclose(result.aggregate_tail_loss, 7_500.0)
    assert np.isclose(result.aggregate_tail_loss_pct, 0.075)
    assert result.tail_loss_source == "historical_stress"
    assert np.isclose(result.stressed_volatility, 0.16)
    assert result.available_components == (
        "tail_risk",
        "deterministic_stress",
        "historical_stress",
        "factor_stress",
        "volatility_correlation_stress",
    )

    # Scenario losses must not be summed.
    envelope = engine.aggregate_scenario_losses(
        deterministic_stress={"portfolio_loss": 1_000.0},
        historical_stress={"worst_loss": 3_000.0},
        factor_stress={"portfolio_loss": 2_000.0},
    )
    assert np.isclose(envelope["scenario_loss_envelope"], 3_000.0)
    assert envelope["tail_loss_source"] == "historical_stress"

    # A probabilistic CVaR can remain the aggregate if larger than scenarios.
    result_cvar = engine.aggregate(
        initial_equity=100_000.0,
        tail_risk={"confidence": 0.95, "var": 0.03, "cvar": 0.10},
        deterministic_stress={"portfolio_loss": 5_000.0},
    )
    assert np.isclose(result_cvar.aggregate_tail_loss, 10_000.0)
    assert result_cvar.tail_loss_source == "historical_cvar"

    # Validation and serialization contract.
    assert engine.health_check()["healthy"] is True
    assert engine.metadata["double_counting_control"] is True
    payload = engine.to_dict()
    assert "metadata" in payload
    assert "summary" in payload

    print("TailAggregationEngine R3E.7 tests passed.")
    print("R3E.7 STATUS: PASS")


if __name__ == "__main__":
    test_tail_aggregation()
