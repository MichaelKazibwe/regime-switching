"""
========================================================================
VOLATILITY / CORRELATION STRESS
========================================================================

R3E.6 production stress engine.

Consumes an existing covariance matrix and applies deterministic
volatility and correlation shocks without modifying the caller's matrix.

Design contract
---------------
- Input covariance remains in its supplied/native frequency unless
  ``annualize=True`` is requested.
- Volatility shocks are multiplicative.
- Correlations are shocked additively and clipped to [-1, 1].
- The stressed covariance is reconstructed as D R D.
- The stressed covariance is symmetrized and validated as PSD.
- Portfolio risk is calculated with w' Sigma w.
- This module is analytics-only. It does not approve, reject, optimize,
  or execute trades.
========================================================================
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any, Mapping

import numpy as np

from core_constants import TRADING_DAYS


class VolatilityCorrelationStressError(Exception):
    """Base exception for R3E.6 stress calculations."""


@dataclass(frozen=True)
class VolatilityCorrelationStressResult:
    """Immutable R3E.6 portfolio stress result."""

    baseline_volatility: float
    stressed_volatility: float
    volatility_change: float
    volatility_change_pct: float
    baseline_variance: float
    stressed_variance: float
    variance_change: float
    baseline_gross_exposure: float
    baseline_net_exposure: float
    stressed_covariance: list[list[float]]
    stressed_volatilities: list[float]
    stressed_correlation: list[list[float]]
    asset_names: list[str]
    volatility_shocks: list[float]
    correlation_shock: float
    annualized: bool
    periods_per_year: int
    risk_frequency: str
    method: str


class VolatilityCorrelationStressEngine:
    """
    Deterministic volatility/correlation stress engine.
    """

    API_VERSION = "1.0.0"
    PHASE = "R3E.6"
    COMPONENT = "VolatilityCorrelationStressEngine"
    DEFAULT_PERIODS_PER_YEAR = TRADING_DAYS
    PUBLIC_METHODS = (
        "stress_covariance",
        "stress_portfolio",
        "stress_scenario",
        "summary",
        "metadata",
        "validate",
        "health_check",
        "to_dict",
        "save_json",
    )

    def __init__(
        self,
        periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
    ) -> None:
        self.periods_per_year = self._validate_periods_per_year(
            periods_per_year
        )
        self.last_result: VolatilityCorrelationStressResult | None = None
        self.last_covariance: np.ndarray | None = None

    @staticmethod
    def _validate_periods_per_year(value: Any) -> int:
        if isinstance(value, bool):
            raise VolatilityCorrelationStressError(
                "periods_per_year must be a positive integer."
            )
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise VolatilityCorrelationStressError(
                "periods_per_year must be a positive integer."
            ) from exc
        if result <= 0:
            raise VolatilityCorrelationStressError(
                "periods_per_year must be positive."
            )
        return result

    @staticmethod
    def _validate_covariance(covariance: Any) -> np.ndarray:
        matrix = np.asarray(covariance, dtype=float)
        if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
            raise VolatilityCorrelationStressError(
                "Covariance must be a non-empty square matrix."
            )
        if matrix.shape[0] == 0:
            raise VolatilityCorrelationStressError(
                "Covariance cannot be empty."
            )
        if not np.isfinite(matrix).all():
            raise VolatilityCorrelationStressError(
                "Covariance contains non-finite values."
            )
        matrix = (matrix + matrix.T) / 2.0
        eigenvalues = np.linalg.eigvalsh(matrix)
        if float(eigenvalues.min()) < -1e-10:
            raise VolatilityCorrelationStressError(
                "Covariance matrix must be positive semi-definite."
            )
        return matrix

    @staticmethod
    def _validate_weights(
        weights: Any,
        n_assets: int,
    ) -> np.ndarray:
        if isinstance(weights, Mapping):
            values = np.asarray(list(weights.values()), dtype=float)
        else:
            values = np.asarray(weights, dtype=float).reshape(-1)
        if values.size != n_assets:
            raise VolatilityCorrelationStressError(
                "Weights dimension does not match covariance."
            )
        if not np.isfinite(values).all():
            raise VolatilityCorrelationStressError(
                "Weights contain non-finite values."
            )
        return values

    @staticmethod
    def _validate_asset_names(
        asset_names: Any,
        n_assets: int,
    ) -> list[str]:
        if asset_names is None:
            return [f"Asset_{i}" for i in range(n_assets)]
        names = [str(name) for name in asset_names]
        if len(names) != n_assets:
            raise VolatilityCorrelationStressError(
                "asset_names dimension does not match covariance."
            )
        if len(set(names)) != len(names):
            raise VolatilityCorrelationStressError(
                "asset_names must be unique."
            )
        return names

    @staticmethod
    def _validate_volatility_shocks(
        shocks: Any,
        n_assets: int,
    ) -> np.ndarray:
        if shocks is None:
            values = np.zeros(n_assets, dtype=float)
        elif isinstance(shocks, Mapping):
            values = np.asarray(list(shocks.values()), dtype=float)
        else:
            values = np.asarray(shocks, dtype=float).reshape(-1)
        if values.size != n_assets:
            raise VolatilityCorrelationStressError(
                "Volatility-shock dimension does not match covariance."
            )
        if not np.isfinite(values).all():
            raise VolatilityCorrelationStressError(
                "Volatility shocks contain non-finite values."
            )
        if np.any(values <= -1.0):
            raise VolatilityCorrelationStressError(
                "Volatility shocks cannot reduce volatility to zero or below."
            )
        return values

    @staticmethod
    def _validate_correlation_shock(value: Any) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise VolatilityCorrelationStressError(
                "correlation_shock must be numeric."
            ) from exc
        if not np.isfinite(result):
            raise VolatilityCorrelationStressError(
                "correlation_shock must be finite."
            )
        return result

    @staticmethod
    def _covariance_to_correlation(
        covariance: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        variances = np.diag(covariance)
        if np.any(variances <= 0.0):
            raise VolatilityCorrelationStressError(
                "Covariance diagonal must be strictly positive."
            )
        volatilities = np.sqrt(variances)
        correlation = covariance / np.outer(volatilities, volatilities)
        correlation = (correlation + correlation.T) / 2.0
        np.fill_diagonal(correlation, 1.0)
        return volatilities, correlation

    @staticmethod
    def _project_psd_correlation(
        correlation: np.ndarray,
    ) -> np.ndarray:
        correlation = (correlation + correlation.T) / 2.0
        eigenvalues, eigenvectors = np.linalg.eigh(correlation)
        eigenvalues = np.maximum(eigenvalues, 0.0)
        projected = (
            eigenvectors
            @ np.diag(eigenvalues)
            @ eigenvectors.T
        )
        diagonal = np.sqrt(np.clip(np.diag(projected), 1e-15, None))
        projected = projected / np.outer(diagonal, diagonal)
        projected = (projected + projected.T) / 2.0
        np.fill_diagonal(projected, 1.0)
        return projected

    def stress_covariance(
        self,
        covariance: Any,
        volatility_shocks: Any = None,
        correlation_shock: float = 0.0,
        annualize: bool = False,
        periods_per_year: int | None = None,
    ) -> np.ndarray:
        """
        Reconstruct a stressed covariance matrix.

        Volatility shocks are percentages:
            0.25 -> +25% volatility.

        Correlation shock is additive:
            0.10 -> +0.10 correlation.
        """
        periods = (
            self.periods_per_year
            if periods_per_year is None
            else self._validate_periods_per_year(periods_per_year)
        )
        matrix = self._validate_covariance(covariance)
        native_vol, correlation = self._covariance_to_correlation(matrix)
        vol_shocks = self._validate_volatility_shocks(
            volatility_shocks,
            matrix.shape[0],
        )
        corr_shock = self._validate_correlation_shock(correlation_shock)

        stressed_vol = native_vol * (1.0 + vol_shocks)
        stressed_corr = correlation + corr_shock * (
            np.ones_like(correlation) - np.eye(correlation.shape[0])
        )
        stressed_corr = np.clip(stressed_corr, -1.0, 1.0)
        np.fill_diagonal(stressed_corr, 1.0)
        stressed_corr = self._project_psd_correlation(stressed_corr)

        stressed = (
            np.diag(stressed_vol)
            @ stressed_corr
            @ np.diag(stressed_vol)
        )
        stressed = (stressed + stressed.T) / 2.0

        if annualize:
            stressed = stressed * periods

        self.last_covariance = stressed.copy()
        return stressed

    def stress_portfolio(
        self,
        weights: Any,
        covariance: Any,
        volatility_shocks: Any = None,
        correlation_shock: float = 0.0,
        asset_names: Any = None,
        annualize: bool = False,
        periods_per_year: int | None = None,
    ) -> dict[str, Any]:
        """
        Calculate baseline and stressed portfolio volatility.
        """
        periods = (
            self.periods_per_year
            if periods_per_year is None
            else self._validate_periods_per_year(periods_per_year)
        )
        matrix = self._validate_covariance(covariance)
        weights_array = self._validate_weights(weights, matrix.shape[0])
        names = self._validate_asset_names(asset_names, matrix.shape[0])

        calculation_matrix = matrix * periods if annualize else matrix
        stressed = self.stress_covariance(
            matrix,
            volatility_shocks=volatility_shocks,
            correlation_shock=correlation_shock,
            annualize=annualize,
            periods_per_year=periods,
        )

        baseline_variance = float(
            weights_array @ calculation_matrix @ weights_array
        )
        stressed_variance = float(
            weights_array @ stressed @ weights_array
        )
        baseline_variance = max(baseline_variance, 0.0)
        stressed_variance = max(stressed_variance, 0.0)

        baseline_volatility = float(np.sqrt(baseline_variance))
        stressed_volatility = float(np.sqrt(stressed_variance))
        volatility_change = stressed_volatility - baseline_volatility
        if baseline_volatility > 0.0:
            volatility_change_pct = (
                volatility_change / baseline_volatility
            )
        else:
            volatility_change_pct = 0.0

        stressed_native = (
            stressed / periods
            if annualize
            else stressed
        )
        _, stressed_corr = self._covariance_to_correlation(
            stressed_native
        )
        native_vol, _ = self._covariance_to_correlation(matrix)
        vol_shocks = self._validate_volatility_shocks(
            volatility_shocks,
            matrix.shape[0],
        )

        result = VolatilityCorrelationStressResult(
            baseline_volatility=baseline_volatility,
            stressed_volatility=stressed_volatility,
            volatility_change=float(volatility_change),
            volatility_change_pct=float(volatility_change_pct),
            baseline_variance=baseline_variance,
            stressed_variance=stressed_variance,
            variance_change=float(
                stressed_variance - baseline_variance
            ),
            baseline_gross_exposure=float(
                np.sum(np.abs(weights_array))
            ),
            baseline_net_exposure=float(
                np.sum(weights_array)
            ),
            stressed_covariance=stressed.tolist(),
            stressed_volatilities=(
                native_vol * (1.0 + vol_shocks)
            ).tolist(),
            stressed_correlation=stressed_corr.tolist(),
            asset_names=names,
            volatility_shocks=vol_shocks.tolist(),
            correlation_shock=float(correlation_shock),
            annualized=bool(annualize),
            periods_per_year=periods,
            risk_frequency="annual" if annualize else "native",
            method="deterministic_volatility_correlation_shock",
        )
        self.last_result = result
        return asdict(result)

    def stress_scenario(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Alias for stress_portfolio."""
        return self.stress_portfolio(*args, **kwargs)

    def summary(self) -> dict[str, Any]:
        """Return the latest R3E.6 summary."""
        if self.last_result is None:
            return {
                "api_version": self.API_VERSION,
                "phase": self.PHASE,
                "component": self.COMPONENT,
                "result_available": False,
            }
        return {
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "component": self.COMPONENT,
            "result_available": True,
            "baseline_volatility": self.last_result.baseline_volatility,
            "stressed_volatility": self.last_result.stressed_volatility,
            "volatility_change": self.last_result.volatility_change,
            "volatility_change_pct": self.last_result.volatility_change_pct,
            "risk_frequency": self.last_result.risk_frequency,
            "annualized": self.last_result.annualized,
        }

    @property
    def metadata(self) -> dict[str, Any]:
        """Return production metadata."""
        return {
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "component": self.COMPONENT,
            "public_methods": list(self.PUBLIC_METHODS),
            "default_periods_per_year": self.DEFAULT_PERIODS_PER_YEAR,
            "risk_frequency_contract": (
                "native covariance frequency unless annualize=True"
            ),
            "volatility_shock_definition": (
                "multiplicative percentage shock"
            ),
            "correlation_shock_definition": (
                "additive off-diagonal correlation shock"
            ),
            "covariance_reconstruction": "D R D",
            "psd_validation": True,
            "analytics_only": True,
            "governance": False,
            "execution": False,
        }

    def validate(self) -> bool:
        """Validate engine configuration."""
        self._validate_periods_per_year(self.periods_per_year)
        return True

    def health_check(self) -> dict[str, Any]:
        """Return production health state."""
        try:
            healthy = self.validate()
            return {
                "status": "HEALTHY" if healthy else "UNHEALTHY",
                "healthy": healthy,
                "api_version": self.API_VERSION,
                "phase": self.PHASE,
                "component": self.COMPONENT,
                "periods_per_year": self.periods_per_year,
            }
        except Exception as exc:
            return {
                "status": "UNHEALTHY",
                "healthy": False,
                "api_version": self.API_VERSION,
                "phase": self.PHASE,
                "component": self.COMPONENT,
                "error": str(exc),
            }

    def to_dict(self) -> dict[str, Any]:
        """Serialize engine state."""
        return {
            "metadata": self.metadata,
            "summary": self.summary(),
            "last_result": (
                None
                if self.last_result is None
                else asdict(self.last_result)
            ),
        }

    def save_json(self, path: str) -> None:
        """Persist serialized engine state."""
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2)

    def __repr__(self) -> str:
        return (
            f"{self.COMPONENT}("
            f"api_version={self.API_VERSION!r}, "
            f"phase={self.PHASE!r})"
        )


