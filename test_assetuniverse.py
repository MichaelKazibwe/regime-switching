"""
======================================================================
ASSET UNIVERSE — TEST SUITE
======================================================================

Institutional Asset Universe Regression and Functional Certification.

This test module certifies:

    1. Asset immutability
    2. Generic universe behaviour
    3. Ticker validation
    4. Lookup and membership
    5. Asset removal
    6. Filtering
    7. Active/inactive state
    8. Serialization
    9. DataFrame export
    10. Canonical production universe
    11. Production asset classes
    12. Production definitions
    13. Production serialization
    14. Production metadata
    15. Production no-cash rule
    16. Public API contract
    17. Deterministic production factory

IMPORTANT
---------
This file is a TEST FILE.

It must be named:

    test_assetuniverse.py

It must NOT be copied into:

    assetuniverse.py

The production implementation lives exclusively in:

    assetuniverse.py

======================================================================
"""

from __future__ import annotations

import pytest

from assetuniverse import (
    Asset,
    AssetUniverse,
    PRODUCTION_ASSETS,
    PRODUCTION_ASSET_COUNT,
    PRODUCTION_ASSET_DEFINITIONS,
    PRODUCTION_ASSET_TUPLE,
)


def test_diversified_research_universe_has_complete_metadata_and_preserves_production():
    from assetuniverse import DIVERSIFIED_ASSETS, DIVERSIFIED_ASSET_COUNT
    from core_constants import DEFAULT_ASSETS, DIVERSIFIED_RESEARCH_ASSETS

    expanded = AssetUniverse.diversified()
    assert expanded.size == DIVERSIFIED_ASSET_COUNT == 26
    assert DIVERSIFIED_ASSETS[:len(PRODUCTION_ASSETS)] == tuple(PRODUCTION_ASSETS)
    assert expanded.health_check()
    assert DEFAULT_ASSETS == PRODUCTION_ASSETS
    assert DIVERSIFIED_RESEARCH_ASSETS == list(DIVERSIFIED_ASSETS)
    assert AssetUniverse.production().size == 14
    assert set(expanded.tickers) == set(DIVERSIFIED_ASSETS)
    assert expanded.get_asset("TIP").sector == "Inflation Linked Government"
    assert expanded.get_asset("SGOV").asset_class == "Bond"
    assert expanded.get_asset("IGOV").country == "International"
    for symbol in DIVERSIFIED_ASSETS:
        asset = expanded.get_asset(symbol)
        assert asset.currency == "USD"
        assert asset.benchmark and asset.name and asset.sector and asset.active


def test_expanded_research_universe_does_not_grant_paper_execution_eligibility():
    from assetuniverse import DIVERSIFIED_ASSETS
    from paperconfig import PaperConfigurationError, PaperRuntimeConfig

    with pytest.raises(PaperConfigurationError,match="canonical production asset order"):
        PaperRuntimeConfig(assets=DIVERSIFIED_ASSETS)
    assert PaperRuntimeConfig().assets == tuple(PRODUCTION_ASSETS)


# ======================================================================
# SECTION 1
# FIXTURES
# ======================================================================


@pytest.fixture
def custom_asset() -> Asset:
    """
    Return a deterministic custom test asset.
    """

    return Asset(
        ticker="TEST",
        name="Test Asset",
        asset_class="Equity",
        sector="Test Sector",
        country="USA",
        currency="USD",
        benchmark="Test Benchmark",
        active=True,
    )


@pytest.fixture
def production_universe() -> AssetUniverse:
    """
    Return the canonical production universe.
    """

    return AssetUniverse.production()


# ======================================================================
# SECTION 2
# ASSET IMMUTABILITY
# ======================================================================


def test_asset_is_immutable(
    custom_asset,
):
    """
    Asset instances must be immutable.
    """

    with pytest.raises(
        AttributeError,
    ):
        custom_asset.ticker = "OTHER"


