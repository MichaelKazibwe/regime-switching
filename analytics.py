from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from core_constants import TRADING_DAYS


# ============================================================
# PERFORMANCE ANALYTICS
# ============================================================
# Portfolio-level performance and risk analytics.
#
# Intentionally NOT responsible for:
#   - trade expectancy / win rate / profit factor / Kelly
#   - ATR position sizing
#   - risk of ruin
#   - options delta / gamma / vega / put-call parity
#
# Those belong in trade, position-risk, survival-risk, and options
# layers respectively. Keeping these boundaries clean prevents a
# portfolio return metric from being mistaken for a trade metric.
# ============================================================


class PerformanceAnalytics:
    """Robust portfolio performance and benchmark-relative analytics."""

    @staticmethod
    def _clean_returns(returns) -> pd.Series:
        series = returns.copy() if isinstance(returns, pd.Series) else pd.Series(returns)
        series = pd.to_numeric(series, errors="coerce")
        series = series.replace([np.inf, -np.inf], np.nan).dropna().astype(float)
        return series

    @staticmethod
    def _periods_per_year() -> float:
        periods = float(TRADING_DAYS)
        if not np.isfinite(periods) or periods <= 0:
            raise ValueError("TRADING_DAYS must be a positive finite number.")
        return periods

    @staticmethod
    def _finite(value: Any) -> float:
        value = float(value)
        return value if np.isfinite(value) else 0.0

    @staticmethod
    def _validate_returns(returns: pd.Series) -> None:
        if (returns <= -1.0).any():
            raise ValueError("Returns must be greater than -100%.")

    def equity_curve(self, returns) -> pd.Series:
        series = self._clean_returns(returns)
        self._validate_returns(series)
        return (1.0 + series).cumprod()

    def drawdown_series(self, returns) -> pd.Series:
        equity = self.equity_curve(returns)
        if equity.empty:
            return pd.Series(dtype=float, index=equity.index)
        return equity / equity.cummax() - 1.0

    # --------------------------------------------------------
    # RETURN METRICS
    # --------------------------------------------------------

    def cumulative_return(self, returns) -> float:
        series = self._clean_returns(returns)
        self._validate_returns(series)
        if series.empty:
            return 0.0
        return self._finite(np.prod(1.0 + series.to_numpy()) - 1.0)

    def annual_return(self, returns) -> float:
        """Geometrically annualized return over the observed sample."""
        series = self._clean_returns(returns)
        self._validate_returns(series)
        if series.empty:
            return 0.0

        years = len(series) / self._periods_per_year()
        compounded = float(np.prod(1.0 + series.to_numpy()))
        if years <= 0 or compounded <= 0:
            return -1.0 if compounded <= 0 else 0.0
        return self._finite(compounded ** (1.0 / years) - 1.0)

    def cagr(self, returns) -> float:
        """Explicit CAGR alias."""
        return self.annual_return(returns)

    def annual_return_estimate(self, returns) -> float:
        """Annualized geometric estimate implied by the supplied return stream."""
        return self.annual_return(returns)

    # --------------------------------------------------------
    # VOLATILITY / DOWNSIDE RISK
    # --------------------------------------------------------

    def annual_volatility(self, returns) -> float:
        series = self._clean_returns(returns)
        if len(series) < 2:
            return 0.0
        return self._finite(series.std(ddof=1) * np.sqrt(self._periods_per_year()))

    def downside_deviation(self, returns, target: float = 0.0) -> float:
        """Annualized downside deviation relative to a periodic target."""
        series = self._clean_returns(returns)
        if series.empty:
            return 0.0
        target = float(target)
        if not np.isfinite(target):
            raise ValueError("target must be finite.")
        downside = np.minimum(series.to_numpy() - target, 0.0)
        return self._finite(np.sqrt(np.mean(downside ** 2)) * np.sqrt(self._periods_per_year()))

    # --------------------------------------------------------
    # RISK-ADJUSTED RETURN
    # --------------------------------------------------------

    def sharpe_ratio(self, returns, rf: float = 0.02) -> float:
        ann_vol = self.annual_volatility(returns)
        if ann_vol <= 0:
            return 0.0
        return self._finite((self.annual_return(returns) - float(rf)) / ann_vol)

    def sortino_ratio(self, returns, rf: float = 0.02) -> float:
        series = self._clean_returns(returns)
        if series.empty:
            return 0.0

        periods = self._periods_per_year()
        rf = float(rf)
        if not np.isfinite(rf):
            raise ValueError("rf must be finite.")
        periodic_rf = (1.0 + rf) ** (1.0 / periods) - 1.0
        downside = np.minimum(series.to_numpy() - periodic_rf, 0.0)
        downside_risk = np.sqrt(np.mean(downside ** 2)) * np.sqrt(periods)
        if downside_risk <= 0:
            return 0.0
        return self._finite((self.annual_return(series) - rf) / downside_risk)

    def calmar_ratio(self, returns) -> float:
        mdd = abs(self.max_drawdown(returns))
        if mdd <= 0:
            return 0.0
        return self._finite(self.cagr(returns) / mdd)

    # --------------------------------------------------------
    # DRAWDOWN / RECOVERY
    # --------------------------------------------------------

    def max_drawdown(self, returns) -> float:
        drawdown = self.drawdown_series(returns)
        return self._finite(drawdown.min()) if not drawdown.empty else 0.0

    def current_drawdown(self, returns) -> float:
        drawdown = self.drawdown_series(returns)
        return self._finite(drawdown.iloc[-1]) if not drawdown.empty else 0.0

    def drawdown_duration(self, returns) -> int:
        """Current continuous time-under-water in observations."""
        drawdown = self.drawdown_series(returns)
        duration = 0
        for value in reversed(drawdown.to_numpy()):
            if value < 0:
                duration += 1
            else:
                break
        return int(duration)

    def max_drawdown_duration(self, returns) -> int:
        """Longest continuous drawdown duration in observations."""
        drawdown = self.drawdown_series(returns)
        longest = current = 0
        for value in drawdown.to_numpy():
            if value < 0:
                current += 1
                longest = max(longest, current)
            else:
                current = 0
        return int(longest)

    def recovery_period(self, returns) -> int:
        """Observations from the maximum-drawdown trough back to its prior peak.

        Returns 0 when the maximum drawdown has not yet recovered. This avoids
        inventing a recovery date for an open drawdown.
        """
        equity = self.equity_curve(returns)
        if equity.empty:
            return 0

        drawdown = equity / equity.cummax() - 1.0
        trough = int(np.argmin(drawdown.to_numpy()))
        max_dd = float(drawdown.iloc[trough])
        if max_dd >= 0:
            return 0

        prior_peak = float(equity.cummax().iloc[trough])
        for position in range(trough + 1, len(equity)):
            if float(equity.iloc[position]) >= prior_peak:
                return int(position - trough)
        return 0

    def recovery_factor(self, returns) -> float:
        mdd = abs(self.max_drawdown(returns))
        if mdd <= 0:
            return 0.0
        return self._finite(self.cumulative_return(returns) / mdd)

    # --------------------------------------------------------
    # BENCHMARK-RELATIVE METRICS
    # --------------------------------------------------------

    @staticmethod
    def _align_benchmark(returns, benchmark_returns) -> tuple[pd.Series, pd.Series]:
        portfolio = pd.to_numeric(pd.Series(returns), errors="coerce")
        benchmark = pd.to_numeric(pd.Series(benchmark_returns), errors="coerce")

        if isinstance(returns, pd.Series) and isinstance(benchmark_returns, pd.Series):
            aligned = pd.concat([portfolio, benchmark], axis=1, join="inner").dropna()
        else:
            aligned = pd.concat([portfolio.reset_index(drop=True), benchmark.reset_index(drop=True)], axis=1).dropna()

        aligned.columns = ["portfolio", "benchmark"]
        return aligned["portfolio"].astype(float), aligned["benchmark"].astype(float)

    def beta(self, returns, benchmark_returns) -> float:
        portfolio, benchmark = self._align_benchmark(returns, benchmark_returns)
        if len(portfolio) < 2:
            return 0.0
        variance = float(benchmark.var(ddof=1))
        if variance <= 0:
            return 0.0
        return self._finite(float(portfolio.cov(benchmark)) / variance)

    def alpha(self, returns, benchmark_returns, rf: float = 0.02) -> float:
        """Jensen alpha from periodic excess-return regression, annualized."""
        portfolio, benchmark = self._align_benchmark(returns, benchmark_returns)
        if len(portfolio) < 2:
            return 0.0

        periods = self._periods_per_year()
        rf = float(rf)
        periodic_rf = (1.0 + rf) ** (1.0 / periods) - 1.0
        x = benchmark.to_numpy() - periodic_rf
        y = portfolio.to_numpy() - periodic_rf
        variance = float(np.var(x, ddof=1))
        if variance <= 0:
            return 0.0

        beta = float(np.cov(y, x, ddof=1)[0, 1] / variance)
        intercept = float(np.mean(y) - beta * np.mean(x))
        return self._finite((1.0 + intercept) ** periods - 1.0)

    def tracking_error(self, returns, benchmark_returns) -> float:
        portfolio, benchmark = self._align_benchmark(returns, benchmark_returns)
        if len(portfolio) < 2:
            return 0.0
        active = portfolio - benchmark
        return self._finite(active.std(ddof=1) * np.sqrt(self._periods_per_year()))

    def information_ratio(self, returns, benchmark_returns) -> float:
        portfolio, benchmark = self._align_benchmark(returns, benchmark_returns)
        if len(portfolio) < 2:
            return 0.0
        tracking_error = self.tracking_error(portfolio, benchmark)
        if tracking_error <= 0:
            return 0.0
        active_return = self.annual_return(portfolio) - self.annual_return(benchmark)
        return self._finite(active_return / tracking_error)

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    def summary(self, returns, benchmark_returns=None, rf: float = 0.02) -> dict:
        series = self._clean_returns(returns)
        result = {
            "cumulative_return": self.cumulative_return(series),
            "annual_return": self.annual_return(series),
            "annual_return_estimate": self.annual_return_estimate(series),
            "cagr": self.cagr(series),
            "annual_vol": self.annual_volatility(series),
            "downside_deviation": self.downside_deviation(series),
            "sharpe": self.sharpe_ratio(series, rf=rf),
            "sortino": self.sortino_ratio(series, rf=rf),
            "max_drawdown": self.max_drawdown(series),
            "current_drawdown": self.current_drawdown(series),
            "drawdown_duration": self.drawdown_duration(series),
            "max_drawdown_duration": self.max_drawdown_duration(series),
            "recovery_period": self.recovery_period(series),
            "recovery_factor": self.recovery_factor(series),
            "calmar": self.calmar_ratio(series),
        }

        if benchmark_returns is not None:
            result.update({
                "beta": self.beta(series, benchmark_returns),
                "alpha": self.alpha(series, benchmark_returns, rf=rf),
                "tracking_error": self.tracking_error(series, benchmark_returns),
                "information_ratio": self.information_ratio(series, benchmark_returns),
            })

        return result
