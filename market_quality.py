"""Immutable capture comparison; revisions are disclosed, never silently merged."""

from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from strategy_integrity import strict_json, file_hash
from strategy_training_data import validate_prices


def read_capture(path):
    path = Path(path)
    doc = strict_json(path)
    if doc.get("status") != "CAPTURED_FOR_SHADOW_TRAINING" or not {
        "prices.csv",
        "macro-manifest.json",
    } <= set(doc["files"]):
        raise ValueError("Complete captured market/macro lineage required")
    for name, digest in doc["files"].items():
        p = path.parent / name
        if Path(name).name != name or p.is_symlink() or file_hash(p) != digest:
            raise ValueError("Capture lineage/hash mismatch")
    prices = pd.read_csv(path.parent / "prices.csv", index_col=0, parse_dates=True)
    contract = doc.get("universe_contract")
    symbols = (
        [i["symbol"] for i in contract["instruments"] if i["research_enabled"]]
        if contract
        else list(prices)
    )
    return doc, validate_prices(
        prices, pd.Timestamp(doc["price_session"]), required_symbols=symbols
    )


def review(current, previous=None, secondary=None):
    doc, prices = read_capture(current)
    result = dict(
        capture_sha256=file_hash(current),
        market_session=doc["price_session"],
        integrity="PASS",
        independent_provider="NOT_SUPPLIED",
        revisions=None,
        financial_inputs="UNVERIFIED_CASH_COSTS_AND_LOOKTHROUGH",
        execution_enabled=False,
        release_approved=False,
    )
    if previous:
        old_doc, old = read_capture(previous)
        if old_doc["captured_at"] > doc["captured_at"]:
            raise ValueError("Comparison cannot use a future capture")
        dates, symbols = (
            old.index.intersection(prices.index),
            old.columns.intersection(prices.columns),
        )
        relative = (prices.loc[dates, symbols] / old.loc[dates, symbols] - 1).to_numpy()
        valid = np.isfinite(relative)
        result["revisions"] = dict(
            changed_cells=int(np.sum(valid & (np.abs(relative) > 1e-8))),
            max_absolute_relative_revision=float(np.max(np.abs(relative[valid])))
            if valid.any()
            else None,
            prior_sha256=file_hash(previous),
            action="DISCLOSED_NOT_MERGED_OR_RELABELED",
        )
    if secondary is not None:
        manifest = Path(secondary)
        other = strict_json(manifest)
        if (
            other["provider"].strip().lower() in {"yahoo", "yahoo finance", "yfinance"}
            or other["basis"] != "ADJUSTED_TOTAL_RETURN"
            or not other["source"]
            or not other["reviewer"]
            or other["rights_reviewed"] is not True
        ):
            raise ValueError(
                "Independent source, compatible basis and rights review required"
            )
        stamp = pd.Timestamp(other["captured_at"])
        if stamp.tzinfo is None or stamp > pd.Timestamp(datetime.now(timezone.utc)):
            raise ValueError("Valid independent capture clock required")
        name = other["file"]
        path = manifest.parent / name
        if (
            Path(name).name != name
            or path.is_symlink()
            or file_hash(path) != other["sha256"]
        ):
            raise ValueError("Independent source integrity failure")
        panel = pd.read_csv(path, index_col=0, parse_dates=True)
        panel = validate_prices(
            panel,
            pd.Timestamp(doc["price_session"]),
            required_symbols=list(prices.columns),
        )
        if list(panel.columns) != list(prices.columns):
            raise ValueError("Complete aligned independent universe required")
        a = prices.pct_change(fill_method=None).tail(252)
        b = panel.pct_change(fill_method=None).reindex(a.index)
        difference = (a - b).abs()
        mismatch = [
            s
            for s in prices
            if ((a[s].notna() != b[s].notna()) | (difference[s] > 0.002)).any()
        ]
        compared = np.isfinite(a.to_numpy()) & np.isfinite(b.to_numpy())
        result["independent_provider"] = (
            "DISCREPANCY_REVIEW_REQUIRED"
            if mismatch
            else "MATCHED_DAILY_RETURN_TOLERANCE"
        )
        result["independent_comparison"] = dict(
            provider=other["provider"],
            manifest_sha256=file_hash(manifest),
            tolerance_absolute_return=0.002,
            mismatches=mismatch,
            comparison_sessions=len(a),
            compared_return_cells=int(compared.sum()),
            maximum_absolute_return_difference=float(np.nanmax(difference.to_numpy()))
            if compared.any()
            else None,
            limitation="Locally reviewed independent file; vendor authenticity and licensing are not independently certified by this comparison.",
        )
    return result
