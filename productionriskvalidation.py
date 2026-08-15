# ======================================================================
# PRODUCTION RISK VALIDATION
# PHASE IV-B.4
# ======================================================================

"""
Production portfolio-risk validation boundary for the institutional
portfolio stack.

This module validates the authoritative portfolio decision produced by
the production decision engine.

Design principles
-----------------
1. PortfolioDecisionEngine remains the decision authority.
2. This module validates decisions; it does not generate portfolio
   weights or make portfolio allocation decisions.
3. Existing RiskBudgetEngine outputs are consumed rather than silently
   recalculated.
4. Risk validation is deterministic.
5. Risk validation is fail-closed.
6. Missing mandatory risk information causes rejection.
7. Missing configured risk limits cause rejection rather than silent
   substitution.
8. Test doubles are not used by the production validation class.
9. Live trading and broker execution remain outside this phase.
10. Execution must not proceed after a failed risk validation.
"""

# ======================================================================
# SECTION 1
# IMPORTS
# ======================================================================

# ----------------------------------------------------------------------
# 1.1 STANDARD LIBRARY
# ----------------------------------------------------------------------

from __future__ import annotations

from dataclasses import (
    dataclass,
    field,
)

import math

from typing import (
    Any,
    Mapping,
    Optional,
)


# ======================================================================
# SECTION 2
# EXCEPTIONS
# ======================================================================


class ProductionRiskValidationError(
    Exception
):
    """
    Base exception for Phase IV-B.4 production risk validation.
    """

    pass


class RiskValidationConfigurationError(
    ProductionRiskValidationError
):
    """
    Raised when the risk validation configuration is invalid.
    """

    pass


class RiskValidationCalculationError(
    ProductionRiskValidationError
):
    """
    Raised when production risk validation cannot be completed.
    """

    pass


# ======================================================================
# SECTION 3
# RISK CHECK RESULT
# ======================================================================


@dataclass(
    frozen=True
)
class RiskCheck:
    """
    Immutable result for one risk validation check.
    """

    # ------------------------------------------------------------------
    # 3.1 CHECK IDENTITY
    # ------------------------------------------------------------------

    name: str

    # ------------------------------------------------------------------
    # 3.2 CHECK STATE
    # ------------------------------------------------------------------

    passed: bool

    # ------------------------------------------------------------------
    # 3.3 CHECK VALUES
    # ------------------------------------------------------------------

    value: Any = None

    limit: Any = None

    # ------------------------------------------------------------------
    # 3.4 CHECK MESSAGE
    # ------------------------------------------------------------------

    message: str = ""

    # ------------------------------------------------------------------
    # 3.5 CHECK CRITICALITY
    # ------------------------------------------------------------------

    mandatory: bool = True

    # ==================================================================
    # 3.6 SERIALIZATION
    # ==================================================================

    def to_dict(
        self,
    ) -> dict[str, Any]:
        """
        Convert the risk check to a serializable dictionary.
        """

        return {
            "name": (
                self.name
            ),
            "passed": (
                bool(
                    self.passed
                )
            ),
            "value": (
                self.value
            ),
            "limit": (
                self.limit
            ),
            "message": (
                self.message
            ),
            "mandatory": (
                bool(
                    self.mandatory
                )
            ),
        }


# ======================================================================
# SECTION 4
# PRODUCTION RISK VALIDATION RESULT
# ======================================================================


@dataclass(
    frozen=True
)
class ProductionRiskValidationResult:
    """
    Immutable representation of one Phase IV-B.4 risk-validation result.
    """

    # ------------------------------------------------------------------
    # 4.1 DECISION STATE
    # ------------------------------------------------------------------

    approved: bool

    status: str

    decision_id: Optional[str]

    regime: Optional[str]

    # ------------------------------------------------------------------
    # 4.2 PORTFOLIO RISK
    # ------------------------------------------------------------------

    portfolio_volatility: float

    gross_exposure: float

    net_exposure: float

    # ------------------------------------------------------------------
    # 4.3 RISK COMPLIANCE
    # ------------------------------------------------------------------

    risk_budget_compliant: bool

    volatility_compliant: bool

    gross_exposure_compliant: bool

    net_exposure_compliant: bool

    concentration_compliant: bool

    numerical_integrity_compliant: bool

    # ------------------------------------------------------------------
    # 4.4 CHECK RESULTS
    # ------------------------------------------------------------------

    checks: tuple[
        RiskCheck,
        ...
    ] = field(
        default_factory=tuple
    )

    # ------------------------------------------------------------------
    # 4.5 WARNINGS / ERRORS
    # ------------------------------------------------------------------

    warnings: tuple[
        str,
        ...
    ] = field(
        default_factory=tuple
    )

    errors: tuple[
        str,
        ...
    ] = field(
        default_factory=tuple
    )

    # ------------------------------------------------------------------
    # 4.6 DIAGNOSTICS
    # ------------------------------------------------------------------

    diagnostics: Mapping[
        str,
        Any,
    ] = field(
        default_factory=dict
    )

    # ==================================================================
    # 4.7 SERIALIZATION
    # ==================================================================

    def to_dict(
        self,
    ) -> dict[str, Any]:
        """
        Convert the complete validation result to a dictionary.
        """

        return {
            "approved": (
                bool(
                    self.approved
                )
            ),
            "status": (
                self.status
            ),
            "decision_id": (
                self.decision_id
            ),
            "regime": (
                self.regime
            ),
            "portfolio_volatility": (
                float(
                    self.portfolio_volatility
                )
            ),
            "gross_exposure": (
                float(
                    self.gross_exposure
                )
            ),
            "net_exposure": (
                float(
                    self.net_exposure
                )
            ),
            "risk_budget_compliant": (
                bool(
                    self.risk_budget_compliant
                )
            ),
            "volatility_compliant": (
                bool(
                    self.volatility_compliant
                )
            ),
            "gross_exposure_compliant": (
                bool(
                    self.gross_exposure_compliant
                )
            ),
            "net_exposure_compliant": (
                bool(
                    self.net_exposure_compliant
                )
            ),
            "concentration_compliant": (
                bool(
                    self.concentration_compliant
                )
            ),
            "numerical_integrity_compliant": (
                bool(
                    self.numerical_integrity_compliant
                )
            ),
            "checks": [
                check.to_dict()
                for check in self.checks
            ],
            "warnings": list(
                self.warnings
            ),
            "errors": list(
                self.errors
            ),
            "diagnostics": dict(
                self.diagnostics
            ),
        }


