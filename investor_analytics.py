"""Dated investor diagnostics. No allocation changes, orders or calibrated forecasts."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from assetuniverse import DIVERSIFIED_ASSETS
from macro_feature_contract import CONTRACT_VERSION

REGIMES = (
    "disinflationary_growth",
    "inflationary_growth",
    "stagflation",
    "deflationary_slowdown",
)
INDICATORS = {
    "ip_growth": (
        "Industrial production growth",
        "% annualized, trailing 6 months",
        "INDPRO",
    ),
    "inflation_yoy": ("CPI inflation", "% year over year", "CPIAUCSL"),
    "inflation_change": (
        "Inflation momentum",
        "percentage points vs 3 months ago",
        "CPIAUCSL",
    ),
    "unemployment_change": (
        "Unemployment momentum",
        "pp, recent vs prior 3-month average",
        "UNRATE",
    ),
    "yield_curve": (
        "Treasury curve · 10Y minus 3M",
        "percentage points",
        "DGS10 / DGS3MO",
    ),
}
STRATEGIES = {
    "disinflationary_growth": (
        "Defensive Growth",
        "Review diversified equity participation with nominal bonds and a liquidity reserve; keep trend and volatility controls.",
    ),
    "inflationary_growth": (
        "Inflation Resilience",
        "Review inflation-linked bonds, gold and broad commodities alongside diversified equities; assess nominal-duration concentration.",
    ),
    "stagflation": (
        "Inflation Resilience / Tail-Aware Ensemble",
        "Review lower equity and credit exposure, inflation diversification and liquidity. Examine correlated bond/equity losses.",
    ),
    "deflationary_slowdown": (
        "Economic Balance",
        "Review high-quality government duration and liquidity, with reduced cyclical equity/credit exposure; assess real-rate and gap risk.",
    ),
}


def _stamp(value):
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        raise ValueError("Macro availability must be timezone-aware")
    return stamp.tz_convert("UTC")


def macro_context(features, as_of, *, forecasts=None, paths=2000, seed=103026):
    """Fit an explicit research-only monthly AR(1) conditional outlook, past data only."""
    cutoff = _stamp(as_of)
    if (
        isinstance(paths, bool)
        or not isinstance(paths, int)
        or not 100 <= paths <= 10000
    ):
        raise ValueError("Conditional outlook requires 100-10000 paths")
    rows = [
        r
        for r in features
        if _stamp(r["as_of"]) <= cutoff
        and pd.Timestamp(r["date"]).date() <= cutoff.date()
    ]
    if not rows:
        return {
            "status": "UNAVAILABLE",
            "reason": "No macro observations available by this plan decision time.",
        }
    rows.sort(key=lambda r: _stamp(r["as_of"]))
    if len({r["date"] for r in rows}) != len(rows):
        raise ValueError("Duplicate macro feature dates")
    keys = list(INDICATORS)
    frame = pd.DataFrame(
        [{**{k: r[k] for k in keys}, "date": r["date"]} for r in rows]
    ).set_index("date")
    frame.index = pd.to_datetime(frame.index)
    if not np.isfinite(frame.to_numpy(dtype=float)).all():
        raise ValueError("Nonfinite macro features")
    latest = rows[-1]
    probabilities = np.array([latest["probabilities"][r] for r in REGIMES], dtype=float)
    if (
        not np.isfinite(probabilities).all()
        or (probabilities < 0).any()
        or not np.isclose(probabilities.sum(), 1)
    ):
        raise ValueError("Invalid current regime scores")
    observed_dates = latest.get("observation_dates", {})
    if any(pd.Timestamp(d).date() > cutoff.date() for d in observed_dates.values()):
        raise ValueError("Future macro observation date")
    regime = REGIMES[int(probabilities.argmax())]
    indicators = []
    for k, (label, unit, source) in INDICATORS.items():
        source_dates = [observed_dates.get(s.strip()) for s in source.split("/")]
        indicators.append(
            {
                "key": k,
                "label": label,
                "unit": unit,
                "value": float(latest[k]),
                "source": source,
                "observation_dates": [d for d in source_dates if d],
                "history": [[r["date"], float(r[k])] for r in rows[-252:]],
            }
        )
    monthly = frame.groupby(frame.index.to_period("M")).last()
    # Preserve missing calendar months as gaps, not adjacent fitting rows.
    calendar = pd.period_range(
        max(monthly.index[0], monthly.index[-1] - 119), monthly.index[-1], freq="M"
    )
    monthly = monthly.reindex(calendar)
    values = monthly.to_numpy(dtype=float)
    complete = np.isfinite(values).all(axis=1)
    pairs = complete[:-1] & complete[1:]
    monthly_count = int(complete.sum())
    fitting_pairs = int(pairs.sum())
    residual_block_count = 0
    quarters = []
    age_days = (cutoff - _stamp(latest["as_of"])).total_seconds() / 86400
    current_calendar_contract = all(
        row.get("feature_contract") == CONTRACT_VERSION
        and row.get("source_kind") == "CURRENT_REVISED_FRED_NOT_HISTORICAL_VINTAGES"
        for row in rows
    )
    possible_blocks = sum(pairs[i : i + 3].all() for i in range(len(pairs) - 2))
    if (
        age_days <= 10
        and monthly_count >= 36
        and fitting_pairs >= 35
        and possible_blocks > 0
        and (complete.all() or current_calendar_contract)
    ):
        mean = values[complete].mean(axis=0)
        x = values[:-1] - mean
        y = values[1:] - mean
        phi = np.clip(
            (x[pairs] * y[pairs]).sum(axis=0)
            / (
                (x[pairs] * x[pairs]).sum(axis=0)
                + 12 * values[complete].var(axis=0)
                + 1e-12
            ),
            0,
            0.98,
        )
        residual = y - x * phi
        residual -= residual[pairs].mean(axis=0)
        # Invalid transitions stay unavailable; no block crosses a missing month.
        block_starts = np.array(
            [i for i in range(len(residual) - 2) if pairs[i : i + 3].all()], dtype=int
        )
        residual_block_count = len(block_starts)
        rng = np.random.default_rng(seed)
        simulations = np.broadcast_to(values[-1], (paths, len(keys))).copy()
        period = cutoff.tz_localize(None).to_period("Q")
        if period.end_time.date() <= cutoff.date():
            period += 1
        targets = [period + i for i in range(4)]
        steps = [
            max(
                1,
                (q.end_time.year - monthly.index[-1].year) * 12
                + q.end_time.month
                - monthly.index[-1].month,
            )
            for q in targets
        ]
        draws = {}
        # Joint residual vectors preserve contemporaneous cross-variable innovations.
        starts = rng.choice(block_starts, size=paths)
        for month in range(1, max(steps) + 1):
            if (month - 1) % 3 == 0:
                starts = rng.choice(block_starts, size=paths)
            shock = residual[starts + (month - 1) % 3]
            simulations = mean + phi * (simulations - mean) + shock
            if month in steps:
                draws[month] = simulations.copy()
        for q, step in zip(targets, steps):
            simulated = draws[step]
            growth = (simulated[:, 0] > 0) & (simulated[:, 3] < 0.25)
            inflation = simulated[:, 2] > 0
            labels = np.where(
                growth, np.where(inflation, 1, 0), np.where(inflation, 2, 3)
            )
            frequency = np.bincount(labels, minlength=4) / paths
            dominant = REGIMES[int(frequency.argmax())]
            quarters.append(
                {
                    "quarter": str(q),
                    "end_date": str(q.end_time.date()),
                    "months_ahead": step,
                    "variables": {
                        k: {
                            "p05": float(np.quantile(simulated[:, j], 0.05)),
                            "median": float(np.median(simulated[:, j])),
                            "p95": float(np.quantile(simulated[:, j], 0.95)),
                        }
                        for j, k in enumerate(keys)
                    },
                    "regime_frequencies": dict(zip(REGIMES, map(float, frequency))),
                    "dominant_regime": dominant,
                    "strategy": STRATEGIES[dominant][0],
                    "guidance": STRATEGIES[dominant][1],
                }
            )
    prior = None
    if forecasts:
        eligible = [
            (d, r)
            for d, r in forecasts.items()
            if pd.Timestamp(d).date() <= cutoff.date() and _stamp(r["as_of"]) <= cutoff
        ]
        if eligible:
            d, f = max(eligible, key=lambda pair: pair[0])
            prior = {
                "feature_date": d,
                "issued_at": f["as_of"],
                "model_enabled": bool(f["enabled"]),
                "horizon_sessions": 63,
                "used": f["used"],
                "description": "Archived 63-session research classifier; baseline used when its validation gate is off. Not calibrated recession probabilities.",
            }
    return {
        "status": "HISTORICAL_RESEARCH_CONTEXT"
        if age_days <= 10
        else "STALE_HISTORICAL_CONTEXT",
        "snapshot_age_days": age_days,
        "as_of": latest["as_of"],
        "feature_date": latest["date"],
        "current_regime": regime,
        "current_scores": dict(zip(REGIMES, map(float, probabilities))),
        "indicators": indicators,
        "quarterly": quarters,
        "archived_classifier": prior,
        "strategy": STRATEGIES[regime][0],
        "guidance": STRATEGIES[regime][1],
        "method": f"Trailing 120 monthly snapshots; shrunk diagonal AR(1) fitted only to consecutive observed month pairs, complete joint 3-month residual blocks, {paths} paths. Conditional 5th/median/95th percentiles; no parameter-uncertainty model.",
        "limitations": [
            "Historical, dated research context - not current live macro data.",
            "Regime scores and simulated frequencies are not calibrated economic or financial-loss probabilities.",
            "Quarterly variable forecasts are unvalidated conditional research estimates, not central-bank forecasts.",
            "Strategy guidance is for review only. It does not modify the selected portfolio or its risk limits.",
        ],
        "monthly_training_count": monthly_count,
        "monthly_training_pairs": fitting_pairs,
        "residual_calendar_blocks": residual_block_count,
        "calendar_gap_policy": "observed_consecutive_pairs_only"
        if current_calendar_contract
        else "complete_calendar_required",
        "missing_training_months": [str(period) for period in monthly.index[~complete]],
        "fitting_pair_months": [
            [str(monthly.index[i]), str(monthly.index[i + 1])]
            for i in np.flatnonzero(pairs)
        ],
        "seed": seed,
        "paths": paths,
    }


def portfolio_diagnostics(result, prices, features):
    """Retrospective fixed-weight sensitivity; never claims actual strategy performance."""
    weights = result["allocation"].get("weights")
    if not weights or result["mandate"]["base_currency"] != "USD":
        return {
            "status": "UNAVAILABLE",
            "reason": "Feasible USD weights and observed prices required; no currency translation invented.",
        }
    cutoff = pd.Timestamp(result["price_session"])
    active = {s: w for s, w in weights.items() if s != "USD_CASH" and w > 1e-8}
    if any(s not in prices for s in active):
        return {
            "status": "UNAVAILABLE",
            "reason": "A held instrument has no observed price series.",
        }
    observed = prices.loc[prices.index <= cutoff, list(active)]
    if (observed <= 0).any().any() or np.isinf(observed.to_numpy(dtype=float)).any():
        raise ValueError("Invalid held-instrument prices")
    returns = observed.pct_change(fill_method=None)
    returns = returns.dropna()
    if len(returns) < 252:
        return {
            "status": "UNAVAILABLE",
            "reason": "Fewer than 252 complete held-instrument returns.",
        }
    series = returns @ pd.Series(active)
    # Retain only consecutive NYSE sessions; gaps cannot be interpreted as daily return chains.
    import pandas_market_calendars as mcal

    calendar = mcal.get_calendar("NYSE")
    expected = calendar.schedule(series.index[0], series.index[-1]).index
    if not series.index.equals(expected):
        return {
            "status": "UNAVAILABLE",
            "reason": "Held-instrument history has missing sessions; no gap filling or stitched performance.",
        }
    wealth = (1 + series).cumprod()
    dd = wealth / wealth.cummax().clip(lower=1) - 1
    vol = series.rolling(63, min_periods=63).std(ddof=1) * np.sqrt(252)
    eligible = [r for r in features if _stamp(r["as_of"]) <= _stamp(result["as_of"])]
    rows = []
    for quarter, part in series.groupby(series.index.to_period("Q")):
        if quarter.end_time.normalize() > cutoff:
            continue
        sessions = calendar.schedule(quarter.start_time, quarter.end_time).index
        if not part.index.equals(sessions):
            continue
        prior = [
            r for r in eligible if _stamp(r["as_of"]).date() < part.index[0].date()
        ]
        if not prior:
            continue
        f = max(prior, key=lambda r: r["as_of"])
        label = max(f["probabilities"], key=f["probabilities"].get)
        rows.append(
            {
                "quarter": str(quarter),
                "return": float((1 + part).prod() - 1),
                "regime": label,
                "feature_date": f["date"],
                **{k: float(f[k]) for k in INDICATORS},
            }
        )
    regimes = []
    for regime in REGIMES:
        sample = [q["return"] for q in rows if q["regime"] == regime]
        regimes.append(
            {
                "regime": regime,
                "quarters": len(sample),
                "mean_quarter_return": float(np.mean(sample)) if sample else None,
                "p05": float(np.quantile(sample, 0.05)) if len(sample) >= 4 else None,
                "p95": float(np.quantile(sample, 0.95)) if len(sample) >= 4 else None,
            }
        )
    correlations = {}
    if len(rows) >= 8:
        table = pd.DataFrame(rows)
        for k in INDICATORS:
            value = (
                table[k].corr(table["return"])
                if table[k].std() > 1e-12 and table["return"].std() > 1e-12
                else np.nan
            )
            correlations[k] = float(value) if np.isfinite(value) else None
    downside = series[series < 0]
    threshold = float(series.quantile(0.05))
    metrics = {
        "total_return": float(wealth.iloc[-1] - 1),
        "annualized_volatility": float(series.std(ddof=1) * np.sqrt(252)),
        "max_drawdown": float(-dd.min()),
        "historical_daily_var95": max(0, -threshold),
        "historical_daily_es95": max(0, -float(series[series <= threshold].mean())),
        "negative_day_frequency": float(len(downside) / len(series)),
    }
    return {
        "status": "RETROSPECTIVE_FIXED_WEIGHT_DIAGNOSTIC",
        "start": str(series.index[0].date()),
        "end": str(series.index[-1].date()),
        "label": "Retrospective constant-weight diagnostic, not actual account or dynamic strategy returns",
        "assumptions": "Today's saved weights applied retrospectively with daily rebalancing; gross of trading costs/taxes/platform fees; uninvested cash yield assumed zero. Selection hindsight is present.",
        "metrics": metrics,
        "history": [
            [
                str(d.date()),
                float(wealth.loc[d]),
                float(dd.loc[d]),
                float(vol.loc[d]) if np.isfinite(vol.loc[d]) else None,
            ]
            for d in series.index[-1260:]
        ],
        "regimes": regimes,
        "quarterly": rows,
        "correlations": correlations,
    }


def build_context(
    results,
    *,
    prices=None,
    features_path=None,
    forecasts_path=None,
    research_allocation_path=None,
    latest_features_path=None,
):
    features = json.loads(Path(features_path).read_text()) if features_path else []
    forecasts = json.loads(Path(forecasts_path).read_text()) if forecasts_path else None
    latest_base = None
    if latest_features_path:
        latest_rows = json.loads(Path(latest_features_path).read_text())
        if not latest_rows or any(
            r.get("source_kind") != "CURRENT_REVISED_FRED_NOT_HISTORICAL_VINTAGES"
            for r in latest_rows
        ):
            raise ValueError(
                "Latest overlay requires explicitly current/revised FRED features"
            )
        now = datetime.now(timezone.utc)
        if any(_stamp(r["as_of"]) > pd.Timestamp(now) for r in latest_rows):
            raise ValueError("Future current-macro availability timestamp")
        latest_base = macro_context(latest_rows, now.isoformat())
        if latest_base["status"] == "HISTORICAL_RESEARCH_CONTEXT":
            latest_base["status"] = "LATEST_AVAILABLE_FRED_CONTEXT"
        latest_base["limitations"][0] = (
            "Latest FRED snapshot is separate from the saved portfolio. Historical training observations are revised as of retrieval, not historical vintages."
        )
        latest_base["limitations"].append(
            "Macro-only descriptive regime scores are not the market/macro production strategy state. No allocation or client risk limit is updated."
        )
    snapshots = {}
    for r in results:
        macro = (
            macro_context(features, r["as_of"], forecasts=forecasts)
            if features
            else {
                "status": "UNAVAILABLE",
                "reason": "No dated macro features supplied.",
            }
        )
        diag = (
            portfolio_diagnostics(r, prices, features)
            if prices is not None
            else {
                "status": "UNAVAILABLE",
                "reason": "No observed price history supplied.",
            }
        )
        overlays = {"macro": macro}
        if latest_base is not None:
            overlays["latest_macro"] = deepcopy(latest_base)
        for overlay in overlays.values():
            for q in overlay.get("quarterly", []):
                records = {g["regime"]: g for g in diag.get("regimes", [])}
                usable = {
                    k: v
                    for k, v in q["regime_frequencies"].items()
                    if records.get(k, {}).get("quarters", 0) >= 4
                }
                coverage = sum(usable.values())
                q["portfolio_scenario"] = {
                    "coverage": coverage,
                    "mean_quarter_return": sum(
                        v * records[k]["mean_quarter_return"] for k, v in usable.items()
                    )
                    / coverage
                    if coverage >= 0.8
                    else None,
                    "label": "Regime-weighted historical quarter mean; not a calibrated return forecast. Missing/low-count regimes excluded; coverage shown.",
                }
        snapshots[r["recommendation_id"]] = {**overlays, "diagnostics": diag}
    research = None
    if research_allocation_path:
        trades = json.loads(Path(research_allocation_path).read_text())
        cutoff = min(pd.Timestamp(r["price_session"]) for r in results)
        valid = [t for t in trades if pd.Timestamp(t["execution_date"]) <= cutoff]
        if valid:
            trade = max(valid, key=lambda t: t["execution_date"])
            weights = {s: float(trade["weights"].get(s, 0)) for s in DIVERSIFIED_ASSETS}
            cash = float(trade["cash"])
            if min([*weights.values(), cash]) < 0 or not np.isclose(
                sum(weights.values()) + cash, 1, atol=1e-6
            ):
                raise ValueError("Research allocation does not reconcile")
            research = {
                "date": trade["execution_date"],
                "weights": weights,
                "cash": cash,
                "status": "ARCHIVED_RESEARCH_TARGET_NOT_SELECTED_PLAN",
            }
    sources = {
        role: hashlib.sha256(Path(path).read_bytes()).hexdigest()
        for role, path in (
            ("plan_features", features_path),
            ("archived_classifier", forecasts_path),
            ("research_allocation", research_allocation_path),
            ("latest_features", latest_features_path),
        )
        if path
    }
    return {
        "plans": snapshots,
        "core_symbols": list(DIVERSIFIED_ASSETS),
        "research_allocation": research,
        "source_hashes": sources,
    }
