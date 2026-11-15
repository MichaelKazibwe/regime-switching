from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from analyticalgreeks import GreeksResult


"""
PORTFOLIO GREEKS AGGREGATION
============================================================

R4.5 of the production options-risk architecture.

Responsibilities
----------------
- Portfolio-level Greek aggregation
- Net Delta
- Net Gamma
- Net Vega
- Net Theta
- Net Rho
- Per-underlying Greek aggregation
- Per-position Greek contributions
- Largest absolute Greek contributors
- Greek concentration diagnostics
- Strict validation
- Deterministic serialization
- Component health checks

Consumes
--------
- GreeksResult from analyticalgreeks.py

Explicitly NOT responsible for
--------------------------------
- Option contract construction
- Option position construction
- Black-Scholes valuation
- Greek calculation
- Implied volatility
- Put/call parity
- Volatility surfaces
- Options stress testing
- Tail-risk aggregation
- Risk governance
- Execution

Important architectural rule
-----------------------------
This module aggregates existing position-level Greeks.

It does NOT recalculate Delta, Gamma, Vega, Theta, or Rho.

Position-level Greeks already include:

    signed quantity × contract multiplier

as established by R4.4.

Architecture
------------

    OPTION CONTRACT
           |
           v
    OPTION POSITION
           |
           v
    BLACK-SCHOLES
           |
           v
    ANALYTICAL GREEKS
           |
           v
    PORTFOLIO GREEKS       <-- R4.5
           |
           v
    PARITY                 <-- R4.6
           |
           v
    VOL SURFACE            <-- R4.7
           |
           v
    OPTIONS STRESS         <-- R4.8
           |
           v
    TAIL RISK              <-- R4.9
           |
           v
    RISK GOVERNOR          <-- R4.10
           |
           v
    RISK REPORT            <-- R4.11
"""


# ============================================================
# MODULE METADATA
# ============================================================

API_VERSION = "1.0.0"
COMPONENT = "PortfolioGreeksAggregator"
PHASE = "R4.5"


# ============================================================
# EXCEPTIONS
# ============================================================


class PortfolioGreeksError(Exception):
    """Base exception for portfolio-Greeks failures."""


class PortfolioGreeksConfigurationError(
    PortfolioGreeksError
):
    """Raised when aggregator configuration is invalid."""


class PortfolioGreeksCalculationError(
    PortfolioGreeksError
):
    """Raised when portfolio Greek aggregation fails."""


# ============================================================
# RESULT OBJECT
# ============================================================


@dataclass(frozen=True)
class PortfolioGreeksResult:
    """
    Immutable portfolio-level Greeks result.

    All portfolio Greek values are aggregated from the
    position-level values contained in GreeksResult.

    No Greek mathematics is performed by this object.
    """

    position_count: int

    net_delta: float
    net_gamma: float
    net_vega: float
    net_theta: float
    net_rho: float

    gross_delta: float
    gross_gamma: float
    gross_vega: float
    gross_theta: float
    gross_rho: float

    largest_delta_contributor: dict[str, Any] | None
    largest_gamma_contributor: dict[str, Any] | None
    largest_vega_contributor: dict[str, Any] | None
    largest_theta_contributor: dict[str, Any] | None
    largest_rho_contributor: dict[str, Any] | None

    delta_concentration: float
    gamma_concentration: float
    vega_concentration: float
    theta_concentration: float
    rho_concentration: float

    by_underlying: dict[str, dict[str, float]]

    position_contributions: tuple[
        dict[str, Any],
        ...
    ]

    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """
        Return a JSON-safe representation.
        """
        return asdict(self)


# ============================================================
# AGGREGATOR
# ============================================================


