"""Versioned portfolio identities shared by UI, simulations, PDF and ledger.

Identity binds allocation and assumptions, never an unverified promise of return.
"""

from pathlib import Path
import json
import numpy as np
import pandas as pd
from portfolio_objectives import POLICY_VERSION
from strategy_integrity import fingerprint, file_hash

COST_MODEL = {
    "rate": 0.0015,
    "basis": "actual_risky_asset_dollars_traded_self_financing",
    "cash_yield": 0.0,
    "taxes": "excluded_unverified",
    "fill": "next_close_after_registration",
}


def normalized_weights(weights):
    result = {s: float(w) for s, w in weights.items() if w != 0}
    if not result or any(
        not isinstance(s, str) or not np.isfinite(w) or w < 0 for s, w in result.items()
    ):
        raise ValueError("Invalid portfolio weights")
    risky = sum(w for s, w in result.items() if s != "USD_CASH")
    result["USD_CASH"] = float(result.get("USD_CASH", 1 - risky))
    if result["USD_CASH"] < -1e-9 or abs(sum(result.values()) - 1) > 1e-8:
        raise ValueError("Portfolio capital does not reconcile")
    return dict(sorted(result.items()))


def make_contract(
    key, weights, session, run_id, *, basis, performance, policy=POLICY_VERSION
):
    pd.Timestamp(session)
    record = {
        "schema_version": 1,
        "portfolio_key": key,
        "policy_version": policy,
        "valuation_session": session,
        "model_run_id": run_id,
        "weights": normalized_weights(weights),
        "cost_model": COST_MODEL,
        "allocation_basis": basis,
        "performance_basis": performance,
        "executable": False,
        "release_approved": False,
    }
    record["contract_id"] = fingerprint(record)
    return record


def validate_contract(record):
    body = {k: v for k, v in record.items() if k != "contract_id"}
    if record.get("schema_version") != 1 or fingerprint(body) != record.get(
        "contract_id"
    ):
        raise ValueError("Portfolio contract checksum mismatch")
    if (
        normalized_weights(record["weights"]) != record["weights"]
        or record["executable"] is not False
        or record["release_approved"] is not False
    ):
        raise ValueError("Invalid non-executable contract")
    return True


def build_contracts(payload):
    contracts = {}
    report = payload["training"]
    for name, rows in payload["allocation_lab"]["results"].items():
        r = rows["latest_model"]
        weights = {**r["weights"], "USD_CASH": r["cash"]}
        contracts[name] = make_contract(
            name,
            weights,
            report["market_session"],
            report["run_id"],
            basis="CURRENT_MACRO_SCENARIO_ALLOCATION",
            performance="FROZEN_MODEL_EVALUATION_NOT_CURRENT_WEIGHTS_BACKTEST",
        )
    if payload.get("growth_resilience"):
        g = payload["growth_resilience"]
        contracts["Growth_Resilience_reference"] = make_contract(
            "Growth_Resilience_reference",
            g["weights"],
            g["end"],
            g["version"],
            basis="DECLARED_STRATEGIC_REFERENCE",
            performance="RETROSPECTIVE_COMMON_OBSERVED_HISTORY_NOT_PROSPECTIVE",
        )
    return contracts


def verify_contracts(payload):
    expected = build_contracts(payload)
    if payload.get("portfolio_contracts") != expected:
        raise ValueError("Displayed portfolio contracts disagree with sources")
    for c in expected.values():
        validate_contract(c)
    return True


def extended_prices(capture_path, extension_root):
    capture_path = Path(capture_path)
    m = json.loads(capture_path.read_text())
    root = capture_path.parent
    for name, digest in m["files"].items():
        p = root / name
        if Path(name).name != name or p.is_symlink() or file_hash(p) != digest:
            raise ValueError("Market capture integrity failure")
    prices = pd.read_csv(root / "prices.csv", index_col=0, parse_dates=True)
    prices.attrs["base_currency"] = m.get("base_currency", "USD")
    extension_root = Path(extension_root)
    em = json.loads((extension_root / "capture.json").read_text())
    p = extension_root / "XLV-adjusted.csv"
    if (
        p.is_symlink()
        or em["market_session"] != m["price_session"]
        or file_hash(p) != em["prices_sha256"]
    ):
        raise ValueError("Benchmark extension integrity/date mismatch")
    extra = pd.read_csv(p, index_col=0, parse_dates=True)
    if extra.index.has_duplicates or not extra.index.is_monotonic_increasing:
        raise ValueError("Invalid extension sessions")
    prices["XLV"] = extra["XLV"].reindex(prices.index)
    if pd.isna(prices.iloc[-1]["XLV"]):
        raise ValueError("Current benchmark price unavailable")
    return prices
