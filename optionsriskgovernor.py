"""
======================================================================
OPTIONS RISK GOVERNOR
PHASE R4.10
======================================================================

Purpose
-------
Govern options exposure using the authoritative R4.9 options tail-risk
result.

Architecture
------------

    R4.2 OptionContract / OptionPosition
                    |
                    v
    R4.3 Black-Scholes Valuation
                    |
                    v
    R4.4 Analytical Greeks
                    |
                    v
    R4.5 Portfolio Greeks
                    |
                    v
    R4.6 Put/Call Parity
                    |
                    v
    R4.7 Volatility Surface Inputs
                    |
                    v
    R4.8 Options Stress
                    |
                    v
    R4.9 Options Tail Risk
                    |
                    v
    R4.10 OPTIONS RISK GOVERNOR
                    |
                    v
    R4.11 Risk Report

R4.10 responsibilities
----------------------
1. Consume the authoritative R4.9 OptionsTailRiskResult.
2. Validate tail-risk inputs strictly.
3. Compare option tail loss against configured limits.
4. Produce PASS / REDUCE / REJECT governance decisions.
5. Apply scalar exposure reduction when a breach is governable.
6. Never increase option exposure.
7. Preserve option position direction.
8. Preserve contract identity.
9. Return immutable governance results.
10. Provide deterministic diagnostics and serialization.
11. Provide production health checks.
12. Provide deterministic self-tests.

Important boundaries
--------------------
- This module does NOT perform option valuation.
- This module does NOT calculate Greeks.
- This module does NOT perform stress testing.
- This module does NOT calculate tail risk.
- This module does NOT construct volatility surfaces.
- This module does NOT execute trades.
- This module does NOT modify the canonical ETF universe.
- This module does NOT replace PortfolioRiskGovernor.
- R4.9 remains authoritative for option tail-risk measurement.
- R4.10 owns the governance decision only.

Governance policy
-----------------
The authoritative R4.9 aggregate tail loss is the maximum comparable
portfolio-level option stress loss. R4.10 does not sum scenarios again.

Two independent limits may be configured:

    max_tail_loss
        Absolute monetary option-tail-loss ceiling.

    max_tail_loss_pct
        Option-tail-loss ceiling as a percentage of initial equity.

If both are configured, the more restrictive resulting scale is used.

Governance actions
------------------
PASS
    No configured tail-risk limit is breached.

REDUCE
    A limit is breached but a positive scalar reduction can bring the
    option exposure within the configured envelope.

REJECT
    The required reduction would be zero exposure or the input cannot
    be governed safely.

Reduction is scalar:

    governed_quantity = original_quantity * scale

with:

    0.0 <= scale <= 1.0

Therefore R4.10 can never increase exposure or reverse position
direction.

======================================================================
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any, Sequence

from optionsrisk import OptionPosition
from optionstailrisk import (
    OptionsTailRiskEngine,
    OptionsTailRiskResult,
)


# ======================================================================
# MODULE METADATA
# ======================================================================

API_VERSION = "1.0.0"
COMPONENT = "OptionsRiskGovernor"
PHASE = "R4.10"

PUBLIC_METHODS = (
    "govern",
    "govern_positions",
    "summary",
    "metadata",
    "validate",
    "health_check",
    "to_dict",
)


# ======================================================================
# GOVERNANCE ACTIONS
# ======================================================================

class OptionsRiskGovernorAction:
    """
    Canonical R4.10 governance actions.
    """

    PASS = "PASS"
    REDUCE = "REDUCE"
    REJECT = "REJECT"

    VALUES = (
        PASS,
        REDUCE,
        REJECT,
    )


# ======================================================================
# STATUS VALUES
# ======================================================================

STATUS_PASS = "PASS"
STATUS_REDUCED = "REDUCED"
STATUS_REJECTED = "REJECTED"


# ======================================================================
# EXCEPTIONS
# ======================================================================

class OptionsRiskGovernorError(Exception):
    """
    Base R4.10 exception.
    """


class OptionsRiskGovernorConfigurationError(
    OptionsRiskGovernorError
):
    """
    Raised when governor configuration is invalid.
    """


class OptionsRiskGovernorValidationError(
    OptionsRiskGovernorError
):
    """
    Raised when supplied risk inputs are invalid.
    """


class OptionsRiskGovernorCalculationError(
    OptionsRiskGovernorError
):
    """
    Raised when a governance calculation cannot be completed safely.
    """


# ======================================================================
# RESULT OBJECT
# ======================================================================

@dataclass(frozen=True)
class OptionsRiskGovernanceResult:
    """
    Immutable R4.10 governance decision.

    The original option positions are not mutated.

    ``governed_positions`` contains scaled replacement positions when
    the caller supplied positions. The tuple is empty when governance
    was performed only against a tail-risk result.
    """

    action: str
    approved: bool

    scale: float

    status: str

    initial_equity: float

    aggregate_tail_loss: float
    aggregate_tail_loss_pct: float

    max_tail_loss: float | None
    max_tail_loss_pct: float | None

    required_scale_absolute: float | None
    required_scale_percentage: float | None

    tail_loss_breach: bool
    tail_loss_percentage_breach: bool

    position_count: int

    original_total_quantity_abs: float
    governed_total_quantity_abs: float

    original_gross_notional: float | None
    governed_gross_notional: float | None

    original_positions: tuple[OptionPosition, ...]
    governed_positions: tuple[OptionPosition, ...]

    breaches: tuple[str, ...]

    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """
        Return deterministic JSON-safe governance state.

        OptionPosition objects are serialized through their existing
        authoritative ``to_dict`` implementation.
        """

        payload = asdict(self)

        payload["original_positions"] = [
            position.to_dict()
            for position in self.original_positions
        ]

        payload["governed_positions"] = [
            position.to_dict()
            for position in self.governed_positions
        ]

        payload["action"] = str(self.action)
        payload["status"] = str(self.status)

        return payload


# ======================================================================
# VALIDATION HELPERS
# ======================================================================

def _validate_finite_number(
    value: Any,
    field_name: str,
) -> float:
    """
    Validate a finite numeric scalar.
    """

    if isinstance(value, bool):
        raise OptionsRiskGovernorValidationError(
            f"{field_name} must be numeric, not bool."
        )

    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise OptionsRiskGovernorValidationError(
            f"{field_name} must be numeric."
        ) from exc

    if not isfinite(numeric):
        raise OptionsRiskGovernorValidationError(
            f"{field_name} must be finite."
        )

    return numeric


def _validate_nonnegative(
    value: Any,
    field_name: str,
) -> float:
    """
    Validate a finite nonnegative scalar.
    """

    numeric = _validate_finite_number(
        value,
        field_name,
    )

    if numeric < 0.0:
        raise OptionsRiskGovernorValidationError(
            f"{field_name} cannot be negative."
        )

    return numeric


def _validate_limit(
    value: Any,
    field_name: str,
) -> float:
    """
    Validate a strictly positive governance limit.
    """

    numeric = _validate_finite_number(
        value,
        field_name,
    )

    if numeric <= 0.0:
        raise OptionsRiskGovernorConfigurationError(
            f"{field_name} must be strictly positive."
        )

    return numeric


def _validate_scale(
    value: Any,
    field_name: str = "scale",
) -> float:
    """
    Validate a scalar exposure multiplier in [0, 1].
    """

    numeric = _validate_finite_number(
        value,
        field_name,
    )

    if numeric < 0.0 or numeric > 1.0:
        raise OptionsRiskGovernorCalculationError(
            f"{field_name} must be between 0 and 1."
        )

    return numeric


# ======================================================================
# OPTIONS RISK GOVERNOR
# ======================================================================

class OptionsRiskGovernor:
    """
    Production R4.10 options-tail-risk governor.

    Parameters
    ----------
    max_tail_loss:
        Maximum permitted absolute option tail loss.

    max_tail_loss_pct:
        Maximum permitted option tail loss as a fraction of initial
        equity.

    minimum_scale:
        Minimum positive scale accepted for REDUCE.

        If the required scale is below this threshold, the governor
        rejects rather than approving an effectively zero-exposure
        portfolio.

    tolerance:
        Numerical comparison tolerance.

    tail_risk_engine:
        Optional authoritative R4.9 engine. The governor does not
        recalculate tail risk.
    """

    API_VERSION = API_VERSION
    COMPONENT = COMPONENT
    PHASE = PHASE
    PUBLIC_METHODS = PUBLIC_METHODS

    def __init__(
        self,
        *,
        max_tail_loss: float | None = None,
        max_tail_loss_pct: float | None = None,
        minimum_scale: float = 1e-12,
        tolerance: float = 1e-10,
        tail_risk_engine: OptionsTailRiskEngine | None = None,
    ) -> None:

        if (
            max_tail_loss is None
            and max_tail_loss_pct is None
        ):
            raise OptionsRiskGovernorConfigurationError(
                "At least one of max_tail_loss or "
                "max_tail_loss_pct must be configured."
            )

        if max_tail_loss is not None:
            max_tail_loss = _validate_limit(
                max_tail_loss,
                "max_tail_loss",
            )

        if max_tail_loss_pct is not None:
            max_tail_loss_pct = _validate_limit(
                max_tail_loss_pct,
                "max_tail_loss_pct",
            )

        minimum_scale = _validate_finite_number(
            minimum_scale,
            "minimum_scale",
        )

        if (
            minimum_scale <= 0.0
            or minimum_scale > 1.0
        ):
            raise OptionsRiskGovernorConfigurationError(
                "minimum_scale must be greater than zero "
                "and no greater than one."
            )

        tolerance = _validate_finite_number(
            tolerance,
            "tolerance",
        )

        if tolerance < 0.0:
            raise OptionsRiskGovernorConfigurationError(
                "tolerance cannot be negative."
            )

        if tail_risk_engine is not None and not isinstance(
            tail_risk_engine,
            OptionsTailRiskEngine,
        ):
            raise OptionsRiskGovernorConfigurationError(
                "tail_risk_engine must be an OptionsTailRiskEngine."
            )

        self.max_tail_loss = max_tail_loss
        self.max_tail_loss_pct = max_tail_loss_pct
        self.minimum_scale = minimum_scale
        self.tolerance = tolerance
        self.tail_risk_engine = (
            tail_risk_engine
            if tail_risk_engine is not None
            else OptionsTailRiskEngine(
                tolerance=tolerance,
            )
        )

        self.last_result: OptionsRiskGovernanceResult | None = None

        self._summary = {
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "max_tail_loss": self.max_tail_loss,
            "max_tail_loss_pct": self.max_tail_loss_pct,
            "minimum_scale": self.minimum_scale,
            "tolerance": self.tolerance,
            "governance_actions": (
                OptionsRiskGovernorAction.VALUES
            ),
            "scope": "options_tail_risk_governance",
        }

        self.validate()

    # ==================================================================
    # CONFIGURATION VALIDATION
    # ==================================================================

    def validate(self) -> bool:
        """
        Validate governor configuration.
        """

        if (
            self.max_tail_loss is None
            and self.max_tail_loss_pct is None
        ):
            raise OptionsRiskGovernorConfigurationError(
                "No tail-risk governance limit is configured."
            )

        if self.max_tail_loss is not None:
            _validate_limit(
                self.max_tail_loss,
                "max_tail_loss",
            )

        if self.max_tail_loss_pct is not None:
            _validate_limit(
                self.max_tail_loss_pct,
                "max_tail_loss_pct",
            )

        if (
            not isfinite(self.minimum_scale)
            or self.minimum_scale <= 0.0
            or self.minimum_scale > 1.0
        ):
            raise OptionsRiskGovernorConfigurationError(
                "minimum_scale must be in (0, 1]."
            )

        if (
            not isfinite(self.tolerance)
            or self.tolerance < 0.0
        ):
            raise OptionsRiskGovernorConfigurationError(
                "tolerance must be finite and nonnegative."
            )

        if not isinstance(
            self.tail_risk_engine,
            OptionsTailRiskEngine,
        ):
            raise OptionsRiskGovernorConfigurationError(
                "Authoritative tail-risk engine is invalid."
            )

        return True

    # ==================================================================
    # TAIL-RISK RESULT VALIDATION
    # ==================================================================

    def _validate_tail_risk_result(
        self,
        result: OptionsTailRiskResult,
    ) -> OptionsTailRiskResult:
        """
        Validate the authoritative R4.9 result.
        """

        if not isinstance(
            result,
            OptionsTailRiskResult,
        ):
            raise OptionsRiskGovernorValidationError(
                "tail_risk_result must be an "
                "OptionsTailRiskResult."
            )

        initial_equity = _validate_finite_number(
            result.initial_equity,
            "initial_equity",
        )

        if initial_equity <= 0.0:
            raise OptionsRiskGovernorValidationError(
                "initial_equity must be strictly positive."
            )

        aggregate_tail_loss = _validate_nonnegative(
            result.aggregate_tail_loss,
            "aggregate_tail_loss",
        )

        _validate_nonnegative(
            result.aggregate_tail_loss_pct,
            "aggregate_tail_loss_pct",
        )

        scenario_count = int(result.scenario_count)

        if scenario_count < 0:
            raise OptionsRiskGovernorValidationError(
                "scenario_count cannot be negative."
            )

        if aggregate_tail_loss > initial_equity + self.tolerance:
            # This is not automatically a rejection. Option tail loss
            # can legitimately exceed starting equity in leveraged or
            # short-option configurations. It is therefore retained as
            # an auditable condition rather than treated as malformed.
            pass

        return result

    # ==================================================================
    # POSITION VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_positions(
        positions: Sequence[OptionPosition],
    ) -> tuple[OptionPosition, ...]:
        """
        Validate and canonicalize option positions.
        """

        if not isinstance(
            positions,
            Sequence,
        ):
            raise OptionsRiskGovernorValidationError(
                "positions must be a sequence."
            )

        validated: list[OptionPosition] = []

        for index, position in enumerate(positions):

            if not isinstance(
                position,
                OptionPosition,
            ):
                raise OptionsRiskGovernorValidationError(
                    "positions["
                    f"{index}"
                    "] must be an OptionPosition."
                )

            quantity = _validate_finite_number(
                position.quantity,
                f"positions[{index}].quantity",
            )

            if not isfinite(quantity):
                raise OptionsRiskGovernorValidationError(
                    f"positions[{index}].quantity must be finite."
                )

            validated.append(position)

        return tuple(validated)

    # ==================================================================
    # POSITION NOTIONAL
    # ==================================================================

    @staticmethod
    def _gross_notional(
        positions: Sequence[OptionPosition],
    ) -> float | None:
        """
        Calculate gross option contract notional where a market price
        is available.

        This is diagnostics only and is NOT used to calculate tail risk.
        """

        total = 0.0

        for position in positions:

            market_price = position.market_price

            if market_price is None:
                return None

            total += abs(
                float(position.quantity)
                * float(position.contract.multiplier)
                * float(market_price)
            )

        return float(total)

    # ==================================================================
    # POSITION QUANTITY METRICS
    # ==================================================================

    @staticmethod
    def _gross_quantity(
        positions: Sequence[OptionPosition],
    ) -> float:
        """
        Calculate gross signed-contract exposure magnitude.
        """

        return float(
            sum(
                abs(float(position.quantity))
                for position in positions
            )
        )

    # ==================================================================
    # SCALE POSITIONS
    # ==================================================================

    def _scale_positions(
        self,
        positions: tuple[OptionPosition, ...],
        scale: float,
    ) -> tuple[OptionPosition, ...]:
        """
        Create immutable scaled option positions.

        No original OptionPosition is mutated.

        Contract identity, pricing metadata, entry information,
        position identifiers, and metadata are preserved.
        """

        scale = _validate_scale(scale)

        governed: list[OptionPosition] = []

        for position in positions:

            new_quantity = float(
                position.quantity
                * scale
            )

            governed.append(
                OptionPosition(
                    contract=position.contract,
                    quantity=new_quantity,
                    market_price=position.market_price,
                    average_entry_price=(
                        position.average_entry_price
                    ),
                    position_id=position.position_id,
                    metadata=position.metadata,
                )
            )

        return tuple(governed)

    # ==================================================================
    # REQUIRED SCALE
    # ==================================================================

    def _required_scale(
        self,
        tail_risk: OptionsTailRiskResult,
    ) -> tuple[
        float,
        float | None,
        float | None,
        bool,
        bool,
    ]:
        """
        Determine the scalar required to satisfy configured limits.

        Returns
        -------
        effective_scale
        absolute_limit_scale
        percentage_limit_scale
        absolute_breach
        percentage_breach
        """

        loss = float(
            tail_risk.aggregate_tail_loss
        )

        loss_pct = float(
            tail_risk.aggregate_tail_loss_pct
        )

        absolute_scale = None
        percentage_scale = None

        absolute_breach = False
        percentage_breach = False

        if self.max_tail_loss is not None:

            if loss > (
                self.max_tail_loss
                + self.tolerance
            ):

                absolute_breach = True

                if loss <= self.tolerance:
                    absolute_scale = 0.0
                else:
                    absolute_scale = (
                        self.max_tail_loss
                        / loss
                    )

        if self.max_tail_loss_pct is not None:

            if loss_pct > (
                self.max_tail_loss_pct
                + self.tolerance
            ):

                percentage_breach = True

                if loss_pct <= self.tolerance:
                    percentage_scale = 0.0
                else:
                    percentage_scale = (
                        self.max_tail_loss_pct
                        / loss_pct
                    )

        scales = [
            scale
            for scale in (
                absolute_scale,
                percentage_scale,
            )
            if scale is not None
        ]

        if not scales:
            effective_scale = 1.0
        else:
            effective_scale = min(scales)

        effective_scale = max(
            0.0,
            min(
                1.0,
                float(effective_scale),
            ),
        )

        return (
            effective_scale,
            absolute_scale,
            percentage_scale,
            absolute_breach,
            percentage_breach,
        )

    # ==================================================================
    # GOVERN
    # ==================================================================

    def govern(
        self,
        tail_risk_result: OptionsTailRiskResult,
        positions: Sequence[OptionPosition] | None = None,
    ) -> OptionsRiskGovernanceResult:
        """
        Govern an authoritative R4.9 tail-risk result.

        Parameters
        ----------
        tail_risk_result:
            Existing R4.9 OptionsTailRiskResult.

        positions:
            Optional option positions to scale according to the
            resulting governance decision.

        Returns
        -------
        OptionsRiskGovernanceResult
        """

        self.validate()

        tail_risk = self._validate_tail_risk_result(
            tail_risk_result
        )

        validated_positions: tuple[
            OptionPosition,
            ...
        ]

        if positions is None:
            validated_positions = ()
        else:
            validated_positions = self._validate_positions(
                positions
            )

        (
            required_scale,
            absolute_scale,
            percentage_scale,
            absolute_breach,
            percentage_breach,
        ) = self._required_scale(
            tail_risk
        )

        breaches: list[str] = []

        if absolute_breach:
            breaches.append(
                "MAX_TAIL_LOSS"
            )

        if percentage_breach:
            breaches.append(
                "MAX_TAIL_LOSS_PCT"
            )

        any_breach = bool(breaches)

        if not any_breach:

            action = (
                OptionsRiskGovernorAction.PASS
            )

            approved = True

            scale = 1.0

            status = STATUS_PASS

        elif (
            required_scale
            >= self.minimum_scale
        ):

            action = (
                OptionsRiskGovernorAction.REDUCE
            )

            approved = True

            scale = required_scale

            status = STATUS_REDUCED

        else:

            action = (
                OptionsRiskGovernorAction.REJECT
            )

            approved = False

            scale = 0.0

            status = STATUS_REJECTED

        if validated_positions:

            if action == (
                OptionsRiskGovernorAction.REJECT
            ):
                governed_positions = ()

            else:
                governed_positions = (
                    self._scale_positions(
                        validated_positions,
                        scale,
                    )
                )

        else:
            governed_positions = ()

        original_total_quantity_abs = (
            self._gross_quantity(
                validated_positions
            )
        )

        governed_total_quantity_abs = (
            self._gross_quantity(
                governed_positions
            )
        )

        original_gross_notional = (
            self._gross_notional(
                validated_positions
            )
            if validated_positions
            else 0.0
        )

        governed_gross_notional = (
            self._gross_notional(
                governed_positions
            )
            if governed_positions
            else (
                0.0
                if validated_positions
                else None
            )
        )

        # --------------------------------------------------------------
        # HARD SAFETY INVARIANTS
        # --------------------------------------------------------------

        if scale < -self.tolerance:
            raise OptionsRiskGovernorCalculationError(
                "Governance scale cannot be negative."
            )

        if scale > (
            1.0
            + self.tolerance
        ):
            raise OptionsRiskGovernorCalculationError(
                "Governance scale increased exposure."
            )

        if governed_positions:

            for original, governed in zip(
                validated_positions,
                governed_positions,
            ):

                original_quantity = float(
                    original.quantity
                )

                governed_quantity = float(
                    governed.quantity
                )

                if abs(governed_quantity) > (
                    abs(original_quantity)
                    + self.tolerance
                ):
                    raise OptionsRiskGovernorCalculationError(
                        "R4.10 increased an option "
                        "position quantity."
                    )

                if (
                    original_quantity != 0.0
                    and governed_quantity != 0.0
                    and (
                        original_quantity > 0.0
                    ) != (
                        governed_quantity > 0.0
                    )
                ):
                    raise OptionsRiskGovernorCalculationError(
                        "R4.10 reversed option "
                        "position direction."
                    )

                if (
                    governed.contract.identity
                    != original.contract.identity
                ):
                    raise OptionsRiskGovernorCalculationError(
                        "R4.10 changed option contract identity."
                    )

        if governed_total_quantity_abs > (
            original_total_quantity_abs
            + self.tolerance
        ):
            raise OptionsRiskGovernorCalculationError(
                "Aggregate governed option exposure "
                "exceeds original exposure."
            )

        diagnostics = {
            "method": (
                "r4.10_options_tail_risk_governance"
            ),
            "tail_risk_component": (
                "OptionsTailRiskEngine"
            ),
            "tail_risk_api_version": (
                self.tail_risk_engine.API_VERSION
            ),
            "tail_risk_phase": (
                self.tail_risk_engine.PHASE
            ),
            "tail_loss_source": (
                tail_risk.tail_loss_source
            ),
            "governance_scope": (
                "options_tail_risk_only"
            ),
            "valuation": False,
            "greeks": False,
            "stress_recalculation": False,
            "tail_risk_recalculation": False,
            "execution": False,
            "canonical_etf_universe_modified": False,
            "scalar_reduction_only": True,
            "never_increase_exposure": True,
            "direction_preserved": True,
            "contract_identity_preserved": True,
            "minimum_scale": float(
                self.minimum_scale
            ),
            "effective_scale": float(
                scale
            ),
            "absolute_limit_scale": (
                None
                if absolute_scale is None
                else float(absolute_scale)
            ),
            "percentage_limit_scale": (
                None
                if percentage_scale is None
                else float(percentage_scale)
            ),
            "absolute_breach": bool(
                absolute_breach
            ),
            "percentage_breach": bool(
                percentage_breach
            ),
        }

        result = OptionsRiskGovernanceResult(
            action=action,
            approved=bool(approved),
            scale=float(scale),
            status=status,
            initial_equity=float(
                tail_risk.initial_equity
            ),
            aggregate_tail_loss=float(
                tail_risk.aggregate_tail_loss
            ),
            aggregate_tail_loss_pct=float(
                tail_risk.aggregate_tail_loss_pct
            ),
            max_tail_loss=(
                None
                if self.max_tail_loss is None
                else float(self.max_tail_loss)
            ),
            max_tail_loss_pct=(
                None
                if self.max_tail_loss_pct is None
                else float(self.max_tail_loss_pct)
            ),
            required_scale_absolute=(
                None
                if absolute_scale is None
                else float(absolute_scale)
            ),
            required_scale_percentage=(
                None
                if percentage_scale is None
                else float(percentage_scale)
            ),
            tail_loss_breach=bool(
                absolute_breach
            ),
            tail_loss_percentage_breach=bool(
                percentage_breach
            ),
            position_count=len(
                validated_positions
            ),
            original_total_quantity_abs=float(
                original_total_quantity_abs
            ),
            governed_total_quantity_abs=float(
                governed_total_quantity_abs
            ),
            original_gross_notional=(
                None
                if original_gross_notional is None
                else float(original_gross_notional)
            ),
            governed_gross_notional=(
                None
                if governed_gross_notional is None
                else float(governed_gross_notional)
            ),
            original_positions=(
                validated_positions
            ),
            governed_positions=(
                governed_positions
            ),
            breaches=tuple(
                breaches
            ),
            diagnostics=diagnostics,
        )

        self.last_result = result

        return result

    # ==================================================================
    # GOVERN POSITIONS
    # ==================================================================

    def govern_positions(
        self,
        positions: Sequence[OptionPosition],
        tail_risk_result: OptionsTailRiskResult,
    ) -> OptionsRiskGovernanceResult:
        """
        Convenience interface with positions first.
        """

        return self.govern(
            tail_risk_result=tail_risk_result,
            positions=positions,
        )

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(self) -> dict[str, Any]:
        """
        Return deterministic governor state.
        """

        return {
            **dict(self._summary),
            "last_result": (
                None
                if self.last_result is None
                else self.last_result.to_dict()
            ),
        }

    # ==================================================================
    # METADATA
    # ==================================================================

    @property
    def metadata(self) -> dict[str, Any]:
        """
        Return institutional component metadata.
        """

        return {
            "class": self.COMPONENT,
            "version": self.API_VERSION,
            "phase": self.PHASE,
            "governance_actions": (
                OptionsRiskGovernorAction.VALUES
            ),
            "scope": (
                "options_tail_risk_governance"
            ),
            "tail_risk_source": (
                "OptionsTailRiskEngine"
            ),
            "scalar_reduction_only": True,
            "never_increase_exposure": True,
            "execution": False,
        }

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def health_check(self) -> dict[str, Any]:
        """
        Return production health state.
        """

        try:

            configuration_ok = self.validate()

            tail_engine_ok = (
                self.tail_risk_engine is not None
                and hasattr(
                    self.tail_risk_engine,
                    "analyze",
                )
                and hasattr(
                    self.tail_risk_engine,
                    "health_check",
                )
            )

            checks = {
                "configuration": bool(
                    configuration_ok
                ),
                "tail_risk_engine": bool(
                    tail_engine_ok
                ),
                "governance_actions": (
                    OptionsRiskGovernorAction.VALUES
                    == (
                        "PASS",
                        "REDUCE",
                        "REJECT",
                    )
                ),
                "scalar_reduction_only": True,
                "never_increase_exposure": True,
                "execution_disabled": True,
            }

            healthy = all(
                checks.values()
            )

            return {
                "status": (
                    "HEALTHY"
                    if healthy
                    else "UNHEALTHY"
                ),
                "healthy": bool(
                    healthy
                ),
                "component": self.COMPONENT,
                "api_version": self.API_VERSION,
                "phase": self.PHASE,
                "checks": checks,
            }

        except Exception as exc:

            return {
                "status": "UNHEALTHY",
                "healthy": False,
                "component": self.COMPONENT,
                "api_version": self.API_VERSION,
                "phase": self.PHASE,
                "error": str(exc),
            }

    # ==================================================================
    # SERIALIZATION
    # ==================================================================

    def to_dict(self) -> dict[str, Any]:
        """
        Return serializable governor state.
        """

        return self.summary()


# ======================================================================
# PRODUCTION FACTORY
# ======================================================================

def build_options_risk_governor(
    *,
    max_tail_loss: float | None = None,
    max_tail_loss_pct: float | None = None,
    minimum_scale: float = 1e-12,
    tolerance: float = 1e-10,
    tail_risk_engine: OptionsTailRiskEngine | None = None,
) -> OptionsRiskGovernor:
    """
    Production factory for OptionsRiskGovernor.
    """

    return OptionsRiskGovernor(
        max_tail_loss=max_tail_loss,
        max_tail_loss_pct=max_tail_loss_pct,
        minimum_scale=minimum_scale,
        tolerance=tolerance,
        tail_risk_engine=tail_risk_engine,
    )


# ======================================================================
# DETERMINISTIC SELF-TEST HELPERS
# ======================================================================

def _build_test_tail_result(
    *,
    aggregate_tail_loss: float,
    aggregate_tail_loss_pct: float,
    initial_equity: float = 100_000.0,
) -> OptionsTailRiskResult:
    """
    Construct a deterministic R4.9-compatible result for local tests.

    This does not invoke valuation or stress engines.
    """

    return OptionsTailRiskResult(
        initial_equity=float(
            initial_equity
        ),
        scenario_count=3,
        loss_scenario_count=2,
        worst_scenario_name="TEST_WORST",
        worst_scenario_loss=float(
            aggregate_tail_loss
        ),
        worst_scenario_loss_pct=float(
            aggregate_tail_loss_pct
        ),
        aggregate_tail_loss=float(
            aggregate_tail_loss
        ),
        aggregate_tail_loss_pct=float(
            aggregate_tail_loss_pct
        ),
        tail_loss_source="scenario",
        scenario_var_95=float(
            aggregate_tail_loss
        ),
        scenario_cvar_95=float(
            aggregate_tail_loss
        ),
        scenario_var_99=float(
            aggregate_tail_loss
        ),
        scenario_cvar_99=float(
            aggregate_tail_loss
        ),
        mean_scenario_loss=float(
            aggregate_tail_loss
        ),
        median_scenario_loss=float(
            aggregate_tail_loss
        ),
        largest_loss_contributor="TEST_OPTION",
        largest_loss_contribution=float(
            aggregate_tail_loss
        ),
        largest_loss_contribution_pct=1.0,
        scenario_losses=(
            float(aggregate_tail_loss),
        ),
        diagnostics={
            "source": "R4.9 deterministic self-test",
        },
    )


def _build_test_position() -> OptionPosition:
    """
    Construct a deterministic option position.
    """

    from datetime import date
    from optionsrisk import OptionContract

    contract = OptionContract(
        underlying="SPY",
        option_type="put",
        strike=500.0,
        expiration=date(
            2027,
            1,
            15,
        ),
        multiplier=100.0,
        exercise_style="european",
        currency="USD",
        contract_id="R410-TEST-PUT",
    )

    return OptionPosition(
        contract=contract,
        quantity=10.0,
        market_price=20.0,
        average_entry_price=15.0,
        position_id="R410-TEST-POSITION",
    )


# ======================================================================
# SELF-TEST 1 — CONFIGURATION
# ======================================================================

def test_options_risk_governor_configuration() -> None:
    """
    Validate production configuration.
    """

    governor = OptionsRiskGovernor(
        max_tail_loss=10_000.0,
        max_tail_loss_pct=0.10,
    )

    assert governor.validate() is True

    assert (
        governor.API_VERSION
        == "1.0.0"
    )

    assert (
        governor.PHASE
        == "R4.10"
    )


# ======================================================================
# SELF-TEST 2 — PASS
# ======================================================================

def test_options_risk_governor_pass() -> None:
    """
    Tail risk inside the configured envelope must PASS.
    """

    governor = OptionsRiskGovernor(
        max_tail_loss=10_000.0,
        max_tail_loss_pct=0.10,
    )

    tail_result = _build_test_tail_result(
        aggregate_tail_loss=5_000.0,
        aggregate_tail_loss_pct=0.05,
    )

    position = _build_test_position()

    result = governor.govern(
        tail_result,
        positions=(position,),
    )

    assert (
        result.action
        == OptionsRiskGovernorAction.PASS
    )

    assert result.approved is True

    assert (
        result.scale
        == 1.0
    )

    assert (
        result.status
        == STATUS_PASS
    )

    assert (
        result.breaches
        == ()
    )

    assert (
        result.governed_positions[0].quantity
        == position.quantity
    )


# ======================================================================
# SELF-TEST 3 — ABSOLUTE REDUCTION
# ======================================================================

def test_options_risk_governor_absolute_reduction() -> None:
    """
    Absolute tail-loss breach must produce REDUCE when possible.
    """

    governor = OptionsRiskGovernor(
        max_tail_loss=5_000.0,
    )

    tail_result = _build_test_tail_result(
        aggregate_tail_loss=10_000.0,
        aggregate_tail_loss_pct=0.10,
    )

    position = _build_test_position()

    result = governor.govern(
        tail_result,
        positions=(position,),
    )

    assert (
        result.action
        == OptionsRiskGovernorAction.REDUCE
    )

    assert result.approved is True

    assert (
        result.scale
        == 0.5
    )

    assert (
        result.tail_loss_breach
        is True
    )

    assert (
        "MAX_TAIL_LOSS"
        in result.breaches
    )

    assert (
        result.governed_positions[0].quantity
        == 5.0
    )


# ======================================================================
# SELF-TEST 4 — PERCENTAGE REDUCTION
# ======================================================================

def test_options_risk_governor_percentage_reduction() -> None:
    """
    Percentage tail-loss breach must produce REDUCE.
    """

    governor = OptionsRiskGovernor(
        max_tail_loss_pct=0.05,
    )

    tail_result = _build_test_tail_result(
        aggregate_tail_loss=10_000.0,
        aggregate_tail_loss_pct=0.10,
    )

    position = _build_test_position()

    result = governor.govern(
        tail_result,
        positions=(position,),
    )

    assert (
        result.action
        == OptionsRiskGovernorAction.REDUCE
    )

    assert result.approved is True

    assert (
        result.scale
        == 0.5
    )

    assert (
        result.tail_loss_percentage_breach
        is True
    )

    assert (
        "MAX_TAIL_LOSS_PCT"
        in result.breaches
    )

    assert (
        result.governed_positions[0].quantity
        == 5.0
    )


# ======================================================================
# SELF-TEST 5 — MOST RESTRICTIVE LIMIT
# ======================================================================

def test_options_risk_governor_uses_most_restrictive_limit() -> None:
    """
    When both limits breach, the smaller required scale wins.
    """

    governor = OptionsRiskGovernor(
        max_tail_loss=8_000.0,
        max_tail_loss_pct=0.05,
    )

    tail_result = _build_test_tail_result(
        aggregate_tail_loss=10_000.0,
        aggregate_tail_loss_pct=0.10,
    )

    result = governor.govern(
        tail_result,
    )

    assert (
        result.action
        == OptionsRiskGovernorAction.REDUCE
    )

    assert result.approved is True

    # Absolute limit requires 0.80.
    assert (
        result.required_scale_absolute
        == 0.8
    )

    # Percentage limit requires 0.50.
    assert (
        result.required_scale_percentage
        == 0.5
    )

    # Percentage limit is more restrictive.
    assert (
        result.scale
        == 0.5
    )


# ======================================================================
# SELF-TEST 6 — REJECTION
# ======================================================================

def test_options_risk_governor_rejection() -> None:
    """
    A required scale below minimum_scale must REJECT.
    """

    governor = OptionsRiskGovernor(
        max_tail_loss=1.0,
        minimum_scale=0.10,
    )

    tail_result = _build_test_tail_result(
        aggregate_tail_loss=100.0,
        aggregate_tail_loss_pct=0.001,
    )

    result = governor.govern(
        tail_result,
    )

    assert (
        result.action
        == OptionsRiskGovernorAction.REJECT
    )

    assert result.approved is False

    assert (
        result.scale
        == 0.0
    )

    assert (
        result.status
        == STATUS_REJECTED
    )


# ======================================================================
# SELF-TEST 7 — NEVER INCREASE EXPOSURE
# ======================================================================

def test_options_risk_governor_never_increases_exposure() -> None:
    """
    Governed option quantities must never exceed originals.
    """

    governor = OptionsRiskGovernor(
        max_tail_loss=5_000.0,
    )

    tail_result = _build_test_tail_result(
        aggregate_tail_loss=10_000.0,
        aggregate_tail_loss_pct=0.10,
    )

    position = _build_test_position()

    result = governor.govern(
        tail_result,
        positions=(position,),
    )

    original_abs = abs(
        position.quantity
    )

    governed_abs = abs(
        result.governed_positions[0].quantity
    )

    assert (
        governed_abs
        <= original_abs
        + 1e-12
    )


# ======================================================================
# SELF-TEST 8 — DIRECTION PRESERVATION
# ======================================================================

def test_options_risk_governor_preserves_direction() -> None:
    """
    A long option remains long after reduction.
    """

    governor = OptionsRiskGovernor(
        max_tail_loss=5_000.0,
    )

    tail_result = _build_test_tail_result(
        aggregate_tail_loss=10_000.0,
        aggregate_tail_loss_pct=0.10,
    )

    position = _build_test_position()

    result = governor.govern(
        tail_result,
        positions=(position,),
    )

    governed = (
        result.governed_positions[0]
    )

    assert (
        governed.quantity
        > 0.0
    )

    assert (
        position.quantity
        > 0.0
    )

    assert (
        governed.contract.identity
        == position.contract.identity
    )


# ======================================================================
# SELF-TEST 9 — SHORT POSITION
# ======================================================================

def test_options_risk_governor_preserves_short_direction() -> None:
    """
    A short option remains short after reduction.
    """

    from dataclasses import replace

    governor = OptionsRiskGovernor(
        max_tail_loss=5_000.0,
    )

    tail_result = _build_test_tail_result(
        aggregate_tail_loss=10_000.0,
        aggregate_tail_loss_pct=0.10,
    )

    position = _build_test_position()

    short_position = replace(
        position,
        quantity=-10.0,
    )

    result = governor.govern(
        tail_result,
        positions=(short_position,),
    )

    governed = (
        result.governed_positions[0]
    )

    assert (
        governed.quantity
        < 0.0
    )

    assert (
        abs(governed.quantity)
        <= abs(short_position.quantity)
        + 1e-12
    )


# ======================================================================
# SELF-TEST 10 — IMMUTABILITY
# ======================================================================

def test_options_risk_governor_does_not_mutate_position() -> None:
    """
    Original OptionPosition remains unchanged.
    """

    governor = OptionsRiskGovernor(
        max_tail_loss=5_000.0,
    )

    tail_result = _build_test_tail_result(
        aggregate_tail_loss=10_000.0,
        aggregate_tail_loss_pct=0.10,
    )

    position = _build_test_position()

    original_quantity = (
        position.quantity
    )

    governor.govern(
        tail_result,
        positions=(position,),
    )

    assert (
        position.quantity
        == original_quantity
    )


# ======================================================================
# SELF-TEST 11 — SERIALIZATION
# ======================================================================

def test_options_risk_governor_serialization() -> None:
    """
    Governance result must serialize deterministically.
    """

    governor = OptionsRiskGovernor(
        max_tail_loss=10_000.0,
    )

    tail_result = _build_test_tail_result(
        aggregate_tail_loss=5_000.0,
        aggregate_tail_loss_pct=0.05,
    )

    result = governor.govern(
        tail_result,
    )

    payload = result.to_dict()

    assert (
        payload["action"]
        == "PASS"
    )

    assert (
        "action"
        in payload
    )

    assert (
        "aggregate_tail_loss"
        in payload
    )

    assert (
        "diagnostics"
        in payload
    )


# ======================================================================
# SELF-TEST 12 — METADATA
# ======================================================================

def test_options_risk_governor_metadata() -> None:
    """
    Validate metadata contract.
    """

    governor = OptionsRiskGovernor(
        max_tail_loss=10_000.0,
    )

    metadata = governor.metadata

    assert (
        metadata["class"]
        == "OptionsRiskGovernor"
    )

    assert (
        metadata["version"]
        == "1.0.0"
    )

    assert (
        metadata["phase"]
        == "R4.10"
    )

    assert (
        metadata["scope"]
        == "options_tail_risk_governance"
    )

    assert (
        metadata["scalar_reduction_only"]
        is True
    )

    assert (
        metadata["never_increase_exposure"]
        is True
    )


# ======================================================================
# SELF-TEST 13 — HEALTH
# ======================================================================

def test_options_risk_governor_health() -> None:
    """
    Validate production health.
    """

    governor = OptionsRiskGovernor(
        max_tail_loss=10_000.0,
    )

    health = governor.health_check()

    assert (
        health["healthy"]
        is True
    )

    assert (
        health["status"]
        == "HEALTHY"
    )

    assert (
        health["phase"]
        == "R4.10"
    )


# ======================================================================
# SELF-TEST 14 — API FREEZE
# ======================================================================

def test_options_risk_governor_api() -> None:
    """
    Validate public API.
    """

    assert (
        API_VERSION
        == "1.0.0"
    )

    assert (
        COMPONENT
        == "OptionsRiskGovernor"
    )

    assert (
        PHASE
        == "R4.10"
    )

    assert (
        "govern"
        in PUBLIC_METHODS
    )

    assert (
        "govern_positions"
        in PUBLIC_METHODS
    )

    assert (
        "health_check"
        in PUBLIC_METHODS
    )

    assert (
        "to_dict"
        in PUBLIC_METHODS
    )


# ======================================================================
# MAIN
# ======================================================================

def _self_test() -> None:
    """
    Run all deterministic R4.10 tests.
    """

    test_options_risk_governor_configuration()
    test_options_risk_governor_pass()
    test_options_risk_governor_absolute_reduction()
    test_options_risk_governor_percentage_reduction()
    test_options_risk_governor_uses_most_restrictive_limit()
    test_options_risk_governor_rejection()
    test_options_risk_governor_never_increases_exposure()
    test_options_risk_governor_preserves_direction()
    test_options_risk_governor_preserves_short_direction()
    test_options_risk_governor_does_not_mutate_position()
    test_options_risk_governor_serialization()
    test_options_risk_governor_metadata()
    test_options_risk_governor_health()
    test_options_risk_governor_api()

    print(
        "optionsriskgovernor.py R4.10 self-test: PASS"
    )


if __name__ == "__main__":
    _self_test()