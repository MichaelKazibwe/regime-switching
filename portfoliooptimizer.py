from __future__ import annotations

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
        black_litterman=None,
    ):
        """
        Production portfolio optimizer.

        Execution order
        ---------------
        1. Normalize regime.
        2. Validate covariance and asset universe.
        3. Retrieve regime-specific risk budgets.
        4. Retrieve regime-specific volatility target.
        5. Retrieve regime-specific leverage limit.
        6. Generate expected-return forecasts.
        7. Apply Black-Litterman posterior returns.
        8. Optimize risk-budget weights.
        9. Apply portfolio constraints.
        10. Apply volatility targeting.
        11. Apply regime leverage safety backstop.
        12. Calculate cash sleeve.
        13. Calculate final volatility diagnostics.
        14. Generate final risk report.
        15. Return production portfolio.
        """

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

        self.last_volatility_diagnostics = None

        self.last_weights = None

        self.last_cash = None

    # ========================================================
    # REGIME NORMALIZATION
    # ========================================================

    @staticmethod
    def _normalize_regime(
        regime,
    ):
        """
        Normalize all supported regime representations
        into the production portfolio regime key.
        """

        # --------------------------------------------
        # STRING REGIME
        # --------------------------------------------

        if isinstance(
            regime,
            str,
        ):

            normalized = (
                regime
                .lower()
                .strip()
            )

            # Already a production portfolio regime.
            if normalized in (
                REGIME_RISK_BUDGETS
            ):

                return normalized

            # Macro-regime aliases.
            if normalized in (
                "expansion",
                "recovery",
                "slowdown",
                "recession",
            ):

                return (
                    PortfolioRegimeMapper.map_regime(
                        Regime(normalized)
                    )
                )

            raise ValueError(
                f"Unknown regime '{regime}'. "
                "Expected one of: "
                f"{list(REGIME_RISK_BUDGETS.keys())} "
                "or a supported macro regime."
            )

        # --------------------------------------------
        # ENUM REGIME
        # --------------------------------------------

        if isinstance(
            regime,
            Regime,
        ):

            return (
                PortfolioRegimeMapper.map_regime(
                    regime
                )
            )

        # --------------------------------------------
        # INVALID TYPE
        # --------------------------------------------

        raise TypeError(
            "Unsupported regime type: "
            f"{type(regime)}"
        )

    # ========================================================
    # COVARIANCE VALIDATION
    # ========================================================

    @staticmethod
    def _validate_covariance(
        covariance,
        asset_order,
    ):
        """
        Validate and symmetrize the covariance matrix.
        """

        covariance = np.asarray(
            covariance,
            dtype=float,
        )

        if covariance.ndim != 2:

            raise ValueError(
                "Covariance must be a "
                "2-dimensional matrix."
            )

        if (
            covariance.shape[0]
            != covariance.shape[1]
        ):

            raise ValueError(
                "Covariance matrix must be square."
            )

        if (
            covariance.shape[0]
            != len(asset_order)
        ):

            raise ValueError(
                "Asset order length "
                f"{len(asset_order)} does not "
                "match covariance dimension "
                f"{covariance.shape[0]}."
            )

        if not np.isfinite(
            covariance
        ).all():

            raise ValueError(
                "Covariance contains "
                "non-finite values."
            )

        # --------------------------------------------
        # SYMMETRIZE
        # --------------------------------------------

        covariance = (
            covariance
            +
            covariance.T
        ) / 2.0

        # --------------------------------------------
        # POSITIVE SEMIDEFINITE CHECK
        # --------------------------------------------

        eigenvalues = np.linalg.eigvalsh(
            covariance
        )

        minimum_eigenvalue = float(
            eigenvalues.min()
        )

        if minimum_eigenvalue < -1e-10:

            raise ValueError(
                "Covariance matrix is not "
                "positive semidefinite. "
                f"Minimum eigenvalue="
                f"{minimum_eigenvalue:.6e}."
            )

        # --------------------------------------------
        # NUMERICAL REGULARIZATION
        # --------------------------------------------

        if minimum_eigenvalue < 1e-12:

            covariance = (
                covariance
                +
                np.eye(
                    covariance.shape[0]
                )
                * 1e-12
            )

        return covariance

    # ========================================================
    # RISK BUDGET VALIDATION
    # ========================================================

    @staticmethod
    def _validate_risk_budgets(
        risk_budget,
        asset_order,
    ):
        """
        Validate regime-specific risk budgets.
        """

        risk_budget = np.asarray(
            risk_budget,
            dtype=float,
        ).reshape(-1)

        if risk_budget.shape != (
            len(asset_order),
        ):

            raise ValueError(
                "Risk budget shape "
                f"{risk_budget.shape} does not "
                "match asset universe size "
                f"{len(asset_order)}."
            )

        if not np.isfinite(
            risk_budget
        ).all():

            raise ValueError(
                "Risk budgets contain "
                "non-finite values."
            )

        if np.any(
            risk_budget < 0.0
        ):

            raise ValueError(
                "Risk budgets cannot "
                "be negative."
            )

        budget_sum = float(
            risk_budget.sum()
        )

        if not np.isclose(
            budget_sum,
            1.0,
            atol=1e-6,
        ):

            raise ValueError(
                "Selected risk budgets must "
                "sum to 1. "
                f"Got {budget_sum}."
            )

        return risk_budget

    # ========================================================
    # OPTIMIZATION
    # ========================================================

    def optimize(
        self,
        covariance,
        regime,
        asset_order,
        prices=None,
    ):
        """
        Construct the production portfolio.

        Returns
        -------
        dict
            {
                "weights": np.ndarray,
                "cash": float,
                "regime": str,
                "expected_returns": ...,
                "forecasts": ...,
                "risk_report": ...,
                "volatility_diagnostics": ...,
            }
        """

        # ============================================
        # RESET PER-RUN DIAGNOSTICS
        # ============================================

        self.last_forecasts = None

        self.last_posterior_returns = None

        self.last_volatility_diagnostics = None

        self.last_weights = None

        self.last_cash = None

        # ============================================
        # NORMALIZE REGIME
        # ============================================

        regime = (
            self._normalize_regime(
                regime
            )
        )

        self.last_regime = regime

        # ============================================
        # ASSET UNIVERSE VALIDATION
        # ============================================

        if not asset_order:

            raise ValueError(
                "asset_order cannot be empty."
            )

        # Prevent duplicate assets from creating
        # ambiguous weight/risk mappings.

        if len(
            set(asset_order)
        ) != len(asset_order):

            raise ValueError(
                "asset_order contains "
                "duplicate assets."
            )

        # ============================================
        # COVARIANCE VALIDATION
        # ============================================

        covariance = (
            self._validate_covariance(
                covariance,
                asset_order,
            )
        )

        # ============================================
        # REGIME CONFIGURATION
        # ============================================

        if regime not in (
            REGIME_VOL_TARGETS
        ):

            raise ValueError(
                "No volatility target configured "
                f"for regime '{regime}'."
            )

        if regime not in (
            REGIME_MAX_LEVERAGE
        ):

            raise ValueError(
                "No maximum leverage configured "
                f"for regime '{regime}'."
            )

        target_vol = float(
            REGIME_VOL_TARGETS[
                regime
            ]
        )

        max_leverage = float(
            REGIME_MAX_LEVERAGE[
                regime
            ]
        )

        if (
            not np.isfinite(
                target_vol
            )
            or target_vol <= 0.0
        ):

            raise ValueError(
                "Regime target volatility must "
                "be positive and finite. "
                f"Got {target_vol}."
            )

        if (
            not np.isfinite(
                max_leverage
            )
            or max_leverage <= 0.0
        ):

            raise ValueError(
                "Regime maximum leverage must "
                "be positive and finite. "
                f"Got {max_leverage}."
            )

        # ============================================
        # RISK BUDGET CONFIGURATION
        # ============================================

        # RiskBudgetEngine remains the authoritative
        # source of regime-specific risk budgets.

        target_budgets = (
            self.risk_budget_engine
            .get_target_budgets(
                regime,
                asset_order,
            )
        )

        # Ensure every requested asset has a budget.

        missing_assets = [
            asset
            for asset in asset_order
            if asset not in target_budgets
        ]

        if missing_assets:

            raise ValueError(
                "Risk budget engine did not "
                "provide budgets for assets: "
                f"{missing_assets}"
            )

        risk_budget = (
            self._validate_risk_budgets(
                [
                    target_budgets[
                        asset
                    ]
                    for asset in asset_order
                ],
                asset_order,
            )
        )

        # ============================================
        # EXPECTED RETURN FORECASTS
        # ============================================

        posterior_returns = None

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

            # ----------------------------------------
            # FORECAST VALIDATION
            # ----------------------------------------

            if forecasts is None:

                raise ValueError(
                    "Expected-return forecaster "
                    "returned None."
                )

            if not hasattr(
                forecasts,
                "values",
            ):

                raise TypeError(
                    "Expected-return forecasts "
                    "must expose a 'values' attribute."
                )

            forecast_values = np.asarray(
                forecasts.values,
                dtype=float,
            ).reshape(-1)

            if forecast_values.size != (
                len(asset_order)
            ):

                raise ValueError(
                    "Forecast vector length "
                    f"{forecast_values.size} does not "
                    "match asset universe size "
                    f"{len(asset_order)}."
                )

            if not np.isfinite(
                forecast_values
            ).all():

                raise ValueError(
                    "Expected-return forecasts "
                    "contain non-finite values."
                )

            # ----------------------------------------
            # STORE FORECASTS
            # ----------------------------------------

            if hasattr(
                forecasts,
                "copy",
            ):

                self.last_forecasts = (
                    forecasts.copy()
                )

            else:

                self.last_forecasts = (
                    forecasts
                )

            # ----------------------------------------
            # MARKET WEIGHTS
            # ----------------------------------------

            market_weights = (
                np.ones(
                    len(asset_order),
                    dtype=float,
                )
                /
                float(
                    len(asset_order)
                )
            )

            # ----------------------------------------
            # BLACK-LITTERMAN POSTERIOR
            # ----------------------------------------

            posterior_returns = (
                self.black_litterman
                .posterior_returns(
                    covariance,
                    market_weights,
                    forecast_values,
                )
            )

            posterior_returns = np.asarray(
                posterior_returns,
                dtype=float,
            ).reshape(-1)

            if posterior_returns.size != (
                len(asset_order)
            ):

                raise ValueError(
                    "Black-Litterman posterior "
                    "return vector length "
                    f"{posterior_returns.size} does not "
                    "match asset universe size "
                    f"{len(asset_order)}."
                )

            if not np.isfinite(
                posterior_returns
            ).all():

                raise ValueError(
                    "Black-Litterman posterior "
                    "returns contain non-finite values."
                )

            self.last_posterior_returns = (
                posterior_returns.copy()
            )

        # ============================================
        # RISK-BUDGET OPTIMIZATION
        # ============================================

        weights = (
            self.risk_budget_engine
            .optimize(
                covariance,
                risk_budget,
            )
        )

        weights = np.asarray(
            weights,
            dtype=float,
        ).reshape(-1)

        # ============================================
        # RISK-BUDGET OUTPUT VALIDATION
        # ============================================

        if weights.size != (
            len(asset_order)
        ):

            raise ValueError(
                "Risk-budget optimizer returned "
                f"{weights.size} weights; "
                "expected "
                f"{len(asset_order)}."
            )

        if not np.isfinite(
            weights
        ).all():

            raise ValueError(
                "Risk-budget optimizer returned "
                "non-finite weights."
            )

        if np.any(
            weights < -1e-10
        ):

            raise ValueError(
                "Risk-budget optimizer returned "
                "negative weights."
            )

        weights = np.maximum(
            weights,
            0.0,
        )

        weight_sum = float(
            weights.sum()
        )

        if not np.isclose(
            weight_sum,
            1.0,
            atol=1e-6,
        ):

            raise ValueError(
                "Risk-budget optimizer returned "
                f"weights summing to {weight_sum}."
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

        if not isinstance(
            constraint_result,
            dict,
        ):

            raise TypeError(
                "Portfolio constraints must "
                "return a dictionary."
            )

        if "weights" not in (
            constraint_result
        ):

            raise ValueError(
                "Portfolio constraints result "
                "does not contain 'weights'."
            )

        if "cash" not in (
            constraint_result
        ):

            raise ValueError(
                "Portfolio constraints result "
                "does not contain 'cash'."
            )

        weights = np.asarray(
            constraint_result[
                "weights"
            ],
            dtype=float,
        ).reshape(-1)

        constraint_cash = float(
            constraint_result[
                "cash"
            ]
        )

        # ============================================
        # POST-CONSTRAINT VALIDATION
        # ============================================

        if weights.size != (
            len(asset_order)
        ):

            raise ValueError(
                "Constraint engine returned "
                f"{weights.size} weights; "
                "expected "
                f"{len(asset_order)}."
            )

        if not np.isfinite(
            weights
        ).all():

            raise ValueError(
                "Constraint engine returned "
                "non-finite weights."
            )

        if np.any(
            weights < -1e-10
        ):

            raise ValueError(
                "Constraint engine returned "
                "negative weights."
            )

        if (
            not np.isfinite(
                constraint_cash
            )
        ):

            raise ValueError(
                "Constraint engine returned "
                "invalid cash weight."
            )

        if constraint_cash < -1e-10:

            raise ValueError(
                "Constraint engine returned "
                "negative cash weight."
            )

        weights = np.maximum(
            weights,
            0.0,
        )

        # ============================================
        # VOLATILITY TARGETING
        # ============================================

        volatility_engine_used = (
            self.vol_target_engine
            is not None
        )

        if volatility_engine_used:

            weights = (
                self.vol_target_engine
                .scale_weights(
                    weights,
                    covariance,
                    target_vol,
                    max_leverage=max_leverage,
                )
            )

            weights = np.asarray(
                weights,
                dtype=float,
            ).reshape(-1)

        # ============================================
        # POST-VOLATILITY WEIGHT VALIDATION
        # ============================================

        if weights.size != (
            len(asset_order)
        ):

            raise ValueError(
                "Volatility-targeting engine "
                "returned an invalid number "
                "of weights. "
                f"Expected {len(asset_order)}, "
                f"got {weights.size}."
            )

        if not np.isfinite(
            weights
        ).all():

            raise ValueError(
                "Volatility-targeting engine "
                "returned non-finite weights."
            )

        if np.any(
            weights < -1e-10
        ):

            raise ValueError(
                "Volatility-targeting engine "
                "returned negative weights."
            )

        weights = np.maximum(
            weights,
            0.0,
        )

        # ============================================
        # LEVERAGE CONTROL
        # ============================================

        gross_exposure = float(
            np.sum(
                np.abs(
                    weights
                )
            )
        )

        if not np.isfinite(
            gross_exposure
        ):

            raise ValueError(
                "Gross exposure became "
                "non-finite."
            )

        leverage_binding = False

        # --------------------------------------------
        # REGIME LEVERAGE SAFETY BACKSTOP
        # --------------------------------------------
        #
        # The volatility engine has already received
        # max_leverage. This is an independent final
        # safety invariant.
        #

        if (
            gross_exposure
            >
            max_leverage + 1e-10
        ):

            if gross_exposure <= 0.0:

                raise ValueError(
                    "Invalid gross exposure "
                    "during leverage enforcement."
                )

            scale = (
                max_leverage
                /
                gross_exposure
            )

            weights *= scale

            leverage_binding = True

            gross_exposure = float(
                np.sum(
                    np.abs(
                        weights
                    )
                )
            )

        # --------------------------------------------
        # FINAL LEVERAGE INVARIANT
        # --------------------------------------------

        if (
            gross_exposure
            >
            max_leverage + 1e-8
        ):

            raise ValueError(
                "Portfolio remains above "
                "maximum regime leverage "
                "after enforcement. "
                f"Gross exposure="
                f"{gross_exposure:.12f}; "
                f"maximum leverage="
                f"{max_leverage:.12f}."
            )

        # ============================================
        # CASH SLEEVE
        # ============================================

        # IMPORTANT:
        #
        # We deliberately calculate cash from final
        # gross exposure. We do NOT renormalize the
        # weights back to 100%.
        #
        # Therefore:
        #
        # Bull    -> max leverage 1.00 -> cash ~ 0
        # Neutral -> max leverage 0.75 -> cash ~ 0.25
        # Crisis  -> max leverage 0.40 -> cash ~ 0.60
        #

        cash_weight = max(
            0.0,
            1.0 - gross_exposure,
        )

        if abs(
            cash_weight
        ) < 1e-12:

            cash_weight = 0.0

        if not np.isfinite(
            cash_weight
        ):

            raise ValueError(
                "Cash weight became "
                "non-finite."
            )

        if cash_weight < 0.0:

            cash_weight = 0.0

        # ============================================
        # FINAL EXPOSURE
        # ============================================

        final_gross_exposure = float(
            np.sum(
                np.abs(
                    weights
                )
            )
        )

        if not np.isfinite(
            final_gross_exposure
        ):

            raise ValueError(
                "Final gross exposure "
                "is non-finite."
            )

        if (
            final_gross_exposure
            >
            max_leverage + 1e-8
        ):

            raise ValueError(
                "Final portfolio exceeds "
                "regime maximum leverage. "
                f"Gross exposure="
                f"{final_gross_exposure:.12f}; "
                f"maximum="
                f"{max_leverage:.12f}."
            )

        # ============================================
        # PORTFOLIO + CASH INVARIANT
        # ============================================

        total_exposure = (
            final_gross_exposure
            +
            cash_weight
        )

        if not np.isfinite(
            total_exposure
        ):

            raise ValueError(
                "Total portfolio exposure "
                "is non-finite."
            )

        if not np.isclose(
            total_exposure,
            1.0,
            atol=1e-6,
        ):

            raise ValueError(
                "Weights + cash must equal 1. "
                f"Got {total_exposure:.12f}."
            )

        # ============================================
        # FINAL PORTFOLIO VOLATILITY
        # ============================================

        final_variance = float(
            weights
            @ covariance
            @ weights
        )

        if not np.isfinite(
            final_variance
        ):

            raise ValueError(
                "Final portfolio variance "
                "is non-finite."
            )

        if final_variance < 0.0:

            if final_variance > -1e-12:

                final_variance = 0.0

            else:

                raise ValueError(
                    "Final portfolio variance "
                    "is materially negative: "
                    f"{final_variance}."
                )

        final_volatility = float(
            np.sqrt(
                final_variance
            )
        )

        if not np.isfinite(
            final_volatility
        ):

            raise ValueError(
                "Final portfolio volatility "
                "is non-finite."
            )

        # ============================================
        # VOLATILITY DIAGNOSTICS
        # ============================================

        volatility_shortfall = max(
            0.0,
            target_vol
            -
            final_volatility,
        )

        volatility_error = (
            final_volatility
            -
            target_vol
        )

        volatility_target_achieved = bool(
            np.isclose(
                final_volatility,
                target_vol,
                rtol=1e-6,
                atol=1e-8,
            )
        )

        # --------------------------------------------
        # TRY TO RETRIEVE ENGINE RESULT
        # --------------------------------------------

        volatility_engine_result = None

        if volatility_engine_used:

            if hasattr(
                self.vol_target_engine,
                "get_last_result",
            ):

                volatility_engine_result = (
                    self.vol_target_engine
                    .get_last_result()
                )

            elif hasattr(
                self.vol_target_engine,
                "last_result",
            ):

                volatility_engine_result = (
                    self.vol_target_engine
                    .last_result
                )

                # ============================================
        # BUILD VOLATILITY DIAGNOSTICS
        # ============================================

        volatility_diagnostics = {
            "status": (
                "ENGINE"
                if volatility_engine_used
                else "CALCULATED"
            ),

            "engine_result": (
                volatility_engine_result
            ),

            "original_volatility": None,

            "target_volatility": float(
                target_vol
            ),

            "final_volatility": (
                final_volatility
            ),

            "volatility_error": (
                volatility_error
            ),

            "volatility_shortfall": (
                volatility_shortfall
            ),

            "target_achieved": (
                volatility_target_achieved
            ),

            "maximum_leverage": (
                float(max_leverage)
            ),

            "gross_exposure": (
                final_gross_exposure
            ),

            "cash_weight": (
                cash_weight
            ),

            # This is deliberately populated below
            # from the authoritative volatility-engine result.
            "leverage_binding": (
                bool(leverage_binding)
            ),

            "required_leverage": None,
        }

        # ============================================
        # INCORPORATE ENGINE DIAGNOSTICS
        # ============================================

        if (
            volatility_engine_result
            is not None
        ):

            # ----------------------------------------
            # ORIGINAL VOLATILITY
            # ----------------------------------------

            if hasattr(
                volatility_engine_result,
                "original_volatility",
            ):

                volatility_diagnostics[
                    "original_volatility"
                ] = float(
                    volatility_engine_result
                    .original_volatility
                )

            # ----------------------------------------
            # SCALE FACTOR
            # ----------------------------------------

            if hasattr(
                volatility_engine_result,
                "scale_factor",
            ):

                volatility_diagnostics[
                    "scale_factor"
                ] = float(
                    volatility_engine_result
                    .scale_factor
                )

            # ----------------------------------------
            # REQUIRED LEVERAGE
            # ----------------------------------------

            if hasattr(
                volatility_engine_result,
                "required_leverage",
            ):

                volatility_diagnostics[
                    "required_leverage"
                ] = float(
                    volatility_engine_result
                    .required_leverage
                )

            # ----------------------------------------
            # TARGET ACHIEVEMENT
            # ----------------------------------------

            if hasattr(
                volatility_engine_result,
                "target_achieved",
            ):

                volatility_diagnostics[
                    "target_achieved"
                ] = bool(
                    volatility_engine_result
                    .target_achieved
                )

            # ----------------------------------------
            # LEVERAGE BINDING
            # ----------------------------------------
            #
            # IMPORTANT:
            #
            # The volatility-targeting engine is the
            # authoritative source for this state.
            #
            # Do NOT reconstruct leverage_binding from
            # final_gross_exposure == max_leverage.
            #
            # The engine determines whether the requested
            # volatility target required more leverage than
            # the configured maximum.
            #

            if hasattr(
                volatility_engine_result,
                "leverage_binding",
            ):

                volatility_diagnostics[
                    "leverage_binding"
                ] = bool(
                    volatility_engine_result
                    .leverage_binding
                )

            # ----------------------------------------
            # ENGINE DIAGNOSTICS PAYLOAD
            # ----------------------------------------

            if hasattr(
                volatility_engine_result,
                "diagnostics",
            ):

                engine_diagnostics = (
                    volatility_engine_result
                    .diagnostics
                )

                if isinstance(
                    engine_diagnostics,
                    dict,
                ):

                    volatility_diagnostics[
                        "engine_diagnostics"
                    ] = dict(
                        engine_diagnostics
                    )

        # ============================================
        # RISK REPORT
        # ============================================

        risk_report = (
            RiskBudgetReport.create(
                asset_order,
                weights,
                covariance,
                risk_budget,
            )
        )

        # ============================================
        # FINAL PRODUCTION INVARIANTS
        # ============================================

        assert np.isfinite(
            weights
        ).all(), (
            "Non-finite final weights detected."
        )

        assert (
            weights >= -1e-10
        ).all(), (
            "Negative final weights detected."
        )

        assert np.isfinite(
            cash_weight
        ), (
            "Invalid final cash weight."
        )

        assert (
            cash_weight >= -1e-10
        ), (
            "Negative final cash allocation."
        )

        assert np.isfinite(
            final_gross_exposure
        ), (
            "Invalid final gross exposure."
        )

        assert (
            final_gross_exposure
            <=
            max_leverage
            +
            1e-8
        ), (
            "Final leverage limit exceeded. "
            f"Gross exposure="
            f"{final_gross_exposure:.8f}; "
            f"maximum="
            f"{max_leverage:.8f}."
        )

        assert np.isclose(
            final_gross_exposure
            +
            cash_weight,
            1.0,
            atol=1e-6,
        ), (
            "Final weights + cash != 1. "
            f"Got "
            f"{final_gross_exposure + cash_weight:.12f}"
        )

        assert np.isfinite(
            final_volatility
        ), (
            "Final volatility is non-finite."
        )

        # ============================================
        # STORE FINAL STATE
        # ============================================

        self.last_weights = (
            weights.copy()
        )

        self.last_cash = (
            float(
                cash_weight
            )
        )

        self.last_volatility_diagnostics = (
            volatility_diagnostics
        )

        # ============================================
        # RETURN PRODUCTION PORTFOLIO
        # ============================================

        return {
            "weights": (
                weights
            ),

            "cash": (
                cash_weight
            ),

            "regime": (
                regime
            ),

            "expected_returns": (
                posterior_returns
            ),

            "forecasts": (
                self.last_forecasts
            ),

            "risk_report": (
                risk_report
            ),

            "volatility_diagnostics": (
                volatility_diagnostics
            ),
        }