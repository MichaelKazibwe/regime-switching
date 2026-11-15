"""
================================================================
PORTFOLIO RISK GOVERNOR

Institutional Portfolio-Level Risk Governance Engine.

Purpose
-------
Evaluates an already-approved candidate portfolio against a
configured portfolio risk envelope.

The Risk Governor is NOT an optimizer.

It does not:
    • generate portfolio weights
    • redistribute portfolio weights
    • replace PortfolioConstraints
    • replace covariance estimation
    • replace volatility targeting
    • replace ATR position sizing
    • calculate scenarios
    • calculate drawdown / ruin
    • calculate tail-risk analytics
    • generate trades

It only governs the final candidate portfolio.

Governance actions
------------------
PASS
    Candidate portfolio is within the configured risk envelope.

REDUCE
    A scalable portfolio-level risk limit is breached.
    The governor reduces total exposure by a scalar <= 1.

REJECT
    The candidate violates a non-scalable risk rule or contains
    invalid risk inputs.

R3C / R3E.9 scope
-----------------
    1. Annualized portfolio volatility ceiling
    2. Gross leverage ceiling
    3. Maximum individual portfolio concentration
    4. Maximum individual risk contribution
    5. Aggregate tail-loss ceiling from R3E.7

R3E.9 integration rule
----------------------
The governor consumes the already-aggregated R3E.7 tail-risk result.
It does not recalculate VaR, CVaR, stress scenarios, factor stress, or
volatility/correlation stress. Aggregate tail loss is treated as a
scalar-exposure risk measure: when all risky weights are multiplied by k,
the supplied P&L loss scales by k.

Risk hierarchy
--------------
    Optimization
        ↓
    Constraints
        ↓
    Volatility Targeting
        ↓
    ATR Position Sizing
        ↓
    Risk Governor
        ↓
    Final Portfolio

Important
---------
The governor can only reduce risk.

It can never increase optimizer-approved exposure.

================================================================
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

import numpy as np

from basecomponent import BaseObject


# ================================================================
# GOVERNOR ACTIONS
# ================================================================


class RiskGovernorAction(str, Enum):
    """
    Actions returned by the portfolio risk governor.
    """

    PASS = "PASS"
    REDUCE = "REDUCE"
    REJECT = "REJECT"


# ================================================================
# GOVERNOR RESULT
# ================================================================


@dataclass(frozen=True)
class RiskGovernorResult:
    """
    Immutable result produced by the Risk Governor.

    Parameters
    ----------
    action:
        PASS, REDUCE, or REJECT.

    approved:
        True only when the resulting portfolio is approved.

    scale:
        Scalar exposure multiplier applied by the governor.

    original_weights:
        Candidate weights supplied to the governor.

    approved_weights:
        Resulting governed weights.

    cash:
        Cash created by scalar risk reduction.

    annualized_volatility:
        Annualized volatility of the candidate portfolio.

    governed_annualized_volatility:
        Annualized volatility after scalar governance.

    gross_leverage:
        Gross leverage of the candidate portfolio.

    governed_gross_leverage:
        Gross leverage after scalar governance.

    max_position_weight:
        Largest absolute individual portfolio weight.

    max_risk_contribution_pct:
        Largest absolute individual risk contribution.

    breaches:
        Machine-readable breach identifiers.

    reasons:
        Human-readable explanations.

    metrics:
        Complete diagnostic metric payload.
    """

    action: str
    approved: bool

    scale: float

    original_weights: tuple[float, ...]
    approved_weights: tuple[float, ...]

    cash: float

    annualized_volatility: float
    governed_annualized_volatility: float

    gross_leverage: float
    governed_gross_leverage: float

    max_position_weight: float
    max_risk_contribution_pct: float

    breaches: tuple[str, ...]
    reasons: tuple[str, ...]

    metrics: Mapping[str, Any]

    # R3E.9 tail-governance diagnostics. These fields are optional so the
    # existing R3C result contract remains backward compatible.
    tail_risk_available: bool = False
    aggregate_tail_loss: float | None = None
    aggregate_tail_loss_pct: float | None = None
    governed_aggregate_tail_loss_pct: float | None = None
    max_aggregate_tail_loss_pct: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the immutable result into a serializable mapping.
        """

        return asdict(self)


# ================================================================
# RISK GOVERNOR
# ================================================================


