from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import date, datetime
from math import erf, exp, isfinite, pi, sqrt
from typing import Any

from optionsrisk import OptionContract, OptionPosition

"""
ANALYTICAL OPTIONS GREEKS
============================================================

R4.4 of the production options-risk architecture.

Responsibilities
----------------
- Analytical European Black-Scholes Greeks
- Contract-level Greeks
- Position-level Greeks
- Strict numerical validation
- Deterministic serialization
- Component health checks

Supported Greeks
----------------
- Delta
- Gamma
- Vega
- Theta
- Rho

Explicitly NOT responsible for
--------------------------------
- Black-Scholes valuation
- Implied volatility
- Put/call parity
- Volatility surfaces
- Options stress testing
- Portfolio aggregation
- Risk governance
- Execution

Those responsibilities belong to later R4 stages.

European options only
---------------------
American options are explicitly rejected because the analytical
Black-Scholes Greeks implemented here are European Black-Scholes
Greeks.
"""

# ============================================================
# MODULE METADATA
# ============================================================

API_VERSION = "1.0.0"
COMPONENT = "AnalyticalGreeksEngine"
PHASE = "R4.4"


# ============================================================
# EXCEPTIONS
# ============================================================


class AnalyticalGreeksError(Exception):
    """Base exception for analytical-Greeks failures."""


class AnalyticalGreeksConfigurationError(
    AnalyticalGreeksError
):
    """Raised when engine configuration is invalid."""


class AnalyticalGreeksCalculationError(
    AnalyticalGreeksError
):
    """Raised when a Greek calculation cannot be completed."""


# ============================================================
# RESULT OBJECT
# ============================================================


@dataclass(frozen=True)
class GreeksResult:
    """
    Immutable analytical Greeks result.

    Contract-level values are expressed per underlying unit.

    Position-level values are scaled by:

        signed quantity × contract multiplier
    """

    contract_id: str | None
    underlying: str
    option_type: str

    strike: float
    expiration: str
    valuation_date: str

    spot: float
    risk_free_rate: float
    volatility: float
    time_to_expiry: float

    d1: float | None
    d2: float | None

    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float

    quantity: float
    multiplier: float

    position_delta: float
    position_gamma: float
    position_vega: float
    position_theta: float
    position_rho: float

    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return asdict(self)


# ============================================================
# ENGINE
# ============================================================


