"""Fixed-design long-only institutional-method challengers; no live promotion.

Public risk diversification, multi-horizon trends and trading discipline are
adapted to observed ETFs. These are not proprietary institutional replicas.
"""

from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from institutionalportfolio import calibrated_covariance
from investmentcatalog import catalogue

VERSION = "INSTITUTIONAL_RETURN_ENGINES_V1"
NAMES = (
    "economic_balance",
    "defensive_growth",
    "inflation_resilience",
    "tail_aware_ensemble",
)
ANCHORS = {
    "economic_balance": dict(
        SPY=0.12,
        VEA=0.10,
        VWO=0.06,
        EWJ=0.02,
        XLP=0.03,
        XLI=0.02,
        IEF=0.15,
        TLT=0.05,
        TIP=0.12,
        IGOV=0.05,
        SHY=0.03,
        GLD=0.12,
        DBC=0.05,
        SLV=0.01,
        DBMF=0.02,
    ),
    "defensive_growth": dict(
        SPY=0.18,
        VEA=0.12,
        VWO=0.08,
        QQQ=0.06,
        IWM=0.03,
        XLP=0.04,
        XLU=0.02,
        KIE=0.02,
        EWJ=0.02,
        XLI=0.03,
        XLF=0.01,
        XLE=0.01,
        VNQ=0.01,
        ITB=0.01,
        XLY=0.01,
        IEF=0.08,
        TIP=0.05,
        GLD=0.08,
        DBC=0.02,
        DBMF=0.04,
        SGOV=0.03,
    ),
    "inflation_resilience": dict(
        SPY=0.12,
        VEA=0.08,
        VWO=0.06,
        XLE=0.04,
        XLI=0.03,
        KIE=0.02,
        TIP=0.18,
        SHY=0.08,
        IEF=0.04,
        GLD=0.15,
        DBC=0.08,
        SLV=0.02,
        DBMF=0.05,
    ),
}
ANCHORS["tail_aware_ensemble"] = {
    s: 0.8 * sum(a.get(s, 0) for a in ANCHORS.values()) / 3
    for s in set().union(*ANCHORS.values())
}
ANCHORS["tail_aware_ensemble"]["DBMF"] = (
    ANCHORS["tail_aware_ensemble"].get("DBMF", 0) + 0.10
)
ANCHORS["tail_aware_ensemble"]["GLD"] = (
    ANCHORS["tail_aware_ensemble"].get("GLD", 0) + 0.05
)
SETTINGS = {
    "economic_balance": dict(volatility=0.08, equity_cap=0.60, trend_floor=0.65),
    "defensive_growth": dict(volatility=0.12, equity_cap=0.75, trend_floor=0.25),
    "inflation_resilience": dict(volatility=0.10, equity_cap=0.50, trend_floor=0.40),
    "tail_aware_ensemble": dict(volatility=0.10, equity_cap=0.65, trend_floor=0.35),
}
PROTOCOL = {
    "version": VERSION,
    "lookbacks": [63, 126, 252],
    "risk_history": 252,
    "rebalance_sessions": 21,
    "asset_cap": 0.25,
    "positive_euler_cap": 0.25,
    "minimum_cash": 0.05,
    "degraded_exposure_cap": 0.65,
    "degraded_volatility": 0.07,
    "macro_tilt_cap": 0.20,
    "discretionary_trade_band": 0.04,
    "partial_rebalance": 0.5,
    "return_target": None,
    "account_drawdown_ceiling": None,
    "shorting": False,
    "leverage": False,
    "automatic_promotion": False,
    "reserve": "Observed SGOV only after 252 returns; otherwise observed SHY. Unavailable reserves remain cash.",
    "missing_macro": "Explicit market-only degraded candidate. No invented macro value; legacy strict policy unchanged.",
}
CATALOGUE = catalogue()
GROUPS = {s: i.bucket for s, i in CATALOGUE.items()}