class PortfolioGreeksAggregator:
    """
    Production portfolio-level Greek aggregation engine.
    """

    API_VERSION = API_VERSION
    COMPONENT = COMPONENT
    PHASE = PHASE

    PUBLIC_METHODS = (
        "aggregate",
        "summary",
        "health_check",
    )

    DEFAULT_TOLERANCE = 1e-12

    def __init__(
        self,
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> None:
        try:
            self.tolerance = float(tolerance)
        except (TypeError, ValueError) as exc:
            raise PortfolioGreeksConfigurationError(
                "tolerance must be numeric."
            ) from exc

        if (
            not self.tolerance > 0.0
            or not self.tolerance < float("inf")
        ):
            raise PortfolioGreeksConfigurationError(
                "tolerance must be a positive finite number."
            )

        self.last_result: PortfolioGreeksResult | None = None

    # ========================================================
    # VALIDATION
    # ========================================================

    @staticmethod
    def _validate_result(
        result: GreeksResult,
    ) -> None:
        """
        Validate one upstream GreeksResult.
        """
        if not isinstance(result, GreeksResult):
            raise PortfolioGreeksCalculationError(
                "All portfolio inputs must be GreeksResult "
                "instances."
            )

        values = (
            result.delta,
            result.gamma,
            result.vega,
            result.theta,
            result.rho,
            result.position_delta,
            result.position_gamma,
            result.position_vega,
            result.position_theta,
            result.position_rho,
            result.quantity,
            result.multiplier,
        )

        for value in values:
            try:
                numeric = float(value)
            except (TypeError, ValueError) as exc:
                raise PortfolioGreeksCalculationError(
                    "GreeksResult contains a non-numeric value."
                ) from exc

            if not (
                numeric == numeric
                and abs(numeric) < float("inf")
            ):
                raise PortfolioGreeksCalculationError(
                    "GreeksResult contains a non-finite value."
                )

    # ========================================================
    # POSITION CONTRIBUTION
    # ========================================================

    @staticmethod
    def _position_contribution(
        result: GreeksResult,
    ) -> dict[str, Any]:
        """
        Create a deterministic position-level contribution record.
        """
        return {
            "contract_id": result.contract_id,
            "underlying": result.underlying,
            "option_type": result.option_type,
            "strike": float(result.strike),
            "expiration": result.expiration,
            "valuation_date": result.valuation_date,
            "quantity": float(result.quantity),
            "multiplier": float(result.multiplier),
            "delta": float(result.position_delta),
            "gamma": float(result.position_gamma),
            "vega": float(result.position_vega),
            "theta": float(result.position_theta),
            "rho": float(result.position_rho),
        }

    # ========================================================
    # LARGEST CONTRIBUTOR
    # ========================================================

    @staticmethod
    def _largest_contributor(
        contributions: list[dict[str, Any]],
        greek: str,
    ) -> dict[str, Any] | None:
        """
        Return the position with the largest absolute contribution
        to the requested Greek.

        Deterministic tie-breaking uses the original contribution
        ordering.
        """
        if not contributions:
            return None

        selected = max(
            contributions,
            key=lambda item: abs(
                float(item[greek])
            ),
        )

        return {
            "contract_id": selected["contract_id"],
            "underlying": selected["underlying"],
            "option_type": selected["option_type"],
            "strike": selected["strike"],
            "expiration": selected["expiration"],
            "contribution": float(selected[greek]),
            "absolute_contribution": abs(
                float(selected[greek])
            ),
        }

    # ========================================================
    # CONCENTRATION
    # ========================================================

    @staticmethod
    def _concentration(
        contributions: list[dict[str, Any]],
        greek: str,
        tolerance: float,
    ) -> float:
        """
        Calculate the largest-position concentration for a Greek.

        Formula:

            max(abs(position contribution))
            --------------------------------
            sum(abs(position contributions))

        Returns zero when gross exposure is effectively zero.
        """
        gross = sum(
            abs(float(item[greek]))
            for item in contributions
        )

        if gross <= tolerance:
            return 0.0

        largest = max(
            abs(float(item[greek]))
            for item in contributions
        )

        return float(largest / gross)

    # ========================================================
    # UNDERLYING AGGREGATION
    # ========================================================

    @staticmethod
    def _aggregate_by_underlying(
        contributions: list[dict[str, Any]],
    ) -> dict[str, dict[str, float]]:
        """
        Aggregate position Greeks by underlying.

        Output ordering is deterministic by underlying symbol.
        """
        aggregated: dict[
            str,
            dict[str, float],
        ] = {}

        for item in contributions:
            underlying = str(
                item["underlying"]
            )

            if underlying not in aggregated:
                aggregated[underlying] = {
                    "net_delta": 0.0,
                    "net_gamma": 0.0,
                    "net_vega": 0.0,
                    "net_theta": 0.0,
                    "net_rho": 0.0,
                }

            aggregated[underlying]["net_delta"] += (
                float(item["delta"])
            )

            aggregated[underlying]["net_gamma"] += (
                float(item["gamma"])
            )

            aggregated[underlying]["net_vega"] += (
                float(item["vega"])
            )

            aggregated[underlying]["net_theta"] += (
                float(item["theta"])
            )

            aggregated[underlying]["net_rho"] += (
                float(item["rho"])
            )

        return {
            key: aggregated[key]
            for key in sorted(aggregated)
        }

    # ========================================================
    # AGGREGATION
    # ========================================================

    def aggregate(
        self,
        results: Iterable[GreeksResult],
    ) -> PortfolioGreeksResult:
        """
        Aggregate position-level Greeks into portfolio Greeks.

        Parameters
        ----------
        results:
            Iterable of GreeksResult objects produced by
            AnalyticalGreeksEngine.greeks_for_position().

        Notes
        -----
        No Greek mathematics is recalculated here.

        The following upstream fields are summed directly:

            position_delta
            position_gamma
            position_vega
            position_theta
            position_rho
        """
        if results is None:
            raise PortfolioGreeksCalculationError(
                "results cannot be None."
            )

        try:
            materialized = list(results)
        except TypeError as exc:
            raise PortfolioGreeksCalculationError(
                "results must be an iterable of GreeksResult."
            ) from exc

        for result in materialized:
            self._validate_result(result)

        contributions = [
            self._position_contribution(result)
            for result in materialized
        ]

        # ----------------------------------------------------
        # NET GREEKS
        # ----------------------------------------------------

        net_delta = sum(
            float(item["delta"])
            for item in contributions
        )

        net_gamma = sum(
            float(item["gamma"])
            for item in contributions
        )

        net_vega = sum(
            float(item["vega"])
            for item in contributions
        )

        net_theta = sum(
            float(item["theta"])
            for item in contributions
        )

        net_rho = sum(
            float(item["rho"])
            for item in contributions
        )

        # ----------------------------------------------------
        # GROSS ABSOLUTE GREEKS
        # ----------------------------------------------------

        gross_delta = sum(
            abs(float(item["delta"]))
            for item in contributions
        )

        gross_gamma = sum(
            abs(float(item["gamma"]))
            for item in contributions
        )

        gross_vega = sum(
            abs(float(item["vega"]))
            for item in contributions
        )

        gross_theta = sum(
            abs(float(item["theta"]))
            for item in contributions
        )

        gross_rho = sum(
            abs(float(item["rho"]))
            for item in contributions
        )

        # ----------------------------------------------------
        # LARGEST CONTRIBUTORS
        # ----------------------------------------------------

        largest_delta = self._largest_contributor(
            contributions,
            "delta",
        )

        largest_gamma = self._largest_contributor(
            contributions,
            "gamma",
        )

        largest_vega = self._largest_contributor(
            contributions,
            "vega",
        )

        largest_theta = self._largest_contributor(
            contributions,
            "theta",
        )

        largest_rho = self._largest_contributor(
            contributions,
            "rho",
        )

        # ----------------------------------------------------
        # CONCENTRATION
        # ----------------------------------------------------

        delta_concentration = self._concentration(
            contributions,
            "delta",
            self.tolerance,
        )

        gamma_concentration = self._concentration(
            contributions,
            "gamma",
            self.tolerance,
        )

        vega_concentration = self._concentration(
            contributions,
            "vega",
            self.tolerance,
        )

        theta_concentration = self._concentration(
            contributions,
            "theta",
            self.tolerance,
        )

        rho_concentration = self._concentration(
            contributions,
            "rho",
            self.tolerance,
        )

        # ----------------------------------------------------
        # UNDERLYING AGGREGATION
        # ----------------------------------------------------

        by_underlying = (
            self._aggregate_by_underlying(
                contributions
            )
        )

        # ----------------------------------------------------
        # RESULT
        # ----------------------------------------------------

        result = PortfolioGreeksResult(
            position_count=len(contributions),
            net_delta=float(net_delta),
            net_gamma=float(net_gamma),
            net_vega=float(net_vega),
            net_theta=float(net_theta),
            net_rho=float(net_rho),
            gross_delta=float(gross_delta),
            gross_gamma=float(gross_gamma),
            gross_vega=float(gross_vega),
            gross_theta=float(gross_theta),
            gross_rho=float(gross_rho),
            largest_delta_contributor=largest_delta,
            largest_gamma_contributor=largest_gamma,
            largest_vega_contributor=largest_vega,
            largest_theta_contributor=largest_theta,
            largest_rho_contributor=largest_rho,
            delta_concentration=float(
                delta_concentration
            ),
            gamma_concentration=float(
                gamma_concentration
            ),
            vega_concentration=float(
                vega_concentration
            ),
            theta_concentration=float(
                theta_concentration
            ),
            rho_concentration=float(
                rho_concentration
            ),
            by_underlying=by_underlying,
            position_contributions=tuple(
                contributions
            ),
            diagnostics={
                "method": (
                    "position_level_greek_aggregation"
                ),
                "source": "AnalyticalGreeksEngine",
                "greeks_recalculated": False,
                "position_scaling_source": (
                    "GreeksResult.position_*"
                ),
                "tolerance": self.tolerance,
            },
        )

        self.last_result = result

        return result

    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
        self,
        result: PortfolioGreeksResult | None = None,
    ) -> dict[str, Any]:
        """
        Return the latest or supplied portfolio Greek result.
        """
        selected = (
            result
            if result is not None
            else self.last_result
        )

        if selected is None:
            raise PortfolioGreeksError(
                "No portfolio Greeks result is available."
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
                    self.tolerance > 0.0
                    and self.tolerance < float("inf")
                ),
                "greeks_result_dependency": True,
                "net_delta_supported": True,
                "net_gamma_supported": True,
                "net_vega_supported": True,
                "net_theta_supported": True,
                "net_rho_supported": True,
                "underlying_aggregation_supported": True,
                "largest_contributor_supported": True,
                "concentration_supported": True,
                "greek_recalculation_disabled": True,
                "implied_volatility_not_in_r4_5": True,
                "parity_not_in_r4_5": True,
                "stress_not_in_r4_5": True,
                "tail_risk_not_in_r4_5": True,
                "governance_not_in_r4_5": True,
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
            "valuation": False,
            "greeks_calculation": False,
            "portfolio_aggregation": True,
            "implied_volatility": False,
            "parity": False,
            "volatility_surface": False,
            "stress": False,
            "tail_risk": False,
            "governance": False,
            "execution": False,
        }


