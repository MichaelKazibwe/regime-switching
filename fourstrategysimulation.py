"""Four-strategy account simulation; independent of frozen earlier experiments."""

from __future__ import annotations
import numpy as np
import pandas as pd
from assetuniverse import DIVERSIFIED_ASSETS
from compare_portfolio_models import rebalance_fee
from diversifiedregimepolicy import AllocationError
from goalportfolio import AccountDrawdownGuard, FilteredHistoricalRisk
from fourregimestrategies import strategy_proposal


def simulate_strategy(
    prices,
    daily,
    states,
    policy,
    parameters,
    *,
    cost_rate=0.0015,
    protect=True,
    start=None,
    end=None,
):
    symbols = list(DIVERSIFIED_ASSETS)
    start = next(iter(states)) if start is None else pd.Timestamp(start)
    end = prices.index[-1] if end is None else pd.Timestamp(end)
    if start not in states or end <= start or end not in prices.index:
        raise ValueError("Invalid simulated account period")
    dates = prices.loc[start:end].index
    weights = np.zeros(len(symbols))
    cash = nav = 1.0
    guard = AccountDrawdownGuard(
        policy.config["protective_drawdown_start"],
        policy.config["protective_cash_lock"],
    )
    filtered = FilteredHistoricalRisk()
    pending = None
    previous_forecast = None
    rows = []
    trades = []
    rejections = []
    lock_date = None
    for number, date in enumerate(dates):
        if number:
            values = daily.loc[date].reindex(symbols).to_numpy()
            held = weights > 0
            if not np.isfinite(values[held]).all():
                raise ValueError("Unpriceable held instrument")
            dollars = np.zeros(len(weights))
            dollars[held] = weights[held] * (1 + values[held])
            growth = float(cash + dollars.sum())
            gross = growth - 1
            weights = dollars / growth
            cash /= growth
            filtered.observe(gross, previous_forecast["sigma"])
            fee = turnover = 0.0
            if pending is not None:
                target = np.array([pending["weights"].get(s, 0.0) for s in symbols])
                fee = rebalance_fee(weights, target, cost_rate)
                turnover = float(np.abs(target * (1 - fee) - weights).sum())
                weights = target
                cash = float(1 - weights.sum())
                trades.append({"date": str(date.date()), **pending})
            cost = nav * growth * fee
            net = growth * (1 - fee) - 1
            nav *= 1 + net
            drawdown, factor = guard.update(nav)
            if guard.locked and lock_date is None:
                lock_date = str(date.date())
            signal = states[dates[number - 1]]["signal"]
            rows.append(
                {
                    "date": date,
                    "return": net,
                    "gross_return": gross,
                    "equity": nav,
                    "cash": cash,
                    "turnover": turnover,
                    "cost_as_initial_capital": cost,
                    "account_drawdown": drawdown,
                    "cash_locked": guard.locked if protect else False,
                    "raw_daily_sigma": previous_forecast["sigma"],
                    "filtered_var95": previous_forecast["var95"],
                    "filtered_es95": previous_forecast["es95"],
                    "filtered_ready": previous_forecast["ready"],
                    "regime": signal["regime"],
                    "macro_quadrant": "DATA_UNAVAILABLE"
                    if signal.get("macro_unavailable")
                    else max(signal["probabilities"], key=signal["probabilities"].get),
                }
            )
        else:
            drawdown, factor = guard.update(nav)
        if not protect:
            factor = 1.0
        pending = None
        if date == end:
            break
        state = states[date]
        if state.get("macro_unavailable"):
            factor = 0.0
        active = state["symbols"]
        ids = [symbols.index(s) for s in active]
        if any(weights[j] > 0 for j, s in enumerate(symbols) if s not in active):
            raise ValueError("Held instrument is ineligible for risk estimation")
        w = weights[ids]
        variance = float(w @ state["covariance"] @ w)
        sigma = np.sqrt(variance / 252)
        previous_forecast = {"sigma": sigma, **filtered.forecast(sigma)}
        rc = (
            w * (state["covariance"] @ w) / variance
            if variance > 1e-15
            else np.zeros(len(active))
        )
        exposure = (0.4 if state["signal"]["stress"] else 0.95) * factor
        ceiling = (
            min(parameters["volatility_ceiling"], 0.05)
            if state["signal"]["stress"]
            else parameters["volatility_ceiling"]
        )
        if (
            protect
            and policy.config.get("maximum_drawdown") is not None
            and drawdown <= -0.05
        ):
            ceiling = min(ceiling, 0.04)
        breach = (
            weights.sum() > exposure + 1e-8
            or weights.max() > 0.25 + 1e-8
            or np.sqrt(variance) > ceiling * factor + 1e-8
            or rc.max() > 0.25 + 1e-6
        )
        ceiling = policy.volatility_ceiling(parameters["strategy"], state["signal"])
        multiplier = 1.0
        if (
            policy.config["strategies"][parameters["strategy"]]["tail_feedback"]
            and sigma > 1e-8
        ):
            multiplier = float(
                np.clip(previous_forecast["es95"] / (2.062713 * sigma), 1, 2)
            )
        parameters = {**parameters, "tail_multiplier": multiplier}
        breach = breach or np.sqrt(variance) * multiplier > ceiling * factor + 1e-8
        regime_change = (
            number > 0
            and state["signal"]["regime"]
            != states[dates[number - 1]]["signal"]["regime"]
        )
        if number % 21 == 0 or breach or regime_change:
            try:
                i = state["i"]
                proposal = strategy_proposal(
                    policy,
                    daily.iloc[i - 251 : i + 1][active],
                    state["covariance"],
                    state["signal"],
                    parameters,
                    state["trends"],
                    reserve_symbol=state["reserve"],
                    drawdown=drawdown if protect else 0.0,
                    factor=factor,
                )
            except AllocationError as exc:
                rejections.append({"date": str(date.date()), "reason": str(exc)})
                proposal = {
                    "weights": {s: 0.0 for s in symbols},
                    "cash": 1.0,
                    "rejected": True,
                    "decision_time": state["signal"]["as_of"],
                }
            target = np.array([proposal["weights"].get(s, 0.0) for s in symbols])
            proposal["decision_time"] = state["signal"]["as_of"]
            if breach or np.abs(target - weights).sum() >= 0.04:
                pending = proposal
    frame = pd.DataFrame(rows).set_index("date")
    return (
        frame,
        trades,
        {"rejections": rejections, "lock_date": lock_date if protect else None},
    )
