# ======================================================================
# PRODUCTION DECISION EXECUTION
# PHASE IV-B.3
# ======================================================================

"""
Production decision execution and regression boundary.

Phase IV-B.3 validates that the real production dependency graph
assembled by ProductionComposition and exposed through
ProductionIntegration can execute an end-to-end portfolio decision.

Design principles
-----------------
1. Real production components only.
2. No test doubles.
3. Deterministic regression data.
4. No duplicated portfolio mathematics.
5. PortfolioDecisionEngine remains the decision authority.
6. ProductionIntegration remains the integration boundary.
7. AssetUniverse remains the canonical source of production tickers.
8. Failed and rejected decisions must not be silently treated as
   successful execution.
9. Live trading remains disabled.
10. Deterministic macro data satisfies the exact Phase IV-B.2
    ProductionIntegration contract.
11. Decision identity originates from PortfolioDecisionEngine.
12. No decision ID is fabricated by this boundary.
13. Deterministic return history is long enough for the production
    forecasting dependency graph.
14. All production regression inputs use the canonical 14-asset
    production universe.
15. No independent production ticker list is maintained here.
"""

# ======================================================================
# SECTION 1
# IMPORTS
# ======================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from assetuniverse import (
    AssetUniverse,
    PRODUCTION_ASSETS,
)

from productionintegration import (
    ProductionIntegration,
    ProductionIntegrationError,
)

from portfoliodecisionengine import (
    PortfolioDecisionStatus,
)


# ======================================================================
# SECTION 2
# EXCEPTIONS
# ======================================================================


class ProductionDecisionExecutionError(RuntimeError):
    """
    Raised when Phase IV-B.3 cannot execute or validate a production
    portfolio decision.
    """

    pass


# ======================================================================
# SECTION 3
# EXECUTION RESULT
# ======================================================================


@dataclass(frozen=True)
class ProductionDecisionExecutionResult:
    """
    Immutable representation of one production decision execution.
    """

    success: bool

    status: str

    approved: bool

    decision_id: str | None

    regime: str | None

    weights: dict[str, float]

    portfolio_return: float

    portfolio_variance: float

    portfolio_volatility: float

    gross_exposure: float

    net_exposure: float

    number_of_positions: int

    risk_contributions: dict[str, float]

    risk_contribution_pct: dict[str, float]

    scenario_results: dict[str, Any]

    warnings: tuple[str, ...]

    errors: tuple[str, ...]

    diagnostics: dict[str, Any]

    # Backward-compatible optional field.  Existing IV-D callers may
    # construct this result without supplying tickers, while IV-B.3
    # preserves the upstream PortfolioDecision ticker identity when it
    # is available.
    tickers: tuple[str, ...] = tuple()


# ======================================================================
# SECTION 4
# PRODUCTION DECISION EXECUTION ENGINE
# ======================================================================