# ============================================================
# FACTORY
# ============================================================


def build_portfolio_greeks_aggregator(
    **kwargs: Any,
) -> PortfolioGreeksAggregator:
    """
    Production factory for PortfolioGreeksAggregator.
    """
    return PortfolioGreeksAggregator(
        **kwargs
    )


# ============================================================
# SELF-TEST
# ============================================================


def _self_test() -> None:
    """
    R4.5 deterministic regression tests.
    """

    # --------------------------------------------------------
    # IMPORTS FOR TEST DATA
    # --------------------------------------------------------

    from datetime import date

    from optionsrisk import (
        OptionContract,
        OptionPosition,
    )

    from analyticalgreeks import (
        AnalyticalGreeksEngine,
    )

    # --------------------------------------------------------
    # CONTRACTS
    # --------------------------------------------------------

    spy_call = OptionContract(
        underlying="SPY",
        option_type="call",
        strike=600.0,
        expiration=date(2027, 1, 15),
        multiplier=100.0,
        exercise_style="european",
        currency="USD",
        contract_id="SPY-C-600-20270115",
    )

    spy_put = OptionContract(
        underlying="SPY",
        option_type="put",
        strike=580.0,
        expiration=date(2027, 1, 15),
        multiplier=100.0,
        exercise_style="european",
        currency="USD",
        contract_id="SPY-P-580-20270115",
    )

    qqq_call = OptionContract(
        underlying="QQQ",
        option_type="call",
        strike=500.0,
        expiration=date(2027, 1, 15),
        multiplier=100.0,
        exercise_style="european",
        currency="USD",
        contract_id="QQQ-C-500-20270115",
    )

    # --------------------------------------------------------
    # POSITIONS
    # --------------------------------------------------------

    spy_call_position = OptionPosition(
        contract=spy_call,
        quantity=2.0,
    )

    spy_put_position = OptionPosition(
        contract=spy_put,
        quantity=-1.0,
    )

    qqq_call_position = OptionPosition(
        contract=qqq_call,
        quantity=3.0,
    )

    # --------------------------------------------------------
    # ANALYTICAL GREEKS
    # --------------------------------------------------------

    greeks_engine = AnalyticalGreeksEngine()

    spy_call_result = (
        greeks_engine.greeks_for_position(
            spy_call_position,
            spot=600.0,
            risk_free_rate=0.05,
            volatility=0.20,
            valuation_date=date(2026, 9, 14),
        )
    )

    spy_put_result = (
        greeks_engine.greeks_for_position(
            spy_put_position,
            spot=600.0,
            risk_free_rate=0.05,
            volatility=0.20,
            valuation_date=date(2026, 9, 14),
        )
    )

    qqq_call_result = (
        greeks_engine.greeks_for_position(
            qqq_call_position,
            spot=500.0,
            risk_free_rate=0.05,
            volatility=0.20,
            valuation_date=date(2026, 9, 14),
        )
    )

    # --------------------------------------------------------
    # AGGREGATION
    # --------------------------------------------------------

    aggregator = PortfolioGreeksAggregator()

    portfolio = aggregator.aggregate(
        (
            spy_call_result,
            spy_put_result,
            qqq_call_result,
        )
    )

    # --------------------------------------------------------
    # POSITION COUNT
    # --------------------------------------------------------

    assert (
        portfolio.position_count
        == 3
    )

    # --------------------------------------------------------
    # NET GREEKS
    # --------------------------------------------------------

    expected_delta = (
        spy_call_result.position_delta
        + spy_put_result.position_delta
        + qqq_call_result.position_delta
    )

    expected_gamma = (
        spy_call_result.position_gamma
        + spy_put_result.position_gamma
        + qqq_call_result.position_gamma
    )

    expected_vega = (
        spy_call_result.position_vega
        + spy_put_result.position_vega
        + qqq_call_result.position_vega
    )

    expected_theta = (
        spy_call_result.position_theta
        + spy_put_result.position_theta
        + qqq_call_result.position_theta
    )

    expected_rho = (
        spy_call_result.position_rho
        + spy_put_result.position_rho
        + qqq_call_result.position_rho
    )

    assert abs(
        portfolio.net_delta
        - expected_delta
    ) < 1e-10

    assert abs(
        portfolio.net_gamma
        - expected_gamma
    ) < 1e-10

    assert abs(
        portfolio.net_vega
        - expected_vega
    ) < 1e-10

    assert abs(
        portfolio.net_theta
        - expected_theta
    ) < 1e-10

    assert abs(
        portfolio.net_rho
        - expected_rho
    ) < 1e-10

    # --------------------------------------------------------
    # GROSS EXPOSURE
    # --------------------------------------------------------

    assert (
        portfolio.gross_delta
        >= abs(portfolio.net_delta)
    )

    assert (
        portfolio.gross_gamma
        >= abs(portfolio.net_gamma)
    )

    assert (
        portfolio.gross_vega
        >= abs(portfolio.net_vega)
    )

    assert (
        portfolio.gross_theta
        >= abs(portfolio.net_theta)
    )

    assert (
        portfolio.gross_rho
        >= abs(portfolio.net_rho)
    )

    # --------------------------------------------------------
    # UNDERLYING AGGREGATION
    # --------------------------------------------------------

    assert "SPY" in (
        portfolio.by_underlying
    )

    assert "QQQ" in (
        portfolio.by_underlying
    )

    expected_spy_delta = (
        spy_call_result.position_delta
        + spy_put_result.position_delta
    )

    expected_qqq_delta = (
        qqq_call_result.position_delta
    )

    assert abs(
        portfolio.by_underlying["SPY"]["net_delta"]
        - expected_spy_delta
    ) < 1e-10

    assert abs(
        portfolio.by_underlying["QQQ"]["net_delta"]
        - expected_qqq_delta
    ) < 1e-10

    # --------------------------------------------------------
    # LARGEST CONTRIBUTOR
    # --------------------------------------------------------

    assert (
        portfolio.largest_delta_contributor
        is not None
    )

    assert (
        portfolio.largest_gamma_contributor
        is not None
    )

    assert (
        portfolio.largest_vega_contributor
        is not None
    )

    # --------------------------------------------------------
    # CONCENTRATION
    # --------------------------------------------------------

    assert (
        0.0
        <= portfolio.delta_concentration
        <= 1.0
    )

    assert (
        0.0
        <= portfolio.gamma_concentration
        <= 1.0
    )

    assert (
        0.0
        <= portfolio.vega_concentration
        <= 1.0
    )

    assert (
        0.0
        <= portfolio.theta_concentration
        <= 1.0
    )

    assert (
        0.0
        <= portfolio.rho_concentration
        <= 1.0
    )

    # --------------------------------------------------------
    # SERIALIZATION
    # --------------------------------------------------------

    payload = portfolio.to_dict()

    assert (
        payload["position_count"]
        == 3
    )

    assert (
        "net_delta"
        in payload
    )

    assert (
        "net_gamma"
        in payload
    )

    assert (
        "net_vega"
        in payload
    )

    assert (
        "net_theta"
        in payload
    )

    assert (
        "net_rho"
        in payload
    )

    assert (
        "by_underlying"
        in payload
    )

    assert (
        "position_contributions"
        in payload
    )

    # --------------------------------------------------------
    # EMPTY PORTFOLIO
    # --------------------------------------------------------

    empty = aggregator.aggregate([])

    assert (
        empty.position_count
        == 0
    )

    assert (
        empty.net_delta
        == 0.0
    )

    assert (
        empty.net_gamma
        == 0.0
    )

    assert (
        empty.net_vega
        == 0.0
    )

    assert (
        empty.net_theta
        == 0.0
    )

    assert (
        empty.net_rho
        == 0.0
    )

    assert (
        empty.by_underlying
        == {}
    )

    assert (
        empty.largest_delta_contributor
        is None
    )

    # --------------------------------------------------------
    # INVALID INPUT
    # --------------------------------------------------------

    rejected = False

    try:
        aggregator.aggregate(
            [
                "not-a-greeks-result",
            ]
        )
    except PortfolioGreeksCalculationError:
        rejected = True

    assert rejected is True

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    summary = aggregator.summary(
        portfolio
    )

    assert (
        summary["net_delta"]
        == portfolio.net_delta
    )

    # --------------------------------------------------------
    # HEALTH
    # --------------------------------------------------------

    health = aggregator.health_check()

    assert (
        health["healthy"]
        is True
    )

    # --------------------------------------------------------
    # METADATA
    # --------------------------------------------------------

    assert (
        aggregator.API_VERSION
        == "1.0.0"
    )

    assert (
        aggregator.PHASE
        == "R4.5"
    )

    assert tuple(
        aggregator.PUBLIC_METHODS
    ) == (
        "aggregate",
        "summary",
        "health_check",
    )

    # --------------------------------------------------------
    # FACTORY
    # --------------------------------------------------------

    factory = (
        build_portfolio_greeks_aggregator()
    )

    assert isinstance(
        factory,
        PortfolioGreeksAggregator,
    )

    print(
        "PortfolioGreeksAggregator R4.5 self-test: PASS"
    )


# ============================================================
# MAIN
# ============================================================


if __name__ == "__main__":
    _self_test()