class PortfolioRiskGovernor(BaseObject):
    """
    Portfolio-level institutional risk governor.

    The governor consumes an already-approved candidate portfolio
    and evaluates it against explicit risk limits.

    It is deliberately downstream of portfolio construction.

    No optimization occurs here.
    """

    API_VERSION = "1.1.0"

    PUBLIC_METHODS = (
        "evaluate",
        "govern",
        "summary",
        "metadata",
        "health_check",
        "validate",
        "to_dict",
        "save_json",
    )

    # ============================================================
    # CONSTRUCTOR
    # ============================================================

    def __init__(
        self,
        max_annual_volatility: float,
        max_leverage: float,
        max_position_weight: float,
        max_risk_contribution_pct: float,
        tolerance: float = 1e-10,
        periods_per_year: int = 252,
        max_aggregate_tail_loss_pct: float | None = None,
    ) -> None:
        """
        Parameters
        ----------
        max_annual_volatility:
            Maximum permitted annualized portfolio volatility.

            Example:
                0.20 = 20% annualized volatility.

        max_leverage:
            Maximum permitted gross leverage.

            Example:
                1.00 = 100% gross exposure.

        max_position_weight:
            Maximum permitted absolute individual portfolio weight.

            Example:
                0.25 = 25%.

        max_risk_contribution_pct:
            Maximum permitted absolute individual risk contribution.

            Example:
                0.35 = 35%.

        tolerance:
            Numerical tolerance used for risk-limit comparisons.

        periods_per_year:
            Annualization factor.

            The production risk contract currently uses:
                252 trading periods/year.
        """

        super().__init__()

        self.max_annual_volatility = self._validate_limit(
            max_annual_volatility,
            "max_annual_volatility",
            strictly_positive=True,
        )

        self.max_leverage = self._validate_limit(
            max_leverage,
            "max_leverage",
            strictly_positive=False,
        )

        self.max_position_weight = self._validate_limit(
            max_position_weight,
            "max_position_weight",
            strictly_positive=True,
        )

        self.max_risk_contribution_pct = self._validate_limit(
            max_risk_contribution_pct,
            "max_risk_contribution_pct",
            strictly_positive=True,
        )

        self.tolerance = self._validate_limit(
            tolerance,
            "tolerance",
            strictly_positive=False,
        )

        if not isinstance(
            periods_per_year,
            (int, np.integer),
        ):
            raise TypeError(
                "periods_per_year must be an integer."
            )

        if periods_per_year <= 0:
            raise ValueError(
                "periods_per_year must be positive."
            )

        self.periods_per_year = int(
            periods_per_year
        )

        if max_aggregate_tail_loss_pct is None:
            self.max_aggregate_tail_loss_pct = None
        else:
            self.max_aggregate_tail_loss_pct = self._validate_limit(
                max_aggregate_tail_loss_pct,
                "max_aggregate_tail_loss_pct",
                strictly_positive=True,
            )

        self.last_result: RiskGovernorResult | None = None

        self._summary = {
            "max_annual_volatility":
                self.max_annual_volatility,
            "max_leverage":
                self.max_leverage,
            "max_position_weight":
                self.max_position_weight,
            "max_risk_contribution_pct":
                self.max_risk_contribution_pct,
            "max_aggregate_tail_loss_pct":
                self.max_aggregate_tail_loss_pct,
            "periods_per_year":
                self.periods_per_year,
        }

    # ============================================================
    # VALIDATE LIMIT
    # ============================================================

    @staticmethod
    def _validate_limit(
        value: float,
        name: str,
        strictly_positive: bool,
    ) -> float:
        """
        Validate a scalar risk-policy parameter.
        """

        try:
            value = float(value)
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise TypeError(
                f"{name} must be numeric."
            ) from exc

        if not np.isfinite(value):
            raise ValueError(
                f"{name} must be finite."
            )

        if strictly_positive:
            if value <= 0.0:
                raise ValueError(
                    f"{name} must be positive."
                )
        else:
            if value < 0.0:
                raise ValueError(
                    f"{name} cannot be negative."
                )

        return value

    # ============================================================
    # INPUT VALIDATION
    # ============================================================

    @staticmethod
    def _prepare_weights(
        weights: Sequence[float] | np.ndarray,
    ) -> np.ndarray:
        """
        Validate and copy portfolio weights.
        """

        array = np.asarray(
            weights,
            dtype=float,
        )

        if array.ndim != 1:
            raise ValueError(
                "weights must be a one-dimensional array."
            )

        if array.size == 0:
            raise ValueError(
                "weights cannot be empty."
            )

        if not np.all(
            np.isfinite(array)
        ):
            raise ValueError(
                "weights must contain only finite values."
            )

        return array.copy()

    @staticmethod
    def _prepare_covariance(
        covariance: Sequence[Sequence[float]] | np.ndarray,
        dimension: int,
    ) -> np.ndarray:
        """
        Validate and copy the covariance matrix.

        The production contract supplies covariance in native
        frequency. The current portfolio risk contract is daily,
        therefore annualized volatility is calculated as:

            sqrt(w' Sigma w * periods_per_year)
        """

        matrix = np.asarray(
            covariance,
            dtype=float,
        )

        if matrix.ndim != 2:
            raise ValueError(
                "covariance must be a two-dimensional matrix."
            )

        if matrix.shape != (
            dimension,
            dimension,
        ):
            raise ValueError(
                "covariance dimensions must match weights."
            )

        if not np.all(
            np.isfinite(matrix)
        ):
            raise ValueError(
                "covariance must contain only finite values."
            )

        if not np.allclose(
            matrix,
            matrix.T,
            atol=1e-10,
            rtol=1e-10,
        ):
            raise ValueError(
                "covariance matrix must be symmetric."
            )

        return matrix.copy()

    # ============================================================
    # RISK CONTRIBUTIONS
    # ============================================================

    @staticmethod
    def _calculate_risk_contributions(
        weights: np.ndarray,
        covariance: np.ndarray,
        volatility: float,
    ) -> np.ndarray:
        """
        Calculate percentage risk contributions.

        Component risk:

            RC_i = w_i * (Sigma w)_i / portfolio_vol

        Percentage contribution:

            RC_i_pct = RC_i / portfolio_vol

        Absolute percentage contributions are used for the
        concentration test so offsetting positive/negative
        contributions cannot conceal a large individual risk.
        """

        if volatility <= 0.0:
            return np.zeros_like(
                weights,
                dtype=float,
            )

        marginal_risk = (
            covariance @ weights
        )

        component_risk = (
            weights * marginal_risk
        )

        risk_contribution_pct = (
            component_risk
            /
            (volatility ** 2)
        )

        return risk_contribution_pct

    # ============================================================
    # RISK METRICS
    # ============================================================

    def _calculate_metrics(
        self,
        weights: np.ndarray,
        covariance: np.ndarray,
    ) -> dict[str, Any]:
        """
        Calculate all portfolio-level governor metrics.
        """

        variance = float(
            weights
            @ covariance
            @ weights
        )

        if variance < -self.tolerance:
            raise ValueError(
                "Portfolio variance cannot be materially negative."
            )

        variance = max(
            variance,
            0.0,
        )

        native_volatility = float(
            np.sqrt(variance)
        )

        annualized_volatility = float(
            native_volatility
            *
            np.sqrt(
                self.periods_per_year
            )
        )

        gross_leverage = float(
            np.sum(
                np.abs(weights)
            )
        )

        position_weights = np.abs(
            weights
        )

        max_position_weight = float(
            np.max(
                position_weights
            )
        )

        risk_contribution_pct = (
            self._calculate_risk_contributions(
                weights,
                covariance,
                native_volatility,
            )
        )

        max_risk_contribution_pct = float(
            np.max(
                np.abs(
                    risk_contribution_pct
                )
            )
        ) if risk_contribution_pct.size else 0.0

        return {
            "variance": variance,
            "native_volatility": native_volatility,
            "annualized_volatility":
                annualized_volatility,
            "gross_leverage":
                gross_leverage,
            "max_position_weight":
                max_position_weight,
            "risk_contribution_pct":
                tuple(
                    float(value)
                    for value in risk_contribution_pct
                ),
            "max_risk_contribution_pct":
                max_risk_contribution_pct,
        }

    # ============================================================
    # R3E.9 TAIL-RISK INPUT
    # ============================================================

    @classmethod
    def _prepare_tail_risk(
        cls,
        tail_risk: Mapping[str, Any] | Any | None,
    ) -> dict[str, Any]:
        """Normalize an already-computed R3E.7 tail aggregation result."""
        if tail_risk is None:
            return {
                "available": False,
                "aggregate_tail_loss": None,
                "aggregate_tail_loss_pct": None,
                "source": None,
            }

        if isinstance(tail_risk, Mapping):
            payload = dict(tail_risk)
        elif hasattr(tail_risk, "__dict__"):
            payload = dict(vars(tail_risk))
        else:
            raise TypeError(
                "tail_risk must be a mapping or R3E.7 result object."
            )

        loss = payload.get("aggregate_tail_loss")
        loss_pct = payload.get("aggregate_tail_loss_pct")

        if loss is None and loss_pct is None:
            raise ValueError(
                "tail_risk must contain aggregate_tail_loss or "
                "aggregate_tail_loss_pct."
            )

        if loss is not None:
            loss = float(loss)
            if not np.isfinite(loss) or loss < 0.0:
                raise ValueError(
                    "aggregate_tail_loss must be finite and non-negative."
                )

        if loss_pct is not None:
            loss_pct = float(loss_pct)
            if not np.isfinite(loss_pct) or loss_pct < 0.0:
                raise ValueError(
                    "aggregate_tail_loss_pct must be finite and non-negative."
                )

        if loss is not None and loss_pct is not None and loss == 0.0 and loss_pct > 1e-12:
            raise ValueError(
                "tail-risk loss and loss percentage are inconsistent."
            )

        return {
            "available": True,
            "aggregate_tail_loss": loss,
            "aggregate_tail_loss_pct": loss_pct,
            "source": payload.get("tail_loss_source"),
            "method": payload.get("method"),
        }

    # ============================================================
    # BREACH DETECTION
    # ============================================================

    def _identify_breaches(
        self,
        metrics: Mapping[str, Any],
    ) -> tuple[
        list[str],
        list[str],
        bool,
        bool,
    ]:
        """
        Identify risk-envelope breaches.

        Returns
        -------
        breaches:
            Machine-readable breach identifiers.

        reasons:
            Human-readable explanations.

        scalable_breach:
            True when a scalar exposure reduction can address the
            breach.

        non_scalable_breach:
            True when scalar reduction cannot address the breach.
        """

        breaches: list[str] = []
        reasons: list[str] = []

        scalable_breach = False
        non_scalable_breach = False

        annualized_volatility = float(
            metrics["annualized_volatility"]
        )

        gross_leverage = float(
            metrics["gross_leverage"]
        )

        max_position_weight = float(
            metrics["max_position_weight"]
        )

        max_risk_contribution_pct = float(
            metrics["max_risk_contribution_pct"]
        )

        tail_risk_available = bool(metrics.get("available", False))
        aggregate_tail_loss_pct = metrics.get("aggregate_tail_loss_pct")

        # --------------------------------------------------------
        # AGGREGATE TAIL LOSS
        # --------------------------------------------------------

        if (
            self.max_aggregate_tail_loss_pct is not None
            and tail_risk_available
            and aggregate_tail_loss_pct is not None
            and float(aggregate_tail_loss_pct)
            > self.max_aggregate_tail_loss_pct + self.tolerance
        ):
            breaches.append("MAX_AGGREGATE_TAIL_LOSS")
            reasons.append(
                "Aggregate tail loss percentage "
                f"{float(aggregate_tail_loss_pct):.8f} exceeds "
                f"limit {self.max_aggregate_tail_loss_pct:.8f}."
            )
            scalable_breach = True

        # --------------------------------------------------------
        # ANNUALIZED VOLATILITY
        # --------------------------------------------------------

        if (
            annualized_volatility
            >
            self.max_annual_volatility
            +
            self.tolerance
        ):
            breaches.append(
                "MAX_ANNUAL_VOLATILITY"
            )

            reasons.append(
                (
                    "Annualized portfolio volatility "
                    f"{annualized_volatility:.8f} exceeds "
                    f"limit {self.max_annual_volatility:.8f}."
                )
            )

            scalable_breach = True

        # --------------------------------------------------------
        # GROSS LEVERAGE
        # --------------------------------------------------------

        if (
            gross_leverage
            >
            self.max_leverage
            +
            self.tolerance
        ):
            breaches.append(
                "MAX_LEVERAGE"
            )

            reasons.append(
                (
                    "Gross leverage "
                    f"{gross_leverage:.8f} exceeds "
                    f"limit {self.max_leverage:.8f}."
                )
            )

            scalable_breach = True

        # --------------------------------------------------------
        # POSITION CONCENTRATION
        # --------------------------------------------------------

        if (
            max_position_weight
            >
            self.max_position_weight
            +
            self.tolerance
        ):
            breaches.append(
                "MAX_POSITION_WEIGHT"
            )

            reasons.append(
                (
                    "Maximum individual portfolio weight "
                    f"{max_position_weight:.8f} exceeds "
                    f"limit {self.max_position_weight:.8f}."
                )
            )

            non_scalable_breach = True

        # --------------------------------------------------------
        # RISK CONTRIBUTION
        # --------------------------------------------------------

        if (
            max_risk_contribution_pct
            >
            self.max_risk_contribution_pct
            +
            self.tolerance
        ):
            breaches.append(
                "MAX_RISK_CONTRIBUTION"
            )

            reasons.append(
                (
                    "Maximum individual risk contribution "
                    f"{max_risk_contribution_pct:.8f} exceeds "
                    f"limit "
                    f"{self.max_risk_contribution_pct:.8f}."
                )
            )

            non_scalable_breach = True

        return (
            breaches,
            reasons,
            scalable_breach,
            non_scalable_breach,
        )

    # ============================================================
    # SCALAR GOVERNANCE
    # ============================================================

    def _calculate_reduction_scale(
        self,
        metrics: Mapping[str, Any],
    ) -> float:
        """
        Calculate the maximum permissible scalar exposure.

        The governor can only reduce exposure.

        Scaling all risky weights by k produces:

            leverage_new = k * leverage_old

        and:

            volatility_new = k * volatility_old

        Therefore the required scale is the minimum of the
        independent scalable risk limits.

        The result is always:

            0 <= scale <= 1
        """

        scale = 1.0

        annualized_volatility = float(
            metrics["annualized_volatility"]
        )

        gross_leverage = float(
            metrics["gross_leverage"]
        )

        aggregate_tail_loss_pct = metrics.get("aggregate_tail_loss_pct")

        # --------------------------------------------------------
        # TAIL-LOSS SCALE
        # --------------------------------------------------------

        if (
            self.max_aggregate_tail_loss_pct is not None
            and aggregate_tail_loss_pct is not None
            and float(aggregate_tail_loss_pct)
            > self.max_aggregate_tail_loss_pct + self.tolerance
        ):
            current_tail_loss_pct = float(aggregate_tail_loss_pct)
            if current_tail_loss_pct <= 0.0:
                tail_scale = 0.0
            else:
                tail_scale = (
                    self.max_aggregate_tail_loss_pct
                    / current_tail_loss_pct
                )
            scale = min(scale, tail_scale)

        # --------------------------------------------------------
        # VOLATILITY SCALE
        # --------------------------------------------------------

        if (
            annualized_volatility
            >
            self.max_annual_volatility
            +
            self.tolerance
        ):
            if annualized_volatility <= 0.0:
                volatility_scale = 0.0
            else:
                volatility_scale = (
                    self.max_annual_volatility
                    /
                    annualized_volatility
                )

            scale = min(
                scale,
                volatility_scale,
            )

        # --------------------------------------------------------
        # LEVERAGE SCALE
        # --------------------------------------------------------

        if (
            gross_leverage
            >
            self.max_leverage
            +
            self.tolerance
        ):
            if gross_leverage <= 0.0:
                leverage_scale = 0.0
            else:
                leverage_scale = (
                    self.max_leverage
                    /
                    gross_leverage
                )

            scale = min(
                scale,
                leverage_scale,
            )

        scale = float(
            np.clip(
                scale,
                0.0,
                1.0,
            )
        )

        return scale

    # ============================================================
    # EVALUATE
    # ============================================================

    def evaluate(
        self,
        weights: Sequence[float] | np.ndarray,
        covariance: Sequence[Sequence[float]] | np.ndarray,
        tail_risk: Mapping[str, Any] | Any | None = None,
    ) -> RiskGovernorResult:
        """
        Evaluate a candidate portfolio without applying governance.

        This method is diagnostic.

        It never modifies the supplied weights.

        A candidate can therefore be evaluated independently before
        deciding whether governance should be applied.
        """

        prepared_weights = self._prepare_weights(
            weights
        )

        prepared_covariance = self._prepare_covariance(
            covariance,
            prepared_weights.size,
        )

        metrics = self._calculate_metrics(
            prepared_weights,
            prepared_covariance,
        )

        tail_metrics = self._prepare_tail_risk(tail_risk)
        metrics.update(tail_metrics)

        (
            breaches,
            reasons,
            scalable_breach,
            non_scalable_breach,
        ) = self._identify_breaches(
            metrics
        )

        if non_scalable_breach:
            action = RiskGovernorAction.REJECT.value
            approved = False
            scale = 0.0

        elif scalable_breach:
            action = RiskGovernorAction.REDUCE.value
            approved = False
            scale = self._calculate_reduction_scale(
                metrics
            )

        else:
            action = RiskGovernorAction.PASS.value
            approved = True
            scale = 1.0

        governed_weights = (
            prepared_weights * scale
        )

        governed_variance = float(
            governed_weights
            @ prepared_covariance
            @ governed_weights
        )

        governed_variance = max(
            governed_variance,
            0.0,
        )

        governed_native_volatility = float(
            np.sqrt(
                governed_variance
            )
        )

        governed_annualized_volatility = float(
            governed_native_volatility
            *
            np.sqrt(
                self.periods_per_year
            )
        )

        governed_gross_leverage = float(
            np.sum(
                np.abs(
                    governed_weights
                )
            )
        )

        cash = float(
            max(
                0.0,
                1.0
                -
                np.sum(
                    governed_weights
                ),
            )
        )

        aggregate_tail_loss_pct = metrics.get("aggregate_tail_loss_pct")
        governed_aggregate_tail_loss_pct = (
            None
            if aggregate_tail_loss_pct is None
            else float(aggregate_tail_loss_pct) * scale
        )

        complete_metrics = dict(
            metrics
        )

        complete_metrics.update(
            {
                "governed_native_volatility":
                    governed_native_volatility,
                "governed_annualized_volatility":
                    governed_annualized_volatility,
                "governed_gross_leverage":
                    governed_gross_leverage,
                "scale":
                    scale,
                "cash":
                    cash,
                "scalable_breach":
                    scalable_breach,
                "non_scalable_breach":
                    non_scalable_breach,
                "governed_aggregate_tail_loss_pct":
                    governed_aggregate_tail_loss_pct,
            }
        )

        # --------------------------------------------------------
        # A REDUCTION IS ONLY APPROVED IF THE REDUCED PORTFOLIO
        # ACTUALLY SATISFIES THE SCALABLE LIMITS.
        # --------------------------------------------------------

        if action == RiskGovernorAction.REDUCE.value:

            # A scalable breach is eligible for approval after
            # successful scalar reduction. Start from an approved
            # state and fail closed if the governed portfolio still
            # violates any scalable limit.
            approved = True

            if (
                governed_annualized_volatility
                >
                self.max_annual_volatility
                +
                self.tolerance
            ):
                approved = False

                reasons.append(
                    (
                        "Scalar volatility reduction did not "
                        "produce a portfolio within the "
                        "annualized volatility limit."
                    )
                )

            if (
                governed_gross_leverage
                >
                self.max_leverage
                +
                self.tolerance
            ):
                approved = False

                reasons.append(
                    (
                        "Scalar leverage reduction did not "
                        "produce a portfolio within the "
                        "gross leverage limit."
                    )
                )

            if (
                self.max_aggregate_tail_loss_pct is not None
                and governed_aggregate_tail_loss_pct is not None
                and governed_aggregate_tail_loss_pct
                > self.max_aggregate_tail_loss_pct + self.tolerance
            ):
                approved = False
                reasons.append(
                    (
                        "Scalar tail-risk reduction did not produce a "
                        "portfolio within the aggregate tail-loss limit."
                    )
                )

            if approved:
                reasons.append(
                    (
                        "Portfolio exposure was reduced by "
                        f"scalar factor {scale:.8f}."
                    )
                )

        # A REDUCE result is still a valid governance decision only
        # when the post-reduction portfolio satisfies every scalable
        # limit. Non-scalable breaches remain REJECT decisions.
        #
        # IMPORTANT: evaluate() must always return a complete
        # RiskGovernorResult. A missing return here would cause govern()
        # to receive None and fail at the first result.action access.
        result = RiskGovernorResult(
            action=action,
            approved=approved,
            scale=scale,
            original_weights=tuple(
                float(value)
                for value in prepared_weights
            ),
            approved_weights=(
                tuple(
                    float(value)
                    for value in governed_weights
                )
                if approved
                else tuple()
            ),
            cash=(cash if approved else 1.0),
            annualized_volatility=float(
                metrics["annualized_volatility"]
            ),
            governed_annualized_volatility=(
                governed_annualized_volatility
                if approved
                else float("nan")
            ),
            gross_leverage=float(
                metrics["gross_leverage"]
            ),
            governed_gross_leverage=(
                governed_gross_leverage
                if approved
                else float("nan")
            ),
            max_position_weight=float(
                metrics["max_position_weight"]
            ),
            max_risk_contribution_pct=float(
                metrics["max_risk_contribution_pct"]
            ),
            breaches=tuple(breaches),
            reasons=tuple(reasons),
            metrics=complete_metrics,
            tail_risk_available=bool(metrics.get("available", False)),
            aggregate_tail_loss=(
                metrics.get("aggregate_tail_loss")
            ),
            aggregate_tail_loss_pct=(
                metrics.get("aggregate_tail_loss_pct")
            ),
            governed_aggregate_tail_loss_pct=(
                governed_aggregate_tail_loss_pct
            ),
            max_aggregate_tail_loss_pct=(
                self.max_aggregate_tail_loss_pct
            ),
        )

        self.last_result = result

        return result

    # ============================================================
    # GOVERN
    # ============================================================

    def govern(
        self,
        weights: Sequence[float] | np.ndarray,
        covariance: Sequence[Sequence[float]] | np.ndarray,
        tail_risk: Mapping[str, Any] | Any | None = None,
    ) -> RiskGovernorResult:
        """
        Evaluate and govern a candidate portfolio.

        The returned result becomes the authoritative governance
        decision for this candidate portfolio.

        No exposure is ever increased.
        """

        try:
            result = self.evaluate(
                weights,
                covariance,
                tail_risk=tail_risk,
            )

        except (
            TypeError,
            ValueError,
            FloatingPointError,
        ) as exc:

            prepared_weights = np.asarray(
                weights,
                dtype=float,
            )

            if prepared_weights.ndim != 1:
                prepared_weights = np.asarray(
                    [],
                    dtype=float,
                )

            result = RiskGovernorResult(
                action=RiskGovernorAction.REJECT.value,
                approved=False,
                scale=0.0,
                original_weights=tuple(
                    float(value)
                    for value in prepared_weights
                ),
                approved_weights=tuple(),
                cash=1.0,
                annualized_volatility=float(
                    "nan"
                ),
                governed_annualized_volatility=
                    float("nan"),
                gross_leverage=float(
                    "nan"
                ),
                governed_gross_leverage=
                    float("nan"),
                max_position_weight=float(
                    "nan"
                ),
                max_risk_contribution_pct=
                    float("nan"),
                breaches=(
                    "INVALID_RISK_INPUT",
                ),
                reasons=(
                    str(exc),
                ),
                metrics={
                    "error":
                        str(exc),
                },
            )

        self.last_result = result

        return result

    # ============================================================
    # VALIDATION
    # ============================================================

    def validate(self) -> bool:
        """
        Validate the configured risk envelope.
        """

        self._validate_limit(
            self.max_annual_volatility,
            "max_annual_volatility",
            strictly_positive=True,
        )

        self._validate_limit(
            self.max_leverage,
            "max_leverage",
            strictly_positive=False,
        )

        self._validate_limit(
            self.max_position_weight,
            "max_position_weight",
            strictly_positive=True,
        )

        self._validate_limit(
            self.max_risk_contribution_pct,
            "max_risk_contribution_pct",
            strictly_positive=True,
        )

        if self.max_aggregate_tail_loss_pct is not None:
            self._validate_limit(
                self.max_aggregate_tail_loss_pct,
                "max_aggregate_tail_loss_pct",
                strictly_positive=True,
            )

        self._validate_limit(
            self.tolerance,
            "tolerance",
            strictly_positive=False,
        )

        if self.periods_per_year <= 0:
            raise ValueError(
                "periods_per_year must be positive."
            )

        return True

    # ============================================================
    # HEALTH CHECK
    # ============================================================

    def health_check(self) -> bool:
        """
        Validate the governor configuration.
        """

        return self.validate()

    # ============================================================
    # METADATA
    # ============================================================

    @property
    def metadata(self) -> dict[str, Any]:
        """
        Return institutional component metadata.
        """

        return {
            "class":
                self.__class__.__name__,
            "version":
                self.API_VERSION,
            "risk_frequency":
                "daily",
            "annualization_method":
                "sqrt_time",
            "periods_per_year":
                self.periods_per_year,
            "max_aggregate_tail_loss_pct":
                self.max_aggregate_tail_loss_pct,
            "r3e_tail_governance": True,
            "tail_loss_scaling_assumption": (
                "Supplied aggregate tail P&L loss is assumed to scale "
                "linearly with scalar risky exposure."
            ),
            "governance_actions": (
                RiskGovernorAction.PASS.value,
                RiskGovernorAction.REDUCE.value,
                RiskGovernorAction.REJECT.value,
            ),
            "scope": (
                "portfolio_risk_governance"
            ),
        }

    # ============================================================
    # SUMMARY
    # ============================================================

    def summary(self) -> dict[str, Any]:
        """
        Return the configured risk envelope and latest decision.
        """

        result = None

        if self.last_result is not None:
            result = self.last_result.to_dict()

        return {
            "configuration":
                dict(self._summary),
            "last_result":
                result,
        }

    # ============================================================
    # SERIALIZATION
    # ============================================================

    def to_dict(self) -> dict[str, Any]:
        """
        Return serializable governor state.
        """

        result = None

        if self.last_result is not None:
            result = self.last_result.to_dict()

        return {
            **self.metadata,
            "configuration": {
                "max_annual_volatility":
                    self.max_annual_volatility,
                "max_leverage":
                    self.max_leverage,
                "max_position_weight":
                    self.max_position_weight,
                "max_risk_contribution_pct":
                    self.max_risk_contribution_pct,
                "max_aggregate_tail_loss_pct":
                    self.max_aggregate_tail_loss_pct,
                "tolerance":
                    self.tolerance,
                "periods_per_year":
                    self.periods_per_year,
            },
            "last_result":
                result,
        }