def test_asset_is_frozen(
    custom_asset,
):
    """
    Verify the frozen Asset contract.
    """

    assert custom_asset.ticker == "TEST"

    assert custom_asset.active is True


# ======================================================================
# SECTION 3
# GENERIC UNIVERSE
# ======================================================================


def test_generic_universe_starts_empty():
    """
    Generic AssetUniverse instances start empty.
    """

    universe = AssetUniverse()

    assert universe.size == 0

    assert universe.tickers == []

    assert universe.assets == []

    assert (
        universe.is_production_universe
        is False
    )


def test_add_asset(
    custom_asset,
):
    """
    Verify successful asset registration.
    """

    universe = AssetUniverse()

    universe.add_asset(
        custom_asset
    )

    assert universe.size == 1

    assert universe.contains(
        "TEST"
    )

    assert (
        universe.get_asset(
            "TEST"
        )
        == custom_asset
    )


def test_add_asset_rejects_non_asset():
    """
    Reject objects that are not Asset instances.
    """

    universe = AssetUniverse()

    with pytest.raises(
        TypeError,
        match="Asset instance",
    ):
        universe.add_asset(
            "SPY"
        )


def test_duplicate_asset_is_rejected(
    custom_asset,
):
    """
    Duplicate tickers must be rejected.
    """

    universe = AssetUniverse()

    universe.add_asset(
        custom_asset
    )

    with pytest.raises(
        ValueError,
        match="Duplicate ticker",
    ):
        universe.add_asset(
            custom_asset
        )


# ======================================================================
# SECTION 4
# TICKER VALIDATION
# ======================================================================


def test_empty_ticker_is_rejected():
    """
    Empty ticker identifiers must be rejected.
    """

    universe = AssetUniverse()

    asset = Asset(
        ticker="",
        name="Invalid",
        asset_class="Equity",
        sector="Test",
        country="USA",
        currency="USD",
        benchmark="Test",
    )

    with pytest.raises(
        ValueError,
        match="ticker cannot be empty",
    ):
        universe.add_asset(
            asset
        )


def test_lowercase_ticker_is_rejected():
    """
    Lowercase ticker identifiers must be rejected.
    """

    universe = AssetUniverse()

    asset = Asset(
        ticker="spy",
        name="Invalid",
        asset_class="Equity",
        sector="Test",
        country="USA",
        currency="USD",
        benchmark="Test",
    )

    with pytest.raises(
        ValueError,
        match="uppercase",
    ):
        universe.add_asset(
            asset
        )


def test_whitespace_ticker_is_rejected():
    """
    Tickers containing surrounding whitespace must be rejected.
    """

    universe = AssetUniverse()

    asset = Asset(
        ticker=" SPY",
        name="Invalid",
        asset_class="Equity",
        sector="Test",
        country="USA",
        currency="USD",
        benchmark="Test",
    )

    with pytest.raises(
        ValueError,
    ):
        universe.add_asset(
            asset
        )


# ======================================================================
# SECTION 5
# LOOKUP AND MEMBERSHIP
# ======================================================================


def test_lookup_is_case_insensitive(
    custom_asset,
):
    """
    Lookup and membership normalize ticker case and whitespace.
    """

    universe = AssetUniverse()

    universe.add_asset(
        custom_asset
    )

    assert universe.contains(
        "test"
    )

    assert universe.contains(
        " TEST "
    )

    assert (
        universe.get_asset(
            "test"
        )
        == custom_asset
    )


def test_unknown_asset_lookup_fails():
    """
    Unknown assets must raise KeyError.
    """

    universe = AssetUniverse()

    with pytest.raises(
        KeyError,
    ):
        universe.get_asset(
            "UNKNOWN"
        )


def test_unknown_asset_removal_fails():
    """
    Removing an unknown asset must raise KeyError.
    """

    universe = AssetUniverse()

    with pytest.raises(
        KeyError,
    ):
        universe.remove_asset(
            "UNKNOWN"
        )


