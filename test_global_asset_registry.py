from copy import deepcopy
import json

import numpy as np
import pandas as pd
import pytest

from global_asset_registry import AssetRegistry, load_registry, resolve_policy, expand_anchor
from productallocation import base_currency_prices


def document():
    return load_registry().payload() | dict(schema_version=1, base_currency="USD")


def test_open_registry_has_no_fixed_count_or_etf_only_boundary():
    data = document()
    prototype = next(r for r in data["instruments"] if r["symbol"] == "MSFT")
    for i in range(80):
        item = deepcopy(prototype)
        item.update(symbol=f"SYNTHETIC_{i}", provider_symbol=f"SYNTHETIC_{i}", name=f"Synthetic test stock {i}", sources=["Synthetic fixture, not market data"])
        data["instruments"].append(item)
    registry = AssetRegistry(data)
    assert len(registry.symbols()) > 100
    assert registry.instruments["TM"].asset_type == "adr"
    assert registry.instruments["7203.T"].listing_currency == "JPY"
    assert registry.instruments["SHEL.L"].price_multiplier == .01
    assert "ALLW" not in registry.symbols()
    assert "MSFT" not in registry.symbols("paper")


@pytest.mark.parametrize("change", ["duplicate", "cap", "benchmark", "bond_clean_price", "future_spot_price", "crypto_as_equity"])
def test_registry_rejects_identity_and_accounting_ambiguities(change):
    data = document()
    if change == "duplicate":
        data["instruments"].append(deepcopy(data["instruments"][0]))
    elif change == "cap":
        data["maximum_universe_size"] = 26
    elif change == "benchmark":
        next(i for i in data["instruments"] if i["symbol"] == "ALLW")["research_enabled"] = True
    elif change == "bond_clean_price":
        data["instruments"][0].update(asset_type="bond", bucket="government", pricing_model="adjusted_close")
    elif change == "future_spot_price":
        data["instruments"][0].update(asset_type="future", bucket="alternative", pricing_model="adjusted_close")
    else:
        data["instruments"][0].update(asset_type="crypto", bucket="equity")
    with pytest.raises(ValueError):
        AssetRegistry(data)


def test_metadata_resolves_sleeves_and_preserves_frozen_contracts():
    raw = json.load(open("research/four_macro_strategies.json"))
    updated = resolve_policy(raw)
    assert {"MSFT", "TM", "ASML", "SONY"} <= set(updated["sleeves"]["equities"])
    assert np.isclose(sum(updated["sleeves"]["equities"].values()), 1)
    assert updated["maximum_asset_weight"] == raw["maximum_asset_weight"]
    assert raw["sleeves"]["equities"] != updated["sleeves"]["equities"]
    frozen = {**raw, "frozen_universe": list(raw["sleeves"]["equities"])}
    assert resolve_policy(frozen) == frozen


def test_reference_expansion_preserves_class_capital_and_cash():
    weights = expand_anchor(dict(SPY=.60, IEF=.30, USD_CASH=.10))
    assert weights["TM"] > 0
    registry = load_registry()
    assert np.isclose(sum(w for s,w in weights.items() if s != "USD_CASH" and registry.instruments[s].bucket == "equity"), .60)
    assert weights["USD_CASH"] == .10
    assert np.isclose(sum(weights.values()), 1)


def test_multi_currency_fx_and_quote_units_are_applied_once():
    dates = pd.date_range("2026-01-01", periods=3)
    raw = pd.DataFrame({"7203.T": [2000., 2100., 2200.], "SHEL.L": [3000., 3100., 3200.], "MSFT": [400., 405., 410.]}, index=dates)
    rates = {"JPY": pd.Series(.007, index=dates), "GBP": pd.Series(1.25, index=dates)}
    converted = base_currency_prices(raw, "USD", rates)
    assert np.allclose(converted["7203.T"], raw["7203.T"] * .007)
    assert np.allclose(converted["SHEL.L"], raw["SHEL.L"] * .01 * 1.25)
    assert np.array_equal(converted.MSFT, raw.MSFT)
    with pytest.raises(ValueError):
        base_currency_prices(raw, "USD", {"JPY": rates["JPY"]})
    with pytest.raises(ValueError):
        base_currency_prices(raw, "USD", {**rates, "USD": pd.Series(2., index=dates)})


def test_paper_factory_accepts_qualified_members_beyond_seed_count(tmp_path):
    import os
    import subprocess
    import sys
    data = document()
    next(i for i in data['instruments'] if i['symbol'] == 'MSFT')['paper_qualified'] = True
    path = tmp_path / 'registry.json'
    path.write_text(json.dumps(data))
    result = subprocess.run([sys.executable, '-c',
        'from assetuniverse import AssetUniverse; from productiondecisionexecution import ProductionDecisionExecution; '
        'u=AssetUniverse.production(); assert u.size==15; assert "MSFT" in ProductionDecisionExecution.production_tickers()'],
        env={**os.environ, 'REGIME_UNIVERSE_CONFIG': str(path)}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
