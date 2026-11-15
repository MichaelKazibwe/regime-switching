
from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

# ============================================================
# DRAWDOWN FORECAST ENGINE
# ============================================================

class DrawdownForecastEngine:
    """
    Drawdown calculation engine.

    This component calculates realized/path drawdown.

    It does NOT claim to provide:
        - risk of ruin,
        - survival probability,
        - recovery probability,
        - tail-loss probability under a calibrated model.

    Those belong to the dedicated R3D/R3E risk layers.
    """

    TOLERANCE = 1e-12

    # ========================================================
    # VALIDATE RETURNS
    # ========================================================

    @staticmethod
    def _validate_returns(
        returns,
    ) -> pd.Series:

        series = pd.Series(
            returns,
            dtype=float,
        ).dropna()

        if series.empty:
            raise ValueError(
                "Returns cannot be empty."
            )

        values = series.to_numpy(
            dtype=float
        )

        if not np.isfinite(
            values
        ).all():
            raise ValueError(
                "Returns contain non-finite values."
            )

        if np.any(
            values <= -1.0
        ):
            raise ValueError(
                "Returns must be greater than -100%."
            )

        return series

    # ========================================================
    # EQUITY CURVE
    # ========================================================

    @classmethod
    def equity_curve(
        cls,
        returns,
    ) -> pd.Series:

        returns = cls._validate_returns(
            returns
        )

        return (
            1.0
            + returns
        ).cumprod()

    # ========================================================
    # DRAWDOWN SERIES
    # ========================================================

    @classmethod
    def drawdown_series(
        cls,
        returns,
    ) -> pd.Series:

        equity = cls.equity_curve(
            returns
        )

        peak = (
            equity
            .cummax()
        )

        return (
            equity
            / peak
            - 1.0
        )

    # ========================================================
    # MAXIMUM DRAWDOWN
    # ========================================================

    @classmethod
    def max_drawdown(
        cls,
        returns,
    ) -> float:

        drawdown = (
            cls.drawdown_series(
                returns
            )
        )

        return float(
            drawdown.min()
        )

    # ========================================================
    # CURRENT DRAWDOWN
    # ========================================================

    @classmethod
    def current_drawdown(
        cls,
        returns,
    ) -> float:

        drawdown = (
            cls.drawdown_series(
                returns
            )
        )

        return float(
            drawdown.iloc[-1]
        )

    # ========================================================
    # DRAWDOWN DURATION
    # ========================================================

    @classmethod
    def current_drawdown_duration(
        cls,
        returns,
    ) -> int:

        drawdown = (
            cls.drawdown_series(
                returns
            )
        )

        duration = 0

        for value in reversed(
            drawdown.to_numpy(
                dtype=float
            )
        ):

            if value < -cls.TOLERANCE:
                duration += 1
            else:
                break

        return duration

    # ========================================================
    # MAXIMUM DRAWDOWN DURATION
    # ========================================================

    @classmethod
    def maximum_drawdown_duration(
        cls,
        returns,
    ) -> int:

        drawdown = (
            cls.drawdown_series(
                returns
            )
        )

        maximum_duration = 0

        current_duration = 0

        for value in drawdown:

            if value < -cls.TOLERANCE:
                current_duration += 1

                maximum_duration = max(
                    maximum_duration,
                    current_duration,
                )

            else:
                current_duration = 0

        return int(
            maximum_duration
        )


# ============================================================
# REGIME DRAWDOWN SIMULATOR
# ============================================================

