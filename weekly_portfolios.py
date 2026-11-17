"""Weekly, non-executable portfolio research from sealed adjusted closes."""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from investmentcatalog import catalogue
from portfolio_contract import extended_prices
from strategy_integrity import file_hash, fingerprint, strict_json
from strategy_receipts import atomic_json
from strategy_report import load_training_report
from strategy_training_data import usable_session
from global_market_calendar import schedule

POLICIES = {
    "short": dict(label="Short term · 3 months", weeks=13, aversion=12., equity=.35, cash=.15),
    "medium": dict(label="Medium term · 1 year", weeks=52, aversion=6., equity=.60, cash=.05),
    "long": dict(label="Long term · 3+ years", weeks=156, aversion=3., equity=.75, cash=.02),
}
REGIONS = {"VEA": "Developed ex-US", "VWO": "Emerging markets", "EWJ": "Japan",
           "IGOV": "International government", "GLD": "Global real assets",
           "SLV": "Global real assets", "DBC": "Global real assets", "DBMF": "Global futures"}
SOURCES = ("weekly_portfolios.py", "weekly_portfolio_report.py", "investmentcatalog.py",
           "global_asset_registry.py", "research/global_asset_registry.json",
           "global_market_panel.py",
           "portfolio_contract.py", "global_market_calendar.py", "strategy_training_data.py")


def weekly_session(now):
    """Latest fully closed trading week, including Friday holidays and early closes."""
    session = usable_session(now)
    monday = session - pd.Timedelta(days=session.weekday())
    days = schedule("XNYS", monday, monday + pd.Timedelta(days=6))
    if session != days.index[-1]:
        monday -= pd.Timedelta(days=7)
        days = schedule("XNYS", monday, monday + pd.Timedelta(days=6))
    return str(days.index[-1].date())


def observations(prices, session):
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("Unique sorted closes required")
    prices = prices.loc[:session]
    if (prices.empty or str(prices.index[-1].date()) != session
            or prices.index.has_duplicates or not prices.index.is_monotonic_increasing):
        raise ValueError("Unique sorted closes through the completed week required")
    cat = catalogue()
    prices = prices[[s for s in prices if s in cat and cat[s].research_enabled and not cat[s].benchmark_only]]
    if (prices.dropna() <= 0).any().any():
        raise ValueError("Positive adjusted prices required")
    # A week is labelled by its actual final observation, not a fictitious holiday close.
    ends = prices.groupby(prices.index.to_period("W-FRI")).tail(1)
    returns = ends.pct_change(fill_method=None).tail(156)
    symbols = [s for s in returns if returns[s].notna().all()]
    if len(returns) < 156 or len(symbols) < 8:
        raise ValueError("156 complete weekly returns for at least eight assets required")
    return returns[symbols], sorted(set(prices) - set(symbols))


def statistics(values):
    values = np.asarray(values)
    wealth = np.r_[1., np.cumprod(1 + values)]
    return dict(total_return=float(wealth[-1] - 1),
                annualized_volatility=float(values.std(ddof=1) * np.sqrt(52)),
                max_drawdown=float(np.min(wealth / np.maximum.accumulate(wealth) - 1)),
                worst_week=float(values.min()),
                weekly_expected_shortfall=float(values[values <= np.quantile(values, .05)].mean()))


def allocate(history, policy):
    """Constrained utility fit; momentum is a noisy estimate, not an alpha claim."""
    cat = catalogue()
    h = history.tail(104)
    cov = h.cov().to_numpy() * 52
    cov = .70 * cov + .30 * np.diag(np.diag(cov)) + np.eye(len(h.columns)) * 1e-8
    annual_mean = h.mean().to_numpy() * 52
    momentum = (1 + h.tail(26)).prod().to_numpy() ** 2 - 1
    expected = np.clip(.25 * annual_mean + .25 * momentum, -.08, .12)
    groups = {g: np.array([cat[s].bucket == g for s in h], float)
              for g in ("equity", "credit", "real_assets", "alternative", "government")}
    caps = dict(equity=policy["equity"], credit=.15, real_assets=.25, alternative=.15, government=.80)
    registry = __import__("global_asset_registry").load_registry()
    sectors = np.array([cat[s].satellite for s in h], float)
    financials = np.array([any(k in registry.instruments[s].sector.lower() for k in ("financial", "insurance", "bank")) for s in h], float)
    international = np.array([registry.instruments[s].region not in {"us", "unknown"} and cat[s].bucket == "equity" for s in h], float)
    core = np.array([cat[s].bucket == "equity" and not cat[s].satellite for s in h], float)
    broad_floor = .50 if core.any() else 0.
    international_floor = .20 if international.any() else 0.
    satellite_cap = .25 if core.any() else policy["equity"]
    def objective(w):
        returns = h.to_numpy() @ w
        tail = np.sort(returns)[:max(1, int(len(h) * .05))].mean()
        wealth = np.r_[1., np.cumprod(1 + returns)]
        drawdown = -np.min(wealth / np.maximum.accumulate(wealth) - 1)
        return float(-expected @ w + policy["aversion"] * (w @ cov @ w)
                     + .10 * max(0., -tail) + .05 * drawdown + .01 * np.sum(w ** 2))
    def residual(w):
        return np.r_[1 - policy["cash"] - w.sum(),
                     [caps[g] - groups[g] @ w for g in groups],
                     satellite_cap - sectors @ w, .15 - financials @ w,
                     international @ w - international_floor * groups["equity"] @ w,
                     core @ w - broad_floor * groups["equity"] @ w]
    fit = minimize(objective, np.zeros(len(h.columns)), method="SLSQP",
                   bounds=[(0., .20)] * len(h.columns),
                   constraints={"type": "ineq", "fun": residual},
                   options=dict(maxiter=500, ftol=1e-10))
    if not fit.success or min(residual(fit.x)) < -1e-7:
        raise ValueError(f"Constrained allocation failed: {fit.message}")
    weights = np.maximum(fit.x, 0.)
    weights[weights < 1e-7] = 0
    return weights, cov, expected