# ================================================================
# R3E.9 TAIL GOVERNANCE TEST
# ================================================================


def test_risk_governor_tail_loss_reduction() -> None:
    """Test scalar governance against an R3E.7 aggregate tail loss."""
    governor = PortfolioRiskGovernor(
        max_annual_volatility=10.0,
        max_leverage=2.0,
        max_position_weight=1.0,
        max_risk_contribution_pct=1.0,
        max_aggregate_tail_loss_pct=0.05,
    )

    weights = np.array([0.60, 0.40], dtype=float)
    covariance = np.diag([0.000001, 0.000001])
    tail_risk = {
        "aggregate_tail_loss": 12_000.0,
        "aggregate_tail_loss_pct": 0.12,
        "tail_loss_source": "historical_stress",
        "method": "historical_tail_plus_max_scenario_envelope",
    }

    result = governor.govern(
        weights,
        covariance,
        tail_risk=tail_risk,
    )

    assert result.action == RiskGovernorAction.REDUCE.value
    assert result.approved
    assert "MAX_AGGREGATE_TAIL_LOSS" in result.breaches
    assert np.isclose(result.scale, 0.05 / 0.12)
    assert np.isclose(result.governed_aggregate_tail_loss_pct, 0.05)
    assert result.tail_risk_available is True
    assert np.all(
        np.abs(np.asarray(result.approved_weights))
        <= np.abs(weights) + 1e-12
    )


