"""Append-only diagnostic risk forecasts for strictly future full close-to-close windows."""

from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
from strategy_integrity import strict_json, fingerprint, file_hash
from strategy_receipts import atomic_json
from strategy_monthly_report import read_events


def register(database, prices, root, *, cohort, now, sessions=21):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    event, head = read_events(database)[-1]
    if str(prices.index[-1].date()) != event["session"]:
        raise ValueError("Risk forecast data/cohort session mismatch")
    cal = mcal.get_calendar("NYSE").schedule(
        now.date(), pd.Timestamp(now) + pd.Timedelta(days=80)
    )
    upcoming = cal[cal.market_close > pd.Timestamp(now)]
    # Return window starts after a strictly future close, never partly elapsed overnight P&L.
    dates = upcoming.index[1 : sessions + 1]
    if len(dates) != sessions:
        raise ValueError("Future exchange risk window missing")
    history = prices.pct_change(fill_method=None).tail(252)
    for name, state in event["states"].items():
        key = fingerprint(
            dict(
                cohort=cohort,
                strategy=name,
                origin=event["session"],
                method=file_hash(__file__),
            )
        )
        path = root / (key + ".json")
        if path.exists():
            old = strict_json(path)
            if old["chain_head"] != head:
                raise ValueError("Risk origin already registered with another event")
            continue
        weights = (state.get("pending") or {}).get("weights", state["weights"])
        held = [s for s, w in weights.items() if w > 0 and s != "USD_CASH"]
        values = history[held].to_numpy()
        if not np.isfinite(values).all():
            raise ValueError("Missing held risk forecast inputs")
        w = np.array([weights[s] for s in held])
        cov = history[held].cov().to_numpy() * 252
        sigma = float(np.sqrt(max(float(w @ cov @ w), 0)))
        record = dict(
            id=key,
            cohort=cohort,
            strategy=name,
            chain_head=head,
            origin_session=event["session"],
            issued_at=now.isoformat(),
            first_session=str(dates[0].date()),
            last_session=str(dates[-1].date()),
            sessions=sessions,
            annual_volatility=sigma,
            basis="252-day covariance on registered starting/next-fill target; gross price-risk diagnostic; future rebalancing may change risk",
            promotion_enabled=False,
        )
        record["record_sha256"] = fingerprint(record)
        atomic_json(path, record, exclusive=True)
    return read(root)


def read(root):
    result = []
    for path in sorted(Path(root).glob("*.json")):
        f = strict_json(path)
        if (
            path.stem != f["id"]
            or fingerprint({k: v for k, v in f.items() if k != "record_sha256"})
            != f.get("record_sha256")
            or datetime.fromisoformat(f["issued_at"]).tzinfo is None
            or f["sessions"] < 2
            or not np.isfinite(f["annual_volatility"])
            or f["annual_volatility"] < 0
        ):
            raise ValueError("Invalid risk forecast registry")
        result.append(f)
    return result
