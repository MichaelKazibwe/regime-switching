"""Unlevered strategic benchmark, common-history comparison and joint bootstrap.

Design weights are declared before evaluation, not fitted to the displayed sample.
This is a reference portfolio, not a client recommendation or a return promise.
"""

from pathlib import Path
import json
import numpy as np
import pandas as pd
from strategy_integrity import file_hash
from global_asset_registry import expand_anchor, load_registry
from compare_portfolio_models import rebalance_fee

WEIGHTS = dict(
    SPY=0.18,
    VEA=0.10,
    VWO=0.08,
    EWJ=0.02,
    QQQ=0.05,
    XLI=0.04,
    XLV=0.04,
    XLP=0.03,
    XLU=0.02,
    XLE=0.02,
    KIE=0.02,
    IEF=0.07,
    TLT=0.03,
    TIP=0.06,
    IGOV=0.03,
    GLD=0.07,
    DBC=0.03,
    DBMF=0.04,
    SGOV=0.02,
    USD_CASH=0.05,
)
ROLES = {
    "SPY": ("US broad equity", "US equity", "Broad earnings growth"),
    "VEA": (
        "Developed ex-US equity",
        "Developed ex-US, including Japan",
        "International earnings diversification",
    ),
    "VWO": (
        "Emerging equity",
        "Emerging markets",
        "Emerging economies and consumption",
    ),
    "EWJ": (
        "Japan equity tilt",
        "Japan; overlaps VEA",
        "Japan industrial and corporate earnings",
    ),
    "QQQ": (
        "Innovation equity tilt",
        "US-listed global companies",
        "Digital infrastructure and technology; concentrated",
    ),
    "XLI": (
        "Industrial equity tilt",
        "US equity",
        "Infrastructure and industrial investment",
    ),
    "XLV": ("Healthcare equity tilt", "US equity", "Healthcare demand and innovation"),
    "XLP": ("Defensive equity", "US equity", "Essential consumption"),
    "XLU": (
        "Defensive equity",
        "US equity",
        "Utilities and electrification; rate sensitive",
    ),
    "XLE": (
        "Energy equity",
        "US equity",
        "Energy production; cyclical inflation sensitivity",
    ),
    "KIE": (
        "Insurance equity",
        "US equity",
        "Insurance earnings; underwriting and catastrophe risk",
    ),
    "IEF": (
        "Intermediate sovereign bonds",
        "US sovereign",
        "Duration diversification in disinflation",
    ),
    "TLT": (
        "Long sovereign bonds",
        "US sovereign",
        "Recession duration hedge; inflation risk",
    ),
    "TIP": (
        "Inflation-linked bonds",
        "US sovereign",
        "Inflation-linked principal; real-rate risk",
    ),
    "IGOV": (
        "International sovereign bonds",
        "Developed ex-US sovereign",
        "Country and currency diversification; unhedged FX",
    ),
    "GLD": (
        "Gold",
        "Global commodity",
        "Monetary and crisis diversification; no yield",
    ),
    "DBC": (
        "Commodity futures",
        "Global commodities",
        "Supply and inflation sensitivity; roll risk",
    ),
    "DBMF": (
        "Managed futures",
        "Global multi-asset",
        "Trend diversification; strategy and derivative risk",
    ),
    "SGOV": ("Treasury bills", "US sovereign", "Short-duration invested reserve"),
    "USD_CASH": (
        "Uninvested cash",
        "USD cash",
        "Liquidity; zero unverified net interest assumed",
    ),
}


LEGACY_REFERENCE_WEIGHTS = WEIGHTS.copy()
WEIGHTS = expand_anchor(WEIGHTS)
for _symbol, _instrument in load_registry().instruments.items():
    ROLES.setdefault(_symbol, (_instrument.name, _instrument.region,
        "Registered exposure; allocation remains subject to the declared class budget and data eligibility."))


