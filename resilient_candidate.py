"""Versioned, non-executable risk-aware candidates; incumbent engines stay frozen."""

import numpy as np
from scipy.optimize import minimize
from institutional_return_engines import (
    ANCHORS,
    SETTINGS,
    GROUPS,
    CATALOGUE,
    limits,
    validate_weights,
)
from portfolio_risk_envelope import assess

VERSION = "RESILIENT_CANDIDATE_V2_REVIEW_ONLY"
VARIANTS = {
    "market_only_efficient": dict(vol_scale=1.0, macro_tilt=0.0, trend_floor=0.6),
    "market_only_cautious": dict(vol_scale=0.8, macro_tilt=0.0, trend_floor=0.4),
    "observed_macro_ablation": dict(vol_scale=1.0, macro_tilt=0.1, trend_floor=0.6),
}


def propose(name, ctx, history, variant):
    cfg = VARIANTS[variant]
    symbols, cov = ctx["symbols"], ctx["cov"]
    ceiling, exposure = limits(name, ctx)
    target = np.array([ANCHORS[name].get(s, 0) for s in symbols], dtype=float)
    for i, s in enumerate(symbols):
        trend = cfg["trend_floor"] + (1 - cfg["trend_floor"]) * ctx["trend"][s]
        tilt = 1.0
        if ctx["macro_valid"]:
            sign = (
                (1 if ctx["growth"] else -1)
                if GROUPS[s] == "equity"
                else (
                    (1 if ctx["inflation"] else -1)
                    if s in {"TIP", "GLD", "DBC", "SLV"}
                    else 0
                )
            )
            tilt += cfg["macro_tilt"] * sign
        target[i] *= trend * tilt
    if not target.sum():
        raise ValueError("No eligible strategic exposure")
    target *= exposure / target.sum()
    vol = np.sqrt(max(float(target @ cov @ target), 1e-15))
    target *= min(1.0, ceiling * cfg["vol_scale"] / vol)
    caps = dict(
        equity=SETTINGS[name]["equity_cap"],
        government=0.55,
        real_assets=0.35,
        credit=0.1,
        alternative=0.15,
    )
    satellite = np.array([CATALOGUE[s].satellite for s in symbols], float)

    def residual(w):
        variance = float(w @ cov @ w)
        return np.r_[
            exposure - w.sum(),
            (ceiling * cfg["vol_scale"]) ** 2 - variance,
            [
                cap - sum(w[i] for i, s in enumerate(symbols) if GROUPS[s] == g)
                for g, cap in caps.items()
            ],
            0.3 - satellite @ w,
            0.25 * variance - w * (cov @ w),
        ]

    fit = minimize(
        lambda w: float(np.sum((w - target) ** 2 / (target + 0.02))),
        target,
        method="SLSQP",
        bounds=[(0, 0.25)] * len(symbols),
        constraints={"type": "ineq", "fun": residual},
        options=dict(ftol=1e-11, maxiter=180),
    )
    w = np.maximum(fit.x, 0)
    checks = None
    if fit.success and validate_weights(w, name, ctx):
        checks = assess(
            dict(zip(symbols, w)),
            history,
            limits=dict(volatility=ceiling, positive_euler=0.25),
        )
    if checks is None or checks["status"] == "REJECT":
        return dict(
            status="BLOCKED_V2_RISK",
            weights=dict.fromkeys(symbols, 0.0),
            cash=1.0,
            reason="Independent risk solve/check failed",
        )
    return dict(
        status="UNAPPROVED_V2_CANDIDATE",
        weights=dict(zip(symbols, map(float, w))),
        cash=float(1 - w.sum()),
        review=checks,
        execution_enabled=False,
        promotion_enabled=False,
    )
