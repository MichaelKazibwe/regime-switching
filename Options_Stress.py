"""
======================================================================
OPTIONS STRESS SCENARIOS
PHASE R4.8
======================================================================

Purpose
-------
Deterministic scenario-based stress testing for option positions and
option portfolios.

R4.8 responsibilities
---------------------
1. Define immutable stress scenarios.
2. Validate stress inputs strictly.
3. Revalue option positions under deterministic shocks.
4. Support:
       - underlying spot shocks
       - volatility shocks
       - interest-rate shocks
       - combined spot/volatility/rate shocks
       - time-to-expiry shocks
5. Calculate stressed option values.
6. Calculate position-level stress P&L.
7. Aggregate portfolio-level stress P&L.
8. Rank scenarios by portfolio loss.
9. Identify largest loss contributors.
10. Provide deterministic serialization.
11. Provide component health checks.

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
R4.7 Volatility-Surface Inputs
              |
              v
R4.8 OPTIONS STRESS
              |
              v
R4.9 Options Tail Risk
              |
              v
R4.10 Risk Governor
              |
              v
R4.11 Risk Report

Important boundaries
--------------------
- This module does NOT calculate Greeks.
- This module does NOT construct volatility surfaces.
- This module does NOT perform tail-risk aggregation.
- This module does NOT perform risk governance.
- This module does NOT execute trades.
- This module does NOT modify the canonical ETF universe.
- Black-Scholes valuation remains owned by R4.3.
- R4.8 consumes the R4.3 valuation engine rather than duplicating
  Black-Scholes formulas.

European options
----------------
R4.3 Black-Scholes valuation supports European options. Consequently,
R4.8 explicitly rejects American options rather than silently applying
a European model to them.

Time stress convention
----------------------
time_shift_days represents movement of the valuation date forward.

    0 days     -> no time shock
    +30 days   -> 30 calendar days of time decay
    +90 days   -> 90 calendar days of time decay

The stressed valuation date is capped at expiration. This allows an
expiry stress without creating an invalid post-expiration valuation.

Volatility shock convention
----------------------------
volatility_shock is an ABSOLUTE volatility change.

Example:

    base volatility = 20%
    volatility_shock = +5%

    stressed volatility = 25%

It is NOT a percentage multiplier.

Spot shock convention
---------------------
spot_shock is a RELATIVE percentage change.

Example:

    base spot = 100
    spot_shock = -0.20

    stressed spot = 80

Rate shock convention
---------------------
risk_free_rate_shock is an ABSOLUTE rate change.

Example:

    base rate = 5%
    rate shock = +1%

    stressed rate = 6%

======================================================================
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from math import isfinite
from typing import Any, Iterable, Sequence

from blackscholes import (
    BlackScholesCalculationError,
    BlackScholesEngine,
)
from optionsrisk import OptionContract, OptionPosition


# ======================================================================
# MODULE METADATA
# ======================================================================

API_VERSION = "1.0.0"
COMPONENT = "OptionsStressEngine"
PHASE = "R4.8"


PUBLIC_OBJECTS = (
    "OptionStressScenario",
    "OptionStressResult",
    "OptionsStressPortfolioResult",
)


# ======================================================================
# CONSTANTS
# ======================================================================

DEFAULT_TOLERANCE = 1e-12
DEFAULT_DIVIDEND_YIELD = 0.0

SCENARIO_STATUS_PASS = "PASS"
SCENARIO_STATUS_LOSS = "LOSS"
SCENARIO_STATUS_GAIN = "GAIN"
SCENARIO_STATUS_FLAT = "FLAT"

SUPPORTED_OPTION_TYPES = frozenset(
    {
        "call",
        "put",
    }
)

SUPPORTED_EXERCISE_STYLE = "european"


# ======================================================================
# EXCEPTIONS
# ======================================================================


class OptionsStressError(Exception):
    """Base exception for options stress failures."""


class OptionsStressConfigurationError(
    OptionsStressError
):
    """Raised when stress-engine configuration is invalid."""


class OptionsStressValidationError(
    OptionsStressError
):
    """Raised when a stress scenario or input is invalid."""


class OptionsStressCalculationError(
    OptionsStressError
):
    """Raised when stress valuation cannot be completed."""


# ======================================================================
# VALIDATION HELPERS
# ======================================================================


def _validate_finite(
    value: Any,
    field_name: str,
) -> float:
    """
    Validate a finite numeric value.

    Boolean values are explicitly rejected.
    """

    if isinstance(value, bool):
        raise TypeError(
            f"{field_name} must be numeric, not bool."
        )

    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"{field_name} must be numeric."
        ) from exc

    if not isfinite(numeric):
        raise ValueError(
            f"{field_name} must be finite."
        )

    return numeric


def _validate_positive(
    value: Any,
    field_name: str,
) -> float:
    """
    Validate a strictly positive finite numeric value.
    """

    numeric = _validate_finite(
        value,
        field_name,
    )

    if numeric <= 0.0:
        raise ValueError(
            f"{field_name} must be greater than zero."
        )

    return numeric


def _validate_non_negative(
    value: Any,
    field_name: str,
) -> float:
    """
    Validate a non-negative finite numeric value.
    """

    numeric = _validate_finite(
        value,
        field_name,
    )

    if numeric < 0.0:
        raise ValueError(
            f"{field_name} cannot be negative."
        )

    return numeric


def _validate_string(
    value: Any,
    field_name: str,
) -> str:
    """
    Validate a non-empty string.
    """

    if not isinstance(value, str):
        raise TypeError(
            f"{field_name} must be a string."
        )

    normalized = value.strip()

    if not normalized:
        raise ValueError(
            f"{field_name} cannot be empty."
        )

    return normalized


def _normalise_date(
    value: date | datetime,
    field_name: str,
) -> date:
    """
    Normalize datetime/date to date.

    This matches the date convention used by the existing
    analytical options layer.
    """

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    raise TypeError(
        f"{field_name} must be a date or datetime."
    )


def _date_key(
    value: date | datetime,
) -> str:
    """
    Return deterministic ISO date representation.
    """

    return _normalise_date(
        value,
        "date",
    ).isoformat()


# ======================================================================
# STRESS SCENARIO
# ======================================================================


@dataclass(frozen=True)
class OptionStressScenario:
    """
    Immutable deterministic options stress scenario.

    Parameters
    ----------
    name:
        Unique scenario name.

    spot_shock:
        Relative spot shock.

        Example:
            -0.20 = -20%
            +0.20 = +20%

    volatility_shock:
        Absolute volatility shock.

        Example:
            +0.05 = +5 volatility points
            -0.05 = -5 volatility points

    risk_free_rate_shock:
        Absolute risk-free-rate shock.

    time_shift_days:
        Number of calendar days by which the valuation date moves
        forward.

    metadata:
        Optional non-authoritative scenario metadata.
    """

    name: str
    spot_shock: float = 0.0
    volatility_shock: float = 0.0
    risk_free_rate_shock: float = 0.0
    time_shift_days: int = 0
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        try:
            name = _validate_string(
                self.name,
                "name",
            )

            spot_shock = _validate_finite(
                self.spot_shock,
                "spot_shock",
            )

            volatility_shock = _validate_finite(
                self.volatility_shock,
                "volatility_shock",
            )

            rate_shock = _validate_finite(
                self.risk_free_rate_shock,
                "risk_free_rate_shock",
            )

            if isinstance(
                self.time_shift_days,
                bool,
            ):
                raise TypeError(
                    "time_shift_days must be an integer."
                )

            if not isinstance(
                self.time_shift_days,
                int,
            ):
                raise TypeError(
                    "time_shift_days must be an integer."
                )

            metadata = (
                {}
                if self.metadata is None
                else dict(self.metadata)
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise OptionsStressValidationError(
                str(exc)
            ) from exc

        object.__setattr__(
            self,
            "name",
            name,
        )

        object.__setattr__(
            self,
            "spot_shock",
            spot_shock,
        )

        object.__setattr__(
            self,
            "volatility_shock",
            volatility_shock,
        )

        object.__setattr__(
            self,
            "risk_free_rate_shock",
            rate_shock,
        )

        object.__setattr__(
            self,
            "metadata",
            metadata,
        )

    @property
    def is_spot_stress(self) -> bool:
        """Return True when the scenario shocks spot."""
        return not isclose_zero(
            self.spot_shock
        )

    @property
    def is_volatility_stress(self) -> bool:
        """Return True when the scenario shocks volatility."""
        return not isclose_zero(
            self.volatility_shock
        )

    @property
    def is_rate_stress(self) -> bool:
        """Return True when the scenario shocks rates."""
        return not isclose_zero(
            self.risk_free_rate_shock
        )

    @property
    def is_time_stress(self) -> bool:
        """Return True when the scenario advances time."""
        return self.time_shift_days != 0

    @property
    def is_combined(self) -> bool:
        """
        Return True when more than one risk dimension is shocked.
        """

        dimensions = sum(
            (
                self.is_spot_stress,
                self.is_volatility_stress,
                self.is_rate_stress,
                self.is_time_stress,
            )
        )

        return dimensions > 1

    def to_dict(self) -> dict[str, Any]:
        """Return deterministic JSON-safe representation."""

        return asdict(self)


# ======================================================================
# POSITION STRESS RESULT
# ======================================================================


@dataclass(frozen=True)
class OptionStressResult:
    """
    Immutable position-level stress result.

    Values are position-level values, i.e. option premium multiplied by
    signed quantity and contract multiplier.
    """

    scenario_name: str

    position_id: str | None
    contract_id: str | None

    underlying: str
    option_type: str

    valuation_date: str
    stressed_valuation_date: str
    expiration: str

    base_spot: float
    stressed_spot: float

    base_volatility: float
    stressed_volatility: float

    base_risk_free_rate: float
    stressed_risk_free_rate: float

    base_time_to_expiry: float
    stressed_time_to_expiry: float

    quantity: float
    multiplier: float

    base_option_price: float
    stressed_option_price: float

    base_position_value: float
    stressed_position_value: float

    pnl: float
    pnl_percentage: float | None

    absolute_loss: float

    status: str

    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return deterministic JSON-safe representation."""
        return asdict(self)