class ProductionDecisionExecution:
    """
    Phase IV-B.3 production decision execution boundary.

    This class creates deterministic production inputs and delegates
    all portfolio decision logic to ProductionIntegration.

    IMPORTANT
    ---------
    This class does not generate decision IDs.

    Decision identity originates from PortfolioDecisionEngine and is
    propagated through ProductionIntegration into the execution result.

    IMPORTANT
    ---------
    This class does not maintain an independent production ticker list.

    The canonical production universe is obtained exclusively through:

        AssetUniverse.production()

    and validated against the canonical module-level
    PRODUCTION_ASSETS reference exposed by assetuniverse.
    """

    # ------------------------------------------------------------------
    # 4.1 API METADATA
    # ------------------------------------------------------------------

    API_VERSION = "1.1.0"

    PHASE = "IV-B.3"

    LIVE_TRADING_ENABLED = False

    TEST_DOUBLES_ALLOWED = False

    # ------------------------------------------------------------------
    # 4.2 PRODUCTION UNIVERSE CONTRACT
    # ------------------------------------------------------------------

    @classmethod
    def production_universe(
        cls,
    ) -> AssetUniverse:
        """
        Return the canonical production AssetUniverse.

        No independent ticker list is constructed here.
        """

        try:

            universe = AssetUniverse.production()

        except Exception as exc:

            raise ProductionDecisionExecutionError(
                (
                    "Unable to construct the canonical production "
                    f"asset universe: {exc}"
                )
            ) from exc

        if universe is None:

            raise ProductionDecisionExecutionError(
                "AssetUniverse.production() returned None."
            )

        if not isinstance(
            universe,
            AssetUniverse,
        ):

            raise ProductionDecisionExecutionError(
                (
                    "AssetUniverse.production() returned an "
                    f"unexpected type: {type(universe).__name__}."
                )
            )

        if not getattr(
            universe,
            "is_production_universe",
            False,
        ):

            raise ProductionDecisionExecutionError(
                "AssetUniverse.production() did not return a production universe."
            )

        return universe

    @classmethod
    def production_tickers(
        cls,
    ) -> tuple[str, ...]:
        """
        Return the canonical ordered production ticker tuple.

        AssetUniverse is authoritative for production membership.  The
        AssetUniverse implementation may expose those assets in a
        different deterministic order, so ordering alone is not treated
        as a universe mismatch.

        PRODUCTION_ASSETS remains the canonical deterministic ordering
        used by this production regression boundary.  It is not an
        independently maintained universe: membership is first verified
        against AssetUniverse.production().
        """

        universe = cls.production_universe()

        tickers = tuple(
            universe.production_tickers
            if hasattr(
                universe,
                "production_tickers",
            )
            else universe.tickers
        )

        expected = tuple(
            PRODUCTION_ASSETS
        )

        if len(tickers) != len(expected):

            raise ProductionDecisionExecutionError(
                (
                    "Canonical production universe must contain "
                    f"{len(expected)} assets. Got {len(tickers)}."
                )
            )

        if len(set(tickers)) != len(tickers):

            raise ProductionDecisionExecutionError(
                "Canonical production universe contains duplicate tickers."
            )

        if set(tickers) != set(expected):

            raise ProductionDecisionExecutionError(
                (
                    "Canonical production universe membership mismatch. "
                    f"AssetUniverse returned {sorted(tickers)}, "
                    f"but assetuniverse.PRODUCTION_ASSETS contains "
                    f"{sorted(expected)}."
                )
            )

        return expected

    @classmethod
    def production_asset_count(
        cls,
    ) -> int:
        """
        Return the canonical production asset count.
        """

        return len(
            cls.production_tickers()
        )

    # ------------------------------------------------------------------
    # 4.3 PRODUCTION INPUT CONTRACT
    # ------------------------------------------------------------------

    REQUIRED_MACRO_FIELDS = frozenset(
        {
            "growth",
            "inflation",
            "unemployment",
            "yield_spread",
        }
    )

    HISTORICAL_MACRO_FIELDS = frozenset(
        {
            "unemployment",
        }
    )

    SCALAR_MACRO_FIELDS = frozenset(
        {
            "growth",
            "inflation",
            "yield_spread",
        }
    )

    MINIMUM_RETURN_HISTORY = 252

    DETERMINISTIC_HISTORY_LENGTH = 300

    # ==================================================================
    # 4.4 CONSTRUCTOR
    # ==================================================================

    def __init__(
        self,
        *,
        integration: ProductionIntegration | None = None,
    ) -> None:
        """
        Initialize the production execution boundary.
        """

        self.integration = (
            integration
            if integration is not None
            else ProductionIntegration()
        )

        self.execution_count = 0

        self.success_count = 0

        self.approved_count = 0

        self.rejected_count = 0

        self.failed_count = 0

        self.last_result: (
            ProductionDecisionExecutionResult | None
        ) = None

    # ==================================================================
    # SECTION 5
    # DETERMINISTIC PRODUCTION INPUTS
    # ==================================================================

    # ------------------------------------------------------------------
    # 5.1 PORTFOLIO
    # ------------------------------------------------------------------

    @classmethod
    def build_portfolio(
        cls,
    ) -> dict[str, float]:
        """
        Return a deterministic portfolio containing every canonical
        production asset.

        Equal weights are used deliberately so that the regression
        boundary exercises all 14 production assets without embedding
        portfolio-optimization logic here.
        """

        tickers = cls.production_tickers()

        count = len(tickers)

        if count <= 0:

            raise ProductionDecisionExecutionError(
                "Canonical production universe is empty."
            )

        weight = 1.0 / count

        portfolio = {
            ticker: weight
            for ticker in tickers
        }

        return portfolio

    # ------------------------------------------------------------------
    # 5.2 RETURNS
    # ------------------------------------------------------------------

    @classmethod
    def build_returns(
        cls,
    ) -> pd.DataFrame:
        """
        Construct deterministic historical return observations for
        every canonical production asset.

        The production forecasting dependency graph requires at least
        252 observations. The deterministic dataset contains 300.

        The data is generated from deterministic factor structure rather
        than external market data.

        No portfolio mathematics is performed here.
        """

        tickers = cls.production_tickers()

        periods = cls.DETERMINISTIC_HISTORY_LENGTH

        rng = np.random.default_rng(
            42
        )

        market_factor = rng.normal(
            loc=0.0004,
            scale=0.0080,
            size=periods,
        )

        defensive_factor = rng.normal(
            loc=0.0001,
            scale=0.0040,
            size=periods,
        )

        commodity_factor = rng.normal(
            loc=0.0002,
            scale=0.0050,
            size=periods,
        )

        idiosyncratic = rng.normal(
            loc=0.0,
            scale=0.0025,
            size=(
                periods,
                len(tickers),
            ),
        )

        market_loadings = np.array(
            [
                1.00,   # SPY
                1.08,   # QQQ
                1.15,   # IWM
                0.82,   # VEA
                0.95,   # VWO
                -0.35,  # TLT
                -0.20,  # IEF
                -0.05,  # SHY
                0.20,   # LQD
                0.45,   # HYG
                0.10,   # GLD
                0.15,   # SLV
                0.30,   # DBC
                0.75,   # VNQ
            ],
            dtype=float,
        )

        defensive_loadings = np.array(
            [
                -0.10,  # SPY
                -0.15,  # QQQ
                -0.20,  # IWM
                -0.05,  # VEA
                -0.10,  # VWO
                0.80,   # TLT
                0.65,   # IEF
                0.30,   # SHY
                0.40,   # LQD
                0.10,   # HYG
                0.35,   # GLD
                0.20,   # SLV
                0.05,   # DBC
                -0.05,  # VNQ
            ],
            dtype=float,
        )

        commodity_loadings = np.array(
            [
                0.00,   # SPY
                0.00,   # QQQ
                0.00,   # IWM
                0.05,   # VEA
                0.10,   # VWO
                -0.05,  # TLT
                -0.02,  # IEF
                0.00,   # SHY
                0.00,   # LQD
                0.05,   # HYG
                0.80,   # GLD
                0.95,   # SLV
                1.10,   # DBC
                0.10,   # VNQ
            ],
            dtype=float,
        )

        returns_array = (
            market_factor[:, None]
            * market_loadings[None, :]
        )

        returns_array += (
            defensive_factor[:, None]
            * defensive_loadings[None, :]
        )

        returns_array += (
            commodity_factor[:, None]
            * commodity_loadings[None, :]
        )

        returns_array += idiosyncratic

        index = pd.date_range(
            "2024-01-01",
            periods=periods,
            freq="D",
        )

        returns = pd.DataFrame(
            returns_array,
            index=index,
            columns=tickers,
            dtype=float,
        )

        return returns

    # ------------------------------------------------------------------
    # 5.3 REGIMES
    # ------------------------------------------------------------------

    @classmethod
    def build_regimes(
        cls,
    ) -> list[str]:
        """
        Construct deterministic regime history aligned with the
        deterministic return history.
        """

        return [
            "EXPANSION"
            for _ in range(
                cls.DETERMINISTIC_HISTORY_LENGTH
            )
        ]

    # ------------------------------------------------------------------
    # 5.4 MACRO DATA
    # ------------------------------------------------------------------

    @classmethod
    def build_macro_data(
        cls,
    ) -> dict[str, Any]:
        """
        Construct deterministic macroeconomic input according to the
        exact ProductionIntegration contract.

        Historical field
        ----------------
        unemployment:
            pandas Series aligned with the return history.

        Scalar fields
        -------------
        growth
        inflation
        yield_spread
        """

        periods = cls.DETERMINISTIC_HISTORY_LENGTH

        index = pd.date_range(
            "2024-01-01",
            periods=periods,
            freq="D",
        )

        unemployment = np.linspace(
            4.00,
            3.95,
            periods,
            dtype=float,
        )

        return {
            "growth": 2.10,
            "inflation": 2.03,
            "yield_spread": 1.47,
            "unemployment": pd.Series(
                unemployment,
                index=index,
                dtype=float,
            ),
        }

    # ------------------------------------------------------------------
    # 5.5 SCENARIOS
    # ------------------------------------------------------------------

    @staticmethod
    def build_scenarios() -> list[str]:
        """
        Construct deterministic scenario set.
        """

        return [
            "BASE",
            "RECESSION",
        ]

    # ==================================================================
    # SECTION 6
    # INPUT VALIDATION
    # ==================================================================

    @classmethod
    def validate_input_contract(
        cls,
        *,
        portfolio: dict[str, float],
        returns: Any,
        regimes: list[str],
        macro_data: dict[str, Any],
        scenarios: list[str],
    ) -> None:
        """
        Validate the deterministic production input contract before
        invoking ProductionIntegration.

        This validation establishes that the complete canonical
        14-asset production universe reaches the integration boundary.
        """

        expected_tickers = set(
            cls.production_tickers()
        )

        # --------------------------------------------------------------
        # PORTFOLIO
        # --------------------------------------------------------------

        if not isinstance(
            portfolio,
            dict,
        ) or not portfolio:

            raise ProductionDecisionExecutionError(
                "Deterministic portfolio input cannot be empty."
            )

        portfolio_tickers = set(
            portfolio.keys()
        )

        if portfolio_tickers != expected_tickers:

            raise ProductionDecisionExecutionError(
                (
                    "Deterministic portfolio tickers do not match "
                    "the canonical production universe. "
                    f"Expected {sorted(expected_tickers)}, "
                    f"got {sorted(portfolio_tickers)}."
                )
            )

        if len(portfolio) != len(
            expected_tickers
        ):

            raise ProductionDecisionExecutionError(
                (
                    "Deterministic portfolio must contain "
                    f"{len(expected_tickers)} assets."
                )
            )

        for ticker, weight in portfolio.items():

            if not isinstance(
                ticker,
                str,
            ):

                raise ProductionDecisionExecutionError(
                    "Production portfolio ticker names must be strings."
                )

            try:

                numeric_weight = float(
                    weight
                )

            except (
                TypeError,
                ValueError,
            ) as exc:

                raise ProductionDecisionExecutionError(
                    (
                        f"Invalid deterministic portfolio weight "
                        f"for '{ticker}': {weight}"
                    )
                ) from exc

            if not np.isfinite(
                numeric_weight
            ):

                raise ProductionDecisionExecutionError(
                    (
                        f"Deterministic portfolio weight for "
                        f"'{ticker}' must be finite."
                    )
                )

        # --------------------------------------------------------------
        # RETURNS
        # --------------------------------------------------------------

        if not hasattr(
            returns,
            "columns",
        ):

            raise ProductionDecisionExecutionError(
                (
                    "Deterministic returns input must expose "
                    "a DataFrame-like columns interface."
                )
            )

        if not hasattr(
            returns,
            "__len__",
        ):

            raise ProductionDecisionExecutionError(
                "Deterministic returns input must expose a length."
            )

        if len(returns) < cls.MINIMUM_RETURN_HISTORY:

            raise ProductionDecisionExecutionError(
                (
                    "Deterministic returns history is too short: "
                    f"{len(returns)} observations supplied; "
                    f"{cls.MINIMUM_RETURN_HISTORY} required."
                )
            )

        return_tickers = set(
            returns.columns
        )

        if return_tickers != expected_tickers:

            raise ProductionDecisionExecutionError(
                (
                    "Deterministic returns columns do not match "
                    "the canonical production universe. "
                    f"Expected {sorted(expected_tickers)}, "
                    f"got {sorted(return_tickers)}."
                )
            )

        if len(
            returns.columns
        ) != len(expected_tickers):

            raise ProductionDecisionExecutionError(
                (
                    "Deterministic returns must contain "
                    f"{len(expected_tickers)} assets."
                )
            )

        if not returns.notna().all().all():

            raise ProductionDecisionExecutionError(
                "Deterministic returns contain missing observations."
            )

        if not np.isfinite(
            returns.to_numpy(
                dtype=float
            )
        ).all():

            raise ProductionDecisionExecutionError(
                "Deterministic returns contain non-finite observations."
            )

        # --------------------------------------------------------------
        # REGIMES
        # --------------------------------------------------------------

        if not regimes:

            raise ProductionDecisionExecutionError(
                "Deterministic regime history cannot be empty."
            )

        if len(regimes) != len(returns):

            raise ProductionDecisionExecutionError(
                (
                    "Deterministic regime history length must match "
                    "the deterministic returns history. "
                    f"Got {len(regimes)} regimes and "
                    f"{len(returns)} return observations."
                )
            )

        # --------------------------------------------------------------
        # MACRO DATA
        # --------------------------------------------------------------

        if not isinstance(
            macro_data,
            dict,
        ):

            raise ProductionDecisionExecutionError(
                "Macro data must be a dictionary."
            )

        missing_macro_fields = (
            cls.REQUIRED_MACRO_FIELDS
            - set(macro_data)
        )

        if missing_macro_fields:

            missing = ", ".join(
                sorted(
                    missing_macro_fields
                )
            )

            raise ProductionDecisionExecutionError(
                (
                    "Deterministic macro data is missing required "
                    f"fields: {missing}."
                )
            )

        # --------------------------------------------------------------
        # HISTORICAL MACRO SERIES
        # --------------------------------------------------------------

        for field_name in cls.HISTORICAL_MACRO_FIELDS:

            value = macro_data[field_name]

            if value is None:

                raise ProductionDecisionExecutionError(
                    (
                        f"Macro field '{field_name}' "
                        "cannot be None."
                    )
                )

            try:

                length = len(value)

            except TypeError as exc:

                raise ProductionDecisionExecutionError(
                    (
                        f"Macro field '{field_name}' must be "
                        "a non-empty historical series."
                    )
                ) from exc

            if length == 0:

                raise ProductionDecisionExecutionError(
                    (
                        f"Macro field '{field_name}' must be "
                        "a non-empty historical series."
                    )
                )

            if not isinstance(
                value,
                pd.Series,
            ):

                raise ProductionDecisionExecutionError(
                    (
                        f"Macro field '{field_name}' must be "
                        "a pandas Series."
                    )
                )

            if not value.notna().all():

                raise ProductionDecisionExecutionError(
                    (
                        f"Macro field '{field_name}' contains "
                        "missing observations."
                    )
                )

            if len(value) != len(returns):

                raise ProductionDecisionExecutionError(
                    (
                        f"Macro field '{field_name}' must contain "
                        f"{len(returns)} observations; "
                        f"got {len(value)}."
                    )
                )

        # --------------------------------------------------------------
        # SCALAR MACRO DATA
        # --------------------------------------------------------------

        for field_name in cls.SCALAR_MACRO_FIELDS:

            value = macro_data[field_name]

            if isinstance(
                value,
                (
                    pd.Series,
                    pd.DataFrame,
                    list,
                    tuple,
                    np.ndarray,
                ),
            ):

                raise ProductionDecisionExecutionError(
                    (
                        f"Macro field '{field_name}' must be "
                        "a numeric scalar."
                    )
                )

            try:

                numeric_value = float(value)

            except (
                TypeError,
                ValueError,
            ) as exc:

                raise ProductionDecisionExecutionError(
                    (
                        f"Macro field '{field_name}' must be "
                        "numeric."
                    )
                ) from exc

            if not np.isfinite(
                numeric_value
            ):

                raise ProductionDecisionExecutionError(
                    (
                        f"Macro field '{field_name}' must be "
                        "finite."
                    )
                )

        # --------------------------------------------------------------
        # SCENARIOS
        # --------------------------------------------------------------

        if not scenarios:

            raise ProductionDecisionExecutionError(
                "Deterministic scenario set cannot be empty."
            )

    # ==================================================================
    # SECTION 7
    # EXECUTION RESULT FACTORIES
    # ==================================================================

    @staticmethod
    def _failed_result(
        *,
        error: str,
        diagnostics: dict[str, Any] | None = None,
        warnings: tuple[str, ...] = tuple(),
    ) -> ProductionDecisionExecutionResult:
        """
        Construct a standardized failed execution result.
        """

        return ProductionDecisionExecutionResult(
            success=False,
            status=PortfolioDecisionStatus.FAILED.value,
            approved=False,
            decision_id=None,
            regime=None,
            weights={},
            portfolio_return=0.0,
            portfolio_variance=0.0,
            portfolio_volatility=0.0,
            gross_exposure=0.0,
            net_exposure=0.0,
            number_of_positions=0,
            risk_contributions={},
            risk_contribution_pct={},
            scenario_results={},
            warnings=warnings,
            errors=(error,),
            diagnostics=(
                {}
                if diagnostics is None
                else dict(diagnostics)
            ),
        )

    # ==================================================================
    # SECTION 8
    # EXECUTION
    # ==================================================================

    def execute(
        self,
    ) -> ProductionDecisionExecutionResult:
        """
        Execute the deterministic production decision pipeline.

        All portfolio decision logic remains delegated to
        ProductionIntegration and PortfolioDecisionEngine.
        """

        self.execution_count += 1

        try:

            portfolio = (
                self.build_portfolio()
            )

            returns = (
                self.build_returns()
            )

            regimes = (
                self.build_regimes()
            )

            macro_data = (
                self.build_macro_data()
            )

            scenarios = (
                self.build_scenarios()
            )

            self.validate_input_contract(
                portfolio=portfolio,
                returns=returns,
                regimes=regimes,
                macro_data=macro_data,
                scenarios=scenarios,
            )

            result = (
                self.integration.run(
                    portfolio=portfolio,
                    returns=returns,
                    regimes=regimes,
                    macro_data=macro_data,
                    scenarios=scenarios,
                )
            )

        except (
            ProductionIntegrationError,
            ProductionDecisionExecutionError,
        ) as exc:

            self.failed_count += 1

            execution_result = (
                self._failed_result(
                    error=str(exc),
                    diagnostics={
                        "exception_type": (
                            type(exc).__name__
                        )
                    },
                )
            )

            self.last_result = execution_result

            return execution_result

        except Exception as exc:

            self.failed_count += 1

            execution_result = (
                self._failed_result(
                    error=str(exc),
                    diagnostics={
                        "exception_type": (
                            type(exc).__name__
                        ),
                        "unexpected_exception": True,
                    },
                )
            )

            self.last_result = execution_result

            return execution_result

        decision = (
            result.decision
        )

        # --------------------------------------------------------------
        # NO DECISION
        # --------------------------------------------------------------

        if decision is None:

            self.failed_count += 1

            execution_result = (
                self._failed_result(
                    error=(
                        result.errors[0]
                        if result.errors
                        else (
                            "ProductionIntegration returned "
                            "no PortfolioDecision."
                        )
                    ),
                    diagnostics=dict(
                        result.diagnostics
                    ),
                    warnings=tuple(
                        result.warnings
                    ),
                )
            )

            self.last_result = execution_result

            return execution_result

        # --------------------------------------------------------------
        # STATUS COUNTERS
        # --------------------------------------------------------------

        if (
            decision.status
            == PortfolioDecisionStatus.APPROVED.value
        ):

            self.approved_count += 1

        elif (
            decision.status
            == PortfolioDecisionStatus.REJECTED.value
        ):

            self.rejected_count += 1

        else:

            self.failed_count += 1

        if result.success:

            self.success_count += 1

        # --------------------------------------------------------------
        # FINAL RESULT
        # --------------------------------------------------------------

        decision_tickers = tuple(
            decision.tickers
        )

        execution_result = (
            ProductionDecisionExecutionResult(
                success=bool(
                    result.success
                ),
                status=decision.status,
                approved=bool(
                    decision.approved
                ),
                decision_id=(
                    decision.decision_id
                ),
                regime=decision.regime,
                weights=dict(
                    decision.weights
                ),
                portfolio_return=float(
                    decision.portfolio_return
                ),
                portfolio_variance=float(
                    decision.portfolio_variance
                ),
                portfolio_volatility=float(
                    decision.portfolio_volatility
                ),
                gross_exposure=float(
                    decision.gross_exposure
                ),
                net_exposure=float(
                    decision.net_exposure
                ),
                number_of_positions=int(
                    decision.number_of_positions
                ),
                risk_contributions=dict(
                    decision.risk_contributions
                ),
                risk_contribution_pct=dict(
                    decision.risk_contribution_pct
                ),
                scenario_results=dict(
                    decision.scenario_results
                ),
                warnings=tuple(
                    decision.warnings
                ),
                errors=tuple(
                    decision.errors
                ),
                diagnostics=dict(
                    decision.diagnostics
                ),
                tickers=decision_tickers,
            )
        )

        self.last_result = (
            execution_result
        )

        return execution_result

    # ==================================================================
    # SECTION 9
    # EXECUTION VALIDATION
    # ==================================================================

    @classmethod
    def validate_result(
        cls,
        result: ProductionDecisionExecutionResult,
    ) -> None:
        """
        Validate the complete Phase IV-B.3 execution result.
        """

        if not isinstance(
            result,
            ProductionDecisionExecutionResult,
        ):

            raise ProductionDecisionExecutionError(
                (
                    "Execution result must be a "
                    "ProductionDecisionExecutionResult."
                )
            )

        expected_tickers = set(
            cls.production_tickers()
        )

        # --------------------------------------------------------------
        # APPROVED
        # --------------------------------------------------------------

        if result.status == (
            PortfolioDecisionStatus.APPROVED.value
        ):

            if not result.success:

                raise ProductionDecisionExecutionError(
                    (
                        "Execution returned APPROVED but "
                        "success=False."
                    )
                )

            if not result.approved:

                raise ProductionDecisionExecutionError(
                    (
                        "Execution returned APPROVED but "
                        "approved=False."
                    )
                )

            if not result.decision_id:

                raise ProductionDecisionExecutionError(
                    "Approved execution has no decision ID."
                )

            if not isinstance(
                result.decision_id,
                str,
            ):

                raise ProductionDecisionExecutionError(
                    "Approved decision ID must be a string."
                )

            if not result.decision_id.strip():

                raise ProductionDecisionExecutionError(
                    "Approved decision ID cannot be blank."
                )

            if not result.regime:

                raise ProductionDecisionExecutionError(
                    "Approved execution has no regime."
                )

            if not result.tickers:

                raise ProductionDecisionExecutionError(
                    "Approved execution has no tickers."
                )

            result_tickers = set(
                result.tickers
            )

            if result_tickers != expected_tickers:

                raise ProductionDecisionExecutionError(
                    (
                        "Approved execution tickers do not match "
                        "the canonical production universe. "
                        f"Expected {sorted(expected_tickers)}, "
                        f"got {sorted(result_tickers)}."
                    )
                )

            if len(
                result.tickers
            ) != len(expected_tickers):

                raise ProductionDecisionExecutionError(
                    (
                        "Approved execution must contain "
                        f"{len(expected_tickers)} tickers."
                    )
                )

            if not result.weights:

                raise ProductionDecisionExecutionError(
                    "Approved execution has no weights."
                )

            weight_tickers = set(
                result.weights.keys()
            )

            if weight_tickers != expected_tickers:

                raise ProductionDecisionExecutionError(
                    (
                        "Approved execution weights do not cover "
                        "the canonical production universe."
                    )
                )

            weight_sum = sum(
                float(value)
                for value in result.weights.values()
            )

            if not np.isclose(
                weight_sum,
                1.0,
                atol=1e-6,
            ):

                raise ProductionDecisionExecutionError(
                    (
                        "Approved portfolio weights do not "
                        f"sum to one. Got {weight_sum}."
                    )
                )

            if not result.risk_contributions:

                raise ProductionDecisionExecutionError(
                    (
                        "Approved execution contains no "
                        "risk contributions."
                    )
                )

            if set(
                result.risk_contributions.keys()
            ) != expected_tickers:

                raise ProductionDecisionExecutionError(
                    (
                        "Approved execution risk contributions "
                        "do not cover the canonical production universe."
                    )
                )

            if not result.risk_contribution_pct:

                raise ProductionDecisionExecutionError(
                    (
                        "Approved execution contains no "
                        "risk contribution percentages."
                    )
                )

            if set(
                result.risk_contribution_pct.keys()
            ) != expected_tickers:

                raise ProductionDecisionExecutionError(
                    (
                        "Approved execution risk contribution "
                        "percentages do not cover the canonical "
                        "production universe."
                    )
                )

            if not result.scenario_results:

                raise ProductionDecisionExecutionError(
                    (
                        "Approved execution contains no "
                        "scenario results."
                    )
                )

            finite_values = (
                result.portfolio_return,
                result.portfolio_variance,
                result.portfolio_volatility,
                result.gross_exposure,
                result.net_exposure,
            )

            if not all(
                np.isfinite(value)
                for value in finite_values
            ):

                raise ProductionDecisionExecutionError(
                    (
                        "Approved execution contains "
                        "non-finite portfolio statistics."
                    )
                )

        # --------------------------------------------------------------
        # REJECTED
        # --------------------------------------------------------------

        elif result.status == (
            PortfolioDecisionStatus.REJECTED.value
        ):

            if result.success:

                raise ProductionDecisionExecutionError(
                    (
                        "Rejected execution cannot have "
                        "success=True."
                    )
                )

            if result.approved:

                raise ProductionDecisionExecutionError(
                    (
                        "Rejected execution has approved=True."
                    )
                )

        # --------------------------------------------------------------
        # FAILED
        # --------------------------------------------------------------

        elif result.status == (
            PortfolioDecisionStatus.FAILED.value
        ):

            if result.success:

                raise ProductionDecisionExecutionError(
                    (
                        "Failed execution cannot have "
                        "success=True."
                    )
                )

            if result.approved:

                raise ProductionDecisionExecutionError(
                    (
                        "Failed execution has approved=True."
                    )
                )

            if not result.errors:

                raise ProductionDecisionExecutionError(
                    (
                        "Failed execution contains no "
                        "diagnostic errors."
                    )
                )

        # --------------------------------------------------------------
        # UNKNOWN
        # --------------------------------------------------------------

        else:

            raise ProductionDecisionExecutionError(
                (
                    "Unknown production decision status: "
                    f"{result.status}"
                )
            )

    # ==================================================================
    # SECTION 10
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ) -> dict[str, Any]:
        """
        Return Phase IV-B.3 health information.
        """

        try:

            tickers = (
                self.production_tickers()
            )

            integration_health = (
                self.integration.health_check()
            )

            healthy = bool(
                integration_health.get(
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
                    len(tickers)
                ),
                "production_assets": list(
                    tickers
                ),
                "integration_health": (
                    integration_health
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
                "error": str(exc),
            }

    # ==================================================================
    # SECTION 11
    # METADATA
    # ==================================================================

    def metadata(
        self,
    ) -> dict[str, Any]:
        """
        Return Phase IV-B.3 metadata.
        """

        tickers = self.production_tickers()

        return {
            "module": (
                "productiondecisionexecution"
            ),
            "component": (
                "ProductionDecisionExecution"
            ),
            "api_version": (
                self.API_VERSION
            ),
            "phase": (
                self.PHASE
            ),
            "production_only": True,
            "test_doubles_allowed": (
                self.TEST_DOUBLES_ALLOWED
            ),
            "live_trading_enabled": (
                self.LIVE_TRADING_ENABLED
            ),
            "deterministic_regression_data": True,
            "decision_engine_is_authoritative": True,
            "decision_id_generated_upstream": True,
            "canonical_production_universe": True,
            "production_asset_count": (
                len(tickers)
            ),
            "production_assets": list(
                tickers
            ),
            "required_macro_fields": sorted(
                self.REQUIRED_MACRO_FIELDS
            ),
            "historical_macro_fields": sorted(
                self.HISTORICAL_MACRO_FIELDS
            ),
            "scalar_macro_fields": sorted(
                self.SCALAR_MACRO_FIELDS
            ),
            "minimum_return_history": (
                self.MINIMUM_RETURN_HISTORY
            ),
            "deterministic_history_length": (
                self.DETERMINISTIC_HISTORY_LENGTH
            ),
        }

    # ==================================================================
    # SECTION 12
    # SUMMARY
    # ==================================================================

    def summary(
        self,
    ) -> dict[str, Any]:
        """
        Return Phase IV-B.3 execution statistics.
        """

        last = (
            self.last_result
        )

        return {
            "api_version": (
                self.API_VERSION
            ),
            "phase": (
                self.PHASE
            ),
            "execution_count": (
                self.execution_count
            ),
            "success_count": (
                self.success_count
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
            "last_status": (
                None
                if last is None
                else last.status
            ),
            "last_approved": (
                None
                if last is None
                else last.approved
            ),
            "last_decision_id": (
                None
                if last is None
                else last.decision_id
            ),
        }


# ======================================================================
# SECTION 13
# CONVENIENCE FACTORY
# ======================================================================


def build_production_decision_execution(
) -> ProductionDecisionExecution:
    """
    Construct the Phase IV-B.3 production execution boundary.
    """

    return ProductionDecisionExecution()


# ======================================================================
# SECTION 14
# REGRESSION TESTS
# ======================================================================


def test_production_decision_execution_metadata() -> None:
    """
    Verify Phase IV-B.3 metadata.
    """

    execution = (
        ProductionDecisionExecution()
    )

    metadata = (
        execution.metadata()
    )

    assert (
        metadata["api_version"]
        == "1.1.0"
    )

    assert (
        metadata["phase"]
        == "IV-B.3"
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
        metadata["deterministic_regression_data"]
        is True
    )

    assert (
        metadata["decision_engine_is_authoritative"]
        is True
    )

    assert (
        metadata["decision_id_generated_upstream"]
        is True
    )

    assert (
        metadata["canonical_production_universe"]
        is True
    )

    assert (
        metadata["production_asset_count"]
        == 14
    )

    assert set(
        metadata["production_assets"]
    ) == set(
        PRODUCTION_ASSETS
    )

    assert set(
        metadata["required_macro_fields"]
    ) == {
        "growth",
        "inflation",
        "unemployment",
        "yield_spread",
    }

    assert set(
        metadata["historical_macro_fields"]
    ) == {
        "unemployment",
    }

    assert set(
        metadata["scalar_macro_fields"]
    ) == {
        "growth",
        "inflation",
        "yield_spread",
    }

    assert (
        metadata["minimum_return_history"]
        == 252
    )

    assert (
        metadata["deterministic_history_length"]
        >= 252
    )


def test_production_decision_execution_universe() -> None:
    """
    Verify that Phase IV-B.3 consumes the canonical production universe.
    """

    execution = (
        ProductionDecisionExecution()
    )

    universe = (
        execution.production_universe()
    )

    assert isinstance(
        universe,
        AssetUniverse,
    )

    assert (
        universe.is_production_universe
        is True
    )

    tickers = (
        execution.production_tickers()
    )

    assert (
        len(tickers)
        == 14
    )

    assert (
        len(set(tickers))
        == 14
    )

    assert tickers == (
        tuple(PRODUCTION_ASSETS)
    )

    assert (
        execution.production_asset_count()
        == 14
    )


def test_production_decision_execution_health() -> None:
    """
    Verify the Phase IV-B.3 health interface.
    """

    execution = (
        ProductionDecisionExecution()
    )

    result = (
        execution.health_check()
    )

    assert isinstance(
        result,
        dict,
    )

    assert (
        result["api_version"]
        == "1.1.0"
    )

    assert (
        result["phase"]
        == "IV-B.3"
    )

    assert (
        "healthy"
        in result
    )

    assert (
        result["production_asset_count"]
        == 14
    )

    assert set(
        result["production_assets"]
    ) == set(
        PRODUCTION_ASSETS
    )


def test_production_decision_execution_data() -> None:
    """
    Verify deterministic production input construction for all 14
    canonical production assets.
    """

    execution = (
        ProductionDecisionExecution()
    )

    portfolio = (
        execution.build_portfolio()
    )

    assert isinstance(
        portfolio,
        dict,
    )

    assert len(
        portfolio
    ) == 14

    assert set(
        portfolio
    ) == set(
        PRODUCTION_ASSETS
    )

    assert np.isclose(
        sum(
            portfolio.values()
        ),
        1.0,
        atol=1e-12,
    )

    returns = (
        execution.build_returns()
    )

    assert isinstance(
        returns,
        pd.DataFrame,
    )

    assert (
        len(returns)
        == 300
    )

    assert (
        returns.shape
        == (
            300,
            14,
        )
    )

    assert list(
        returns.columns
    ) == list(
        PRODUCTION_ASSETS
    )

    assert returns.notna().all().all()

    assert np.isfinite(
        returns.to_numpy(
            dtype=float
        )
    ).all()

    regimes = (
        execution.build_regimes()
    )

    assert (
        len(regimes)
        == len(returns)
    )

    assert all(
        regime == "EXPANSION"
        for regime in regimes
    )

    macro_data = (
        execution.build_macro_data()
    )

    assert isinstance(
        macro_data,
        dict,
    )

    required_macro_fields = {
        "growth",
        "inflation",
        "unemployment",
        "yield_spread",
    }

    assert (
        set(macro_data)
        == required_macro_fields
    )

    unemployment = (
        macro_data["unemployment"]
    )

    assert isinstance(
        unemployment,
        pd.Series,
    )

    assert not unemployment.empty

    assert (
        len(unemployment)
        == len(returns)
    )

    assert unemployment.dtype.kind in (
        "f",
        "i",
    )

    assert unemployment.notna().all()

    assert isinstance(
        macro_data["growth"],
        (int, float),
    )

    assert isinstance(
        macro_data["inflation"],
        (int, float),
    )

    assert isinstance(
        macro_data["yield_spread"],
        (int, float),
    )

    scenarios = (
        execution.build_scenarios()
    )

    assert scenarios == [
        "BASE",
        "RECESSION",
    ]


def test_production_decision_execution_input_contract() -> None:
    """
    Verify the complete deterministic production input contract.
    """

    execution = (
        ProductionDecisionExecution()
    )

    portfolio = (
        execution.build_portfolio()
    )

    returns = (
        execution.build_returns()
    )

    regimes = (
        execution.build_regimes()
    )

    macro_data = (
        execution.build_macro_data()
    )

    scenarios = (
        execution.build_scenarios()
    )

    execution.validate_input_contract(
        portfolio=portfolio,
        returns=returns,
        regimes=regimes,
        macro_data=macro_data,
        scenarios=scenarios,
    )


def test_production_decision_execution_missing_macro_field() -> None:
    """
    Verify missing macroeconomic fields are rejected before the real
    production integration boundary is invoked.
    """

    execution = (
        ProductionDecisionExecution()
    )

    portfolio = (
        execution.build_portfolio()
    )

    returns = (
        execution.build_returns()
    )

    regimes = (
        execution.build_regimes()
    )

    macro_data = {
        "growth": 2.10,
        "inflation": 2.03,
        "unemployment": pd.Series(
            np.full(
                len(returns),
                4.0,
            ),
            index=returns.index,
        ),
    }

    scenarios = (
        execution.build_scenarios()
    )

    try:

        execution.validate_input_contract(
            portfolio=portfolio,
            returns=returns,
            regimes=regimes,
            macro_data=macro_data,
            scenarios=scenarios,
        )

        raise AssertionError(
            "Expected missing macro field failure."
        )

    except ProductionDecisionExecutionError as exc:

        assert (
            "yield_spread"
            in str(exc)
        )


def test_production_decision_execution_macro_shape_contract() -> None:
    """
    Verify that historical and scalar macro fields use the exact
    shapes expected by ProductionIntegration.
    """

    macro_data = (
        ProductionDecisionExecution
        .build_macro_data()
    )

    assert isinstance(
        macro_data["unemployment"],
        pd.Series,
    )

    assert not isinstance(
        macro_data["inflation"],
        pd.Series,
    )

    assert not isinstance(
        macro_data["yield_spread"],
        pd.Series,
    )

    assert isinstance(
        macro_data["inflation"],
        (int, float),
    )

    assert isinstance(
        macro_data["yield_spread"],
        (int, float),
    )


def test_production_decision_execution_summary() -> None:
    """
    Verify initial execution statistics.
    """

    execution = (
        ProductionDecisionExecution()
    )

    summary = (
        execution.summary()
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
        summary["approved_count"]
        == 0
    )

    assert (
        summary["rejected_count"]
        == 0
    )

    assert (
        summary["failed_count"]
        == 0
    )

    assert (
        summary["last_decision_id"]
        is None
    )


def test_production_decision_execution_real_pipeline() -> None:
    """
    Execute the actual deterministic production dependency graph.

    This test deliberately uses the real ProductionIntegration and
    therefore the real PortfolioDecisionEngine dependency graph.

    It verifies that:

        ProductionDecisionExecution
                    |
                    v
        ProductionIntegration
                    |
                    v
        PortfolioDecisionEngine
                    |
                    v
        PortfolioDecision
                    |
                    v
        decision_id

    No decision ID is manufactured by this boundary.
    """

    execution = (
        ProductionDecisionExecution()
    )

    result = (
        execution.execute()
    )

    execution.validate_result(
        result
    )

    assert isinstance(
        result,
        ProductionDecisionExecutionResult,
    )

    assert result.success is True

    assert result.approved is True

    assert (
        result.status
        == PortfolioDecisionStatus.APPROVED.value
    )

    assert result.decision_id

    assert isinstance(
        result.decision_id,
        str,
    )

    assert result.decision_id.strip()

    assert result.regime

    assert result.tickers

    assert len(
        result.tickers
    ) == 14

    assert set(
        result.tickers
    ) == set(
        PRODUCTION_ASSETS
    )

    assert result.weights

    assert set(
        result.weights.keys()
    ) == set(
        PRODUCTION_ASSETS
    )

    assert result.risk_contributions

    assert set(
        result.risk_contributions.keys()
    ) == set(
        PRODUCTION_ASSETS
    )

    assert result.risk_contribution_pct

    assert set(
        result.risk_contribution_pct.keys()
    ) == set(
        PRODUCTION_ASSETS
    )

    assert result.scenario_results

    assert (
        execution.execution_count
        == 1
    )

    assert (
        execution.success_count
        == 1
    )

    assert (
        execution.approved_count
        == 1
    )

    assert (
        execution.rejected_count
        == 0
    )

    assert (
        execution.failed_count
        == 0
    )


def test_production_decision_execution_deterministic_inputs() -> None:
    """
    Verify that deterministic production input construction is stable.
    """

    first_returns = (
        ProductionDecisionExecution
        .build_returns()
    )

    second_returns = (
        ProductionDecisionExecution
        .build_returns()
    )

    assert first_returns.equals(
        second_returns
    )

    first_portfolio = (
        ProductionDecisionExecution
        .build_portfolio()
    )

    second_portfolio = (
        ProductionDecisionExecution
        .build_portfolio()
    )

    assert (
        first_portfolio
        == second_portfolio
    )

    first_regimes = (
        ProductionDecisionExecution
        .build_regimes()
    )

    second_regimes = (
        ProductionDecisionExecution
        .build_regimes()
    )

    assert (
        first_regimes
        == second_regimes
    )

    first_macro = (
        ProductionDecisionExecution
        .build_macro_data()
    )

    second_macro = (
        ProductionDecisionExecution
        .build_macro_data()
    )

    assert (
        first_macro["growth"]
        == second_macro["growth"]
    )

    assert (
        first_macro["inflation"]
        == second_macro["inflation"]
    )

    assert (
        first_macro["yield_spread"]
        == second_macro["yield_spread"]
    )

    assert first_macro[
        "unemployment"
    ].equals(
        second_macro[
            "unemployment"
        ]
    )


# ======================================================================
# SECTION 15
# REGRESSION ENTRY POINT
# ======================================================================


def run_regression_tests() -> None:
    """
    Run Phase IV-B.3 structural and production regression tests.
    """

    test_production_decision_execution_metadata()

    test_production_decision_execution_universe()

    test_production_decision_execution_health()

    test_production_decision_execution_data()

    test_production_decision_execution_input_contract()

    test_production_decision_execution_missing_macro_field()

    test_production_decision_execution_macro_shape_contract()

    test_production_decision_execution_summary()

    test_production_decision_execution_real_pipeline()

    test_production_decision_execution_deterministic_inputs()

    print(
        "ProductionDecisionExecution Phase IV-B.3 "
        "structural and production tests passed."
    )


# ======================================================================
# SECTION 16
# MODULE ENTRY POINT
# ======================================================================


if __name__ == "__main__":

    print(
        "============================================================"
    )

    print(
        "PHASE IV-B.3 PRODUCTION DECISION EXECUTION"
    )

    print(
        "============================================================"
    )

    execution = (
        ProductionDecisionExecution()
    )

    print()

    print(
        "METADATA:"
    )

    print(
        execution.metadata()
    )

    print()

    print(
        "CANONICAL PRODUCTION ASSETS:"
    )

    print(
        execution.production_tickers()
    )

    print()

    print(
        "HEALTH CHECK:"
    )

    health = (
        execution.health_check()
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
                "Unknown production execution error.",
            ),
        )

    print()

    run_regression_tests()
