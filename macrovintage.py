"""Historical FRED vintage selection for research; never substitutes revised data.

FRED realtime_start is date-only. Releases become usable at midnight New York
time on the following day, conservatively avoiding assumptions about release
time. This is research input infrastructure, not a replacement paper adapter.
"""

from __future__ import annotations

from datetime import timedelta
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd


class MacroVintageData:
    def __init__(self, releases: pd.DataFrame) -> None:
        required = {"date", "realtime_start", "value"}
        if not required.issubset(releases.columns) or releases.empty:
            raise ValueError("Expected nonempty FRED all-releases data: date, realtime_start, value")
        frame = releases[list(sorted(required))].copy()
        for column in ("date", "realtime_start"):
            frame[column] = pd.to_datetime(frame[column], errors="raise")
            if frame[column].dt.tz is not None or not frame[column].equals(frame[column].dt.normalize()):
                raise ValueError("FRED dates must be naive calendar dates")
        frame["value"] = pd.to_numeric(frame["value"].replace(".", np.nan), errors="raise")
        # Missing releases are represented as NaN, never interpolated.
        if np.isinf(frame["value"]).any():
            raise ValueError("Infinite macro observations are invalid")
        if frame.duplicated(["date", "realtime_start"]).any():
            raise ValueError("Duplicate vintage keys are ambiguous")
        if (frame["date"] > frame["realtime_start"]).any():
            raise ValueError("Observation date cannot follow its vintage release date")
        available_dates = [date.date() + timedelta(days=1) for date in frame["realtime_start"]]
        frame["available_at"] = pd.DatetimeIndex(available_dates).tz_localize("America/New_York").tz_convert("UTC")
        self.releases = frame.sort_values(["date", "realtime_start"]).reset_index(drop=True)

    @classmethod
    def from_csv(cls, path: Path, *, expected_sha256: str) -> MacroVintageData:
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
            raise ValueError("Vintage dataset checksum mismatch")
        return cls(pd.read_csv(path))

    @classmethod
    def from_fred(cls, fred_client, series_id: str) -> MacroVintageData:
        return cls(fred_client.get_series_all_releases(series_id))

    def as_of(self, decision_time) -> pd.Series:
        timestamp = pd.Timestamp(decision_time)
        if timestamp.tzinfo is None:
            raise ValueError("Research decision time must be timezone-aware")
        eligible = self.releases[self.releases["available_at"] <= timestamp.tz_convert("UTC")]
        latest = eligible.drop_duplicates("date", keep="last").set_index("date")["value"]
        return latest.sort_index().copy()

    def freeze(self, destination: Path) -> dict:
        if destination.exists():
            raise ValueError("Refuse to overwrite a frozen vintage dataset")
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = self.releases[["date", "realtime_start", "value"]].to_csv(index=False, date_format="%Y-%m-%d")
        with destination.open("x") as handle:
            handle.write(content)
        return {"path": str(destination), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "availability_policy": "NEXT_NEW_YORK_MIDNIGHT", "rows": len(self.releases)}
