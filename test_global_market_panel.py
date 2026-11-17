import pandas as pd
import pytest

from global_asset_registry import load_registry
from global_market_panel import base_currency_panel


def bars(session, stamp, value, column="close"):
    return pd.DataFrame(dict(session=session, available_at=stamp, **{column: value}))


def test_observed_london_pence_prices_and_fx_are_causal():
    registry = load_registry()
    valuations = pd.DatetimeIndex(["2026-11-12T21:00:00Z", "2026-11-13T21:00:00Z"])
    observed = bars(
        ["2026-11-12", "2026-11-13"],
        ["2026-11-12T16:30:00Z", "2026-11-13T16:30:00Z"],
        [3000.0, 3100.0],
    )
    fx = bars(
        ["2026-11-12", "2026-11-13"],
        ["2026-11-12T20:00:00Z", "2026-11-13T22:00:00Z"],
        [1.25, 9.99],
        "rate",
    )
    result = base_currency_panel(
        registry, {"SHEL.L": observed}, valuations, fx={"GBP": fx}
    )
    assert list(result["SHEL.L"]) == [37.5, 38.75]  # future FX quote is excluded
    assert (
        result.attrs["observations"]["SHEL.L"][-1]["fx_available_at"]
        == "2026-11-12T20:00:00+00:00"
    )


def test_closed_local_holiday_can_reuse_a_real_mark_but_missing_open_session_cannot():
    registry = load_registry()
    observed = bars(["2026-11-02"], ["2026-11-02T06:30:00Z"], [2000.0])
    fx = bars(["2026-11-02"], ["2026-11-02T20:00:00Z"], [0.007], "rate")
    result = base_currency_panel(
        registry,
        {"7203.T": observed},
        pd.DatetimeIndex(["2026-11-03T21:00:00Z"]),
        fx={"JPY": fx},
    )
    assert result.iloc[0, 0] == 14.0
    assert result.attrs["observations"]["7203.T"][0]["unchanged_closed_market_mark"]
    with pytest.raises(ValueError, match="Missing actual"):
        base_currency_panel(
            registry,
            {"7203.T": observed},
            pd.DatetimeIndex(["2026-11-04T21:00:00Z"]),
            fx={"JPY": fx},
        )


def test_missing_fx_and_false_early_availability_are_rejected():
    registry = load_registry()
    observed = bars(["2026-11-13"], ["2026-11-13T12:00:00Z"], [3000.0])
    valuation = pd.DatetimeIndex(["2026-11-13T21:00:00Z"])
    with pytest.raises(ValueError, match="FX required"):
        base_currency_panel(registry, {"SHEL.L": observed}, valuation)
    fx = bars(["2026-11-13"], ["2026-11-13T20:00:00Z"], [1.25], "rate")
    with pytest.raises(ValueError, match="precedes"):
        base_currency_panel(registry, {"SHEL.L": observed}, valuation, fx={"GBP": fx})


@pytest.mark.parametrize("session", ["2026-11-17", "2020-01-02"])
def test_new_availability_does_not_legitimize_future_or_obsolete_fx(session):
    observed = bars(["2026-11-16"], ["2026-11-16T16:35:00Z"], [3000.0])
    fx = bars([session], ["2026-11-16T18:00:00Z"], [1.25], "rate")
    with pytest.raises(ValueError, match="FX"):
        base_currency_panel(
            load_registry(),
            {"SHEL.L": observed},
            pd.DatetimeIndex(["2026-11-16T21:00:00Z"]),
            fx={"GBP": fx},
        )


def test_global_provider_manifest_archives_verified_inputs_and_rejects_tampering(
    tmp_path,
):
    import json
    from global_asset_registry import AssetRegistry
    from global_market_panel import capture_manifest
    from strategy_integrity import file_hash

    data = load_registry().payload()
    data["schema_version"] = 1
    data["instruments"] = [r for r in data["instruments"] if r["symbol"] == "MSFT"]
    registry = AssetRegistry(data)
    quote = tmp_path / "quote.csv"
    bars(["2026-11-13"], ["2026-11-13T21:00:00Z"], [100.0]).to_csv(quote, index=False)
    valuations = tmp_path / "valuations.csv"
    pd.DataFrame({"timestamp": ["2026-11-13T21:05:00Z"]}).to_csv(
        valuations, index=False
    )
    doc = dict(
        schema_version=1,
        base_currency="USD",
        registry_id=registry.identity,
        valuations={"path": str(valuations), "sha256": file_hash(valuations)},
        quotes={"MSFT": {"path": str(quote), "sha256": file_hash(quote)}},
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(doc))
    destination = tmp_path / "capture"
    destination.mkdir()
    panel, files = capture_manifest(manifest, destination, registry)
    assert panel.iloc[0, 0] == 100 and len(files) == 3
    assert (
        json.loads((destination / "global-valuation-provenance.json").read_text())[
            "registry_id"
        ]
        == registry.identity
    )
    quote.write_text("tampered input")
    second = tmp_path / "second"
    second.mkdir()
    with pytest.raises(ValueError, match="hash mismatch"):
        capture_manifest(manifest, second, registry)


@pytest.mark.parametrize(
    "kind", ["naive", "empty", "fx_age", "negative", "duplicate", "unsupported"]
)
def test_valuation_contract_rejects_invalid_inputs(kind):
    registry = load_registry()
    quote = bars(["2026-11-13"], ["2026-11-13T21:00:00Z"], [100.0])
    dates = pd.DatetimeIndex(["2026-11-13T21:05:00Z"])
    kwargs = {}
    if kind == "naive":
        dates = dates.tz_localize(None)
    elif kind == "empty":
        dates = pd.DatetimeIndex([], tz="UTC")
    elif kind == "fx_age":
        kwargs["max_fx_age_hours"] = 1000
    elif kind == "negative":
        quote["close"] = -1.0
    elif kind == "duplicate":
        quote = pd.concat([quote, quote])
    else:
        from dataclasses import replace

        registry.instruments["MSFT"] = replace(
            registry.instruments["MSFT"], pricing_model="UNSUPPORTED"
        )
    with pytest.raises(ValueError):
        base_currency_panel(registry, {"MSFT": quote}, dates, **kwargs)