# ======================================================================
# PORTFOLIO STRESS RESULT
# ======================================================================


@dataclass(frozen=True)
class OptionsStressPortfolioResult:
    """
    Immutable portfolio-level stress result.
    """

    scenario_name: str

    valuation_date: str

    position_count: int

    base_portfolio_value: float
    stressed_portfolio_value: float

    portfolio_pnl: float
    portfolio_loss: float

    pnl_percentage: float | None

    largest_loss_contributor: str | None
    largest_gain_contributor: str | None

    scenario_rank_metric: float

    position_results: tuple[OptionStressResult, ...]

    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """
        Return deterministic JSON-safe representation.
        """

        payload = asdict(self)

        payload["position_results"] = [
            result.to_dict()
            for result in self.position_results
        ]

        return payload


# ======================================================================
# NUMERICAL HELPERS
# ======================================================================


def isclose_zero(
    value: float,
    tolerance: float = DEFAULT_TOLERANCE,
) -> bool:
    """
    Deterministic zero comparison.
    """

    return abs(
        float(value)
    ) <= tolerance


def _safe_percentage(
    numerator: float,
    denominator: float,
    tolerance: float,
) -> float | None:
    """
    Return percentage change when denominator is non-zero.
    """

    if abs(denominator) <= tolerance:
        return None

    return (
        numerator
        / abs(denominator)
    )


