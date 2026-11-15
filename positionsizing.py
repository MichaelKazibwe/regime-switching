"""
======================================================================
POSITION SIZING
======================================================================

Institutional ATR-aware position sizing.

R3B
---
This module converts instrument-level ATR / stop-distance risk into
capital exposure and share quantities.

The sizing engine is intentionally downstream of portfolio construction:

    PortfolioOptimizer
        ->
    target weights
        ->
    ATRPositionSizer
        ->
    executable quantities

ATR sizing is therefore a risk-aware sizing constraint, not a competing
portfolio optimizer.

For one unit of an instrument:

    stop_loss_risk = ATR * stop_multiple * contract_multiplier

For account equity E and risk fraction r:

    risk_capital = E * r

The maximum number of units is:

    floor(risk_capital / stop_loss_risk)

The resulting ATR-derived maximum weight is:

    max_weight =
        risk_capital * price
        / (E * stop_distance * contract_multiplier)

which simplifies to:

    r * price / stop_distance

before any external portfolio cap is applied.

No covariance, risk-budget, leverage, or volatility-target logic is
duplicated here. Those remain authoritative at the portfolio layer.
======================================================================
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from basecomponent import BaseObject


class PositionSizingError(ValueError):
    """Raised when position-sizing inputs are invalid."""


@dataclass(frozen=True)
class PositionSizeResult:
    """
    Immutable result for one instrument.
    """

    target_weight: float
    sized_weight: float
    max_atr_weight: float
    price: float
    atr: float
    stop_multiple: float
    stop_distance: float
    risk_fraction: float
    risk_capital: float
    shares: float
    position_value: float
    estimated_stop_loss: float
    contract_multiplier: float

    @property
    def capped_by_atr(self) -> bool:
        return (
            abs(self.target_weight)
            > self.max_atr_weight
            + 1e-12
        )


class ATRPositionSizer(BaseObject):
    """
    Production ATR-aware position sizing component.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (
        "risk_capital",
        "stop_distance",
        "max_shares",
        "max_weight",
        "size_position",
        "size_portfolio",
        "metadata",
        "health_check",
    )

    COMPONENT = "ATRPositionSizer"
    DEFAULT_RISK_FRACTION = 0.005
    DEFAULT_STOP_MULTIPLE = 2.0
    DEFAULT_CONTRACT_MULTIPLIER = 1.0

    def __init__(
        self,
        risk_fraction: float = DEFAULT_RISK_FRACTION,
        stop_multiple: float = DEFAULT_STOP_MULTIPLE,
        contract_multiplier: float = DEFAULT_CONTRACT_MULTIPLIER,
    ) -> None:
        super().__init__()

        self.risk_fraction = self._validate_fraction(
            risk_fraction,
            "risk_fraction",
        )
        self.stop_multiple = self._validate_positive(
            stop_multiple,
            "stop_multiple",
        )
        self.contract_multiplier = self._validate_positive(
            contract_multiplier,
            "contract_multiplier",
        )

        self.last_results: dict[str, PositionSizeResult] = {}

    # ==================================================================
    # VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_positive(
        value: float,
        name: str,
    ) -> float:
        if isinstance(value, bool):
            raise TypeError(
                f"{name} must be a positive finite number."
            )

        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{name} must be a positive finite number."
            ) from exc

        if not np.isfinite(result) or result <= 0.0:
            raise ValueError(
                f"{name} must be a positive finite number."
            )

        return result

    @staticmethod
    def _validate_fraction(
        value: float,
        name: str,
    ) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{name} must be a finite value in [0, 1]."
            ) from exc

        if not np.isfinite(result) or not (
            0.0 <= result <= 1.0
        ):
            raise ValueError(
                f"{name} must be a finite value in [0, 1]."
            )

        return result

    @classmethod
    def _validate_equity(
        cls,
        account_equity: float,
    ) -> float:
        return cls._validate_positive(
            account_equity,
            "account_equity",
        )

    # ==================================================================
    # RISK CAPITAL
    # ==================================================================

    def risk_capital(
        self,
        account_equity: float,
        risk_fraction: float | None = None,
    ) -> float:
        equity = self._validate_equity(
            account_equity,
        )

        fraction = (
            self.risk_fraction
            if risk_fraction is None
            else self._validate_fraction(
                risk_fraction,
                "risk_fraction",
            )
        )

        return float(
            equity * fraction
        )

    # ==================================================================
    # STOP DISTANCE
    # ==================================================================

    def stop_distance(
        self,
        atr: float,
        stop_multiple: float | None = None,
    ) -> float:
        atr_value = self._validate_positive(
            atr,
            "atr",
        )

        multiple = (
            self.stop_multiple
            if stop_multiple is None
            else self._validate_positive(
                stop_multiple,
                "stop_multiple",
            )
        )

        return float(
            atr_value * multiple
        )

    # ==================================================================
    # MAXIMUM SHARES
    # ==================================================================

    def max_shares(
        self,
        account_equity: float,
        atr: float,
        risk_fraction: float | None = None,
        stop_multiple: float | None = None,
        contract_multiplier: float | None = None,
        fractional_shares: bool = False,
    ) -> float:
        risk_capital_value = self.risk_capital(
            account_equity,
            risk_fraction=risk_fraction,
        )

        stop = self.stop_distance(
            atr,
            stop_multiple=stop_multiple,
        )

        multiplier = (
            self.contract_multiplier
            if contract_multiplier is None
            else self._validate_positive(
                contract_multiplier,
                "contract_multiplier",
            )
        )

        raw_shares = (
            risk_capital_value
            / (
                stop
                * multiplier
            )
        )

        if fractional_shares:
            return float(raw_shares)

        return float(
            math.floor(
                raw_shares
            )
        )

    # ==================================================================
    # MAXIMUM WEIGHT
    # ==================================================================

    def max_weight(
        self,
        account_equity: float,
        price: float,
        atr: float,
        risk_fraction: float | None = None,
        stop_multiple: float | None = None,
        contract_multiplier: float | None = None,
    ) -> float:
        equity = self._validate_equity(
            account_equity,
        )

        price_value = self._validate_positive(
            price,
            "price",
        )

        shares = self.max_shares(
            account_equity=equity,
            atr=atr,
            risk_fraction=risk_fraction,
            stop_multiple=stop_multiple,
            contract_multiplier=contract_multiplier,
            fractional_shares=True,
        )

        return float(
            shares
            * price_value
            / equity
        )

    # ==================================================================
    # SINGLE POSITION
    # ==================================================================

    def size_position(
        self,
        account_equity: float,
        price: float,
        atr: float,
        target_weight: float,
        risk_fraction: float | None = None,
        stop_multiple: float | None = None,
        contract_multiplier: float | None = None,
        max_position_weight: float | None = None,
        fractional_shares: bool = False,
    ) -> PositionSizeResult:
        equity = self._validate_equity(
            account_equity,
        )

        price_value = self._validate_positive(
            price,
            "price",
        )

        atr_value = self._validate_positive(
            atr,
            "atr",
        )

        try:
            target = float(target_weight)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "target_weight must be finite."
            ) from exc

        if not np.isfinite(target):
            raise ValueError(
                "target_weight must be finite."
            )

        fraction = (
            self.risk_fraction
            if risk_fraction is None
            else self._validate_fraction(
                risk_fraction,
                "risk_fraction",
            )
        )

        multiple = (
            self.stop_multiple
            if stop_multiple is None
            else self._validate_positive(
                stop_multiple,
                "stop_multiple",
            )
        )

        multiplier = (
            self.contract_multiplier
            if contract_multiplier is None
            else self._validate_positive(
                contract_multiplier,
                "contract_multiplier",
            )
        )

        if (
            max_position_weight is not None
        ):
            cap = self._validate_positive(
                max_position_weight,
                "max_position_weight",
            )
        else:
            cap = float("inf")

        atr_weight = self.max_weight(
            account_equity=equity,
            price=price_value,
            atr=atr_value,
            risk_fraction=fraction,
            stop_multiple=multiple,
            contract_multiplier=multiplier,
        )

        max_allowed_weight = min(
            atr_weight,
            cap,
        )

        sign = (
            1.0
            if target >= 0.0
            else -1.0
        )

        sized_weight = (
            sign
            * min(
                abs(target),
                max_allowed_weight,
            )
        )

        risk_capital_value = (
            equity
            * fraction
        )

        stop = (
            atr_value
            * multiple
        )

        raw_shares = (
            abs(sized_weight)
            * equity
            / price_value
        )

        if fractional_shares:
            shares = float(raw_shares)
        else:
            shares = float(
                math.floor(
                    raw_shares
                )
            )

        position_value = (
            shares
            * price_value
        )

        estimated_stop_loss = (
            shares
            * stop
            * multiplier
        )

        final_weight = (
            sign
            * position_value
            / equity
        )

        result = PositionSizeResult(
            target_weight=target,
            sized_weight=final_weight,
            max_atr_weight=max_allowed_weight,
            price=price_value,
            atr=atr_value,
            stop_multiple=multiple,
            stop_distance=stop,
            risk_fraction=fraction,
            risk_capital=risk_capital_value,
            shares=shares,
            position_value=position_value,
            estimated_stop_loss=float(
                estimated_stop_loss
            ),
            contract_multiplier=multiplier,
        )

        return result

    # ==================================================================
    # PORTFOLIO
    # ==================================================================

    def size_portfolio(
        self,
        account_equity: float,
        target_weights: Mapping[str, float],
        prices: Mapping[str, float],
        atrs: Mapping[str, float],
        risk_fraction: float | None = None,
        stop_multiple: float | None = None,
        contract_multipliers: Mapping[str, float]
        | None = None,
        max_position_weight: float | None = None,
        fractional_shares: bool = False,
    ) -> dict[str, PositionSizeResult]:
        if not isinstance(
            target_weights,
            Mapping,
        ):
            raise TypeError(
                "target_weights must be a mapping."
            )

        if not isinstance(
            prices,
            Mapping,
        ):
            raise TypeError(
                "prices must be a mapping."
            )

        if not isinstance(
            atrs,
            Mapping,
        ):
            raise TypeError(
                "atrs must be a mapping."
            )

        assets = tuple(
            target_weights.keys()
        )

        missing_prices = [
            asset
            for asset in assets
            if asset not in prices
        ]

        missing_atrs = [
            asset
            for asset in assets
            if asset not in atrs
        ]

        if missing_prices:
            raise PositionSizingError(
                "Missing prices for assets: "
                f"{missing_prices}"
            )

        if missing_atrs:
            raise PositionSizingError(
                "Missing ATR values for assets: "
                f"{missing_atrs}"
            )

        multipliers = (
            {}
            if contract_multipliers is None
            else dict(
                contract_multipliers
            )
        )

        results: dict[
            str,
            PositionSizeResult,
        ] = {}

        for asset in assets:
            multiplier = multipliers.get(
                asset,
                self.contract_multiplier,
            )

            results[asset] = (
                self.size_position(
                    account_equity=account_equity,
                    price=prices[asset],
                    atr=atrs[asset],
                    target_weight=target_weights[asset],
                    risk_fraction=risk_fraction,
                    stop_multiple=stop_multiple,
                    contract_multiplier=multiplier,
                    max_position_weight=max_position_weight,
                    fractional_shares=fractional_shares,
                )
            )

        self.last_results = dict(
            results
        )

        return results

    # ==================================================================
    # METADATA
    # ==================================================================

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "module": "positionsizing",
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "risk_fraction": self.risk_fraction,
            "stop_multiple": self.stop_multiple,
            "contract_multiplier": self.contract_multiplier,
            "sizing_basis": "ATR_stop_distance",
            "portfolio_risk_authority": (
                "PortfolioOptimizer/RiskBudgetEngine"
            ),
            "has_result": bool(
                self.last_results
            ),
        }

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def health_check(self) -> bool:
        if self.API_VERSION != "1.0.0":
            raise RuntimeError(
                "Invalid ATRPositionSizer API version."
            )

        if not (
            0.0
            <= self.risk_fraction
            <= 1.0
        ):
            raise RuntimeError(
                "Risk fraction is invalid."
            )

        if self.stop_multiple <= 0.0:
            raise RuntimeError(
                "Stop multiple is invalid."
            )

        if self.contract_multiplier <= 0.0:
            raise RuntimeError(
                "Contract multiplier is invalid."
            )

        for asset, result in self.last_results.items():
            if not np.isfinite(
                result.sized_weight
            ):
                raise RuntimeError(
                    f"Non-finite sized weight for {asset!r}."
                )

            if result.shares < 0.0:
                raise RuntimeError(
                    f"Negative share count for {asset!r}."
                )

        return True


