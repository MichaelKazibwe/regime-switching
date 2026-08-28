# ======================================================================
# PRODUCTION COMPOSITION
# PHASE IV-B.1
# ======================================================================

"""
Production composition boundary for the institutional portfolio stack.

This module constructs the real production dependency graph used by
PortfolioDecisionEngine.

Design principles
-----------------
1. Production components must be real implementations.
2. Test doubles are forbidden.
3. Mandatory dependencies fail fast.
4. Constructor incompatibilities are explicit.
5. Composite components must be fully configured.
6. The canonical 14-asset production universe is mandatory.
7. Health checks must pass before the engine is released.
8. Live trading remains disabled in Phase IV-B.1.

Canonical production universe
-----------------------------
The production engine consumes AssetUniverse.production().

Expected production assets:

    SPY
    QQQ
    IWM
    VEA
    VWO
    TLT
    IEF
    SHY
    LQD
    HYG
    GLD
    SLV
    DBC
    VNQ

The production composition layer is deliberately responsible for
enforcing this contract so downstream components do not accidentally
construct or receive a reduced universe.
"""

# ======================================================================
# SECTION 1
# IMPORTS
# ======================================================================

from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any, Callable

import numpy as np

from assetuniverse import (
    AssetUniverse,
    PRODUCTION_ASSETS,
    PRODUCTION_ASSET_COUNT,
)

from blacklitterman import (
    BlackLittermanModel,
)

from constraints import (
    PortfolioConstraints,
)

from covarianceengine import (
    CovarianceEngine,
)

from ensemblecovariance import (
    EnsembleCovariance,
)

from expectedreturnforecaster import (
    ExpectedReturnForecaster,
)

from macroregime import (
    MacroRegimeModel,
)

from portfoliooptimizer import (
    PortfolioOptimizer,
)

from regimecovariance import (
    RegimeCovariance,
)

from riskbudgetengine import (
    RiskBudgetEngine,
)

from riskcontributionanalyzer import (
    RiskContributionAnalytics,
)

from riskmodel import (
    RiskModel,
)

from scenarioengine import (
    ScenarioEngine,
)

from portfoliodecisionengine import (
    PortfolioDecisionEngine,
)

from volatilitytargeting import (
    VolatilityTargeting,
)


# ======================================================================
# SECTION 2
# EXCEPTIONS
# ======================================================================


class ProductionCompositionError(
    RuntimeError,
):
    """
    Raised when the production dependency graph cannot be constructed
    or validated.
    """

    pass


# ======================================================================
# SECTION 3
# PRODUCTION COMPONENT REGISTRY
# ======================================================================


@dataclass(
    frozen=True,
)
class ProductionComponents:
    """
    Immutable registry of production components.
    """

    asset_universe: Any

    regime_model: Any

    expected_return_forecaster: Any

    covariance_engine: Any

    regime_covariance: Any

    ensemble_covariance: Any

    black_litterman: Any

    optimizer: Any

    constraints: Any

    risk_model: Any

    risk_contribution_analyzer: Any

    scenario_engine: Any

    # ==================================================================
    # ENGINE KWARGS
    # ==================================================================

    def as_engine_kwargs(
        self,
    ) -> dict[str, Any]:

        return {
            "asset_universe": (
                self.asset_universe
            ),
            "regime_model": (
                self.regime_model
            ),
            "expected_return_forecaster": (
                self.expected_return_forecaster
            ),
            "covariance_engine": (
                self.covariance_engine
            ),
            "regime_covariance": (
                self.regime_covariance
            ),
            "ensemble_covariance": (
                self.ensemble_covariance
            ),
            "black_litterman": (
                self.black_litterman
            ),
            "optimizer": (
                self.optimizer
            ),
            "constraints": (
                self.constraints
            ),
            "risk_model": (
                self.risk_model
            ),
            "risk_contribution_analyzer": (
                self.risk_contribution_analyzer
            ),
            "scenario_engine": (
                self.scenario_engine
            ),
        }


