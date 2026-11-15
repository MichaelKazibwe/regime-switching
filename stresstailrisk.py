"""
stresstailrisk.py

Canonical stress and tail-risk analytics.

R3E roadmap
-----------
R3E.2 : Historical VaR / CVaR / Expected Shortfall
R3E.3 : Deterministic portfolio stress
R3E.4 : Historical stress scenarios
R3E.5 : Factor stress
R3E.6 : Volatility / correlation stress
R3E.7 : Tail aggregation
R3E.8 : Risk report integration
R3E.9 : Risk Governor integration
R3E.10: Regression certification

Design principles
-----------------
* One responsibility per module.
* No competing legacy risk engines are promoted.
* Deterministic stress calculations are reproducible.
* Portfolio stress is calculated from asset-level shocks.
* Historical stress uses actual cross-sectional asset returns.
* Stress analytics do not approve, reject, or modify portfolios.
* Risk governance remains the responsibility of PortfolioRiskGovernor.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd

from basecomponent import BaseObject


# ======================================================================
# PUBLIC API
# ======================================================================

PUBLIC_METHODS = (
    "historical_var",
    "historical_cvar",
    "expected_shortfall",
    "analyze",
    "analyze_levels",
    "stress_portfolio",
    "stress_scenario",
    "historical_scenario",
    "historical_stress",
    "historical_stress_scenarios",
    "summary",
    "metadata",
    "health_check",
    "validate",
    "to_dict",
    "save_json",
)


# ======================================================================
# EXCEPTIONS
# ======================================================================


class StressTailRiskError(ValueError):
    """Raised when stress or tail-risk inputs are invalid."""


# ======================================================================
# RESULT OBJECTS
# ======================================================================


@dataclass(frozen=True)
class TailRiskResult:
    """Immutable historical VaR/CVaR/Expected Shortfall result."""

    observations: int
    tail_observations: int
    confidence: float
    var: float
    cvar: float
    expected_shortfall: float
    worst_return: float
    tail_mean_return: float
    frequency: str
    periods_per_year: int
    method: str


@dataclass(frozen=True)
class StressAssetResult:
    """Immutable deterministic stress result for one asset."""

    asset: str
    weight: float
    shock: float
    contribution: float
    pnl: float


@dataclass(frozen=True)
class StressResult:
    """Immutable deterministic portfolio stress result."""

    scenario: str
    initial_equity: float
    portfolio_return: float
    portfolio_loss: float
    stressed_equity: float
    gross_exposure: float
    net_exposure: float
    largest_loss_contributor: str | None
    largest_loss_contribution: float
    asset_results: tuple[StressAssetResult, ...]


@dataclass(frozen=True)
class HistoricalStressScenario:
    """
    Immutable historical portfolio stress scenario.

    The scenario is calculated by applying the current portfolio weights
    to the actual cross-sectional asset returns observed on one date.
    """

    date: Any
    portfolio_return: float
    portfolio_pnl: float
    portfolio_loss: float
    stressed_equity: float
    largest_loss_contributor: str | None
    asset_contributions: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class HistoricalStressResult:
    """Immutable collection of historical stress scenarios."""

    observations: int
    assets: int
    initial_equity: float
    scenarios: tuple[dict[str, Any], ...]
    worst_scenario: dict[str, Any]
    worst_loss: float
    worst_return: float
    average_worst_loss: float
    average_worst_return: float
    top_n: int
    method: str


# ======================================================================
# ENGINE
# ======================================================================


class StressTailRiskEngine(BaseObject):
    """
    Canonical stress and tail-risk engine.

    R3E.2
        Historical VaR / CVaR / Expected Shortfall.

    R3E.3
        Deterministic asset-level portfolio stress.

    R3E.4
        Historical cross-sectional portfolio stress scenarios.

    The engine is analytics-only.

    It does not:
        * alter portfolio weights,
        * optimize portfolios,
        * approve or reject trades,
        * act as a risk governor,
        * execute orders.
    """

    API_VERSION = "1.2.0"
    PHASE = "R3E.4"
    COMPONENT = "StressTailRiskEngine"

    DEFAULT_FREQUENCY = "daily"
    DEFAULT_PERIODS_PER_YEAR = 252

    TOLERANCE = 1e-12

    PUBLIC_METHODS = PUBLIC_METHODS

    # ------------------------------------------------------------------
    # INITIALIZATION
    # ------------------------------------------------------------------

    def __init__(
        self,
        frequency: str = DEFAULT_FREQUENCY,
        periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
    ) -> None:
        super().__init__()

        if not isinstance(frequency, str) or not frequency.strip():
            raise StressTailRiskError(
                "frequency must be a non-empty string."
            )

        if (
            not isinstance(periods_per_year, int)
            or isinstance(periods_per_year, bool)
            or periods_per_year <= 0
        ):
            raise StressTailRiskError(
                "periods_per_year must be a positive integer."
            )

        self.frequency = frequency.strip().lower()
        self.periods_per_year = periods_per_year

        self.analysis_count = 0
        self.stress_count = 0
        self.historical_stress_count = 0

        self.last_result: TailRiskResult | None = None
        self.last_stress_result: StressResult | None = None
        self.last_historical_stress_result: HistoricalStressResult | None = None

    # ==================================================================
    # COMMON VALIDATION HELPERS
    # ==================================================================

    @staticmethod
    def _validate_confidence(confidence: float) -> float:
        """Validate a VaR/CVaR confidence level."""

        try:
            value = float(confidence)
        except (TypeError, ValueError) as exc:
            raise StressTailRiskError(
                "confidence must be numeric."
            ) from exc

        if not np.isfinite(value):
            raise StressTailRiskError(
                "confidence must be finite."
            )

        if not 0.0 < value < 1.0:
            raise StressTailRiskError(
                "confidence must satisfy 0 < confidence < 1."
            )

        return value

    @staticmethod
    def _validate_initial_equity(
        initial_equity: float,
    ) -> float:
        """Validate positive initial portfolio equity."""

        try:
            equity = float(initial_equity)
        except (TypeError, ValueError) as exc:
            raise StressTailRiskError(
                "initial_equity must be numeric."
            ) from exc

        if not np.isfinite(equity):
            raise StressTailRiskError(
                "initial_equity must be finite."
            )

        if equity <= 0.0:
            raise StressTailRiskError(
                "initial_equity must be positive."
            )

        return equity

    @staticmethod
    def _prepare_returns(returns: Any) -> np.ndarray:
        """
        Convert returns into a finite 1D return vector.

        NaNs are removed.

        Infinite values and returns <= -100% are rejected.
        """

        if isinstance(returns, pd.DataFrame):
            if returns.shape[1] != 1:
                raise StressTailRiskError(
                    "returns DataFrame must contain exactly one column."
                )

            values = returns.iloc[:, 0].to_numpy(dtype=float)

        elif isinstance(returns, pd.Series):
            try:
                values = returns.to_numpy(dtype=float)
            except (TypeError, ValueError) as exc:
                raise StressTailRiskError(
                    "returns must be numeric and one-dimensional."
                ) from exc

        else:
            try:
                values = np.asarray(returns, dtype=float)
            except (TypeError, ValueError) as exc:
                raise StressTailRiskError(
                    "returns must be numeric and one-dimensional."
                ) from exc

        if values.ndim != 1:
            raise StressTailRiskError(
                "returns must be one-dimensional."
            )

        finite_mask = np.isfinite(values)

        if not finite_mask.all():
            raise StressTailRiskError(
                "returns must not contain non-finite values."
            )

        if values.size == 0:
            raise StressTailRiskError(
                "returns must contain at least one observation."
            )

        if np.any(values <= -1.0):
            raise StressTailRiskError(
                "returns cannot contain values <= -100%."
            )

        return values

    @staticmethod
    def _prepare_weights(
        weights: Mapping[str, float] | pd.Series,
    ) -> pd.Series:
        """Validate portfolio weights into a labelled float Series."""

        if isinstance(weights, pd.Series):
            result = weights.copy()
        elif isinstance(weights, Mapping):
            result = pd.Series(dict(weights), dtype=float)
        else:
            raise StressTailRiskError(
                "weights must be a mapping or pandas Series."
            )

        if result.empty:
            raise StressTailRiskError(
                "weights cannot be empty."
            )

        if result.index.has_duplicates:
            raise StressTailRiskError(
                "weights cannot contain duplicate asset names."
            )

        if result.index.isnull().any():
            raise StressTailRiskError(
                "weight asset names cannot contain null values."
            )

        try:
            result = result.astype(float)
        except (TypeError, ValueError) as exc:
            raise StressTailRiskError(
                "weights must be numeric."
            ) from exc

        if not np.isfinite(result.to_numpy(dtype=float)).all():
            raise StressTailRiskError(
                "weights must contain only finite values."
            )

        result.index = result.index.astype(str)

        return result

    @staticmethod
    def _prepare_shocks(
        shocks: Mapping[str, float] | pd.Series,
    ) -> pd.Series:
        """Validate asset-level deterministic shocks."""

        if isinstance(shocks, pd.Series):
            result = shocks.copy()
        elif isinstance(shocks, Mapping):
            result = pd.Series(dict(shocks), dtype=float)
        else:
            raise StressTailRiskError(
                "shocks must be a mapping or pandas Series."
            )

        if result.empty:
            raise StressTailRiskError(
                "shocks cannot be empty."
            )

        if result.index.has_duplicates:
            raise StressTailRiskError(
                "shocks cannot contain duplicate asset names."
            )

        if result.index.isnull().any():
            raise StressTailRiskError(
                "shock asset names cannot contain null values."
            )

        try:
            result = result.astype(float)
        except (TypeError, ValueError) as exc:
            raise StressTailRiskError(
                "shocks must be numeric."
            ) from exc

        if not np.isfinite(result.to_numpy(dtype=float)).all():
            raise StressTailRiskError(
                "shocks must contain only finite values."
            )

        result.index = result.index.astype(str)

        if np.any(result.to_numpy(dtype=float) <= -1.0):
            raise StressTailRiskError(
                "asset shocks cannot be <= -100%."
            )

        return result

    # ==================================================================
    # R3E.4 HISTORICAL MATRIX VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_historical_returns(
        returns: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Validate a cross-sectional historical asset-return matrix.

        Rows represent historical observations/dates.
        Columns represent assets.

        NaNs are allowed only when an entire row is unavailable; such
        rows are removed. Partial missing observations are rejected
        because a historical scenario must have a complete cross-section.
        """

        if not isinstance(returns, pd.DataFrame):
            raise StressTailRiskError(
                "Historical returns must be a pandas DataFrame."
            )

        if returns.empty:
            raise StressTailRiskError(
                "Historical returns cannot be empty."
            )

        if returns.shape[1] == 0:
            raise StressTailRiskError(
                "Historical returns must contain at least one asset."
            )

        if returns.columns.has_duplicates:
            raise StressTailRiskError(
                "Historical returns contain duplicate asset names."
            )

        if returns.columns.isnull().any():
            raise StressTailRiskError(
                "Historical return asset names cannot contain null values."
            )

        frame = returns.copy()

        try:
            frame = frame.apply(
                pd.to_numeric,
                errors="raise",
            )
        except (TypeError, ValueError) as exc:
            raise StressTailRiskError(
                "Historical returns must be numeric."
            ) from exc

        frame = frame.dropna(
            how="all",
        )

        if frame.empty:
            raise StressTailRiskError(
                "Historical returns contain no usable observations."
            )

        if frame.isna().any().any():
            raise StressTailRiskError(
                "Historical returns contain partial missing observations."
            )

        values = frame.to_numpy(dtype=float)

        if not np.isfinite(values).all():
            raise StressTailRiskError(
                "Historical returns contain non-finite values."
            )

        if np.any(values <= -1.0):
            raise StressTailRiskError(
                "Historical returns must be greater than -100%."
            )

        frame.columns = frame.columns.astype(str)

        return frame

    @staticmethod
    def _validate_historical_weights(
        weights: Mapping[str, float] | pd.Series,
        assets: pd.Index,
    ) -> pd.Series:
        """
        Validate and align portfolio weights to the historical
        return matrix.
        """

        series = StressTailRiskEngine._prepare_weights(
            weights,
        )

        asset_index = pd.Index(
            [str(asset) for asset in assets]
        )

        missing = [
            asset
            for asset in asset_index
            if asset not in series.index
        ]

        extra = [
            asset
            for asset in series.index
            if asset not in asset_index
        ]

        if missing:
            raise StressTailRiskError(
                "Weights are missing assets: "
                + ", ".join(map(str, missing))
            )

        if extra:
            raise StressTailRiskError(
                "Weights contain assets absent from returns: "
                + ", ".join(map(str, extra))
            )

        aligned = series.reindex(
            asset_index,
        )

        if not np.isfinite(
            aligned.to_numpy(dtype=float)
        ).all():
            raise StressTailRiskError(
                "Aligned weights contain non-finite values."
            )

        return aligned.astype(float)

    # ==================================================================
    # R3E.2 HISTORICAL VAR
    # ==================================================================

    def historical_var(
        self,
        returns: Any,
        confidence: float = 0.95,
    ) -> float:
        """Calculate historical VaR as a positive loss magnitude."""

        confidence = self._validate_confidence(
            confidence,
        )

        values = self._prepare_returns(
            returns,
        )

        alpha = 1.0 - confidence

        quantile = float(
            np.quantile(
                values,
                alpha,
                method="linear",
            )
        )

        return float(
            max(
                0.0,
                -quantile,
            )
        )

    # ==================================================================
    # R3E.2 HISTORICAL CVAR / EXPECTED SHORTFALL
    # ==================================================================

    def historical_cvar(
        self,
        returns: Any,
        confidence: float = 0.95,
    ) -> float:
        """
        Calculate historical CVaR / Expected Shortfall.

        The result is expressed as a positive tail-loss magnitude.
        """

        confidence = self._validate_confidence(
            confidence,
        )

        values = self._prepare_returns(
            returns,
        )

        alpha = 1.0 - confidence

        quantile = float(
            np.quantile(
                values,
                alpha,
                method="linear",
            )
        )

        tail = values[
            values <= quantile + self.TOLERANCE
        ]

        if tail.size == 0:
            raise StressTailRiskError(
                "Unable to construct historical tail."
            )

        return float(
            max(
                0.0,
                -float(np.mean(tail)),
            )
        )

    def expected_shortfall(
        self,
        returns: Any,
        confidence: float = 0.95,
    ) -> float:
        """Alias for historical CVaR / Expected Shortfall."""

        return self.historical_cvar(
            returns=returns,
            confidence=confidence,
        )

    # ==================================================================
    # R3E.2 COMPLETE HISTORICAL TAIL ANALYSIS
    # ==================================================================

    def analyze(
        self,
        returns: Any,
        confidence: float = 0.95,
    ) -> TailRiskResult:
        """Return complete historical tail-risk analysis."""

        confidence = self._validate_confidence(
            confidence,
        )

        values = self._prepare_returns(
            returns,
        )

        alpha = 1.0 - confidence

        quantile = float(
            np.quantile(
                values,
                alpha,
                method="linear",
            )
        )

        tail = values[
            values <= quantile + self.TOLERANCE
        ]

        if tail.size == 0:
            raise StressTailRiskError(
                "Unable to construct historical tail."
            )

        var = float(
            max(
                0.0,
                -quantile,
            )
        )

        cvar = float(
            max(
                0.0,
                -float(np.mean(tail)),
            )
        )

        result = TailRiskResult(
            observations=int(values.size),
            tail_observations=int(tail.size),
            confidence=confidence,
            var=var,
            cvar=cvar,
            expected_shortfall=cvar,
            worst_return=float(np.min(values)),
            tail_mean_return=float(np.mean(tail)),
            frequency=self.frequency,
            periods_per_year=self.periods_per_year,
            method="historical",
        )

        self.analysis_count += 1
        self.last_result = result

        return result

    def analyze_levels(
        self,
        returns: Any,
        confidences: tuple[float, ...] = (
            0.95,
            0.99,
        ),
    ) -> dict[str, dict[str, float]]:
        """Calculate VaR/CVaR at multiple confidence levels."""

        if not confidences:
            raise StressTailRiskError(
                "confidences cannot be empty."
            )

        results: dict[str, dict[str, float]] = {}

        for confidence in confidences:
            result = self.analyze(
                returns=returns,
                confidence=confidence,
            )

            key = f"{confidence:.2%}"

            results[key] = {
                "var": result.var,
                "cvar": result.cvar,
                "expected_shortfall": (
                    result.expected_shortfall
                ),
            }

        return results

    # ==================================================================
    # R3E.3 DETERMINISTIC PORTFOLIO STRESS
    # ==================================================================

    def stress_portfolio(
        self,
        weights: Mapping[str, float] | pd.Series,
        shocks: Mapping[str, float] | pd.Series,
        initial_equity: float = 1.0,
        scenario: str = "deterministic",
    ) -> StressResult:
        """
        Apply deterministic asset-level shocks to a portfolio.

        Portfolio return:

            sum(weight_i * shock_i)

        Asset P&L:

            initial_equity * weight_i * shock_i

        Portfolio P&L:

            sum(asset P&L)

        Portfolio loss is reported as a positive loss magnitude when
        the portfolio loses money and zero when it gains.
        """

        weight_series = self._prepare_weights(
            weights,
        )

        shock_series = self._prepare_shocks(
            shocks,
        )

        equity = self._validate_initial_equity(
            initial_equity,
        )

        if not isinstance(scenario, str) or not scenario.strip():
            raise StressTailRiskError(
                "scenario must be a non-empty string."
            )

        missing_shocks = [
            asset
            for asset in weight_series.index
            if asset not in shock_series.index
        ]

        if missing_shocks:
            raise StressTailRiskError(
                "Missing shocks for portfolio assets: "
                + ", ".join(missing_shocks)
            )

        extra_shocks = [
            asset
            for asset in shock_series.index
            if asset not in weight_series.index
        ]

        if extra_shocks:
            raise StressTailRiskError(
                "Shocks contain assets not present in weights: "
                + ", ".join(extra_shocks)
            )

        aligned_shocks = shock_series.reindex(
            weight_series.index,
        )

        contributions = (
            weight_series
            * aligned_shocks
        )

        pnl = contributions * equity

        portfolio_return = float(
            contributions.sum()
        )

        portfolio_pnl = float(
            pnl.sum()
        )

        portfolio_loss = float(
            max(
                0.0,
                -portfolio_pnl,
            )
        )

        stressed_equity = float(
            equity + portfolio_pnl
        )

        asset_results: list[StressAssetResult] = []

        for asset in weight_series.index:
            asset_contribution = float(
                contributions.loc[asset]
            )

            asset_pnl = float(
                pnl.loc[asset]
            )

            asset_results.append(
                StressAssetResult(
                    asset=str(asset),
                    weight=float(weight_series.loc[asset]),
                    shock=float(aligned_shocks.loc[asset]),
                    contribution=asset_contribution,
                    pnl=asset_pnl,
                )
            )

        largest = min(
            asset_results,
            key=lambda result: result.contribution,
        )

        result = StressResult(
            scenario=scenario.strip(),
            initial_equity=equity,
            portfolio_return=portfolio_return,
            portfolio_loss=portfolio_loss,
            stressed_equity=stressed_equity,
            gross_exposure=float(
                np.abs(weight_series).sum()
            ),
            net_exposure=float(
                weight_series.sum()
            ),
            largest_loss_contributor=(
                largest.asset
                if largest.contribution < 0.0
                else None
            ),
            largest_loss_contribution=float(
                largest.contribution
            ),
            asset_results=tuple(
                asset_results
            ),
        )

        self.stress_count += 1
        self.last_stress_result = result

        return result

    def stress_scenario(
        self,
        weights: Mapping[str, float] | pd.Series,
        shocks: Mapping[str, float] | pd.Series,
        initial_equity: float = 1.0,
        scenario: str = "deterministic",
    ) -> StressResult:
        """Explicit scenario-oriented alias for stress_portfolio."""

        return self.stress_portfolio(
            weights=weights,
            shocks=shocks,
            initial_equity=initial_equity,
            scenario=scenario,
        )

    # ==================================================================
    # R3E.4 SINGLE HISTORICAL SCENARIO
    # ==================================================================

    def historical_scenario(
        self,
        returns: pd.Series,
        weights: Mapping[str, float] | pd.Series,
        initial_equity: float = 1.0,
    ) -> dict[str, Any]:
        """
        Calculate one historical cross-sectional stress scenario.

        Parameters
        ----------
        returns:
            One row of cross-sectional asset returns.

        weights:
            Current portfolio weights.

        initial_equity:
            Portfolio NAV used to convert return contributions into P&L.
        """

        if not isinstance(returns, pd.Series):
            try:
                returns = pd.Series(
                    returns,
                    dtype=float,
                )
            except (TypeError, ValueError) as exc:
                raise StressTailRiskError(
                    "Historical scenario returns must be a Series or "
                    "Series-compatible mapping."
                ) from exc

        if returns.empty:
            raise StressTailRiskError(
                "Historical scenario returns cannot be empty."
            )

        if returns.index.has_duplicates:
            raise StressTailRiskError(
                "Historical scenario returns contain duplicate assets."
            )

        if returns.index.isnull().any():
            raise StressTailRiskError(
                "Historical scenario asset names cannot contain null values."
            )

        try:
            returns = pd.to_numeric(
                returns,
                errors="raise",
            )
        except (TypeError, ValueError) as exc:
            raise StressTailRiskError(
                "Historical scenario returns must be numeric."
            ) from exc

        if returns.isna().any():
            raise StressTailRiskError(
                "Historical scenario returns contain missing values."
            )

        values = returns.to_numpy(
            dtype=float,
        )

        if not np.isfinite(values).all():
            raise StressTailRiskError(
                "Historical scenario returns contain non-finite values."
            )

        if np.any(values <= -1.0):
            raise StressTailRiskError(
                "Historical scenario returns must be greater than -100%."
            )

        returns.index = returns.index.astype(str)

        weight_series = self._validate_historical_weights(
            weights,
            returns.index,
        )

        equity = self._validate_initial_equity(
            initial_equity,
        )

        asset_contributions: list[dict[str, Any]] = []

        for asset in returns.index:
            weight = float(
                weight_series.loc[asset]
            )

            asset_return = float(
                returns.loc[asset]
            )

            contribution = (
                weight
                * asset_return
            )

            pnl = (
                equity
                * contribution
            )

            asset_contributions.append(
                {
                    "asset": str(asset),
                    "weight": weight,
                    "return": asset_return,
                    "return_contribution": contribution,
                    "pnl": pnl,
                }
            )

        portfolio_return = float(
            sum(
                item["return_contribution"]
                for item in asset_contributions
            )
        )

        portfolio_pnl = float(
            equity
            * portfolio_return
        )

        portfolio_loss = float(
            max(
                0.0,
                -portfolio_pnl,
            )
        )

        stressed_equity = float(
            equity
            + portfolio_pnl
        )

        loss_contributors = sorted(
            asset_contributions,
            key=lambda item: item["pnl"],
        )

        largest_loss_contributor: str | None = None

        if loss_contributors:
            largest = loss_contributors[0]

            if largest["pnl"] < 0.0:
                largest_loss_contributor = (
                    largest["asset"]
                )

        return {
            "date": returns.name,
            "portfolio_return": portfolio_return,
            "portfolio_pnl": portfolio_pnl,
            "portfolio_loss": portfolio_loss,
            "stressed_equity": stressed_equity,
            "gross_exposure": float(
                np.abs(weight_series).sum()
            ),
            "net_exposure": float(
                weight_series.sum()
            ),
            "largest_loss_contributor":
                largest_loss_contributor,
            "asset_contributions":
                tuple(asset_contributions),
        }

    # ==================================================================
    # R3E.4 HISTORICAL STRESS SCENARIOS
    # ==================================================================

    def historical_stress(
        self,
        returns: pd.DataFrame,
        weights: Mapping[str, float] | pd.Series,
        initial_equity: float = 1.0,
        top_n: int = 10,
    ) -> dict[str, Any]:
        """
        Calculate portfolio stress across historical observations.

        Rows are historical dates/observations and columns are assets.
        Current portfolio weights are applied to each historical
        cross-section.

        The returned scenarios are ordered from largest portfolio loss
        to smallest portfolio loss.
        """

        frame = self._validate_historical_returns(
            returns,
        )

        weight_series = self._validate_historical_weights(
            weights,
            frame.columns,
        )

        equity = self._validate_initial_equity(
            initial_equity,
        )

        if (
            isinstance(top_n, bool)
            or not isinstance(top_n, (int, np.integer))
        ):
            raise StressTailRiskError(
                "top_n must be a positive integer."
            )

        top_n = int(top_n)

        if top_n <= 0:
            raise StressTailRiskError(
                "top_n must be a positive integer."
            )

        scenarios: list[dict[str, Any]] = []

        for date, row in frame.iterrows():
            scenario = self.historical_scenario(
                returns=row,
                weights=weight_series,
                initial_equity=equity,
            )

            scenarios.append(
                scenario
            )

        if not scenarios:
            raise StressTailRiskError(
                "No historical stress scenarios were generated."
            )

        scenarios.sort(
            key=lambda item: (
                item["portfolio_loss"],
                item["portfolio_return"],
            ),
            reverse=True,
        )

        selected = scenarios[:top_n]

        worst = selected[0]

        worst_losses = np.asarray(
            [
                item["portfolio_loss"]
                for item in selected
            ],
            dtype=float,
        )

        worst_returns = np.asarray(
            [
                item["portfolio_return"]
                for item in selected
            ],
            dtype=float,
        )

        result = HistoricalStressResult(
            observations=len(scenarios),
            assets=frame.shape[1],
            initial_equity=equity,
            scenarios=tuple(selected),
            worst_scenario=worst,
            worst_loss=float(
                worst["portfolio_loss"]
            ),
            worst_return=float(
                worst["portfolio_return"]
            ),
            average_worst_loss=float(
                np.mean(worst_losses)
            ),
            average_worst_return=float(
                np.mean(worst_returns)
            ),
            top_n=len(selected),
            method="historical_cross_sectional_stress",
        )

        self.historical_stress_count += 1
        self.last_historical_stress_result = result

        return asdict(result)

    def historical_stress_scenarios(
        self,
        returns: pd.DataFrame,
        weights: Mapping[str, float] | pd.Series,
        initial_equity: float = 1.0,
        top_n: int = 10,
    ) -> dict[str, Any]:
        """Explicit alias for historical stress scenario analysis."""

        return self.historical_stress(
            returns=returns,
            weights=weights,
            initial_equity=initial_equity,
            top_n=top_n,
        )

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(self) -> dict[str, Any]:
        """Return the current engine summary."""

        return {
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "frequency": self.frequency,
            "periods_per_year": self.periods_per_year,
            "analysis_count": self.analysis_count,
            "stress_count": self.stress_count,
            "historical_stress_count": (
                self.historical_stress_count
            ),
            "last_tail_result": (
                asdict(self.last_result)
                if self.last_result is not None
                else None
            ),
            "last_stress_result": (
                self._stress_result_to_dict(
                    self.last_stress_result
                )
                if self.last_stress_result is not None
                else None
            ),
            "last_historical_stress_result": (
                asdict(
                    self.last_historical_stress_result
                )
                if self.last_historical_stress_result is not None
                else None
            ),
        }

    # ==================================================================
    # SERIALIZATION
    # ==================================================================

    @staticmethod
    def _stress_result_to_dict(
        result: StressResult,
    ) -> dict[str, Any]:
        """Serialize a StressResult cleanly."""

        return asdict(result)

    def to_dict(self) -> dict[str, Any]:
        """Return serializable engine state."""

        return self.summary()

    # ==================================================================
    # METADATA
    # ==================================================================

    @property
    def metadata(self) -> dict[str, Any]:
        """Return engine metadata and risk-unit conventions."""

        return {
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "frequency": self.frequency,
            "periods_per_year": self.periods_per_year,
            "tail_risk_method": "historical",
            "stress_method": "deterministic_asset_shock",
            "historical_stress_method": (
                "historical_cross_sectional_stress"
            ),
            "var_definition": (
                "positive loss magnitude"
            ),
            "cvar_definition": (
                "positive tail-loss magnitude"
            ),
            "historical_stress_definition": (
                "Portfolio stress is calculated by applying "
                "current portfolio weights to the cross-sectional "
                "asset returns observed on each historical date."
            ),
            "historical_stress_pnl_definition": (
                "Asset P&L equals initial equity multiplied by "
                "portfolio weight multiplied by historical asset return."
            ),
            "historical_stress_loss_definition": (
                "Portfolio loss is the positive magnitude of a "
                "negative portfolio P&L and zero otherwise."
            ),
            "analytics_only": True,
            "governance": False,
            "execution": False,
        }

    # ==================================================================
    # VALIDATION
    # ==================================================================

    def validate(self) -> dict[str, Any]:
        """Validate engine configuration."""

        errors: list[str] = []

        if not isinstance(self.frequency, str):
            errors.append(
                "frequency must be a string."
            )
        elif not self.frequency.strip():
            errors.append(
                "frequency must not be empty."
            )

        if (
            not isinstance(self.periods_per_year, int)
            or isinstance(self.periods_per_year, bool)
            or self.periods_per_year <= 0
        ):
            errors.append(
                "periods_per_year must be a positive integer."
            )

        return {
            "valid": not errors,
            "errors": errors,
        }

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def health_check(self) -> dict[str, Any]:
        """Return engine health status."""

        validation = self.validate()

        return {
            "healthy": validation["valid"],
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "analysis_count": self.analysis_count,
            "stress_count": self.stress_count,
            "historical_stress_count": (
                self.historical_stress_count
            ),
            "errors": validation["errors"],
        }

    # ==================================================================
    # JSON PERSISTENCE
    # ==================================================================

    def save_json(self, path: str) -> None:
        """Persist engine state as JSON."""

        import json

        with open(
            path,
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                self.to_dict(),
                handle,
                indent=2,
                default=str,
            )