# ======================================================================
# SECTION 6
# REMOVAL
# ======================================================================


def test_remove_asset(
    custom_asset,
):
    """
    Verify asset removal.
    """

    universe = AssetUniverse()

    universe.add_asset(
        custom_asset
    )

    universe.remove_asset(
        "TEST"
    )

    assert universe.size == 0

    assert not universe.contains(
        "TEST"
    )


# ======================================================================
# SECTION 7
# FILTERING
# ======================================================================


def test_asset_class_filters():
    """
    Verify asset-class filtering.
    """

    universe = AssetUniverse()

    universe.add_asset(
        Asset(
            ticker="EQ",
            name="Equity",
            asset_class="Equity",
            sector="Equity",
            country="USA",
            currency="USD",
            benchmark="EQ",
        )
    )

    universe.add_asset(
        Asset(
            ticker="BD",
            name="Bond",
            asset_class="Bond",
            sector="Government",
            country="USA",
            currency="USD",
            benchmark="BD",
        )
    )

    assert [
        asset.ticker
        for asset in universe.equities()
    ] == [
        "EQ"
    ]

    assert [
        asset.ticker
        for asset in universe.bonds()
    ] == [
        "BD"
    ]


def test_active_and_inactive_assets():
    """
    Verify active and inactive asset filtering.
    """

    universe = AssetUniverse()

    universe.add_asset(
        Asset(
            ticker="ACTIVE",
            name="Active",
            asset_class="Equity",
            sector="Test",
            country="USA",
            currency="USD",
            benchmark="Test",
            active=True,
        )
    )

    universe.add_asset(
        Asset(
            ticker="INACTIVE",
            name="Inactive",
            asset_class="Equity",
            sector="Test",
            country="USA",
            currency="USD",
            benchmark="Test",
            active=False,
        )
    )

    assert len(
        universe.active_assets
    ) == 1

    assert len(
        universe.inactive_assets
    ) == 1


def test_invalid_filter_field():
    """
    Invalid filter fields must be rejected.
    """

    universe = AssetUniverse()

    with pytest.raises(
        AttributeError,
        match="Asset has no field",
    ):
        universe.filter(
            invalid_field="value"
        )


# ======================================================================
# SECTION 8
# SERIALIZATION
# ======================================================================


def test_serialization_round_trip(
    custom_asset,
):
    """
    Verify generic serialization and restoration.
    """

    universe = AssetUniverse()

    universe.add_asset(
        custom_asset
    )

    serialized = (
        universe.to_dict()
    )

    restored = (
        AssetUniverse.from_dict(
            serialized
        )
    )

    assert restored.size == 1

    assert restored.tickers == [
        "TEST"
    ]

    assert (
        restored.get_asset(
            "TEST"
        )
        == custom_asset
    )


def test_from_dict_rejects_non_dictionary():
    """
    from_dict must reject non-dictionary input.
    """

    with pytest.raises(
        TypeError,
    ):
        AssetUniverse.from_dict(
            []
        )


def test_from_dict_rejects_invalid_definition():
    """
    from_dict must reject malformed asset definitions.
    """

    with pytest.raises(
        TypeError,
    ):
        AssetUniverse.from_dict(
            {
                "TEST": "invalid"
            }
        )


# ======================================================================
# SECTION 9
# DATAFRAME EXPORT
# ======================================================================


def test_dataframe_export(
    custom_asset,
):
    """
    Verify DataFrame serialization.
    """

    universe = AssetUniverse()

    universe.add_asset(
        custom_asset
    )

    dataframe = (
        universe.to_dataframe()
    )

    assert dataframe.shape[0] == 1

    assert "ticker" in (
        dataframe.columns
    )

    assert "asset_class" in (
        dataframe.columns
    )

    assert "currency" in (
        dataframe.columns
    )