def test_risk_governor_tail_loss_is_ignored_when_unconfigured() -> None:
    """Tail results must remain diagnostic when no tail ceiling is configured."""
    governor = PortfolioRiskGovernor(
        max_annual_volatility=10.0,
        max_leverage=2.0,
        max_position_weight=1.0,
        max_risk_contribution_pct=1.0,
    )

    result = governor.govern(
        np.array([0.50, 0.50]),
        np.diag([0.000001, 0.000001]),
        tail_risk={
            "aggregate_tail_loss": 50_000.0,
            "aggregate_tail_loss_pct": 0.50,
        },
    )

    assert result.action == RiskGovernorAction.PASS.value
    assert result.approved
    assert result.scale == 1.0
    assert result.tail_risk_available is True


# ================================================================
# DETERMINISTIC SELF-TESTS
# ================================================================


def test_risk_governor_pass() -> None:
    """
    Test a portfolio inside the complete risk envelope.
    """

    governor = PortfolioRiskGovernor(
        max_annual_volatility=0.30,
        max_leverage=1.00,
        max_position_weight=0.60,
        max_risk_contribution_pct=0.75,
    )

    weights = np.array(
        [0.50, 0.50],
        dtype=float,
    )

    covariance = np.diag(
        [
            0.0001,
            0.0001,
        ]
    )

    result = governor.govern(
        weights,
        covariance,
    )

    assert result.action == "PASS"
    assert result.approved
    assert result.scale == 1.0

    assert np.allclose(
        result.approved_weights,
        weights,
    )