# ======================================================================
# SELF TEST
# ======================================================================


def test_stress_tail_risk() -> None:
    """Run deterministic R3E.2/R3E.3/R3E.4 module tests."""

    engine = StressTailRiskEngine()

    # ------------------------------------------------------------------
    # R3E.2 HISTORICAL TAIL TEST
    # ------------------------------------------------------------------

    returns = np.array(
        [
            0.02,
            0.01,
            -0.01,
            0.03,
            -0.02,
            0.01,
            -0.05,
            0.02,
            -0.03,
            0.01,
        ]
    )

    tail = engine.analyze(
        returns,
        confidence=0.90,
    )

    assert tail.observations == 10
    assert tail.var >= 0.0
    assert tail.cvar >= tail.var
    assert tail.expected_shortfall == tail.cvar

    # ------------------------------------------------------------------
    # R3E.3 DETERMINISTIC TWO-ASSET STRESS
    # ------------------------------------------------------------------

    weights = {
        "SPY": 0.60,
        "TLT": 0.40,
    }

    shocks = {
        "SPY": -0.20,
        "TLT": -0.05,
    }

    stress = engine.stress_portfolio(
        weights=weights,
        shocks=shocks,
        initial_equity=100_000.0,
        scenario="market_crash",
    )

    # 0.60 * -20% + 0.40 * -5% = -14%
    assert np.isclose(
        stress.portfolio_return,
        -0.14,
    )

    # -14% * €100,000 = -€14,000,
    # therefore positive loss magnitude = €14,000.
    assert np.isclose(
        stress.portfolio_loss,
        14_000.0,
    )

    assert np.isclose(
        stress.stressed_equity,
        86_000.0,
    )

    assert np.isclose(
        stress.gross_exposure,
        1.0,
    )

    assert np.isclose(
        stress.net_exposure,
        1.0,
    )

    assert (
        stress.largest_loss_contributor
        == "SPY"
    )

    # ------------------------------------------------------------------
    # R3E.3 SHORT POSITION TEST
    # ------------------------------------------------------------------

    stress = engine.stress_portfolio(
        weights={
            "SPY": 0.70,
            "TLT": -0.30,
        },
        shocks={
            "SPY": -0.20,
            "TLT": -0.10,
        },
        initial_equity=100_000.0,
        scenario="risk_off",
    )

    # 0.70*(-0.20) + (-0.30)*(-0.10) = -0.11
    assert np.isclose(
        stress.portfolio_return,
        -0.11,
    )

    assert np.isclose(
        stress.stressed_equity,
        89_000.0,
    )

    # ------------------------------------------------------------------
    # R3E.3 SCENARIO ALIAS TEST
    # ------------------------------------------------------------------

    alias_result = engine.stress_scenario(
        weights={
            "SPY": 1.0,
        },
        shocks={
            "SPY": -0.10,
        },
        initial_equity=1_000.0,
        scenario="single_asset",
    )

    assert np.isclose(
        alias_result.portfolio_return,
        -0.10,
    )

    assert np.isclose(
        alias_result.stressed_equity,
        900.0,
    )

    # ------------------------------------------------------------------
    # R3E.4 HISTORICAL STRESS TEST
    # ------------------------------------------------------------------

    historical_returns = pd.DataFrame(
        {
            "SPY": [
                0.01,
                -0.20,
                -0.05,
                0.02,
            ],
            "TLT": [
                0.00,
                -0.05,
                0.01,
                -0.01,
            ],
        },
        index=pd.to_datetime(
            [
                "2020-01-01",
                "2020-01-02",
                "2020-01-03",
                "2020-01-04",
            ]
        ),
    )

    historical = engine.historical_stress(
        returns=historical_returns,
        weights={
            "SPY": 0.60,
            "TLT": 0.40,
        },
        initial_equity=100_000.0,
        top_n=2,
    )

    assert historical["observations"] == 4
    assert historical["assets"] == 2
    assert historical["top_n"] == 2

    worst = historical["worst_scenario"]

    # 0.60*(-0.20) + 0.40*(-0.05) = -0.14
    assert np.isclose(
        worst["portfolio_return"],
        -0.14,
    )

    assert np.isclose(
        worst["portfolio_pnl"],
        -14_000.0,
    )

    assert np.isclose(
        worst["portfolio_loss"],
        14_000.0,
    )

    assert np.isclose(
        worst["stressed_equity"],
        86_000.0,
    )

    assert (
        worst["largest_loss_contributor"]
        == "SPY"
    )

    contribution_pnl = sum(
        item["pnl"]
        for item in worst["asset_contributions"]
    )

    assert np.isclose(
        contribution_pnl,
        worst["portfolio_pnl"],
    )

    scenario_losses = [
        scenario["portfolio_loss"]
        for scenario in historical["scenarios"]
    ]

    assert scenario_losses == sorted(
        scenario_losses,
        reverse=True,
    )

    # ------------------------------------------------------------------
    # R3E.4 HISTORICAL ALIAS TEST
    # ------------------------------------------------------------------

    alias_historical = (
        engine.historical_stress_scenarios(
            returns=historical_returns,
            weights={
                "SPY": 0.60,
                "TLT": 0.40,
            },
            initial_equity=100_000.0,
            top_n=2,
        )
    )

    assert np.isclose(
        alias_historical["worst_loss"],
        historical["worst_loss"],
    )

    # ------------------------------------------------------------------
    # R3E.4 VALIDATION TESTS
    # ------------------------------------------------------------------

    try:
        engine.stress_portfolio(
            weights={
                "SPY": 0.5,
                "TLT": 0.5,
            },
            shocks={
                "SPY": -0.10,
            },
        )
    except StressTailRiskError:
        pass
    else:
        raise AssertionError(
            "Missing deterministic shock should raise "
            "StressTailRiskError."
        )

    try:
        engine.historical_stress(
            returns=historical_returns,
            weights={
                "SPY": 0.60,
            },
        )
    except StressTailRiskError:
        pass
    else:
        raise AssertionError(
            "Missing historical weight should raise "
            "StressTailRiskError."
        )

    try:
        engine.historical_stress(
            returns=historical_returns,
            weights={
                "SPY": 0.60,
                "TLT": 0.40,
            },
            top_n=0,
        )
    except StressTailRiskError:
        pass
    else:
        raise AssertionError(
            "Invalid top_n should raise StressTailRiskError."
        )

    # ------------------------------------------------------------------
    # HEALTH / METADATA
    # ------------------------------------------------------------------

    health = engine.health_check()

    assert health["healthy"] is True

    metadata = engine.metadata

    assert metadata["analytics_only"] is True
    assert metadata["governance"] is False
    assert metadata["execution"] is False
    assert (
        metadata["historical_stress_method"]
        == "historical_cross_sectional_stress"
    )

    print(
        "StressTailRiskEngine R3E.2/R3E.3/R3E.4 tests passed."
    )


if __name__ == "__main__":
    test_stress_tail_risk()
    print("R3E.4 STATUS: PASS")