def build_volatility_correlation_stress() -> VolatilityCorrelationStressEngine:
    """Construct the production R3E.6 engine."""
    return VolatilityCorrelationStressEngine()


def test_volatility_correlation_stress() -> None:
    covariance = np.array(
        [
            [0.04, 0.01],
            [0.01, 0.09],
        ],
        dtype=float,
    )
    weights = np.array([0.60, 0.40], dtype=float)

    engine = VolatilityCorrelationStressEngine()

    baseline = engine.stress_portfolio(
        weights,
        covariance,
        volatility_shocks=[0.0, 0.0],
        correlation_shock=0.0,
        asset_names=["SPY", "TLT"],
        annualize=False,
    )
    assert np.isclose(
        baseline["baseline_volatility"],
        baseline["stressed_volatility"],
    )

    stressed = engine.stress_portfolio(
        weights,
        covariance,
        volatility_shocks=[0.50, 0.25],
        correlation_shock=0.10,
        asset_names=["SPY", "TLT"],
        annualize=False,
    )
    assert stressed["stressed_volatility"] > stressed["baseline_volatility"]
    assert stressed["volatility_change"] > 0.0
    assert np.isclose(
        stressed["baseline_gross_exposure"],
        1.0,
    )
    assert np.isclose(
        stressed["baseline_net_exposure"],
        1.0,
    )

    matrix = np.asarray(
        stressed["stressed_covariance"],
        dtype=float,
    )
    assert np.allclose(matrix, matrix.T)
    assert np.linalg.eigvalsh(matrix).min() >= -1e-10

    annual = engine.stress_portfolio(
        weights,
        covariance,
        volatility_shocks=[0.0, 0.0],
        correlation_shock=0.0,
        annualize=True,
    )
    assert np.isclose(
        annual["baseline_volatility"],
        baseline["baseline_volatility"] * np.sqrt(TRADING_DAYS),
    )

    alias = engine.stress_scenario(
        weights,
        covariance,
        volatility_shocks=[0.0, 0.0],
    )
    assert np.isclose(
        alias["stressed_volatility"],
        baseline["stressed_volatility"],
    )

    try:
        engine.stress_portfolio(
            weights,
            covariance,
            volatility_shocks=[-1.0, 0.0],
        )
        raise AssertionError("Expected VolatilityCorrelationStressError")
    except VolatilityCorrelationStressError:
        pass

    try:
        engine.stress_portfolio(
            [0.5],
            covariance,
        )
        raise AssertionError("Expected VolatilityCorrelationStressError")
    except VolatilityCorrelationStressError:
        pass

    assert engine.validate()
    assert engine.health_check()["healthy"]
    assert engine.API_VERSION == "1.0.0"
    assert engine.PHASE == "R3E.6"
    assert "stress_portfolio" in engine.PUBLIC_METHODS

    print(
        "VolatilityCorrelationStressEngine R3E.6 tests passed."
    )
    print("R3E.6 STATUS: PASS")


if __name__ == "__main__":
    test_volatility_correlation_stress()
