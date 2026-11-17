"""Versioned, extensible instrument identity and research/execution eligibility.

Universe membership is configuration, never a fixed instrument count. An enabled
research instrument still needs qualified prices, FX, calendars and mandate access.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import json
import math
import os
import re

DEFAULT_REGISTRY = Path(__file__).resolve().parent / "research/global_asset_registry.json"
ASSET_TYPES = {"etf", "equity", "adr", "bond", "fund", "commodity", "future", "option", "crypto", "fx", "cash", "reit"}
BUCKETS = {"equity", "government", "credit", "real_assets", "alternative", "composite", "cash"}


@dataclass(frozen=True)
class Instrument:
    symbol: str
    provider_symbol: str
    name: str
    asset_type: str
    bucket: str
    asset_class: str
    sector: str
    country: str
    region: str
    listing_currency: str
    quote_unit: str
    price_multiplier: float
    venue: str
    calendar: str
    benchmark: str
    research_enabled: bool
    product_enabled: bool
    paper_qualified: bool
    benchmark_only: bool
    satellite: bool
    pricing_model: str
    sources: tuple[str, ...]

    def asset_definition(self):
        return dict(ticker=self.symbol, name=self.name, asset_class=self.asset_class,
                    sector=self.sector, country=self.country, currency=self.listing_currency,
                    benchmark=self.benchmark, active=True)


class AssetRegistry:
    def __init__(self, document):
        if (document.get("schema_version") != 1 or document.get("policy") != "OPEN_GLOBAL_ELIGIBILITY_V1"
                or document.get("maximum_universe_size") is not None):
            raise ValueError("Open, versioned global registry required")
        self.instruments = {}
        for raw in document["instruments"]:
            row = dict(raw)
            row["sources"] = tuple(row["sources"])
            item = Instrument(**row)
            if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@=^/+\-]{0,63}", item.symbol)
                    or item.symbol in self.instruments or not item.provider_symbol.strip()
                    or item.asset_type not in ASSET_TYPES or item.bucket not in BUCKETS
                    or not re.fullmatch(r"[A-Z]{3}", item.listing_currency)
                    or not item.venue.strip() or not item.calendar.strip() or not item.name.strip()
                    or isinstance(item.price_multiplier, bool) or not math.isfinite(item.price_multiplier)
                    or item.price_multiplier <= 0 or not item.sources
                    or any(type(getattr(item, k)) is not bool for k in
                           ("research_enabled", "product_enabled", "paper_qualified", "benchmark_only", "satellite"))):
                raise ValueError("Invalid or duplicate global instrument metadata")
            if item.benchmark_only and (item.research_enabled or item.paper_qualified):
                raise ValueError("A benchmark-only listing cannot become an allocation component")
            required_bucket = {"equity": {"equity"}, "adr": {"equity"}, "reit": {"equity"},
                               "bond": {"government", "credit"}, "commodity": {"real_assets"},
                               "crypto": {"alternative"}, "cash": {"cash"}}
            if item.asset_type in required_bucket and item.bucket not in required_bucket[item.asset_type]:
                raise ValueError("Asset type and economic risk bucket conflict")
            if item.asset_type == "bond" and item.pricing_model != "total_return":
                raise ValueError("Direct bonds require coupon/accrual-aware total returns")
            if item.asset_type in {"future", "option", "fx"} and item.pricing_model in {"adjusted_close", "net_asset_value"}:
                raise ValueError("Derivatives and FX require their own return-accounting model")
            if item.research_enabled and item.pricing_model not in {"adjusted_close", "total_return", "net_asset_value"}:
                raise ValueError("Research activation requires a supported return-accounting adapter")
            if item.paper_qualified and not item.research_enabled:
                raise ValueError("Paper qualification requires research eligibility")
            self.instruments[item.symbol] = item
        if not self.instruments:
            raise ValueError("Nonempty registry required")
        self.identity = hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def symbols(self, purpose="research"):
        field = {"research": "research_enabled", "product": "product_enabled", "paper": "paper_qualified"}.get(purpose)
        if field is None:
            raise ValueError("Unknown universe purpose")
        return tuple(s for s, item in self.instruments.items() if getattr(item, field))

    def payload(self):
        return dict(policy="OPEN_GLOBAL_ELIGIBILITY_V1", registry_id=self.identity,
                    maximum_universe_size=None, instruments=[asdict(i) for i in self.instruments.values()])


def load_registry(path=None):
    path = Path(path or os.environ.get("REGIME_UNIVERSE_CONFIG", DEFAULT_REGISTRY))
    if path.is_symlink():
        raise ValueError("Registry must be a regular reviewed file")
    return AssetRegistry(json.loads(path.read_text()))


def research_symbols():
    return load_registry().symbols("research")


def common_sessions(symbols, start, end, *, completed_at=None):
    """Joint actual session dates; never manufacture a missing exchange bar."""
    import pandas as pd
    import pandas_market_calendars as mcal
    registry = load_registry()
    calendars = {registry.instruments[s].calendar for s in symbols}
    common = None
    for name in sorted(calendars):
        rows = mcal.get_calendar(name).schedule(start, end)
        if completed_at is not None:
            stamp = pd.Timestamp(completed_at)
            if stamp.tzinfo is None:
                raise ValueError("Aware global decision timestamp required")
            rows = rows.loc[rows.market_close <= stamp]
        common = rows.index if common is None else common.intersection(rows.index)
    if common is None or common.empty:
        raise ValueError("No common completed exchange sessions")
    return common


def periods_per_year(symbols, as_of):
    import pandas as pd
    registry = load_registry()
    if all(registry.instruments[s].calendar in {"NYSE", "NASDAQ"} for s in symbols):
        return 252  # established US-session convention, not an instrument restriction
    end = pd.Timestamp(as_of)
    return len(common_sessions(symbols, (end - pd.Timedelta(days=365)).date(), end.date()))


def expand_anchor(anchor):
    """Keep the declared class/cash budgets, open their constituents by metadata."""
    registry = load_registry()
    updated = {s: w for s, w in anchor.items() if s.endswith("CASH")}
    for bucket in sorted(BUCKETS - {"cash", "composite"}):
        original = {s: w for s, w in anchor.items() if s in registry.instruments and registry.instruments[s].bucket == bucket}
        budget = sum(original.values())
        if budget <= 0:
            continue
        pool = {s: w for s, w in original.items()}
        for symbol in registry.symbols():
            if registry.instruments[symbol].bucket == bucket:
                pool.setdefault(symbol, .025)
        total = sum(pool.values())
        updated.update({s: budget * w / total for s, w in pool.items()})
    if not math.isclose(sum(updated.values()), sum(anchor.values()), abs_tol=1e-10):
        raise ValueError("Reference anchor contains an unregistered instrument")
    return updated


def resolve_policy(config):
    """Expand declared economic sleeves by metadata; retain strategy risk limits.

    Existing ticker weights are priors. New eligible instruments receive a small
    within-sleeve prior, normalized with existing members; they are not guaranteed
    an allocation. Explicit frozen_universe contracts never expand retroactively.
    """
    from copy import deepcopy
    result = deepcopy(config)
    if result.get("frozen_universe") is not None:
        return result
    registry = load_registry()
    items = [registry.instruments[s] for s in registry.symbols()]
    equities = [i.symbol for i in items if i.bucket == "equity"]
    nominal = [i.symbol for i in items if i.bucket == "government" and "Inflation" not in i.sector]
    credit = [i.symbol for i in items if i.bucket == "credit"]
    inflation = [i.symbol for i in items if i.bucket == "real_assets" or "Inflation" in i.sector]
    mappings = {"equities": equities, "government_bonds": nominal, "nominal_bonds": nominal,
                "inflation_sensitive": inflation, "credit": credit}
    def extend(weights, symbols):
        known = registry.instruments
        updated = {s: v for s, v in weights.items() if s in known and known[s].research_enabled}
        # Do not introduce reserves or unsupported instruments into risk sleeves.
        for symbol in symbols:
            item = known[symbol]
            if item.sector in {"Treasury Bills", "Short Duration Government"}:
                continue
            updated.setdefault(symbol, .025)
        total = sum(updated.values())
        return {s: v / total for s, v in updated.items()} if total > 0 else updated
    for regime in result.get("regimes", {}).values():
        for name, weights in regime.get("groups", {}).items():
            if name in mappings:
                regime["groups"][name] = extend(weights, mappings[name])
    for name, weights in result.get("sleeves", {}).items():
        if name in mappings:
            result["sleeves"][name] = extend(weights, mappings[name])
    if "risk_groups" in result:
        excluded = set(result.get("excluded_from_risk_budget", []))
        for name, values in result["risk_groups"].items():
            result["risk_groups"][name] = [s for s in values if s in registry.symbols()]
        assigned = {s for values in result["risk_groups"].values() for s in values}
        for name, values in result["risk_groups"].items():
            for symbol in mappings.get(name, []):
                if symbol not in assigned and symbol not in excluded:
                    values.append(symbol)
                    assigned.add(symbol)
        # Unsupported sleeves remain excluded explicitly, rather than misclassified.
        result["excluded_from_risk_budget"] = [s for s in registry.symbols() if s not in assigned]
    if "core_equity_risk_weights" in result:
        result["core_equity_risk_weights"] = extend(result["core_equity_risk_weights"], equities)
    result["universe_contract"] = dict(policy="OPEN_GLOBAL_ELIGIBILITY_V1", registry_id=registry.identity,
                                       symbols=list(registry.symbols()), maximum_universe_size=None)
    return result
