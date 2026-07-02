import numpy as np

from macroregime import (
    Regime,
    PortfolioRegimeMapper,
)

from expectedreturnforecaster import (
    ExpectedReturnForecaster,
)

from blacklitterman import (
    BlackLittermanModel,
)

from riskcontributionanalyzer import (
    RiskBudgetReport,
)

from core_constants import (
    REGIME_RISK_BUDGETS,
    REGIME_VOL_TARGETS,
    REGIME_MAX_LEVERAGE,
)

# ============================================================
# PORTFOLIO OPTIMIZER
# ============================================================

class PortfolioOptimizer:

    def __init__(
        self,
        risk_budget_engine,
        constraints,
        vol_target_engine=None,
        forecast_engine=None,
        black_litterman=None
    ):

        # ============================================
        # CORE ENGINES
        # ============================================

        self.risk_budget_engine = (
            risk_budget_engine
        )

        self.constraints = (
            constraints
        )

        self.vol_target_engine = (
            vol_target_engine
        )

        # ============================================
        # FORECASTING
        # ============================================

        self.forecast_engine = (

            forecast_engine

            if forecast_engine is not None

            else ExpectedReturnForecaster()

        )

        # ============================================
        # BLACK-LITTERMAN
        # ============================================

        self.black_litterman = (

            black_litterman

            if black_litterman is not None

            else BlackLittermanModel()

        )

        # ============================================
        # DIAGNOSTICS
        # ============================================

        self.last_forecasts = None

        self.last_posterior_returns = None

        self.last_regime = None

    def optimize(
        self,
        covariance,
        regime,
        asset_order,
        prices=None
    ):

        # ============================================
        # NORMALIZE REGIME
        # ============================================

        if isinstance(regime, str):

            regime = regime.lower()

            if regime in REGIME_RISK_BUDGETS:
                pass

            elif regime in (
                "expansion",
                "recovery",
                "slowdown",
                "recession",
            ):

                regime = PortfolioRegimeMapper.map_regime(
                    Regime(regime)
                )

            else:

                raise ValueError(
                    f"Unknown regime '{regime}'"
                )

        elif isinstance(regime, Regime):

            regime = PortfolioRegimeMapper.map_regime(
                regime
            )

        else:

            raise TypeError(
                f"Unsupported regime type: {type(regime)}"
            )

        self.last_regime = regime

        # ============================================
        # REGIME CONFIGURATION
        # ============================================

        for asset in asset_order:

            assert asset in (

                REGIME_RISK_BUDGETS[
                    regime
                ]

            ), (
                f"Missing risk budget "
                f"for asset '{asset}' "
                f"in regime '{regime}'"
            )

        risk_budget = np.array(

            [

                REGIME_RISK_BUDGETS[
                    regime
                ][asset]

                for asset
                in asset_order

            ],

            dtype=float

        )

        assert len(
            asset_order
        ) == len(
            risk_budget
        ), (
            "Asset order and risk budget mismatch"
        )

        assert len(
            risk_budget
        ) == covariance.shape[0], (
            f"Risk budget length "
            f"{len(risk_budget)} "
            f"!= covariance dimension "
            f"{covariance.shape[0]}"
        )

        assert np.isclose(
            risk_budget.sum(),
            1.0,
            atol=1e-6
        ), (
            f"Risk budgets do not sum to 1. "
            f"Got {risk_budget.sum()}"
        )

        target_vol = (

            REGIME_VOL_TARGETS[
                regime
            ]

        )

        max_leverage = (

            REGIME_MAX_LEVERAGE[
                regime
            ]

        )

        # ============================================
        # EXPECTED RETURN FORECASTS
        # ============================================

        posterior_returns = None

        self.last_forecasts = None

        self.last_posterior_returns = None

        if (

            prices is not None

            and

            self.forecast_engine is not None

            and

            self.black_litterman is not None

        ):

            forecasts = (

                self.forecast_engine
                .forecast(
                    prices
                )

            )

            self.last_forecasts = (
                forecasts.copy()
            )

            market_weights = (

                np.ones(
                    len(asset_order)
                )

                /

                len(asset_order)

            )

            posterior_returns = (

                self.black_litterman
                .posterior_returns(

                    covariance,

                    market_weights,

                    forecasts.values

                )

            )

            self.last_posterior_returns = (
                posterior_returns
            )

        # ============================================
        # RISK BUDGET OPTIMIZATION
        # ============================================

        weights = (

            self.risk_budget_engine
            .optimize(
                covariance,
                risk_budget
            )

        )

        # ============================================
        # PORTFOLIO CONSTRAINTS
        # ============================================

        constraint_result = (

            self.constraints
            .enforce(
                weights
            )

        )

        weights = np.asarray(

            constraint_result[
                "weights"
            ],

            dtype=float

        )

        cash_weight = float(

            constraint_result[
                "cash"
            ]

        )

        # ============================================
        # VOL TARGETING
        # ============================================

        if self.vol_target_engine:

            weights = (

                self.vol_target_engine
                .scale_weights(
                    weights,
                    covariance,
                    target_vol
                )

            )

        # ============================================
        # LEVERAGE CONTROL
        # ============================================

        gross_exposure = (
            weights.sum()
        )

        if gross_exposure > max_leverage:

            scale = (

                max_leverage

                /

                gross_exposure

            )

            weights *= scale

            gross_exposure = (
                weights.sum()
            )

        cash_weight = max(
            0.0,
            1.0 - gross_exposure
        )


        # ============================================
        # INVARIANT CHECKS
        # ============================================

        assert np.isfinite(
            weights
        ).all(), (
            "Non-finite weights detected"
        )

        assert (
            weights >= 0
        ).all(), (
            "Negative weights detected"
        )

        assert np.isfinite(
            cash_weight
        ), (
            "Invalid cash weight"
        )

        assert cash_weight >= 0, (
            "Negative cash allocation"
        )

        assert np.isclose(

            weights.sum()
            +
            cash_weight,

            1.0,

            atol=1e-6

        ), (
            f"Weights + cash != 1. "
            f"Got {weights.sum() + cash_weight}"
        )

        assert (

            weights.sum()

            <=

            max_leverage

            +

            1e-6

        ), (
            "Leverage limit exceeded"
        )

        # ============================================
        # RETURN RESULTS
        # ============================================
       
        risk_report = (
            RiskBudgetReport.create(
                asset_order,
                weights,
                covariance,
                risk_budget,
            )
        )
        
        return {

            "weights": weights,

            "cash": cash_weight,

            "regime": regime,

            "expected_returns":
                posterior_returns,

            "forecasts":
                self.last_forecasts,

            "risk_report":
                risk_report

        }