# ======================================================================
# SECTION 10
# PRODUCTION UNIVERSE
# ======================================================================


def test_production_universe_has_14_assets(
    production_universe,
):
    """
    The canonical production universe must contain exactly 14 assets.
    """

    assert (
        production_universe.size
        == 14
    )

    assert (
        PRODUCTION_ASSET_COUNT
        == 14
    )

    assert (
        production_universe.PRODUCTION_ASSET_COUNT
        == 14
    )


def test_production_tickers_are_canonical(
    production_universe,
):
    """
    Verify the canonical production ticker set.
    """

    expected = {
        "SPY",
        "QQQ",
        "IWM",
        "VEA",
        "VWO",
        "TLT",
        "IEF",
        "SHY",
        "LQD",
        "HYG",
        "GLD",
        "SLV",
        "DBC",
        "VNQ",
    }

    assert set(
        production_universe.tickers
    ) == expected


def test_production_tickers_are_unique():
    """
    The production ticker list must contain no duplicates.
    """

    assert len(
        PRODUCTION_ASSETS
    ) == len(
        set(
            PRODUCTION_ASSETS
        )
    )


def test_production_reference_tuple_is_canonical():
    """
    Verify the authoritative ordered production tuple.
    """

    assert (
        PRODUCTION_ASSET_TUPLE
        == (
            "SPY",
            "QQQ",
            "IWM",
            "VEA",
            "VWO",
            "TLT",
            "IEF",
            "SHY",
            "LQD",
            "HYG",
            "GLD",
            "SLV",
            "DBC",
            "VNQ",
        )
    )


def test_production_universe_flag(
    production_universe,
):
    """
    The production factory must produce a production universe.
    """

    assert (
        production_universe.is_production_universe
        is True
    )


def test_production_universe_is_healthy(
    production_universe,
):
    """
    The production universe must pass its health check.
    """

    assert (
        production_universe.health_check()
        is True
    )


# ======================================================================
# SECTION 11
# PRODUCTION ASSET CLASSES
# ======================================================================


def test_production_asset_class_counts(
    production_universe,
):
    """
    Verify canonical production asset-class counts.
    """

    assert len(
        production_universe.equities()
    ) == 5

    assert len(
        production_universe.bonds()
    ) == 5

    assert len(
        production_universe.commodities()
    ) == 3

    assert len(
        production_universe.reits()
    ) == 1


def test_production_equity_tickers(
    production_universe,
):
    """
    Verify canonical equity membership.
    """

    assert {
        asset.ticker
        for asset
        in production_universe.equities()
    } == {
        "SPY",
        "QQQ",
        "IWM",
        "VEA",
        "VWO",
    }


def test_production_bond_tickers(
    production_universe,
):
    """
    Verify canonical bond membership.
    """

    assert {
        asset.ticker
        for asset
        in production_universe.bonds()
    } == {
        "TLT",
        "IEF",
        "SHY",
        "LQD",
        "HYG",
    }


def test_production_commodity_tickers(
    production_universe,
):
    """
    Verify canonical commodity membership.
    """

    assert {
        asset.ticker
        for asset
        in production_universe.commodities()
    } == {
        "GLD",
        "SLV",
        "DBC",
    }


def test_production_reit_tickers(
    production_universe,
):
    """
    Verify canonical REIT membership.
    """

    assert {
        asset.ticker
        for asset
        in production_universe.reits()
    } == {
        "VNQ",
    }


# ======================================================================
# SECTION 12
# PRODUCTION DEFINITIONS
# ======================================================================


def test_production_definitions_match_ticker_universe():
    """
    Production definitions must exactly match the ticker universe.
    """

    definition_tickers = [
        definition["ticker"]
        for definition
        in PRODUCTION_ASSET_DEFINITIONS
    ]

    assert len(
        definition_tickers
    ) == 14

    assert len(
        set(
            definition_tickers
        )
    ) == 14

    assert set(
        definition_tickers
    ) == set(
        PRODUCTION_ASSETS
    )


