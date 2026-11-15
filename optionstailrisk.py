"""
======================================================================
OPTIONS TAIL RISK
PHASE R4.9
======================================================================

Purpose
-------
Convert already-computed R4.8 deterministic option stress results into
an auditable option-specific tail-risk envelope.

R4.9 responsibilities
----------------------
1. Consume R4.8 OptionsStressPortfolioResult outputs.
2. Validate scenario results strictly.
3. Preserve scenario P&L provenance.
4. Calculate deterministic option-tail metrics.
5. Identify the worst option stress scenario.
6. Identify the largest loss contributor in the worst scenario.
7. Calculate loss concentration across supplied scenarios.
8. Provide deterministic serialization and health checks.

Important boundaries
--------------------
- This module does NOT revalue options.
- This module does NOT calculate Greeks.
- This module does NOT construct volatility surfaces.
- This module does NOT perform Black-Scholes valuation.
- This module does NOT recalculate R3 historical VaR/CVaR.
- This module does NOT sum overlapping stress scenarios.
- This module does NOT govern or modify portfolio weights.
- This module does NOT execute trades.

The canonical R4.9 option-tail envelope is the maximum comparable
R4.8 portfolio loss. Scenario losses are not summed.

A scenario-distribution VaR/CVaR is also available as a descriptive
diagnostic over the supplied deterministic scenario-loss set. It is
explicitly labelled deterministic scenario VaR/CVaR and must not be
treated as historical market VaR/CVaR.
======================================================================
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from math import isfinite
from typing import Any, Iterable, Mapping

import numpy as np

from Options_Stress import (
    OptionStressResult,
    OptionsStressPortfolioResult,
)


# ======================================================================
# MODULE METADATA
# ======================================================================

API_VERSION = "1.0.0"
COMPONENT = "OptionsTailRiskEngine"
PHASE = "R4.9"

PUBLIC_OBJECTS = (
    "OptionsTailRiskResult",
    "OptionsTailRiskEngine",
)

PUBLIC_METHODS = (
    "analyze",
    "analyze_scenarios",
    "summary",
    "metadata",
    "validate",
    "health_check",
    "to_dict",
)


# ======================================================================
# CONSTANTS
# ======================================================================

DEFAULT_TOLERANCE = 1e-12
DEFAULT_CONFIDENCES = (0.95, 0.99)


# ======================================================================
# EXCEPTIONS
# ======================================================================


class OptionsTailRiskError(ValueError):
    """Base exception for R4.9 options tail-risk failures."""


class OptionsTailRiskConfigurationError(
    OptionsTailRiskError
):
    """Raised when the R4.9 engine configuration is invalid."""


class OptionsTailRiskValidationError(
    OptionsTailRiskError
):
    """Raised when supplied R4.8 results are invalid."""


class OptionsTailRiskCalculationError(
    OptionsTailRiskError
):
    """Raised when R4.9 calculations cannot be completed."""


# ======================================================================
# RESULT OBJECT
# ======================================================================


@dataclass(frozen=True)
class OptionsTailRiskResult:
    """
    Immutable R4.9 options tail-risk result.

    Loss values are positive loss magnitudes.

    The canonical aggregate option-tail loss is the maximum comparable
    R4.8 portfolio loss, not a sum of scenario losses.
    """

    initial_equity: float

    scenario_count: int
    loss_scenario_count: int

    worst_scenario_name: str | None
    worst_scenario_loss: float
    worst_scenario_loss_pct: float | None

    aggregate_tail_loss: float
    aggregate_tail_loss_pct: float | None
    tail_loss_source: str

    scenario_var_95: float | None
    scenario_cvar_95: float | None
    scenario_var_99: float | None
    scenario_cvar_99: float | None

    mean_scenario_loss: float
    median_scenario_loss: float

    largest_loss_contributor: str | None
    largest_loss_contribution: float | None
    largest_loss_contribution_pct: float | None

    scenario_losses: tuple[dict[str, Any], ...]

    diagnostics: dict[str, Any]


# ======================================================================
# HELPERS
# ======================================================================


def _finite(
    value: Any,
    field_name: str,
) -> float:
    """Validate and return a finite float."""

    if isinstance(value, bool):
        raise TypeError(
            f"{field_name} must be numeric, not bool."
        )

    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"{field_name} must be numeric."
        ) from exc

    if not isfinite(result):
        raise ValueError(
            f"{field_name} must be finite."
        )

    return result


def _non_negative(
    value: Any,
    field_name: str,
) -> float:
    """Validate a finite non-negative number."""

    result = _finite(
        value,
        field_name,
    )

    if result < 0.0:
        raise ValueError(
            f"{field_name} cannot be negative."
        )

    return result


def _positive(
    value: Any,
    field_name: str,
) -> float:
    """Validate a finite positive number."""

    result = _finite(
        value,
        field_name,
    )

    if result <= 0.0:
        raise ValueError(
            f"{field_name} must be greater than zero."
        )

    return result


def _mapping(
    value: Any,
    field_name: str,
) -> Mapping[str, Any]:
    """
    Normalize supported result representations.

    R4.8 frozen dataclasses, mappings and compatible result objects
    are accepted without recalculating their contents.
    """

    if isinstance(value, Mapping):
        return value

    if is_dataclass(value):
        return asdict(value)

    if hasattr(value, "__dict__"):
        return vars(value)

    raise OptionsTailRiskValidationError(
        f"{field_name} must be a mapping, dataclass result, "
        "or compatible result object."
    )


def _confidence(
    value: Any,
) -> float:
    """Validate a confidence level."""

    result = _finite(
        value,
        "confidence",
    )

    if not 0.0 < result < 1.0:
        raise ValueError(
            "confidence must satisfy 0 < confidence < 1."
        )

    return result


def _scenario_loss_quantile(
    losses: np.ndarray,
    confidence: float,
) -> float | None:
    """
    Calculate deterministic scenario VaR as a positive loss magnitude.

    The input is already a set of positive loss magnitudes.
    """

    if losses.size == 0:
        return None

    alpha = 1.0 - confidence

    return float(
        max(
            0.0,
            np.quantile(
                losses,
                1.0 - alpha,
                method="linear",
            ),
        )
    )


def _scenario_cvar(
    losses: np.ndarray,
    confidence: float,
    tolerance: float,
) -> float | None:
    """
    Calculate deterministic scenario CVaR / ES.

    This is a descriptive statistic over the supplied R4.8 scenario
    loss set. It is not historical market CVaR.
    """

    if losses.size == 0:
        return None

    var = _scenario_loss_quantile(
        losses,
        confidence,
    )

    if var is None:
        return None

    tail = losses[
        losses >= var - tolerance
    ]

    if tail.size == 0:
        return float(var)

    return float(
        max(
            0.0,
            np.mean(tail),
        )
    )


# ======================================================================
# ENGINE
# ======================================================================


class OptionsTailRiskEngine:
    """
    Production R4.9 options tail-risk engine.

    The engine consumes already-computed R4.8 stress results and does
    not perform another option valuation.
    """

    API_VERSION = API_VERSION
    COMPONENT = COMPONENT
    PHASE = PHASE
    PUBLIC_METHODS = PUBLIC_METHODS

    def __init__(
        self,
        *,
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> None:
        try:
            tolerance = _positive(
                tolerance,
                "tolerance",
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise OptionsTailRiskConfigurationError(
                str(exc)
            ) from exc

        self.tolerance = tolerance
        self.analysis_count = 0
        self.last_result: OptionsTailRiskResult | None = None

    # ==================================================================
    # VALIDATION
    # ==================================================================

    def _validate_portfolio_result(
        self,
        result: Any,
    ) -> Mapping[str, Any]:
        """Validate one R4.8 portfolio stress result."""

        if isinstance(
            result,
            OptionsStressPortfolioResult,
        ):
            payload = _mapping(
                result,
                "portfolio_result",
            )
        else:
            payload = _mapping(
                result,
                "portfolio_result",
            )

        required = (
            "scenario_name",
            "valuation_date",
            "position_count",
            "base_portfolio_value",
            "stressed_portfolio_value",
            "portfolio_pnl",
            "portfolio_loss",
            "position_results",
        )

        missing = [
            field
            for field in required
            if field not in payload
        ]

        if missing:
            raise OptionsTailRiskValidationError(
                "R4.8 portfolio result is missing fields: "
                + ", ".join(missing)
            )

        scenario_name = payload["scenario_name"]

        if not isinstance(
            scenario_name,
            str,
        ) or not scenario_name.strip():
            raise OptionsTailRiskValidationError(
                "scenario_name must be a non-empty string."
            )

        position_count = payload["position_count"]

        if (
            isinstance(position_count, bool)
            or not isinstance(position_count, int)
            or position_count < 0
        ):
            raise OptionsTailRiskValidationError(
                "position_count must be a non-negative integer."
            )

        base_value = _finite(
            payload["base_portfolio_value"],
            "base_portfolio_value",
        )

        stressed_value = _finite(
            payload["stressed_portfolio_value"],
            "stressed_portfolio_value",
        )

        portfolio_pnl = _finite(
            payload["portfolio_pnl"],
            "portfolio_pnl",
        )

        portfolio_loss = _non_negative(
            payload["portfolio_loss"],
            "portfolio_loss",
        )

        expected_pnl = stressed_value - base_value

        if not np.isclose(
            portfolio_pnl,
            expected_pnl,
            rtol=0.0,
            atol=max(self.tolerance, 1e-10),
        ):
            raise OptionsTailRiskValidationError(
                "portfolio_pnl is inconsistent with "
                "stressed_portfolio_value - base_portfolio_value."
            )

        expected_loss = max(
            -expected_pnl,
            0.0,
        )

        if not np.isclose(
            portfolio_loss,
            expected_loss,
            rtol=0.0,
            atol=max(self.tolerance, 1e-10),
        ):
            raise OptionsTailRiskValidationError(
                "portfolio_loss is inconsistent with portfolio_pnl."
            )

        position_results = payload["position_results"]

        if not isinstance(
            position_results,
            (tuple, list),
        ):
            raise OptionsTailRiskValidationError(
                "position_results must be a tuple or list."
            )

        if len(position_results) != position_count:
            raise OptionsTailRiskValidationError(
                "position_count does not match position_results."
            )

        return payload

    # ==================================================================
    # ANALYSIS
    # ==================================================================

    def analyze(
        self,
        portfolio_results: Iterable[
            OptionsStressPortfolioResult
        ],
        *,
        initial_equity: float,
        confidences: tuple[float, ...] = DEFAULT_CONFIDENCES,
    ) -> OptionsTailRiskResult:
        """
        Analyze an iterable of R4.8 portfolio stress results.

        Scenario losses are treated as overlapping deterministic views.
        Therefore aggregate_tail_loss is the maximum scenario loss.
        """

        try:
            equity = _positive(
                initial_equity,
                "initial_equity",
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise OptionsTailRiskValidationError(
                str(exc)
            ) from exc

        if not isinstance(
            confidences,
            tuple,
        ):
            confidences = tuple(confidences)

        if not confidences:
            raise OptionsTailRiskValidationError(
                "confidences cannot be empty."
            )

        validated_confidences: list[float] = []

        try:
            for confidence in confidences:
                validated_confidences.append(
                    _confidence(confidence)
                )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise OptionsTailRiskValidationError(
                str(exc)
            ) from exc

        if len(
            set(validated_confidences)
        ) != len(validated_confidences):
            raise OptionsTailRiskValidationError(
                "confidences must be unique."
            )

        results = list(
            portfolio_results
        )

        if not results:
            raise OptionsTailRiskValidationError(
                "At least one R4.8 portfolio stress result is required."
            )

        validated: list[Mapping[str, Any]] = []

        for result in results:
            validated.append(
                self._validate_portfolio_result(
                    result
                )
            )

        # Deterministic ordering by scenario name.
        ordered = tuple(
            sorted(
                validated,
                key=lambda item: str(
                    item["scenario_name"]
                ),
            )
        )

        scenario_names = [
            str(item["scenario_name"])
            for item in ordered
        ]

        if len(
            set(scenario_names)
        ) != len(scenario_names):
            raise OptionsTailRiskValidationError(
                "Scenario names must be unique."
            )

        scenario_losses = np.asarray(
            [
                _non_negative(
                    item["portfolio_loss"],
                    "portfolio_loss",
                )
                for item in ordered
            ],
            dtype=float,
        )

        if not np.isfinite(
            scenario_losses
        ).all():
            raise OptionsTailRiskCalculationError(
                "Scenario losses contain non-finite values."
            )

        loss_mask = (
            scenario_losses > self.tolerance
        )

        loss_count = int(
            np.count_nonzero(loss_mask)
        )

        worst_index = int(
            np.argmax(
                scenario_losses
            )
        )

        worst_loss = float(
            scenario_losses[worst_index]
        )

        worst_payload = ordered[
            worst_index
        ]

        worst_name = str(
            worst_payload["scenario_name"]
        )

        worst_loss_pct = (
            None
            if equity <= self.tolerance
            else float(
                worst_loss / equity
            )
        )

        scenario_var_95 = (
            _scenario_loss_quantile(
                scenario_losses,
                0.95,
            )
        )

        scenario_cvar_95 = (
            _scenario_cvar(
                scenario_losses,
                0.95,
                self.tolerance,
            )
        )

        scenario_var_99 = (
            _scenario_loss_quantile(
                scenario_losses,
                0.99,
            )
        )

        scenario_cvar_99 = (
            _scenario_cvar(
                scenario_losses,
                0.99,
                self.tolerance,
            )
        )

        # R4.8 already identifies the largest loss contributor.
        largest_loss_contributor = (
            worst_payload.get(
                "largest_loss_contributor"
            )
        )

        largest_loss_contribution: float | None = None
        largest_loss_contribution_pct: float | None = None

        if (
            largest_loss_contributor is not None
            and isinstance(
                worst_payload.get(
                    "position_results"
                ),
                (tuple, list),
            )
        ):
            position_payloads = [
                _mapping(
                    position_result,
                    "position_result",
                )
                for position_result in worst_payload[
                    "position_results"
                ]
            ]

            loss_candidates = [
                item
                for item in position_payloads
                if _finite(
                    item.get("pnl", 0.0),
                    "position pnl",
                ) < -self.tolerance
            ]

            if loss_candidates:
                largest_position = min(
                    loss_candidates,
                    key=lambda item: float(
                        item["pnl"]
                    ),
                )

                largest_loss_contribution = float(
                    max(
                        -float(
                            largest_position["pnl"]
                        ),
                        0.0,
                    )
                )

                if worst_loss > self.tolerance:
                    largest_loss_contribution_pct = float(
                        largest_loss_contribution
                        / worst_loss
                    )

        scenario_loss_records = tuple(
            {
                "scenario_name": str(
                    item["scenario_name"]
                ),
                "portfolio_loss": float(
                    item["portfolio_loss"]
                ),
                "portfolio_loss_pct": (
                    None
                    if equity <= self.tolerance
                    else float(
                        item["portfolio_loss"]
                        / equity
                    )
                ),
                "portfolio_pnl": float(
                    item["portfolio_pnl"]
                ),
                "base_portfolio_value": float(
                    item["base_portfolio_value"]
                ),
                "stressed_portfolio_value": float(
                    item["stressed_portfolio_value"]
                ),
            }
            for item in ordered
        )

        result = OptionsTailRiskResult(
            initial_equity=float(equity),
            scenario_count=len(
                ordered
            ),
            loss_scenario_count=loss_count,
            worst_scenario_name=worst_name,
            worst_scenario_loss=worst_loss,
            worst_scenario_loss_pct=worst_loss_pct,
            aggregate_tail_loss=worst_loss,
            aggregate_tail_loss_pct=worst_loss_pct,
            tail_loss_source=(
                "options_stress_max_scenario_envelope"
            ),
            scenario_var_95=scenario_var_95,
            scenario_cvar_95=scenario_cvar_95,
            scenario_var_99=scenario_var_99,
            scenario_cvar_99=scenario_cvar_99,
            mean_scenario_loss=float(
                np.mean(scenario_losses)
            ),
            median_scenario_loss=float(
                np.median(scenario_losses)
            ),
            largest_loss_contributor=(
                None
                if largest_loss_contributor is None
                else str(
                    largest_loss_contributor
                )
            ),
            largest_loss_contribution=(
                None
                if largest_loss_contribution is None
                else float(
                    largest_loss_contribution
                )
            ),
            largest_loss_contribution_pct=(
                None
                if largest_loss_contribution_pct is None
                else float(
                    largest_loss_contribution_pct
                )
            ),
            scenario_losses=scenario_loss_records,
            diagnostics={
                "method": (
                    "r4.9_options_stress_tail_envelope"
                ),
                "source_component": (
                    "OptionsStressEngine"
                ),
                "source_phase": "R4.8",
                "scenario_overlap_control": (
                    "maximum_comparable_loss"
                ),
                "scenario_losses_summed": False,
                "historical_var": False,
                "historical_cvar": False,
                "scenario_var_is_descriptive": True,
                "scenario_cvar_is_descriptive": True,
                "worst_scenario_index": worst_index,
                "loss_scenario_count": loss_count,
                "confidence_levels": tuple(
                    validated_confidences
                ),
            },
        )

        self.analysis_count += 1
        self.last_result = result

        return result

    def analyze_scenarios(
        self,
        portfolio_results: Iterable[
            OptionsStressPortfolioResult
        ],
        *,
        initial_equity: float,
        confidence: float = 0.95,
    ) -> OptionsTailRiskResult:
        """
        Convenience wrapper for one confidence level.

        The result always retains the canonical 95% and 99% descriptive
        scenario metrics; confidence is recorded in diagnostics.
        """

        result = self.analyze(
            portfolio_results,
            initial_equity=initial_equity,
            confidences=(confidence,),
        )

        diagnostics = dict(
            result.diagnostics
        )
        diagnostics["requested_confidence"] = float(
            _confidence(confidence)
        )

        return OptionsTailRiskResult(
            **{
                **asdict(result),
                "diagnostics": diagnostics,
            }
        )

    # ==================================================================
    # SUMMARY / METADATA
    # ==================================================================

    def summary(
        self,
        result: OptionsTailRiskResult | None = None,
    ) -> dict[str, Any]:
        """Return the latest or supplied result."""

        selected = (
            result
            if result is not None
            else self.last_result
        )

        if selected is None:
            return {
                "component": self.COMPONENT,
                "api_version": self.API_VERSION,
                "phase": self.PHASE,
                "analysis_count": self.analysis_count,
                "result": None,
            }

        return asdict(
            selected
        )

    @property
    def metadata(self) -> dict[str, Any]:
        """Return deterministic R4.9 metadata."""

        return {
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "method": (
                "r4.9_options_stress_tail_envelope"
            ),
            "source_component": (
                "OptionsStressEngine"
            ),
            "source_phase": "R4.8",
            "aggregate_tail_definition": (
                "maximum comparable R4.8 portfolio loss"
            ),
            "scenario_losses_summed": False,
            "historical_var": False,
            "historical_cvar": False,
            "scenario_var_cvar": (
                "descriptive deterministic scenario statistics"
            ),
            "greeks": False,
            "valuation": False,
            "volatility_surface": False,
            "governance": False,
            "execution": False,
        }

    def validate(self) -> dict[str, Any]:
        """Validate static engine configuration."""

        errors: list[str] = []

        if (
            not isinstance(
                self.tolerance,
                float,
            )
            or not isfinite(
                self.tolerance
            )
            or self.tolerance <= 0.0
        ):
            errors.append(
                "tolerance must be positive and finite."
            )

        if (
            not isinstance(
                self.analysis_count,
                int,
            )
            or self.analysis_count < 0
        ):
            errors.append(
                "analysis_count must be a non-negative integer."
            )

        return {
            "valid": not errors,
            "errors": errors,
        }

    def health_check(self) -> dict[str, Any]:
        """Return deterministic component health information."""

        validation = self.validate()

        return {
            "status": (
                "HEALTHY"
                if validation["valid"]
                else "UNHEALTHY"
            ),
            "healthy": validation["valid"],
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "analysis_count": self.analysis_count,
            "checks": {
                "configuration": validation["valid"],
                "r4_8_result_type": True,
                "no_valuation_recalculation": True,
                "no_scenario_sum": True,
                "analytics_only": True,
            },
            "errors": validation["errors"],
        }

    def to_dict(self) -> dict[str, Any]:
        """Return serializable engine state."""

        return {
            "metadata": self.metadata,
            "health": self.health_check(),
            "summary": self.summary(),
        }


# ======================================================================
# FACTORY
# ======================================================================


def create_options_tail_risk_engine(
    *,
    tolerance: float = DEFAULT_TOLERANCE,
) -> OptionsTailRiskEngine:
    """Create a configured R4.9 options tail-risk engine."""

    return OptionsTailRiskEngine(
        tolerance=tolerance,
    )


# ======================================================================
# SELF TEST
# ======================================================================


def _self_test() -> None:
    """Deterministic R4.9 self-test using real R4.8 result objects."""

    # --------------------------------------------------------------
    # BUILD R4.8-LIKE RESULTS USING THE REAL DATACLASS
    # --------------------------------------------------------------

    position_loss_1 = OptionStressResult(
        scenario_name="SCENARIO_A",
        position_id="POS-1",
        contract_id="CONTRACT-1",
        underlying="SPY",
        option_type="call",
        valuation_date="2026-01-01",
        stressed_valuation_date="2026-01-01",
        expiration="2027-01-01",
        base_spot=100.0,
        stressed_spot=80.0,
        base_volatility=0.20,
        stressed_volatility=0.20,
        base_risk_free_rate=0.05,
        stressed_risk_free_rate=0.05,
        base_time_to_expiry=1.0,
        stressed_time_to_expiry=1.0,
        quantity=1.0,
        multiplier=100.0,
        base_option_price=10.0,
        stressed_option_price=5.0,
        base_position_value=1000.0,
        stressed_position_value=500.0,
        pnl=-500.0,
        pnl_percentage=-0.50,
        absolute_loss=500.0,
        status="LOSS",
        diagnostics={},
    )

    position_loss_2 = OptionStressResult(
        scenario_name="SCENARIO_B",
        position_id="POS-1",
        contract_id="CONTRACT-1",
        underlying="SPY",
        option_type="call",
        valuation_date="2026-01-01",
        stressed_valuation_date="2026-01-01",
        expiration="2027-01-01",
        base_spot=100.0,
        stressed_spot=70.0,
        base_volatility=0.20,
        stressed_volatility=0.20,
        base_risk_free_rate=0.05,
        stressed_risk_free_rate=0.05,
        base_time_to_expiry=1.0,
        stressed_time_to_expiry=1.0,
        quantity=1.0,
        multiplier=100.0,
        base_option_price=10.0,
        stressed_option_price=2.0,
        base_position_value=1000.0,
        stressed_position_value=200.0,
        pnl=-800.0,
        pnl_percentage=-0.80,
        absolute_loss=800.0,
        status="LOSS",
        diagnostics={},
    )

    def portfolio_result(
        name: str,
        loss: float,
        positions: tuple[
            OptionStressResult,
            ...
        ],
    ) -> OptionsStressPortfolioResult:
        return OptionsStressPortfolioResult(
            scenario_name=name,
            valuation_date="2026-01-01",
            position_count=len(positions),
            base_portfolio_value=10000.0,
            stressed_portfolio_value=10000.0 - loss,
            portfolio_pnl=-loss,
            portfolio_loss=loss,
            pnl_percentage=(
                -loss / 10000.0
            ),
            largest_loss_contributor="POS-1",
            largest_gain_contributor=None,
            scenario_rank_metric=loss,
            position_results=positions,
            diagnostics={},
        )

    results = (
        portfolio_result(
            "SCENARIO_A",
            500.0,
            (position_loss_1,),
        ),
        portfolio_result(
            "SCENARIO_B",
            800.0,
            (position_loss_2,),
        ),
        portfolio_result(
            "SCENARIO_FLAT",
            0.0,
            (),
        ),
    )

    # --------------------------------------------------------------
    # ENGINE / HEALTH
    # --------------------------------------------------------------

    engine = OptionsTailRiskEngine()

    health = engine.health_check()

    assert health["healthy"] is True

    # --------------------------------------------------------------
    # ANALYSIS
    # --------------------------------------------------------------

    result = engine.analyze(
        results,
        initial_equity=10000.0,
    )

    assert result.scenario_count == 3
    assert result.loss_scenario_count == 2

    assert result.worst_scenario_name == "SCENARIO_B"
    assert np.isclose(
        result.worst_scenario_loss,
        800.0,
    )

    assert np.isclose(
        result.aggregate_tail_loss,
        800.0,
    )

    assert np.isclose(
        result.aggregate_tail_loss_pct,
        0.08,
    )

    assert (
        result.tail_loss_source
        == "options_stress_max_scenario_envelope"
    )

    assert np.isclose(
        result.largest_loss_contribution,
        800.0,
    )

    assert np.isclose(
        result.largest_loss_contribution_pct,
        1.0,
    )

    # Scenario losses are never summed.
    assert not np.isclose(
        result.aggregate_tail_loss,
        1300.0,
    )

    # --------------------------------------------------------------
    # DESCRIPTIVE SCENARIO CVAR
    # --------------------------------------------------------------

    assert (
        result.scenario_var_95
        is not None
    )

    assert (
        result.scenario_cvar_95
        is not None
    )

    assert (
        result.scenario_var_99
        is not None
    )

    assert (
        result.scenario_cvar_99
        is not None
    )

    # --------------------------------------------------------------
    # SERIALIZATION
    # --------------------------------------------------------------

    payload = asdict(result)

    assert (
        payload["worst_scenario_name"]
        == "SCENARIO_B"
    )

    assert (
        "scenario_losses"
        in payload
    )

    engine_payload = engine.to_dict()

    assert (
        "metadata"
        in engine_payload
    )

    assert (
        "health"
        in engine_payload
    )

    assert (
        "summary"
        in engine_payload
    )

    # --------------------------------------------------------------
    # INVALID INPUT
    # --------------------------------------------------------------

    rejected = False

    try:
        engine.analyze(
            [],
            initial_equity=10000.0,
        )
    except OptionsTailRiskValidationError:
        rejected = True

    assert rejected is True

    rejected = False

    try:
        engine.analyze(
            results,
            initial_equity=-1.0,
        )
    except OptionsTailRiskValidationError:
        rejected = True

    assert rejected is True

    print(
        "R4.9 Options Tail Risk "
        "self-test: PASS"
    )


# ======================================================================
# MODULE ENTRY POINT
# ======================================================================


if __name__ == "__main__":
    _self_test()