def backtest(returns, weights, cost=0.0015):
    """Trade at close every 21 observations; first return is cash, no lookahead."""
    cols = list(returns)
    target = np.array([weights.get(s, 0) for s in cols], dtype=float)
    if (
        not weights
        or set(weights) - set(cols) - {"USD_CASH"}
        or not np.isfinite(list(weights.values())).all()
        or not np.isfinite(returns.to_numpy()).all()
        or (returns.to_numpy() <= -1).any()
        or min(weights.values()) < 0
        or abs(sum(weights.values()) - 1) > 1e-9
    ):
        raise ValueError("Fully funded nonnegative weights required")
    w = np.zeros(len(cols))
    reserve = 1.0
    nav = 1.0
    curve = []
    turns = []
    for i, row in enumerate(returns.to_numpy()):
        gain = 1 + float(w @ row)
        nav *= gain
        w = w * (1 + row) / gain
        reserve /= gain
        turnover = 0.0
        if i % 21 == 0:
            fee = rebalance_fee(w, target, cost)
            turnover = float(abs(target * (1 - fee) - w).sum())
            nav *= 1 - fee
            w = target.copy()
            reserve = weights.get("USD_CASH", 0)
        curve.append(nav)
        turns.append(turnover)
    curve = np.array(curve)
    r = curve / np.r_[1.0, curve[:-1]] - 1
    return curve, r, np.array(turns)


def metrics(curve, returns, turnover=None):
    dd = curve / np.maximum.accumulate(np.r_[1.0, curve])[1:] - 1
    q = np.quantile(returns, 0.05)
    tail = returns[returns <= q]
    return dict(
        total_return=float(curve[-1] - 1),
        cagr=float(curve[-1] ** (252 / len(curve)) - 1),
        annual_volatility=float(np.std(returns, ddof=1) * np.sqrt(252)),
        maximum_drawdown=float(dd.min()),
        daily_expected_shortfall95=float(-tail.mean()),
        annual_turnover=float(turnover.sum() * 252 / len(curve))
        if turnover is not None
        else None,
    )


