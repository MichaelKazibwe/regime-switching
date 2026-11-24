"""Daily, non-executable adaptive blend of the four observed-market engines."""

from datetime import datetime, timezone
from pathlib import Path
import argparse
import json

import numpy as np
from scipy.optimize import minimize

from institutional_return_engines import (
    NAMES,
    GROUPS,
    CATALOGUE,
    context,
    proposal,
    validate_weights,
)
from portfolio_contract import extended_prices, make_contract
from strategy_integrity import file_hash, fingerprint, strict_json
from strategy_receipts import atomic_json
from strategy_report import load_training_report
from strategy_training_data import usable_session
from strategy_eligibility import eligible_prices

VERSION = "DYNAMIC_GROWTH_RESILIENCE_V2_ADAPTIVE"
# Ordered as economic balance, defensive growth, inflation resilience, tail aware.
MIXES = {
    "disinflationary_growth": [0.25, 0.40, 0.10, 0.25],
    "inflationary_growth": [0.20, 0.25, 0.35, 0.20],
    "stagflation": [0.15, 0.10, 0.40, 0.35],
    "deflationary_slowdown": [0.35, 0.10, 0.10, 0.45],
    "MARKET_ONLY_DEGRADED": [0.30, 0.10, 0.20, 0.40],
}


def allocate(ctx):
    """Recalculate all engines, then verify the blended portfolio independently.

    Blend weights fit current covariance and observed momentum estimates.
    Re-project the blend because component risk caps do not imply blend caps.
    """
    candidates = {name: proposal(name, ctx) for name in NAMES}
    if any(r["status"].startswith("BLOCKED") for r in candidates.values()):
        raise ValueError("A component risk solve is blocked")
    symbols = ctx["symbols"]
    sleeves = np.column_stack([[candidates[n]["weights"][s] for s in symbols] for n in NAMES])
    # Shrink noisy observed annual momentum towards zero. This is a research
    # input, not a validated forward return estimate or a regime lookup table.
    expected = .25 * np.clip([ctx["momentum"][s] for s in symbols], -.12, .12)
    c = sleeves.T @ ctx["cov"] @ sleeves
    mean = sleeves.T @ expected
    mixed = minimize(lambda x: float(-mean @ x + 12*x @ c @ x + .001*np.sum(x*x)),
        np.full(len(NAMES), 1/len(NAMES)), method="SLSQP",
        bounds=[(0., 1.)]*len(NAMES),
        constraints={"type":"eq", "fun":lambda x:x.sum()-1},
        options={"ftol":1e-11, "maxiter":250})
    if not mixed.success or not np.isfinite(mixed.x).all() or abs(mixed.x.sum()-1)>1e-7:
        raise ValueError("Adaptive strategy mix solve blocked")
    mix = np.maximum(mixed.x, 0.)
    mix /= mix.sum()
    w = sleeves @ mix
    variance = float(w @ ctx["cov"] @ w)
    ceiling = 0.08 if ctx["macro_valid"] else 0.07
    w *= min(1.0, ceiling / max(np.sqrt(variance), 1e-12))
    target = w.copy()
    caps = {
        "equity": 0.60,
        "government": 0.55,
        "real_assets": 0.35,
        "credit": 0.10,
        "alternative": 0.15,
    }
    exposure = 0.95 if ctx["macro_valid"] else 0.65

    def residual(x):
        variance = float(x @ ctx["cov"] @ x)
        return np.r_[
            exposure - x.sum(),
            ceiling**2 - variance,
            [
                cap - sum(x[i] for i, s in enumerate(symbols) if GROUPS[s] == group)
                for group, cap in caps.items()
            ],
            0.30 - sum(x[i] for i, s in enumerate(symbols) if CATALOGUE[s].satellite),
            0.25 * variance - x * (ctx["cov"] @ x),
        ]

    solved = minimize(
        lambda x: float(np.sum((x - target) ** 2 / (target + 0.02))),
        target,
        method="SLSQP",
        bounds=[(0, 0.25)] * len(w),
        constraints={"type": "ineq", "fun": residual},
        options={"ftol": 1e-11, "maxiter": 250},
    )
    if not solved.success:
        raise ValueError("Combined portfolio risk solve blocked")
    w = np.maximum(solved.x, 0)
    # The balance engine provides conservative bucket/equity constraints.
    if not validate_weights(w, "economic_balance", ctx):
        raise ValueError("Combined portfolio fails independent risk constraints")
    variance = float(w @ ctx["cov"] @ w)
    shares = w * (ctx["cov"] @ w) / variance if variance > 1e-15 else np.zeros(len(w))
    return {
        "version": VERSION,
        "status": "UNAPPROVED_DYNAMIC_CANDIDATE",
        "decision_session": ctx["decision_session"],
        "regime": ctx["regime"],
        "macro_valid": ctx["macro_valid"],
        "engine_mix": dict(zip(NAMES, map(float, mix))),
        "mix_method": "CURRENT_COVARIANCE_SHRUNK_MOMENTUM_UTILITY",
        "mix_note": "Strategy proportions are refitted from observed market inputs; legacy regime lookup percentages are not used. Expected growth remains unvalidated; risk limits remain safeguards.",
        "strategies": candidates,
        "weights": dict(zip(symbols, map(float, w))),
        "cash": float(1 - w.sum()),
        "forecast_volatility": float(np.sqrt(variance)),
        "risk_shares": dict(zip(symbols, map(float, shares))),
        "execution_enabled": False,
        "promotion_enabled": False,
        "return_target": None,
        "drawdown_ceiling": None,
    }


def refresh(bundle, output, *, now=None):
    now = now or datetime.now(timezone.utc)
    b = strict_json(bundle)
    report = load_training_report(b["training_report"])
    if not report["current_numerical_source_match"] or report["market_session"] != str(
        usable_session(now).date()
    ):
        raise ValueError("Fresh source-matched completed-session inputs required")
    prices = eligible_prices(extended_prices(b["capture"], b["benchmark_extension"]))
    features = strict_json(Path(b["training_report"]).parent / "features.json")
    if str(prices.index[-1].date()) != report["market_session"]:
        raise ValueError("Market/report session mismatch")
    ctx = context(prices, len(prices) - 1, {r["date"]: r for r in features})
    result = allocate(ctx)
    result["source_hashes"] = {
        str(p): file_hash(p)
        for p in [bundle, __file__, "institutional_return_engines.py",
                  "strategy_eligibility.py", "research/dynamic_eligibility.json",
                  "global_asset_registry.py", "research/global_asset_registry.json"]
    }
    result["contract"] = make_contract(
        "Dynamic_Growth_Resilience",
        result["weights"],
        ctx["decision_session"],
        fingerprint(result["source_hashes"]),
        basis="DYNAMIC_MARKET_MACRO_BLEND",
        performance="UNVALIDATED_NEW_DESIGN_NO_PERFORMANCE_CLAIM",
        policy=VERSION,
    )
    result["snapshot_id"] = fingerprint(result)
    atomic_json(Path(output), result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle", default="var/investor-dashboard/latest-strategy-run.json"
    )
    parser.add_argument("--output", default="var/dynamic-portfolio/latest.json")
    args = parser.parse_args()
    print(json.dumps(refresh(args.bundle, args.output), indent=2))
