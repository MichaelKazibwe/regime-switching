"""
===============================================================================
FACTOR STRESS RISK ENGINE
===============================================================================

R3E.5 — deterministic systematic-factor stress analytics.

This module consumes the existing FactorExposureModel output rather than
creating a competing factor model.  Given asset factor loadings, portfolio
weights, and explicit factor shocks, it computes implied asset shocks,
portfolio P&L, loss, and factor/asset loss contributions.

Scope
-----
* deterministic factor shocks only;
* systematic factor contribution only;
* analytics only — no optimization, approval, governance, or execution;
* no replacement for FactorExposureModel or FactorCovariance.

The factor model convention is:

    asset_return = beta @ factor_shock

and portfolio factor return is:

    portfolio_return = exposure @ factor_shock

where exposure = weights.T @ beta.
===============================================================================
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd


class FactorStressRiskError(ValueError):
    """Raised when factor-stress inputs are invalid."""


@dataclass(frozen=True)
class FactorAssetStressResult:
    """Stress result for one asset."""

    asset: str
    weight: float
    implied_return: float
    pnl: float
    loss: float


@dataclass(frozen=True)
class FactorStressResult:
    """Structured deterministic factor-stress result."""

    method: str
    initial_equity: float
    portfolio_return: float
    portfolio_pnl: float
    portfolio_loss: float
    stressed_equity: float
    gross_exposure: float
    net_exposure: float
    factor_exposures: dict[str, float]
    factor_shocks: dict[str, float]
    factor_pnl_contributions: dict[str, float]
    factor_loss_contributions: dict[str, float]
    asset_results: tuple[FactorAssetStressResult, ...]
    largest_loss_contributor: str | None
    largest_factor_loss_contributor: str | None


class FactorStressRiskEngine:
    """Deterministic factor-stress analytics built on existing factor loadings."""

    API_VERSION = "1.0.0"
    PHASE = "R3E.5"
    COMPONENT = "FactorStressRiskEngine"
    PUBLIC_METHODS = (
        "factor_stress",
        "stress_scenario",
        "summary",
        "metadata",
        "health_check",
        "validate",
        "to_dict",
        "save_json",
    )

    def __init__(self) -> None:
        self.last_result: FactorStressResult | None = None
        self.factor_stress_count = 0

    @staticmethod
    def _validate_weights(weights: Mapping[str, float] | pd.Series) -> pd.Series:
        if isinstance(weights, pd.Series):
            series = weights.copy()
        elif isinstance(weights, Mapping):
            series = pd.Series(dict(weights), dtype=float)
        else:
            raise TypeError("weights must be a mapping or pandas Series.")

        if series.empty:
            raise FactorStressRiskError("weights cannot be empty.")
        if series.index.duplicated().any():
            raise FactorStressRiskError("weights contain duplicate assets.")

        try:
            series = series.astype(float)
        except (TypeError, ValueError) as exc:
            raise FactorStressRiskError("weights must be numeric.") from exc

        if not np.isfinite(series.to_numpy()).all():
            raise FactorStressRiskError("weights must be finite.")

        if not all(str(asset) for asset in series.index):
            raise FactorStressRiskError("asset names must be non-empty.")

        series.index = series.index.astype(str)
        return series

    @staticmethod
    def _validate_loadings(
        factor_loadings: pd.DataFrame | np.ndarray,
        assets: pd.Index,
        factor_names: list[str] | None = None,
    ) -> pd.DataFrame:
        if isinstance(factor_loadings, pd.DataFrame):
            loadings = factor_loadings.copy()
            loadings.index = loadings.index.astype(str)
            loadings.columns = loadings.columns.astype(str)
        else:
            array = np.asarray(factor_loadings, dtype=float)
            if array.ndim != 2:
                raise FactorStressRiskError(
                    "factor_loadings must be a 2D array or DataFrame."
                )
            if array.shape[0] != len(assets):
                raise FactorStressRiskError(
                    "factor_loadings asset dimension does not match weights."
                )
            names = factor_names or [
                f"Factor_{i}" for i in range(array.shape[1])
            ]
            if len(names) != array.shape[1]:
                raise FactorStressRiskError(
                    "factor_names do not match factor dimension."
                )
            loadings = pd.DataFrame(
                array,
                index=assets,
                columns=[str(name) for name in names],
            )

        if loadings.empty:
            raise FactorStressRiskError("factor_loadings cannot be empty.")
        if loadings.index.duplicated().any():
            raise FactorStressRiskError(
                "factor_loadings contain duplicate assets."
            )
        if loadings.columns.duplicated().any():
            raise FactorStressRiskError(
                "factor_loadings contain duplicate factors."
            )
        if set(loadings.index) != set(assets):
            raise FactorStressRiskError(
                "factor_loadings assets must match portfolio weights."
            )
        loadings = loadings.reindex(assets)
        if not np.isfinite(loadings.to_numpy(dtype=float)).all():
            raise FactorStressRiskError("factor_loadings must be finite.")

        return loadings.astype(float)

    @staticmethod
    def _validate_factor_shocks(
        factor_shocks: Mapping[str, float] | pd.Series,
        factors: pd.Index,
    ) -> pd.Series:
        if isinstance(factor_shocks, pd.Series):
            shocks = factor_shocks.copy()
        elif isinstance(factor_shocks, Mapping):
            shocks = pd.Series(dict(factor_shocks), dtype=float)
        else:
            raise TypeError(
                "factor_shocks must be a mapping or pandas Series."
            )

        shocks.index = shocks.index.astype(str)
        if shocks.empty:
            raise FactorStressRiskError("factor_shocks cannot be empty.")
        if shocks.index.duplicated().any():
            raise FactorStressRiskError(
                "factor_shocks contain duplicate factors."
            )

        missing = factors.difference(shocks.index)
        extra = shocks.index.difference(factors)
        if len(missing) or len(extra):
            raise FactorStressRiskError(
                "factor_shocks must exactly match factor_loadings columns."
            )

        try:
            shocks = shocks.astype(float)
        except (TypeError, ValueError) as exc:
            raise FactorStressRiskError("factor_shocks must be numeric.") from exc

        if not np.isfinite(shocks.to_numpy()).all():
            raise FactorStressRiskError("factor_shocks must be finite.")
        if (shocks.to_numpy() <= -1.0).any():
            raise FactorStressRiskError(
                "factor_shocks must be greater than -100%."
            )

        return shocks.reindex(factors)

    @staticmethod
    def _validate_equity(initial_equity: float) -> float:
        try:
            equity = float(initial_equity)
        except (TypeError, ValueError) as exc:
            raise FactorStressRiskError(
                "initial_equity must be numeric."
            ) from exc
        if not np.isfinite(equity) or equity <= 0.0:
            raise FactorStressRiskError(
                "initial_equity must be finite and positive."
            )
        return equity

    @staticmethod
    def _resolve_loadings(
        factor_loadings: Any,
        assets: pd.Index,
    ) -> pd.DataFrame:
        """Accept a DataFrame or an existing FactorExposureModel instance."""
        if isinstance(factor_loadings, pd.DataFrame):
            return FactorStressRiskEngine._validate_loadings(
                factor_loadings,
                assets,
            )

        model_loadings = getattr(factor_loadings, "asset_loadings", None)
        if model_loadings is not None:
            return FactorStressRiskEngine._validate_loadings(
                model_loadings,
                assets,
            )

        return FactorStressRiskEngine._validate_loadings(
            factor_loadings,
            assets,
        )

    def factor_stress(
        self,
        weights: Mapping[str, float] | pd.Series,
        factor_loadings: pd.DataFrame | np.ndarray | Any,
        factor_shocks: Mapping[str, float] | pd.Series,
        initial_equity: float = 1.0,
        factor_names: list[str] | None = None,
    ) -> FactorStressResult:
        """Apply explicit factor shocks and calculate deterministic P&L."""
        weight_series = self._validate_weights(weights)
        loadings = self._resolve_loadings(factor_loadings, weight_series.index)

        if not isinstance(factor_loadings, pd.DataFrame) and getattr(
            factor_loadings, "asset_loadings", None
        ) is None and not isinstance(factor_loadings, np.ndarray):
            raise TypeError(
                "factor_loadings must be a DataFrame, 2D array, or fitted factor model."
            )

        if factor_names is not None and not isinstance(factor_loadings, pd.DataFrame):
            loadings = self._validate_loadings(
                factor_loadings,
                weight_series.index,
                factor_names=factor_names,
            )

        shocks = self._validate_factor_shocks(
            factor_shocks,
            loadings.columns,
        )
        equity = self._validate_equity(initial_equity)

        implied_returns = loadings.to_numpy() @ shocks.to_numpy()
        weights_array = weight_series.to_numpy()
        asset_pnl = equity * weights_array * implied_returns
        portfolio_pnl = float(asset_pnl.sum())
        portfolio_return = float(portfolio_pnl / equity)
        portfolio_loss = float(max(0.0, -portfolio_pnl))
        stressed_equity = float(equity + portfolio_pnl)

        factor_exposures_array = weights_array @ loadings.to_numpy()
        factor_exposures = {
            str(name): float(value)
            for name, value in zip(loadings.columns, factor_exposures_array)
        }

        factor_pnl_array = equity * factor_exposures_array * shocks.to_numpy()
        factor_pnl = {
            str(name): float(value)
            for name, value in zip(loadings.columns, factor_pnl_array)
        }
        factor_losses = {
            name: float(max(0.0, -value))
            for name, value in factor_pnl.items()
        }

        asset_results = tuple(
            FactorAssetStressResult(
                asset=str(asset),
                weight=float(weight_series.loc[asset]),
                implied_return=float(implied_returns[i]),
                pnl=float(asset_pnl[i]),
                loss=float(max(0.0, -asset_pnl[i])),
            )
            for i, asset in enumerate(weight_series.index)
        )

        negative_assets = [result for result in asset_results if result.loss > 0.0]
        largest_asset = (
            max(negative_assets, key=lambda result: result.loss).asset
            if negative_assets
            else None
        )

        negative_factors = [
            (name, loss)
            for name, loss in factor_losses.items()
            if loss > 0.0
        ]
        largest_factor = (
            max(negative_factors, key=lambda item: item[1])[0]
            if negative_factors
            else None
        )

        result = FactorStressResult(
            method="deterministic_factor_shock",
            initial_equity=equity,
            portfolio_return=portfolio_return,
            portfolio_pnl=portfolio_pnl,
            portfolio_loss=portfolio_loss,
            stressed_equity=stressed_equity,
            gross_exposure=float(np.abs(weights_array).sum()),
            net_exposure=float(weights_array.sum()),
            factor_exposures=factor_exposures,
            factor_shocks={
                str(name): float(value)
                for name, value in shocks.items()
            },
            factor_pnl_contributions=factor_pnl,
            factor_loss_contributions=factor_losses,
            asset_results=asset_results,
            largest_loss_contributor=largest_asset,
            largest_factor_loss_contributor=largest_factor,
        )

        self.last_result = result
        self.factor_stress_count += 1
        return result

    def stress_scenario(self, *args: Any, **kwargs: Any) -> FactorStressResult:
        """Alias for :meth:`factor_stress`."""
        return self.factor_stress(*args, **kwargs)

    def summary(self) -> dict[str, Any]:
        """Return current engine state."""
        return {
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "component": self.COMPONENT,
            "factor_stress_count": int(self.factor_stress_count),
            "last_result_available": self.last_result is not None,
        }

    @property
    def metadata(self) -> dict[str, Any]:
        """Return immutable contract metadata."""
        return {
            **self.summary(),
            "public_methods": list(self.PUBLIC_METHODS),
            "factor_model_source": "existing FactorExposureModel asset_loadings",
            "factor_stress_method": "deterministic_factor_shock",
            "portfolio_loss_definition": "max(0, -portfolio_pnl)",
            "factor_loss_definition": "max(0, -factor_pnl_contribution)",
            "analytics_only": True,
            "governance": False,
            "execution": False,
        }

    def validate(self) -> dict[str, Any]:
        """Validate current stored state without running a new stress."""
        healthy = self.last_result is None or (
            np.isfinite(self.last_result.portfolio_pnl)
            and self.last_result.stressed_equity >= 0.0
        )
        return {
            "valid": bool(healthy),
            "api_version": self.API_VERSION,
            "component": self.COMPONENT,
            "last_result_available": self.last_result is not None,
        }

    def health_check(self) -> bool:
        """Return whether the engine is operational."""
        return bool(self.validate()["valid"])

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

    def save_json(self, path: str | Path) -> Path:
        """Persist engine state as JSON."""
        target = Path(path)
        target.write_text(
            json.dumps(self.to_dict(), indent=2),
            encoding="utf-8",
        )
        return target


def _self_test() -> None:
    loadings = pd.DataFrame(
        {
            "Market": [1.0, 0.8, 0.2],
            "Value": [0.0, 0.5, -0.3],
            "Momentum": [0.2, 0.1, 0.7],
        },
        index=["SPY", "QQQ", "TLT"],
    )
    weights = {"SPY": 0.5, "QQQ": 0.3, "TLT": 0.2}
    shocks = {
        "Market": -0.20,
        "Value": -0.10,
        "Momentum": -0.05,
    }

    engine = FactorStressRiskEngine()
    result = engine.factor_stress(
        weights=weights,
        factor_loadings=loadings,
        factor_shocks=shocks,
        initial_equity=100_000.0,
    )

    expected_exposure = np.array(list(weights.values())) @ loadings.to_numpy()
    expected_return = float(expected_exposure @ np.array(list(shocks.values())))

    assert np.isclose(result.portfolio_return, expected_return)
    assert np.isclose(result.portfolio_pnl, 100_000.0 * expected_return)
    assert np.isclose(
        result.stressed_equity,
        100_000.0 + result.portfolio_pnl,
    )
    assert result.largest_loss_contributor is not None
    assert result.largest_factor_loss_contributor is not None
    assert engine.health_check()
    assert engine.metadata["factor_stress_method"] == (
        "deterministic_factor_shock"
    )

    alias_result = engine.stress_scenario(
        weights=weights,
        factor_loadings=loadings,
        factor_shocks=shocks,
        initial_equity=100_000.0,
    )
    assert np.isclose(alias_result.portfolio_pnl, result.portfolio_pnl)

    try:
        engine.factor_stress(
            weights=weights,
            factor_loadings=loadings,
            factor_shocks={"Market": -0.20},
        )
        raise AssertionError("Expected FactorStressRiskError")
    except FactorStressRiskError:
        pass

    print("FactorStressRiskEngine R3E.5 tests passed.")
    print("R3E.5 STATUS: PASS")


if __name__ == "__main__":
    _self_test()