def simulate(returns, weights, *, paths=1000, years=3, seed=9417):
    rng = np.random.default_rng(seed)
    days = years * 252
    block = 21
    # Resample whole daily cross-sections jointly, preserving within-block dependence.
    arr = returns.to_numpy()
    starts = rng.integers(
        0, len(arr) - block + 1, size=(paths, (days + block - 1) // block)
    )
    idx = (starts[:, :, None] + np.arange(block)).reshape(paths, -1)[:, :days]
    sample = arr[idx]
    target = np.array([weights.get(s, 0) for s in returns])
    w = np.zeros((paths, len(target)))
    cash = np.ones(paths)
    nav = np.ones(paths)
    peak = nav.copy()
    worst = np.zeros(paths)
    fan = []
    for day in range(days):
        row = sample[:, day]
        gain = 1 + (w * row).sum(axis=1)
        nav *= gain
        w = w * (1 + row) / gain[:, None]
        cash /= gain
        if day % 21 == 0:
            fee = np.zeros(paths)
            for _ in range(30):
                updated = 0.0015 * abs(target[None, :] * (1 - fee[:, None]) - w).sum(
                    axis=1
                )
                if np.max(abs(updated - fee)) < 1e-14:
                    fee = updated
                    break
                fee = updated
            nav *= 1 - fee
            w[:] = target
            cash[:] = weights.get("USD_CASH", 0)
        peak = np.maximum(peak, nav)
        worst = np.minimum(worst, nav / peak - 1)
        if day % 21 == 20:
            fan.append([float(v) for v in np.quantile(nav, [0.05, 0.5, 0.95])])
    return dict(
        paths=paths,
        years=years,
        block_sessions=block,
        seed=seed,
        terminal_return_quantiles=dict(
            zip(
                ["p05", "median", "p95"],
                map(float, np.quantile(nav - 1, [0.05, 0.5, 0.95])),
            )
        ),
        terminal_loss_frequency=float((nav < 1).mean()),
        p95_drawdown_magnitude=float(np.quantile(-worst, 0.95)),
        fan=fan,
        method="Joint 21-session moving-block bootstrap; fixed weights, monthly costs; no drawdown clipping. Conditional scenarios, not macroeconomic predictions.",
    )


def build_benchmark(capture, extension_root):
    capture = Path(capture)
    meta = json.loads(capture.read_text())
    p = capture.parent / "prices.csv"
    if file_hash(p) != meta["files"]["prices.csv"]:
        raise ValueError("Benchmark market checksum mismatch")
    ext = Path(extension_root)
    em = json.loads((ext / "capture.json").read_text())
    xp = ext / "XLV-adjusted.csv"
    if (
        file_hash(xp) != em["prices_sha256"]
        or em["market_session"] != meta["price_session"]
    ):
        raise ValueError("Healthcare capture mismatch")
    prices = pd.read_csv(p, index_col=0, parse_dates=True)
    prices["XLV"] = pd.read_csv(xp, index_col=0, parse_dates=True)["XLV"]
    symbols = [s for s in WEIGHTS if s != "USD_CASH"]
    data = prices[symbols]
    # Require contiguous, actually observed common history; do not backfill younger funds.
    first = max(data[s].first_valid_index() for s in symbols)
    data = data.loc[first:]
    if len(data) < 505 or data.isna().any().any() or (data <= 0).any().any():
        raise ValueError("Incomplete common benchmark history")
    daily = data.pct_change(fill_method=None).iloc[1:]
    results = {}
    curves = {}
    references = {
        "Growth & Resilience": WEIGHTS,
        "US equity": {"SPY": 1.0},
        "60/40 US": {"SPY": 0.6, "IEF": 0.4},
        "All Weather-style proxy": {
            "SPY": 0.3,
            "TLT": 0.4,
            "IEF": 0.15,
            "GLD": 0.075,
            "DBC": 0.075,
        },
    }
    stride = max(1, len(daily) // 240)
    for name, w in references.items():
        curve, r, turn = backtest(daily, w)
        results[name] = metrics(curve, r, turn)
        curves[name] = [float(x) for x in curve[::stride]]
        if (len(curve) - 1) % stride:
            curves[name].append(float(curve[-1]))
    dates = [str(x.date()) for x in daily.index[::stride]]
    if dates[-1] != str(daily.index[-1].date()):
        dates.append(str(daily.index[-1].date()))
    cov = daily.iloc[-252:].cov().to_numpy() * 252
    w = np.array([WEIGHTS[s] for s in symbols])
    var = float(w @ cov @ w)
    rc = w * (cov @ w) / var
    rows = [
        dict(
            symbol=s,
            weight=WEIGHTS[s],
            role=ROLES[s][0],
            geography=ROLES[s][1],
            purpose=ROLES[s][2],
            variance_share=float(rc[symbols.index(s)]) if s in symbols else 0.0,
        )
        for s in WEIGHTS
    ]
    return dict(
        version="GROWTH_RESILIENCE_V1",
        name="Growth & Resilience",
        status="STRATEGIC_REFERENCE_NOT_APPROVED_RECOMMENDATION",
        objective="Long-horizon growth with diversified economic resilience; no fixed return target or account drawdown ceiling.",
        equity_weight=0.6,
        weights=WEIGHTS,
        assets=rows,
        start=dates[0],
        end=dates[-1],
        sessions=len(daily),
        metrics=results,
        chart=dict(dates=dates, series=curves),
        simulation=simulate(daily, WEIGHTS),
        estimated_annual_volatility=float(np.sqrt(var)),
        provenance=dict(
            capture_sha256=file_hash(capture),
            prices_sha256=file_hash(p),
            extension_sha256=file_hash(ext / "capture.json"),
        ),
        limitations=[
            "Weights designed, not optimized to this sample. Retrospective universe selection; no prospective performance claim.",
            "Common observed instrument history only. Shorter histories limit the available backtest. No synthetic pre-inception prices.",
            "Modeled 15 bps on actual risky-asset dollars traded (self-financing); monthly 21-session close rebalancing. No verified brokerage, taxes, spreads or cash yield.",
            "All Weather-style proxy is a transparent illustrative mix, not Bridgewater fund performance.",
            "Geography describes fund mandates, not verified country look-through. Japan overlaps VEA; themes overlap broad equity. USD listings carry foreign currency risk.",
            "Constituents resolve from the versioned global registry; historical references retain their original universe.",
            "Diversification can fail during simultaneous equity and bond shocks. Drawdowns and losses remain possible.",
        ],
    )
