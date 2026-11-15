"""
=======================================================================
DRAWDOWN RISK ENGINE
R3D — Drawdown / Recovery / Risk-of-Ruin Layer

Institutional portfolio drawdown-risk analytics.

This module deliberately separates:
    * realized drawdown state,
    * historical recovery analytics,
    * empirical drawdown probabilities,
    * model-explicit survival / risk-of-ruin simulation.

It does NOT implement:
    * stress testing,
    * CVaR / Expected Shortfall,
    * tail scenario generation,
    * liquidity risk,
    * factor risk.

Those belong to later risk layers (R3E and beyond).

Risk-of-ruin convention
-----------------------
Risk of ruin is explicitly defined as the probability that simulated
equity falls to or below a configured ruin threshold within a finite
horizon.

The default simulation method is historical bootstrap:
    each simulated period samples one observed return with replacement.

Therefore risk-of-ruin results are conditional on:
    * the supplied return sample,
    * the bootstrap assumption,
    * the horizon,
    * the ruin threshold,
    * the number of simulations.

They are not unconditional forecasts of future ruin.
=======================================================================
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from basecomponent import BaseObject


# ======================================================================
# ERRORS
# ======================================================================


class DrawdownRiskError(ValueError):
    """Raised when drawdown-risk inputs are invalid."""


# ======================================================================
# DRAWdown RISK STATE
# ======================================================================


@dataclass(frozen=True)
class DrawdownRiskState:
    """Immutable point-in-time portfolio drawdown state."""

    current_equity: float
    peak_equity: float
    current_drawdown: float
    maximum_drawdown: float
    current_drawdown_duration: int
    maximum_drawdown_duration: int
    underwater: bool
    recovered: bool


# ======================================================================
# RECOVERY ANALYTICS
# ======================================================================


class RecoveryAnalytics:
    """
    Historical recovery analytics from an observed return path.

    A drawdown episode begins when the equity curve moves below its
    running peak and ends when that peak is recovered.
    """

    TOLERANCE = 1e-12

    @classmethod
    def _validate_returns(cls, returns) -> pd.Series:
        series = pd.Series(returns, dtype=float).dropna()

        if series.empty:
            raise DrawdownRiskError(
                "Returns cannot be empty."
            )

        values = series.to_numpy(dtype=float)

        if not np.isfinite(values).all():
            raise DrawdownRiskError(
                "Returns contain non-finite values."
            )

        if np.any(values <= -1.0):
            raise DrawdownRiskError(
                "Returns must be greater than -100%."
            )

        return series

    @classmethod
    def _equity_and_drawdown(
        cls,
        returns,
    ) -> tuple[np.ndarray, np.ndarray]:
        series = cls._validate_returns(returns)

        equity = np.cumprod(
            1.0 + series.to_numpy(dtype=float)
        )
        peaks = np.maximum.accumulate(equity)

        drawdown = (
            equity / peaks
        ) - 1.0

        return equity, drawdown

    @classmethod
    def recovery_episodes(
        cls,
        returns,
    ) -> list[dict[str, Any]]:
        """
        Return completed and unresolved drawdown episodes.

        Each episode contains:
            start_index
            trough_index
            recovery_index
            maximum_drawdown
            recovery_duration
            recovered
        """
        equity, drawdown = cls._equity_and_drawdown(returns)

        episodes: list[dict[str, Any]] = []
        start_index: int | None = None
        trough_index: int | None = None
        trough_drawdown = 0.0

        for index, value in enumerate(drawdown):
            value = float(value)

            if start_index is None:
                if value < -cls.TOLERANCE:
                    start_index = index
                    trough_index = index
                    trough_drawdown = value
                continue

            if value < trough_drawdown:
                trough_drawdown = value
                trough_index = index

            if value >= -cls.TOLERANCE:
                assert start_index is not None

                episodes.append(
                    {
                        "start_index": int(start_index),
                        "trough_index": int(trough_index),
                        "recovery_index": int(index),
                        "maximum_drawdown": float(
                            trough_drawdown
                        ),
                        "recovery_duration": int(
                            index - start_index + 1
                        ),
                        "time_to_recovery_from_trough": int(
                            index - trough_index
                        ),
                        "recovered": True,
                    }
                )

                start_index = None
                trough_index = None
                trough_drawdown = 0.0

        if start_index is not None:
            assert trough_index is not None

            episodes.append(
                {
                    "start_index": int(start_index),
                    "trough_index": int(trough_index),
                    "recovery_index": None,
                    "maximum_drawdown": float(
                        trough_drawdown
                    ),
                    "recovery_duration": None,
                    "time_to_recovery_from_trough": None,
                    "recovered": False,
                }
            )

        return episodes

    @classmethod
    def summary(
        cls,
        returns,
    ) -> dict[str, float]:
        episodes = cls.recovery_episodes(returns)

        completed = [
            episode
            for episode in episodes
            if episode["recovered"]
        ]

        durations = np.asarray(
            [
                episode["recovery_duration"]
                for episode in completed
            ],
            dtype=float,
        )

        trough_to_recovery = np.asarray(
            [
                episode["time_to_recovery_from_trough"]
                for episode in completed
            ],
            dtype=float,
        )

        total = len(episodes)
        recovered = len(completed)
        unrecovered = total - recovered

        return {
            "drawdown_episodes": float(total),
            "recovered_episodes": float(recovered),
            "unrecovered_episodes": float(unrecovered),
            "recovery_rate": (
                float(recovered / total)
                if total
                else 1.0
            ),
            "average_recovery_duration": (
                float(durations.mean())
                if durations.size
                else 0.0
            ),
            "median_recovery_duration": (
                float(np.median(durations))
                if durations.size
                else 0.0
            ),
            "maximum_recovery_duration": (
                float(durations.max())
                if durations.size
                else 0.0
            ),
            "average_trough_to_recovery": (
                float(trough_to_recovery.mean())
                if trough_to_recovery.size
                else 0.0
            ),
            "median_trough_to_recovery": (
                float(np.median(trough_to_recovery))
                if trough_to_recovery.size
                else 0.0
            ),
        }


# ======================================================================
# SURVIVAL / RISK OF RUIN
# ======================================================================


class RiskOfRuinAnalytics:
    """
    Finite-horizon survival and risk-of-ruin analytics.

    The default simulation uses historical bootstrap sampling. This
    makes the model assumption explicit and avoids silently presenting
    a Gaussian or normal-distribution assumption as fact.
    """

    TOLERANCE = 1e-12

    @staticmethod
    def _validate_returns(returns) -> np.ndarray:
        series = pd.Series(returns, dtype=float).dropna()

        if series.empty:
            raise DrawdownRiskError(
                "Returns cannot be empty."
            )

        values = series.to_numpy(dtype=float)

        if not np.isfinite(values).all():
            raise DrawdownRiskError(
                "Returns contain non-finite values."
            )

        if np.any(values <= -1.0):
            raise DrawdownRiskError(
                "Returns must be greater than -100%."
            )

        return values

    @staticmethod
    def _validate_simulation_inputs(
        horizon: int,
        simulations: int,
        initial_equity: float,
        ruin_threshold: float,
    ) -> tuple[int, int, float, float]:
        horizon = int(horizon)
        simulations = int(simulations)
        initial_equity = float(initial_equity)
        ruin_threshold = float(ruin_threshold)

        if horizon <= 0:
            raise DrawdownRiskError(
                "horizon must be a positive integer."
            )

        if simulations <= 0:
            raise DrawdownRiskError(
                "simulations must be a positive integer."
            )

        if not np.isfinite(initial_equity) or initial_equity <= 0.0:
            raise DrawdownRiskError(
                "initial_equity must be finite and positive."
            )

        if not np.isfinite(ruin_threshold):
            raise DrawdownRiskError(
                "ruin_threshold must be finite."
            )

        if (
            ruin_threshold <= 0.0
            or ruin_threshold > initial_equity
        ):
            raise DrawdownRiskError(
                "ruin_threshold must be > 0 and "
                "<= initial_equity."
            )

        return (
            horizon,
            simulations,
            initial_equity,
            ruin_threshold,
        )

    @classmethod
    def simulate(
        cls,
        returns,
        *,
        horizon: int,
        simulations: int,
        initial_equity: float = 1.0,
        ruin_threshold: float | None = None,
        rng=None,
    ) -> dict[str, Any]:
        """
        Estimate finite-horizon ruin and survival probability.

        If ruin_threshold is omitted, it defaults to 50% of initial
        equity.

        Returns both aggregate statistics and the per-path terminal
        equity / ruin indicators.
        """
        observed = cls._validate_returns(returns)

        if ruin_threshold is None:
            ruin_threshold = 0.50 * float(initial_equity)

        (
            horizon,
            simulations,
            initial_equity,
            ruin_threshold,
        ) = cls._validate_simulation_inputs(
            horizon,
            simulations,
            initial_equity,
            ruin_threshold,
        )

        if rng is None:
            rng = np.random.default_rng()

        sampled = rng.choice(
            observed,
            size=(simulations, horizon),
            replace=True,
        )

        equity = np.full(
            simulations,
            initial_equity,
            dtype=float,
        )

        ruined = np.zeros(
            simulations,
            dtype=bool,
        )

        minimum_equity = equity.copy()
        peak_equity = equity.copy()
        maximum_drawdown = np.zeros(
            simulations,
            dtype=float,
        )

        for period in range(horizon):
            equity *= (
                1.0
                + sampled[:, period]
            )

            minimum_equity = np.minimum(
                minimum_equity,
                equity,
            )
            peak_equity = np.maximum(
                peak_equity,
                equity,
            )

            drawdown = (
                equity / peak_equity
            ) - 1.0
            maximum_drawdown = np.minimum(
                maximum_drawdown,
                drawdown,
            )

            ruined |= (
                equity
                <= ruin_threshold
                + cls.TOLERANCE
            )

        ruin_count = int(ruined.sum())
        survival_count = int(simulations - ruin_count)

        return {
            "method": "historical_bootstrap",
            "horizon": horizon,
            "simulations": simulations,
            "initial_equity": initial_equity,
            "ruin_threshold": ruin_threshold,
            "ruin_probability": float(
                ruin_count / simulations
            ),
            "survival_probability": float(
                survival_count / simulations
            ),
            "ruined_paths": ruin_count,
            "surviving_paths": survival_count,
            "mean_terminal_equity": float(
                equity.mean()
            ),
            "median_terminal_equity": float(
                np.median(equity)
            ),
            "worst_terminal_equity": float(
                equity.min()
            ),
            "mean_minimum_equity": float(
                minimum_equity.mean()
            ),
            "minimum_path_equity": float(
                minimum_equity.min()
            ),
            "prob_dd_10pct": float(
                np.mean(
                    maximum_drawdown <= -0.10
                )
            ),
            "prob_dd_20pct": float(
                np.mean(
                    maximum_drawdown <= -0.20
                )
            ),
            "prob_dd_30pct": float(
                np.mean(
                    maximum_drawdown <= -0.30
                )
            ),
            "prob_dd_50pct": float(
                np.mean(
                    maximum_drawdown <= -0.50
                )
            ),
            "mean_maximum_drawdown": float(
                maximum_drawdown.mean()
            ),
            "median_maximum_drawdown": float(
                np.median(maximum_drawdown)
            ),
            "worst_maximum_drawdown": float(
                maximum_drawdown.min()
            ),
        }


# ======================================================================
# UNIFIED R3D ENGINE
# ======================================================================


class DrawdownRiskEngine(BaseObject):
    """
    Unified R3D drawdown, recovery and survival-risk engine.

    This is an analytics/risk component, not an optimizer and not an
    execution gate.

    It consumes realized returns and produces a structured risk report.
    """

    API_VERSION = "1.0.0"
    PHASE = "R3D"
    COMPONENT = "DrawdownRiskEngine"

    PUBLIC_METHODS = (
        "analyze",
        "drawdown_state",
        "recovery_summary",
        "risk_of_ruin",
        "summary",
        "metadata",
        "health_check",
        "validate",
        "to_dict",
        "save_json",
    )

    def __init__(
        self,
        *,
        default_ruin_threshold_fraction: float = 0.50,
        default_periods_per_year: int = 252,
    ) -> None:
        super().__init__()

        self.default_ruin_threshold_fraction = float(
            default_ruin_threshold_fraction
        )
        self.default_periods_per_year = int(
            default_periods_per_year
        )

        self.last_state: DrawdownRiskState | None = None
        self.last_recovery_summary: dict[str, float] = {}
        self.last_ruin_result: dict[str, Any] = {}
        self.last_result: dict[str, Any] = {}

        self.validate()

    # ------------------------------------------------------------------
    # VALIDATION
    # ------------------------------------------------------------------

    def validate(self) -> bool:
        if (
            not np.isfinite(
                self.default_ruin_threshold_fraction
            )
            or not (
                0.0
                < self.default_ruin_threshold_fraction
                <= 1.0
            )
        ):
            raise DrawdownRiskError(
                "default_ruin_threshold_fraction must be in "
                "(0, 1]."
            )

        if self.default_periods_per_year <= 0:
            raise DrawdownRiskError(
                "default_periods_per_year must be positive."
            )

        return True

    # ------------------------------------------------------------------
    # DRAWDOWN STATE
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_returns(returns) -> pd.Series:
        series = pd.Series(returns, dtype=float).dropna()

        if series.empty:
            raise DrawdownRiskError(
                "Returns cannot be empty."
            )

        values = series.to_numpy(dtype=float)

        if not np.isfinite(values).all():
            raise DrawdownRiskError(
                "Returns contain non-finite values."
            )

        if np.any(values <= -1.0):
            raise DrawdownRiskError(
                "Returns must be greater than -100%."
            )

        return series

    def drawdown_state(
        self,
        returns,
    ) -> DrawdownRiskState:
        series = self._validate_returns(returns)

        equity = np.cumprod(
            1.0
            + series.to_numpy(dtype=float)
        )

        peaks = np.maximum.accumulate(equity)
        drawdown = (
            equity / peaks
        ) - 1.0

        current_drawdown = float(
            drawdown[-1]
        )

        current_duration = 0

        for value in reversed(drawdown):
            if value < -self._tolerance():
                current_duration += 1
            else:
                break

        maximum_duration = 0
        duration = 0

        for value in drawdown:
            if value < -self._tolerance():
                duration += 1
                maximum_duration = max(
                    maximum_duration,
                    duration,
                )
            else:
                duration = 0

        state = DrawdownRiskState(
            current_equity=float(equity[-1]),
            peak_equity=float(peaks[-1]),
            current_drawdown=current_drawdown,
            maximum_drawdown=float(drawdown.min()),
            current_drawdown_duration=int(
                current_duration
            ),
            maximum_drawdown_duration=int(
                maximum_duration
            ),
            underwater=bool(
                current_drawdown < -self._tolerance()
            ),
            recovered=bool(
                current_drawdown >= -self._tolerance()
            ),
        )

        self.last_state = state

        return state

    def _tolerance(self) -> float:
        return 1e-12

    # ------------------------------------------------------------------
    # RECOVERY
    # ------------------------------------------------------------------

    def recovery_summary(
        self,
        returns,
    ) -> dict[str, float]:
        result = RecoveryAnalytics.summary(
            returns
        )

        self.last_recovery_summary = dict(
            result
        )

        return result

    # ------------------------------------------------------------------
    # RISK OF RUIN
    # ------------------------------------------------------------------

    def risk_of_ruin(
        self,
        returns,
        *,
        horizon: int,
        simulations: int = 10_000,
        initial_equity: float = 1.0,
        ruin_threshold: float | None = None,
        rng=None,
    ) -> dict[str, Any]:
        if ruin_threshold is None:
            ruin_threshold = (
                initial_equity
                * self.default_ruin_threshold_fraction
            )

        result = RiskOfRuinAnalytics.simulate(
            returns,
            horizon=horizon,
            simulations=simulations,
            initial_equity=initial_equity,
            ruin_threshold=ruin_threshold,
            rng=rng,
        )

        self.last_ruin_result = dict(
            result
        )

        return result

    # ------------------------------------------------------------------
    # UNIFIED ANALYSIS
    # ------------------------------------------------------------------

    def analyze(
        self,
        returns,
        *,
        horizon: int | None = None,
        simulations: int = 10_000,
        initial_equity: float = 1.0,
        ruin_threshold: float | None = None,
        rng=None,
    ) -> dict[str, Any]:
        state = self.drawdown_state(
            returns
        )

        recovery = self.recovery_summary(
            returns
        )

        result: dict[str, Any] = {
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "component": self.COMPONENT,
            "drawdown_state": asdict(state),
            "recovery": dict(recovery),
        }

        if horizon is not None:
            ruin = self.risk_of_ruin(
                returns,
                horizon=horizon,
                simulations=simulations,
                initial_equity=initial_equity,
                ruin_threshold=ruin_threshold,
                rng=rng,
            )
            result["risk_of_ruin"] = dict(
                ruin
            )
        else:
            result["risk_of_ruin"] = None

        # Report-ready R3D aliases. These remain analytics only; they do not
        # alter portfolio approval or governance.
        result["drawdown_report"] = {
            "current_drawdown": float(
                state.current_drawdown
            ),
            "maximum_drawdown": float(
                state.maximum_drawdown
            ),
            "current_drawdown_duration": int(
                state.current_drawdown_duration
            ),
            "maximum_drawdown_duration": int(
                state.maximum_drawdown_duration
            ),
            "time_under_water": int(
                state.maximum_drawdown_duration
            ),
            "recovered": bool(
                state.recovered
            ),
            "underwater": bool(
                state.underwater
            ),
            "recovery": dict(recovery),
        }

        self.last_result = result

        return result

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        return {
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "has_state": self.last_state is not None,
            "has_recovery_summary": bool(
                self.last_recovery_summary
            ),
            "has_ruin_result": bool(
                self.last_ruin_result
            ),
        }

    # ------------------------------------------------------------------
    # METADATA
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "class": self.__class__.__name__,
            "version": self.API_VERSION,
            "phase": self.PHASE,
            "component": self.COMPONENT,
            "risk_of_ruin_method": (
                "historical_bootstrap"
            ),
            "default_ruin_threshold_fraction": (
                self.default_ruin_threshold_fraction
            ),
            "default_periods_per_year": (
                self.default_periods_per_year
            ),
        }

    # ------------------------------------------------------------------
    # HEALTH CHECK
    # ------------------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        try:
            healthy = self.validate()

            checks = {
                "drawdown_state": True,
                "recovery_analytics": (
                    hasattr(
                        RecoveryAnalytics,
                        "recovery_episodes",
                    )
                    and hasattr(
                        RecoveryAnalytics,
                        "summary",
                    )
                ),
                "risk_of_ruin": (
                    hasattr(
                        RiskOfRuinAnalytics,
                        "simulate",
                    )
                ),
                "configuration": healthy,
            }

            healthy = bool(
                healthy
                and all(checks.values())
            )

            return {
                "status": (
                    "HEALTHY"
                    if healthy
                    else "UNHEALTHY"
                ),
                "healthy": healthy,
                "component": self.COMPONENT,
                "api_version": self.API_VERSION,
                "phase": self.PHASE,
                "checks": checks,
            }

        except Exception as exc:
            return {
                "status": "UNHEALTHY",
                "healthy": False,
                "component": self.COMPONENT,
                "api_version": self.API_VERSION,
                "phase": self.PHASE,
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # SERIALIZATION
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        result = dict(
            self.metadata
        )

        result["summary"] = self.summary()

        if self.last_state is not None:
            result["last_state"] = asdict(
                self.last_state
            )
        else:
            result["last_state"] = None

        result["last_recovery_summary"] = dict(
            self.last_recovery_summary
        )

        result["last_ruin_result"] = dict(
            self.last_ruin_result
        )

        return result


# ======================================================================
# DETERMINISTIC REGRESSION TESTS
# ======================================================================


def test_drawdown_risk_state() -> None:
    returns = np.array(
        [
            0.10,
            -0.20,
            0.25,
        ]
    )

    engine = DrawdownRiskEngine()

    state = engine.drawdown_state(
        returns
    )

    assert np.isclose(
        state.current_equity,
        1.10,
    )

    assert np.isclose(
        state.peak_equity,
        1.10,
    )

    assert np.isclose(
        state.current_drawdown,
        0.0,
        atol=1e-12,
    )

    assert state.maximum_drawdown < 0.0
    assert state.current_drawdown_duration == 0
    assert state.underwater is False
    assert state.recovered is True


def test_recovery_analytics() -> None:
    returns = np.array(
        [
            0.10,
            -0.20,
            0.25,
        ]
    )

    episodes = RecoveryAnalytics.recovery_episodes(
        returns
    )

    assert len(episodes) == 1

    episode = episodes[0]

    assert episode["recovered"] is True
    assert episode["start_index"] == 1
    assert episode["trough_index"] == 1
    assert episode["recovery_index"] == 2
    assert episode["recovery_duration"] == 2
    assert episode["time_to_recovery_from_trough"] == 1

    summary = RecoveryAnalytics.summary(
        returns
    )

    assert summary["drawdown_episodes"] == 1.0
    assert summary["recovered_episodes"] == 1.0
    assert summary["unrecovered_episodes"] == 0.0
    assert summary["recovery_rate"] == 1.0
    assert summary["maximum_recovery_duration"] == 2.0


def test_unrecovered_drawdown() -> None:
    returns = np.array(
        [
            0.10,
            -0.20,
            -0.10,
        ]
    )

    summary = RecoveryAnalytics.summary(
        returns
    )

    assert summary["drawdown_episodes"] == 1.0
    assert summary["recovered_episodes"] == 0.0
    assert summary["unrecovered_episodes"] == 1.0
    assert summary["recovery_rate"] == 0.0


def test_risk_of_ruin_deterministic() -> None:
    returns = np.array(
        [
            -0.01,
        ]
    )

    result = RiskOfRuinAnalytics.simulate(
        returns,
        horizon=10,
        simulations=100,
        initial_equity=1.0,
        ruin_threshold=0.50,
        rng=np.random.default_rng(42),
    )

    assert result["method"] == (
        "historical_bootstrap"
    )

    assert result["ruin_probability"] == 0.0
    assert result["survival_probability"] == 1.0
    assert result["ruined_paths"] == 0
    assert result["surviving_paths"] == 100


def test_risk_of_ruin_positive_case() -> None:
    returns = np.array(
        [
            -0.25,
        ]
    )

    result = RiskOfRuinAnalytics.simulate(
        returns,
        horizon=10,
        simulations=100,
        initial_equity=1.0,
        ruin_threshold=0.50,
        rng=np.random.default_rng(42),
    )

    assert result["ruin_probability"] == 1.0
    assert result["survival_probability"] == 0.0
    assert result["ruined_paths"] == 100


def test_drawdown_probability_outputs() -> None:
    returns = np.array([
        -0.10,
        -0.10,
    ])

    result = RiskOfRuinAnalytics.simulate(
        returns,
        horizon=2,
        simulations=100,
        initial_equity=1.0,
        ruin_threshold=0.50,
        rng=np.random.default_rng(42),
    )

    assert np.isclose(result["prob_dd_10pct"], 1.0)
    assert np.isclose(result["prob_dd_20pct"], 0.0)
    assert np.isclose(result["prob_dd_30pct"], 0.0)
    assert np.isclose(result["prob_dd_50pct"], 0.0)
    assert result["worst_maximum_drawdown"] < 0.20


def test_unified_analysis_report_contract() -> None:
    returns = np.array([
        0.10,
        -0.20,
        0.25,
    ])

    engine = DrawdownRiskEngine()
    result = engine.analyze(
        returns,
        horizon=5,
        simulations=100,
        rng=np.random.default_rng(42),
    )

    report = result["drawdown_report"]
    assert np.isclose(
        report["current_drawdown"],
        result["drawdown_state"]["current_drawdown"],
    )
    assert report["maximum_drawdown"] <= 0.0
    assert report["time_under_water"] == report["maximum_drawdown_duration"]
    assert "recovery" in report
    assert result["risk_of_ruin"] is not None
    assert "prob_dd_50pct" in result["risk_of_ruin"]


def test_unified_analysis() -> None:
    returns = np.array(
        [
            0.10,
            -0.20,
            0.25,
        ]
    )

    engine = DrawdownRiskEngine()

    result = engine.analyze(
        returns,
        horizon=10,
        simulations=100,
        initial_equity=1.0,
        ruin_threshold=0.50,
        rng=np.random.default_rng(42),
    )

    assert result["api_version"] == "1.0.0"
    assert result["phase"] == "R3D"
    assert "drawdown_state" in result
    assert "recovery" in result
    assert "risk_of_ruin" in result
    assert np.isfinite(
        result["risk_of_ruin"]["ruin_probability"]
    )


def test_invalid_inputs() -> None:
    engine = DrawdownRiskEngine()

    for invalid in (
        [],
        [np.nan],
        [-1.0],
    ):
        try:
            engine.drawdown_state(
                invalid
            )
            raise AssertionError(
                "Expected DrawdownRiskError"
            )
        except DrawdownRiskError:
            pass

    try:
        engine.risk_of_ruin(
            [0.01],
            horizon=0,
        )
        raise AssertionError(
            "Expected DrawdownRiskError"
        )
    except DrawdownRiskError:
        pass


def test_health_and_metadata() -> None:
    engine = DrawdownRiskEngine()

    assert engine.validate() is True

    metadata = engine.metadata

    assert metadata["version"] == "1.0.0"
    assert metadata["phase"] == "R3D"
    assert metadata["risk_of_ruin_method"] == (
        "historical_bootstrap"
    )

    health = engine.health_check()

    assert health["healthy"] is True
    assert health["status"] == "HEALTHY"


def test_to_dict() -> None:
    engine = DrawdownRiskEngine()

    engine.analyze(
        [0.01, -0.02, 0.01],
        horizon=5,
        simulations=20,
        rng=np.random.default_rng(42),
    )

    payload = engine.to_dict()

    assert payload["component"] == (
        "DrawdownRiskEngine"
    )
    assert payload["last_state"] is not None
    assert payload["last_recovery_summary"]
    assert payload["last_ruin_result"]


def run_r3d_tests() -> None:
    tests = (
        test_drawdown_risk_state,
        test_recovery_analytics,
        test_unrecovered_drawdown,
        test_risk_of_ruin_deterministic,
        test_risk_of_ruin_positive_case,
        test_drawdown_probability_outputs,
        test_unified_analysis_report_contract,
        test_unified_analysis,
        test_invalid_inputs,
        test_health_and_metadata,
        test_to_dict,
    )

    passed = 0

    for test in tests:
        test()
        passed += 1

    print(
        f"DrawdownRiskEngine tests: "
        f"{passed}/{len(tests)} passed."
    )
    print(
        "R3D.4 STATUS: PASS"
    )


if __name__ == "__main__":
    run_r3d_tests()