# ======================================================================
# REGRESSION TESTS
# ======================================================================

def test_position_sizing_basic() -> None:
    sizer = ATRPositionSizer(
        risk_fraction=0.01,
        stop_multiple=2.0,
    )

    result = sizer.size_position(
        account_equity=100_000.0,
        price=100.0,
        atr=2.0,
        target_weight=0.10,
        fractional_shares=True,
    )

    # Risk capital = 1,000
    # Stop distance = 4
    # Max shares = 250
    # Max weight = 250 * 100 / 100,000 = 25%
    assert np.isclose(
        result.risk_capital,
        1_000.0,
    )

    assert np.isclose(
        result.stop_distance,
        4.0,
    )

    assert np.isclose(
        result.max_atr_weight,
        0.25,
    )

    assert np.isclose(
        result.shares,
        100.0,
    )

    assert np.isclose(
        result.sized_weight,
        0.10,
    )

    assert (
        result.capped_by_atr
        is False
    )

    assert np.isclose(
        result.estimated_stop_loss,
        400.0,
    )

    assert sizer.health_check() is True


def test_position_sizing_atr_cap() -> None:
    sizer = ATRPositionSizer(
        risk_fraction=0.01,
        stop_multiple=2.0,
    )

    result = sizer.size_position(
        account_equity=100_000.0,
        price=100.0,
        atr=10.0,
        target_weight=0.20,
        fractional_shares=True,
    )

    # Stop distance = 20.
    # Risk capital = 1,000.
    # Max shares = 50.
    # Max weight = 5%.
    assert np.isclose(
        result.max_atr_weight,
        0.05,
    )

    assert np.isclose(
        result.sized_weight,
        0.05,
    )

    assert (
        result.capped_by_atr
        is True
    )


