"""Release-aware features using exact required periods; no missing-month fill.

Unemployment needs six consecutive months. CPI and production need specific
calendar-period endpoints, rather than an unrelated 16-month completeness
requirement. Genuine stale/missing required inputs still quarantine decisions.
"""

import numpy as np
import pandas as pd

from diversifiedregimepolicy import AllocationError
from smartregimeportfolio import PointInTimeMacro
from macro_feature_contract import calculate_macro_features


class TrainingMacro(PointInTimeMacro):
    def features(self, decision_time):
        stamp = pd.Timestamp(decision_time)
        if stamp.tzinfo is None:
            raise AllocationError("Aware macro decision timestamp required")
        stamp = stamp.tz_convert("UTC")
        views = {}
        for key, data in self.data.items():
            signature = int(np.searchsorted(self.times[key], stamp.value, side="right"))
            if not signature:
                raise AllocationError(f"Macro history unavailable: {key}")
            if key not in self.cache or self.cache[key][0] != signature:
                self.cache[key] = (signature, data.as_of(stamp).dropna())
            s = self.cache[key][1]
            maximum = 14 if key in {"DGS10", "DGS3MO"} else 90
            if (
                s.empty
                or (
                    stamp.tz_convert("America/New_York").date() - s.index[-1].date()
                ).days
                > maximum
            ):
                raise AllocationError(f"Macro series missing or stale: {key}")
            views[key] = s
        try:
            result = calculate_macro_features(views, stamp)
        except ValueError as exc:
            raise AllocationError(str(exc)) from exc
        return {**result, "as_of": stamp.isoformat()}
