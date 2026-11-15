"""
======================================================================
OPTIONS RISK MODEL
PHASE R4.2
======================================================================

Purpose
-------
Canonical contract and position models for the options-risk layer.

This module is intentionally limited to:

    1. OptionContract
    2. OptionPosition
    3. Strict validation
    4. Immutable production data structures
    5. Deterministic serialization

It does NOT perform:

    - option valuation
    - Black-Scholes pricing
    - implied-volatility calculation
    - Greeks calculation
    - portfolio Greek aggregation
    - put/call parity analysis
    - volatility-surface construction
    - options stress testing
    - tail-risk aggregation
    - risk governance
    - execution

Those responsibilities belong to later R4 stages.

Architecture
------------

    OPTIONS CONTRACT
           |
           v
    OPTIONS POSITION
           |
           v
    R4.3 VALUATION ENGINE
           |
           v
    R4.4 GREEKS
           |
           v
    R4.5 PORTFOLIO GREEKS
           |
           v
    R4.6 PARITY
           |
           v
    R4.7 VOL SURFACE
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
4. Explicit option type.
5. Explicit exercise style.
6. Explicit contract multiplier.
7. Explicit expiration.
8. Position quantity is signed.
9. Contract identity is deterministic.
10. Serialization is deterministic.
11. No pricing logic belongs in this module.
12. No dependency on the canonical ETF universe.
13. Options are an additional instrument layer.
======================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
from typing import Any, Mapping, Optional


# ======================================================================
# MODULE METADATA
# ======================================================================

API_VERSION = "1.0.0"
COMPONENT = "OptionsRiskModel"
PHASE = "R4.2"

PUBLIC_OBJECTS = (
    "OptionContract",
    "OptionPosition",
)


# ======================================================================
# CONSTANTS
# ======================================================================

OPTION_TYPES = frozenset(
    {
        "call",
        "put",
    }
)

EXERCISE_STYLES = frozenset(
    {
        "european",
        "american",
    }
)

DEFAULT_CURRENCY = "USD"
DEFAULT_MULTIPLIER = 100.0


# ======================================================================
# EXCEPTIONS
# ======================================================================


class OptionsRiskError(Exception):
    """
    Base exception for the options-risk model.
    """


class OptionsRiskConfigurationError(OptionsRiskError):
    """
    Raised when an options-risk configuration is invalid.
    """


class OptionContractValidationError(
    OptionsRiskError
):
    """
    Raised when an OptionContract contains invalid data.
    """


class OptionPositionValidationError(
    OptionsRiskError
):
    """
    Raised when an OptionPosition contains invalid data.
    """


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


def _validate_finite_positive(
    value: Any,
    field_name: str,
) -> float:
    """
    Validate a finite strictly positive numeric value.
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

    if not math.isfinite(numeric):
        raise ValueError(
            f"{field_name} must be finite."
        )

    if numeric <= 0.0:
        raise ValueError(
            f"{field_name} must be greater than zero."
        )

    return numeric