def context(prices, end, features, *, decision_time=None):
    """Everything ends at the decision close, strictly before any simulated fill."""
    past = prices.iloc[: end + 1]
    if decision_time is None:
        from tradingcalendar import TradingCalendar

        session = TradingCalendar().session(past.index[-1])
        if session is None:
            raise ValueError("Decision must be an exchange session")
        decision_time = session["market_close"]
    decision_time = pd.Timestamp(decision_time)
    if (
        decision_time.tzinfo is None
        or decision_time.tz_convert("America/New_York").date() != past.index[-1].date()
    ):
        raise ValueError("Dated aware decision close required")
    if len(past) < 253:
        raise ValueError("252 actual returns required")
    history = past.pct_change(fill_method=None).tail(252)
    eligible = [
        s
        for s in history
        if s != "ALLW"
        and s in GROUPS
        and np.isfinite(history[s]).all()
        and (history[s] > -1).all()
        and history[s].std() > 1e-10
    ]
    if len(eligible) < 8:
        raise ValueError("Insufficient diversified observed history")
    history = history[eligible]
    stress = (
        history.loc[history.SPY <= history.SPY.quantile(0.2)]
        if "SPY" in history
        else None
    )
    cov, _ = calibrated_covariance(history, stress)
    reserve = "SGOV" if "SGOV" in eligible else "SHY" if "SHY" in eligible else None
    trend = {}
    mom = {}
    for s in eligible:
        signals = []
        raw = []
        for length in PROTOCOL["lookbacks"]:
            total = float(past[s].iloc[-1] / past[s].iloc[-length - 1] - 1)
            hurdle = (
                float(past[reserve].iloc[-1] / past[reserve].iloc[-length - 1] - 1)
                if reserve
                else 0.0
            )
            signals.append(float(total > hurdle))
            raw.append((total - hurdle) / (length / 252))
        trend[s] = float(np.mean(signals))
        mom[s] = float(np.clip(np.mean(raw), -0.30, 0.30))
    day = str(past.index[-1].date())
    feature = features.get(day)
    if feature:
        stamp = pd.Timestamp(feature["as_of"])
        if stamp.tzinfo is None or stamp > decision_time:
            raise ValueError("Future macro information")
    valid = bool(feature and feature.get("macro_valid", False))
    if valid and not all(
        np.isfinite(feature[k])
        for k in ["ip_growth", "unemployment_change", "inflation_change"]
    ):
        raise ValueError("Invalid macro inputs")
    growth = (
        (feature["ip_growth"] > 0 and feature["unemployment_change"] < 0.25)
        if valid
        else None
    )
    inflation = feature["inflation_change"] > 0 if valid else None
    regime = (
        ("inflationary_growth" if inflation else "disinflationary_growth")
        if growth
        else ("stagflation" if inflation else "deflationary_slowdown")
        if valid
        else "MARKET_ONLY_DEGRADED"
    )
    return dict(
        symbols=eligible,
        cov=cov,
        reserve=reserve,
        trend=trend,
        momentum=mom,
        macro_valid=valid,
        regime=regime,
        growth=growth,
        inflation=inflation,
        decision_session=day,
    )


def limits(name, ctx):
    cfg = SETTINGS[name]
    return min(cfg["volatility"], PROTOCOL["degraded_volatility"]) if not ctx[
        "macro_valid"
    ] else cfg["volatility"], 0.95 if ctx["macro_valid"] else PROTOCOL[
        "degraded_exposure_cap"
    ]


def validate_weights(w, name, ctx, *, tolerance=1e-7):
    w = np.asarray(w, dtype=float)
    c = ctx["cov"]
    symbols = ctx["symbols"]
    vol, exposure = limits(name, ctx)
    if w.shape != (len(symbols),) or not np.isfinite(w).all():
        return False
    variance = float(w @ c @ w)
    rc = w * (c @ w) / variance if variance > 1e-15 else np.zeros(len(w))
    caps = {
        "equity": SETTINGS[name]["equity_cap"],
        "government": 0.55,
        "real_assets": 0.35,
        "credit": 0.10,
        "alternative": 0.15,
    }
    return bool(
        w.min(initial=0) >= -tolerance
        and w.max(initial=0) <= 0.25 + tolerance
        and w.sum() <= exposure + tolerance
        and variance <= vol**2 + tolerance
        and rc.max(initial=0) <= 0.25 + tolerance
        and all(
            sum(w[i] for i, s in enumerate(symbols) if GROUPS[s] == g)
            <= cap + tolerance
            for g, cap in caps.items()
        )
        and sum(w[i] for i, s in enumerate(symbols) if CATALOGUE[s].satellite)
        <= 0.30 + tolerance
    )