def replay(history, policy, fixed=None):
    """Expanding causal origins; subsequent weekly close fills, no in-sample backtest."""
    assets, cash, nav, values, turnover = np.zeros(history.shape[1]), 1., 1., [], 0.
    pending = None
    for i in range(104, len(history)):
        assets *= 1 + history.iloc[i].to_numpy()
        pre = cash + assets.sum()
        if pending is not None:
            # Solve the actual self-financing fee on risky dollars traded.
            post = pre
            for _ in range(30):
                post = pre - .0015 * np.abs(pending * post - assets).sum()
            turnover += float(np.abs(pending * post - assets).sum())
            assets, cash = pending * post, (1 - pending.sum()) * post
        else:
            post = pre
        values.append(float(post / nav - 1))
        nav = post
        # Decision uses closes available now, fills only next week's close.
        pending = allocate(history.iloc[:i + 1], policy)[0] if fixed is None else fixed
    return dict(**statistics(values), weeks=len(values), risky_dollars_traded_per_initial_dollar=turnover,
                timing="Weekly decisions filled at the following weekly close; 15 bps risky turnover",
                note="Historical research replay; policy constants were not selected on a separate holdout")


def projections(history, weights, seed=187):
    rng = np.random.default_rng(seed)
    matrix = history.to_numpy()
    starts = rng.integers(0, len(matrix) - 3, size=(1000, 39))
    ids = (starts[..., None] + np.arange(4)).reshape(1000, 156)
    sampled = matrix[ids]
    assets = np.tile(weights, (1000, 1))
    cash = np.full(1000, 1 - weights.sum())
    # Initial entry fee and weekly rebalance fees, zero cash interest, no taxes.
    assets /= 1 + .0015 * weights.sum()
    cash /= 1 + .0015 * weights.sum()
    peak = np.ones(1000)
    drawdown = np.zeros(1000)
    result = {}
    for i in range(156):
        assets *= 1 + sampled[:, i, :]
        before = cash + assets.sum(axis=1)
        nav = before.copy()
        for _ in range(12):
            nav = before - .0015 * np.abs(nav[:, None] * weights - assets).sum(axis=1)
        assets, cash = nav[:, None] * weights, nav * (1 - weights.sum())
        peak = np.maximum(peak, nav)
        drawdown = np.minimum(drawdown, nav / peak - 1)
        if i + 1 in (4, 13, 52, 156):
            result[str(i + 1)] = dict(weeks=i + 1, p05_return=float(np.quantile(nav - 1, .05)),
                median_return=float(np.median(nav - 1)), p95_return=float(np.quantile(nav - 1, .95)),
                loss_frequency=float(np.mean(nav < 1)), loss_10_frequency=float(np.mean(nav < .9)),
                p95_drawdown=float(np.quantile(-drawdown, .95)))
    return result