class AnalyticalGreeksEngine:
    """
    Production analytical European Black-Scholes Greeks engine.
    """

    API_VERSION = API_VERSION
    COMPONENT = COMPONENT
    PHASE = PHASE

    PUBLIC_METHODS = (
        "greeks",
        "greeks_for_position",
        "summary",
        "health_check",
    )

    DEFAULT_TOLERANCE = 1e-12

    def __init__(
        self,
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> None:
        self.tolerance = float(tolerance)

        if (
            not isfinite(self.tolerance)
            or self.tolerance <= 0.0
        ):
            raise AnalyticalGreeksConfigurationError(
                "tolerance must be a positive finite number."
            )

        self.last_result: GreeksResult | None = None

    # ========================================================
    # VALIDATION
    # ========================================================

    @staticmethod
    def _validate_scalar(
        name: str,
        value: float,
        *,
        minimum: float | None = None,
        strict_minimum: bool = False,
    ) -> float:
        """
        Validate a scalar numerical input.
        """
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise AnalyticalGreeksCalculationError(
                f"{name} must be numeric."
            ) from exc

        if not isfinite(numeric):
            raise AnalyticalGreeksCalculationError(
                f"{name} must be finite."
            )

        if minimum is not None:
            if strict_minimum and numeric <= minimum:
                raise AnalyticalGreeksCalculationError(
                    f"{name} must be greater than {minimum}."
                )

            if not strict_minimum and numeric < minimum:
                raise AnalyticalGreeksCalculationError(
                    f"{name} must be greater than or equal to "
                    f"{minimum}."
                )

        return numeric

    @staticmethod
    def _validate_contract(
        contract: OptionContract,
    ) -> None:
        """
        Validate an OptionContract for R4.4.
        """
        if not isinstance(
            contract,
            OptionContract,
        ):
            raise AnalyticalGreeksCalculationError(
                "contract must be an OptionContract."
            )

        if contract.exercise_style != "european":
            raise AnalyticalGreeksCalculationError(
                "Analytical Black-Scholes Greeks support "
                "European options only. American options are "
                "explicitly rejected."
            )

        if contract.option_type not in (
            "call",
            "put",
        ):
            raise AnalyticalGreeksCalculationError(
                "option_type must be 'call' or 'put'."
            )

    # ========================================================
    # DATE / EXPIRY
    # ========================================================

    @staticmethod
    def _normalise_date(
        value: date | datetime,
        name: str,
    ) -> date:
        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, date):
            return value

        raise AnalyticalGreeksCalculationError(
            f"{name} must be a date or datetime."
        )

    @classmethod
    def _time_to_expiry(
        cls,
        valuation_date: date | datetime,
        expiration: date | datetime,
    ) -> float:
        """
        ACT/365 year fraction.

        This matches the convention established by the
        Black-Scholes valuation layer.
        """
        valuation = cls._normalise_date(
            valuation_date,
            "valuation_date",
        )

        expiry = cls._normalise_date(
            expiration,
            "expiration",
        )

        days = (
            expiry - valuation
        ).days

        if days < 0:
            raise AnalyticalGreeksCalculationError(
                "expiration cannot precede valuation_date."
            )

        return float(days) / 365.0

    # ========================================================
    # NORMAL DISTRIBUTION
    # ========================================================

    @staticmethod
    def _normal_pdf(
        value: float,
    ) -> float:
        return (
            exp(-0.5 * value * value)
            / sqrt(2.0 * pi)
        )

    @staticmethod
    def _normal_cdf(
        value: float,
    ) -> float:
        return 0.5 * (
            1.0
            + erf(value / sqrt(2.0))
        )

    # ========================================================
    # BLACK-SCHOLES d1 / d2
    # ========================================================

    @staticmethod
    def _d1_d2(
        spot: float,
        strike: float,
        rate: float,
        volatility: float,
        time_to_expiry: float,
    ) -> tuple[float, float]:
        """
        Calculate Black-Scholes d1 and d2.
        """
        sqrt_t = sqrt(time_to_expiry)

        d1 = (
            (
                __import__("math").log(
                    spot / strike
                )
                + (
                    rate
                    + 0.5 * volatility * volatility
                )
                * time_to_expiry
            )
            / (
                volatility * sqrt_t
            )
        )

        d2 = d1 - (
            volatility * sqrt_t
        )

        return d1, d2

    # ========================================================
    # EXPIRY GREEKS
    # ========================================================

    @staticmethod
    def _expiry_greeks(
        option_type: str,
        spot: float,
        strike: float,
    ) -> tuple[
        float,
        float,
        float,
        float,
        float,
    ]:
        """
        Deterministic expiry convention.

        Delta:
            Call ITM  = 1
            Call OTM  = 0
            Call ATM  = 0.5

            Put ITM   = -1
            Put OTM   = 0
            Put ATM   = -0.5

        Higher-order Greeks are set to zero at exact expiry.

        This avoids producing infinities or undefined numerical
        values at T = 0.
        """
        if (
            abs(spot - strike)
            <= 1e-12
        ):
            if option_type == "call":
                return (
                    0.5,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                )

            return (
                -0.5,
                0.0,
                0.0,
                0.0,
                0.0,
            )

        if option_type == "call":
            delta = (
                1.0
                if spot > strike
                else 0.0
            )
        else:
            delta = (
                -1.0
                if spot < strike
                else 0.0
            )

        return (
            delta,
            0.0,
            0.0,
            0.0,
            0.0,
        )

    # ========================================================
    # ZERO-VOLATILITY GREEKS
    # ========================================================

    @staticmethod
    def _zero_volatility_greeks(
        option_type: str,
        spot: float,
        strike: float,
        rate: float,
        time_to_expiry: float,
    ) -> tuple[
        float,
        float,
        float,
        float,
        float,
    ]:
        """
        Deterministic zero-volatility limit.

        With sigma = 0:

            call = max(S - K exp(-rT), 0)
            put  = max(K exp(-rT) - S, 0)

        Delta is determined by the discounted strike boundary.

        At the exact boundary, delta is conventionally set to
        the midpoint value.
        """
        discounted_strike = (
            strike
            * exp(
                -rate * time_to_expiry
            )
        )

        boundary_tolerance = 1e-12

        if (
            abs(
                spot
                - discounted_strike
            )
            <= boundary_tolerance
        ):
            if option_type == "call":
                delta = 0.5
                rho = (
                    time_to_expiry
                    * discounted_strike
                )
            else:
                delta = -0.5
                rho = (
                    -time_to_expiry
                    * discounted_strike
                )

            return (
                delta,
                0.0,
                0.0,
                0.0,
                rho,
            )

        if option_type == "call":
            in_the_money = (
                spot > discounted_strike
            )

            delta = (
                1.0
                if in_the_money
                else 0.0
            )

            theta = (
                -rate
                * discounted_strike
                if in_the_money
                else 0.0
            )

            rho = (
                time_to_expiry
                * discounted_strike
                if in_the_money
                else 0.0
            )

        else:
            in_the_money = (
                spot < discounted_strike
            )

            delta = (
                -1.0
                if in_the_money
                else 0.0
            )

            theta = (
                rate
                * discounted_strike
                if in_the_money
                else 0.0
            )

            rho = (
                -time_to_expiry
                * discounted_strike
                if in_the_money
                else 0.0
            )

        return (
            delta,
            0.0,
            0.0,
            theta,
            rho,
        )

    # ========================================================
    # CORE GREEKS
    # ========================================================

    def greeks(
        self,
        contract: OptionContract,
        *,
        spot: float,
        risk_free_rate: float,
        volatility: float,
        valuation_date: date | datetime,
    ) -> GreeksResult:
        """
        Calculate analytical Black-Scholes Greeks for a contract.

        Values are per underlying unit.
        """
        self._validate_contract(contract)

        spot = self._validate_scalar(
            "spot",
            spot,
            minimum=0.0,
            strict_minimum=True,
        )

        strike = self._validate_scalar(
            "strike",
            contract.strike,
            minimum=0.0,
            strict_minimum=True,
        )

        rate = self._validate_scalar(
            "risk_free_rate",
            risk_free_rate,
        )

        volatility = self._validate_scalar(
            "volatility",
            volatility,
            minimum=0.0,
        )

        valuation = self._normalise_date(
            valuation_date,
            "valuation_date",
        )

        expiration = self._normalise_date(
            contract.expiration,
            "expiration",
        )

        time_to_expiry = self._time_to_expiry(
            valuation,
            expiration,
        )

        # ----------------------------------------------------
        # EXACT EXPIRY
        # ----------------------------------------------------

        if time_to_expiry <= self.tolerance:
            (
                delta,
                gamma,
                vega,
                theta,
                rho,
            ) = self._expiry_greeks(
                contract.option_type,
                spot,
                strike,
            )

            result = GreeksResult(
                contract_id=contract.contract_id,
                underlying=contract.underlying,
                option_type=contract.option_type,
                strike=strike,
                expiration=expiration.isoformat(),
                valuation_date=valuation.isoformat(),
                spot=spot,
                risk_free_rate=rate,
                volatility=volatility,
                time_to_expiry=0.0,
                d1=None,
                d2=None,
                delta=delta,
                gamma=gamma,
                vega=vega,
                theta=theta,
                rho=rho,
                quantity=0.0,
                multiplier=float(contract.multiplier),
                position_delta=0.0,
                position_gamma=0.0,
                position_vega=0.0,
                position_theta=0.0,
                position_rho=0.0,
                diagnostics={
                    "method": "black_scholes_analytical_greeks",
                    "expiry_convention": True,
                    "zero_volatility_convention": False,
                    "european_only": True,
                },
            )

            self.last_result = result
            return result

        # ----------------------------------------------------
        # ZERO VOLATILITY
        # ----------------------------------------------------

        if volatility <= self.tolerance:
            (
                delta,
                gamma,
                vega,
                theta,
                rho,
            ) = self._zero_volatility_greeks(
                contract.option_type,
                spot,
                strike,
                rate,
                time_to_expiry,
            )

            result = GreeksResult(
                contract_id=contract.contract_id,
                underlying=contract.underlying,
                option_type=contract.option_type,
                strike=strike,
                expiration=expiration.isoformat(),
                valuation_date=valuation.isoformat(),
                spot=spot,
                risk_free_rate=rate,
                volatility=0.0,
                time_to_expiry=time_to_expiry,
                d1=None,
                d2=None,
                delta=delta,
                gamma=gamma,
                vega=vega,
                theta=theta,
                rho=rho,
                quantity=0.0,
                multiplier=float(contract.multiplier),
                position_delta=0.0,
                position_gamma=0.0,
                position_vega=0.0,
                position_theta=0.0,
                position_rho=0.0,
                diagnostics={
                    "method": "deterministic_zero_volatility_limit",
                    "expiry_convention": False,
                    "zero_volatility_convention": True,
                    "european_only": True,
                },
            )

            self.last_result = result
            return result

        # ----------------------------------------------------
        # STANDARD BLACK-SCHOLES
        # ----------------------------------------------------

        try:
            d1, d2 = self._d1_d2(
                spot,
                strike,
                rate,
                volatility,
                time_to_expiry,
            )

            pdf_d1 = self._normal_pdf(d1)

            cdf_d1 = self._normal_cdf(d1)
            cdf_d2 = self._normal_cdf(d2)

            sqrt_t = sqrt(
                time_to_expiry
            )

            discount_factor = exp(
                -rate * time_to_expiry
            )

            # ------------------------------------------------
            # DELTA
            # ------------------------------------------------

            if contract.option_type == "call":
                delta = cdf_d1
            else:
                delta = cdf_d1 - 1.0

            # ------------------------------------------------
            # GAMMA
            # ------------------------------------------------

            gamma = (
                pdf_d1
                / (
                    spot
                    * volatility
                    * sqrt_t
                )
            )

            # ------------------------------------------------
            # VEGA
            #
            # Per 1.00 change in volatility.
            # Later reporting layers may scale this to
            # 1 percentage-point volatility if desired.
            # ------------------------------------------------

            vega = (
                spot
                * pdf_d1
                * sqrt_t
            )

            # ------------------------------------------------
            # THETA
            #
            # Calendar-time convention:
            # dV/dt while holding T-to-expiry convention.
            # ------------------------------------------------

            common_theta = (
                -(
                    spot
                    * pdf_d1
                    * volatility
                )
                / (
                    2.0 * sqrt_t
                )
            )

            if contract.option_type == "call":
                theta = (
                    common_theta
                    - (
                        rate
                        * strike
                        * discount_factor
                        * cdf_d2
                    )
                )
            else:
                theta = (
                    common_theta
                    + (
                        rate
                        * strike
                        * discount_factor
                        * self._normal_cdf(
                            -d2
                        )
                    )
                )

            # ------------------------------------------------
            # RHO
            # ------------------------------------------------

            if contract.option_type == "call":
                rho = (
                    strike
                    * time_to_expiry
                    * discount_factor
                    * cdf_d2
                )
            else:
                rho = (
                    -strike
                    * time_to_expiry
                    * discount_factor
                    * self._normal_cdf(
                        -d2
                    )
                )

        except (
            ArithmeticError,
            OverflowError,
            ValueError,
        ) as exc:
            raise AnalyticalGreeksCalculationError(
                "Unable to calculate analytical Greeks."
            ) from exc

        values = (
            delta,
            gamma,
            vega,
            theta,
            rho,
        )

        if not all(
            isfinite(float(value))
            for value in values
        ):
            raise AnalyticalGreeksCalculationError(
                "Analytical Greek calculation produced "
                "non-finite values."
            )

        result = GreeksResult(
            contract_id=contract.contract_id,
            underlying=contract.underlying,
            option_type=contract.option_type,
            strike=strike,
            expiration=expiration.isoformat(),
            valuation_date=valuation.isoformat(),
            spot=spot,
            risk_free_rate=rate,
            volatility=volatility,
            time_to_expiry=time_to_expiry,
            d1=d1,
            d2=d2,
            delta=float(delta),
            gamma=float(gamma),
            vega=float(vega),
            theta=float(theta),
            rho=float(rho),
            quantity=0.0,
            multiplier=float(contract.multiplier),
            position_delta=0.0,
            position_gamma=0.0,
            position_vega=0.0,
            position_theta=0.0,
            position_rho=0.0,
            diagnostics={
                "method": "black_scholes_analytical_greeks",
                "expiry_convention": False,
                "zero_volatility_convention": False,
                "european_only": True,
                "vega_unit": "per_1.00_volatility_change",
                "theta_unit": "per_year",
                "rho_unit": "per_1.00_rate_change",
            },
        )

        self.last_result = result

        return result

    # ========================================================
    # POSITION GREEKS
    # ========================================================

    def greeks_for_position(
        self,
        position: OptionPosition,
        *,
        spot: float,
        risk_free_rate: float,
        volatility: float,
        valuation_date: date | datetime,
    ) -> GreeksResult:
        """
        Calculate analytical Greeks for an option position.

        Contract Greeks are scaled by:

            signed quantity × contract multiplier
        """
        if not isinstance(
            position,
            OptionPosition,
        ):
            raise AnalyticalGreeksCalculationError(
                "position must be an OptionPosition."
            )

        base = self.greeks(
            position.contract,
            spot=spot,
            risk_free_rate=risk_free_rate,
            volatility=volatility,
            valuation_date=valuation_date,
        )

        quantity = float(
            position.quantity
        )

        multiplier = float(
            position.contract.multiplier
        )

        scale = (
            quantity
            * multiplier
        )

        result = GreeksResult(
            contract_id=base.contract_id,
            underlying=base.underlying,
            option_type=base.option_type,
            strike=base.strike,
            expiration=base.expiration,
            valuation_date=base.valuation_date,
            spot=base.spot,
            risk_free_rate=base.risk_free_rate,
            volatility=base.volatility,
            time_to_expiry=base.time_to_expiry,
            d1=base.d1,
            d2=base.d2,
            delta=base.delta,
            gamma=base.gamma,
            vega=base.vega,
            theta=base.theta,
            rho=base.rho,
            quantity=quantity,
            multiplier=multiplier,
            position_delta=base.delta * scale,
            position_gamma=base.gamma * scale,
            position_vega=base.vega * scale,
            position_theta=base.theta * scale,
            position_rho=base.rho * scale,
            diagnostics={
                **base.diagnostics,
                "position_scaling": (
                    "signed_quantity_times_contract_multiplier"
                ),
                "signed_quantity": quantity,
                "contract_multiplier": multiplier,
            },
        )

        self.last_result = result

        return result

    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
        self,
        result: GreeksResult | None = None,
    ) -> dict[str, Any]:
        """
        Return the latest or supplied Greeks result.
        """
        selected = (
            result
            if result is not None
            else self.last_result
        )

        if selected is None:
            raise AnalyticalGreeksError(
                "No Greeks result is available."
            )

        return selected.to_dict()

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(self) -> dict[str, Any]:
        """
        Return component health information.
        """
        try:
            checks = {
                "configuration": (
                    isfinite(self.tolerance)
                    and self.tolerance > 0.0
                ),
                "european_greeks_supported": True,
                "american_options_explicitly_rejected": True,
                "expiry_handling_defined": True,
                "zero_volatility_handling_defined": True,
                "implied_volatility_not_included_in_r4_4": True,
                "parity_not_included_in_r4_4": True,
                "stress_not_included_in_r4_4": True,
                "portfolio_aggregation_not_included_in_r4_4": True,
            }

            healthy = all(
                checks.values()
            )

            return {
                "api_version": self.API_VERSION,
                "component": self.COMPONENT,
                "phase": self.PHASE,
                "healthy": healthy,
                "checks": checks,
                "tolerance": self.tolerance,
            }

        except Exception as exc:
            return {
                "api_version": self.API_VERSION,
                "component": self.COMPONENT,
                "phase": self.PHASE,
                "healthy": False,
                "error": str(exc),
            }

    # ========================================================
    # METADATA
    # ========================================================

    @property
    def metadata(self) -> dict[str, Any]:
        """
        Return component metadata.
        """
        return {
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "public_methods": tuple(
                self.PUBLIC_METHODS
            ),
            "analytics_only": True,
            "european_only": True,
            "valuation": False,
            "implied_volatility": False,
            "parity": False,
            "stress": False,
            "portfolio_aggregation": False,
            "governance": False,
            "execution": False,
        }


