"""Research-only three-year mandate controls. No broker or authorization API."""

from __future__ import annotations

from collections import deque
from copy import deepcopy

import numpy as np
from scipy.stats import norm

from diversifiedregimepolicy import AllocationError
from institutionalportfolio import InstitutionalPortfolio


class AccountDrawdownGuard:
    """Persistent high-water mark; protective cash lock cannot reset itself."""

    def __init__(self, start=None, lock=None):
        if (start is None) != (lock is None) or (
            start is not None and not 0 < start < lock < 1
        ):
            raise AllocationError("Invalid mandate drawdown controls")
        self.start, self.lock = start, lock
        self.peak = 1.0
        self.locked = False

    def update(self, equity):
        if not np.isfinite(equity) or equity <= 0:
            raise AllocationError("Invalid account valuation")
        self.peak = max(self.peak, float(equity))
        drawdown = float(equity / self.peak - 1)
        self.locked = self.locked or (self.lock is not None and drawdown <= -self.lock)
        from portfolio_objectives import drawdown_factor

        factor = drawdown_factor(drawdown, self.start, self.lock, locked=self.locked)
        return drawdown, factor


class FilteredHistoricalRisk:
    """Prior realized forecast residuals; forecasts never resize the portfolio."""

    def __init__(self, window=252, warmup=63):
        if not 2 <= warmup <= window:
            raise AllocationError("Invalid filtered-risk history controls")
        self.scores = deque(maxlen=window)
        self.warmup = warmup

    def observe(self, realized, forecast_sigma):
        if (
            not np.isfinite(realized)
            or not np.isfinite(forecast_sigma)
            or forecast_sigma < 0
        ):
            raise AllocationError("Invalid forecast outcome")
        if forecast_sigma > 1e-8:
            self.scores.append(float(realized / forecast_sigma))

    def forecast(self, sigma):
        if not np.isfinite(sigma) or sigma < 0:
            raise AllocationError("Invalid forecast volatility")
        ready = len(self.scores) >= self.warmup
        if ready:
            values = np.sort(self.scores)
            # Lower-tail order statistic uses only already realized outcomes.
            rank = max(0, int(np.floor((len(values) + 1) * 0.05)) - 1)
            quantile = float(values[rank])
            var = max(0.0, -quantile) * sigma
            es = max(0.0, -float(values[: rank + 1].mean())) * sigma
        else:
            var = norm.ppf(0.95) * sigma
            es = norm.pdf(norm.ppf(0.95)) / 0.05 * sigma
        return {
            "var95": float(var),
            "es95": float(es),
            "ready": ready,
            "past_outcomes": len(self.scores),
        }


def research_parameters(config):
    result = []
    for ceiling in config["candidate_grid"]["volatility_ceiling"]:
        for anchor in config["candidate_grid"]["anchor"]:
            for overlay in config["overlay_grid"]:
                result.append(
                    {
                        "volatility_ceiling": ceiling,
                        "anchor": anchor,
                        "macro_view_weight": 0.10 if overlay == "macro_market" else 0.0,
                        "overlay": overlay,
                    }
                )
    return result


def goal_proposal(
    base,
    history,
    covariance,
    signal,
    parameters,
    trends,
    *,
    reserve_symbol,
    drawdown,
    factor,
):
    """Adapt declared research budgets; reuse the unchanged strict V4 solve."""
    if not np.isfinite(factor) or not 0 <= factor <= 1:
        raise AllocationError("Invalid mandate exposure factor")
    if parameters not in research_parameters(base.config):
        raise AllocationError("Undeclared research variant")
    if factor == 0:
        return {
            "weights": {s: 0.0 for s in history},
            "cash": 1.0,
            "cash_lock": True,
            "risk_budget_error": 0.0,
            "risk_contract": "No invested core: percentage risk contributions are undefined",
        }
    if set(trends) != set(history) or any(
        not np.isfinite(v) or not 0 <= v <= 1 for v in trends.values()
    ):
        raise AllocationError("Invalid historical trend features")
    policy = object.__new__(InstitutionalPortfolio)
    policy.config = deepcopy(base.config)
    p = {k: parameters[k] for k in base.config["candidate_grid"]}
    if parameters["overlay"] != "plain":
        strength = np.array(
            [
                np.mean([trends[s] for s in group if s in history])
                for group in policy.config["sleeves"].values()
            ]
        )
        multiplier = 0.5 + 0.5 * strength
        # Apply the same bounded market filter to anchor and tactical views.
        anchor = np.asarray(policy.config["anchors"][p["anchor"]]) * multiplier
        policy.config["anchors"][p["anchor"]] = (anchor / anchor.sum()).tolist()
        for name, values in policy.config["macro_views"].items():
            values = np.asarray(values) * multiplier
            policy.config["macro_views"][name] = (values / values.sum()).tolist()
    proposal = policy.allocate(
        history,
        covariance,
        signal,
        p,
        reserve_symbol=reserve_symbol,
        account_drawdown=drawdown,
        calibration_multiplier=1.0,
        decision_time=signal["as_of"],
        use_trend=False,
    )
    for symbol in proposal["weights"]:
        proposal["weights"][symbol] *= factor
    proposal["cash"] = 1 - sum(proposal["weights"].values())
    for key in [
        "reserve_weight",
        "raw_estimated_volatility",
        "calibrated_estimated_volatility",
        "estimated_daily_es95",
    ]:
        proposal[key] *= factor
    proposal["account_drawdown_factor"] = factor
    proposal["cash_lock"] = False
    return proposal