# ======================================================================
# SECTION 4
# PRODUCTION COMPOSITION ENGINE
# ======================================================================


class ProductionComposition:
    """
    Strict production dependency-composition engine.
    """

    API_VERSION = (
        "1.0.0"
    )

    PHASE = (
        "IV-B.1"
    )

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

    # Canonical production universe.
    PRODUCTION_ASSETS = (
        PRODUCTION_ASSETS
    )

    PRODUCTION_ASSET_COUNT = (
        PRODUCTION_ASSET_COUNT
    )

    # ==================================================================
    # SECTION 5
    # CONSTRUCTOR
    # ==================================================================

    def __init__(
        self,
        *,
        risk_budget_engine_factory: (
            Callable[[], Any]
            | None
        ) = None,
        volatility_targeting_factory: (
            Callable[[], Any]
            | None
        ) = None,
    ) -> None:

        self.risk_budget_engine_factory = (
            risk_budget_engine_factory
            if risk_budget_engine_factory
            is not None
            else self._default_risk_budget_engine_factory
        )

        self.volatility_targeting_factory = (
            volatility_targeting_factory
            if volatility_targeting_factory
            is not None
            else self._default_volatility_targeting_factory
        )

    # ==================================================================
    # SECTION 6
    # GENERIC CONSTRUCTION
    # ==================================================================

    @staticmethod
    def _construct(
        component_class: type[Any],
        component_name: str,
    ) -> Any:

        try:

            component = (
                component_class()
            )

        except Exception as exc:

            raise ProductionCompositionError(
                (
                    "Unable to construct production "
                    f"component '{component_name}' "
                    f"from "
                    f"{component_class.__module__}."
                    f"{component_class.__name__}: "
                    f"{exc}"
                )
            ) from exc

        if component is None:

            raise ProductionCompositionError(
                (
                    f"Production component "
                    f"'{component_name}' returned None."
                )
            )

        return component

    # ==================================================================
    # SECTION 7
    # CANONICAL ASSET UNIVERSE
    # ==================================================================

    @classmethod
    def _construct_asset_universe(
        cls,
    ) -> AssetUniverse:
        """
        Construct and validate the canonical production universe.

        The production composition boundary must never construct a
        generic blank AssetUniverse.

        AssetUniverse.production() is the sole source of the production
        asset universe.
        """

        try:

            universe = (
                AssetUniverse.production()
            )

        except Exception as exc:

            raise ProductionCompositionError(
                (
                    "Unable to construct the canonical "
                    "production AssetUniverse: "
                    f"{exc}"
                )
            ) from exc

        if universe is None:

            raise ProductionCompositionError(
                "AssetUniverse.production() returned None."
            )

        # --------------------------------------------------------------
        # Type validation
        # --------------------------------------------------------------

        if not isinstance(
            universe,
            AssetUniverse,
        ):

            raise ProductionCompositionError(
                (
                    "AssetUniverse.production() returned "
                    "an unexpected object type: "
                    f"{type(universe).__name__}."
                )
            )

        # --------------------------------------------------------------
        # Production flag
        # --------------------------------------------------------------

        if not bool(
            getattr(
                universe,
                "is_production_universe",
                False,
            )
        ):

            raise ProductionCompositionError(
                (
                    "Canonical AssetUniverse is not marked "
                    "as a production universe."
                )
            )

        # --------------------------------------------------------------
        # Size
        # --------------------------------------------------------------

        if (
            universe.size
            != cls.PRODUCTION_ASSET_COUNT
        ):

            raise ProductionCompositionError(
                (
                    "Canonical production AssetUniverse "
                    "contains "
                    f"{universe.size} assets; expected "
                    f"{cls.PRODUCTION_ASSET_COUNT}."
                )
            )

        # --------------------------------------------------------------
        # Ticker integrity
        # --------------------------------------------------------------

        actual_tickers = (
            list(
                universe.tickers
            )
        )

        expected_tickers = (
            list(
                cls.PRODUCTION_ASSETS
            )
        )

        if set(actual_tickers) != set(
            expected_tickers
        ):

            missing = sorted(
                set(expected_tickers)
                - set(actual_tickers)
            )

            unexpected = sorted(
                set(actual_tickers)
                - set(expected_tickers)
            )

            raise ProductionCompositionError(
                (
                    "Canonical production AssetUniverse "
                    "ticker mismatch. "
                    f"Missing={missing}; "
                    f"Unexpected={unexpected}."
                )
            )

        # --------------------------------------------------------------
        # Duplicate protection
        # --------------------------------------------------------------

        if len(
            actual_tickers
        ) != len(
            set(actual_tickers)
        ):

            raise ProductionCompositionError(
                "Canonical production AssetUniverse contains duplicate tickers."
            )

        # --------------------------------------------------------------
        # Health check
        # --------------------------------------------------------------

        try:

            health = (
                universe.health_check()
            )

        except Exception as exc:

            raise ProductionCompositionError(
                (
                    "Canonical production AssetUniverse "
                    f"health check failed: {exc}"
                )
            ) from exc

        if not bool(
            health
        ):

            raise ProductionCompositionError(
                "Canonical production AssetUniverse health check returned False."
            )

        return universe

    # ==================================================================
    # SECTION 8
    # OPTIMIZER DEPENDENCY DISCOVERY
    # ==================================================================

    @staticmethod
    def _optimizer_parameters() -> list[
        inspect.Parameter
    ]:

        try:

            signature = (
                inspect.signature(
                    PortfolioOptimizer
                )
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise ProductionCompositionError(
                (
                    "Unable to inspect PortfolioOptimizer "
                    f"constructor: {exc}"
                )
            ) from exc

        return [
            parameter
            for parameter in (
                signature.parameters.values()
            )
            if parameter.name != "self"
            and parameter.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        ]

    # ==================================================================
    # SECTION 9
    # OPTIMIZER DEPENDENCY RESOLUTION
    # ==================================================================

    def _resolve_optimizer_dependency(
        self,
        parameter: inspect.Parameter,
        constraints: Any,
    ) -> tuple[
        bool,
        Any,
    ]:

        name = (
            parameter.name
        )

        # --------------------------------------------------------------
        # CONSTRAINTS
        # --------------------------------------------------------------

        if name in (
            "constraints",
            "portfolio_constraints",
        ):

            return (
                True,
                constraints,
            )

        # --------------------------------------------------------------
        # RISK BUDGET ENGINE
        # --------------------------------------------------------------

        if name in (
            "risk_budget_engine",
            "risk_budget",
            "risk_budgeting",
        ):

            if (
                self.risk_budget_engine_factory
                is None
            ):

                raise ProductionCompositionError(
                    (
                        "PortfolioOptimizer requires "
                        f"'{name}', but no "
                        "risk budget factory exists."
                    )
                )

            try:

                dependency = (
                    self.risk_budget_engine_factory()
                )

            except Exception as exc:

                raise ProductionCompositionError(
                    (
                        "Unable to construct "
                        "PortfolioOptimizer dependency "
                        f"'{name}': {exc}"
                    )
                ) from exc

            if dependency is None:

                raise ProductionCompositionError(
                    (
                        "PortfolioOptimizer dependency "
                        f"'{name}' returned None."
                    )
                )

            return (
                True,
                dependency,
            )

        # --------------------------------------------------------------
        # VOLATILITY TARGETING
        # --------------------------------------------------------------

        if name in (
            "volatility_targeting",
            "volatility_targeting_engine",
            "vol_targeting",
            "vol_target_engine",
        ):

            if (
                self.volatility_targeting_factory
                is None
            ):

                if (
                    parameter.default
                    is not inspect.Parameter.empty
                ):

                    return (
                        False,
                        None,
                    )

                raise ProductionCompositionError(
                    (
                        "PortfolioOptimizer requires "
                        f"'{name}', but no "
                        "volatility-targeting factory exists."
                    )
                )

            try:

                dependency = (
                    self.volatility_targeting_factory()
                )

            except Exception as exc:

                raise ProductionCompositionError(
                    (
                        "Unable to construct "
                        "PortfolioOptimizer dependency "
                        f"'{name}': {exc}"
                    )
                ) from exc

            if dependency is None:

                raise ProductionCompositionError(
                    (
                        "PortfolioOptimizer dependency "
                        f"'{name}' returned None."
                    )
                )

            if not hasattr(
                dependency,
                "scale_weights",
            ):

                raise ProductionCompositionError(
                    (
                        "Volatility-targeting dependency "
                        "must expose scale_weights()."
                    )
                )

            return (
                True,
                dependency,
            )

        # --------------------------------------------------------------
        # OPTIONAL DEPENDENCY
        # --------------------------------------------------------------

        if (
            parameter.default
            is not inspect.Parameter.empty
        ):

            return (
                False,
                None,
            )

        # --------------------------------------------------------------
        # UNKNOWN REQUIRED DEPENDENCY
        # --------------------------------------------------------------

        raise ProductionCompositionError(
            (
                "PortfolioOptimizer contains an "
                "unsupported required dependency "
                f"'{name}'."
            )
        )

    # ==================================================================
    # SECTION 10
    # OPTIMIZER CONSTRUCTION
    # ==================================================================

    def _construct_optimizer(
        self,
        constraints: Any,
    ) -> Any:

        parameters = (
            self._optimizer_parameters()
        )

        if not parameters:

            return self._construct(
                PortfolioOptimizer,
                "optimizer",
            )

        kwargs: dict[
            str,
            Any,
        ] = {}

        for parameter in parameters:

            resolved, dependency = (
                self._resolve_optimizer_dependency(
                    parameter,
                    constraints,
                )
            )

            if resolved:

                kwargs[
                    parameter.name
                ] = dependency

        try:

            optimizer = (
                PortfolioOptimizer(
                    **kwargs
                )
            )

        except Exception as exc:

            raise ProductionCompositionError(
                (
                    "Unable to construct "
                    "PortfolioOptimizer: "
                    f"{exc}"
                )
            ) from exc

        if optimizer is None:

            raise ProductionCompositionError(
                "PortfolioOptimizer returned None."
            )

        return optimizer

    # ==================================================================
    # SECTION 11
    # COVARIANCE ENSEMBLE CONSTRUCTION
    # ==================================================================

    @staticmethod
    def _construct_covariance_ensemble(
        covariance_engine: Any,
        regime_covariance: Any,
    ) -> EnsembleCovariance:
        """
        Construct the production covariance ensemble.

        Default production blend
        -------------------------
        Base covariance  : 60%
        Regime covariance: 40%

        These are model-combination weights, not portfolio risk
        budgets.
        """

        ensemble = (
            EnsembleCovariance()
        )

        try:

            ensemble.add_model(
                "base",
                covariance_engine,
                weight=0.60,
            )

            ensemble.add_model(
                "regime",
                regime_covariance,
                weight=0.40,
            )

        except Exception as exc:

            raise ProductionCompositionError(
                (
                    "Unable to configure the production "
                    "covariance ensemble: "
                    f"{exc}"
                )
            ) from exc

        try:

            health = (
                ensemble.health_check()
            )

        except Exception as exc:

            raise ProductionCompositionError(
                (
                    "Production covariance ensemble "
                    f"health check failed: {exc}"
                )
            ) from exc

        if isinstance(
            health,
            dict,
        ):

            healthy = bool(
                health.get(
                    "healthy",
                    False,
                )
            )

        else:

            healthy = bool(
                health
            )

        if not healthy:

            raise ProductionCompositionError(
                "Covariance ensemble health check failed."
            )

        return ensemble

    # ==================================================================
    # SECTION 12
    # DEFAULT RISK BUDGET ENGINE
    # ==================================================================

    @staticmethod
    def _default_risk_budget_engine_factory(
    ) -> RiskBudgetEngine:

        return (
            RiskBudgetEngine()
        )

    @staticmethod
    def _default_volatility_targeting_factory(
    ) -> VolatilityTargeting:

        return (
            VolatilityTargeting()
        )

    # ==================================================================
    # SECTION 13
    # BUILD COMPONENTS
    # ==================================================================

    def build_components(
        self,
    ) -> ProductionComponents:

        # --------------------------------------------------------------
        # 13.1 CONSTRAINTS
        # --------------------------------------------------------------

        constraints = (
            self._construct(
                PortfolioConstraints,
                "constraints",
            )
        )

        # --------------------------------------------------------------
        # 13.2 CANONICAL 14-ASSET UNIVERSE
        # --------------------------------------------------------------

        asset_universe = (
            self._construct_asset_universe()
        )

        # --------------------------------------------------------------
        # 13.3 REGIME MODEL
        # --------------------------------------------------------------

        regime_model = (
            self._construct(
                MacroRegimeModel,
                "regime_model",
            )
        )

        # --------------------------------------------------------------
        # 13.4 EXPECTED RETURN FORECASTER
        # --------------------------------------------------------------

        expected_return_forecaster = (
            self._construct(
                ExpectedReturnForecaster,
                "expected_return_forecaster",
            )
        )

        # --------------------------------------------------------------
        # 13.5 BASE COVARIANCE
        # --------------------------------------------------------------

        covariance_engine = (
            self._construct(
                CovarianceEngine,
                "covariance_engine",
            )
        )

        # --------------------------------------------------------------
        # 13.6 REGIME COVARIANCE
        # --------------------------------------------------------------

        regime_covariance = (
            self._construct(
                RegimeCovariance,
                "regime_covariance",
            )
        )

        # --------------------------------------------------------------
        # 13.7 ENSEMBLE COVARIANCE
        # --------------------------------------------------------------

        ensemble_covariance = (
            self._construct_covariance_ensemble(
                covariance_engine,
                regime_covariance,
            )
        )

        # --------------------------------------------------------------
        # 13.8 BLACK-LITTERMAN
        # --------------------------------------------------------------

        black_litterman = (
            self._construct(
                BlackLittermanModel,
                "black_litterman",
            )
        )

        # --------------------------------------------------------------
        # 13.9 OPTIMIZER
        # --------------------------------------------------------------

        optimizer = (
            self._construct_optimizer(
                constraints,
            )
        )

        # --------------------------------------------------------------
        # 13.10 RISK MODEL
        # --------------------------------------------------------------

        risk_model = (
            self._construct(
                RiskModel,
                "risk_model",
            )
        )

        # --------------------------------------------------------------
        # 13.11 RISK CONTRIBUTION ANALYZER
        # --------------------------------------------------------------

        risk_contribution_analyzer = (
            self._construct(
                RiskContributionAnalytics,
                "risk_contribution_analyzer",
            )
        )

        # --------------------------------------------------------------
        # 13.12 SCENARIO ENGINE
        # --------------------------------------------------------------

        scenario_engine = (
            self._construct(
                ScenarioEngine,
                "scenario_engine",
            )
        )

        # --------------------------------------------------------------
        # 13.13 REGISTRY
        # --------------------------------------------------------------

        return ProductionComponents(
            asset_universe=(
                asset_universe
            ),
            regime_model=(
                regime_model
            ),
            expected_return_forecaster=(
                expected_return_forecaster
            ),
            covariance_engine=(
                covariance_engine
            ),
            regime_covariance=(
                regime_covariance
            ),
            ensemble_covariance=(
                ensemble_covariance
            ),
            black_litterman=(
                black_litterman
            ),
            optimizer=(
                optimizer
            ),
            constraints=(
                constraints
            ),
            risk_model=(
                risk_model
            ),
            risk_contribution_analyzer=(
                risk_contribution_analyzer
            ),
            scenario_engine=(
                scenario_engine
            ),
        )

    # ==================================================================
    # SECTION 14
    # ENGINE CONSTRUCTION
    # ==================================================================

    def build_engine(
        self,
    ) -> PortfolioDecisionEngine:

        components = (
            self.build_components()
        )

        # --------------------------------------------------------------
        # FINAL UNIVERSE BOUNDARY VALIDATION
        # --------------------------------------------------------------

        universe = (
            components.asset_universe
        )

        if universe.size != (
            self.PRODUCTION_ASSET_COUNT
        ):

            raise ProductionCompositionError(
                (
                    "Production engine cannot be released "
                    "with an invalid asset universe. "
                    f"Expected {self.PRODUCTION_ASSET_COUNT} "
                    f"assets; received {universe.size}."
                )
            )

        if set(
            universe.tickers
        ) != set(
            self.PRODUCTION_ASSETS
        ):

            raise ProductionCompositionError(
                (
                    "Production engine asset universe does "
                    "not match the canonical 14-asset universe."
                )
            )

        # --------------------------------------------------------------
        # ENGINE CONSTRUCTION
        # --------------------------------------------------------------

        try:

            engine = (
                PortfolioDecisionEngine(
                    **components.as_engine_kwargs()
                )
            )

        except Exception as exc:

            raise ProductionCompositionError(
                (
                    "Unable to construct "
                    "PortfolioDecisionEngine "
                    "from production components: "
                    f"{exc}"
                )
            ) from exc

        if engine is None:

            raise ProductionCompositionError(
                "PortfolioDecisionEngine returned None."
            )

        # --------------------------------------------------------------
        # ENGINE HEALTH
        # --------------------------------------------------------------

        try:

            health = (
                engine.health_check()
            )

        except Exception as exc:

            raise ProductionCompositionError(
                (
                    "PortfolioDecisionEngine health "
                    f"check failed: {exc}"
                )
            ) from exc

        if not isinstance(
            health,
            dict,
        ):

            raise ProductionCompositionError(
                (
                    "PortfolioDecisionEngine health_check() "
                    "must return a dictionary."
                )
            )

        if not health.get(
            "healthy",
            False,
        ):

            unhealthy_components = []

            for (
                name,
                result,
            ) in health.get(
                "components",
                {},
            ).items():

                if (
                    isinstance(
                        result,
                        dict,
                    )
                    and result.get(
                        "healthy"
                    ) is False
                ):

                    unhealthy_components.append(
                        name
                    )

            component_text = (
                ", ".join(
                    unhealthy_components
                )
                if unhealthy_components
                else "unknown"
            )

            raise ProductionCompositionError(
                (
                    "Phase IV-B.1 production composition "
                    "produced an unhealthy "
                    "PortfolioDecisionEngine. "
                    "Unhealthy components: "
                    f"{component_text}"
                )
            )

        # --------------------------------------------------------------
        # ENGINE UNIVERSE VALIDATION
        # --------------------------------------------------------------

        engine_universe = getattr(
            engine,
            "asset_universe",
            None,
        )

        if engine_universe is None:

            raise ProductionCompositionError(
                (
                    "PortfolioDecisionEngine does not expose "
                    "the canonical asset_universe dependency."
                )
            )

        if engine_universe is not universe:

            raise ProductionCompositionError(
                (
                    "PortfolioDecisionEngine is not using "
                    "the exact AssetUniverse instance supplied "
                    "by ProductionComposition."
                )
            )

        if (
            engine_universe.size
            != self.PRODUCTION_ASSET_COUNT
        ):

            raise ProductionCompositionError(
                (
                    "PortfolioDecisionEngine received an "
                    f"invalid asset universe size: "
                    f"{engine_universe.size}; expected "
                    f"{self.PRODUCTION_ASSET_COUNT}."
                )
            )

        if set(
            engine_universe.tickers
        ) != set(
            self.PRODUCTION_ASSETS
        ):

            raise ProductionCompositionError(
                (
                    "PortfolioDecisionEngine received a "
                    "non-canonical production asset universe."
                )
            )

        return engine

    # ==================================================================
    # SECTION 15
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ) -> dict[str, Any]:

        try:

            engine = (
                self.build_engine()
            )

        except ProductionCompositionError as exc:

            return {
                "api_version": (
                    self.API_VERSION
                ),
                "phase": (
                    self.PHASE
                ),
                "healthy": False,
                "error": str(
                    exc
                ),
            }

        try:

            result = (
                engine.health_check()
            )

        except Exception as exc:

            return {
                "api_version": (
                    self.API_VERSION
                ),
                "phase": (
                    self.PHASE
                ),
                "healthy": False,
                "error": str(
                    exc
                ),
            }

        universe = getattr(
            engine,
            "asset_universe",
            None,
        )

        universe_healthy = (
            universe is not None
            and isinstance(
                universe,
                AssetUniverse,
            )
            and universe.size
            == self.PRODUCTION_ASSET_COUNT
            and set(
                universe.tickers
            )
            == set(
                self.PRODUCTION_ASSETS
            )
        )

        healthy = (
            bool(
                result.get(
                    "healthy",
                    False,
                )
            )
            and universe_healthy
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
                result
            ),
        }

    # ==================================================================
    # SECTION 16
    # METADATA
    # ==================================================================

    def metadata(
        self,
    ) -> dict[str, Any]:

        return {
            "module": (
                "productioncomposition"
            ),
            "component": (
                "ProductionComposition"
            ),
            "api_version": (
                self.API_VERSION
            ),
            "phase": (
                self.PHASE
            ),
            "required_components": list(
                self.REQUIRED_COMPONENTS
            ),
            "live_trading_enabled": False,
            "test_doubles_allowed": False,
            "strict_dependency_validation": True,
            "fail_fast": True,
            "canonical_production_universe": True,
            "production_asset_count": (
                self.PRODUCTION_ASSET_COUNT
            ),
            "production_assets": list(
                self.PRODUCTION_ASSETS
            ),
            "covariance_ensemble": {
                "base_weight": 0.60,
                "regime_weight": 0.40,
            },
        }


