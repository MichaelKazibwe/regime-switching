"""Predeclared retrospective comparisons; no winner selection or active changes."""

from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from compare_portfolio_models import rebalance_fee
from goalportfolio import AccountDrawdownGuard
from institutionalportfolio import calibrated_covariance
from live_strategy_training import _metrics
from stress_budget_challenger import allocate, checks, trade_decision, finalize_target
from strategy_integrity import fingerprint
from strategy_receipts import atomic_json

VARIANTS = [
    ("strict_plain", False, False),
    ("strict_cost_aware", False, True),
    ("degraded_plain", True, False),
    ("degraded_cost_aware", True, True),
]


def experiment(prices, features, start, end, config, output):
    symbols = [s for s in prices if s != "ALLW"]
    daily = prices[symbols].pct_change(fill_method=None)
    first = prices.index.get_loc(pd.Timestamp(start))
    last = prices.index.get_loc(pd.Timestamp(end))
    if first < 253:
        raise ValueError("Prior risk history required")
    histories = {}
    covariances = {}
    for i in range(first - 1, last + 1):
        date = prices.index[i]
        h = daily.iloc[i - 251 : i + 1]
        if len(h) != 252 or not np.isfinite(h).all().all():
            raise ValueError("Complete eligible component history required")
        histories[date] = h
        covariances[date] = calibrated_covariance(h)[0]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for name, fallback, cost_aware in VARIANTS:
        print("Evaluating independent shadow variant: " + name, flush=True)
        weights = np.zeros(len(symbols))
        nav = cash = 1.0
        guard = AccountDrawdownGuard(config["protective_start"], config["cash_lock"])
        pending = None
        audit = []
        rows = []
        counts = Counter()
        last_trade = -1000
        previous_valid = None
        for i in range(first - 1, last + 1):
            date = prices.index[i]
            if i >= first:
                r = daily.loc[date].to_numpy()
                growth = float(cash + (weights * (1 + r)).sum())
                weights = weights * (1 + r) / growth
                cash /= growth
                fee = turnover = 0.0
                if pending is not None:
                    target = np.array([pending.get(s, 0.0) for s in symbols])
                    fee = rebalance_fee(weights, target, config["modeled_cost_rate"])
                    turnover = float(np.abs(target * (1 - fee) - weights).sum())
                    weights = target
                    cash = float(1 - weights.sum())
                    last_trade = i
                cost = nav * growth * fee
                ret = growth * (1 - fee) - 1
                nav *= 1 + ret
                dd, factor = guard.update(nav)
                rows.append(
                    {
                        "date": date,
                        "return": ret,
                        "equity": nav,
                        "cash": cash,
                        "turnover": turnover,
                        "cost_as_initial_capital": cost,
                        "account_drawdown": dd,
                        "cash_locked": guard.locked,
                    }
                )
            else:
                dd, factor = guard.update(nav)
            pending = None
            if i == last:
                break
            feature = features.get(str(date.date()))
            valid = bool(feature and feature.get("macro_valid", True))
            current = dict(zip(symbols, map(float, weights)))
            cov = covariances[date]
            h = histories[date]
            safe = checks(
                weights, cov, symbols, config, drawdown=dd, degraded=not valid
            )["passed"]
            scheduled = (i - (first - 1)) % 21 == 0
            if (
                scheduled
                or not safe
                or previous_valid is None
                or valid != previous_valid
                or guard.locked
                or (not valid and not fallback)
            ):
                target = allocate(
                    h,
                    cov,
                    config,
                    current=current,
                    drawdown=dd,
                    macro_valid=valid,
                    market_fallback=fallback,
                    locked=guard.locked,
                )
                counts[target["status"]] += 1
                # Uniform protective scaling retains relative Euler contributions.
                target = finalize_target(
                    target,
                    cov,
                    symbols,
                    config,
                    factor=factor,
                    drawdown=dd,
                    degraded=not valid,
                )
                decision = trade_decision(
                    current,
                    target,
                    cov,
                    h,
                    config,
                    drawdown=dd,
                    macro_valid=valid,
                    market_fallback=fallback,
                    sessions_since_trade=i - last_trade,
                    cost_aware=cost_aware,
                    locked=guard.locked,
                )
                counts[decision["reason"]] += 1
                target.pop("calculation_id", None)
                target["calculation_id"] = fingerprint(target)
                audit.append(
                    {
                        "decision_session": str(date.date()),
                        "execution_session": str(prices.index[i + 1].date()),
                        "macro_valid": valid,
                        "target": target,
                        "decision": decision,
                    }
                )
                if decision["trade"]:
                    pending = target["weights"]
            previous_valid = valid
        frame = pd.DataFrame(rows).set_index("date")
        frame.to_csv(output / (name + ".csv"))
        atomic_json(output / (name + "-decisions.json"), audit)
        results.append(
            {
                "variant": name,
                "market_only_fallback": fallback,
                "cost_aware": cost_aware,
                "metrics": _metrics(frame),
                "fully_cash_sessions": int((frame.cash > 0.999).sum()),
                "events": dict(counts),
                "role": "RETROSPECTIVE_SHADOW_ONLY_NO_PROMOTION",
                "solver_rejections": counts["BLOCKED_SOLVER_OR_ACCOUNT_REVIEW"],
            }
        )
    return results