def build(prices, session):
    cat = catalogue()
    history, excluded = observations(prices, session)
    candidates = {}
    baseline_weights = np.array([.60 if s == "SPY" else .40 if s == "IEF" else 0. for s in history])
    baseline = replay(history, POLICIES["medium"], fixed=baseline_weights) if np.isclose(baseline_weights.sum(), 1.) else dict(
        status="UNAVAILABLE_REFERENCE_COMPONENTS", total_return=None, max_drawdown=None,
        reason="The optional declared SPY/IEF reference is outside this observed universe")
    for key, policy in POLICIES.items():
        weights, cov, expected = allocate(history, policy)
        variance = float(weights @ cov @ weights)
        contributions = weights * (cov @ weights) / variance if variance > 0 else weights * 0
        rows = []
        for i, symbol in enumerate(history):
            if weights[i] <= 0:
                continue
            h = history[symbol]
            momentum = float((1 + h.tail(26)).prod() - 1)
            vol = float(h.tail(104).std() * np.sqrt(52))
            rows.append(dict(symbol=symbol, weight=float(weights[i]), risk_share=float(contributions[i]),
                bucket=cat[symbol].bucket, region=REGIONS.get(symbol, cat[symbol].region),
                momentum_26w=momentum, annualized_volatility=vol, utility_return_estimate=float(expected[i]),
                justification=f"26-week adjusted return {momentum:.1%}; annualized weekly volatility {vol:.1%}. "
                f"Constrained allocation balances estimated growth, covariance and historical tail losses; "
                f"signed variance share {contributions[i]:.1%}."))
        cash = float(1 - weights.sum())
        rows.append(dict(symbol="USD_CASH", weight=cash, risk_share=0., bucket="cash", region="USD cash",
                         justification="Residual cash lowers modelled volatility; zero interest assumed; inflation loss remains possible."))
        mix = history.to_numpy() @ weights
        rolling = pd.Series(1 + mix).rolling(13).apply(np.prod, raw=True) - 1
        worst = int(np.nanargmin(rolling))
        groups = {g: sum(r["weight"] for r in rows if r["bucket"] == g) for g in sorted({r["bucket"] for r in rows})}
        regions = {g: sum(r["weight"] for r in rows if r["region"] == g) for g in sorted({r["region"] for r in rows})}
        shock_masks = {
            "Growth slowdown": dict(equity=-.30, government=.05, credit=-.12, real_assets=-.12, alternative=0., cash=0.),
            "Inflation and rate shock": dict(equity=-.15, government=-.15, credit=-.12, real_assets=.10, alternative=0., cash=0.),
            "Liquidity crisis": dict(equity=-.40, government=-.05, credit=-.20, real_assets=-.20, alternative=-.10, cash=0.),
        }
        candidates[key] = dict(policy=policy, allocations=sorted(rows, key=lambda r: -r["weight"]),
            group_weights=groups, exposure_labels=regions,
            estimated_volatility=float(np.sqrt(variance)), effective_holdings=float(1 / sum(r["weight"]**2 for r in rows)),
            replay=replay(history, policy), baseline_60_40=baseline, projections=projections(history, weights),
            historical_static_stress=dict(return_13w=float(rolling.iloc[worst]),
                end=str(history.index[worst].date()), note="Worst overlapping observed 13-week block for today's fixed weights, before fees; not a held-out result"),
            declared_shocks={label: sum(r["weight"] * shocks[r["bucket"]] for r in rows) for label, shocks in shock_masks.items()})
    return dict(schema_version=1, status="REVIEW_REQUIRED", market_session=session,
        generated_at=datetime.now(timezone.utc).isoformat(), execution_enabled=False, promotion_enabled=False,
        candidates=candidates, eligible_symbols=list(history), excluded_insufficient_history=excluded,
        weekly_observations=len(history), first_week=str(history.index[0].date()),
        methodology="Long-only portfolios from the registry-qualified, USD-valued research universe. 20% asset cap; horizon-specific equity/cash limits; "
        "Satellite exposure capped at 25% when broad funds are available, financial-sector exposure at 15%; "
        "at least half of equity in broad funds and one fifth in ex-US exposures when those categories are available. "
        "Asset roles and regions resolve from registry metadata. These are declared constraints, not country look-through. "
        "104-week covariance with 30% diagonal shrinkage; noisy clipped mean/momentum return estimate; weekly tail-loss and drawdown penalties. "
        "Monthly=4, quarterly=13, annual=52 weeks. 1,000 joint 4-week observed-block paths, fixed current target weights, "
        "weekly self-financing rebalancing at 15 bps risky turnover, zero cash yield, no tax or FX conversion fees.",
        limitations=["Research candidates, not globally optimal or approved allocations. Client review required.",
            "Resampled projections are uncalibrated conditional scenarios, not reliable market predictions.",
            "Weekly drawdowns miss intraweek losses. Future losses can exceed every displayed stress or quantile.",
            "Universe survivorship, short history, parameter choices, currency exposure and overlapping holdings may bias results.",
            "Geographic labels describe registered exposure mandates or issuer locations, not verified country look-through. US listings do not imply US-only underlying holdings.",
            "Historical replay is causal but has no untouched policy-selection holdout; no demonstrated forecasting advantage.",
            "Macro-regime probabilities are unavailable when upstream macro inputs fail validation; no macro alpha is assumed."])