class RegimeDrawdownSimulator:
    """
    Simulate drawdowns conditional on regime paths.

    state_return_map
        Maps each state to its expected period return.

    state_volatility_map
        Optional mapping from state to volatility in the same
        period/frequency as the supplied state returns.

    If state_volatility_map is omitted, the legacy fallback
    standard deviation of 1 percentage point is used.

    This fallback exists only for backward compatibility.
    Production risk simulations should supply explicit
    state volatility assumptions.
    """

    DEFAULT_STATE_VOLATILITY = 0.01

    # ========================================================
    # VALIDATION
    # ========================================================

    @staticmethod
    def _validate_state_paths(
        state_paths,
    ):

        if state_paths is None:
            raise ValueError(
                "state_paths cannot be None."
            )

        paths = list(
            state_paths
        )

        if not paths:
            raise ValueError(
                "state_paths cannot be empty."
            )

        return paths

    # ========================================================
    # SIMULATION
    # ========================================================

    @classmethod
    def simulate_drawdowns(
        cls,
        state_paths,
        state_return_map: Mapping,
        state_volatility_map: Mapping | None = None,
        rng=None,
    ) -> np.ndarray:

        paths = (
            cls._validate_state_paths(
                state_paths
            )
        )

        if not isinstance(
            state_return_map,
            Mapping,
        ):
            raise TypeError(
                "state_return_map must be a mapping."
            )

        if state_volatility_map is not None:
            if not isinstance(
                state_volatility_map,
                Mapping,
            ):
                raise TypeError(
                    "state_volatility_map must be a mapping."
                )

        if rng is None:
            rng = np.random.default_rng()

        drawdowns = []

        for path in paths:

            path_returns = []

            for state in path:

                if state not in (
                    state_return_map
                ):
                    raise KeyError(
                        f"Missing return assumption "
                        f"for state: {state!r}"
                    )

                mu = float(
                    state_return_map[
                        state
                    ]
                )

                if not np.isfinite(
                    mu
                ):
                    raise ValueError(
                        f"Non-finite return assumption "
                        f"for state: {state!r}"
                    )

                if (
                    state_volatility_map
                    is None
                ):
                    sigma = (
                        cls.DEFAULT_STATE_VOLATILITY
                    )

                else:

                    if state not in (
                        state_volatility_map
                    ):
                        raise KeyError(
                            f"Missing volatility assumption "
                            f"for state: {state!r}"
                        )

                    sigma = float(
                        state_volatility_map[
                            state
                        ]
                    )

                if (
                    not np.isfinite(
                        sigma
                    )
                    or sigma < 0.0
                ):
                    raise ValueError(
                        f"Invalid volatility assumption "
                        f"for state: {state!r}"
                    )

                simulated_return = float(
                    rng.normal(
                        mu,
                        sigma,
                    )
                )

                # A single-period return below -100%
                # is mathematically invalid.
                simulated_return = max(
                    simulated_return,
                    -0.999999999,
                )

                path_returns.append(
                    simulated_return
                )

            drawdown = (
                DrawdownForecastEngine
                .max_drawdown(
                    path_returns
                )
            )

            drawdowns.append(
                drawdown
            )

        return np.asarray(
            drawdowns,
            dtype=float,
        )


# ============================================================
# DRAWDOWN PROBABILITY ANALYTICS
# ============================================================

