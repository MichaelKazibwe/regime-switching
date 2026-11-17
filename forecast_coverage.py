"""Prospective weekly-portfolio interval coverage, anchored after genuine issuance."""

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

from strategy_integrity import fingerprint, strict_json
from strategy_receipts import atomic_json


def issue(research, root, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Aware forecast issuance timestamp required")
    schedule = mcal.get_calendar("NYSE").schedule(
        now.date(), (pd.Timestamp(now) + pd.Timedelta(days=15)).date()
    )
    week_end = schedule.groupby(schedule.index.to_period("W-FRI")).tail(1)
    future = week_end[week_end.market_close > pd.Timestamp(now)]
    if future.empty:
        raise ValueError("No later actual weekly execution close")
    fill = str(future.index[0].date())
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    records = []
    for name, candidate in research["candidates"].items():
        for horizon, projection in candidate["projections"].items():
            document = dict(
                schema_version=1,
                research_id=research["research_id"],
                policy=name,
                source_week=research["market_session"],
                issued_at=now.isoformat(),
                first_execution_close=fill,
                horizon_weeks=int(horizon),
                weights={r["symbol"]: r["weight"] for r in candidate["allocations"]},
                lower=projection["p05_return"],
                upper=projection["p95_return"],
                median=projection["median_return"],
                cost_rate=0.0015,
                protocol="FIXED_TARGET_WEEKLY_SELF_FINANCING_V1",
                execution_enabled=False,
            )
            identity = fingerprint(
                {k: v for k, v in document.items() if k != "issued_at"}
            )
            document["forecast_id"] = identity
            path = root / (identity + ".json")
            if path.exists():
                previous = strict_json(path)
                if (
                    fingerprint(
                        {
                            k: v
                            for k, v in previous.items()
                            if k not in {"issued_at", "forecast_id"}
                        }
                    )
                    != identity
                ):
                    raise ValueError("Stored forecast identity mismatch")
            else:
                atomic_json(path, document, exclusive=True)
            records.append(identity)
    return records


def realized(record, prices, *, as_of):
    stamp = pd.Timestamp(as_of)
    if stamp.tzinfo is None:
        raise ValueError("Aware realized-outcome cutoff required")
    prices = prices.loc[
        prices.index
        <= stamp.tz_convert("America/New_York").tz_localize(None).normalize()
    ]
    held = [s for s, w in record["weights"].items() if s != "USD_CASH" and w > 0]
    if set(held) - set(prices):
        return dict(status="UNSCORABLE_MISSING_HOLDINGS")
    selected = prices[held]
    # A partial current week must never be mistaken for a completed outcome.
    schedule = mcal.get_calendar("NYSE").schedule(
        record["first_execution_close"], (stamp + pd.Timedelta(days=7)).date()
    )
    expected = schedule.groupby(schedule.index.to_period("W-FRI")).tail(1)
    complete = expected.loc[expected.market_close <= stamp]
    last = selected.reindex(complete.index)
    h = record["horizon_weeks"]
    if len(last) < h + 1:
        return dict(status="PENDING")
    last = last.iloc[: h + 1]
    if (
        str(last.index[0].date()) != record["first_execution_close"]
        or not np.isfinite(last.to_numpy()).all()
        or (last <= 0).any().any()
    ):
        return dict(status="UNSCORABLE_MISSING_OR_INVALID_OBSERVATIONS")
    weights = np.array([record["weights"][s] for s in held], float)
    rate = record["cost_rate"]
    assets = weights / (1 + rate * weights.sum())
    cash = (1 - weights.sum()) / (1 + rate * weights.sum())
    for change in last.pct_change(fill_method=None).iloc[1:].to_numpy():
        assets *= 1 + change
        before = float(cash + assets.sum())
        nav = before
        for _ in range(100):
            updated = before - rate * np.abs(nav * weights - assets).sum()
            if abs(updated - nav) < 1e-13:
                break
            nav = updated
        else:
            raise ValueError("Prospective self-financing replay did not converge")
        nav = updated
        assets = nav * weights
        cash = nav * (1 - weights.sum())
    outcome = float(assets.sum() + cash - 1)
    return dict(
        status="MATURED",
        outcome_session=str(last.index[-1].date()),
        realized_return=outcome,
        interval_hit=record["lower"] <= outcome <= record["upper"],
        median_error=outcome - record["median"],
        outcome_evidence_sha256=fingerprint(
            dict(
                dates=[str(d.date()) for d in last.index],
                prices=last.to_numpy().tolist(),
            )
        ),
    )


def evaluate(root, prices, *, as_of):
    root = Path(root)
    records = []
    for path in sorted(root.glob("*.json")):
        record = strict_json(path)
        if "forecast_id" not in record:
            continue
        expected = fingerprint(
            {k: v for k, v in record.items() if k not in {"forecast_id", "issued_at"}}
        )
        if expected != record["forecast_id"]:
            raise ValueError("Prospective interval receipt changed")
        if pd.Timestamp(record["issued_at"]) > pd.Timestamp(as_of):
            continue
        records.append(
            dict(
                forecast_id=record["forecast_id"],
                policy=record["policy"],
                horizon_weeks=record["horizon_weeks"],
                issued_at=record["issued_at"],
                **realized(record, prices, as_of=as_of),
            )
        )
    groups = []
    for key in sorted({(r["policy"], r["horizon_weeks"]) for r in records}):
        values = [r for r in records if (r["policy"], r["horizon_weeks"]) == key]
        mature = [r for r in values if r["status"] == "MATURED"]
        groups.append(
            dict(
                policy=key[0],
                horizon_weeks=key[1],
                issued=len(values),
                matured=len(mature),
                pending=sum(r["status"] == "PENDING" for r in values),
                empirical_coverage=float(np.mean([r["interval_hit"] for r in mature]))
                if mature
                else None,
                mean_absolute_median_error=float(
                    np.mean([abs(r["median_error"]) for r in mature])
                )
                if mature
                else None,
            )
        )
    return dict(
        status="PROSPECTIVE_COVERAGE_MONITOR",
        as_of=str(as_of),
        groups=groups,
        outcomes=records,
        calibrated_intervals_established=False,
        execution_enabled=False,
        limitations=[
            "Targets start at the first actual weekly execution close strictly after issuance.",
            "Potentially overlapping origins; descriptive coverage is not an independent confidence interval.",
            "Costs match declared weekly scenario assumptions; taxes, FX fees and cash yield remain unqualified.",
        ],
    )
