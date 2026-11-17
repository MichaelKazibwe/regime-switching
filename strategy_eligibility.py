"""Explicit strategy membership, separate from the open global investment menu."""

from pathlib import Path
from global_asset_registry import load_registry
from strategy_integrity import strict_json


def eligible_prices(prices, contract=Path("research/dynamic_eligibility.json")):
    policy = strict_json(contract)
    if (
        policy.get("schema_version") != 1
        or policy.get("policy") != "DYNAMIC_RESEARCH_ELIGIBILITY_V1"
    ):
        raise ValueError("Versioned strategy eligibility contract required")
    excluded = policy["exclude"]
    if any(
        not isinstance(reason, str) or not reason.strip()
        for reason in excluded.values()
    ):
        raise ValueError("Each strategy exclusion requires a reason")
    registry = load_registry()
    symbols = [
        s
        for s in prices
        if s in registry.instruments
        and registry.instruments[s].research_enabled
        and not registry.instruments[s].benchmark_only
        and s not in excluded
    ]
    if not symbols:
        raise ValueError("No qualified strategy research observations")
    result = prices[symbols].copy()
    result.attrs["strategy_exclusions"] = excluded
    return result