def _validate_finite_number(
    value: Any,
    field_name: str,
) -> float:
    """
    Validate a finite numeric value.

    Zero and negative values are permitted.
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

    if not math.isfinite(numeric):
        raise ValueError(
            f"{field_name} must be finite."
        )

    return numeric


def _validate_signed_quantity(
    value: Any,
) -> float:
    """
    Validate an option position quantity.

    Quantity is signed:

        positive -> long
        negative -> short

    Zero is allowed at the model layer because a position object may
    legitimately represent a flattened position.
    """

    return _validate_finite_number(
        value,
        "quantity",
    )


def _normalize_option_type(
    value: Any,
) -> str:
    """
    Normalize and validate option type.
    """

    value = _validate_non_empty_string(
        value,
        "option_type",
    ).lower()

    if value not in OPTION_TYPES:
        raise ValueError(
            "option_type must be one of "
            f"{sorted(OPTION_TYPES)}; got {value!r}."
        )

    return value


def _normalize_exercise_style(
    value: Any,
) -> str:
    """
    Normalize and validate exercise style.
    """

    value = _validate_non_empty_string(
        value,
        "exercise_style",
    ).lower()

    if value not in EXERCISE_STYLES:
        raise ValueError(
            "exercise_style must be one of "
            f"{sorted(EXERCISE_STYLES)}; got {value!r}."
        )

    return value


def _normalize_currency(
    value: Any,
) -> str:
    """
    Normalize a three-letter currency code.

    Currency is deliberately kept as metadata at R4.2.
    FX conversion is outside this module.
    """

    value = _validate_non_empty_string(
        value,
        "currency",
    ).upper()

    if len(value) != 3:
        raise ValueError(
            "currency must be a three-letter ISO-style code."
        )

    if not value.isalpha():
        raise ValueError(
            "currency must contain alphabetic characters only."
        )

    return value


def _validate_expiration(
    value: Any,
) -> date | datetime:
    """
    Validate option expiration.

    Both date and datetime are accepted.

    A datetime preserves timestamp information for later valuation.
    A date represents expiration at the contract's canonical expiry
    date and does not invent a time-of-day convention.
    """

    if isinstance(value, datetime):
        return value

    if isinstance(value, date):
        return value

    raise TypeError(
        "expiration must be a datetime or date."
    )


def _validate_metadata(
    value: Optional[Mapping[str, Any]],
    field_name: str,
) -> dict[str, Any]:
    """
    Validate optional metadata.

    Metadata is copied into a plain dictionary so the immutable model
    does not retain a caller-owned mutable mapping.
    """

    if value is None:
        return {}

    if not isinstance(value, Mapping):
        raise TypeError(
            f"{field_name} must be a mapping or None."
        )

    return dict(value)


def _expiration_key(
    expiration: date | datetime,
) -> str:
    """
    Produce a deterministic serialization key for expiration.
    """

    if isinstance(expiration, datetime):
        return expiration.isoformat()

    return expiration.isoformat()


# ======================================================================
# OPTION CONTRACT
# ======================================================================


@dataclass(frozen=True)
class OptionContract:
    """
    Immutable canonical representation of one option contract.

    Parameters
    ----------
    underlying:
        Underlying instrument identifier, e.g. "SPY".

    option_type:
        "call" or "put".

    strike:
        Strike price of the option.

    expiration:
        Contract expiration date or datetime.

    multiplier:
        Number of underlying units represented by one option contract.

        For many standardized U.S. equity options this is commonly 100,
        but the value must be explicit rather than assumed.

    exercise_style:
        "european" or "american".

    currency:
        Contract currency.

    contract_id:
        Optional external/native contract identifier.

    metadata:
        Additional non-authoritative contract metadata.

    Notes
    -----
    This class contains contract identity only.

    It deliberately does not contain:

        - implied volatility
        - interest rate
        - dividend yield
        - delta
        - gamma
        - vega
        - zomma
        - option price

    Those belong to later R4 layers.
    """

    underlying: str
    option_type: str
    strike: float
    expiration: date | datetime
    multiplier: float = DEFAULT_MULTIPLIER
    exercise_style: str = "european"
    currency: str = DEFAULT_CURRENCY
    contract_id: Optional[str] = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        """
        Validate and canonicalize the contract.
        """

        try:
            underlying = _validate_non_empty_string(
                self.underlying,
                "underlying",
            )

            option_type = _normalize_option_type(
                self.option_type,
            )

            strike = _validate_finite_positive(
                self.strike,
                "strike",
            )

            expiration = _validate_expiration(
                self.expiration,
            )

            multiplier = _validate_finite_positive(
                self.multiplier,
                "multiplier",
            )

            exercise_style = _normalize_exercise_style(
                self.exercise_style,
            )

            currency = _normalize_currency(
                self.currency,
            )

            contract_id = self.contract_id

            if contract_id is not None:
                contract_id = _validate_non_empty_string(
                    contract_id,
                    "contract_id",
                )

            metadata = _validate_metadata(
                self.metadata,
                "metadata",
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise OptionContractValidationError(
                str(exc)
            ) from exc

        object.__setattr__(
            self,
            "underlying",
            underlying.upper(),
        )

        object.__setattr__(
            self,
            "option_type",
            option_type,
        )

        object.__setattr__(
            self,
            "strike",
            strike,
        )

        object.__setattr__(
            self,
            "expiration",
            expiration,
        )

        object.__setattr__(
            self,
            "multiplier",
            multiplier,
        )

        object.__setattr__(
            self,
            "exercise_style",
            exercise_style,
        )

        object.__setattr__(
            self,
            "currency",
            currency,
        )

        object.__setattr__(
            self,
            "contract_id",
            contract_id,
        )

        object.__setattr__(
            self,
            "metadata",
            metadata,
        )

    # ------------------------------------------------------------------
    # CONTRACT IDENTITY
    # ------------------------------------------------------------------

    @property
    def identity(self) -> tuple[Any, ...]:
        """
        Return deterministic contract identity.

        The external contract_id is deliberately excluded.

        Identity is based on the economic contract definition.
        """

        return (
            self.underlying,
            self.option_type,
            self.strike,
            _expiration_key(self.expiration),
            self.multiplier,
            self.exercise_style,
            self.currency,
        )

    # ------------------------------------------------------------------
    # DIRECTION
    # ------------------------------------------------------------------

    @property
    def is_call(self) -> bool:
        """
        Return True when the contract is a call.
        """

        return self.option_type == "call"

    @property
    def is_put(self) -> bool:
        """
        Return True when the contract is a put.
        """

        return self.option_type == "put"

    @property
    def is_european(self) -> bool:
        """
        Return True when the contract is European style.
        """

        return self.exercise_style == "european"

    @property
    def is_american(self) -> bool:
        """
        Return True when the contract is American style.
        """

        return self.exercise_style == "american"

    # ------------------------------------------------------------------
    # SERIALIZATION
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize the contract deterministically.
        """

        return {
            "underlying": self.underlying,
            "option_type": self.option_type,
            "strike": float(self.strike),
            "expiration": _expiration_key(
                self.expiration,
            ),
            "multiplier": float(self.multiplier),
            "exercise_style": self.exercise_style,
            "currency": self.currency,
            "contract_id": self.contract_id,
            "metadata": dict(self.metadata),
        }