class DrawdownProbabilityAnalytics:
    """
    Empirical drawdown-distribution analytics.

    Probabilities are empirical frequencies over the supplied
    simulated/observed drawdown sample.

    They are NOT model-free probabilities of future ruin.
    """

    TOLERANCE = 1e-12

    # ========================================================
    # VALIDATION
    # ========================================================

    @classmethod
    def _validate_drawdowns(
        cls,
        drawdowns,
    ) -> np.ndarray:

        values = np.asarray(
            drawdowns,
            dtype=float,
        ).reshape(-1)

        if values.size == 0:
            raise ValueError(
                "Drawdown sample cannot be empty."
            )

        if not np.isfinite(
            values
        ).all():
            raise ValueError(
                "Drawdown sample contains "
                "non-finite values."
            )

        if np.any(
            values > cls.TOLERANCE
        ):
            raise ValueError(
                "Maximum drawdown observations "
                "cannot be positive."
            )

        return values

    # ========================================================
    # PROBABILITY
    # ========================================================

    @classmethod
    def probability_exceeding(
        cls,
        drawdowns,
        threshold: float,
    ) -> float:
        """
        Probability of drawdown at or beyond a negative threshold.

        Example:

            threshold = -0.20

        means:

            P(DD <= -20%)
        """

        values = (
            cls._validate_drawdowns(
                drawdowns
            )
        )

        threshold = float(
            threshold
        )

        if not np.isfinite(
            threshold
        ):
            raise ValueError(
                "Threshold must be finite."
            )

        if threshold > 0.0:
            raise ValueError(
                "Drawdown threshold must be "
                "zero or negative."
            )

        return float(
            np.mean(
                values <= threshold
            )
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    @classmethod
    def summary(
        cls,
        drawdowns,
    ) -> dict[str, float]:

        values = (
            cls._validate_drawdowns(
                drawdowns
            )
        )

        return {
            "mean_drawdown":
                float(
                    values.mean()
                ),

            "median_drawdown":
                float(
                    np.median(values)
                ),

            "worst_drawdown":
                float(
                    values.min()
                ),

            "best_drawdown":
                float(
                    values.max()
                ),

            "prob_10pct":
                cls.probability_exceeding(
                    values,
                    -0.10,
                ),

            "prob_20pct":
                cls.probability_exceeding(
                    values,
                    -0.20,
                ),

            "prob_30pct":
                cls.probability_exceeding(
                    values,
                    -0.30,
                ),

            "observations":
                float(
                    values.size
                ),
        }


# ============================================================
# REGRESSION TESTS
# ============================================================

def test_drawdown_forecast():

    # --------------------------------------------------------
    # DETERMINISTIC DRAWDOWN
    # --------------------------------------------------------

    returns = np.array([
        0.10,
        -0.20,
        0.05,
        -0.10,
    ])

    expected_equity = (
        1.10
        * 0.80
        * 1.05
        * 0.90
    )

    assert expected_equity > 0

    dd = (
        DrawdownForecastEngine
        .max_drawdown(
            returns
        )
    )

    assert dd < 0.0

    series = (
        DrawdownForecastEngine
        .drawdown_series(
            returns
        )
    )

    assert len(
        series
    ) == len(
        returns
    )

    assert (
        DrawdownForecastEngine
        .current_drawdown(
            returns
        )
        == series.iloc[-1]
    )

    assert (
        DrawdownForecastEngine
        .maximum_drawdown_duration(
            returns
        )
        >= 1
    )

    # --------------------------------------------------------
    # SIMULATION
    # --------------------------------------------------------

    paths = [
        ["growth", "growth", "crisis"],
        ["growth", "crisis", "crisis"],
        ["crisis", "crisis", "growth"],
    ]

    returns_map = {
        "growth": 0.001,
        "crisis": -0.005,
    }

    volatility_map = {
        "growth": 0.005,
        "crisis": 0.020,
    }

    rng = np.random.default_rng(
        42
    )

    drawdowns = (
        RegimeDrawdownSimulator
        .simulate_drawdowns(
            paths,
            returns_map,
            volatility_map,
            rng=rng,
        )
    )

    assert drawdowns.shape == (
        3,
    )

    assert np.isfinite(
        drawdowns
    ).all()

    assert (
        drawdowns <= 0
    ).all()

    # --------------------------------------------------------
    # PROBABILITY ANALYTICS
    # --------------------------------------------------------

    sample = np.array([
        0.0,
        -0.05,
        -0.10,
        -0.20,
        -0.30,
    ])

    stats = (
        DrawdownProbabilityAnalytics
        .summary(
            sample
        )
    )

    assert np.isclose(
        stats["prob_10pct"],
        3 / 5,
    )

    assert np.isclose(
        stats["prob_20pct"],
        2 / 5,
    )

    assert np.isclose(
        stats["prob_30pct"],
        1 / 5,
    )

    assert (
        stats["observations"]
        == 5.0
    )

    print(
        "DrawdownForecast tests passed."
    )


if __name__ == "__main__":
    test_drawdown_forecast()
