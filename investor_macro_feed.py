"""Current FRED macro overlay, isolated from point-in-time historical research.

Historical rows here use today's revised observations and carry today's
availability timestamp. They must never be fed to historical strategy tests.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import pandas as pd

from investor_analytics import REGIMES
from productreport import private_write
from macro_feature_contract import calculate_macro_features, MacroFeatureUnavailable

SERIES = ("UNRATE", "CPIAUCSL", "INDPRO", "DGS10", "DGS3MO")


def current_features(observations, as_of):
    stamp = pd.Timestamp(as_of)
    if stamp.tzinfo is None:
        raise ValueError("Aware retrieval timestamp required")
    cutoff = stamp.tz_convert("UTC").tz_localize(None).normalize()
    if set(observations) != set(SERIES):
        raise ValueError("All five FRED series required")
    cleaned = {}
    for key, series in observations.items():
        series = series.loc[series.index <= cutoff].dropna().sort_index()
        if (
            not series.index.is_unique
            or not np.isfinite(series.to_numpy(dtype=float)).all()
        ):
            raise ValueError("Invalid macro observations")
        if series.empty or (cutoff - series.index[-1]).days > (
            14 if key in {"DGS10", "DGS3MO"} else 90
        ):
            raise MacroFeatureUnavailable(f"Missing or stale current macro series: {key}")
        cleaned[key] = series
    dates = list(pd.date_range("2011-06-30", cutoff, freq="ME"))
    if not dates or dates[-1] != cutoff:
        dates.append(cutoff)
    rows = []
    for date in dates:
        views = {key: s.loc[:date] for key, s in cleaned.items()}
        try:
            features = calculate_macro_features(views, date)
        except MacroFeatureUnavailable:
            if date == cutoff:
                raise
            # Historical current/revised feature holes stay holes, never filled.
            continue
        ip_growth = features["ip_growth"]
        inflation = features["inflation_yoy"]
        momentum = features["inflation_change"]
        unemployment = features["unemployment_change"]
        curve = features["yield_curve"]
        # Macro-only descriptive scores, not the validated market/macro strategy state.
        growth = (
            0.5 * np.tanh(ip_growth / 4)
            - 0.3 * np.tanh(unemployment / 0.3)
            + 0.2 * np.tanh(curve / 0.75)
        )
        pg = 1 / (1 + np.exp(-2 * growth))
        pi = 1 / (1 + np.exp(-2 * np.tanh(momentum)))
        scores = [pg * (1 - pi), pg * pi, (1 - pg) * pi, (1 - pg) * (1 - pi)]
        rows.append(
            {
                **features,
                "date": str(date.date()),
                "as_of": stamp.isoformat(),
                "ip_growth": ip_growth,
                "inflation_yoy": inflation,
                "inflation_change": momentum,
                "unemployment_change": unemployment,
                "yield_curve": curve,
                "probabilities": dict(zip(REGIMES, map(float, scores))),
                "observation_dates": {
                    key: str(value.index[-1].date()) for key, value in views.items()
                },
                "source_kind": "CURRENT_REVISED_FRED_NOT_HISTORICAL_VINTAGES",
            }
        )
    return rows


def features_from_directory(root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    observations = {}
    for key in SERIES:
        path = root / f"{key}.csv"
        expected = manifest["series"][key].get("sha256")
        if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Current macro file checksum mismatch")
        frame = pd.read_csv(path)
        values = pd.to_numeric(frame["value"].replace(".", np.nan), errors="raise")
        observations[key] = pd.Series(
            values.to_numpy(), index=pd.to_datetime(frame["date"])
        )
    return current_features(observations, manifest["retrieved_at"])


def refresh(root):
    """Read-only remote capture. No credentials are logged or embedded in reports."""
    from core_constants import settings

    if not settings.fred_api_key:
        raise ValueError("Configure FRED credentials privately")
    now = datetime.now(timezone.utc)
    root = Path(root) / now.strftime("%Y%m%dT%H%M%S%fZ")
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    manifest = {
        "kind": "CURRENT_REVISED_FRED_OBSERVATIONS_NOT_HISTORICAL_VINTAGES",
        "retrieved_at": now.isoformat(),
        "series": {},
    }
    for key in SERIES:
        params = {
            "series_id": key,
            "api_key": settings.fred_api_key,
            "file_type": "json",
            "observation_start": "2010-01-01",
            "observation_end": str(now.date()),
        }
        try:
            with urlopen(
                "https://api.stlouisfed.org/fred/series/observations?"
                + urlencode(params),
                timeout=12,
            ) as response:
                data = json.load(response)
            frame = pd.DataFrame(data["observations"])[["date", "value"]]
        except Exception as exc:
            raise RuntimeError(
                f"Current macro capture failed ({type(exc).__name__}); no partial snapshot is ready"
            ) from None
        path = root / f"{key}.csv"
        private_write(path, frame.to_csv(index=False))
        manifest["series"][key] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "rows": len(frame),
        }
    private_write(root / "manifest.json", json.dumps(manifest, indent=2))
    try:
        rows = features_from_directory(root)
    except MacroFeatureUnavailable as exc:
        # This revised informational overlay is independent of the release-aware
        # strategy inputs. Preserve the capture and disclose the gap; never fill
        # CPI endpoints or substitute an older overlay as current information.
        rows = []
        manifest["feature_status"] = "UNAVAILABLE"
        manifest["feature_reason"] = str(exc)
    else:
        manifest["feature_status"] = "AVAILABLE"
    private_write(root / "manifest.json", json.dumps(manifest, indent=2))
    private_write(root / "features.json", json.dumps(rows, allow_nan=False))
    return {
        "status": "CAPTURED_INFORMATIONAL_MACRO_ONLY"
        if rows else "INFORMATIONAL_MACRO_UNAVAILABLE",
        "features": str(root / "features.json"),
        "retrieved_at": now.isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("var/investor-macro-snapshots")
    )
    args = parser.parse_args()
    print(json.dumps(refresh(args.output), indent=2))


if __name__ == "__main__":
    main()
