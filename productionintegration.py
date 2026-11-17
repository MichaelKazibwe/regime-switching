# ======================================================================
# PRODUCTION INTEGRATION
# PHASE IV-B.2

# ======================================================================
"""
Production integration boundary for the institutional portfolio stack.
Phase IV-B.2 proves that the production dependency graph assembled by
ProductionComposition can execute an end-to-end portfolio decision.
The production portfolio is based on the registry-qualified universe
defined by AssetUniverse.production().
Design principles
-----------------
1. ProductionComposition owns dependency construction.
2. ProductionIntegration owns integration validation.
3. AssetUniverse owns the canonical production asset universe.
4. PortfolioDecisionEngine owns decision orchestration.
5. PortfolioOptimizer owns portfolio optimization.
6. RiskBudgetEngine owns risk budgeting.
7. No optimization logic is duplicated here.
8. No trading or broker execution occurs in this phase.
9. Test doubles are not permitted at the production boundary.
10. Production inputs must align to the registry-qualified assets.
11. Historical macro series and scalar macro observations are supported.
12. Failures remain explicit and auditable.
"""

# ======================================================================

# SECTION 1
# IMPORTS

# ======================================================================
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import numpy as np
from exceptions import ExecutionError
from assetuniverse import (
    AssetUniverse,
    PRODUCTION_ASSETS as CANONICAL_PRODUCTION_ASSETS,
)

from productioncomposition import (
    ProductionComposition,
    ProductionCompositionError,
)
from portfoliodecisionengine import (
    PortfolioDecision,
    PortfolioDecisionStatus,
)

# Backward-compatible alias; AssetUniverse remains the source of truth.
PRODUCTION_ASSETS = tuple(CANONICAL_PRODUCTION_ASSETS)

# ======================================================================

# SECTION 2
# EXCEPTIONS

# ======================================================================

class ProductionIntegrationError(
    ExecutionError
):
    """
    Raised when the Phase IV-B.2 production integration boundary
    cannot safely execute a portfolio decision.
    """
    pass

# ======================================================================

# SECTION 3
# INTEGRATION RESULT

# ======================================================================

@dataclass(
    frozen=True
)

class ProductionIntegrationResult:
    """
    Immutable result returned by the Phase IV-B.2 integration layer.
    """
    success: bool
    status: str
    approved: bool
    decision: PortfolioDecision | None
    diagnostics: dict[str, Any]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

# ======================================================================

# SECTION 4
# PRODUCTION INTEGRATION ENGINE

# ======================================================================

