"""
======================================================================
BLACK-SCHOLES OPTION VALUATION ENGINE
======================================================================

Phase
-----
R4.3

Purpose
-------
Production Black-Scholes valuation engine for European options.

Architecture
------------
OptionContract
      |
      v
BlackScholesEngine
      |
      v
OptionValuationResult
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
R4.8 Options Stress
      |
      v
R4.9 Options Tail Risk
      |
      v
R4.10 Options Risk Governor
      |
      v
R4.11 Risk Report

Design principles
-----------------
1. Black-Scholes is responsible only for European option valuation.
2. American options are explicitly rejected.
3. Greeks are NOT calculated in this phase.
4. Implied volatility is NOT calculated in this phase.
5. Put/call parity is NOT calculated in this phase.
6. Options stress is NOT calculated in this phase.
7. Portfolio risk governance is NOT performed here.
8. Inputs are strictly validated before valuation.
9. Caller-owned inputs are never mutated.
10. Results are immutable.
11. Valuation is deterministic for identical inputs.
12. Contract multiplier is applied only when valuing a position.
13. Contract-level option price is expressed on a per-underlying-unit basis.
14. Position market value is expressed in currency units.
15. Expired options are valued at intrinsic value.
16. Zero-time-to-expiry handling is explicit.
17. Non-finite numerical inputs fail closed.
18. European Black-Scholes is never silently applied to American options.

Black-Scholes assumptions
-------------------------
For a European call:

    C = S exp(-qT) N(d1) - K exp(-rT) N(d2)

For a European put:

    P = K exp(-rT) N(-d2) - S exp(-qT) N(-d1)

where:

    d1 = [ln(S/K) + (r - q + 0.5*sigma^2)T]
         / (sigma*sqrt(T))

    d2 = d1 - sigma*sqrt(T)

Parameters
----------
S
    Spot price of the underlying.

K
    Strike price.

T
    Time to expiry in years.

r
    Continuously compounded risk-free interest rate.

q
    Continuously compounded dividend yield.

sigma
    Annualized volatility.

Notes
-----
Rates, dividend yields and volatility are decimal quantities.

No external data source is queried by this engine.

======================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
from typing import Any

import numpy as np

from optionsrisk import (
    OptionContract,
    OptionPosition,
)


# ======================================================================
# EXCEPTIONS
# ======================================================================


class BlackScholesError(Exception):
    """
    Base exception for Black-Scholes valuation errors.
    """


class BlackScholesConfigurationError(
    BlackScholesError
):
    """
    Raised when Black-Scholes engine configuration is invalid.
    """


class BlackScholesCalculationError(
    BlackScholesError
):
    """
    Raised when a Black-Scholes valuation cannot be completed safely.
    """


# ======================================================================
# RESULT OBJECT
# ======================================================================


@dataclass(frozen=True)
class OptionValuationResult:
    """
    Immutable Black-Scholes valuation result.

    ``option_price`` is the theoretical option premium per underlying
    unit.

    ``position_value`` is the theoretical value of the complete position
    after applying quantity and contract multiplier.
    """

    contract_id: str | None

    underlying: str

    option_type: str

    strike: float

    expiration: str

    valuation_date: str

    spot_price: float

    risk_free_rate: float

    dividend_yield: float

    volatility: float

    time_to_expiry: float

    d1: float | None

    d2: float | None

    option_price: float

    intrinsic_value: float

    time_value: float

    moneyness: float

    quantity: float | None

    multiplier: float

    position_value: float | None

    diagnostics: dict[str, Any]

    # ------------------------------------------------------------------
    # SERIALIZATION
    # ------------------------------------------------------------------

    def to_dict(
        self,
    ) -> dict[str, Any]:
        """
        Serialize the valuation result.
        """

        return {
            "contract_id": self.contract_id,
            "underlying": self.underlying,
            "option_type": self.option_type,
            "strike": float(self.strike),
            "expiration": self.expiration,
            "valuation_date": self.valuation_date,
            "spot_price": float(self.spot_price),
            "risk_free_rate": float(
                self.risk_free_rate
            ),
            "dividend_yield": float(
                self.dividend_yield
            ),
            "volatility": float(
                self.volatility
            ),
            "time_to_expiry": float(
                self.time_to_expiry
            ),
            "d1": (
                None
                if self.d1 is None
                else float(self.d1)
            ),
            "d2": (
                None
                if self.d2 is None
                else float(self.d2)
            ),
            "option_price": float(
                self.option_price
            ),
            "intrinsic_value": float(
                self.intrinsic_value
            ),
            "time_value": float(
                self.time_value
            ),
            "moneyness": float(
                self.moneyness
            ),
            "quantity": (
                None
                if self.quantity is None
                else float(self.quantity)
            ),
            "multiplier": float(
                self.multiplier
            ),
            "position_value": (
                None
                if self.position_value is None
                else float(self.position_value)
            ),
            "diagnostics": dict(
                self.diagnostics
            ),
        }


# ======================================================================
# BLACK-SCHOLES ENGINE
# ======================================================================


class BlackScholesEngine:
    """
    Production Black-Scholes valuation engine.

    Responsibilities
    ----------------
    1. Validate European option contracts.
    2. Validate market inputs.
    3. Calculate time to expiry.
    4. Calculate d1 and d2.
    5. Calculate theoretical call prices.
    6. Calculate theoretical put prices.
    7. Calculate intrinsic value.
    8. Calculate time value.
    9. Value complete option positions.

    Explicit exclusions
    -------------------
    - American option valuation
    - implied volatility
    - Greeks
    - volatility surface construction
    - put/call parity diagnostics
    - stress testing
    - portfolio aggregation
    - risk governance
    """

    API_VERSION = "1.0.0"

    COMPONENT = "BlackScholesEngine"

    PHASE = "R4.3"

    PUBLIC_METHODS = (
        "price",
        "value_position",
        "summary",
        "health_check",
    )

    DEFAULT_TOLERANCE = 1e-10

    MIN_TIME_TO_EXPIRY = 0.0

    # ------------------------------------------------------------------
    # CONSTRUCTOR
    # ------------------------------------------------------------------

    def __init__(
        self,
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> None:
        """
        Initialize the Black-Scholes engine.
        """

        self.tolerance = self._validate_scalar(
            tolerance,
            "tolerance",
            strictly_positive=True,
        )

        self.last_result: (
            OptionValuationResult | None
        ) = None

        self.last_diagnostics: (
            dict[str, Any] | None
        ) = None

    # ==================================================================
    # VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_scalar(
        value: Any,
        name: str,
        *,
        strictly_positive: bool = False,
        non_negative: bool = False,
    ) -> float:
        """
        Validate one numerical scalar.
        """

        try:
            result = float(value)

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise BlackScholesCalculationError(
                f"{name} must be numeric."
            ) from exc

        if not np.isfinite(result):
            raise BlackScholesCalculationError(
                f"{name} must be finite."
            )

        if (
            strictly_positive
            and result <= 0.0
        ):
            raise BlackScholesCalculationError(
                f"{name} must be strictly positive."
            )

        if (
            non_negative
            and result < 0.0
        ):
            raise BlackScholesCalculationError(
                f"{name} cannot be negative."
            )

        return result

    # ------------------------------------------------------------------
    # CONTRACT VALIDATION
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_contract(
        contract: OptionContract,
    ) -> OptionContract:
        """
        Validate an option contract for Black-Scholes valuation.
        """

        if not isinstance(
            contract,
            OptionContract,
        ):
            raise BlackScholesCalculationError(
                "contract must be an OptionContract instance."
            )

        if contract.exercise_style != "european":
            raise BlackScholesCalculationError(
                "Black-Scholes valuation in R4.3 "
                "supports European options only. "
                "American options require a dedicated "
                "American-option valuation method."
            )

        if contract.option_type not in (
            "call",
            "put",
        ):
            raise BlackScholesCalculationError(
                "Option type must be 'call' or 'put'."
            )

        return contract

    # ------------------------------------------------------------------
    # DATE VALIDATION
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_valuation_date(
        valuation_date: date | datetime | None,
    ) -> date:
        """
        Normalize valuation date to a calendar date.
        """

        if valuation_date is None:
            return date.today()

        if isinstance(
            valuation_date,
            datetime,
        ):
            return valuation_date.date()

        if isinstance(
            valuation_date,
            date,
        ):
            return valuation_date

        raise BlackScholesCalculationError(
            "valuation_date must be a date, "
            "datetime, or None."
        )

    @staticmethod
    def _normalize_expiration(
        expiration: date | datetime,
    ) -> date:
        """
        Normalize contract expiration to a calendar date.
        """

        if isinstance(
            expiration,
            datetime,
        ):
            return expiration.date()

        if isinstance(
            expiration,
            date,
        ):
            return expiration

        raise BlackScholesCalculationError(
            "Option expiration must be a date "
            "or datetime."
        )

    @classmethod
    def _time_to_expiry(
        cls,
        expiration: date | datetime,
        valuation_date: date | datetime | None,
    ) -> float:
        """
        Calculate time to expiry in years.

        R4.3 uses a simple ACT/365 calendar convention.
        """

        expiry = cls._normalize_expiration(
            expiration
        )

        valuation = cls._normalize_valuation_date(
            valuation_date
        )

        days = (
            expiry - valuation
        ).days

        if days <= 0:
            return 0.0

        return float(days) / 365.0

    # ==================================================================
    # NORMAL DISTRIBUTION
    # ==================================================================

    @staticmethod
    def _normal_cdf(
        value: float,
    ) -> float:
        """
        Standard normal cumulative distribution function.

        Implemented with ``erf`` to avoid introducing an additional
        numerical dependency for this elementary operation.
        """

        value = float(value)

        return 0.5 * (
            1.0
            + math.erf(
                value
                / math.sqrt(2.0)
            )
        )

    # ==================================================================
    # INTRINSIC VALUE
    # ==================================================================

    @staticmethod
    def _intrinsic_value(
        option_type: str,
        spot_price: float,
        strike: float,
    ) -> float:
        """
        Calculate intrinsic value per underlying unit.
        """

        if option_type == "call":

            return max(
                spot_price - strike,
                0.0,
            )

        if option_type == "put":

            return max(
                strike - spot_price,
                0.0,
            )

        raise BlackScholesCalculationError(
            "Option type must be 'call' or 'put'."
        )

    # ==================================================================
    # BLACK-SCHOLES CORE
    # ==================================================================

    def _calculate_price(
        self,
        *,
        option_type: str,
        spot_price: float,
        strike: float,
        time_to_expiry: float,
        risk_free_rate: float,
        dividend_yield: float,
        volatility: float,
    ) -> tuple[
        float,
        float | None,
        float | None,
    ]:
        """
        Calculate Black-Scholes theoretical price.

        Returns
        -------
        tuple
            option_price, d1, d2
        """

        intrinsic = self._intrinsic_value(
            option_type,
            spot_price,
            strike,
        )

        # --------------------------------------------------------------
        # EXPIRY
        # --------------------------------------------------------------

        if time_to_expiry <= 0.0:

            return (
                intrinsic,
                None,
                None,
            )

        # --------------------------------------------------------------
        # POSITIVE VOLATILITY REQUIRED
        # --------------------------------------------------------------

        if volatility <= 0.0:

            discounted_strike = (
                strike
                * math.exp(
                    -risk_free_rate
                    * time_to_expiry
                )
            )

            discounted_spot = (
                spot_price
                * math.exp(
                    -dividend_yield
                    * time_to_expiry
                )
            )

            if option_type == "call":

                price = max(
                    discounted_spot
                    - discounted_strike,
                    0.0,
                )

            else:

                price = max(
                    discounted_strike
                    - discounted_spot,
                    0.0,
                )

            return (
                float(price),
                None,
                None,
            )

        sqrt_t = math.sqrt(
            time_to_expiry
        )

        denominator = (
            volatility
            * sqrt_t
        )

        if denominator <= 0.0:
            raise BlackScholesCalculationError(
                "Black-Scholes denominator "
                "must be positive."
            )

        numerator = (
            math.log(
                spot_price / strike
            )
            + (
                risk_free_rate
                - dividend_yield
                + 0.5
                * volatility**2
            )
            * time_to_expiry
        )

        d1 = (
            numerator
            / denominator
        )

        d2 = (
            d1
            - volatility
            * sqrt_t
        )

        nd1 = self._normal_cdf(d1)
        nd2 = self._normal_cdf(d2)

        discount_rate = math.exp(
            -risk_free_rate
            * time_to_expiry
        )

        discount_dividend = math.exp(
            -dividend_yield
            * time_to_expiry
        )

        if option_type == "call":

            price = (
                spot_price
                * discount_dividend
                * nd1
                - strike
                * discount_rate
                * nd2
            )

        else:

            price = (
                strike
                * discount_rate
                * self._normal_cdf(-d2)
                - spot_price
                * discount_dividend
                * self._normal_cdf(-d1)
            )

        if not np.isfinite(price):

            raise BlackScholesCalculationError(
                "Black-Scholes produced "
                "a non-finite option price."
            )

        # Numerical protection against tiny negative
        # floating-point values.

        if price < 0.0:

            if abs(price) <= self.tolerance:

                price = 0.0

            else:

                raise BlackScholesCalculationError(
                    "Black-Scholes produced "
                    "a materially negative option price."
                )

        return (
            float(price),
            float(d1),
            float(d2),
        )

    # ==================================================================
    # PRICE
    # ==================================================================

    def price(
        self,
        contract: OptionContract,
        spot_price: float,
        risk_free_rate: float,
        dividend_yield: float,
        volatility: float,
        valuation_date: date | datetime | None = None,
    ) -> OptionValuationResult:
        """
        Calculate the theoretical Black-Scholes value of an option.

        Parameters
        ----------
        contract:
            European OptionContract.

        spot_price:
            Current underlying spot price.

        risk_free_rate:
            Continuously compounded annual risk-free rate.

        dividend_yield:
            Continuously compounded annual dividend yield.

        volatility:
            Annualized volatility.

        valuation_date:
            Date used for time-to-expiry calculation.
            Defaults to today's local Python date.
        """

        contract = self._validate_contract(
            contract
        )

        spot_price = self._validate_scalar(
            spot_price,
            "spot_price",
            strictly_positive=True,
        )

        strike = self._validate_scalar(
            contract.strike,
            "strike",
            strictly_positive=True,
        )

        risk_free_rate = self._validate_scalar(
            risk_free_rate,
            "risk_free_rate",
        )

        dividend_yield = self._validate_scalar(
            dividend_yield,
            "dividend_yield",
        )

        volatility = self._validate_scalar(
            volatility,
            "volatility",
            non_negative=True,
        )

        valuation = self._normalize_valuation_date(
            valuation_date
        )

        expiration = self._normalize_expiration(
            contract.expiration
        )

        time_to_expiry = (
            self._time_to_expiry(
                expiration,
                valuation,
            )
        )

        option_price, d1, d2 = (
            self._calculate_price(
                option_type=contract.option_type,
                spot_price=spot_price,
                strike=strike,
                time_to_expiry=time_to_expiry,
                risk_free_rate=risk_free_rate,
                dividend_yield=dividend_yield,
                volatility=volatility,
            )
        )

        intrinsic_value = (
            self._intrinsic_value(
                contract.option_type,
                spot_price,
                strike,
            )
        )

        time_value = max(
            option_price
            - intrinsic_value,
            0.0,
        )

        moneyness = (
            spot_price / strike
        )

        diagnostics = {
            "phase": self.PHASE,
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "model": "Black-Scholes-Merton",
            "exercise_style": (
                contract.exercise_style
            ),
            "valuation_convention": (
                "ACT/365"
            ),
            "price_unit": (
                "per underlying unit"
            ),
            "position_value_included": False,
            "greeks_included": False,
            "implied_volatility_included": False,
            "parity_included": False,
            "stress_included": False,
        }

        result = OptionValuationResult(
            contract_id=contract.contract_id,
            underlying=contract.underlying,
            option_type=contract.option_type,
            strike=strike,
            expiration=expiration.isoformat(),
            valuation_date=valuation.isoformat(),
            spot_price=spot_price,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
            volatility=volatility,
            time_to_expiry=time_to_expiry,
            d1=d1,
            d2=d2,
            option_price=option_price,
            intrinsic_value=intrinsic_value,
            time_value=time_value,
            moneyness=moneyness,
            quantity=None,
            multiplier=float(
                contract.multiplier
            ),
            position_value=None,
            diagnostics=diagnostics,
        )

        self.last_result = result
        self.last_diagnostics = dict(
            diagnostics
        )

        return result

    # ==================================================================
    # POSITION VALUATION
    # ==================================================================

    def value_position(
        self,
        position: OptionPosition,
        spot_price: float,
        risk_free_rate: float,
        dividend_yield: float,
        volatility: float,
        valuation_date: date | datetime | None = None,
    ) -> OptionValuationResult:
        """
        Calculate theoretical value of an option position.

        Position value:

            option_price
            × quantity
            × contract_multiplier

        Quantity is signed, so short positions naturally produce
        negative position values.
        """

        if not isinstance(
            position,
            OptionPosition,
        ):
            raise BlackScholesCalculationError(
                "position must be an OptionPosition instance."
            )

        valuation = self.price(
            contract=position.contract,
            spot_price=spot_price,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
            volatility=volatility,
            valuation_date=valuation_date,
        )

        quantity = self._validate_scalar(
            position.quantity,
            "position.quantity",
        )

        multiplier = self._validate_scalar(
            position.contract.multiplier,
            "contract.multiplier",
            strictly_positive=True,
        )

        position_value = (
            valuation.option_price
            * quantity
            * multiplier
        )

        if not np.isfinite(
            position_value
        ):
            raise BlackScholesCalculationError(
                "Position valuation produced "
                "a non-finite value."
            )

        diagnostics = dict(
            valuation.diagnostics
        )

        diagnostics.update(
            {
                "position_valuation": True,
                "quantity": quantity,
                "contract_multiplier": multiplier,
                "signed_position": (
                    "long"
                    if quantity > 0.0
                    else (
                        "short"
                        if quantity < 0.0
                        else "flat"
                    )
                ),
            }
        )

        result = OptionValuationResult(
            contract_id=valuation.contract_id,
            underlying=valuation.underlying,
            option_type=valuation.option_type,
            strike=valuation.strike,
            expiration=valuation.expiration,
            valuation_date=valuation.valuation_date,
            spot_price=valuation.spot_price,
            risk_free_rate=valuation.risk_free_rate,
            dividend_yield=valuation.dividend_yield,
            volatility=valuation.volatility,
            time_to_expiry=valuation.time_to_expiry,
            d1=valuation.d1,
            d2=valuation.d2,
            option_price=valuation.option_price,
            intrinsic_value=valuation.intrinsic_value,
            time_value=valuation.time_value,
            moneyness=valuation.moneyness,
            quantity=quantity,
            multiplier=multiplier,
            position_value=float(
                position_value
            ),
            diagnostics=diagnostics,
        )

        self.last_result = result
        self.last_diagnostics = dict(
            diagnostics
        )

        return result

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(
        self,
    ) -> dict[str, Any]:
        """
        Return deterministic state for the most recent valuation.
        """

        return {
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "last_result_available": (
                self.last_result is not None
            ),
            "last_underlying": (
                None
                if self.last_result is None
                else self.last_result.underlying
            ),
            "last_option_type": (
                None
                if self.last_result is None
                else self.last_result.option_type
            ),
            "last_option_price": (
                None
                if self.last_result is None
                else self.last_result.option_price
            ),
            "last_position_value": (
                None
                if self.last_result is None
                else self.last_result.position_value
            ),
        }

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ) -> dict[str, Any]:
        """
        Return deterministic engine health.
        """

        try:

            checks = {
                "configuration": (
                    np.isfinite(
                        self.tolerance
                    )
                    and self.tolerance > 0.0
                ),
                "european_pricing_supported": True,
                "american_pricing_explicitly_rejected": True,
                "greeks_not_included_in_r4_3": True,
                "implied_volatility_not_included_in_r4_3": True,
                "parity_not_included_in_r4_3": True,
                "stress_not_included_in_r4_3": True,
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


# ======================================================================
# SELF TEST
# ======================================================================


def _self_test() -> None:
    """
    Deterministic R4.3 self-test.
    """

    # --------------------------------------------------------------
    # EUROPEAN CALL
    # --------------------------------------------------------------

    call = OptionContract(
        underlying="SPY",
        option_type="call",
        strike=100.0,
        expiration=date(
            2027,
            1,
            1,
        ),
        multiplier=100.0,
        exercise_style="european",
        currency="USD",
        contract_id="SPY-C-100-20270101",
    )

    engine = BlackScholesEngine()

    result = engine.price(
        contract=call,
        spot_price=100.0,
        risk_free_rate=0.05,
        dividend_yield=0.00,
        volatility=0.20,
        valuation_date=date(
            2026,
            1,
            1,
        ),
    )

    assert np.isfinite(
        result.option_price
    )

    assert result.option_price >= 0.0

    assert result.option_type == "call"

    assert result.underlying == "SPY"

    assert result.d1 is not None

    assert result.d2 is not None

    assert result.time_value >= 0.0

    assert np.isclose(
        result.option_price,
        10.45,
        atol=0.10,
    )

    # --------------------------------------------------------------
    # EUROPEAN PUT
    # --------------------------------------------------------------

    put = OptionContract(
        underlying="SPY",
        option_type="put",
        strike=100.0,
        expiration=date(
            2027,
            1,
            1,
        ),
        multiplier=100.0,
        exercise_style="european",
        currency="USD",
        contract_id="SPY-P-100-20270101",
    )

    put_result = engine.price(
        contract=put,
        spot_price=100.0,
        risk_free_rate=0.05,
        dividend_yield=0.00,
        volatility=0.20,
        valuation_date=date(
            2026,
            1,
            1,
        ),
    )

    assert np.isfinite(
        put_result.option_price
    )

    assert put_result.option_price >= 0.0

    assert put_result.option_type == "put"

    assert np.isclose(
        put_result.option_price,
        5.57,
        atol=0.10,
    )

    # --------------------------------------------------------------
    # POSITION VALUATION
    # --------------------------------------------------------------

    position = OptionPosition(
        contract=call,
        quantity=2.0,
    )

    position_result = engine.value_position(
        position=position,
        spot_price=100.0,
        risk_free_rate=0.05,
        dividend_yield=0.00,
        volatility=0.20,
        valuation_date=date(
            2026,
            1,
            1,
        ),
    )

    assert position_result.quantity == 2.0

    assert position_result.multiplier == 100.0

    assert position_result.position_value is not None

    assert np.isclose(
        position_result.position_value,
        position_result.option_price
        * 2.0
        * 100.0,
        atol=1e-8,
    )

    # --------------------------------------------------------------
    # SHORT POSITION
    # --------------------------------------------------------------

    short_position = OptionPosition(
        contract=call,
        quantity=-2.0,
    )

    short_result = engine.value_position(
        position=short_position,
        spot_price=100.0,
        risk_free_rate=0.05,
        dividend_yield=0.00,
        volatility=0.20,
        valuation_date=date(
            2026,
            1,
            1,
        ),
    )

    assert short_result.position_value is not None

    assert short_result.position_value < 0.0

    # --------------------------------------------------------------
    # EXPIRY
    # --------------------------------------------------------------

    expired_result = engine.price(
        contract=call,
        spot_price=110.0,
        risk_free_rate=0.05,
        dividend_yield=0.00,
        volatility=0.20,
        valuation_date=date(
            2027,
            1,
            1,
        ),
    )

    assert np.isclose(
        expired_result.option_price,
        10.0,
        atol=1e-10,
    )

    assert expired_result.d1 is None

    assert expired_result.d2 is None

    assert np.isclose(
        expired_result.time_value,
        0.0,
        atol=1e-10,
    )

    # --------------------------------------------------------------
    # PUT EXPIRY
    # --------------------------------------------------------------

    expired_put = engine.price(
        contract=put,
        spot_price=90.0,
        risk_free_rate=0.05,
        dividend_yield=0.00,
        volatility=0.20,
        valuation_date=date(
            2027,
            1,
            1,
        ),
    )

    assert np.isclose(
        expired_put.option_price,
        10.0,
        atol=1e-10,
    )

    # --------------------------------------------------------------
    # AMERICAN OPTION MUST BE REJECTED
    # --------------------------------------------------------------

    american_call = OptionContract(
        underlying="SPY",
        option_type="call",
        strike=100.0,
        expiration=date(
            2027,
            1,
            1,
        ),
        multiplier=100.0,
        exercise_style="american",
        currency="USD",
        contract_id="SPY-C-100-20270101-A",
    )

    try:

        engine.price(
            contract=american_call,
            spot_price=100.0,
            risk_free_rate=0.05,
            dividend_yield=0.00,
            volatility=0.20,
            valuation_date=date(
                2026,
                1,
                1,
            ),
        )

        raise AssertionError(
            "Expected American-option rejection."
        )

    except BlackScholesCalculationError:
        pass

    # --------------------------------------------------------------
    # INVALID SPOT
    # --------------------------------------------------------------

    try:

        engine.price(
            contract=call,
            spot_price=0.0,
            risk_free_rate=0.05,
            dividend_yield=0.00,
            volatility=0.20,
            valuation_date=date(
                2026,
                1,
                1,
            ),
        )

        raise AssertionError(
            "Expected invalid spot rejection."
        )

    except BlackScholesCalculationError:
        pass

    # --------------------------------------------------------------
    # INVALID VOLATILITY
    # --------------------------------------------------------------

    try:

        engine.price(
            contract=call,
            spot_price=100.0,
            risk_free_rate=0.05,
            dividend_yield=0.00,
            volatility=-0.20,
            valuation_date=date(
                2026,
                1,
                1,
            ),
        )

        raise AssertionError(
            "Expected invalid volatility rejection."
        )

    except BlackScholesCalculationError:
        pass

    # --------------------------------------------------------------
    # SERIALIZATION
    # --------------------------------------------------------------

    serialized = result.to_dict()

    assert (
        serialized["underlying"]
        == "SPY"
    )

    assert (
        serialized["option_type"]
        == "call"
    )

    assert np.isfinite(
        serialized["option_price"]
    )

    # --------------------------------------------------------------
    # HEALTH
    # --------------------------------------------------------------

    health = engine.health_check()

    assert health["healthy"] is True

    assert (
        health["api_version"]
        == "1.0.0"
    )

    assert (
        health["phase"]
        == "R4.3"
    )

    # --------------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------------

    summary = engine.summary()

    assert (
        summary["last_result_available"]
        is True
    )

    assert (
        summary["last_underlying"]
        == "SPY"
    )

    # --------------------------------------------------------------
    # API FREEZE
    # --------------------------------------------------------------

    assert (
        BlackScholesEngine.API_VERSION
        == "1.0.0"
    )

    assert tuple(
        BlackScholesEngine.PUBLIC_METHODS
    ) == (
        "price",
        "value_position",
        "summary",
        "health_check",
    )


# ======================================================================
# MAIN
# ======================================================================


if __name__ == "__main__":

    _self_test()

    print(
        "blackscholes.py R4.3 self-test: PASS"
    )