def test_position_sizing_preserves_direction() -> None:
    sizer = ATRPositionSizer(
        risk_fraction=0.01,
        stop_multiple=2.0,
    )

    result = sizer.size_position(
        account_equity=100_000.0,
        price=100.0,
        atr=2.0,
        target_weight=-0.10,
        fractional_shares=True,
    )

    assert result.sized_weight < 0.0
    assert result.shares >= 0.0


def test_position_sizing_portfolio_alignment() -> None:
    sizer = ATRPositionSizer(
        risk_fraction=0.005,
        stop_multiple=2.0,
    )

    results = sizer.size_portfolio(
        account_equity=1_000_000.0,
        target_weights={
            "SPY": 0.10,
            "TLT": 0.10,
        },
        prices={
            "SPY": 500.0,
            "TLT": 100.0,
        },
        atrs={
            "SPY": 10.0,
            "TLT": 2.0,
        },
        fractional_shares=True,
    )

    assert tuple(
        results.keys()
    ) == (
        "SPY",
        "TLT",
    )

    assert all(
        np.isfinite(
            result.sized_weight
        )
        for result in results.values()
    )

    assert sizer.health_check() is True


if __name__ == "__main__":
    test_position_sizing_basic()
    test_position_sizing_atr_cap()
    test_position_sizing_preserves_direction()
    test_position_sizing_portfolio_alignment()
    print("Position sizing regression tests passed.")
