"""
======================================================================
VOLATILITY SURFACE INPUTS
PHASE R4.7
======================================================================

Purpose
-------
Production input-data contract for the options volatility-surface layer.

This module is intentionally limited to:

    1. Volatility-surface observations
    2. Volatility-surface input collections
    3. Strict validation
    4. Deterministic normalization
    5. Deterministic serialization
    6. Data-quality diagnostics
    7. Component health checks

It does NOT perform:

    - option valuation
    - implied-volatility calculation
    - Black-Scholes pricing
    - Greeks calculation
    - portfolio Greek aggregation
    - put/call parity analysis
    - volatility-surface interpolation
    - volatility-surface fitting
    - volatility-surface smoothing
    - options stress testing
    - tail-risk aggregation
    - risk governance
    - execution

Those responsibilities belong to other R4 stages.

Architecture
------------

    OPTION CONTRACT
           |
           v
    MARKET OBSERVATION
           |
           v
    R4.7 VOLATILITY-SURFACE INPUTS
           |
           v
    R4.8 OPTIONS STRESS
           |
           v
    R4.9 TAIL RISK
           |
           v
    R4.10 RISK GOVERNOR
           |
           v
    R4.11 RISK REPORT

Design principles
-----------------
1. Immutable production objects.
2. Strict validation.
3. No silent coercion of invalid values.
4. Explicit option contract.
5. Explicit valuation date.
6. Explicit implied volatility.
7. Explicit market-quality fields where available.
8. Deterministic time-to-expiry.
9. Deterministic moneyness.
10. Deterministic serialization.
11. No volatility-surface construction in this module.
12. No dependency on the canonical ETF universe.
13. Options remain an additional instrument layer.

R4.7 Boundary
-------------

This module represents OBSERVED volatility information.

It does not decide:

    - which interpolation method to use
    - how to smooth observations
    - how to fill missing strikes
    - how to extrapolate wings
    - how to construct an arbitrage-free surface
    - how to transform volatility observations into trading signals

Those are downstream responsibilities.

======================================================================
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from math import isfinite, log
from typing import Any, Iterable

from optionsrisk import OptionContract


# ======================================================================
# MODULE METADATA
# ======================================================================

API_VERSION = "1.0.0"
COMPONENT = "VolatilitySurfaceInputs"
PHASE = "R4.7"

PUBLIC_OBJECTS = (
    "VolatilitySurfaceObservation",
    "VolatilitySurfaceInputSet",
)

PUBLIC_METHODS = (
    "validate_observation",
    "build_input_set",
    "summary",
    "health_check",
)


# ======================================================================
# CONSTANTS
# ======================================================================

DEFAULT_DAY_COUNT = 365.0

MIN_IMPLIED_VOLATILITY = 0.0

OPTION_TYPES = frozenset(
    {
        "call",
        "put",
    }
)

VALID_QUALITY_FLAGS = frozenset(
    {
        "valid",
        "stale",
        "illiquid",
        "wide_market",
        "indicative",
        "rejected",
    }
)


# ======================================================================
# EXCEPTIONS
# ======================================================================


class VolatilitySurfaceInputsError(Exception):
    """Base exception for R4.7 volatility-surface input failures."""


class VolatilitySurfaceInputsConfigurationError(
    VolatilitySurfaceInputsError
):
    """Raised when R4.7 configuration is invalid."""


class VolatilitySurfaceObservationValidationError(
    VolatilitySurfaceInputsError
):
    """Raised when an individual observation is invalid."""


class VolatilitySurfaceInputSetValidationError(
    VolatilitySurfaceInputsError
):
    """Raised when a collection of observations is invalid."""


# ======================================================================
# VALIDATION HELPERS
# ======================================================================


def _validate_non_empty_string(
    value: Any,
    field_name: str,
) -> str:
    """
    Validate a required non-empty string.

    Whitespace-only values are rejected.
    """

    if not isinstance(value, str):
        raise TypeError(
            f"{field_name} must be a string."
        )

    value = value.strip()

    if not value:
        raise ValueError(
            f"{field_name} cannot be empty."
        )

    return value


def _validate_finite_float(
    value: Any,
    field_name: str,
) -> float:
    """
    Validate a finite numerical scalar.

    No silent coercion is performed.
    """

    if isinstance(value, bool):
        raise TypeError(
            f"{field_name} must be a finite number."
        )

    if not isinstance(
        value,
        (int, float),
    ):
        raise TypeError(
            f"{field_name} must be a finite number."
        )

    numeric_value = float(value)

    if not isfinite(numeric_value):
        raise ValueError(
            f"{field_name} must be finite."
        )

    return numeric_value


def _validate_non_negative_float(
    value: Any,
    field_name: str,
) -> float:
    """
    Validate a finite non-negative numerical scalar.
    """

    numeric_value = _validate_finite_float(
        value,
        field_name,
    )

    if numeric_value < 0.0:
        raise ValueError(
            f"{field_name} cannot be negative."
        )

    return numeric_value


def _validate_positive_float(
    value: Any,
    field_name: str,
) -> float:
    """
    Validate a finite strictly positive numerical scalar.
    """

    numeric_value = _validate_finite_float(
        value,
        field_name,
    )

    if numeric_value <= 0.0:
        raise ValueError(
            f"{field_name} must be greater than zero."
        )

    return numeric_value


def _normalize_date(
    value: date | datetime,
    field_name: str,
) -> date:
    """
    Normalize a date/datetime into a date.

    Datetimes are accepted only as date-bearing observations.
    """

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    raise TypeError(
        f"{field_name} must be a date or datetime."
    )


def _date_to_string(
    value: date,
) -> str:
    """Return deterministic ISO date representation."""

    return value.isoformat()


def _validate_optional_string(
    value: Any,
    field_name: str,
) -> str | None:
    """
    Validate an optional string.

    None remains None.
    """

    if value is None:
        return None

    return _validate_non_empty_string(
        value,
        field_name,
    )


def _validate_optional_non_negative_float(
    value: Any,
    field_name: str,
) -> float | None:
    """
    Validate an optional non-negative numerical field.
    """

    if value is None:
        return None

    return _validate_non_negative_float(
        value,
        field_name,
    )


def _validate_quality_flag(
    value: str,
) -> str:
    """Validate the observation quality flag."""

    value = _validate_non_empty_string(
        value,
        "quality_flag",
    ).lower()

    if value not in VALID_QUALITY_FLAGS:
        raise ValueError(
            "quality_flag must be one of "
            f"{sorted(VALID_QUALITY_FLAGS)}."
        )

    return value


# ======================================================================
# VOLATILITY-SURFACE OBSERVATION
# ======================================================================


@dataclass(frozen=True)
class VolatilitySurfaceObservation:
    """
    Immutable observed volatility-surface input.

    implied_volatility
    ------------------
    Annualized implied volatility expressed as a decimal.

    Example:

        25% -> 0.25

    spot
    ----
    Underlying spot price observed at the valuation date.

    time_to_expiry
    --------------
    Deterministically derived using ACT/365:

        (expiration - valuation_date) / 365

    moneyness
    ---------
    Deterministically represented as:

        spot / strike

    log_moneyness
    -------------
    Deterministically represented as:

        log(spot / strike)

    Market-quality fields
    ---------------------
    bid, ask, volume and open_interest are optional because
    market-data availability is not guaranteed for every observation.

    This object does NOT calculate implied volatility.

    The supplied implied volatility must already be an observed or
    externally calculated market input.
    """

    contract_id: str | None
    underlying: str
    option_type: str
    strike: float
    expiration: str
    valuation_date: str

    spot: float
    implied_volatility: float

    time_to_expiry: float
    moneyness: float
    log_moneyness: float

    bid: float | None
    ask: float | None

    volume: float | None
    open_interest: float | None

    source: str | None
    quality_flag: str

    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """
        Return a deterministic JSON-safe representation.
        """

        return asdict(self)


# ======================================================================
# INPUT COLLECTION
# ======================================================================


@dataclass(frozen=True)
class VolatilitySurfaceInputSet:
    """
    Immutable collection of volatility-surface observations.

    The collection is deliberately an INPUT DATASET.

    It does not represent a fitted or interpolated volatility surface.
    """

    valuation_date: str
    observation_count: int

    observations: tuple[
        VolatilitySurfaceObservation,
        ...

    ]

    underlyings: tuple[str, ...]
    expirations: tuple[str, ...]
    strikes: tuple[float, ...]

    valid_observation_count: int
    rejected_observation_count: int

    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """
        Return a deterministic JSON-safe representation.
        """

        return {
            "valuation_date": self.valuation_date,
            "observation_count": self.observation_count,
            "observations": [
                observation.to_dict()
                for observation in self.observations
            ],
            "underlyings": list(
                self.underlyings
            ),
            "expirations": list(
                self.expirations
            ),
            "strikes": list(
                self.strikes
            ),
            "valid_observation_count": (
                self.valid_observation_count
            ),
            "rejected_observation_count": (
                self.rejected_observation_count
            ),
            "diagnostics": dict(
                self.diagnostics
            ),
        }


# ======================================================================
# ENGINE
# ======================================================================


class VolatilitySurfaceInputs:
    """
    Production R4.7 volatility-surface input validator.

    Responsibilities
    ----------------
    - validate individual observations
    - construct deterministic observation objects
    - construct immutable input collections
    - expose data-quality diagnostics
    - expose health checks

    Explicitly not responsible for surface construction.
    """

    API_VERSION = API_VERSION
    COMPONENT = COMPONENT
    PHASE = PHASE

    PUBLIC_METHODS = PUBLIC_METHODS

    DEFAULT_DAY_COUNT = DEFAULT_DAY_COUNT

    def __init__(
        self,
        day_count: float = DEFAULT_DAY_COUNT,
        tolerance: float = 1e-12,
    ) -> None:
        self.day_count = _validate_positive_float(
            day_count,
            "day_count",
        )

        self.tolerance = _validate_positive_float(
            tolerance,
            "tolerance",
        )

        self.last_observation: (
            VolatilitySurfaceObservation | None
        ) = None

        self.last_input_set: (
            VolatilitySurfaceInputSet | None
        ) = None

    # ==================================================================
    # CONTRACT VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_contract(
        contract: OptionContract,
    ) -> None:
        """
        Validate that the supplied object is an OptionContract.

        American contracts are not rejected here because R4.7 is an
        input-data layer rather than a valuation engine.

        Downstream European-only consumers may impose their own
        restrictions.
        """

        if not isinstance(
            contract,
            OptionContract,
        ):
            raise TypeError(
                "contract must be an OptionContract."
            )

    # ==================================================================
    # TIME CALCULATION
    # ==================================================================

    def _calculate_time_to_expiry(
        self,
        expiration: date | datetime,
        valuation_date: date | datetime,
    ) -> float:
        """
        Calculate ACT/365 time to expiry.
        """

        expiration_date = _normalize_date(
            expiration,
            "expiration",
        )

        valuation_date_value = _normalize_date(
            valuation_date,
            "valuation_date",
        )

        days = (
            expiration_date
            - valuation_date_value
        ).days

        if days < 0:
            raise ValueError(
                "expiration cannot be before "
                "valuation_date."
            )

        return days / self.day_count

    # ==================================================================
    # OBSERVATION VALIDATION
    # ==================================================================

    def validate_observation(
        self,
        contract: OptionContract,
        valuation_date: date | datetime,
        spot: float,
        implied_volatility: float,
        bid: float | None = None,
        ask: float | None = None,
        volume: float | None = None,
        open_interest: float | None = None,
        source: str | None = None,
        quality_flag: str = "valid",
    ) -> VolatilitySurfaceObservation:
        """
        Validate and construct one volatility-surface observation.

        Parameters
        ----------
        contract:
            Existing R4.2 OptionContract.

        valuation_date:
            Date on which the observation applies.

        spot:
            Underlying spot price.

        implied_volatility:
            Annualized implied volatility as a decimal.

        bid:
            Optional option bid price.

        ask:
            Optional option ask price.

        volume:
            Optional traded volume.

        open_interest:
            Optional open interest.

        source:
            Optional market-data source identifier.

        quality_flag:
            Data-quality classification.

        Returns
        -------
        VolatilitySurfaceObservation
            Immutable validated observation.
        """

        self._validate_contract(
            contract
        )

        valuation_date_value = _normalize_date(
            valuation_date,
            "valuation_date",
        )

        spot_value = _validate_positive_float(
            spot,
            "spot",
        )

        implied_volatility_value = (
            _validate_non_negative_float(
                implied_volatility,
                "implied_volatility",
            )
        )

        bid_value = (
            _validate_optional_non_negative_float(
                bid,
                "bid",
            )
        )

        ask_value = (
            _validate_optional_non_negative_float(
                ask,
                "ask",
            )
        )

        volume_value = (
            _validate_optional_non_negative_float(
                volume,
                "volume",
            )
        )

        open_interest_value = (
            _validate_optional_non_negative_float(
                open_interest,
                "open_interest",
            )
        )

        source_value = _validate_optional_string(
            source,
            "source",
        )

        quality_flag_value = _validate_quality_flag(
            quality_flag
        )

        strike_value = _validate_positive_float(
            contract.strike,
            "contract.strike",
        )

        if bid_value is not None and ask_value is not None:
            if ask_value < bid_value:
                raise ValueError(
                    "ask cannot be less than bid."
                )

        time_to_expiry = (
            self._calculate_time_to_expiry(
                expiration=contract.expiration,
                valuation_date=valuation_date_value,
            )
        )

        moneyness = spot_value / strike_value

        if not isfinite(moneyness):
            raise ValueError(
                "Calculated moneyness must be finite."
            )

        log_moneyness = log(
            moneyness
        )

        if not isfinite(log_moneyness):
            raise ValueError(
                "Calculated log_moneyness must be finite."
            )

        diagnostics = {
            "input_layer": "observed_volatility",
            "surface_construction": False,
            "interpolation": False,
            "extrapolation": False,
            "smoothing": False,
            "arbitrage_free_fit": False,
            "day_count": self.day_count,
            "time_convention": "ACT/365",
            "moneyness_definition": "spot_divided_by_strike",
            "log_moneyness_definition": (
                "natural_log_spot_divided_by_strike"
            ),
            "implied_volatility_definition": (
                "annualized_decimal"
            ),
        }

        observation = VolatilitySurfaceObservation(
            contract_id=contract.contract_id,
            underlying=contract.underlying,
            option_type=contract.option_type,
            strike=strike_value,
            expiration=_date_to_string(
                _normalize_date(
                    contract.expiration,
                    "contract.expiration",
                )
            ),
            valuation_date=_date_to_string(
                valuation_date_value
            ),
            spot=spot_value,
            implied_volatility=(
                implied_volatility_value
            ),
            time_to_expiry=time_to_expiry,
            moneyness=moneyness,
            log_moneyness=log_moneyness,
            bid=bid_value,
            ask=ask_value,
            volume=volume_value,
            open_interest=open_interest_value,
            source=source_value,
            quality_flag=quality_flag_value,
            diagnostics=diagnostics,
        )

        self.last_observation = observation

        return observation

    # ==================================================================
    # INPUT-SET CONSTRUCTION
    # ==================================================================

    def build_input_set(
        self,
        observations: Iterable[
            VolatilitySurfaceObservation
        ],
        valuation_date: date | datetime | None = None,
    ) -> VolatilitySurfaceInputSet:
        """
        Construct an immutable volatility-surface input set.

        Observations are not recalculated.

        The collection layer validates object types and enforces
        deterministic ordering.

        Sorting key:

            underlying
            expiration
            strike
            option_type
            contract_id

        This guarantees deterministic serialization independent of
        the order in which observations were supplied.
        """

        if observations is None:
            raise TypeError(
                "observations cannot be None."
            )

        observation_list = list(
            observations
        )

        for index, observation in enumerate(
            observation_list
        ):
            if not isinstance(
                observation,
                VolatilitySurfaceObservation,
            ):
                raise TypeError(
                    "All observations must be "
                    "VolatilitySurfaceObservation "
                    f"instances. Invalid index: {index}."
                )

        if not observation_list:
            raise ValueError(
                "observations cannot be empty."
            )

        if valuation_date is not None:
            valuation_date_value = (
                _normalize_date(
                    valuation_date,
                    "valuation_date",
                )
            )

            valuation_date_string = (
                _date_to_string(
                    valuation_date_value
                )
            )

            mismatched = [
                observation
                for observation in observation_list
                if observation.valuation_date
                != valuation_date_string
            ]

            if mismatched:
                raise ValueError(
                    "All observations must use the "
                    "specified valuation_date."
                )

        else:
            valuation_dates = sorted(
                {
                    observation.valuation_date
                    for observation in observation_list
                }
            )

            if len(valuation_dates) != 1:
                raise ValueError(
                    "All observations must have the "
                    "same valuation_date when "
                    "valuation_date is not explicitly "
                    "provided."
                )

            valuation_date_string = (
                valuation_dates[0]
            )

        sorted_observations = tuple(
            sorted(
                observation_list,
                key=lambda observation: (
                    observation.underlying,
                    observation.expiration,
                    observation.strike,
                    observation.option_type,
                    observation.contract_id
                    or "",
                ),
            )
        )

        underlyings = tuple(
            sorted(
                {
                    observation.underlying
                    for observation in sorted_observations
                }
            )
        )

        expirations = tuple(
            sorted(
                {
                    observation.expiration
                    for observation in sorted_observations
                }
            )
        )

        strikes = tuple(
            sorted(
                {
                    observation.strike
                    for observation in sorted_observations
                }
            )
        )

        valid_observation_count = sum(
            observation.quality_flag
            == "valid"
            for observation in sorted_observations
        )

        rejected_observation_count = sum(
            observation.quality_flag
            == "rejected"
            for observation in sorted_observations
        )

        quality_counts: dict[str, int] = {}

        for observation in sorted_observations:
            quality_counts[
                observation.quality_flag
            ] = (
                quality_counts.get(
                    observation.quality_flag,
                    0,
                )
                + 1
            )

        diagnostics = {
            "surface_construction": False,
            "interpolation": False,
            "extrapolation": False,
            "smoothing": False,
            "arbitrage_free_fit": False,
            "unique_underlyings": len(
                underlyings
            ),
            "unique_expirations": len(
                expirations
            ),
            "unique_strikes": len(
                strikes
            ),
            "quality_counts": dict(
                sorted(
                    quality_counts.items()
                )
            ),
            "deterministic_ordering": True,
        }

        input_set = VolatilitySurfaceInputSet(
            valuation_date=valuation_date_string,
            observation_count=len(
                sorted_observations
            ),
            observations=sorted_observations,
            underlyings=underlyings,
            expirations=expirations,
            strikes=strikes,
            valid_observation_count=(
                valid_observation_count
            ),
            rejected_observation_count=(
                rejected_observation_count
            ),
            diagnostics=diagnostics,
        )

        self.last_input_set = input_set

        return input_set

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(self) -> dict[str, Any]:
        """
        Return deterministic component metadata and state.
        """

        return {
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "day_count": self.day_count,
            "time_convention": "ACT/365",
            "has_last_observation": (
                self.last_observation is not None
            ),
            "has_last_input_set": (
                self.last_input_set is not None
            ),
            "surface_construction": False,
            "interpolation": False,
            "extrapolation": False,
            "smoothing": False,
            "arbitrage_free_fit": False,
        }

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def health_check(self) -> dict[str, Any]:
        """
        Return production health status.
        """

        try:
            checks = {
                "configuration": (
                    isfinite(self.day_count)
                    and self.day_count > 0.0
                    and isfinite(self.tolerance)
                    and self.tolerance > 0.0
                ),
                "api_version": (
                    self.API_VERSION == "1.0.0"
                ),
                "component": (
                    self.COMPONENT
                    == "VolatilitySurfaceInputs"
                ),
                "phase": (
                    self.PHASE == "R4.7"
                ),
                "surface_construction_disabled": (
                    self.summary()[
                        "surface_construction"
                    ]
                    is False
                ),
                "interpolation_disabled": (
                    self.summary()[
                        "interpolation"
                    ]
                    is False
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

        except Exception as exc:
            return {
                "status": "UNHEALTHY",
                "healthy": False,
                "component": self.COMPONENT,
                "api_version": self.API_VERSION,
                "phase": self.PHASE,
                "error": str(exc),
            }


# ======================================================================
# FACTORY
# ======================================================================


def build_volatility_surface_inputs(
    day_count: float = DEFAULT_DAY_COUNT,
    tolerance: float = 1e-12,
) -> VolatilitySurfaceInputs:
    """
    Construct the production R4.7 volatility-surface input validator.
    """

    return VolatilitySurfaceInputs(
        day_count=day_count,
        tolerance=tolerance,
    )


# ======================================================================
# SELF-TEST
# ======================================================================


def test_volatility_surface_inputs() -> None:
    """
    Basic production self-test for R4.7.
    """

    from datetime import date

    from optionsrisk import OptionContract

    engine = VolatilitySurfaceInputs()

    # --------------------------------------------------------------
    # Contract
    # --------------------------------------------------------------

    contract = OptionContract(
        underlying="SPY",
        option_type="call",
        strike=500.0,
        expiration=date(
            2027,
            1,
            15,
        ),
        multiplier=100.0,
        exercise_style="european",
        currency="USD",
        contract_id="SPY-C-500-20270115",
    )

    # --------------------------------------------------------------
    # Observation
    # --------------------------------------------------------------

    observation = engine.validate_observation(
        contract=contract,
        valuation_date=date(
            2026,
            9,
            14,
        ),
        spot=510.0,
        implied_volatility=0.20,
        bid=19.50,
        ask=20.50,
        volume=1250,
        open_interest=25000,
        source="test",
        quality_flag="valid",
    )

    assert isinstance(
        observation,
        VolatilitySurfaceObservation,
    )

    assert observation.underlying == "SPY"

    assert observation.option_type == "call"

    assert observation.strike == 500.0

    assert observation.spot == 510.0

    assert observation.implied_volatility == 0.20

    assert observation.bid == 19.50

    assert observation.ask == 20.50

    assert observation.volume == 1250.0

    assert observation.open_interest == 25000.0

    assert observation.moneyness == 1.02

    assert observation.time_to_expiry > 0.0

    assert observation.diagnostics[
        "surface_construction"
    ] is False

    # --------------------------------------------------------------
    # Serialization
    # --------------------------------------------------------------

    serialized = observation.to_dict()

    assert serialized[
        "underlying"
    ] == "SPY"

    assert serialized[
        "implied_volatility"
    ] == 0.20

    # --------------------------------------------------------------
    # Input set
    # --------------------------------------------------------------

    second_contract = OptionContract(
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
        contract_id="SPY-P-500-20270115",
    )

    second_observation = (
        engine.validate_observation(
            contract=second_contract,
            valuation_date=date(
                2026,
                9,
                14,
            ),
            spot=510.0,
            implied_volatility=0.21,
            bid=18.50,
            ask=19.25,
            source="test",
            quality_flag="valid",
        )
    )

    input_set = engine.build_input_set(
        observations=[
            second_observation,
            observation,
        ]
    )

    assert isinstance(
        input_set,
        VolatilitySurfaceInputSet,
    )

    assert input_set.observation_count == 2

    assert input_set.valid_observation_count == 2

    assert input_set.rejected_observation_count == 0

    assert input_set.underlyings == (
        "SPY",
    )

    assert input_set.expirations == (
        "2027-01-15",
    )

    assert input_set.strikes == (
        500.0,
    )

    # Deterministic ordering:
    assert (
        input_set.observations[0].option_type
        == "call"
    )

    assert (
        input_set.observations[1].option_type
        == "put"
    )

    # --------------------------------------------------------------
    # Serialization of input set
    # --------------------------------------------------------------

    input_dict = input_set.to_dict()

    assert input_dict[
        "observation_count"
    ] == 2

    assert len(
        input_dict["observations"]
    ) == 2

    # --------------------------------------------------------------
    # Invalid volatility
    # --------------------------------------------------------------

    try:
        engine.validate_observation(
            contract=contract,
            valuation_date=date(
                2026,
                9,
                14,
            ),
            spot=510.0,
            implied_volatility=-0.10,
        )

    except ValueError:
        pass

    else:
        raise AssertionError(
            "Negative implied volatility "
            "must be rejected."
        )

    # --------------------------------------------------------------
    # Invalid spot
    # --------------------------------------------------------------

    try:
        engine.validate_observation(
            contract=contract,
            valuation_date=date(
                2026,
                9,
                14,
            ),
            spot=0.0,
            implied_volatility=0.20,
        )

    except ValueError:
        pass

    else:
        raise AssertionError(
            "Non-positive spot must be rejected."
        )

    # --------------------------------------------------------------
    # Invalid bid/ask
    # --------------------------------------------------------------

    try:
        engine.validate_observation(
            contract=contract,
            valuation_date=date(
                2026,
                9,
                14,
            ),
            spot=510.0,
            implied_volatility=0.20,
            bid=21.0,
            ask=20.0,
        )

    except ValueError:
        pass

    else:
        raise AssertionError(
            "ask < bid must be rejected."
        )

    # --------------------------------------------------------------
    # Expired observation
    # --------------------------------------------------------------

    try:
        engine.validate_observation(
            contract=contract,
            valuation_date=date(
                2028,
                1,
                1,
            ),
            spot=510.0,
            implied_volatility=0.20,
        )

    except ValueError:
        pass

    else:
        raise AssertionError(
            "Expiration before valuation date "
            "must be rejected."
        )

    # --------------------------------------------------------------
    # Invalid quality flag
    # --------------------------------------------------------------

    try:
        engine.validate_observation(
            contract=contract,
            valuation_date=date(
                2026,
                9,
                14,
            ),
            spot=510.0,
            implied_volatility=0.20,
            quality_flag="invalid-quality",
        )

    except ValueError:
        pass

    else:
        raise AssertionError(
            "Invalid quality flag must be rejected."
        )

    # --------------------------------------------------------------
    # Health
    # --------------------------------------------------------------

    health = engine.health_check()

    assert health["healthy"] is True

    assert health["status"] == "HEALTHY"

    assert health["component"] == (
        "VolatilitySurfaceInputs"
    )

    assert health["api_version"] == "1.0.0"

    assert health["phase"] == "R4.7"

    # --------------------------------------------------------------
    # Metadata
    # --------------------------------------------------------------

    summary = engine.summary()

    assert summary["component"] == (
        "VolatilitySurfaceInputs"
    )

    assert summary["phase"] == "R4.7"

    assert summary[
        "surface_construction"
    ] is False

    assert summary[
        "interpolation"
    ] is False


# ======================================================================
# MODULE SELF-EXECUTION
# ======================================================================


if __name__ == "__main__":
    test_volatility_surface_inputs()

    print(
        "VolatilitySurfaceInputs R4.7 "
        "self-test passed."
    )