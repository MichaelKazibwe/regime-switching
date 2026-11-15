"""Fail-closed private cash, fund exposure and transaction-cost evidence gate."""

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from economic_design_assessment import load_cash_history
from strategy_integrity import strict_json, file_hash


def verify(root, symbols, dates, *, now=None):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    root = Path(root) if root else None
    flags = {
        "cash_history": False,
        "fund_exposure_metadata": False,
        "transaction_cost_evidence": False,
        "instrument_access": False,
    }
    reasons = []
    details = {}
    if root is None:
        return {
            "status": "BLOCKED_NO_VERIFIED_EVIDENCE",
            "checks": flags,
            "reasons": ["No protected evidence supplied"],
            "release_approved": False,
        }
    try:
        _, details["cash"] = load_cash_history(root / "cash-history.json", dates)
        flags["cash_history"] = True
    except (OSError, ValueError, TypeError, KeyError) as exc:
        reasons.append("cash_history: " + type(exc).__name__)
    for filename, kind in [
        ("exposures.json", "fund_exposure_metadata"),
        ("execution-costs.json", "transaction_cost_evidence"),
    ]:
        try:
            doc = strict_json(root / filename)
            if (root / filename).is_symlink():
                raise ValueError("Regular evidence manifest required")
            if (
                doc.get("schema_version") != 1
                or doc.get("verified") is not True
                or not isinstance(doc.get("reviewer"), str)
                or not doc["reviewer"].strip()
                or not doc.get("evidence")
            ):
                raise ValueError("Named source review required")
            stamp = pd.Timestamp(doc["as_of"])
            reviewed = pd.Timestamp(doc["reviewed_at"])
            if (
                stamp.tzinfo is None
                or reviewed.tzinfo is None
                or not stamp <= reviewed <= now
                or (now - stamp).days > 31
            ):
                raise ValueError("Fresh dated metadata required")
            for item in doc["evidence"]:
                if (
                    Path(item["file"]).name != item["file"]
                    or (root / item["file"]).is_symlink()
                    or file_hash(root / item["file"]) != item["sha256"]
                ):
                    raise ValueError("Evidence hash mismatch")
            if set(doc["instruments"]) != set(symbols):
                raise ValueError("Complete proposed-universe coverage required")
            for item in doc["instruments"].values():
                if kind == "fund_exposure_metadata":
                    duration = item["effective_duration"]
                    fx = item["unhedged_fx_fraction"]
                    covered = item["lookthrough_coverage"]
                    if (
                        any(
                            isinstance(v, bool) or not np.isfinite(v)
                            for v in [duration, fx, covered]
                        )
                        or not 0 <= duration <= 40
                        or not 0 <= fx <= 1
                        or not 0.99 <= covered <= 1
                    ):
                        raise ValueError("Invalid measured exposures")
                    if not item["holdings_source"] or not isinstance(
                        item["accessible"], bool
                    ):
                        raise ValueError("Access/source evidence required")
                else:
                    values = [
                        item[k]
                        for k in [
                            "commission",
                            "half_spread",
                            "impact",
                            "fx_cost",
                            "stress_cost_rate",
                        ]
                    ]
                    if any(
                        isinstance(v, bool) or not np.isfinite(v) or not 0 <= v <= 0.1
                        for v in values
                    ) or values[-1] < sum(values[:-1]):
                        raise ValueError("Invalid observed costs/stress allowance")
                    if not item["source"]:
                        raise ValueError("Observed cost source required")
            flags[kind] = True
            details[kind] = {
                "manifest_sha256": file_hash(root / filename),
                "as_of": stamp.isoformat(),
            }
            if kind == "fund_exposure_metadata":
                flags["instrument_access"] = all(
                    item["accessible"] for item in doc["instruments"].values()
                )
        except (OSError, ValueError, TypeError, KeyError) as exc:
            reasons.append(kind + ": " + type(exc).__name__)
    return {
        "status": "LOCAL_EVIDENCE_REVIEW_PASSED_NOT_PUBLIC_APPROVAL"
        if all(flags.values())
        else "BLOCKED_MISSING_OR_INVALID_EVIDENCE",
        "checks": flags,
        "reasons": reasons,
        "details": details,
        "release_approved": False,
    }


def portfolio_review(weights, config, evidence, evidence_root):
    """Measured exposure review stays unavailable until its source gate passes."""
    if not evidence["checks"]["fund_exposure_metadata"]:
        return {
            "status": "BLOCKED_UNVERIFIED_DURATION_FX_HOLDINGS",
            "duration": None,
            "unhedged_fx_fraction": None,
            "public_approval": False,
        }
    path = Path(evidence_root) / "exposures.json"
    if (
        file_hash(path)
        != evidence["details"]["fund_exposure_metadata"]["manifest_sha256"]
    ):
        raise ValueError("Exposure evidence changed after validation")
    items = strict_json(path)["instruments"]
    duration = sum(w * items[s]["effective_duration"] for s, w in weights.items())
    fx = sum(w * items[s]["unhedged_fx_fraction"] for s, w in weights.items())
    return {
        "status": "LOCAL_EXPOSURE_LIMIT_REVIEW_PASS"
        if duration <= config["portfolio_duration_ceiling"]
        and fx <= config["unhedged_fx_ceiling"]
        else "BLOCKED_AGGREGATE_EXPOSURES",
        "duration": duration,
        "unhedged_fx_fraction": fx,
        "measurement": "Weighted supplied fund exposures; not independent holdings authentication or a substitute for nonlinear derivative risk.",
        "public_approval": False,
    }
