"""Explain every macro rejection without weakening or filling its input contract."""

from collections import Counter

import pandas as pd

from training_macro import TrainingMacro

BLS = {
    "UNRATE": "https://www.bls.gov/cps/methods/2025-federal-government-shutdown-impact-cps.htm",
    "CPIAUCSL": "https://www.bls.gov/cpi/additional-resources/2025-federal-government-shutdown-impact-cpi.htm",
}
OFFSETS = {"UNRATE": [0, 1, 2, 3, 4, 5], "CPIAUCSL": [0, 12, 3, 15], "INDPRO": [0, 6]}


def release_delay_evidence(series, observed_period, decision):
    """Post-hoc primary-calendar corroboration, never a historical trading input."""
    windows = {
        "UNRATE": [
            ("2025-08", "2025-10-01", "2025-11-20"),
            ("2025-09", "2025-11-21", "2025-12-16"),
        ],
        "CPIAUCSL": [("2025-09", "2025-10-25", "2025-12-18")],
        "INDPRO": [
            ("2025-08", "2025-10-01", "2025-12-03"),
            ("2025-09", "2025-12-04", "2025-12-23"),
        ],
    }
    if any(
        observed_period == period and start <= decision <= end
        for period, start, end in windows.get(series, [])
    ):
        return (
            "https://www.federalreserve.gov/feeds/G17.html"
            if series == "INDPRO"
            else "https://www.bls.gov/bls/2025-lapse-revised-release-dates.htm"
        )
    return None


def diagnose(manifest, features, start, end):
    reader = TrainingMacro(manifest)
    rows = []
    counts = Counter()
    for feature in features:
        if not start <= feature["date"] < end or feature.get("macro_valid", True):
            continue
        stamp = pd.Timestamp(feature["as_of"])
        issues = []
        for key, data in reader.data.items():
            series = data.as_of(stamp).dropna()
            maximum = 14 if key.startswith("DGS") else 90
            if series.empty:
                issues.append(
                    {
                        "series": key,
                        "type": "NO_AVAILABLE_HISTORY",
                        "classification": "REQUIRES_PROVIDER_RECONCILIATION",
                    }
                )
                continue
            age = (
                stamp.tz_convert("America/New_York").date() - series.index[-1].date()
            ).days
            if age > maximum:
                source = release_delay_evidence(
                    key, str(series.index[-1].to_period("M")), feature["date"]
                )
                issues.append(
                    {
                        "series": key,
                        "type": "STALE",
                        "age_days": age,
                        "last_observed_period": str(series.index[-1].to_period("M")),
                        "classification": "OFFICIAL_RELEASE_DELAY_CORROBORATED"
                        if source
                        else "RELEASE_DELAY_OR_CAPTURE_GAP_REQUIRES_RECONCILIATION",
                        "source": source,
                    }
                )
            if key in OFFSETS:
                periods = series.index.to_period("M")
                last = periods[-1]
                for offset in OFFSETS[key]:
                    missing = last - offset
                    if missing not in periods:
                        known = str(missing) == "2025-10" and key in BLS
                        issues.append(
                            {
                                "series": key,
                                "type": "MISSING_REQUIRED_PERIOD",
                                "period": str(missing),
                                "classification": "OFFICIAL_NONCOLLECTION_CORROBORATED"
                                if known
                                else "REQUIRES_PROVIDER_RECONCILIATION",
                                "source": BLS.get(key) if known else None,
                            }
                        )
        for issue in issues:
            counts[issue["classification"]] += 1
        rows.append(
            {
                "decision_session": feature["date"],
                "first_error": feature.get("macro_unavailable_reason"),
                "issues": issues,
            }
        )
    return {
        "rejected_sessions": len(rows),
        "issue_classifications": dict(counts),
        "sessions": rows,
        "contract": "Unchanged exact-calendar and 90-day/14-day freshness requirements; no missing values filled.",
        "limitations": "Retrospective calendar corroboration uses exact observation-period/date windows plus the existing next-New-York-midnight availability policy. Other periods are not attributed automatically. Multiple issues can occur per session; this source catalog is never a historical trading input.",
    }