def verify(root):
    root = Path(root)
    manifest = strict_json(root / "manifest.json")
    if manifest.get("schema_version") != 1 or set(manifest["source_hashes"]) != set(SOURCES):
        raise ValueError("Complete weekly source manifest required")
    if set(manifest["files"]) != {"recommendations.json", "dashboard-report.pdf"}:
        raise ValueError("Unexpected weekly artifact set")
    for name, digest in manifest["files"].items():
        if (root / name).is_symlink() or file_hash(root / name) != digest:
            raise ValueError("Weekly artifact checksum mismatch")
    for name, digest in manifest["source_hashes"].items():
        if file_hash(name) != digest:
            raise ValueError("Weekly source mismatch")
    data = strict_json(root / "recommendations.json")
    if (data.get("schema_version") != 1 or data.get("status") != "REVIEW_REQUIRED"
            or fingerprint({k: v for k, v in data.items() if k != "research_id"}) != data["research_id"]):
        raise ValueError("Weekly research identity mismatch")
    if data["execution_enabled"] is not False or data["promotion_enabled"] is not False:
        raise ValueError("Weekly portfolios must remain review-only")
    if set(data["candidates"]) != set(POLICIES):
        raise ValueError("All declared holding periods required")
    for candidate in data["candidates"].values():
        rows = candidate["allocations"]
        if (any(not np.isfinite(r["weight"]) or r["weight"] < 0 for r in rows)
                or not np.isclose(sum(r["weight"] for r in rows), 1., atol=1e-8)
                or not np.isclose(sum(r["risk_share"] for r in rows), 1., atol=1e-7)):
            raise ValueError("Weekly capital and risk must reconcile")
    return data


def published(root):
    root = Path(root)
    pointer = strict_json(root / "latest.json")
    revision = pointer["research_id"]
    if not isinstance(revision, str) or len(revision) != 64 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("Invalid weekly research revision")
    directory = root / revision
    if directory.is_symlink():
        raise ValueError("Symlink weekly release rejected")
    data = verify(directory)
    if data["research_id"] != revision:
        raise ValueError("Weekly revision identity mismatch")
    return directory, data


def run(bundle, output, now=None):
    from weekly_portfolio_report import report_pdf
    bundle, output = Path(bundle), Path(output)
    b = strict_json(bundle)
    report = load_training_report(b["training_report"])
    if not report["current_numerical_source_match"]:
        raise ValueError("Current source-matched training required")
    session = weekly_session(now or datetime.now(timezone.utc))
    prices = extended_prices(b["capture"], b["benchmark_extension"])
    data = build(prices, session)
    from strategy_dashboard_server import read_payload
    from strategy_integrity import verify_seal
    pointer = strict_json("var/dashboard-live/latest.json")
    document = Path(pointer["document"])
    if file_hash(document) != pointer["document_sha256"]:
        raise ValueError("Dashboard document checksum mismatch")
    dashboard = read_payload(document)
    verify_seal(document, dashboard)
    data["dashboard_context"] = dict(market_session=dashboard["training"]["market_session"],
        document_sha256=file_hash(document), training_status=dashboard["training"]["status"],
        macro_available=dashboard["training"]["latest_macro_available"],
        plans=[dict(title=p["title"], status=p["qualification"]["status"],
                    weights=p["allocation"]["weights"], volatility=p["allocation"]["planning_annual_volatility"],
                    expected_return=p["allocation"]["planning_expected_annual_return"],
                    limitations=p["limitations"]) for p in dashboard["plans"]],
        growth={k: dashboard["growth_resilience"][k] for k in ("name", "status", "weights", "metrics", "start", "end", "limitations")},
        dynamic_status=dashboard.get("dynamic_portfolio", {}).get("snapshot", {}).get("status", "UNAVAILABLE"),
        engine_status=dashboard.get("return_engines", {}).get("status", "UNAVAILABLE"))
    data["input_evidence"] = dict(bundle_sha256=file_hash(bundle), capture_sha256=file_hash(b["capture"]),
                                  training_sha256=file_hash(b["training_report"]))
    data["research_id"] = fingerprint(data)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    atomic_json(output / "recommendations.json", data)
    report_pdf(data, output / "dashboard-report.pdf")
    atomic_json(output / "manifest.json", dict(schema_version=1,
        files={n: file_hash(output / n) for n in ("recommendations.json", "dashboard-report.pdf")},
        source_hashes={n: file_hash(n) for n in SOURCES}))
    verify(output)
    return data["research_id"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(run(args.bundle, args.output))