def proposal(name, ctx):
    if name not in NAMES:
        raise ValueError("Unknown frozen engine")
    symbols = ctx["symbols"]
    c = ctx["cov"]
    cfg = SETTINGS[name]
    target = np.zeros(len(symbols))
    for i, s in enumerate(symbols):
        base = ANCHORS[name].get(s, 0.0)
        if s == ctx["reserve"] and ctx["reserve"] == "SHY":
            base += ANCHORS[name].get("SGOV", 0)
        trend = cfg["trend_floor"] + (1 - cfg["trend_floor"]) * ctx["trend"][s]
        tilt = 1.0
        if ctx["macro_valid"]:
            if GROUPS[s] == "equity":
                tilt = 1.1 if ctx["growth"] else 0.9
            if s in {"GLD", "DBC", "SLV", "TIP"}:
                tilt = 1.2 if ctx["inflation"] else 0.9
            if s in {"TLT", "IEF", "IGOV"}:
                tilt = 0.8 if ctx["inflation"] else 1.1
        # Modest within-group momentum tilt; this is a signal, not a calibrated expected return.
        rank = [ctx["momentum"][x] for x in symbols if GROUPS[x] == GROUPS[s]]
        relative = 0.9 + 0.2 * float(np.mean(np.asarray(rank) <= ctx["momentum"][s]))
        target[i] = base * trend * tilt * relative
    vol, exposure = limits(name, ctx)
    if ctx["reserve"]:
        reserve_id = symbols.index(ctx["reserve"])
        target[reserve_id] += max(
            0.0, min(0.25 - target[reserve_id], exposure - target.sum())
        )
    target *= min(1.0, exposure / max(target.sum(), 1e-12))
    sigma = np.sqrt(max(float(target @ c @ target), 1e-15))
    target *= min(1.0, vol / sigma)
    buckets = {
        g: np.array([GROUPS[s] == g for s in symbols], float)
        for g in set(GROUPS.values())
    }
    caps = {
        "equity": cfg["equity_cap"],
        "government": 0.55,
        "real_assets": 0.35,
        "credit": 0.10,
        "alternative": 0.15,
    }
    satellite = np.array([CATALOGUE[s].satellite for s in symbols], float)

    def residual(w):
        variance = float(w @ c @ w)
        return np.r_[
            exposure - w.sum(),
            vol**2 - variance,
            [cap - buckets[g] @ w for g, cap in caps.items()],
            0.30 - satellite @ w,
            0.25 * variance - w * (c @ w),
        ]

    def objective(w):
        return float(np.sum((w - target) ** 2 / (target + 0.02)))

    result = minimize(
        objective,
        target,
        method="SLSQP",
        bounds=[(0.0, 0.25)] * len(symbols),
        constraints={"type": "ineq", "fun": residual},
        options={"ftol": 1e-11, "maxiter": 180},
    )
    w = np.maximum(result.x, 0)
    if not result.success or not validate_weights(w, name, ctx):
        return {
            "status": "BLOCKED_RISK_SOLVE",
            "weights": dict.fromkeys(symbols, 0.0),
            "cash": 1.0,
            "reason": str(result.message),
            "regime": ctx["regime"],
        }
    variance = float(w @ c @ w)
    return {
        "status": "UNAPPROVED_INSTITUTIONAL_METHOD_CANDIDATE",
        "weights": dict(zip(symbols, map(float, w))),
        "cash": float(1 - w.sum()),
        "forecast_volatility": float(np.sqrt(variance)),
        "risk_shares": dict(zip(symbols, map(float, w * (c @ w) / variance)))
        if variance > 1e-15
        else dict.fromkeys(symbols, None),
        "regime": ctx["regime"],
        "macro_valid": ctx["macro_valid"],
        "decision_session": ctx["decision_session"],
        "execution_enabled": False,
        "promotion_enabled": False,
    }


def write_protocol(path):
    from strategy_integrity import file_hash
    from strategy_receipts import atomic_json

    p = Path(path)
    atomic_json(
        p,
        {
            "protocol": PROTOCOL,
            "anchors": ANCHORS,
            "settings": SETTINGS,
            "code_sha256": file_hash(__file__),
        },
    )
    return json.loads(p.read_text())