# ============================================================
# FACTORY
# ============================================================


def build_analytical_greeks_engine(
    **kwargs: Any,
) -> AnalyticalGreeksEngine:
    """
    Production factory for AnalyticalGreeksEngine.
    """
    return AnalyticalGreeksEngine(
        **kwargs
    )


# ============================================================
# SELF-TEST
# ============================================================


def _self_test() -> None:
    """
    R4.4 deterministic regression tests.
    """
    contract = OptionContract(
        underlying="SPY",
        option_type="call",
        strike=100.0,
        expiration=date(2027, 1, 1),
        multiplier=100,
        exercise_style="european",
        currency="USD",
        contract_id="SPY-C-100-20270101",
    )

    engine = AnalyticalGreeksEngine()

    # --------------------------------------------------------
    # CALL
    # --------------------------------------------------------

    result = engine.greeks(
        contract,
        spot=100.0,
        risk_free_rate=0.05,
        volatility=0.20,
        valuation_date=date(2026, 1, 1),
    )

    assert result.option_type == "call"

    assert (
        result.time_to_expiry
        > 0.0
    )

    assert (
        0.0
        < result.delta
        < 1.0
    )

    assert (
        result.gamma
        > 0.0
    )

    assert (
        result.vega
        > 0.0
    )

    # --------------------------------------------------------
    # PUT
    # --------------------------------------------------------

    put_contract = OptionContract(
        underlying="SPY",
        option_type="put",
        strike=100.0,
        expiration=date(2027, 1, 1),
        multiplier=100,
        exercise_style="european",
        currency="USD",
        contract_id="SPY-P-100-20270101",
    )

    put_result = engine.greeks(
        put_contract,
        spot=100.0,
        risk_free_rate=0.05,
        volatility=0.20,
        valuation_date=date(2026, 1, 1),
    )

    assert (
        -1.0
        < put_result.delta
        < 0.0
    )

    assert (
        put_result.gamma
        > 0.0
    )

    assert (
        put_result.vega
        > 0.0
    )

    # --------------------------------------------------------
    # DELTA PARITY
    # --------------------------------------------------------

    assert abs(
        result.delta
        - put_result.delta
        - 1.0
    ) < 1e-10

    # --------------------------------------------------------
    # GAMMA / VEGA MATCH
    # --------------------------------------------------------

    assert abs(
        result.gamma
        - put_result.gamma
    ) < 1e-10

    assert abs(
        result.vega
        - put_result.vega
    ) < 1e-10

    # --------------------------------------------------------
    # POSITION
    # --------------------------------------------------------

    position = OptionPosition(
        contract=contract,
        quantity=2,
    )

    position_result = (
        engine.greeks_for_position(
            position,
            spot=100.0,
            risk_free_rate=0.05,
            volatility=0.20,
            valuation_date=date(2026, 1, 1),
        )
    )

    expected_scale = 2.0 * 100.0

    assert abs(
        position_result.position_delta
        - result.delta * expected_scale
    ) < 1e-10

    assert abs(
        position_result.position_gamma
        - result.gamma * expected_scale
    ) < 1e-10

    # --------------------------------------------------------
    # SHORT POSITION
    # --------------------------------------------------------

    short_position = OptionPosition(
        contract=contract,
        quantity=-2,
    )

    short_result = (
        engine.greeks_for_position(
            short_position,
            spot=100.0,
            risk_free_rate=0.05,
            volatility=0.20,
            valuation_date=date(2026, 1, 1),
        )
    )

    assert abs(
        short_result.position_delta
        + position_result.position_delta
    ) < 1e-10

    assert abs(
        short_result.position_gamma
        + position_result.position_gamma
    ) < 1e-10

    assert abs(
        short_result.position_vega
        + position_result.position_vega
    ) < 1e-10

    # --------------------------------------------------------
    # EXPIRY
    # --------------------------------------------------------

    expiry_result = engine.greeks(
        contract,
        spot=110.0,
        risk_free_rate=0.05,
        volatility=0.20,
        valuation_date=date(2027, 1, 1),
    )

    assert (
        expiry_result.delta
        == 1.0
    )

    assert (
        expiry_result.gamma
        == 0.0
    )

    assert (
        expiry_result.vega
        == 0.0
    )

    # --------------------------------------------------------
    # ZERO VOLATILITY
    # --------------------------------------------------------

    zero_vol_result = engine.greeks(
        contract,
        spot=110.0,
        risk_free_rate=0.0,
        volatility=0.0,
        valuation_date=date(2026, 1, 1),
    )

    assert (
        zero_vol_result.delta
        == 1.0
    )

    assert (
        zero_vol_result.gamma
        == 0.0
    )

    # --------------------------------------------------------
    # AMERICAN REJECTION
    # --------------------------------------------------------

    american_contract = OptionContract(
        underlying="SPY",
        option_type="call",
        strike=100.0,
        expiration=date(2027, 1, 1),
        multiplier=100,
        exercise_style="american",
        currency="USD",
        contract_id="SPY-C-100-AMERICAN",
    )

    rejected = False

    try:
        engine.greeks(
            american_contract,
            spot=100.0,
            risk_free_rate=0.05,
            volatility=0.20,
            valuation_date=date(2026, 1, 1),
        )
    except AnalyticalGreeksCalculationError:
        rejected = True

    assert rejected is True

    # --------------------------------------------------------
    # SERIALIZATION
    # --------------------------------------------------------

    payload = result.to_dict()

    assert (
        payload["underlying"]
        == "SPY"
    )

    assert (
        payload["option_type"]
        == "call"
    )

    assert (
        "delta"
        in payload
    )

    assert (
        "gamma"
        in payload
    )

    assert (
        "vega"
        in payload
    )

    assert (
        "theta"
        in payload
    )

    assert (
        "rho"
        in payload
    )

    # --------------------------------------------------------
    # HEALTH
    # --------------------------------------------------------

    health = engine.health_check()

    assert (
        health["healthy"]
        is True
    )

    # --------------------------------------------------------
    # METADATA
    # --------------------------------------------------------

    assert (
        engine.API_VERSION
        == "1.0.0"
    )

    assert (
        engine.PHASE
        == "R4.4"
    )

    assert tuple(
        engine.PUBLIC_METHODS
    ) == (
        "greeks",
        "greeks_for_position",
        "summary",
        "health_check",
    )

    print(
        "AnalyticalGreeksEngine R4.4 self-test: PASS"
    )


# ============================================================
# MAIN
# ============================================================


if __name__ == "__main__":
    _self_test()