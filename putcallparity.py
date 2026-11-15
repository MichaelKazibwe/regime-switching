"""
======================================================================
PUT / CALL PARITY DIAGNOSTICS
PHASE R4.6
======================================================================

Purpose
-------
Production diagnostic layer for European put/call parity.

Canonical European put/call parity:

    C - P = S - K * exp(-rT)

Therefore:

    parity_value = S - K * exp(-rT)

    parity_deviation =
        (observed_call - observed_put)
        - parity_value

This module is intentionally limited to:

    1. Put/call parity diagnostics
    2. Strict validation
    3. Existing R4.3 valuation-result consumption
    4. Optional observed market-price comparison
    5. Deterministic serialization
    6. Tolerance-based parity status
    7. Component health checks

It does NOT perform:

    - Black-Scholes valuation
    - implied-volatility calculation
    - volatility-surface construction
    - Greeks calculation
    - portfolio Greek aggregation
    - options stress testing
    - tail-risk aggregation
    - risk governance
    - execution

Architecture
------------

    R4.2 OPTION CONTRACT
             |
             v
    R4.3 VALUATION ENGINE
             |
             v
    R4.4 ANALYTICAL GREEKS
             |
             v
    R4.5 PORTFOLIO GREEKS
             |
             v
    R4.6 PUT/CALL PARITY
             |
             v
    R4.7 VOLATILITY SURFACE
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

Parity scope
------------
This implementation uses European parity without dividends:

    C - P = S - K * exp(-rT)

Dividend-adjusted parity is deliberately NOT introduced here because
the existing architecture does not establish a dividend or continuous
dividend-yield input contract at this stage.

American options are explicitly rejected.

Design principles
-----------------
1. Immutable production result objects.
2. Strict numerical validation.
3. No duplicate pricing engine.
4. Existing R4.3 valuation results are consumed as inputs.
5. No silent treatment of American options as European.
6. Explicit tolerance configuration.
7. Deterministic serialization.
8. Relative deviation is guarded against zero denominators.
9. Diagnostics are observable.
10. No dependency on the canonical ETF universe.
11. No mutation of caller-owned objects.
12. Frozen public API.
======================================================================
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from math import exp, isfinite
from typing import Any

from blackscholes import OptionValuationResult
from optionsrisk import OptionContract


# ======================================================================
# MODULE METADATA
# ======================================================================

API_VERSION = "1.0.0"
COMPONENT = "PutCallParityDiagnostics"
PHASE = "R4.6"

PUBLIC_OBJECTS = (
    "PutCallParityResult",
)

PUBLIC_METHODS = (
    "analyze",
    "analyze_valuations",
    "summary",
    "health_check",
)


# ======================================================================
# EXCEPTIONS
# ======================================================================


class PutCallParityError(Exception):
    """Base exception for put/call parity diagnostics."""


class PutCallParityConfigurationError(
    PutCallParityError
):
    """Raised when parity-engine configuration is invalid."""


class PutCallParityCalculationError(
    PutCallParityError
):
    """Raised when a parity diagnostic cannot be completed."""


# ======================================================================
# RESULT OBJECT
# ======================================================================


@dataclass(frozen=True)
class PutCallParityResult:
    """
    Immutable put/call parity diagnostic.

    The theoretical relationship is:

        C - P = S - K * exp(-rT)

    All option prices are per option unit.

    ``observed_call_price`` and ``observed_put_price`` represent the
    prices actually supplied to the diagnostic.

    When R4.3 valuation results are supplied without observed market
    prices, their model option prices are used. In that case the
    diagnostic verifies the internal consistency of the valuation
    layer rather than measuring a market-arbitrage discrepancy.
    """

    underlying: str
    strike: float
    expiration: str
    valuation_date: str

    risk_free_rate: float
    time_to_expiry: float
    spot: float

    theoretical_parity_value: float

    observed_call_price: float
    observed_put_price: float

    observed_call_minus_put: float
    parity_deviation: float
    absolute_deviation: float
    relative_deviation: float

    tolerance: float
    within_tolerance: bool
    status: str

    call_contract_id: str | None
    put_contract_id: str | None

    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic JSON-safe representation."""
        return asdict(self)


# ======================================================================
# ENGINE
# ======================================================================