def test_risk_governor_volatility_reduction() -> None:
    """
    Test scalar reduction caused by excessive volatility.
    """

    governor = PortfolioRiskGovernor(
        max_annual_volatility=0.10,
        max_leverage=2.00,
        max_position_weight=1.00,
        max_risk_contribution_pct=1.00,
    )

    weights = np.array(
        [1.00],
        dtype=float,
    )

    covariance = np.array(
        [
            [0.0004],
        ]
    )

    result = governor.govern(
        weights,
        covariance,
    )

    assert result.action == "REDUCE"
    assert result.approved

    assert result.scale < 1.0
    assert result.scale > 0.0

    assert (
        result.governed_annualized_volatility
        <=
        governor.max_annual_volatility
        +
        governor.tolerance
    )

    assert (
        result.approved_weights[0]
        <
        result.original_weights[0]
    )


def test_risk_governor_leverage_reduction() -> None:
    """
    Test scalar reduction caused by excessive gross leverage.
    """

    governor = PortfolioRiskGovernor(
        max_annual_volatility=10.0,
        max_leverage=1.00,
        max_position_weight=2.00,
        max_risk_contribution_pct=1.00,
    )

    weights = np.array(
        [0.80, 0.80],
        dtype=float,
    )

    covariance = np.diag(
        [
            0.0001,
            0.0001,
        ]
    )

    result = governor.govern(
        weights,
        covariance,
    )

    assert result.action == "REDUCE"
    assert result.approved

    assert np.isclose(
        result.scale,
        1.00 / 1.60,
    )

    assert (
        result.governed_gross_leverage
        <=
        governor.max_leverage
        +
        governor.tolerance
    )