def test_production_definitions_have_required_fields():
    """
    Every production definition must contain all required metadata.
    """

    required = {
        "ticker",
        "name",
        "asset_class",
        "sector",
        "country",
        "currency",
        "benchmark",
        "active",
    }

    for definition in (
        PRODUCTION_ASSET_DEFINITIONS
    ):

        assert required.issubset(
            definition.keys()
        )


def test_all_production_assets_are_active():
    """
    All canonical production assets must be active.
    """

    assert all(
        definition["active"] is True
        for definition
        in PRODUCTION_ASSET_DEFINITIONS
    )


# ======================================================================
# SECTION 13
# PRODUCTION SERIALIZATION
# ======================================================================


def test_production_serialization_round_trip(
    production_universe,
):
    """
    Verify production universe serialization and restoration.
    """

    exported = (
        production_universe.to_dict()
    )

    assert len(
        exported
    ) == 14

    restored = (
        AssetUniverse.from_dict(
            exported
        )
    )

    assert restored.size == 14

    assert set(
        restored.tickers
    ) == set(
        PRODUCTION_ASSETS
    )

    assert (
        restored.is_production_universe
        is True
    )

    assert (
        restored.health_check()
        is True
    )


# ======================================================================
# SECTION 14
# PRODUCTION METADATA
# ======================================================================


def test_production_metadata(
    production_universe,
):
    """
    Verify production universe metadata.
    """

    metadata = (
        production_universe.metadata
    )

    assert (
        metadata["version"]
        == "1.0.0"
    )

    assert (
        metadata["assets"]
        == 14
    )

    assert (
        metadata["active"]
        == 14
    )

    assert (
        metadata["inactive"]
        == 0
    )

    assert (
        metadata["production_asset_count"]
        == 14
    )

    assert (
        metadata["is_production_universe"]
        is True
    )


# ======================================================================
# SECTION 15
# PRODUCTION NO-CASH RULE
# ======================================================================


def test_cash_is_not_a_production_asset(
    production_universe,
):
    """
    CASH must not be part of the canonical production asset universe.
    """

    assert not production_universe.contains(
        "CASH"
    )

    assert (
        production_universe.cash()
        == []
    )


# ======================================================================
# SECTION 16
# API CONTRACT
# ======================================================================


def test_public_api_contract():
    """
    Verify the frozen public API contract.
    """

    assert (
        AssetUniverse.API_VERSION
        == "1.0.0"
    )

    assert tuple(
        AssetUniverse.PUBLIC_METHODS
    ) == (
        "add_asset",
        "remove_asset",
        "get_asset",
        "tickers",
        "metadata",
    )


# ======================================================================
# SECTION 17
# DETERMINISM
# ======================================================================


def test_production_factory_is_deterministic():
    """
    Repeated production factory calls must produce equivalent universes.
    """

    first = (
        AssetUniverse.production()
    )

    second = (
        AssetUniverse.production()
    )

    assert (
        first.tickers
        == second.tickers
    )

    assert (
        first.to_dict()
        == second.to_dict()
    )

    assert (
        first.metadata
        == second.metadata
    )


# ======================================================================
# SECTION 18
# PRODUCTION ASSET LOOKUP
# ======================================================================


def test_all_production_assets_are_retrievable(
    production_universe,
):
    """
    Every canonical production ticker must resolve successfully.
    """

    for ticker in PRODUCTION_ASSETS:

        assert production_universe.contains(
            ticker
        )

        asset = (
            production_universe.get_asset(
                ticker
            )
        )

        assert asset.ticker == ticker

        assert asset.active is True


# ======================================================================
# SECTION 19
# PRODUCTION UNIVERSE INTEGRITY
# ======================================================================