class PutCallParityDiagnostics:
    """
    Production European put/call parity diagnostic engine.
    """

    API_VERSION = API_VERSION
    COMPONENT = COMPONENT
    PHASE = PHASE
    PUBLIC_METHODS = PUBLIC_METHODS

    DEFAULT_TOLERANCE = 1e-8
    DEFAULT_RELATIVE_FLOOR = 1e-12

    def __init__(
        self,
        tolerance: float = DEFAULT_TOLERANCE,
        relative_floor: float = DEFAULT_RELATIVE_FLOOR,
    ) -> None:
        self.tolerance = self._validate_positive_scalar(
            tolerance,
            "tolerance",
        )

        self.relative_floor = self._validate_positive_scalar(
            relative_floor,
            "relative_floor",
        )

        self.last_result: PutCallParityResult | None = None
        self.analysis_count = 0

    # ==================================================================
    # VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_positive_scalar(
        value: float,
        name: str,
    ) -> float:
        """
        Validate a strictly positive finite scalar.
        """
        if isinstance(value, bool):
            raise PutCallParityConfigurationError(
                f"{name} must be numeric, not bool."
            )

        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise PutCallParityConfigurationError(
                f"{name} must be numeric."
            ) from exc

        if not isfinite(numeric):
            raise PutCallParityConfigurationError(
                f"{name} must be finite."
            )

        if numeric <= 0.0:
            raise PutCallParityConfigurationError(
                f"{name} must be greater than zero."
            )

        return numeric

    @staticmethod
    def _validate_scalar(
        value: float,
        name: str,
        *,
        minimum: float | None = None,
        strict_minimum: bool = False,
    ) -> float:
        """
        Validate a finite numerical calculation input.
        """
        if isinstance(value, bool):
            raise PutCallParityCalculationError(
                f"{name} must be numeric, not bool."
            )

        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise PutCallParityCalculationError(
                f"{name} must be numeric."
            ) from exc

        if not isfinite(numeric):
            raise PutCallParityCalculationError(
                f"{name} must be finite."
            )

        if minimum is not None:
            if strict_minimum and numeric <= minimum:
                raise PutCallParityCalculationError(
                    f"{name} must be greater than {minimum}."
                )

            if not strict_minimum and numeric < minimum:
                raise PutCallParityCalculationError(
                    f"{name} must be greater than or equal to "
                    f"{minimum}."
                )

        return numeric

    @staticmethod
    def _validate_contract(
        contract: OptionContract,
        name: str,
    ) -> None:
        """
        Validate an option contract for European parity.
        """
        if not isinstance(contract, OptionContract):
            raise PutCallParityCalculationError(
                f"{name} must be an OptionContract."
            )

        if contract.exercise_style != "european":
            raise PutCallParityCalculationError(
                "Put/call parity diagnostics support "
                "European options only. American options are "
                "explicitly rejected."
            )

        if contract.option_type not in (
            "call",
            "put",
        ):
            raise PutCallParityCalculationError(
                f"{name} must be a call or put contract."
            )

    @staticmethod
    def _validate_valuation(
        valuation: OptionValuationResult,
        name: str,
    ) -> None:
        """
        Validate an existing R4.3 valuation result.

        R4.6 consumes the valuation result and does not recalculate
        option valuation.
        """
        if not isinstance(
            valuation,
            OptionValuationResult,
        ):
            raise PutCallParityCalculationError(
                f"{name} must be an OptionValuationResult."
            )

    # ==================================================================
    # CONTRACT MATCHING
    # ==================================================================

    @staticmethod
    def _validate_pair_contracts(
        call_contract: OptionContract,
        put_contract: OptionContract,
    ) -> None:
        """
        Ensure the call and put belong to the same parity pair.
        """
        PutCallParityDiagnostics._validate_contract(
            call_contract,
            "call_contract",
        )

        PutCallParityDiagnostics._validate_contract(
            put_contract,
            "put_contract",
        )

        if call_contract.option_type != "call":
            raise PutCallParityCalculationError(
                "call_contract must have option_type='call'."
            )

        if put_contract.option_type != "put":
            raise PutCallParityCalculationError(
                "put_contract must have option_type='put'."
            )

        if (
            call_contract.underlying
            != put_contract.underlying
        ):
            raise PutCallParityCalculationError(
                "Call and put underlyings must match."
            )

        if not isfinite(
            float(call_contract.strike)
        ) or not isfinite(
            float(put_contract.strike)
        ):
            raise PutCallParityCalculationError(
                "Call and put strikes must be finite."
            )

        if not _close(
            float(call_contract.strike),
            float(put_contract.strike),
        ):
            raise PutCallParityCalculationError(
                "Call and put strikes must match."
            )

        call_expiration = (
            call_contract.expiration
        )
        put_expiration = (
            put_contract.expiration
        )

        if call_expiration != put_expiration:
            raise PutCallParityCalculationError(
                "Call and put expirations must match."
            )

        if (
            call_contract.currency
            != put_contract.currency
        ):
            raise PutCallParityCalculationError(
                "Call and put currencies must match."
            )

    # ==================================================================
    # PARITY CALCULATION
    # ==================================================================

    def analyze(
        self,
        *,
        call_contract: OptionContract,
        put_contract: OptionContract,
        spot: float,
        risk_free_rate: float,
        time_to_expiry: float,
        call_price: float,
        put_price: float,
        valuation_date: date | datetime | str,
        tolerance: float | None = None,
    ) -> PutCallParityResult:
        """
        Analyze European put/call parity.

        Parameters
        ----------
        call_contract:
            European call contract.

        put_contract:
            European put contract.

        spot:
            Current underlying spot price.

        risk_free_rate:
            Continuously compounded risk-free rate.

        time_to_expiry:
            ACT/365 year fraction supplied by the valuation layer.

        call_price:
            Observed or supplied call premium per option unit.

        put_price:
            Observed or supplied put premium per option unit.

        valuation_date:
            Date on which the diagnostic is performed.

        tolerance:
            Absolute parity-deviation tolerance. When omitted,
            the engine's configured tolerance is used.
        """
        self._validate_pair_contracts(
            call_contract,
            put_contract,
        )

        spot_value = self._validate_scalar(
            spot,
            "spot",
            minimum=0.0,
            strict_minimum=True,
        )

        rate = self._validate_scalar(
            risk_free_rate,
            "risk_free_rate",
        )

        expiry = self._validate_scalar(
            time_to_expiry,
            "time_to_expiry",
            minimum=0.0,
        )

        call_value = self._validate_scalar(
            call_price,
            "call_price",
            minimum=0.0,
        )

        put_value = self._validate_scalar(
            put_price,
            "put_price",
            minimum=0.0,
        )

        configured_tolerance = (
            self.tolerance
            if tolerance is None
            else self._validate_positive_scalar(
                tolerance,
                "tolerance",
            )
        )

        try:
            discount_factor = exp(
                -rate * expiry
            )

            theoretical_parity = (
                spot_value
                - float(call_contract.strike)
                * discount_factor
            )

        except (
            ArithmeticError,
            OverflowError,
            ValueError,
        ) as exc:
            raise PutCallParityCalculationError(
                "Unable to calculate put/call parity."
            ) from exc

        observed_difference = (
            call_value
            - put_value
        )

        deviation = (
            observed_difference
            - theoretical_parity
        )

        absolute_deviation = abs(
            deviation
        )

        denominator = max(
            abs(theoretical_parity),
            self.relative_floor,
        )

        relative_deviation = (
            absolute_deviation
            / denominator
        )

        within_tolerance = (
            absolute_deviation
            <= configured_tolerance
        )

        status = (
            "PASS"
            if within_tolerance
            else "BREACH"
        )

        valuation_date_string = (
            self._normalise_date_string(
                valuation_date
            )
        )

        expiration_string = (
            self._normalise_date_string(
                call_contract.expiration
            )
        )

        result = PutCallParityResult(
            underlying=call_contract.underlying,
            strike=float(call_contract.strike),
            expiration=expiration_string,
            valuation_date=valuation_date_string,
            risk_free_rate=rate,
            time_to_expiry=expiry,
            spot=spot_value,
            theoretical_parity_value=float(
                theoretical_parity
            ),
            observed_call_price=call_value,
            observed_put_price=put_value,
            observed_call_minus_put=float(
                observed_difference
            ),
            parity_deviation=float(
                deviation
            ),
            absolute_deviation=float(
                absolute_deviation
            ),
            relative_deviation=float(
                relative_deviation
            ),
            tolerance=float(
                configured_tolerance
            ),
            within_tolerance=bool(
                within_tolerance
            ),
            status=status,
            call_contract_id=(
                call_contract.contract_id
            ),
            put_contract_id=(
                put_contract.contract_id
            ),
            diagnostics={
                "method": (
                    "european_put_call_parity"
                ),
                "formula": (
                    "C_minus_P_equals_S_minus_K_exp_minus_rT"
                ),
                "dividend_adjustment": False,
                "exercise_style": "european",
                "relative_denominator_floor": (
                    self.relative_floor
                ),
                "pricing_engine": (
                    "external_input"
                ),
                "market_arbitrage_interpretation": (
                    "diagnostic_only"
                ),
            },
        )

        self.last_result = result
        self.analysis_count += 1

        return result

    # ==================================================================
    # R4.3 VALUATION RESULT CONSUMPTION
    # ==================================================================

    def analyze_valuations(
        self,
        *,
        call_valuation: OptionValuationResult,
        put_valuation: OptionValuationResult,
        valuation_date: date | datetime | str | None = None,
        tolerance: float | None = None,
        call_market_price: float | None = None,
        put_market_price: float | None = None,
    ) -> PutCallParityResult:
        """
        Analyze parity directly from existing R4.3 valuation results.

        R4.3 remains the sole pricing engine.

        By default:

            call_price = call_valuation.option_price
            put_price  = put_valuation.option_price

        Optional market prices can be supplied to measure market
        parity deviation rather than model-internal parity deviation.

        The R4.3 valuation result already carries:

            underlying
            option_type
            strike
            expiration
            valuation_date
            spot
            risk_free_rate
            time_to_expiry
            option_price

        No option valuation is recalculated here.
        """
        self._validate_valuation(
            call_valuation,
            "call_valuation",
        )

        self._validate_valuation(
            put_valuation,
            "put_valuation",
        )

        if call_valuation.option_type != "call":
            raise PutCallParityCalculationError(
                "call_valuation must represent a call."
            )

        if put_valuation.option_type != "put":
            raise PutCallParityCalculationError(
                "put_valuation must represent a put."
            )

        if (
            call_valuation.underlying
            != put_valuation.underlying
        ):
            raise PutCallParityCalculationError(
                "Call and put valuation underlyings must match."
            )

        if not _close(
            float(call_valuation.strike),
            float(put_valuation.strike),
        ):
            raise PutCallParityCalculationError(
                "Call and put valuation strikes must match."
            )

        if (
            call_valuation.expiration
            != put_valuation.expiration
        ):
            raise PutCallParityCalculationError(
                "Call and put valuation expirations must match."
            )

        if not _close(
            float(call_valuation.spot),
            float(put_valuation.spot),
        ):
            raise PutCallParityCalculationError(
                "Call and put spot prices must match."
            )

        if not _close(
            float(call_valuation.risk_free_rate),
            float(put_valuation.risk_free_rate),
        ):
            raise PutCallParityCalculationError(
                "Call and put risk-free rates must match."
            )

        if not _close(
            float(call_valuation.time_to_expiry),
            float(put_valuation.time_to_expiry),
        ):
            raise PutCallParityCalculationError(
                "Call and put time-to-expiry values must match."
            )

        call_price = (
            float(call_market_price)
            if call_market_price is not None
            else float(call_valuation.option_price)
        )

        put_price = (
            float(put_market_price)
            if put_market_price is not None
            else float(put_valuation.option_price)
        )

        if valuation_date is None:
            valuation_date = (
                call_valuation.valuation_date
            )

        result = self.analyze(
            call_contract=self._contract_from_valuation(
                call_valuation
            ),
            put_contract=self._contract_from_valuation(
                put_valuation
            ),
            spot=call_valuation.spot,
            risk_free_rate=(
                call_valuation.risk_free_rate
            ),
            time_to_expiry=(
                call_valuation.time_to_expiry
            ),
            call_price=call_price,
            put_price=put_price,
            valuation_date=valuation_date,
            tolerance=tolerance,
        )

        market_prices_supplied = (
            call_market_price is not None
            or put_market_price is not None
        )

        diagnostics = dict(
            result.diagnostics
        )

        diagnostics.update(
            {
                "source": (
                    "r4.3_option_valuation_results"
                ),
                "market_prices_supplied": (
                    market_prices_supplied
                ),
                "call_price_source": (
                    "market"
                    if call_market_price is not None
                    else "r4.3_valuation"
                ),
                "put_price_source": (
                    "market"
                    if put_market_price is not None
                    else "r4.3_valuation"
                ),
            }
        )

        final_result = PutCallParityResult(
            **{
                **result.to_dict(),
                "diagnostics": diagnostics,
            }
        )

        self.last_result = final_result

        return final_result

    # ==================================================================
    # CONTRACT RECONSTRUCTION
    # ==================================================================

    @staticmethod
    def _contract_from_valuation(
        valuation: OptionValuationResult,
    ) -> OptionContract:
        """
        Reconstruct the canonical contract identity represented by
        an R4.3 valuation result.

        The valuation result carries the required economic contract
        fields. The reconstruction is used only for parity identity
        validation.
        """
        return OptionContract(
            underlying=valuation.underlying,
            option_type=valuation.option_type,
            strike=float(valuation.strike),
            expiration=(
                PutCallParityDiagnostics._parse_date(
                    valuation.expiration
                )
            ),
            multiplier=float(
                valuation.multiplier
            ),
            exercise_style="european",
            currency="USD",
            contract_id=valuation.contract_id,
        )

    # ==================================================================
    # DATE HELPERS
    # ==================================================================

    @staticmethod
    def _parse_date(
        value: str | date | datetime,
    ) -> date:
        """
        Convert supported date representations to date.
        """
        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, date):
            return value

        if isinstance(value, str):
            try:
                return date.fromisoformat(
                    value
                )
            except ValueError as exc:
                raise PutCallParityCalculationError(
                    "Date string must use ISO format."
                ) from exc

        raise PutCallParityCalculationError(
            "Date must be a date, datetime, or ISO string."
        )

    @classmethod
    def _normalise_date_string(
        cls,
        value: date | datetime | str,
    ) -> str:
        """
        Return deterministic ISO date representation.
        """
        if isinstance(value, str):
            parsed = cls._parse_date(value)
            return parsed.isoformat()

        return cls._parse_date(value).isoformat()

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(
        self,
        result: PutCallParityResult | None = None,
    ) -> dict[str, Any]:
        """
        Return the supplied or latest parity result.
        """
        selected = (
            result
            if result is not None
            else self.last_result
        )

        if selected is None:
            raise PutCallParityError(
                "No parity result is available."
            )

        return selected.to_dict()

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def health_check(self) -> dict[str, Any]:
        """
        Return deterministic engine health information.
        """
        checks = {
            "component": (
                self.COMPONENT == "PutCallParityDiagnostics"
            ),
            "api_version": (
                self.API_VERSION == "1.0.0"
            ),
            "phase": (
                self.PHASE == "R4.6"
            ),
            "public_methods": (
                tuple(self.PUBLIC_METHODS)
                == (
                    "analyze",
                    "analyze_valuations",
                    "summary",
                    "health_check",
                )
            ),
            "tolerance": (
                isfinite(self.tolerance)
                and self.tolerance > 0.0
            ),
            "relative_floor": (
                isfinite(self.relative_floor)
                and self.relative_floor > 0.0
            ),
            "r4_3_result_type": (
                OptionValuationResult is not None
            ),
            "r4_2_contract_type": (
                OptionContract is not None
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
            "analysis_count": self.analysis_count,
            "checks": checks,
        }

    # ==================================================================
    # METADATA
    # ==================================================================

    @property
    def metadata(self) -> dict[str, Any]:
        """
        Return deterministic engine metadata.
        """
        return {
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "public_objects": list(
                PUBLIC_OBJECTS
            ),
            "public_methods": list(
                self.PUBLIC_METHODS
            ),
            "parity_formula": (
                "C - P = S - K * exp(-rT)"
            ),
            "exercise_style": "european",
            "dividend_adjustment": False,
            "tolerance": self.tolerance,
            "relative_floor": self.relative_floor,
            "valuation": False,
            "greeks": False,
            "portfolio_aggregation": False,
            "volatility_surface": False,
            "stress": False,
            "tail_risk": False,
            "governance": False,
            "execution": False,
        }


# ======================================================================
# NUMERICAL HELPER
# ======================================================================


def _close(
    left: float,
    right: float,
    *,
    tolerance: float = 1e-12,
) -> bool:
    """
    Deterministic floating-point comparison.
    """
    return abs(
        float(left) - float(right)
    ) <= tolerance


# ======================================================================
# MODULE FACTORY
# ======================================================================


def create_put_call_parity_engine(
    *,
    tolerance: float = (
        PutCallParityDiagnostics.DEFAULT_TOLERANCE
    ),
    relative_floor: float = (
        PutCallParityDiagnostics.DEFAULT_RELATIVE_FLOOR
    ),
) -> PutCallParityDiagnostics:
    """
    Explicit factory for the R4.6 parity engine.
    """
    return PutCallParityDiagnostics(
        tolerance=tolerance,
        relative_floor=relative_floor,
    )


# ======================================================================
# MODULE HEALTH
# ======================================================================


def health_check() -> dict[str, Any]:
    """
    Return module-level health information.
    """
    engine = PutCallParityDiagnostics()

    return engine.health_check()


# ======================================================================
# MODULE SUMMARY
# ======================================================================


def summary() -> dict[str, Any]:
    """
    Return deterministic module metadata.
    """
    engine = PutCallParityDiagnostics()

    return engine.metadata


# ======================================================================
# SELF TEST
# ======================================================================


def _self_test() -> None:
    """
    Run deterministic R4.6 parity diagnostics tests.
    """

    # ------------------------------------------------------------------
    # CONTRACTS
    # ------------------------------------------------------------------

    from datetime import date

    from optionsrisk import OptionContract

    call = OptionContract(
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
        contract_id="SPY-C-600-20270115",
    )

    put = OptionContract(
        underlying="SPY",
        option_type="put",
        strike=600.0,
        expiration=date(
            2027,
            1,
            15,
        ),
        multiplier=100.0,
        exercise_style="european",
        currency="USD",
        contract_id="SPY-P-600-20270115",
    )

    engine = PutCallParityDiagnostics(
        tolerance=1e-8,
    )

    # ------------------------------------------------------------------
    # EXACT PARITY
    # ------------------------------------------------------------------

    spot = 610.0
    rate = 0.04
    time_to_expiry = 0.5

    theoretical_parity = (
        spot
        - 600.0
        * exp(
            -rate
            * time_to_expiry
        )
    )

    call_price = 25.0
    put_price = (
        call_price
        - theoretical_parity
    )

    result = engine.analyze(
        call_contract=call,
        put_contract=put,
        spot=spot,
        risk_free_rate=rate,
        time_to_expiry=time_to_expiry,
        call_price=call_price,
        put_price=put_price,
        valuation_date=date(
            2026,
            9,
            14,
        ),
    )

    assert result.within_tolerance
    assert result.status == "PASS"

    assert abs(
        result.parity_deviation
    ) <= 1e-8

    assert (
        result.underlying
        == "SPY"
    )

    assert (
        result.strike
        == 600.0
    )

    # ------------------------------------------------------------------
    # PARITY BREACH
    # ------------------------------------------------------------------

    breached = engine.analyze(
        call_contract=call,
        put_contract=put,
        spot=spot,
        risk_free_rate=rate,
        time_to_expiry=time_to_expiry,
        call_price=call_price + 1.0,
        put_price=put_price,
        valuation_date=date(
            2026,
            9,
            14,
        ),
    )

    assert not breached.within_tolerance
    assert breached.status == "BREACH"

    assert (
        breached.parity_deviation
        > 0.99
    )

    assert (
        breached.absolute_deviation
        > 0.99
    )

    # ------------------------------------------------------------------
    # RELATIVE DEVIATION
    # ------------------------------------------------------------------

    assert (
        breached.relative_deviation
        >= 0.0
    )

    # ------------------------------------------------------------------
    # SERIALIZATION
    # ------------------------------------------------------------------

    exported = result.to_dict()

    assert (
        exported["underlying"]
        == "SPY"
    )

    assert (
        exported["status"]
        == "PASS"
    )

    assert (
        exported["within_tolerance"]
        is True
    )

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------

    summary_result = engine.summary(
        result
    )

    assert (
        summary_result["parity_deviation"]
        == result.parity_deviation
    )

    # ------------------------------------------------------------------
    # HEALTH
    # ------------------------------------------------------------------

    health = engine.health_check()

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

    # ------------------------------------------------------------------
    # METADATA
    # ------------------------------------------------------------------

    metadata = engine.metadata

    assert (
        metadata["component"]
        == COMPONENT
    )

    assert (
        metadata["api_version"]
        == API_VERSION
    )

    assert (
        metadata["phase"]
        == PHASE
    )

    assert (
        metadata["parity_formula"]
        == "C - P = S - K * exp(-rT)"
    )

    assert (
        metadata["dividend_adjustment"]
        is False
    )

    assert (
        metadata["valuation"]
        is False
    )

    assert (
        metadata["greeks"]
        is False
    )

    assert (
        metadata["portfolio_aggregation"]
        is False
    )

    assert (
        metadata["stress"]
        is False
    )

    assert (
        metadata["tail_risk"]
        is False
    )

    # ------------------------------------------------------------------
    # INVALID UNDERLYING
    # ------------------------------------------------------------------

    invalid_put = OptionContract(
        underlying="QQQ",
        option_type="put",
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

    try:
        engine.analyze(
            call_contract=call,
            put_contract=invalid_put,
            spot=spot,
            risk_free_rate=rate,
            time_to_expiry=time_to_expiry,
            call_price=call_price,
            put_price=put_price,
            valuation_date=date(
                2026,
                9,
                14,
            ),
        )
    except PutCallParityCalculationError:
        pass
    else:
        raise AssertionError(
            "Mismatched underlyings were accepted."
        )

    # ------------------------------------------------------------------
    # INVALID OPTION TYPE
    # ------------------------------------------------------------------

    try:
        engine.analyze(
            call_contract=put,
            put_contract=call,
            spot=spot,
            risk_free_rate=rate,
            time_to_expiry=time_to_expiry,
            call_price=call_price,
            put_price=put_price,
            valuation_date=date(
                2026,
                9,
                14,
            ),
        )
    except PutCallParityCalculationError:
        pass
    else:
        raise AssertionError(
            "Invalid call/put ordering was accepted."
        )

    # ------------------------------------------------------------------
    # AMERICAN OPTION REJECTION
    # ------------------------------------------------------------------

    american_call = OptionContract(
        underlying="SPY",
        option_type="call",
        strike=600.0,
        expiration=date(
            2027,
            1,
            15,
        ),
        multiplier=100.0,
        exercise_style="american",
        currency="USD",
    )

    try:
        engine.analyze(
            call_contract=american_call,
            put_contract=put,
            spot=spot,
            risk_free_rate=rate,
            time_to_expiry=time_to_expiry,
            call_price=call_price,
            put_price=put_price,
            valuation_date=date(
                2026,
                9,
                14,
            ),
        )
    except PutCallParityCalculationError:
        pass
    else:
        raise AssertionError(
            "American option was accepted."
        )

    # ------------------------------------------------------------------
    # API FREEZE
    # ------------------------------------------------------------------

    assert (
        PutCallParityDiagnostics.API_VERSION
        == "1.0.0"
    )

    assert tuple(
        PutCallParityDiagnostics.PUBLIC_METHODS
    ) == (
        "analyze",
        "analyze_valuations",
        "summary",
        "health_check",
    )

    assert hasattr(
        engine,
        "analyze",
    )

    assert hasattr(
        engine,
        "analyze_valuations",
    )

    assert hasattr(
        engine,
        "summary",
    )

    assert hasattr(
        engine,
        "health_check",
    )

    # ------------------------------------------------------------------
    # MODULE HEALTH
    # ------------------------------------------------------------------

    module_health = health_check()

    assert (
        module_health["healthy"]
        is True
    )

    # ------------------------------------------------------------------
    # MODULE SUMMARY
    # ------------------------------------------------------------------

    module_summary = summary()

    assert (
        module_summary["component"]
        == COMPONENT
    )

    assert (
        module_summary["phase"]
        == PHASE
    )

    print(
        "putcallparity.py R4.6 self-test: PASS"
    )


# ======================================================================
# SCRIPT ENTRY POINT
# ======================================================================


if __name__ == "__main__":
    _self_test()