def test_risk_governor_position_concentration_reject() -> None:
    """
    Position concentration cannot be solved by scalar reduction
    because scalar reduction does not change relative
    concentration.
    """

    governor = PortfolioRiskGovernor(
        max_annual_volatility=10.0,
        max_leverage=2.00,
        max_position_weight=0.40,
        max_risk_contribution_pct=1.00,
    )

    weights = np.array(
        [0.80, 0.20],
        dtype=float,
    )

    covariance = np.diag(
        [
            0.0001,
            0.0001,
        ]
    )

    result = governor.govern(
        weights,
        covariance,
    )

    assert result.action == "REJECT"
    assert not result.approved

    assert (
        "MAX_POSITION_WEIGHT"
        in result.breaches
    )


def test_risk_governor_risk_contribution_reject() -> None:
    """
    Test individual risk-contribution governance.
    """

    governor = PortfolioRiskGovernor(
        max_annual_volatility=10.0,
        max_leverage=2.00,
        max_position_weight=1.00,
        max_risk_contribution_pct=0.60,
    )

    weights = np.array(
        [0.90, 0.10],
        dtype=float,
    )

    covariance = np.diag(
        [
            0.0004,
            0.0001,
        ]
    )

    result = governor.govern(
        weights,
        covariance,
    )

    assert result.action == "REJECT"
    assert not result.approved

    assert (
        "MAX_RISK_CONTRIBUTION"
        in result.breaches
    )