def test_production_universe_has_no_inactive_assets(
    production_universe,
):
    """
    The canonical production universe must contain only active assets.
    """

    assert (
        production_universe.inactive_assets
        == []
    )

    assert all(
        asset.active
        for asset
        in production_universe.assets
    )


def test_production_universe_contains_no_duplicate_tickers(
    production_universe,
):
    """
    Production ticker identifiers must be unique.
    """

    tickers = [
        asset.ticker
        for asset
        in production_universe.assets
    ]

    assert len(
        tickers
    ) == len(
        set(tickers)
    )


def test_production_universe_asset_count_matches_classes(
    production_universe,
):
    """
    Asset-class partitions must reconcile exactly to 14 assets.
    """

    total = (
        len(
            production_universe.equities()
        )
        + len(
            production_universe.bonds()
        )
        + len(
            production_universe.commodities()
        )
        + len(
            production_universe.reits()
        )
    )

    assert total == 14


# ======================================================================
# SECTION 20
# ASSET METADATA INTEGRITY
# ======================================================================


def test_production_asset_metadata_is_complete(
    production_universe,
):
    """
    Every production asset must contain complete metadata.
    """

    for asset in (
        production_universe.assets
    ):

        assert asset.ticker

        assert asset.name

        assert asset.asset_class

        assert asset.sector

        assert asset.country

        assert asset.currency

        assert asset.benchmark

        assert isinstance(
            asset.active,
            bool,
        )


# ======================================================================
# SECTION 21
# SERIALIZATION KEY INTEGRITY
# ======================================================================


def test_serialization_keys_match_asset_tickers(
    production_universe,
):
    """
    Serialized dictionary keys must equal canonical tickers.
    """

    serialized = (
        production_universe.to_dict()
    )

    assert set(
        serialized.keys()
    ) == set(
        PRODUCTION_ASSETS
    )


# ======================================================================
# SECTION 22
# PRODUCTION CLASSIFICATION RECONCILIATION
# ======================================================================


def test_production_asset_classes_are_exhaustive(
    production_universe,
):
    """
    Every production asset must belong to exactly one expected class.
    """

    expected_classes = {
        "Equity",
        "Bond",
        "Commodity",
        "REIT",
    }

    assert set(
        production_universe.asset_classes
    ) == expected_classes


def test_production_assets_are_all_usd(
    production_universe,
):
    """
    Verify the canonical production currency classification.
    """

    assert (
        production_universe.currencies
        == ["USD"]
    )


# ======================================================================
# SECTION 23
# HEALTH-CHECK CONTRACT
# ======================================================================


def test_empty_generic_universe_is_healthy():
    """
    An empty generic universe is internally consistent.
    """

    universe = AssetUniverse()

    assert (
        universe.health_check()
        is True
    )


def test_custom_universe_is_healthy(
    custom_asset,
):
    """
    A valid custom universe must pass health validation.
    """

    universe = AssetUniverse()

    universe.add_asset(
        custom_asset
    )

    assert (
        universe.health_check()
        is True
    )


# ======================================================================
# SECTION 24
# REGRESSION ENTRY POINT
# ======================================================================


def run_regression_tests() -> None:
    """
    Execute a lightweight production-universe regression certification.
    """

    production = (
        AssetUniverse.production()
    )

    assert (
        production.health_check()
        is True
    )

    assert (
        production.size
        == 14
    )

    assert (
        set(
            production.tickers
        )
        == set(
            PRODUCTION_ASSETS
        )
    )

    print(
        "============================================================"
    )

    print(
        "AssetUniverse regression certification: PASS"
    )

    print(
        "Production asset count: 14"
    )

    print(
        "Production tickers:"
    )

    print(
        production.tickers
    )

    print(
        "============================================================"
    )


# ======================================================================
# SECTION 25
# MODULE ENTRY POINT
# ======================================================================


if __name__ == "__main__":

    run_regression_tests()