# ======================================================================
# OPTION POSITION
# ======================================================================


@dataclass(frozen=True)
class OptionPosition:
    """
    Immutable representation of an option position.

    Parameters
    ----------
    contract:
        Canonical OptionContract.

    quantity:
        Signed number of option contracts.

        Positive:
            long position

        Negative:
            short position

        Zero:
            flat position

    market_price:
        Current option premium per option unit.

        This is optional because R4.2 does not own market-data
        acquisition. R4.3 valuation and later market-data integration
        may provide authoritative pricing.

    average_entry_price:
        Optional average entry premium per option unit.

    position_id:
        Optional external position identifier.

    metadata:
        Additional non-authoritative position metadata.

    Notes
    -----
    The position model does not calculate P&L or Greeks.

    Contract multiplier is obtained from the associated
    OptionContract.
    """

    contract: OptionContract
    quantity: float
    market_price: Optional[float] = None
    average_entry_price: Optional[float] = None
    position_id: Optional[str] = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        """
        Validate and canonicalize the option position.
        """

        if not isinstance(
            self.contract,
            OptionContract,
        ):
            raise OptionPositionValidationError(
                "contract must be an OptionContract."
            )

        try:
            quantity = _validate_signed_quantity(
                self.quantity,
            )

            market_price = self.market_price

            if market_price is not None:
                market_price = _validate_finite_number(
                    market_price,
                    "market_price",
                )

                if market_price < 0.0:
                    raise ValueError(
                        "market_price cannot be negative."
                    )

            average_entry_price = (
                self.average_entry_price
            )

            if average_entry_price is not None:
                average_entry_price = _validate_finite_number(
                    average_entry_price,
                    "average_entry_price",
                )

                if average_entry_price < 0.0:
                    raise ValueError(
                        "average_entry_price cannot be negative."
                    )

            position_id = self.position_id

            if position_id is not None:
                position_id = _validate_non_empty_string(
                    position_id,
                    "position_id",
                )

            metadata = _validate_metadata(
                self.metadata,
                "metadata",
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise OptionPositionValidationError(
                str(exc)
            ) from exc

        object.__setattr__(
            self,
            "quantity",
            quantity,
        )

        object.__setattr__(
            self,
            "market_price",
            market_price,
        )

        object.__setattr__(
            self,
            "average_entry_price",
            average_entry_price,
        )

        object.__setattr__(
            self,
            "position_id",
            position_id,
        )

        object.__setattr__(
            self,
            "metadata",
            metadata,
        )

    # ------------------------------------------------------------------
    # POSITION DIRECTION
    # ------------------------------------------------------------------

    @property
    def is_long(self) -> bool:
        """
        Return True when the position is long.
        """

        return self.quantity > 0.0

    @property
    def is_short(self) -> bool:
        """
        Return True when the position is short.
        """

        return self.quantity < 0.0

    @property
    def is_flat(self) -> bool:
        """
        Return True when the position quantity is zero.
        """

        return math.isclose(
            self.quantity,
            0.0,
            abs_tol=1e-12,
        )

    # ------------------------------------------------------------------
    # NOTIONAL EXPOSURE
    # ------------------------------------------------------------------

    @property
    def contract_units(self) -> float:
        """
        Return signed underlying units represented by the position.

        This is:

            quantity × multiplier

        No underlying price is used.
        """

        return (
            self.quantity
            * self.contract.multiplier
        )

    @property
    def market_value(self) -> Optional[float]:
        """
        Return signed market value when market_price is available.

        Formula:

            quantity × multiplier × market_price

        If market_price is unavailable, return None.
        """

        if self.market_price is None:
            return None

        return (
            self.quantity
            * self.contract.multiplier
            * self.market_price
        )

    @property
    def entry_value(self) -> Optional[float]:
        """
        Return signed entry value when average entry price exists.
        """

        if self.average_entry_price is None:
            return None

        return (
            self.quantity
            * self.contract.multiplier
            * self.average_entry_price
        )

    # ------------------------------------------------------------------
    # SERIALIZATION
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize the position deterministically.
        """

        return {
            "contract": self.contract.to_dict(),
            "quantity": float(self.quantity),
            "market_price": (
                None
                if self.market_price is None
                else float(self.market_price)
            ),
            "average_entry_price": (
                None
                if self.average_entry_price is None
                else float(self.average_entry_price)
            ),
            "position_id": self.position_id,
            "metadata": dict(self.metadata),
        }


# ======================================================================
# MODEL FACTORY HELPERS
# ======================================================================


def create_option_contract(
    *,
    underlying: str,
    option_type: str,
    strike: float,
    expiration: date | datetime,
    multiplier: float = DEFAULT_MULTIPLIER,
    exercise_style: str = "european",
    currency: str = DEFAULT_CURRENCY,
    contract_id: Optional[str] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> OptionContract:
    """
    Explicit factory for constructing an OptionContract.
    """

    return OptionContract(
        underlying=underlying,
        option_type=option_type,
        strike=strike,
        expiration=expiration,
        multiplier=multiplier,
        exercise_style=exercise_style,
        currency=currency,
        contract_id=contract_id,
        metadata=metadata,
    )


def create_option_position(
    *,
    contract: OptionContract,
    quantity: float,
    market_price: Optional[float] = None,
    average_entry_price: Optional[float] = None,
    position_id: Optional[str] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> OptionPosition:
    """
    Explicit factory for constructing an OptionPosition.
    """

    return OptionPosition(
        contract=contract,
        quantity=quantity,
        market_price=market_price,
        average_entry_price=average_entry_price,
        position_id=position_id,
        metadata=metadata,
    )


# ======================================================================
# MODULE HEALTH
# ======================================================================


def health_check() -> dict[str, Any]:
    """
    Return deterministic module health information.

    R4.2 is a data-model layer, so health is based on the availability
    of its canonical public objects.
    """

    checks = {
        "option_contract": callable(
            OptionContract
        ),
        "option_position": callable(
            OptionPosition
        ),
        "contract_validation": (
            OptionContractValidationError
            is not None
        ),
        "position_validation": (
            OptionPositionValidationError
            is not None
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
        "component": COMPONENT,
        "api_version": API_VERSION,
        "phase": PHASE,
        "checks": checks,
    }


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
        "option_types": sorted(
            OPTION_TYPES
        ),
        "exercise_styles": sorted(
            EXERCISE_STYLES
        ),
        "default_currency": DEFAULT_CURRENCY,
        "default_multiplier": DEFAULT_MULTIPLIER,
        "valuation": False,
        "greeks": False,
        "portfolio_aggregation": False,
        "stress": False,
        "governance": False,
        "execution": False,
    }


# ======================================================================
# SELF TEST
# ======================================================================


def _self_test() -> None:
    """
    Run deterministic R4.2 model tests.
    """

    # --------------------------------------------------------------
    # CONTRACT CREATION
    # --------------------------------------------------------------

    contract = OptionContract(
        underlying="SPY",
        option_type="call",
        strike=600.0,
        expiration=date(
            2027,
            1,
            15,
        ),
        multiplier=100.0,
        exercise_style="european",
        currency="USD",
    )

    assert contract.underlying == "SPY"
    assert contract.option_type == "call"
    assert contract.strike == 600.0
    assert contract.multiplier == 100.0
    assert contract.is_call is True
    assert contract.is_put is False
    assert contract.is_european is True
    assert contract.is_american is False

    # --------------------------------------------------------------
    # CONTRACT SERIALIZATION
    # --------------------------------------------------------------

    serialized_contract = (
        contract.to_dict()
    )

    assert (
        serialized_contract["underlying"]
        == "SPY"
    )

    assert (
        serialized_contract["option_type"]
        == "call"
    )

    assert (
        serialized_contract["strike"]
        == 600.0
    )

    # --------------------------------------------------------------
    # POSITION CREATION
    # --------------------------------------------------------------

    position = OptionPosition(
        contract=contract,
        quantity=2.0,
        market_price=12.50,
        average_entry_price=10.00,
    )

    assert position.is_long is True
    assert position.is_short is False
    assert position.is_flat is False

    assert (
        position.contract_units
        == 200.0
    )

    assert (
        position.market_value
        == 2500.0
    )

    assert (
        position.entry_value
        == 2000.0
    )

    # --------------------------------------------------------------
    # SHORT POSITION
    # --------------------------------------------------------------

    short_position = OptionPosition(
        contract=contract,
        quantity=-3.0,
        market_price=8.0,
    )

    assert short_position.is_short is True
    assert short_position.is_long is False

    assert (
        short_position.contract_units
        == -300.0
    )

    assert (
        short_position.market_value
        == -2400.0
    )

    # --------------------------------------------------------------
    # FLAT POSITION
    # --------------------------------------------------------------

    flat_position = OptionPosition(
        contract=contract,
        quantity=0.0,
    )

    assert flat_position.is_flat is True
    assert flat_position.market_value is None

    # --------------------------------------------------------------
    # PUT
    # --------------------------------------------------------------

    put_contract = OptionContract(
        underlying="QQQ",
        option_type="put",
        strike=500.0,
        expiration=date(
            2027,
            6,
            18,
        ),
    )

    assert put_contract.is_put is True
    assert put_contract.is_call is False

    # --------------------------------------------------------------
    # AMERICAN CONTRACT
    # --------------------------------------------------------------

    american_contract = OptionContract(
        underlying="IWM",
        option_type="put",
        strike=200.0,
        expiration=date(
            2027,
            3,
            19,
        ),
        exercise_style="american",
    )

    assert (
        american_contract.is_american
        is True
    )

    # --------------------------------------------------------------
    # VALIDATION TESTS
    # --------------------------------------------------------------

    invalid_cases = (
        {
            "underlying": "",
            "option_type": "call",
            "strike": 100.0,
            "expiration": date(2027, 1, 1),
        },
        {
            "underlying": "SPY",
            "option_type": "invalid",
            "strike": 100.0,
            "expiration": date(2027, 1, 1),
        },
        {
            "underlying": "SPY",
            "option_type": "call",
            "strike": 0.0,
            "expiration": date(2027, 1, 1),
        },
        {
            "underlying": "SPY",
            "option_type": "call",
            "strike": 100.0,
            "expiration": date(2027, 1, 1),
            "multiplier": 0.0,
        },
    )

    for kwargs in invalid_cases:
        try:
            OptionContract(
                **kwargs
            )
        except OptionContractValidationError:
            pass
        else:
            raise AssertionError(
                "Invalid OptionContract "
                "was accepted."
            )

    # --------------------------------------------------------------
    # INVALID POSITION CONTRACT
    # --------------------------------------------------------------

    try:
        OptionPosition(
            contract="SPY",
            quantity=1.0,
        )
    except OptionPositionValidationError:
        pass
    else:
        raise AssertionError(
            "Invalid OptionPosition contract "
            "was accepted."
        )

    # --------------------------------------------------------------
    # INVALID MARKET PRICE
    # --------------------------------------------------------------

    try:
        OptionPosition(
            contract=contract,
            quantity=1.0,
            market_price=-1.0,
        )
    except OptionPositionValidationError:
        pass
    else:
        raise AssertionError(
            "Negative market price was accepted."
        )

    # --------------------------------------------------------------
    # IMMUTABILITY
    # --------------------------------------------------------------

    try:
        contract.strike = 700.0
    except (
        AttributeError,
        TypeError,
    ):
        pass
    else:
        raise AssertionError(
            "OptionContract is not immutable."
        )

    try:
        position.quantity = 10.0
    except (
        AttributeError,
        TypeError,
    ):
        pass
    else:
        raise AssertionError(
            "OptionPosition is not immutable."
        )

    # --------------------------------------------------------------
    # HEALTH
    # --------------------------------------------------------------

    health = health_check()

    assert health["healthy"] is True
    assert health["status"] == "HEALTHY"
    assert (
        health["component"]
        == COMPONENT
    )
    assert (
        health["api_version"]
        == API_VERSION
    )
    assert (
        health["phase"]
        == PHASE
    )

    # --------------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------------

    module_summary = summary()

    assert (
        module_summary["component"]
        == COMPONENT
    )

    assert (
        module_summary["api_version"]
        == API_VERSION
    )

    assert (
        module_summary["phase"]
        == PHASE
    )

    assert (
        module_summary["valuation"]
        is False
    )

    assert (
        module_summary["greeks"]
        is False
    )

    print(
        "optionsrisk.py R4.2 self-test: PASS"
    )


# ======================================================================
# SCRIPT ENTRY POINT
# ======================================================================


if __name__ == "__main__":
    _self_test()