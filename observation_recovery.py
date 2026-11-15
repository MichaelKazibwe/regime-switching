"""Verify completed training before reusing it for a failed reporting stage."""

from pathlib import Path
from strategy_integrity import strict_json, file_hash
from strategy_report import load_training_report
from portfolio_contract import extended_prices


def reusable_bundle(job, session):
    checkpoint = Path(job) / "dashboard/training-checkpoint.json"
    path = (
        checkpoint
        if checkpoint.is_file()
        else Path(job) / "dashboard/latest-strategy-run.json"
    )
    if not path.is_file():
        return None
    bundle = strict_json(path)
    if checkpoint.is_file() and any(
        file_hash(p) != h for p, h in bundle["input_hashes"].items()
    ):
        raise ValueError("Training checkpoint inputs changed")
    report = load_training_report(bundle["training_report"])
    capture = strict_json(bundle["capture"])
    if (
        not report["current_numerical_source_match"]
        or report["market_session"] != session
        or capture["price_session"] != session
        or report["capture_sha256"] != file_hash(bundle["capture"])
    ):
        return None
    # Checks every captured input and the dated benchmark extension; no synthetic repair.
    extended_prices(bundle["capture"], bundle["benchmark_extension"])
    return bundle