# ======================================================================
# SECTION 17
# CONVENIENCE FACTORY
# ======================================================================


def build_production_engine(
    *,
    risk_budget_engine_factory: (
        Callable[[], Any]
        | None
    ) = None,
    volatility_targeting_factory: (
        Callable[[], Any]
        | None
    ) = None,
) -> PortfolioDecisionEngine:

    composition = (
        ProductionComposition(
            risk_budget_engine_factory=(
                risk_budget_engine_factory
            ),
            volatility_targeting_factory=(
                volatility_targeting_factory
            ),
        )
    )

    return (
        composition.build_engine()
    )


# ======================================================================
# SECTION 18
# REGRESSION TESTS
# ======================================================================


def test_production_composition_metadata() -> None:

    composition = (
        ProductionComposition()
    )

    metadata = (
        composition.metadata()
    )

    assert (
        metadata["api_version"]
        == "1.0.0"
    )

    assert (
        metadata["phase"]
        == "IV-B.1"
    )

    assert (
        metadata["live_trading_enabled"]
        is False
    )

    assert (
        metadata["test_doubles_allowed"]
        is False
    )

    assert (
        metadata["strict_dependency_validation"]
        is True
    )

    assert (
        metadata["fail_fast"]
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

    assert (
        metadata["production_assets"]
        == list(
            PRODUCTION_ASSETS
        )
    )


def test_production_composition_asset_universe() -> None:
    """
    Verify that ProductionComposition consumes the canonical
    14-asset production AssetUniverse.
    """

    composition = (
        ProductionComposition()
    )

    components = (
        composition.build_components()
    )

    universe = (
        components.asset_universe
    )

    assert isinstance(
        universe,
        AssetUniverse,
    )

    assert (
        universe.is_production_universe
        is True
    )

    assert (
        universe.size
        == 14
    )

    assert (
        universe.PRODUCTION_ASSET_COUNT
        == 14
    )

    assert (
        universe.tickers
        == sorted(
            PRODUCTION_ASSETS
        )
    )

    assert (
        set(
            universe.tickers
        )
        == set(
            PRODUCTION_ASSETS
        )
    )

    assert (
        len(
            set(
                universe.tickers
            )
        )
        == 14
    )

    assert universe.health_check()


def test_production_composition_component_registry() -> None:
    """
    Verify that all mandatory production components are present.
    """

    composition = (
        ProductionComposition()
    )

    components = (
        composition.build_components()
    )

    for component_name in (
        ProductionComposition.REQUIRED_COMPONENTS
    ):

        component = getattr(
            components,
            component_name,
        )

        assert component is not None


def test_covariance_ensemble_composition() -> None:
    """
    Verify that the production covariance ensemble contains real
    covariance implementations.
    """

    composition = (
        ProductionComposition()
    )

    components = (
        composition.build_components()
    )

    ensemble = (
        components.ensemble_covariance
    )

    assert (
        ensemble.available_models
        == [
            "base",
            "regime",
        ]
    )

    assert np.isclose(
        ensemble.weights["base"],
        0.60,
    )

    assert np.isclose(
        ensemble.weights["regime"],
        0.40,
    )

    health = (
        ensemble.health_check()
    )

    assert (
        health
        is True
    )


def test_production_composition_engine_uses_14_assets() -> None:
    """
    Verify that the final PortfolioDecisionEngine receives the
    canonical 14-asset production universe.
    """

    composition = (
        ProductionComposition()
    )

    engine = (
        composition.build_engine()
    )

    assert engine is not None

    assert hasattr(
        engine,
        "asset_universe",
    )

    universe = (
        engine.asset_universe
    )

    assert isinstance(
        universe,
        AssetUniverse,
    )

    assert (
        universe.is_production_universe
        is True
    )

    assert (
        universe.size
        == 14
    )

    assert (
        set(
            universe.tickers
        )
        == set(
            PRODUCTION_ASSETS
        )
    )

    assert (
        len(
            universe.tickers
        )
        == 14
    )


def test_production_composition_health() -> None:

    composition = (
        ProductionComposition()
    )

    result = (
        composition.health_check()
    )

    assert isinstance(
        result,
        dict,
    )

    assert (
        "api_version"
        in result
    )

    assert (
        "phase"
        in result
    )

    assert (
        "healthy"
        in result
    )

    assert (
        result[
            "production_asset_count"
        ]
        == 14
    )

    assert (
        result[
            "production_assets"
        ]
        == list(
            PRODUCTION_ASSETS
        )
    )


# ======================================================================
# SECTION 19
# REGRESSION ENTRY POINT
# ======================================================================


def run_regression_tests() -> None:

    test_production_composition_metadata()

    test_production_composition_asset_universe()

    test_production_composition_component_registry()

    test_covariance_ensemble_composition()

    test_production_composition_engine_uses_14_assets()

    test_production_composition_health()

    print(
        "ProductionComposition Phase IV-B.1 tests passed."
    )


# ======================================================================
# SECTION 20
# MODULE ENTRY POINT
# ======================================================================


if __name__ == "__main__":

    print(
        "============================================================"
    )

    print(
        "PHASE IV-B.1 PRODUCTION COMPOSITION"
    )

    print(
        "============================================================"
    )

    composition = (
        ProductionComposition()
    )

    print()

    print(
        "METADATA:"
    )

    print(
        composition.metadata()
    )

    print()

    print(
        "CANONICAL PRODUCTION ASSETS:"
    )

    print(
        list(
            PRODUCTION_ASSETS
        )
    )

    print()

    print(
        "HEALTH CHECK:"
    )

    health = (
        composition.health_check()
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
                "Unknown composition error.",
            ),
        )

    print()

    run_regression_tests()