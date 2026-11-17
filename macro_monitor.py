"""Daily as-known macro observations and transparent calendar-quarter aggregates."""

from pathlib import Path

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

from macrovintage import MacroVintageData
from strategy_integrity import strict_json, file_hash, fingerprint
from strategy_report import load_training_report

SERIES = {
    "UNRATE": ("Unemployment rate", "%"),
    "CPIAUCSL": ("Consumer price index", "index"),
    "INDPRO": ("Industrial production", "index"),
    "DGS10": ("10-year Treasury yield", "%"),
    "DGS3MO": ("3-month Treasury yield", "%"),
}


def as_known(data, stamp, key):
    eligible = data.releases.loc[data.releases.available_at <= pd.Timestamp(stamp)]
    latest = eligible.drop_duplicates("date", keep="last").dropna(subset=["value"]).tail(1)
    if latest.empty:
        return dict(value=None, observation_date=None, available_at=None, status="UNAVAILABLE")
    row = latest.iloc[0]
    age = (pd.Timestamp(stamp).tz_convert("America/New_York").date() - row.date.date()).days
    stale = age > (14 if key in {"DGS10", "DGS3MO"} else 90)
    return dict(value=None if stale else float(row.value), observation_date=str(row.date.date()),
                available_at=row.available_at.isoformat(), age_days=age,
                status="STALE" if stale else "AVAILABLE")


def aggregate(rows, expected_sessions, market_session):
    """Equal-weight daily context means; compounded observed SPY returns, no filling."""
    result = []
    quarters = sorted({r["quarter"] for r in rows}, reverse=True)
    for quarter in quarters:
        observations = [r for r in rows if r["quarter"] == quarter]
        expected = [d for d in expected_sessions if str(pd.Period(d, freq="Q")) == quarter and d <= market_session]
        dates = {r["date"] for r in observations}
        valid = [r for r in observations if r["macro_valid"]]
        returns = [r["spy_return"] for r in observations if r["spy_return"] is not None]
        means, coverage, releases = {}, {}, {}
        for key in SERIES:
            items = [r["series"][key] for r in observations if r["series"][key]["value"] is not None]
            means[key] = float(np.mean([i["value"] for i in items])) if items else None
            coverage[key] = len(items)
            releases[key] = len({(i["observation_date"], i["available_at"]) for i in items})
        curve = [r["yield_curve"] for r in observations if r["yield_curve"] is not None]
        regimes = {r: sum(item["regime"] == r for item in valid) / len(valid)
                   for r in sorted({item["regime"] for item in valid})} if valid else {}
        result.append(dict(quarter=quarter, observed_sessions=len(observations), expected_sessions=len(expected),
            missing_sessions=sorted(set(expected) - dates), valid_macro_sessions=len(valid),
            macro_coverage=len(valid) / len(expected) if expected else 0.,
            complete=bool(expected and set(expected) == dates),
            period_status="QUARTER_TO_DATE" if quarter == str(pd.Period(market_session, freq="Q")) else "HISTORICAL_QUARTER",
            spy_compounded_return=float(np.prod(1 + np.array(returns)) - 1) if returns and len(returns) == len(expected) and set(expected) == dates else None,
            daily_context_means=means, available_sessions=coverage, distinct_observation_vintages=releases,
            mean_yield_curve=float(np.mean(curve)) if curve else None,
            valid_regime_frequencies=regimes))
    return result


def build(capture_path, training_path):
    capture_path, training_path = Path(capture_path), Path(training_path)
    capture, report = strict_json(capture_path), load_training_report(training_path)
    if file_hash(capture_path) != report["capture_sha256"] or not report["current_numerical_source_match"]:
        raise ValueError("Source-matched macro monitoring inputs required")
    for name, digest in capture["files"].items():
        if Path(name).name != name or (capture_path.parent / name).is_symlink() or file_hash(capture_path.parent / name) != digest:
            raise ValueError("Macro capture integrity mismatch")
    features = strict_json(training_path.parent / "features.json")
    if [r["date"] for r in features] != sorted({r["date"] for r in features}) or features[-1]["date"] != report["market_session"]:
        raise ValueError("Unique sorted features through the market session required")
    start = (pd.Period(report["market_session"], freq="Q") - 7).start_time
    features = [r for r in features if pd.Timestamp(r["date"]) >= start]
    sources = {key: MacroVintageData.from_csv(capture_path.parent / f"{key}.csv",
               expected_sha256=capture["files"][f"{key}.csv"]) for key in SERIES}
    prices = pd.read_csv(capture_path.parent / "prices.csv", index_col=0, parse_dates=True)
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("Unique sorted market observations required")
    spy = prices.SPY.pct_change(fill_method=None)
    expected = [str(d.date()) for d in mcal.get_calendar("NYSE").schedule(start, report["market_session"]).index]
    if any(r["date"] not in expected for r in features):
        raise ValueError("Daily monitoring rows must be completed trading sessions")
    rows, previous = [], {}
    for feature in features:
        stamp = pd.Timestamp(feature["as_of"])
        if stamp.tzinfo is None or str(stamp.tz_convert("America/New_York").date()) != feature["date"]:
            raise ValueError("Daily decision timestamp mismatch")
        values = {key: as_known(source, stamp, key) for key, source in sources.items()}
        for key, item in values.items():
            signature = (item["value"], item["observation_date"], item["available_at"])
            item["update"] = "INITIAL_CONTEXT" if key not in previous else "NEW_OR_REVISED" if previous[key] != signature else "CARRIED_FORWARD"
            previous[key] = signature
        a, b = values["DGS10"], values["DGS3MO"]
        curve = a["value"] - b["value"] if a["value"] is not None and b["value"] is not None and a["observation_date"] == b["observation_date"] else None
        value = spy.get(pd.Timestamp(feature["date"]))
        valid = bool(feature.get("macro_valid", False))
        rows.append(dict(date=feature["date"], quarter=str(pd.Period(feature["date"], freq="Q")), as_of=feature["as_of"],
            series=values, yield_curve=curve, macro_valid=valid,
            regime=feature["regime"] if valid else "UNAVAILABLE",
            reason=feature.get("macro_unavailable_reason") if not valid else None,
            spy_return=float(value) if value is not None and np.isfinite(value) else None))
    result = dict(schema_version=1, status="DAILY_AS_KNOWN_MONITOR", market_session=report["market_session"],
        captured_at=capture["captured_at"], training_run_id=report["run_id"], rows=rows,
        series={key: dict(label=label, unit=unit) for key, (label, unit) in SERIES.items()},
        quarters=aggregate(rows, expected, report["market_session"]),
        provenance=dict(capture_sha256=file_hash(capture_path), training_sha256=file_hash(training_path),
                        features_sha256=file_hash(training_path.parent / "features.json")),
        method="Daily as-known context reconstructed from captured ALFRED vintages. Releases become usable at the next New York midnight. "
               "Monthly indicators repeat until a new observation or revision becomes available. Quarterly means average available daily contexts, "
               "not independent releases or official quarterly statistics. Missing values are excluded and coverage is disclosed. "
               "SPY is an adjusted-close market reference: daily returns compound only when every expected session has a return. "
               "Historical reconstructed rows are not a live-issued forecast ledger. Quarterly scenario forecasts remain separate.",
        execution_enabled=False, promotion_enabled=False)
    result["monitor_id"] = fingerprint(result)
    return result
