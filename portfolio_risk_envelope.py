"""Independent long-only portfolio checks, including pending BUY exposure.

No loss guarantee. Historical ES and full-correlation volatility are diagnostics;
measured country/FX/liquidity checks require separately verified evidence.
"""

import numpy as np
import pandas as pd

DEFAULT_LIMITS = dict(
    asset=0.25,
    gross=0.95,
    volatility=0.12,
    positive_euler=0.30,
    historical_daily_es=0.03,
)


def assess(weights, returns, *, pending_buys=None, limits=None):
    limits = {**DEFAULT_LIMITS, **(limits or {})}
    if set(limits) != set(DEFAULT_LIMITS) or any(
        isinstance(v, bool) or not np.isfinite(v) or not 0 < v <= 1
        for v in limits.values()
    ):
        raise ValueError("Explicit finite risk limits required")
    if (
        not isinstance(returns, pd.DataFrame)
        or len(returns) < 126
        or not returns.index.is_unique
        or not returns.index.is_monotonic_increasing
        or not returns.columns.is_unique
    ):
        raise ValueError("Ordered observed risk history required")
    combined = dict(weights)
    for symbol, value in (pending_buys or {}).items():
        combined[symbol] = combined.get(symbol, 0) + value
    if any(
        isinstance(v, bool) or not np.isfinite(v) or v < 0 for v in combined.values()
    ):
        raise ValueError("Finite long-only exposures required")
    held = [s for s, w in combined.items() if w > 0]
    if set(held) - set(returns):
        raise ValueError("Missing held or pending risk history")
    history = returns[held].tail(252)
    if not np.isfinite(history).all().all() or (history <= -1).any().any():
        raise ValueError("Incomplete held risk history")
    w = np.array([combined[s] for s in held], dtype=float)
    cov = history.cov().to_numpy() * 252
    variance = max(float(w @ cov @ w), 0)
    rc = w * (cov @ w) / variance if variance > 1e-15 else np.zeros(len(w))
    pnl = history.to_numpy() @ w
    tail = pnl[pnl <= np.quantile(pnl, 0.05)]
    es = max(0.0, -float(tail.mean()))
    metrics = dict(
        gross=float(w.sum()),
        asset=float(w.max(initial=0)),
        volatility=float(np.sqrt(variance)),
        positive_euler=float(rc.max(initial=0)),
        historical_daily_es=es,
    )
    breaches = [k for k, v in metrics.items() if v > limits[k] + 1e-7]
    return dict(
        status="REJECT" if breaches else "STATISTICAL_PASS_NOT_RELEASE_APPROVAL",
        breaches=breaches,
        metrics=metrics,
        limits=limits,
        risk_shares=dict(zip(held, map(float, rc))),
        full_correlation_volatility=float(
            np.abs(w) @ np.sqrt(np.maximum(np.diag(cov), 0))
        ),
        covariance_min_eigenvalue=float(np.linalg.eigvalsh(cov).min()) if held else 0,
        measured_exposures_status="BLOCKED_UNTIL_VERIFIED_HOLDINGS_FX_DURATION_LIQUIDITY",
        execution_enabled=False,
        promotion_enabled=False,
    )