# ======================================================================
# SECTION 5
# PRODUCTION RISK VALIDATION ENGINE
# ======================================================================


class ProductionRiskValidation:
    """
    Phase IV-B.4 production risk-validation boundary.

    The validator consumes the authoritative portfolio decision and the
    existing risk-budget result.

    It deliberately does not independently calculate covariance,
    portfolio volatility, or portfolio risk contributions.

    Those calculations belong to the established production risk stack.
    """

    # ==================================================================
    # 5.1 API METADATA
    # ==================================================================

    API_VERSION = (
        "1.0.0"
    )

    COMPONENT = (
        "ProductionRiskValidation"
    )

    PHASE = (
        "IV-B.4"
    )

    # ==================================================================
    # 5.2 DECISION STATUSES
    # ==================================================================

    APPROVED = (
        "APPROVED"
    )

    REJECTED = (
        "REJECTED"
    )

    FAILED = (
        "FAILED"
    )

    # ==================================================================
    # 5.3 CONSTRUCTOR
    # ==================================================================

    def __init__(
        self,
        *,
        max_portfolio_volatility: (
            Optional[float]
        ) = None,
        max_net_exposure: (
            Optional[float]
        ) = None,
        max_position_weight: (
            Optional[float]
        ) = None,
        fail_closed: bool = True,
        budget_tolerance: (
            Optional[float]
        ) = None,
    ) -> None:
        """
        Initialize the Phase IV-B.4 production risk validator.

        Parameters
        ----------
        max_portfolio_volatility:
            Maximum permitted portfolio volatility.

        max_net_exposure:
            Maximum permitted absolute net exposure.

        max_position_weight:
            Maximum permitted absolute individual position weight.

        fail_closed:
            If True, unexpected validation failures produce a FAILED
            result rather than permitting execution.

        budget_tolerance:
            Optional explicit tolerance for the risk-budget error.
        """

        # --------------------------------------------------------------
        # PORTFOLIO VOLATILITY LIMIT
        # --------------------------------------------------------------

        self.max_portfolio_volatility = (
            self._positive_or_none(
                max_portfolio_volatility,
                "max_portfolio_volatility",
            )
        )

        # --------------------------------------------------------------
        # NET EXPOSURE LIMIT
        # --------------------------------------------------------------

        self.max_net_exposure = (
            self._nonnegative_or_none(
                max_net_exposure,
                "max_net_exposure",
            )
        )

        # --------------------------------------------------------------
        # POSITION CONCENTRATION LIMIT
        # --------------------------------------------------------------

        self.max_position_weight = (
            self._positive_or_none(
                max_position_weight,
                "max_position_weight",
            )
        )

        # --------------------------------------------------------------
        # FAIL-CLOSED POLICY
        # --------------------------------------------------------------

        self.fail_closed = bool(
            fail_closed
        )

        # --------------------------------------------------------------
        # RISK BUDGET TOLERANCE
        # --------------------------------------------------------------

        if budget_tolerance is not None:

            budget_tolerance = float(
                budget_tolerance
            )

            if (
                not math.isfinite(
                    budget_tolerance
                )
                or budget_tolerance <= 0
            ):

                raise RiskValidationConfigurationError(
                    "budget_tolerance must be "
                    "finite and positive."
                )

            self.budget_tolerance = (
                budget_tolerance
            )

        else:

            self.budget_tolerance = None

        # --------------------------------------------------------------
        # VALIDATION STATE
        # --------------------------------------------------------------

        self.last_result: Optional[
            ProductionRiskValidationResult
        ] = None

        self.validation_count = (
            0
        )

        self.approved_count = (
            0
        )

        self.rejected_count = (
            0
        )

        self.failed_count = (
            0
        )

    # ==================================================================
    # SECTION 6
    # CONFIGURATION VALIDATION
    # ==================================================================

    # ------------------------------------------------------------------
    # 6.1 POSITIVE VALUE
    # ------------------------------------------------------------------

    @staticmethod
    def _positive_or_none(
        value: Optional[float],
        name: str,
    ) -> Optional[float]:
        """
        Validate an optional positive numeric configuration value.
        """

        if value is None:

            return None

        value = float(
            value
        )

        if (
            not math.isfinite(
                value
            )
            or value <= 0
        ):

            raise RiskValidationConfigurationError(
                f"{name} must be "
                "finite and positive."
            )

        return value

    # ------------------------------------------------------------------
    # 6.2 NON-NEGATIVE VALUE
    # ------------------------------------------------------------------

    @staticmethod
    def _nonnegative_or_none(
        value: Optional[float],
        name: str,
    ) -> Optional[float]:
        """
        Validate an optional non-negative numeric configuration value.
        """

        if value is None:

            return None

        value = float(
            value
        )

        if (
            not math.isfinite(
                value
            )
            or value < 0
        ):

            raise RiskValidationConfigurationError(
                f"{name} must be "
                "finite and non-negative."
            )

        return value

    # ==================================================================
    # SECTION 7
    # GENERIC OBJECT ACCESS
    # ==================================================================

    # ------------------------------------------------------------------
    # 7.1 ATTRIBUTE / MAPPING ACCESS
    # ------------------------------------------------------------------

    @staticmethod
    def _get(
        obj: Any,
        name: str,
        default: Any = None,
    ) -> Any:
        """
        Read a value from either an object or mapping.
        """

        if obj is None:

            return default

        if isinstance(
            obj,
            Mapping,
        ):

            return obj.get(
                name,
                default,
            )

        return getattr(
            obj,
            name,
            default,
        )

    # ------------------------------------------------------------------
    # 7.2 FINITE NUMBER CHECK
    # ------------------------------------------------------------------

    @staticmethod
    def _finite(
        value: Any,
    ) -> bool:
        """
        Determine whether a value is finite numeric data.
        """

        try:

            return math.isfinite(
                float(
                    value
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            return False

    # ==================================================================
    # SECTION 8
    # DECISION EXTRACTION
    # ==================================================================

    # ------------------------------------------------------------------
    # 8.1 DECISION STATUS
    # ------------------------------------------------------------------

    @staticmethod
    def _status_value(
        decision: Any,
    ) -> Optional[str]:
        """
        Extract normalized decision status.
        """

        status = (
            ProductionRiskValidation._get(
                decision,
                "status",
            )
        )

        if status is None:

            return None

        return str(
            getattr(
                status,
                "value",
                status,
            )
        )

    # ------------------------------------------------------------------
    # 8.2 DECISION ID
    # ------------------------------------------------------------------

    @staticmethod
    def _decision_id(
        decision: Any,
    ) -> Optional[str]:
        """
        Extract decision identifier.
        """

        value = (
            ProductionRiskValidation._get(
                decision,
                "decision_id",
            )
        )

        if value is None:

            return None

        return str(
            value
        )

    # ------------------------------------------------------------------
    # 8.3 REGIME
    # ------------------------------------------------------------------

    @staticmethod
    def _regime(
        decision: Any,
    ) -> Optional[str]:
        """
        Extract normalized regime.
        """

        value = (
            ProductionRiskValidation._get(
                decision,
                "regime",
            )
        )

        if value is None:

            return None

        return str(
            getattr(
                value,
                "value",
                value,
            )
        )

    # ------------------------------------------------------------------
    # 8.4 PORTFOLIO WEIGHTS
    # ------------------------------------------------------------------

    @staticmethod
    def _weights(
        decision: Any,
    ) -> Optional[
        Mapping[str, float]
    ]:
        """
        Extract portfolio weights.
        """

        weights = (
            ProductionRiskValidation._get(
                decision,
                "weights",
            )
        )

        if weights is None:

            return None

        if hasattr(
            weights,
            "to_dict",
        ):

            try:

                weights = (
                    weights.to_dict()
                )

            except TypeError:

                pass

        if not isinstance(
            weights,
            Mapping,
        ):

            return None

        return {
            str(key): float(
                value
            )
            for key, value
            in weights.items()
        }

    # ==================================================================
    # SECTION 9
    # RISK BUDGET EXTRACTION
    # ==================================================================

    # ------------------------------------------------------------------
    # 9.1 RISK-BUDGET COMPLIANCE
    # ------------------------------------------------------------------

    @staticmethod
    def _risk_budget_ok(
        risk_budget_result: Any,
    ) -> bool:
        """
        Determine whether the existing risk-budget result is compliant.
        """

        if risk_budget_result is None:

            return False

        within = (
            ProductionRiskValidation._get(
                risk_budget_result,
                "within_tolerance",
                None,
            )
        )

        if within is not None:

            return bool(
                within
            )

        budget_error = (
            ProductionRiskValidation._get(
                risk_budget_result,
                "budget_error",
                None,
            )
        )

        if budget_error is None:

            return False

        return (
            math.isfinite(
                float(
                    budget_error
                )
            )
            and float(
                budget_error
            ) <= 1e-6
        )

    # ------------------------------------------------------------------
    # 9.2 BUDGET ERROR
    # ------------------------------------------------------------------

    @staticmethod
    def _risk_budget_error(
        risk_budget_result: Any,
    ) -> Optional[float]:
        """
        Extract risk-budget error.
        """

        value = (
            ProductionRiskValidation._get(
                risk_budget_result,
                "budget_error",
                None,
            )
        )

        if value is None:

            return None

        try:

            return float(
                value
            )

        except (
            TypeError,
            ValueError,
        ):

            return None

    # ------------------------------------------------------------------
    # 9.3 BUDGET DIAGNOSTICS
    # ------------------------------------------------------------------

    @staticmethod
    def _risk_budget_diagnostics(
        risk_budget_result: Any,
    ) -> dict[str, Any]:
        """
        Extract existing risk-budget diagnostics.
        """

        if risk_budget_result is None:

            return {}

        diagnostics = (
            ProductionRiskValidation._get(
                risk_budget_result,
                "diagnostics",
                {},
            )
        )

        return dict(
            diagnostics
            or {}
        )

    # ==================================================================
    # SECTION 10
    # MAIN RISK VALIDATION
    # ==================================================================

    def validate(
        self,
        decision: Any,
        *,
        risk_budget_result: Any = None,
        regime_max_leverage: Optional[float] = None,
    ) -> ProductionRiskValidationResult:
        """
        Validate an authoritative portfolio decision.

        The validator does not generate or modify portfolio weights.

        Parameters
        ----------
        decision:
            Authoritative PortfolioDecision produced by the decision
            engine.

        risk_budget_result:
            Existing RiskBudgetEngine production result.

        regime_max_leverage:
            Maximum gross exposure permitted by the active regime.
        """

        self.validation_count += (
            1
        )

        checks: list[
            RiskCheck
        ] = []

        warnings: list[
            str
        ] = []

        errors: list[
            str
        ] = []

        decision_id = (
            self._decision_id(
                decision
            )
        )

        regime = (
            self._regime(
                decision
            )
        )

        status = (
            self._status_value(
                decision
            )
        )

        try:

            # ==========================================================
            # 10.1 DECISION EXISTENCE
            # ==========================================================

            if decision is None:

                raise RiskValidationCalculationError(
                    "Authoritative portfolio decision "
                    "is missing."
                )

            # ==========================================================
            # 10.2 DECISION IDENTIFIERS
            # ==========================================================

            if status is None:

                errors.append(
                    "Decision has no status."
                )

            if decision_id is None:

                errors.append(
                    "Decision has no decision_id."
                )

            if regime is None:

                errors.append(
                    "Decision has no regime."
                )

            # ==========================================================
            # 10.3 WEIGHTS
            # ==========================================================

            weights = (
                self._weights(
                    decision
                )
            )

            numerical_ok = (
                True
            )

            if (
                weights is None
                or not weights
            ):

                numerical_ok = (
                    False
                )

                errors.append(
                    "Decision contains no "
                    "portfolio weights."
                )

            else:

                for (
                    ticker,
                    weight,
                ) in weights.items():

                    if not math.isfinite(
                        weight
                    ):

                        numerical_ok = (
                            False
                        )

                        errors.append(
                            "Non-finite portfolio "
                            f"weight for '{ticker}'."
                        )

            # ==========================================================
            # 10.4 PORTFOLIO VOLATILITY
            # ==========================================================

            volatility = (
                self._get(
                    decision,
                    "portfolio_volatility",
                    None,
                )
            )

            if not self._finite(
                volatility
            ):

                numerical_ok = (
                    False
                )

                errors.append(
                    "Portfolio volatility is "
                    "missing or non-finite."
                )

                volatility_value = (
                    0.0
                )

            else:

                volatility_value = float(
                    volatility
                )

            # ==========================================================
            # 10.5 GROSS EXPOSURE
            # ==========================================================

            gross_exposure = (
                self._get(
                    decision,
                    "gross_exposure",
                    None,
                )
            )

            if not self._finite(
                gross_exposure
            ):

                numerical_ok = (
                    False
                )

                errors.append(
                    "Gross exposure is "
                    "missing or non-finite."
                )

                gross_value = (
                    0.0
                )

            else:

                gross_value = float(
                    gross_exposure
                )

            # ==========================================================
            # 10.6 NET EXPOSURE
            # ==========================================================

            net_exposure = (
                self._get(
                    decision,
                    "net_exposure",
                    None,
                )
            )

            if not self._finite(
                net_exposure
            ):

                numerical_ok = (
                    False
                )

                errors.append(
                    "Net exposure is "
                    "missing or non-finite."
                )

                net_value = (
                    0.0
                )

            else:

                net_value = float(
                    net_exposure
                )

            # ==========================================================
            # 10.7 NUMERICAL SANITY
            # ==========================================================

            if volatility_value < 0:

                numerical_ok = (
                    False
                )

                errors.append(
                    "Portfolio volatility "
                    "cannot be negative."
                )

            if gross_value < 0:

                numerical_ok = (
                    False
                )

                errors.append(
                    "Gross exposure "
                    "cannot be negative."
                )

            # ==========================================================
            # 10.8 RISK BUDGET
            # ==========================================================

            budget_ok = (
                self._risk_budget_ok(
                    risk_budget_result
                )
            )

            if risk_budget_result is None:

                budget_ok = (
                    False
                )

                errors.append(
                    "RiskBudgetResult is missing; "
                    "risk-budget validation cannot "
                    "be established."
                )

            else:

                budget_error = (
                    self._risk_budget_error(
                        risk_budget_result
                    )
                )

                if (
                    budget_error is None
                    or not math.isfinite(
                        budget_error
                    )
                ):

                    budget_ok = (
                        False
                    )

                    errors.append(
                        "Risk-budget result has no "
                        "finite budget_error."
                    )

                elif (
                    self.budget_tolerance
                    is not None
                    and budget_error
                    > self.budget_tolerance
                ):

                    budget_ok = (
                        False
                    )

                    errors.append(
                        "Risk-budget error exceeds "
                        "configured tolerance."
                    )

            checks.append(
                RiskCheck(
                    name="risk_budget",
                    passed=budget_ok,
                    value=(
                        self._risk_budget_error(
                            risk_budget_result
                        )
                    ),
                    limit=(
                        self.budget_tolerance
                    ),
                    message=(
                        "Risk budget is within tolerance."
                        if budget_ok
                        else
                        "Risk budget validation failed."
                    ),
                )
            )

            # ==========================================================
            # 10.9 REGIME LEVERAGE
            # ==========================================================

            if (
                regime_max_leverage
                is None
            ):

                gross_ok = (
                    False
                )

                errors.append(
                    "Regime maximum leverage is missing; "
                    "gross-exposure validation cannot "
                    "be established."
                )

            else:

                regime_max_leverage = float(
                    regime_max_leverage
                )

                if (
                    not math.isfinite(
                        regime_max_leverage
                    )
                    or regime_max_leverage <= 0
                ):

                    raise RiskValidationConfigurationError(
                        "regime_max_leverage must be "
                        "finite and positive."
                    )

                gross_ok = (
                    gross_value
                    <= regime_max_leverage
                    + 1e-12
                )

                if not gross_ok:

                    errors.append(
                        "Gross exposure exceeds "
                        "the regime maximum leverage."
                    )

            checks.append(
                RiskCheck(
                    name="gross_exposure",
                    passed=gross_ok,
                    value=gross_value,
                    limit=(
                        regime_max_leverage
                    ),
                    message=(
                        "Gross exposure is within "
                        "regime leverage."
                        if gross_ok
                        else
                        "Gross exposure exceeds "
                        "regime leverage."
                    ),
                )
            )

            # ==========================================================
            # 10.10 PORTFOLIO VOLATILITY LIMIT
            # ==========================================================

            if (
                self.max_portfolio_volatility
                is None
            ):

                volatility_ok = (
                    False
                )

                errors.append(
                    "Maximum portfolio volatility "
                    "is not configured; volatility "
                    "validation cannot be established."
                )

            else:

                volatility_ok = (
                    volatility_value
                    <= (
                        self.max_portfolio_volatility
                        + 1e-12
                    )
                )

                if not volatility_ok:

                    errors.append(
                        "Portfolio volatility exceeds "
                        "configured maximum."
                    )

            checks.append(
                RiskCheck(
                    name="portfolio_volatility",
                    passed=volatility_ok,
                    value=(
                        volatility_value
                    ),
                    limit=(
                        self.max_portfolio_volatility
                    ),
                    message=(
                        "Portfolio volatility is "
                        "within limit."
                        if volatility_ok
                        else
                        "Portfolio volatility exceeds "
                        "limit."
                    ),
                )
            )

            # ==========================================================
            # 10.11 NET EXPOSURE LIMIT
            # ==========================================================

            if (
                self.max_net_exposure
                is None
            ):

                net_ok = (
                    False
                )

                errors.append(
                    "Maximum net exposure is not "
                    "configured; net-exposure validation "
                    "cannot be established."
                )

            else:

                net_ok = (
                    abs(
                        net_value
                    )
                    <= (
                        self.max_net_exposure
                        + 1e-12
                    )
                )

                if not net_ok:

                    errors.append(
                        "Absolute net exposure exceeds "
                        "configured maximum."
                    )

            checks.append(
                RiskCheck(
                    name="net_exposure",
                    passed=net_ok,
                    value=net_value,
                    limit=(
                        self.max_net_exposure
                    ),
                    message=(
                        "Net exposure is "
                        "within limit."
                        if net_ok
                        else
                        "Net exposure exceeds "
                        "limit."
                    ),
                )
            )

            # ==========================================================
            # 10.12 CONCENTRATION
            # ==========================================================

            if (
                self.max_position_weight
                is None
            ):

                concentration_ok = (
                    False
                )

                errors.append(
                    "Maximum position weight is not "
                    "configured; concentration validation "
                    "cannot be established."
                )

            elif weights is None:

                concentration_ok = (
                    False
                )

            else:

                concentration_ok = all(
                    abs(
                        weight
                    )
                    <= (
                        self.max_position_weight
                        + 1e-12
                    )
                    for weight
                    in weights.values()
                )

                if not concentration_ok:

                    errors.append(
                        "At least one portfolio position "
                        "exceeds the configured maximum "
                        "weight."
                    )

            checks.append(
                RiskCheck(
                    name="concentration",
                    passed=concentration_ok,
                    value=(
                        max(
                            (
                                abs(
                                    value
                                )
                                for value
                                in weights.values()
                            ),
                            default=0.0,
                        )
                        if weights is not None
                        else None
                    ),
                    limit=(
                        self.max_position_weight
                    ),
                    message=(
                        "Position concentration "
                        "is within limit."
                        if concentration_ok
                        else
                        "Position concentration "
                        "exceeds limit."
                    ),
                )
            )

            # ==========================================================
            # 10.13 NUMERICAL INTEGRITY
            # ==========================================================

            checks.append(
                RiskCheck(
                    name="numerical_integrity",
                    passed=numerical_ok,
                    message=(
                        "All mandatory numerical "
                        "fields are finite."
                        if numerical_ok
                        else
                        "Numerical integrity "
                        "check failed."
                    ),
                )
            )

            # ==========================================================
            # 10.14 AUTHORITATIVE DECISION STATUS
            # ==========================================================

            decision_status_ok = (
                status
                == self.APPROVED
            )

            checks.append(
                RiskCheck(
                    name="decision_status",
                    passed=(
                        decision_status_ok
                    ),
                    value=status,
                    limit=self.APPROVED,
                    message=(
                        "Authoritative decision "
                        "is APPROVED."
                        if decision_status_ok
                        else
                        "Authoritative decision "
                        "is not APPROVED."
                    ),
                )
            )

            if not decision_status_ok:

                errors.append(
                    "Authoritative decision status "
                    f"is '{status}', not 'APPROVED'."
                )

            # ==========================================================
            # 10.15 MANDATORY CHECK AGGREGATION
            # ==========================================================

            mandatory_pass = all(
                check.passed
                for check
                in checks
                if check.mandatory
            )

            # ==========================================================
            # 10.16 FINAL APPROVAL
            # ==========================================================

            approved = bool(
                mandatory_pass
                and numerical_ok
                and status
                == self.APPROVED
                and not errors
            )

            result_status = (
                self.APPROVED
                if approved
                else self.REJECTED
            )

            # ==========================================================
            # 10.17 COUNTERS
            # ==========================================================

            if approved:

                self.approved_count += (
                    1
                )

            else:

                self.rejected_count += (
                    1
                )

            # ==========================================================
            # 10.18 DIAGNOSTICS
            # ==========================================================

            diagnostics = {

                "phase": (
                    self.PHASE
                ),

                "component": (
                    self.COMPONENT
                ),

                "api_version": (
                    self.API_VERSION
                ),

                "fail_closed": (
                    self.fail_closed
                ),

                "check_count": (
                    len(
                        checks
                    )
                ),

                "failed_check_count": sum(
                    not check.passed
                    for check
                    in checks
                ),

                "risk_budget_diagnostics": (
                    self._risk_budget_diagnostics(
                        risk_budget_result
                    )
                ),

            }

            # ==========================================================
            # 10.19 RESULT
            # ==========================================================

            result = (
                ProductionRiskValidationResult(
                    approved=(
                        approved
                    ),
                    status=(
                        result_status
                    ),
                    decision_id=(
                        decision_id
                    ),
                    regime=(
                        regime
                    ),
                    portfolio_volatility=(
                        volatility_value
                    ),
                    gross_exposure=(
                        gross_value
                    ),
                    net_exposure=(
                        net_value
                    ),
                    risk_budget_compliant=(
                        budget_ok
                    ),
                    volatility_compliant=(
                        volatility_ok
                    ),
                    gross_exposure_compliant=(
                        gross_ok
                    ),
                    net_exposure_compliant=(
                        net_ok
                    ),
                    concentration_compliant=(
                        concentration_ok
                    ),
                    numerical_integrity_compliant=(
                        numerical_ok
                    ),
                    checks=(
                        tuple(
                            checks
                        )
                    ),
                    warnings=(
                        tuple(
                            warnings
                        )
                    ),
                    errors=(
                        tuple(
                            errors
                        )
                    ),
                    diagnostics=(
                        diagnostics
                    ),
                )
            )

            self.last_result = (
                result
            )

            return result

        except (
            RiskValidationConfigurationError
        ):

            self.failed_count += (
                1
            )

            raise

        except Exception as exc:

            self.failed_count += (
                1
            )

            # ----------------------------------------------------------
            # FAIL-CLOSED
            # ----------------------------------------------------------

            if not self.fail_closed:

                raise

            result = (
                ProductionRiskValidationResult(
                    approved=False,
                    status=(
                        self.FAILED
                    ),
                    decision_id=(
                        decision_id
                    ),
                    regime=(
                        regime
                    ),
                    portfolio_volatility=0.0,
                    gross_exposure=0.0,
                    net_exposure=0.0,
                    risk_budget_compliant=False,
                    volatility_compliant=False,
                    gross_exposure_compliant=False,
                    net_exposure_compliant=False,
                    concentration_compliant=False,
                    numerical_integrity_compliant=False,
                    checks=(
                        tuple(
                            checks
                        )
                    ),
                    warnings=(
                        tuple(
                            warnings
                        )
                    ),
                    errors=(
                        tuple(
                            errors
                        )
                        + (
                            str(
                                exc
                            ),
                        )
                    ),
                    diagnostics={
                        "phase": (
                            self.PHASE
                        ),
                        "component": (
                            self.COMPONENT
                        ),
                        "api_version": (
                            self.API_VERSION
                        ),
                        "fail_closed": (
                            self.fail_closed
                        ),
                    },
                )
            )

            self.last_result = (
                result
            )

            return result

    # ==================================================================
    # SECTION 11
    # METADATA
    # ==================================================================

    @property
    def metadata(
        self,
    ) -> dict[str, Any]:
        """
        Return production risk-validation metadata.
        """

        return {

            "module": (
                "productionriskvalidation"
            ),

            "component": (
                self.COMPONENT
            ),

            "api_version": (
                self.API_VERSION
            ),

            "phase": (
                self.PHASE
            ),

            "production_only": (
                True
            ),

            "test_doubles_allowed": (
                False
            ),

            "decision_engine_is_authoritative": (
                True
            ),

            "fail_closed": (
                self.fail_closed
            ),

            "has_result": (
                self.last_result
                is not None
            ),

            "validation_count": (
                self.validation_count
            ),

            "approved_count": (
                self.approved_count
            ),

            "rejected_count": (
                self.rejected_count
            ),

            "failed_count": (
                self.failed_count
            ),

        }

    # ==================================================================
    # SECTION 12
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ) -> bool:
        """
        Verify internal validator health.
        """

        if (
            self.last_result
            is None
        ):

            return True

        if (
            self.last_result.status
            == self.FAILED
        ):

            raise RuntimeError(
                "ProductionRiskValidation "
                "last execution failed."
            )

        if (
            self.last_result.approved
            and self.last_result.errors
        ):

            raise RuntimeError(
                "Validator returned "
                "approved=True with errors."
            )

        return True

    # ==================================================================
    # SECTION 13
    # SUMMARY
    # ==================================================================

    def summary(
        self,
    ) -> dict[str, Any]:
        """
        Return validator execution summary.
        """

        return {

            **self.metadata,

            "last_approved": (
                None
                if self.last_result is None
                else self.last_result.approved
            ),

            "last_status": (
                None
                if self.last_result is None
                else self.last_result.status
            ),

            "last_decision_id": (
                None
                if self.last_result is None
                else self.last_result.decision_id
            ),

        }


# ======================================================================
# SECTION 14
# CONVENIENCE FACTORY
# ======================================================================


def build_production_risk_validation(
    **kwargs: Any,
) -> ProductionRiskValidation:
    """
    Construct the Phase IV-B.4 production risk validator.
    """

    return ProductionRiskValidation(
        **kwargs
    )


# ======================================================================
# SECTION 15
# REGRESSION TESTS
# ======================================================================

# ----------------------------------------------------------------------
# 15.1 DETERMINISTIC REGRESSION DECISION
# ----------------------------------------------------------------------


class _RegressionDecision:
    """
    Internal deterministic regression object.

    This object exists only inside the regression tests.

    It is not injected into the production composition.
    """

    def __init__(
        self,
        *,
        status="APPROVED",
        decision_id="D-001",
        regime="NEUTRAL",
        weights=None,
        volatility=0.10,
        gross_exposure=1.0,
        net_exposure=0.20,
    ):

        self.status = (
            status
        )

        self.decision_id = (
            decision_id
        )

        self.regime = (
            regime
        )

        self.weights = (
            weights
            if weights is not None
            else {
                "SPY": 0.50,
                "TLT": 0.30,
                "GLD": 0.20,
            }
        )

        self.portfolio_volatility = (
            volatility
        )

        self.gross_exposure = (
            gross_exposure
        )

        self.net_exposure = (
            net_exposure
        )


# ----------------------------------------------------------------------
# 15.2 DETERMINISTIC RISK-BUDGET RESULT
# ----------------------------------------------------------------------


class _RegressionRiskBudget:
    """
    Internal deterministic regression risk-budget result.

    This object exists only inside the regression tests.
    """

    def __init__(
        self,
        *,
        within_tolerance=True,
        budget_error=0.0,
    ):

        self.within_tolerance = (
            within_tolerance
        )

        self.budget_error = (
            budget_error
        )

        self.diagnostics = {
            "source": (
                "RiskBudgetEngine"
            )
        }


# ----------------------------------------------------------------------
# 15.3 VALIDATOR FACTORY FOR TESTS
# ----------------------------------------------------------------------


def _regression_validator():
    """
    Construct deterministic regression configuration.
    """

    return ProductionRiskValidation(

        max_portfolio_volatility=(
            0.15
        ),

        max_net_exposure=(
            1.0
        ),

        max_position_weight=(
            0.60
        ),

    )


# ======================================================================
# SECTION 16
# APPROVED DECISION TEST
# ======================================================================


def test_approved_decision() -> None:
    """
    Verify that a fully compliant production decision is approved.
    """

    validator = (
        _regression_validator()
    )

    result = (
        validator.validate(

            _RegressionDecision(),

            risk_budget_result=(
                _RegressionRiskBudget()
            ),

            regime_max_leverage=(
                1.0
            ),

        )
    )

    assert (
        result.approved
        is True
    )

    assert (
        result.status
        == "APPROVED"
    )

    assert (
        result.errors
        == ()
    )


# ======================================================================
# SECTION 17
# LEVERAGE REJECTION TEST
# ======================================================================


def test_rejects_leverage() -> None:
    """
    Verify that excessive gross exposure is rejected.
    """

    validator = (
        _regression_validator()
    )

    result = (
        validator.validate(

            _RegressionDecision(
                gross_exposure=1.20
            ),

            risk_budget_result=(
                _RegressionRiskBudget()
            ),

            regime_max_leverage=(
                1.0
            ),

        )
    )

    assert (
        result.approved
        is False
    )

    assert (
        result.gross_exposure_compliant
        is False
    )


# ======================================================================
# SECTION 18
# RISK-BUDGET REJECTION TEST
# ======================================================================


def test_rejects_budget() -> None:
    """
    Verify that an out-of-tolerance risk budget is rejected.
    """

    validator = (
        _regression_validator()
    )

    result = (
        validator.validate(

            _RegressionDecision(),

            risk_budget_result=(
                _RegressionRiskBudget(
                    within_tolerance=False,
                    budget_error=0.05,
                )
            ),

            regime_max_leverage=(
                1.0
            ),

        )
    )

    assert (
        result.approved
        is False
    )

    assert (
        result.risk_budget_compliant
        is False
    )


# ======================================================================
# SECTION 19
# NON-APPROVED DECISION TEST
# ======================================================================


def test_rejects_non_approved_decision() -> None:
    """
    Verify that a non-approved authoritative decision cannot pass
    Phase IV-B.4.
    """

    validator = (
        _regression_validator()
    )

    result = (
        validator.validate(

            _RegressionDecision(
                status="REJECTED"
            ),

            risk_budget_result=(
                _RegressionRiskBudget()
            ),

            regime_max_leverage=(
                1.0
            ),

        )
    )

    assert (
        result.approved
        is False
    )


# ======================================================================
# SECTION 20
# MISSING RISK-BUDGET TEST
# ======================================================================


def test_fails_closed_on_missing_budget() -> None:
    """
    Verify that missing risk-budget information cannot produce
    approval.
    """

    validator = (
        _regression_validator()
    )

    result = (
        validator.validate(

            _RegressionDecision(),

            risk_budget_result=None,

            regime_max_leverage=(
                1.0
            ),

        )
    )

    assert (
        result.approved
        is False
    )

    assert (
        result.risk_budget_compliant
        is False
    )


# ======================================================================
# SECTION 21
# CONCENTRATION REJECTION TEST
# ======================================================================


def test_rejects_concentration() -> None:
    """
    Verify that excessive individual position concentration is rejected.
    """

    validator = (
        _regression_validator()
    )

    result = (
        validator.validate(

            _RegressionDecision(
                weights={
                    "SPY": 0.80,
                    "TLT": 0.10,
                    "GLD": 0.10,
                }
            ),

            risk_budget_result=(
                _RegressionRiskBudget()
            ),

            regime_max_leverage=(
                1.0
            ),

        )
    )

    assert (
        result.approved
        is False
    )

    assert (
        result.concentration_compliant
        is False
    )


# ======================================================================
# SECTION 22
# HEALTH AND METADATA TEST
# ======================================================================


def test_health_and_metadata() -> None:
    """
    Verify the production validator health and metadata contracts.
    """

    validator = (
        _regression_validator()
    )

    validator.validate(

        _RegressionDecision(),

        risk_budget_result=(
            _RegressionRiskBudget()
        ),

        regime_max_leverage=(
            1.0
        ),

    )

    assert (
        validator.health_check()
        is True
    )

    metadata = (
        validator.metadata
    )

    assert (
        metadata["api_version"]
        == "1.0.0"
    )

    assert (
        metadata["phase"]
        == "IV-B.4"
    )

    assert (
        metadata["production_only"]
        is True
    )

    assert (
        metadata["test_doubles_allowed"]
        is False
    )

    assert (
        metadata[
            "decision_engine_is_authoritative"
        ]
        is True
    )


# ======================================================================
# SECTION 23
# REGRESSION TEST ENTRY POINT
# ======================================================================


def run_regression_tests() -> None:
    """
    Run all Phase IV-B.4 regression tests.
    """

    test_approved_decision()

    test_rejects_leverage()

    test_rejects_budget()

    test_rejects_non_approved_decision()

    test_fails_closed_on_missing_budget()

    test_rejects_concentration()

    test_health_and_metadata()

    print(
        "ProductionRiskValidation "
        "Phase IV-B.4 tests passed."
    )


# ======================================================================
# SECTION 24
# MODULE ENTRY POINT
# ======================================================================


if __name__ == "__main__":

    print(
        "============================================================"
    )

    print(
        "PHASE IV-B.4 PRODUCTION RISK VALIDATION"
    )

    print(
        "============================================================"
    )

    validator = (
        ProductionRiskValidation()
    )

    print()

    print(
        "METADATA:"
    )

    print(
        validator.metadata
    )

    print()

    print(
        "HEALTH CHECK:"
    )

    try:

        health = (
            validator.health_check()
        )

        print(
            {
                "healthy": health
            }
        )

    except Exception as exc:

        print(
            {
                "healthy": False,
                "error": str(
                    exc
                ),
            }
        )

    print()

    run_regression_tests()