def test_risk_governor_never_increases_exposure() -> None:
    """
    Governance must never increase any candidate weight.
    """

    governor = PortfolioRiskGovernor(
        max_annual_volatility=0.10,
        max_leverage=1.00,
        max_position_weight=1.00,
        max_risk_contribution_pct=1.00,
    )

    weights = np.array(
        [0.80, 0.80],
        dtype=float,
    )

    covariance = np.diag(
        [
            0.0004,
            0.0004,
        ]
    )

    result = governor.govern(
        weights,
        covariance,
    )

    assert np.all(
        np.asarray(
            result.approved_weights
        )
        <=
        weights
        +
        1e-12
    )

    assert (
        result.scale
        <=
        1.0
    )


def test_risk_governor_invalid_inputs_reject() -> None:
    """
    Invalid risk inputs must fail closed.
    """

    governor = PortfolioRiskGovernor(
        max_annual_volatility=0.20,
        max_leverage=1.00,
        max_position_weight=0.50,
        max_risk_contribution_pct=0.50,
    )

    weights = np.array(
        [0.50, 0.50],
        dtype=float,
    )

    covariance = np.array(
        [
            [0.0001, np.nan],
            [np.nan, 0.0001],
        ]
    )

    result = governor.govern(
        weights,
        covariance,
    )

    assert result.action == "REJECT"
    assert not result.approved

    assert (
        "INVALID_RISK_INPUT"
        in result.breaches
    )


