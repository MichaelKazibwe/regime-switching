"""
======================================================================
ATR
======================================================================

Institutional Average True Range calculation component.

R3B
---
ATR is an instrument-level volatility / stop-distance measure. It is
deliberately kept separate from portfolio covariance, risk budgets, and
portfolio volatility targeting.

The module uses Wilder's recursive smoothing:

    ATR_t = ((ATR_{t-1} * (n - 1)) + TR_t) / n

The initial ATR is the arithmetic mean of the first ``n`` true ranges.

No portfolio allocation decisions are made here.
======================================================================
"""

from __future__ import annotations

from typing import Any

import numpy as np

from basecomponent import BaseObject


class ATRCalculationError(ValueError):
    """Raised when ATR inputs cannot be processed safely."""


class ATRCalculator(BaseObject):
    """
    Production Average True Range calculator.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (
        "true_range",
        "calculate",
        "latest_atr",
        "metadata",
        "health_check",
    )

    DEFAULT_PERIOD = 14
    COMPONENT = "ATRCalculator"

    def __init__(
        self,
        period: int = DEFAULT_PERIOD,
    ) -> None:
        super().__init__()

        self.period = self._validate_period(period)
        self.last_true_range: np.ndarray | None = None
        self.last_atr: np.ndarray | None = None

    # ==================================================================
    # VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_period(period: int) -> int:
        if isinstance(period, bool):
            raise TypeError(
                "ATR period must be a positive integer."
            )

        try:
            value = int(period)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "ATR period must be a positive integer."
            ) from exc

        if value <= 0:
            raise ValueError(
                "ATR period must be positive."
            )

        return value

    @staticmethod
    def _validate_ohlc(
        high: Any,
        low: Any,
        close: Any,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        try:
            high_array = np.asarray(
                high,
                dtype=float,
            ).reshape(-1)

            low_array = np.asarray(
                low,
                dtype=float,
            ).reshape(-1)

            close_array = np.asarray(
                close,
                dtype=float,
            ).reshape(-1)
        except (TypeError, ValueError) as exc:
            raise ATRCalculationError(
                "High, low, and close must be numeric one-dimensional data."
            ) from exc

        if not (
            high_array.size
            == low_array.size
            == close_array.size
        ):
            raise ATRCalculationError(
                "High, low, and close must have identical lengths."
            )

        if high_array.size == 0:
            raise ATRCalculationError(
                "OHLC data cannot be empty."
            )

        if not (
            np.isfinite(high_array).all()
            and np.isfinite(low_array).all()
            and np.isfinite(close_array).all()
        ):
            raise ATRCalculationError(
                "OHLC data contains non-finite values."
            )

        if np.any(high_array < low_array):
            raise ATRCalculationError(
                "High prices cannot be below low prices."
            )

        if np.any(high_array <= 0.0) or np.any(
            low_array <= 0.0
        ) or np.any(close_array <= 0.0):
            raise ATRCalculationError(
                "OHLC prices must be positive."
            )

        return (
            high_array,
            low_array,
            close_array,
        )

    # ==================================================================
    # TRUE RANGE
    # ==================================================================

    @staticmethod
    def true_range(
        high: Any,
        low: Any,
        close: Any,
    ) -> np.ndarray:
        """
        Calculate period-by-period True Range.

        The first observation uses high-low because no prior close
        exists. Subsequent observations use:

            max(
                high-low,
                abs(high-prior_close),
                abs(low-prior_close),
            )
        """
        (
            high_array,
            low_array,
            close_array,
        ) = ATRCalculator._validate_ohlc(
            high,
            low,
            close,
        )

        result = np.empty_like(high_array)

        result[0] = (
            high_array[0]
            - low_array[0]
        )

        if high_array.size > 1:
            previous_close = close_array[:-1]

            result[1:] = np.maximum.reduce(
                (
                    high_array[1:]
                    - low_array[1:],
                    np.abs(
                        high_array[1:]
                        - previous_close
                    ),
                    np.abs(
                        low_array[1:]
                        - previous_close
                    ),
                )
            )

        return result

    # ==================================================================
    # ATR
    # ==================================================================

    def calculate(
        self,
        high: Any,
        low: Any,
        close: Any,
    ) -> np.ndarray:
        """
        Calculate the full Wilder-smoothed ATR series.

        Values before the first complete ATR window are NaN.
        """
        (
            high_array,
            low_array,
            close_array,
        ) = self._validate_ohlc(
            high,
            low,
            close,
        )

        if high_array.size < self.period:
            raise ATRCalculationError(
                "Insufficient OHLC history for ATR period "
                f"{self.period}: received {high_array.size} observations."
            )

        true_range = self.true_range(
            high_array,
            low_array,
            close_array,
        )

        atr = np.full(
            true_range.shape,
            np.nan,
            dtype=float,
        )

        first_atr_index = self.period - 1

        atr[first_atr_index] = float(
            np.mean(
                true_range[
                    : self.period
                ]
            )
        )

        smoothing = float(
            self.period - 1
        )

        for index in range(
            first_atr_index + 1,
            true_range.size,
        ):
            atr[index] = (
                (
                    atr[index - 1]
                    * smoothing
                )
                + true_range[index]
            ) / float(self.period)

        if not np.isfinite(
            atr[first_atr_index:]
        ).all():
            raise ATRCalculationError(
                "ATR calculation produced non-finite values."
            )

        self.last_true_range = true_range.copy()
        self.last_atr = atr.copy()

        return atr

    # ==================================================================
    # LATEST ATR
    # ==================================================================

    def latest_atr(
        self,
        high: Any,
        low: Any,
        close: Any,
    ) -> float:
        """Return the latest finite ATR observation."""
        atr = self.calculate(
            high,
            low,
            close,
        )

        value = float(atr[-1])

        if not np.isfinite(value) or value <= 0.0:
            raise ATRCalculationError(
                "Latest ATR must be finite and positive."
            )

        return value

    # ==================================================================
    # METADATA
    # ==================================================================

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "module": "atr",
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "method": "Wilder",
            "period": self.period,
            "has_result": self.last_atr is not None,
            "measure": "price_units",
        }

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def health_check(self) -> bool:
        if self.API_VERSION != "1.0.0":
            raise RuntimeError(
                "Invalid ATRCalculator API version."
            )

        if self.period <= 0:
            raise RuntimeError(
                "ATR period is invalid."
            )

        if self.last_atr is not None:
            if not np.isfinite(
                self.last_atr[
                    self.period - 1:
                ]
            ):
                raise RuntimeError(
                    "Stored ATR result is invalid."
                )

        return True


# ======================================================================
# REGRESSION TESTS
# ======================================================================

def test_atr_true_range() -> None:
    high = np.array(
        [10.0, 12.0, 13.0],
    )
    low = np.array(
        [9.0, 10.0, 11.0],
    )
    close = np.array(
        [9.5, 11.0, 12.0],
    )

    result = ATRCalculator.true_range(
        high,
        low,
        close,
    )

    expected = np.array(
        [
            1.0,
            2.5,
            2.0,
        ]
    )

    assert np.allclose(
        result,
        expected,
    )


def test_atr_wilder_calculation() -> None:
    high = np.array(
        [10.0, 12.0, 13.0, 14.0, 15.0],
    )
    low = np.array(
        [9.0, 10.0, 11.0, 12.0, 13.0],
    )
    close = np.array(
        [9.5, 11.0, 12.0, 13.0, 14.0],
    )

    engine = ATRCalculator(
        period=3,
    )

    atr = engine.calculate(
        high,
        low,
        close,
    )

    # True ranges:
    # 1.0, 2.5, 2.0, 2.0, 2.0
    # Initial ATR = (1 + 2.5 + 2) / 3 = 1.833333...
    # Next ATR = ((1.833333 * 2) + 2) / 3
    expected_initial = (
        1.0
        + 2.5
        + 2.0
    ) / 3.0

    expected_next = (
        (
            expected_initial
            * 2.0
        )
        + 2.0
    ) / 3.0

    assert np.isnan(
        atr[0]
    )
    assert np.isnan(
        atr[1]
    )
    assert np.isclose(
        atr[2],
        expected_initial,
    )
    assert np.isclose(
        atr[3],
        expected_next,
    )
    assert np.isclose(
        engine.latest_atr(
            high,
            low,
            close,
        ),
        atr[-1],
    )


def test_atr_validation_and_health() -> None:
    engine = ATRCalculator(
        period=14,
    )

    assert engine.health_check() is True

    try:
        engine.calculate(
            [10.0],
            [9.0],
            [9.5],
        )
    except ATRCalculationError:
        pass
    else:
        raise AssertionError(
            "Insufficient history must raise ATRCalculationError."
        )


if __name__ == "__main__":
    test_atr_true_range()
    test_atr_wilder_calculation()
    test_atr_validation_and_health()
    print("ATR regression tests passed.")