class ProductionIntegration:
    """
    Production integration boundary for PortfolioDecisionEngine.
    This class does not implement portfolio mathematics.
    It validates:
        AssetUniverse
                |
                v
        Production inputs
                |
                v
        ProductionComposition
                |
                v
        PortfolioDecisionEngine
                |
                v
        PortfolioDecision
    The canonical production universe contains the registered qualified assets.
    """
    # ------------------------------------------------------------------
    # 4.1 API METADATA
    # ------------------------------------------------------------------
    API_VERSION = (
        "1.0.0"
    )
    PHASE = (
        "IV-B.2"
    )
    # ------------------------------------------------------------------
    # 4.2 CANONICAL PRODUCTION ASSETS
    # ------------------------------------------------------------------
    PRODUCTION_ASSETS = tuple(CANONICAL_PRODUCTION_ASSETS)
    PRODUCTION_ASSET_COUNT = (
        len(PRODUCTION_ASSETS)
    )
    # ------------------------------------------------------------------
    # 4.3 REQUIRED ENGINE COMPONENTS
    # ------------------------------------------------------------------
    REQUIRED_COMPONENTS = (
        "asset_universe",
        "regime_model",
        "expected_return_forecaster",
        "covariance_engine",
        "regime_covariance",
        "ensemble_covariance",
        "black_litterman",
        "optimizer",
        "constraints",
        "risk_model",
        "risk_contribution_analyzer",
        "scenario_engine",
    )

    # ==================================================================
    # 4.4 CONSTRUCTOR

    # ==================================================================

    def __init__(
        self,
        *,
        composition: (
            ProductionComposition
            | None
        ) = None,
    ) -> None:
        """
        Initialize the production integration boundary.
        Parameters
        ----------
        composition:
            Optional ProductionComposition instance.
            If omitted, a real production composition is constructed.
        """
        self.composition = (
            composition
            if composition is not None
            else ProductionComposition()
        )
        self.engine: Any = None
        self.last_result: (
            ProductionIntegrationResult
            | None
        ) = None
        self.execution_count = 0
        self.success_count = 0
        self.failure_count = 0

    # ==================================================================

    # SECTION 5
    # CANONICAL UNIVERSE VALIDATION

    # ==================================================================

    @classmethod

    def _canonical_asset_set(
        cls,
    ) -> set[str]:
        return set(
            cls.PRODUCTION_ASSETS
        )

    @classmethod

    def _validate_canonical_universe(
        cls,
        universe: Any,
    ) -> None:
        """
        Validate that the supplied AssetUniverse is the canonical
        registry-qualified production universe.
        """
        if universe is None:
            raise ProductionIntegrationError(
                "Production asset universe cannot be None."
            )
        if not hasattr(
            universe,
            "tickers",
        ):
            raise ProductionIntegrationError(
                (
                    "Production asset universe must expose "
                    "a tickers property."
                )
            )
        tickers = list(
            universe.tickers
        )
        if len(tickers) != (
            cls.PRODUCTION_ASSET_COUNT
        ):
            raise ProductionIntegrationError(
                (
                    "Production asset universe must contain "
                    f"exactly {cls.PRODUCTION_ASSET_COUNT} assets. "
                    f"Got {len(tickers)}."
                )
            )
        expected = (
            cls._canonical_asset_set()
        )
        actual = set(
            tickers
        )
        if actual != expected:
            missing = sorted(
                expected - actual
            )
            unexpected = sorted(
                actual - expected
            )
            raise ProductionIntegrationError(
                (
                    "Production asset universe does not match "
                    "the registry-qualified universe. "
                    f"Missing: {missing}; "
                    f"Unexpected: {unexpected}."
                )
            )
        if len(
            actual
        ) != len(tickers):
            raise ProductionIntegrationError(
                "Production asset universe contains duplicate tickers."
            )

    # ==================================================================

    # SECTION 6
    # ENGINE CONSTRUCTION

    # ==================================================================

    def _build_engine(
        self,
    ) -> Any:
        """
        Construct the production decision engine.
        """
        if self.engine is not None:
            return self.engine
        try:
            engine = (
                self.composition.build_engine()
            )
        except ProductionCompositionError as exc:
            raise ProductionIntegrationError(
                (
                    "Unable to construct the Phase IV-B.2 "
                    "production decision engine: "
                    f"{exc}"
                )
            ) from exc
        if engine is None:
            raise ProductionIntegrationError(
                "ProductionComposition returned None."
            )
        self._validate_canonical_universe(
            getattr(
                engine,
                "asset_universe",
                None,
            )
        )
        self.engine = engine
        return engine

    # ==================================================================

    # SECTION 7
    # DEPENDENCY VALIDATION

    # ==================================================================

    def _validate_dependencies(
        self,
        engine: Any,
    ) -> None:
        """
        Validate the complete production dependency graph.
        """
        if engine is None:
            raise ProductionIntegrationError(
                "Production decision engine cannot be None."
            )
        missing: list[str] = []
        for name in (
            self.REQUIRED_COMPONENTS
        ):
            component = getattr(
                engine,
                name,
                None,
            )
            if component is None:
                missing.append(
                    name
                )
        if missing:
            raise ProductionIntegrationError(
                (
                    "Production dependency validation failed. "
                    "Missing components: "
                    + ", ".join(
                        missing
                    )
                )
            )
        # --------------------------------------------------------------
        # ASSET UNIVERSE
        # --------------------------------------------------------------
        self._validate_canonical_universe(
            engine.asset_universe
        )
        # --------------------------------------------------------------
        # OPTIMIZER
        # --------------------------------------------------------------
        optimizer = getattr(
            engine,
            "optimizer",
            None,
        )
        if optimizer is None:
            raise ProductionIntegrationError(
                "PortfolioOptimizer is unavailable."
            )
        # --------------------------------------------------------------
        # RISK BUDGET ENGINE
        # --------------------------------------------------------------
        risk_budget_engine = getattr(
            optimizer,
            "risk_budget_engine",
            None,
        )
        if risk_budget_engine is None:
            raise ProductionIntegrationError(
                (
                    "PortfolioOptimizer does not contain a "
                    "production risk_budget_engine."
                )
            )
        # --------------------------------------------------------------
        # OPTIMIZER CONSTRAINTS
        # --------------------------------------------------------------
        if getattr(
            optimizer,
            "constraints",
            None,
        ) is None:
            raise ProductionIntegrationError(
                (
                    "PortfolioOptimizer does not contain "
                    "production constraints."
                )
            )
        # --------------------------------------------------------------
        # VOLATILITY TARGETING
        # --------------------------------------------------------------
        if getattr(
            optimizer,
            "volatility_targeting",
            None,
        ) is None:
            raise ProductionIntegrationError(
                (
                    "PortfolioOptimizer does not contain "
                    "production volatility targeting."
                )
            )

    # ==================================================================

    # SECTION 8
    # INPUT VALIDATION

    # ==================================================================
    # ------------------------------------------------------------------
    # 8.1 PORTFOLIO EXTRACTION
    # ------------------------------------------------------------------

    @classmethod

    def _extract_portfolio_weights(
        cls,
        portfolio: Any,
    ) -> dict[str, Any]:
        """
        Extract ticker weights from the supported production portfolio
        structure.
        Supported form:
            {
                "weights": {
                    "SPY": ...,
                    ...
                }
            }
        A direct ticker-to-weight dictionary is also accepted for
        compatibility with the underlying decision engine.
        """
        if portfolio is None:
            raise ProductionIntegrationError(
                "Portfolio input cannot be None."
            )
        if not isinstance(
            portfolio,
            dict,
        ):
            raise ProductionIntegrationError(
                (
                    "Portfolio input must be a dictionary."
                )
            )
        if "weights" in portfolio:
            weights = portfolio.get(
                "weights"
            )
            if not isinstance(
                weights,
                dict,
            ):
                raise ProductionIntegrationError(
                    (
                        "Portfolio 'weights' field must "
                        "be a dictionary."
                    )
                )
            return dict(
                weights
            )
        return dict(
            portfolio
        )
    # ------------------------------------------------------------------
    # 8.2 PORTFOLIO
    # ------------------------------------------------------------------

    @classmethod

    def _validate_portfolio(
        cls,
        portfolio: Any,
    ) -> None:
        """
        Validate the production portfolio against the canonical
        14-asset universe.
        """
        weights = (
            cls._extract_portfolio_weights(
                portfolio
            )
        )
        if not weights:
            raise ProductionIntegrationError(
                "Portfolio input cannot be empty."
            )
        expected = (
            cls._canonical_asset_set()
        )
        actual = set(
            weights.keys()
        )
        if actual != expected:
            missing = sorted(
                expected - actual
            )
            unexpected = sorted(
                actual - expected
            )
            raise ProductionIntegrationError(
                (
                    "Portfolio must contain exactly the "
                    "registry-qualified assets. "
                    f"Missing: {missing}; "
                    f"Unexpected: {unexpected}."
                )
            )
        for ticker, weight in (
            weights.items()
        ):
            if not isinstance(
                ticker,
                str,
            ):
                raise ProductionIntegrationError(
                    "Portfolio ticker names must be strings."
                )
            try:
                numeric_weight = float(
                    weight
                )
            except (
                TypeError,
                ValueError,
            ) as exc:
                raise ProductionIntegrationError(
                    (
                        f"Invalid portfolio weight for "
                        f"'{ticker}': {weight}"
                    )
                ) from exc
            if not np.isfinite(
                numeric_weight
            ):
                raise ProductionIntegrationError(
                    (
                        f"Portfolio weight for "
                        f"'{ticker}' must be finite."
                    )
                )
            if numeric_weight < 0.0:
                raise ProductionIntegrationError(
                    (
                        f"Portfolio weight for "
                        f"'{ticker}' cannot be negative "
                        "in the production long-only contract."
                    )
                )
        total = sum(
            float(weight)
            for weight in weights.values()
        )
        if not np.isclose(
            total,
            1.0,
            atol=1e-8,
            rtol=0.0,
        ):
            raise ProductionIntegrationError(
                (
                    "Portfolio weights must sum to one. "
                    f"Got {total}."
                )
            )
    # ------------------------------------------------------------------
    # 8.3 RETURNS
    # ------------------------------------------------------------------

    @classmethod

    def _validate_returns(
        cls,
        returns: Any,
    ) -> None:
        """
        Validate production return/price history.
        The production decision engine may receive either return history
        or price history, but the input must contain exactly the
        registry-qualified assets.
        """
        if returns is None:
            raise ProductionIntegrationError(
                "Returns input cannot be None."
            )
        if not hasattr(
            returns,
            "columns",
        ):
            raise ProductionIntegrationError(
                (
                    "Returns input must expose "
                    "a columns attribute."
                )
            )
        columns = list(
            returns.columns
        )
        if not columns:
            raise ProductionIntegrationError(
                "Returns input contains no assets."
            )
        expected = (
            cls._canonical_asset_set()
        )
        actual = set(
            columns
        )
        if len(columns) != (
            cls.PRODUCTION_ASSET_COUNT
        ):
            raise ProductionIntegrationError(
                (
                    "Production return history must contain "
                    f"exactly {cls.PRODUCTION_ASSET_COUNT} assets. "
                    f"Got {len(columns)}."
                )
            )
        if actual != expected:
            missing = sorted(
                expected - actual
            )
            unexpected = sorted(
                actual - expected
            )
            raise ProductionIntegrationError(
                (
                    "Production return history does not match "
                    "the registry-qualified universe. "
                    f"Missing: {missing}; "
                    f"Unexpected: {unexpected}."
                )
            )
        if hasattr(
            returns,
            "empty",
        ) and returns.empty:
            raise ProductionIntegrationError(
                "Returns input cannot be empty."
            )
        # --------------------------------------------------------------
        # NUMERIC / FINITE CHECK
        # --------------------------------------------------------------
        try:
            values = np.asarray(
                returns.to_numpy(),
                dtype=float,
            )
        except Exception as exc:
            raise ProductionIntegrationError(
                (
                    "Returns input contains "
                    "non-numeric values."
                )
            ) from exc
        if values.size == 0:
            raise ProductionIntegrationError(
                "Returns input contains no observations."
            )
        if not np.isfinite(
            values
        ).all():
            raise ProductionIntegrationError(
                "Returns input contains non-finite values."
            )
    # ------------------------------------------------------------------
    # 8.4 PRICES
    # ------------------------------------------------------------------

    @classmethod

    def _validate_prices(cls, prices: Any) -> None:
        """Validate positive, finite price history for the canonical universe."""
        if prices is None or not hasattr(prices, "columns"):
            raise ProductionIntegrationError(
                "Price history must be a DataFrame-like object with columns."
            )
        columns = list(prices.columns)
        expected = cls._canonical_asset_set()
        if len(columns) != cls.PRODUCTION_ASSET_COUNT or set(columns) != expected:
            missing = sorted(expected - set(columns))
            unexpected = sorted(set(columns) - expected)
            raise ProductionIntegrationError(
                "Price history must match the registry-qualified universe. "
                f"Missing: {missing}; Unexpected: {unexpected}."
            )
        if getattr(prices, "empty", False):
            raise ProductionIntegrationError("Price history cannot be empty.")
        try:
            values = np.asarray(prices.to_numpy(), dtype=float)
        except Exception as exc:
            raise ProductionIntegrationError("Price history contains non-numeric values.") from exc
        if values.size == 0 or not np.isfinite(values).all():
            raise ProductionIntegrationError("Price history contains no data or non-finite values.")
        if (values <= 0.0).any():
            raise ProductionIntegrationError("Price history must contain strictly positive prices.")
    # ------------------------------------------------------------------
    # 8.5 REGIMES
    # ------------------------------------------------------------------

    @staticmethod

    def _validate_regimes(
        regimes: Any,
    ) -> None:
        """
        Validate regime information.
        Supports pandas Series, arrays, lists and other sized
        historical regime containers.
        """
        if regimes is None:
            raise ProductionIntegrationError(
                "Regime information cannot be None."
            )
        try:
            length = len(
                regimes
            )
        except TypeError as exc:
            raise ProductionIntegrationError(
                (
                    "Regime information must be "
                    "a non-empty historical container."
                )
            ) from exc
        if length == 0:
            raise ProductionIntegrationError(
                "Regime information cannot be empty."
            )
        # --------------------------------------------------------------
        # FINITE / NULL-LIKE VALIDATION
        # --------------------------------------------------------------
        if hasattr(
            regimes,
            "isna",
        ):
            try:
                missing = regimes.isna()
                if bool(
                    missing.any()
                ):
                    raise ProductionIntegrationError(
                        "Regime information contains missing values."
                    )
            except ProductionIntegrationError:
                raise
            except Exception as exc:
                raise ProductionIntegrationError("Unable to validate regime missing-value status") from exc
    # ------------------------------------------------------------------
    # 8.5 MACRO SERIES VALIDATION
    # ------------------------------------------------------------------

    @staticmethod

    def _validate_macro_series(
        value: Any,
        field_name: str,
    ) -> None:
        """
        Validate a historical numeric macroeconomic series.
        """
        if value is None:
            raise ProductionIntegrationError(
                (
                    f"Macro data '{field_name}' "
                    "cannot be None."
                )
            )
        # --------------------------------------------------------------
        # SCALAR
        # --------------------------------------------------------------
        if np.isscalar(
            value
        ):
            try:
                numeric_value = float(
                    value
                )
            except (
                TypeError,
                ValueError,
            ) as exc:
                raise ProductionIntegrationError(
                    (
                        f"Macro data '{field_name}' "
                        "must be numeric."
                    )
                ) from exc
            if not np.isfinite(
                numeric_value
            ):
                raise ProductionIntegrationError(
                    (
                        f"Macro data '{field_name}' "
                        "must be finite."
                    )
                )
            return
        # --------------------------------------------------------------
        # HISTORICAL SERIES / ARRAY
        # --------------------------------------------------------------
        try:
            length = len(
                value
            )
        except TypeError as exc:
            raise ProductionIntegrationError(
                (
                    f"Macro data '{field_name}' must be "
                    "numeric or a historical numeric series."
                )
            ) from exc
        if length == 0:
            raise ProductionIntegrationError(
                (
                    f"Macro data '{field_name}' "
                    "cannot be empty."
                )
            )
        try:
            numeric_values = np.asarray(
                value,
                dtype=float,
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ProductionIntegrationError(
                (
                    f"Macro data '{field_name}' "
                    "must contain numeric values."
                )
            ) from exc
        if numeric_values.size == 0:
            raise ProductionIntegrationError(
                (
                    f"Macro data '{field_name}' "
                    "cannot be empty."
                )
            )
        if not np.isfinite(
            numeric_values
        ).all():
            raise ProductionIntegrationError(
                (
                    f"Macro data '{field_name}' "
                    "contains non-finite values."
                )
            )
    # ------------------------------------------------------------------
    # 8.6 MACRO DATA
    # ------------------------------------------------------------------

    @classmethod

    def _validate_macro_data(
        cls,
        macro_data: Any,
    ) -> None:
        """
        Validate macroeconomic input required by MacroRegimeModel.
        Required fields
        ---------------
        unemployment:
            Historical unemployment series or scalar observation.
        yield_spread:
            Historical yield-curve spread series or scalar observation.
        inflation:
            Historical inflation series or scalar observation.
        """
        if macro_data is None:
            raise ProductionIntegrationError(
                "Macro data cannot be None."
            )
        if not isinstance(
            macro_data,
            dict,
        ):
            raise ProductionIntegrationError(
                "Macro data must be a dictionary."
            )
        required = (
            "unemployment",
            "yield_spread",
            "inflation",
        )
        missing = [
            key
            for key in required
            if key not in macro_data
        ]
        if missing:
            raise ProductionIntegrationError(
                (
                    "Macro data is missing required fields: "
                    + ", ".join(
                        missing
                    )
                    + "."
                )
            )
        for field_name in required:
            cls._validate_macro_series(
                macro_data[field_name],
                field_name,
            )

    # ==================================================================

    # SECTION 9
    # DECISION VALIDATION

    # ==================================================================

    @classmethod

    def _validate_decision(
        cls,
        decision: PortfolioDecision,
    ) -> None:
        """
        Validate a PortfolioDecision returned by the production engine.
        """
        if decision is None:
            raise ProductionIntegrationError(
                "PortfolioDecisionEngine returned None."
            )
        if not isinstance(
            decision,
            PortfolioDecision,
        ):
            raise ProductionIntegrationError(
                (
                    "PortfolioDecisionEngine returned an "
                    f"unexpected object type: "
                    f"{type(decision).__name__}"
                )
            )
        if not decision.decision_id:
            raise ProductionIntegrationError(
                "Decision does not contain a decision_id."
            )
        # --------------------------------------------------------------
        # APPROVED DECISION
        # --------------------------------------------------------------
        if (
            decision.status
            == PortfolioDecisionStatus.APPROVED.value
        ):
            if not decision.approved:
                raise ProductionIntegrationError(
                    (
                        "Decision status is APPROVED but "
                        "approved=False."
                    )
                )
            if decision.regime is None:
                raise ProductionIntegrationError(
                    "Approved decision has no regime."
                )
            if not decision.tickers:
                raise ProductionIntegrationError(
                    "Approved decision contains no tickers."
                )
            if not decision.weights:
                raise ProductionIntegrationError(
                    "Approved decision contains no weights."
                )
            # ----------------------------------------------------------
            # TICKER INTEGRITY
            # ----------------------------------------------------------
            actual_tickers = set(
                decision.tickers
            )
            expected_tickers = (
                cls._canonical_asset_set()
            )
            if actual_tickers != expected_tickers:
                missing = sorted(
                    expected_tickers
                    - actual_tickers
                )
                unexpected = sorted(
                    actual_tickers
                    - expected_tickers
                )
                raise ProductionIntegrationError(
                    (
                        "Approved decision does not contain "
                        "the registry-qualified assets. "
                        f"Missing: {missing}; "
                        f"Unexpected: {unexpected}."
                    )
                )
            # ----------------------------------------------------------
            # WEIGHT INTEGRITY
            # ----------------------------------------------------------
            if set(
                decision.weights.keys()
            ) != expected_tickers:
                raise ProductionIntegrationError(
                    (
                        "Approved decision weights do not "
                        "cover the registry-qualified assets."
                    )
                )
            weight_total = sum(
                float(value)
                for value in decision.weights.values()
            )
            if not np.isfinite(
                weight_total
            ):
                raise ProductionIntegrationError(
                    "Approved decision weight total is non-finite."
                )
            # The input portfolio must be fully invested, but the decision
            # may intentionally hold residual cash after a risk-governor REDUCE.
            if weight_total <= 0.0 or weight_total > 1.0 + 1e-6:
                raise ProductionIntegrationError(
                    "Approved decision total exposure must be in (0, 1]. "
                    f"Got {weight_total}."
                )
            for ticker, weight in (
                decision.weights.items()
            ):
                numeric_weight = float(
                    weight
                )
                if not np.isfinite(
                    numeric_weight
                ):
                    raise ProductionIntegrationError(
                        (
                            f"Approved decision weight "
                            f"for '{ticker}' is non-finite."
                        )
                    )
                if numeric_weight < -1e-10:
                    raise ProductionIntegrationError(
                        (
                            f"Approved decision weight "
                            f"for '{ticker}' is negative."
                        )
                    )
        # --------------------------------------------------------------
        # REJECTED DECISION
        # --------------------------------------------------------------
        elif (
            decision.status
            == PortfolioDecisionStatus.REJECTED.value
        ):
            if decision.approved:
                raise ProductionIntegrationError(
                    (
                        "Decision status is REJECTED but "
                        "approved=True."
                    )
                )
        # --------------------------------------------------------------
        # FAILED DECISION
        # --------------------------------------------------------------
        elif (
            decision.status
            == PortfolioDecisionStatus.FAILED.value
        ):
            if decision.approved:
                raise ProductionIntegrationError(
                    (
                        "Decision status is FAILED but "
                        "approved=True."
                    )
                )
            if not decision.errors:
                raise ProductionIntegrationError(
                    (
                        "FAILED decision contains no "
                        "diagnostic errors."
                    )
                )
        # --------------------------------------------------------------
        # UNKNOWN STATUS
        # --------------------------------------------------------------
        else:
            raise ProductionIntegrationError(
                (
                    "PortfolioDecisionEngine returned "
                    f"unsupported decision status: "
                    f"{decision.status}"
                )
            )

    # ==================================================================

    # SECTION 10
    # PRODUCTION DECISION EXECUTION

    # ==================================================================

    def run(
        self,
        *,
        portfolio: dict[str, Any],
        returns: Any,
        regimes: Any,
        macro_data: dict[str, Any],
        prices: Any = None,
        scenarios: Any = None,
    ) -> ProductionIntegrationResult:
        """
        Execute one production portfolio decision.
        """
        self.execution_count += 1
        try:
            # ----------------------------------------------------------
            # INPUT VALIDATION
            # ----------------------------------------------------------
            self._validate_portfolio(
                portfolio
            )
            self._validate_returns(
                returns
            )
            self._validate_prices(prices)
            self._validate_regimes(
                regimes
            )
            self._validate_macro_data(
                macro_data
            )
            # ----------------------------------------------------------
            # ENGINE
            # ----------------------------------------------------------
            engine = (
                self._build_engine()
            )
            # ----------------------------------------------------------
            # DEPENDENCY VALIDATION
            # ----------------------------------------------------------
            self._validate_dependencies(
                engine
            )
            # ----------------------------------------------------------
            # DECISION
            # ----------------------------------------------------------
            decision = (
                engine.decide(
                    portfolio=portfolio,
                    returns=returns,
                    prices=prices,
                    regimes=regimes,
                    macro_data=macro_data,
                    scenarios=scenarios,
                )
            )
            # ----------------------------------------------------------
            # RESULT VALIDATION
            # ----------------------------------------------------------
            self._validate_decision(
                decision
            )
            decision_failed = (
                decision.status
                == PortfolioDecisionStatus.FAILED.value
            )
            if decision_failed:
                self.failure_count += 1
            else:
                self.success_count += 1
            result = (
                ProductionIntegrationResult(
                    success=not decision_failed,
                    status=decision.status,
                    approved=bool(
                        decision.approved
                    ),
                    decision=decision,
                    diagnostics=dict(
                        decision.diagnostics
                    ),
                    errors=tuple(
                        decision.errors
                    ),
                    warnings=tuple(
                        decision.warnings
                    ),
                )
            )
            self.last_result = result
            return result
        except Exception as exc:
            self.failure_count += 1
            result = (
                ProductionIntegrationResult(
                    success=False,
                    status=(
                        PortfolioDecisionStatus.FAILED.value
                    ),
                    approved=False,
                    decision=None,
                    diagnostics={
                        "exception_type": (
                            type(exc).__name__
                        ),
                        "production_asset_count": (
                            self.PRODUCTION_ASSET_COUNT
                        ),
                        "production_assets": list(
                            self.PRODUCTION_ASSETS
                        ),
                    },
                    errors=(
                        str(exc),
                    ),
                    warnings=tuple(),
                )
            )
            self.last_result = result
            return result

    # ==================================================================

    # SECTION 11
    # HEALTH CHECK

    # ==================================================================

    def health_check(
        self,
    ) -> dict[str, Any]:
        """
        Return Phase IV-B.2 integration health.
        """
        try:
            engine = (
                self._build_engine()
            )
            self._validate_dependencies(
                engine
            )
            engine_health = (
                engine.health_check()
            )
            healthy = bool(
                engine_health.get(
                    "healthy",
                    False,
                )
            )
            return {
                "api_version": (
                    self.API_VERSION
                ),
                "phase": (
                    self.PHASE
                ),
                "healthy": healthy,
                "production_asset_count": (
                    self.PRODUCTION_ASSET_COUNT
                ),
                "production_assets": list(
                    self.PRODUCTION_ASSETS
                ),
                "engine_health": (
                    engine_health
                ),
            }
        except Exception as exc:
            return {
                "api_version": (
                    self.API_VERSION
                ),
                "phase": (
                    self.PHASE
                ),
                "healthy": False,
                "production_asset_count": (
                    self.PRODUCTION_ASSET_COUNT
                ),
                "production_assets": list(
                    self.PRODUCTION_ASSETS
                ),
                "error": str(
                    exc
                ),
            }

    # ==================================================================

    # SECTION 12
    # METADATA

    # ==================================================================

    def metadata(
        self,
    ) -> dict[str, Any]:
        """
        Return Phase IV-B.2 integration metadata.
        """
        return {
            "module": (
                "productionintegration"
            ),
            "component": (
                "ProductionIntegration"
            ),
            "api_version": (
                self.API_VERSION
            ),
            "phase": (
                self.PHASE
            ),
            "production_only": True,
            "test_doubles_allowed": False,
            "live_trading_enabled": False,
            "strict_dependency_validation": True,
            "fail_fast_dependency_validation": True,
            "canonical_production_universe": True,
            "production_asset_count": (
                self.PRODUCTION_ASSET_COUNT
            ),
            "production_assets": list(
                self.PRODUCTION_ASSETS
            ),
            "required_components": list(
                self.REQUIRED_COMPONENTS
            ),
        }

    # ==================================================================

    # SECTION 13
    # SUMMARY

    # ==================================================================

    def summary(
        self,
    ) -> dict[str, Any]:
        """
        Return integration execution statistics.
        """
        last = self.last_result
        return {
            "api_version": (
                self.API_VERSION
            ),
            "phase": (
                self.PHASE
            ),
            "production_asset_count": (
                self.PRODUCTION_ASSET_COUNT
            ),
            "production_assets": list(
                self.PRODUCTION_ASSETS
            ),
            "execution_count": (
                self.execution_count
            ),
            "success_count": (
                self.success_count
            ),
            "failure_count": (
                self.failure_count
            ),
            "last_status": (
                None
                if last is None
                else last.status
            ),
            "last_success": (
                None
                if last is None
                else last.success
            ),
            "last_approved": (
                None
                if last is None
                else last.approved
            ),
        }

# ======================================================================

# SECTION 14
# CONVENIENCE FACTORY

# ======================================================================

def build_production_integration(
) -> ProductionIntegration:
    """
    Construct the Phase IV-B.2 production integration boundary.
    """
    return ProductionIntegration()

# ======================================================================

# SECTION 15
# REGRESSION TESTS

# ======================================================================

def test_production_integration_metadata() -> None:
    """
    Verify Phase IV-B.2 metadata and the canonical production universe.
    """
    integration = (
        ProductionIntegration()
    )
    metadata = (
        integration.metadata()
    )
    assert (
        metadata["api_version"]
        == "1.0.0"
    )
    assert (
        metadata["phase"]
        == "IV-B.2"
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
        metadata["live_trading_enabled"]
        is False
    )
    assert (
        metadata["canonical_production_universe"]
        is True
    )
    assert (
        metadata["production_asset_count"]
        == len(PRODUCTION_ASSETS)
    )
    assert (
        metadata["production_assets"]
        == list(
            ProductionIntegration.PRODUCTION_ASSETS
        )
    )

def test_production_integration_health() -> None:
    """
    Verify the deterministic health-check interface.
    """
    integration = (
        ProductionIntegration()
    )
    result = (
        integration.health_check()
    )
    assert isinstance(
        result,
        dict,
    )
    assert (
        result["api_version"]
        == "1.0.0"
    )
    assert (
        result["phase"]
        == "IV-B.2"
    )
    assert (
        "healthy"
        in result
    )
    assert (
        result["production_asset_count"]
        == len(PRODUCTION_ASSETS)
    )
    assert (
        result["production_assets"]
        == list(
            ProductionIntegration.PRODUCTION_ASSETS
        )
    )

def test_production_integration_summary() -> None:
    """
    Verify initial integration statistics.
    """
    integration = (
        ProductionIntegration()
    )
    summary = (
        integration.summary()
    )
    assert (
        summary["execution_count"]
        == 0
    )
    assert (
        summary["success_count"]
        == 0
    )
    assert (
        summary["failure_count"]
        == 0
    )
    assert (
        summary["production_asset_count"]
        == len(PRODUCTION_ASSETS)
    )

def test_production_integration_portfolio_validation() -> None:
    """
    Verify the registry-qualified portfolio contract.
    """
    weight = (
        1.0
        / ProductionIntegration.PRODUCTION_ASSET_COUNT
    )
    portfolio = {
        "weights": {
            ticker: weight
            for ticker in (
                ProductionIntegration.PRODUCTION_ASSETS
            )
        }
    }
    ProductionIntegration._validate_portfolio(
        portfolio
    )

def test_production_integration_macro_series_validation() -> None:
    """
    Verify that scalar and historical macro inputs are accepted.
    """
    import pandas as pd
    index = pd.date_range(
        start="2020-01-01",
        periods=10,
        freq="B",
    )
    macro_data = {
        "unemployment": pd.Series(
            np.full(
                len(index),
                5.0,
            ),
            index=index,
        ),
        "yield_spread": pd.Series(
            np.full(
                len(index),
                1.5,
            ),
            index=index,
        ),
        "inflation": pd.Series(
            np.full(
                len(index),
                2.0,
            ),
            index=index,
        ),
    }
    ProductionIntegration._validate_macro_data(
        macro_data
    )
    ProductionIntegration._validate_macro_data(
        {
            "unemployment": 5.0,
            "yield_spread": 1.5,
            "inflation": 2.0,
        }
    )

def test_production_integration_price_validation() -> None:
    """Reject malformed prices and accept finite positive canonical prices."""
    import pandas as pd
    tickers = ProductionIntegration.PRODUCTION_ASSETS
    valid = pd.DataFrame(
        np.full((252, len(tickers)), 100.0, dtype=float),
        columns=tickers,
    )
    ProductionIntegration._validate_prices(valid)
    invalid = valid.copy()
    invalid.iloc[0, 0] = 0.0
    try:
        ProductionIntegration._validate_prices(invalid)
    except ProductionIntegrationError:
        pass
    else:
        raise AssertionError("Non-positive prices must be rejected.")

def test_production_integration_accepts_risk_reduced_decision() -> None:
    """A risk-governor reduction may legitimately leave residual cash."""
    tickers = tuple(ProductionIntegration.PRODUCTION_ASSETS)
    weights = {ticker: 0.5 / len(tickers) for ticker in tickers}
    decision = PortfolioDecision(
        decision_id="PDEC-TEST-REDUCE",
        status=PortfolioDecisionStatus.APPROVED.value,
        approved=True,
        regime="EXPANSION",
        tickers=tickers,
        weights=weights,
        expected_returns={ticker: 0.01 for ticker in tickers},
        covariance={ticker: {other: 0.0 for other in tickers} for ticker in tickers},
        portfolio_return=0.005,
        portfolio_volatility=0.01,
        portfolio_variance=0.0001,
        gross_exposure=0.5,
        net_exposure=0.5,
        number_of_positions=len(tickers),
        risk_contributions={ticker: 0.0 for ticker in tickers},
        risk_contribution_pct={ticker: 0.0 for ticker in tickers},
        scenario_results={"BASE": {"portfolio_return": 0.005}},
        diagnostics={"risk_governance_action": "REDUCE"},
        warnings=tuple(),
        errors=tuple(),
        timestamp="2026-10-23T00:00:00+00:00",
        api_version="1.0.0",
    )
    ProductionIntegration._validate_decision(decision)


def test_production_integration_regime_validation() -> None:
    """
    Verify that pandas regime histories are validated without
    ambiguous truth-value evaluation.
    """
    import pandas as pd
    regimes = pd.Series(
        [
            "EXPANSION",
            "EXPANSION",
            "EXPANSION",
        ]
    )
    ProductionIntegration._validate_regimes(
        regimes
    )

def test_production_integration_universe_validation() -> None:
    """
    Verify that the actual AssetUniverse.production() object is
    accepted as the canonical production universe.
    """
    universe = (
        AssetUniverse.production()
    )
    ProductionIntegration._validate_canonical_universe(
        universe
    )
    assert (
        universe.tickers
        == sorted(
            CANONICAL_PRODUCTION_ASSETS
        )
    )
    assert (
        universe.size
        == len(PRODUCTION_ASSETS)
    )

# ======================================================================

# SECTION 16
# REGRESSION ENTRY POINT

# ======================================================================

def run_regression_tests() -> None:
    """
    Run Phase IV-B.2 regression tests.
    """
    test_production_integration_metadata()
    test_production_integration_health()
    test_production_integration_summary()
    test_production_integration_portfolio_validation()
    test_production_integration_macro_series_validation()
    test_production_integration_regime_validation()
    test_production_integration_universe_validation()
    print(
        "ProductionIntegration Phase IV-B.2 tests passed."
    )

# ======================================================================

# SECTION 17
# MODULE ENTRY POINT

# ======================================================================
if __name__ == "__main__":
    print(
        "============================================================"
    )
    print(
        "PHASE IV-B.2 PRODUCTION INTEGRATION"
    )
    print(
        "============================================================"
    )
    integration = (
        ProductionIntegration()
    )
    print()
    print(
        "METADATA:"
    )
    print(
        integration.metadata()
    )
    print()
    print(
        "CANONICAL PRODUCTION ASSETS:"
    )
    print(
        list(
            ProductionIntegration.PRODUCTION_ASSETS
        )
    )
    print()
    print(
        "HEALTH CHECK:"
    )
    health = (
        integration.health_check()
    )
    print(
        health
    )
    print()
    if health.get(
        "healthy",
        False,
    ):
        print(
            "STATUS: HEALTHY"
        )
    else:
        print(
            "STATUS: UNHEALTHY"
        )
        print(
            "ERROR:",
            health.get(
                "error",
                "Unknown integration error.",
            ),
        )
    print()
    run_regression_tests()