def test_risk_governor_health_and_metadata() -> None:
    """
    Test institutional component contract.
    """

    governor = PortfolioRiskGovernor(
        max_annual_volatility=0.20,
        max_leverage=1.00,
        max_position_weight=0.50,
        max_risk_contribution_pct=0.50,
    )

    assert governor.validate()
    assert governor.health_check()

    assert (
        governor.API_VERSION
        ==
        "1.1.0"
    )

    assert (
        "evaluate"
        in governor.PUBLIC_METHODS
    )

    assert (
        "govern"
        in governor.PUBLIC_METHODS
    )

    metadata = governor.metadata

    assert (
        metadata["version"]
        ==
        "1.1.0"
    )

    assert (
        metadata["risk_frequency"]
        ==
        "daily"
    )

    assert (
        metadata["periods_per_year"]
        ==
        252
    )


# ================================================================
# SELF-TEST RUNNER
# ================================================================


def run_self_tests() -> None:
    """
    Run all deterministic Risk Governor tests.
    """

    test_risk_governor_pass()

    test_risk_governor_volatility_reduction()

    test_risk_governor_leverage_reduction()

    test_risk_governor_position_concentration_reject()

    test_risk_governor_risk_contribution_reject()

    test_risk_governor_never_increases_exposure()

    test_risk_governor_invalid_inputs_reject()

    test_risk_governor_health_and_metadata()

    print(
        "Risk Governor tests passed."
    )


# ================================================================
# MAIN
# ================================================================


if __name__ == "__main__":
    run_self_tests()