# ======================================================================
# ENGINE
# ======================================================================


class OptionsStressEngine:
    """
    Production deterministic options stress engine.

    R4.8 deliberately delegates valuation to the existing R4.3
    BlackScholesEngine.
    """

    API_VERSION = API_VERSION
    COMPONENT = COMPONENT
    PHASE = PHASE

    PUBLIC_METHODS = (
        "stress_position",
        "stress_portfolio",
        "run_scenarios",
        "summary",
        "health_check",
    )

    def __init__(
        self,
        *,
        valuation_engine: BlackScholesEngine | None = None,
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> None:
        try:
            tolerance = _validate_positive(
                tolerance,
                "tolerance",
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise OptionsStressConfigurationError(
                str(exc)
            ) from exc

        if valuation_engine is not None and not isinstance(
            valuation_engine,
            BlackScholesEngine,
        ):
            raise OptionsStressConfigurationError(
                "valuation_engine must be a "
                "BlackScholesEngine."
            )

        self.tolerance = tolerance

        self.valuation_engine = (
            valuation_engine
            if valuation_engine is not None
            else BlackScholesEngine(
                tolerance=tolerance,
            )
        )

        self.last_result: (
            OptionStressResult
            | OptionsStressPortfolioResult
            | None
        ) = None

    # ==================================================================
    # VALIDATION
    # ==================================================================

    def _validate_position(
        self,
        position: OptionPosition,
    ) -> None:
        """
        Validate an option position for R4.8.
        """

        if not isinstance(
            position,
            OptionPosition,
        ):
            raise OptionsStressValidationError(
                "position must be an OptionPosition."
            )

        contract = position.contract

        if not isinstance(
            contract,
            OptionContract,
        ):
            raise OptionsStressValidationError(
                "position.contract must be an "
                "OptionContract."
            )

        if contract.option_type not in SUPPORTED_OPTION_TYPES:
            raise OptionsStressValidationError(
                "Unsupported option type."
            )

        if contract.exercise_style != (
            SUPPORTED_EXERCISE_STYLE
        ):
            raise OptionsStressValidationError(
                "R4.8 Black-Scholes stress testing "
                "supports European options only. "
                "American options are explicitly "
                "rejected."
            )

    def _validate_market_inputs(
        self,
        *,
        spot: float,
        risk_free_rate: float,
        volatility: float,
        valuation_date: date | datetime,
    ) -> tuple[
        float,
        float,
        float,
        date,
    ]:
        """
        Validate base market inputs.
        """

        try:
            spot = _validate_positive(
                spot,
                "spot",
            )

            risk_free_rate = _validate_finite(
                risk_free_rate,
                "risk_free_rate",
            )

            volatility = _validate_non_negative(
                volatility,
                "volatility",
            )

            valuation_date = _normalise_date(
                valuation_date,
                "valuation_date",
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise OptionsStressValidationError(
                str(exc)
            ) from exc

        return (
            spot,
            risk_free_rate,
            volatility,
            valuation_date,
        )

    def _validate_scenario(
        self,
        scenario: OptionStressScenario,
    ) -> None:
        """
        Validate a stress scenario.
        """

        if not isinstance(
            scenario,
            OptionStressScenario,
        ):
            raise OptionsStressValidationError(
                "scenario must be an "
                "OptionStressScenario."
            )

    # ==================================================================
    # STRESS INPUT CALCULATION
    # ==================================================================

    def _stressed_inputs(
        self,
        *,
        position: OptionPosition,
        scenario: OptionStressScenario,
        spot: float,
        risk_free_rate: float,
        volatility: float,
        valuation_date: date,
    ) -> tuple[
        float,
        float,
        float,
        date,
    ]:
        """
        Apply a scenario to base market inputs.
        """

        stressed_spot = (
            spot
            * (
                1.0
                + scenario.spot_shock
            )
        )

        if stressed_spot <= 0.0:
            raise OptionsStressCalculationError(
                "Scenario produces non-positive "
                "stressed spot."
            )

        stressed_volatility = (
            volatility
            + scenario.volatility_shock
        )

        if stressed_volatility < 0.0:
            raise OptionsStressCalculationError(
                "Scenario produces negative "
                "stressed volatility."
            )

        stressed_rate = (
            risk_free_rate
            + scenario.risk_free_rate_shock
        )

        expiration = _normalise_date(
            position.contract.expiration,
            "expiration",
        )

        stressed_valuation_date = (
            valuation_date
            + timedelta(
                days=scenario.time_shift_days
            )
        )

        if stressed_valuation_date > expiration:
            stressed_valuation_date = expiration

        return (
            float(stressed_spot),
            float(stressed_rate),
            float(stressed_volatility),
            stressed_valuation_date,
        )

    # ==================================================================
    # POSITION STRESS
    # ==================================================================

    def stress_position(
        self,
        position: OptionPosition,
        *,
        spot: float,
        risk_free_rate: float,
        volatility: float,
        valuation_date: date | datetime,
        scenario: OptionStressScenario,
    ) -> OptionStressResult:
        """
        Revalue one option position under one stress scenario.

        The base valuation and stressed valuation are both delegated to
        the existing R4.3 Black-Scholes engine.
        """

        self._validate_position(
            position
        )

        self._validate_scenario(
            scenario
        )

        (
            spot,
            risk_free_rate,
            volatility,
            valuation_date,
        ) = self._validate_market_inputs(
            spot=spot,
            risk_free_rate=risk_free_rate,
            volatility=volatility,
            valuation_date=valuation_date,
        )

        contract = position.contract

        expiration = _normalise_date(
            contract.expiration,
            "expiration",
        )

        if expiration < valuation_date:
            raise OptionsStressValidationError(
                "expiration cannot precede "
                "valuation_date."
            )

        try:
            base_valuation = (
                self.valuation_engine.value_position(
                    position,
                    spot_price=spot,
                    risk_free_rate=risk_free_rate,
                    dividend_yield=DEFAULT_DIVIDEND_YIELD,
                    volatility=volatility,
                    valuation_date=valuation_date,
                )
            )
        except (
            BlackScholesCalculationError,
            ArithmeticError,
            ValueError,
            TypeError,
        ) as exc:
            raise OptionsStressCalculationError(
                "Unable to calculate base option "
                "valuation."
            ) from exc

        (
            stressed_spot,
            stressed_rate,
            stressed_volatility,
            stressed_valuation_date,
        ) = self._stressed_inputs(
            position=position,
            scenario=scenario,
            spot=spot,
            risk_free_rate=risk_free_rate,
            volatility=volatility,
            valuation_date=valuation_date,
        )

        try:
            stressed_valuation = (
                self.valuation_engine.value_position(
                    position,
                    spot_price=stressed_spot,
                    risk_free_rate=stressed_rate,
                    dividend_yield=DEFAULT_DIVIDEND_YIELD,
                    volatility=stressed_volatility,
                    valuation_date=(
                        stressed_valuation_date
                    ),
                )
            )
        except (
            BlackScholesCalculationError,
            ArithmeticError,
            ValueError,
            TypeError,
        ) as exc:
            raise OptionsStressCalculationError(
                "Unable to calculate stressed "
                "option valuation."
            ) from exc

        base_position_value = float(
            base_valuation.position_value
        )

        stressed_position_value = float(
            stressed_valuation.position_value
        )

        pnl = (
            stressed_position_value
            - base_position_value
        )

        absolute_loss = max(
            -pnl,
            0.0,
        )

        pnl_percentage = _safe_percentage(
            pnl,
            base_position_value,
            self.tolerance,
        )

        if pnl < -self.tolerance:
            status = SCENARIO_STATUS_LOSS
        elif pnl > self.tolerance:
            status = SCENARIO_STATUS_GAIN
        else:
            status = SCENARIO_STATUS_FLAT

        expiration_days_base = (
            expiration
            - valuation_date
        ).days

        expiration_days_stressed = (
            expiration
            - stressed_valuation_date
        ).days

        base_time_to_expiry = (
            float(expiration_days_base)
            / 365.0
        )

        stressed_time_to_expiry = (
            float(expiration_days_stressed)
            / 365.0
        )

        result = OptionStressResult(
            scenario_name=scenario.name,
            position_id=position.position_id,
            contract_id=contract.contract_id,
            underlying=contract.underlying,
            option_type=contract.option_type,
            valuation_date=valuation_date.isoformat(),
            stressed_valuation_date=(
                stressed_valuation_date.isoformat()
            ),
            expiration=expiration.isoformat(),
            base_spot=spot,
            stressed_spot=stressed_spot,
            base_volatility=volatility,
            stressed_volatility=(
                stressed_volatility
            ),
            base_risk_free_rate=(
                risk_free_rate
            ),
            stressed_risk_free_rate=(
                stressed_rate
            ),
            base_time_to_expiry=(
                base_time_to_expiry
            ),
            stressed_time_to_expiry=(
                stressed_time_to_expiry
            ),
            quantity=float(position.quantity),
            multiplier=float(contract.multiplier),
            base_option_price=float(
                base_valuation.option_price
            ),
            stressed_option_price=float(
                stressed_valuation.option_price
            ),
            base_position_value=(
                base_position_value
            ),
            stressed_position_value=(
                stressed_position_value
            ),
            pnl=float(pnl),
            pnl_percentage=(
                None
                if pnl_percentage is None
                else float(pnl_percentage)
            ),
            absolute_loss=float(
                absolute_loss
            ),
            status=status,
            diagnostics={
                "method": (
                    "r4.8_deterministic_option_stress"
                ),
                "valuation_engine": (
                    "BlackScholesEngine"
                ),
                "valuation_api_version": (
                    self.valuation_engine.API_VERSION
                ),
                "dividend_yield": DEFAULT_DIVIDEND_YIELD,
                "spot_shock": (
                    scenario.spot_shock
                ),
                "volatility_shock": (
                    scenario.volatility_shock
                ),
                "risk_free_rate_shock": (
                    scenario.risk_free_rate_shock
                ),
                "time_shift_days": (
                    scenario.time_shift_days
                ),
                "spot_shock_convention": (
                    "relative"
                ),
                "volatility_shock_convention": (
                    "absolute"
                ),
                "rate_shock_convention": (
                    "absolute"
                ),
                "time_shock_convention": (
                    "forward_calendar_days"
                ),
                "position_scaling": (
                    "signed_quantity_times_contract_multiplier"
                ),
                "european_only": True,
            },
        )

        self.last_result = result

        return result

    # ==================================================================
    # PORTFOLIO STRESS
    # ==================================================================

    def stress_portfolio(
        self,
        positions: Sequence[OptionPosition],
        *,
        market_inputs: dict[
            str,
            dict[str, Any],
        ],
        valuation_date: date | datetime,
        scenario: OptionStressScenario,
    ) -> OptionsStressPortfolioResult:
        """
        Stress an option portfolio.

        market_inputs maps each underlying to:

            {
                "spot": float,
                "risk_free_rate": float,
                "volatility": float,
                # R4.8 currently uses DEFAULT_DIVIDEND_YIELD = 0.0.
            }

        Each position is independently valued using the market inputs
        for its underlying.
        """

        self._validate_scenario(
            scenario
        )

        if not isinstance(
            positions,
            Sequence,
        ):
            raise OptionsStressValidationError(
                "positions must be a sequence."
            )

        if not isinstance(
            market_inputs,
            dict,
        ):
            raise OptionsStressValidationError(
                "market_inputs must be a dictionary."
            )

        valuation_date = _normalise_date(
            valuation_date,
            "valuation_date",
        )

        position_results: list[
            OptionStressResult
        ] = []

        for position in positions:
            self._validate_position(
                position
            )

            underlying = position.contract.underlying

            if underlying not in market_inputs:
                raise OptionsStressValidationError(
                    "Missing market inputs for "
                    f"underlying '{underlying}'."
                )

            inputs = market_inputs[
                underlying
            ]

            if not isinstance(
                inputs,
                dict,
            ):
                raise OptionsStressValidationError(
                    "Market inputs for "
                    f"'{underlying}' must be a dictionary."
                )

            required = (
                "spot",
                "risk_free_rate",
                "volatility",
            )

            missing = [
                field
                for field in required
                if field not in inputs
            ]

            if missing:
                raise OptionsStressValidationError(
                    "Missing market inputs for "
                    f"'{underlying}': "
                    f"{missing}"
                )

            result = self.stress_position(
                position,
                spot=inputs["spot"],
                risk_free_rate=(
                    inputs["risk_free_rate"]
                ),
                volatility=inputs["volatility"],
                valuation_date=valuation_date,
                scenario=scenario,
            )

            position_results.append(
                result
            )

        ordered_results = tuple(
            sorted(
                position_results,
                key=lambda item: (
                    item.underlying,
                    item.contract_id or "",
                    item.position_id or "",
                ),
            )
        )

        base_portfolio_value = sum(
            result.base_position_value
            for result in ordered_results
        )

        stressed_portfolio_value = sum(
            result.stressed_position_value
            for result in ordered_results
        )

        portfolio_pnl = (
            stressed_portfolio_value
            - base_portfolio_value
        )

        portfolio_loss = max(
            -portfolio_pnl,
            0.0,
        )

        pnl_percentage = _safe_percentage(
            portfolio_pnl,
            base_portfolio_value,
            self.tolerance,
        )

        loss_candidates = [
            result
            for result in ordered_results
            if result.pnl < -self.tolerance
        ]

        gain_candidates = [
            result
            for result in ordered_results
            if result.pnl > self.tolerance
        ]

        largest_loss = None

        if loss_candidates:
            largest_loss = min(
                loss_candidates,
                key=lambda item: item.pnl,
            )

        largest_gain = None

        if gain_candidates:
            largest_gain = max(
                gain_candidates,
                key=lambda item: item.pnl,
            )

        result = OptionsStressPortfolioResult(
            scenario_name=scenario.name,
            valuation_date=valuation_date.isoformat(),
            position_count=len(
                ordered_results
            ),
            base_portfolio_value=float(
                base_portfolio_value
            ),
            stressed_portfolio_value=float(
                stressed_portfolio_value
            ),
            portfolio_pnl=float(
                portfolio_pnl
            ),
            portfolio_loss=float(
                portfolio_loss
            ),
            pnl_percentage=(
                None
                if pnl_percentage is None
                else float(pnl_percentage)
            ),
            largest_loss_contributor=(
                None
                if largest_loss is None
                else (
                    largest_loss.position_id
                    or largest_loss.contract_id
                    or largest_loss.underlying
                )
            ),
            largest_gain_contributor=(
                None
                if largest_gain is None
                else (
                    largest_gain.position_id
                    or largest_gain.contract_id
                    or largest_gain.underlying
                )
            ),
            scenario_rank_metric=float(
                portfolio_loss
            ),
            position_results=ordered_results,
            diagnostics={
                "method": (
                    "r4.8_portfolio_option_stress"
                ),
                "aggregation": (
                    "sum_of_position_stress_pnl"
                ),
                "largest_loss_metric": (
                    "minimum_position_pnl"
                ),
                "scenario_rank_metric": (
                    "portfolio_absolute_loss"
                ),
                "deterministic_sorting": True,
            },
        )

        self.last_result = result

        return result

    # ==================================================================
    # MULTI-SCENARIO ENGINE
    # ==================================================================

    def run_scenarios(
        self,
        positions: Sequence[OptionPosition],
        *,
        market_inputs: dict[
            str,
            dict[str, Any],
        ],
        valuation_date: date | datetime,
        scenarios: Iterable[
            OptionStressScenario
        ],
    ) -> tuple[
        OptionsStressPortfolioResult,
        ...,
    ]:
        """
        Execute multiple deterministic stress scenarios.

        Results are sorted by descending portfolio loss and then by
        scenario name for deterministic ordering.
        """

        scenario_list = list(
            scenarios
        )

        if not scenario_list:
            raise OptionsStressValidationError(
                "At least one stress scenario "
                "is required."
            )

        for scenario in scenario_list:
            self._validate_scenario(
                scenario
            )

        results = [
            self.stress_portfolio(
                positions,
                market_inputs=market_inputs,
                valuation_date=valuation_date,
                scenario=scenario,
            )
            for scenario in scenario_list
        ]

        return tuple(
            sorted(
                results,
                key=lambda item: (
                    -item.portfolio_loss,
                    item.scenario_name,
                ),
            )
        )

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(
        self,
        result: (
            OptionStressResult
            | OptionsStressPortfolioResult
            | None
        ) = None,
    ) -> dict[str, Any]:
        """
        Return the latest or supplied stress result.
        """

        selected = (
            result
            if result is not None
            else self.last_result
        )

        if selected is None:
            raise OptionsStressError(
                "No options stress result "
                "is available."
            )

        return selected.to_dict()

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def health_check(self) -> dict[str, Any]:
        """
        Return deterministic component health information.
        """

        checks = {
            "valuation_engine": isinstance(
                self.valuation_engine,
                BlackScholesEngine,
            ),
            "stress_position": callable(
                self.stress_position
            ),
            "stress_portfolio": callable(
                self.stress_portfolio
            ),
            "run_scenarios": callable(
                self.run_scenarios
            ),
            "summary": callable(
                self.summary
            ),
            "european_only": (
                SUPPORTED_EXERCISE_STYLE
                == "european"
            ),
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
            "healthy": healthy,
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "checks": checks,
        }


# ======================================================================
# FACTORY
# ======================================================================


def create_option_stress_engine(
    *,
    valuation_engine: BlackScholesEngine | None = None,
    tolerance: float = DEFAULT_TOLERANCE,
) -> OptionsStressEngine:
    """
    Explicit factory for the R4.8 stress engine.
    """

    return OptionsStressEngine(
        valuation_engine=valuation_engine,
        tolerance=tolerance,
    )


# ======================================================================
# MODULE SUMMARY
# ======================================================================


def summary() -> dict[str, Any]:
    """
    Return deterministic module metadata.
    """

    return {
        "component": COMPONENT,
        "api_version": API_VERSION,
        "phase": PHASE,
        "public_objects": list(
            PUBLIC_OBJECTS
        ),
        "supported_option_types": sorted(
            SUPPORTED_OPTION_TYPES
        ),
        "exercise_style": (
            SUPPORTED_EXERCISE_STYLE
        ),
        "spot_stress": True,
        "volatility_stress": True,
        "rate_stress": True,
        "time_stress": True,
        "combined_stress": True,
        "position_stress": True,
        "portfolio_stress": True,
        "scenario_ranking": True,
        "greeks": False,
        "volatility_surface": False,
        "tail_risk": False,
        "governance": False,
        "execution": False,
    }


# ======================================================================
# STANDARD SCENARIOS
# ======================================================================


def standard_option_stress_scenarios() -> tuple[
    OptionStressScenario,
    ...,
]:
    """
    Return the deterministic base R4.8 scenario library.

    These are deliberately generic scenario definitions. They do not
    assume a particular underlying or portfolio.
    """

    return (
        OptionStressScenario(
            name="SPOT_DOWN_10",
            spot_shock=-0.10,
        ),
        OptionStressScenario(
            name="SPOT_DOWN_20",
            spot_shock=-0.20,
        ),
        OptionStressScenario(
            name="SPOT_DOWN_30",
            spot_shock=-0.30,
        ),
        OptionStressScenario(
            name="SPOT_UP_10",
            spot_shock=0.10,
        ),
        OptionStressScenario(
            name="SPOT_UP_20",
            spot_shock=0.20,
        ),
        OptionStressScenario(
            name="VOL_UP_5",
            volatility_shock=0.05,
        ),
        OptionStressScenario(
            name="VOL_UP_10",
            volatility_shock=0.10,
        ),
        OptionStressScenario(
            name="VOL_DOWN_5",
            volatility_shock=-0.05,
        ),
        OptionStressScenario(
            name="RATE_UP_1",
            risk_free_rate_shock=0.01,
        ),
        OptionStressScenario(
            name="RATE_DOWN_1",
            risk_free_rate_shock=-0.01,
        ),
        OptionStressScenario(
            name="TIME_DECAY_30D",
            time_shift_days=30,
        ),
        OptionStressScenario(
            name="TIME_DECAY_90D",
            time_shift_days=90,
        ),
        OptionStressScenario(
            name="SPOT_DOWN_20_VOL_UP_10",
            spot_shock=-0.20,
            volatility_shock=0.10,
        ),
        OptionStressScenario(
            name="SPOT_DOWN_30_VOL_UP_15",
            spot_shock=-0.30,
            volatility_shock=0.15,
        ),
        OptionStressScenario(
            name="SPOT_UP_20_VOL_DOWN_10",
            spot_shock=0.20,
            volatility_shock=-0.10,
        ),
    )


# ======================================================================
# SELF TEST
# ======================================================================


def _self_test() -> None:
    """
    Deterministic R4.8 self-test.
    """

    valuation_date = date(
        2026,
        1,
        1,
    )

    expiration = date(
        2027,
        1,
        1,
    )

    # --------------------------------------------------------------
    # CONTRACT
    # --------------------------------------------------------------

    contract = OptionContract(
        underlying="SPY",
        option_type="call",
        strike=100.0,
        expiration=expiration,
        multiplier=100.0,
        exercise_style="european",
        currency="USD",
        contract_id="R48-SPY-C-100",
    )

    position = OptionPosition(
        contract=contract,
        quantity=2.0,
    )

    # --------------------------------------------------------------
    # ENGINE
    # --------------------------------------------------------------

    engine = OptionsStressEngine()

    health = engine.health_check()

    assert health["healthy"] is True

    # --------------------------------------------------------------
    # SCENARIO
    # --------------------------------------------------------------

    scenario = OptionStressScenario(
        name="TEST_DOWN_20_VOL_UP_10",
        spot_shock=-0.20,
        volatility_shock=0.10,
    )

    assert scenario.name == (
        "TEST_DOWN_20_VOL_UP_10"
    )

    assert scenario.is_spot_stress is True
    assert scenario.is_volatility_stress is True
    assert scenario.is_combined is True

    # --------------------------------------------------------------
    # POSITION STRESS
    # --------------------------------------------------------------

    result = engine.stress_position(
        position,
        spot=100.0,
        risk_free_rate=0.05,
        volatility=0.20,
        valuation_date=valuation_date,
        scenario=scenario,
    )

    assert result.scenario_name == (
        "TEST_DOWN_20_VOL_UP_10"
    )

    assert result.base_spot == 100.0
    assert result.stressed_spot == 80.0

    assert (
        abs(
            result.stressed_volatility
            - 0.30
        )
        < 1e-12
    )

    assert result.quantity == 2.0
    assert result.multiplier == 100.0

    assert isfinite(
        result.base_option_price
    )

    assert isfinite(
        result.stressed_option_price
    )

    assert isfinite(
        result.base_position_value
    )

    assert isfinite(
        result.stressed_position_value
    )

    assert isfinite(
        result.pnl
    )

    # --------------------------------------------------------------
    # LONG POSITION LOSS
    # --------------------------------------------------------------

    down_result = engine.stress_position(
        position,
        spot=100.0,
        risk_free_rate=0.05,
        volatility=0.20,
        valuation_date=valuation_date,
        scenario=OptionStressScenario(
            name="DOWN_20",
            spot_shock=-0.20,
        ),
    )

    assert (
        down_result.stressed_spot
        == 80.0
    )

    assert (
        down_result.pnl
        < 0.0
    )

    assert (
        down_result.absolute_loss
        > 0.0
    )

    assert (
        down_result.status
        == SCENARIO_STATUS_LOSS
    )

    # --------------------------------------------------------------
    # SHORT POSITION SIGN
    # --------------------------------------------------------------

    short_position = OptionPosition(
        contract=contract,
        quantity=-2.0,
    )

    short_result = engine.stress_position(
        short_position,
        spot=100.0,
        risk_free_rate=0.05,
        volatility=0.20,
        valuation_date=valuation_date,
        scenario=OptionStressScenario(
            name="DOWN_20",
            spot_shock=-0.20,
        ),
    )

    assert (
        abs(
            short_result.pnl
            + down_result.pnl
        )
        < 1e-10
    )

    # --------------------------------------------------------------
    # TIME STRESS
    # --------------------------------------------------------------

    time_result = engine.stress_position(
        position,
        spot=100.0,
        risk_free_rate=0.05,
        volatility=0.20,
        valuation_date=valuation_date,
        scenario=OptionStressScenario(
            name="TIME_30",
            time_shift_days=30,
        ),
    )

    assert (
        time_result.stressed_valuation_date
        == date(
            2026,
            1,
            31,
        ).isoformat()
    )

    assert (
        time_result.stressed_time_to_expiry
        < time_result.base_time_to_expiry
    )

    # --------------------------------------------------------------
    # EXPIRY CLAMP
    # --------------------------------------------------------------

    expiry_stress = engine.stress_position(
        position,
        spot=100.0,
        risk_free_rate=0.05,
        volatility=0.20,
        valuation_date=valuation_date,
        scenario=OptionStressScenario(
            name="TIME_5000",
            time_shift_days=5000,
        ),
    )

    assert (
        expiry_stress.stressed_valuation_date
        == expiration.isoformat()
    )

    assert (
        expiry_stress.stressed_time_to_expiry
        == 0.0
    )

    # --------------------------------------------------------------
    # PORTFOLIO
    # --------------------------------------------------------------

    put_contract = OptionContract(
        underlying="SPY",
        option_type="put",
        strike=100.0,
        expiration=expiration,
        multiplier=100.0,
        exercise_style="european",
        currency="USD",
        contract_id="R48-SPY-P-100",
    )

    put_position = OptionPosition(
        contract=put_contract,
        quantity=1.0,
    )

    portfolio_result = engine.stress_portfolio(
        [
            position,
            put_position,
        ],
        market_inputs={
            "SPY": {
                "spot": 100.0,
                "risk_free_rate": 0.05,
                "volatility": 0.20,
            },
        },
        valuation_date=valuation_date,
        scenario=OptionStressScenario(
            name="PORTFOLIO_DOWN_20",
            spot_shock=-0.20,
        ),
    )

    assert (
        portfolio_result.position_count
        == 2
    )

    assert isfinite(
        portfolio_result.base_portfolio_value
    )

    assert isfinite(
        portfolio_result.stressed_portfolio_value
    )

    assert isfinite(
        portfolio_result.portfolio_pnl
    )

    assert isfinite(
        portfolio_result.portfolio_loss
    )

    assert (
        len(
            portfolio_result.position_results
        )
        == 2
    )

    # --------------------------------------------------------------
    # MULTI-SCENARIO
    # --------------------------------------------------------------

    scenarios = (
        OptionStressScenario(
            name="MILD_DOWN",
            spot_shock=-0.10,
        ),
        OptionStressScenario(
            name="SEVERE_DOWN",
            spot_shock=-0.30,
        ),
        OptionStressScenario(
            name="VOL_UP",
            volatility_shock=0.10,
        ),
    )

    scenario_results = engine.run_scenarios(
        [
            position,
            put_position,
        ],
        market_inputs={
            "SPY": {
                "spot": 100.0,
                "risk_free_rate": 0.05,
                "volatility": 0.20,
            },
        },
        valuation_date=valuation_date,
        scenarios=scenarios,
    )

    assert (
        len(scenario_results)
        == 3
    )

    # Results sorted by descending loss.
    for index in range(
        len(scenario_results) - 1
    ):
        assert (
            scenario_results[index]
            .portfolio_loss
            >=
            scenario_results[index + 1]
            .portfolio_loss
        )

    # --------------------------------------------------------------
    # SERIALIZATION
    # --------------------------------------------------------------

    scenario_payload = scenario.to_dict()

    assert (
        scenario_payload["name"]
        == "TEST_DOWN_20_VOL_UP_10"
    )

    result_payload = result.to_dict()

    assert (
        result_payload["underlying"]
        == "SPY"
    )

    assert (
        "pnl"
        in result_payload
    )

    portfolio_payload = (
        portfolio_result.to_dict()
    )

    assert (
        "position_results"
        in portfolio_payload
    )

    # --------------------------------------------------------------
    # AMERICAN REJECTION
    # --------------------------------------------------------------

    american_contract = OptionContract(
        underlying="SPY",
        option_type="call",
        strike=100.0,
        expiration=expiration,
        multiplier=100.0,
        exercise_style="american",
        currency="USD",
        contract_id="R48-SPY-C-100-AMERICAN",
    )

    american_position = OptionPosition(
        contract=american_contract,
        quantity=1.0,
    )

    rejected = False

    try:
        engine.stress_position(
            american_position,
            spot=100.0,
            risk_free_rate=0.05,
            volatility=0.20,
            valuation_date=valuation_date,
            scenario=OptionStressScenario(
                name="TEST",
                spot_shock=-0.10,
            ),
        )
    except OptionsStressValidationError:
        rejected = True

    assert rejected is True

    # --------------------------------------------------------------
    # INVALID SCENARIO
    # --------------------------------------------------------------

    rejected = False

    try:
        engine.stress_position(
            position,
            spot=100.0,
            risk_free_rate=0.05,
            volatility=0.20,
            valuation_date=valuation_date,
            scenario="INVALID",  # type: ignore[arg-type]
        )
    except OptionsStressValidationError:
        rejected = True

    assert rejected is True

    # --------------------------------------------------------------
    # INVALID MARKET INPUT
    # --------------------------------------------------------------

    rejected = False

    try:
        engine.stress_position(
            position,
            spot=-100.0,
            risk_free_rate=0.05,
            volatility=0.20,
            valuation_date=valuation_date,
            scenario=OptionStressScenario(
                name="TEST",
            ),
        )
    except OptionsStressValidationError:
        rejected = True

    assert rejected is True

    print(
        "R4.8 Options Stress Scenarios "
        "self-test: PASS"
    )


# ======================================================================
# MODULE ENTRY POINT
# ======================================================================


if __name__ == "__main__":
    _self_test()