"""
======================================================================
ASSET UNIVERSE
======================================================================

Institutional Asset Universe

Maintains the canonical list of investable assets together with their
metadata.

ARCHITECTURAL PRINCIPLE
-----------------------
All portfolio construction, forecasting, optimization, risk modelling,
scenario analysis and execution modules should consume AssetUniverse
instead of maintaining independent ticker lists.

UNIVERSE MODES
--------------
1. AssetUniverse()

   Generic empty universe.

   This preserves the original generic AssetUniverse behaviour and
   allows callers/tests to construct custom universes explicitly.

2. AssetUniverse.production()

   Canonical 14-asset production universe.

   This is the authoritative production investment universe used by
   the production portfolio decision pipeline.

CANONICAL PRODUCTION ASSETS
---------------------------
    SPY
    QQQ
    IWM
    VEA
    VWO
    TLT
    IEF
    SHY
    LQD
    HYG
    GLD
    SLV
    DBC
    VNQ

IMPORTANT
---------
Production modules must obtain their production ticker universe from
AssetUniverse.production() rather than maintaining their own ticker
lists.

======================================================================
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable


# ======================================================================
# SECTION 1
# ASSET
# ======================================================================


@dataclass(frozen=True)
class Asset:
    """
    Immutable description of one investable asset.
    """

    ticker: str

    name: str

    asset_class: str

    sector: str

    country: str

    currency: str

    benchmark: str

    active: bool = True


# ======================================================================
# SECTION 2
# CANONICAL PRODUCTION UNIVERSE
# ======================================================================


# ----------------------------------------------------------------------
# 2.1 PRODUCTION TICKERS
# ----------------------------------------------------------------------

PRODUCTION_ASSETS = [
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
]


# Immutable reference representation.

PRODUCTION_ASSET_TUPLE = tuple(
    PRODUCTION_ASSETS
)


# Explicit production universe size.

PRODUCTION_ASSET_COUNT = len(
    PRODUCTION_ASSETS
)


# ----------------------------------------------------------------------
# 2.2 PRODUCTION ASSET DEFINITIONS
# ----------------------------------------------------------------------
#
# These definitions are the canonical metadata associated with the
# production universe.
#
# The ticker list above remains the canonical ordering supplied to
# production components.
#
# ----------------------------------------------------------------------

PRODUCTION_ASSET_DEFINITIONS = (
    {
        "ticker": "SPY",
        "name": "SPDR S&P 500 ETF",
        "asset_class": "Equity",
        "sector": "US Large Cap",
        "country": "USA",
        "currency": "USD",
        "benchmark": "S&P 500",
        "active": True,
    },
    {
        "ticker": "QQQ",
        "name": "Invesco QQQ",
        "asset_class": "Equity",
        "sector": "US Technology / Growth",
        "country": "USA",
        "currency": "USD",
        "benchmark": "NASDAQ-100",
        "active": True,
    },
    {
        "ticker": "IWM",
        "name": "iShares Russell 2000 ETF",
        "asset_class": "Equity",
        "sector": "US Small Cap",
        "country": "USA",
        "currency": "USD",
        "benchmark": "Russell 2000",
        "active": True,
    },
    {
        "ticker": "VEA",
        "name": "Vanguard FTSE Developed Markets ETF",
        "asset_class": "Equity",
        "sector": "Developed International",
        "country": "International",
        "currency": "USD",
        "benchmark": "FTSE Developed All Cap ex US",
        "active": True,
    },
    {
        "ticker": "VWO",
        "name": "Vanguard FTSE Emerging Markets ETF",
        "asset_class": "Equity",
        "sector": "Emerging Markets",
        "country": "Emerging Markets",
        "currency": "USD",
        "benchmark": "FTSE Emerging Markets All Cap China A Inclusion",
        "active": True,
    },
    {
        "ticker": "TLT",
        "name": "iShares 20+ Year Treasury Bond ETF",
        "asset_class": "Bond",
        "sector": "Long Duration Government",
        "country": "USA",
        "currency": "USD",
        "benchmark": "ICE US Treasury 20+ Year",
        "active": True,
    },
    {
        "ticker": "IEF",
        "name": "iShares 7-10 Year Treasury Bond ETF",
        "asset_class": "Bond",
        "sector": "Intermediate Government",
        "country": "USA",
        "currency": "USD",
        "benchmark": "ICE US Treasury 7-10 Year",
        "active": True,
    },
    {
        "ticker": "SHY",
        "name": "iShares 1-3 Year Treasury Bond ETF",
        "asset_class": "Bond",
        "sector": "Short Duration Government",
        "country": "USA",
        "currency": "USD",
        "benchmark": "ICE US Treasury 1-3 Year",
        "active": True,
    },
    {
        "ticker": "LQD",
        "name": "iShares iBoxx Investment Grade Corporate Bond ETF",
        "asset_class": "Bond",
        "sector": "Investment Grade Corporate",
        "country": "USA",
        "currency": "USD",
        "benchmark": "Markit iBoxx USD Liquid Investment Grade",
        "active": True,
    },
    {
        "ticker": "HYG",
        "name": "iShares iBoxx High Yield Corporate Bond ETF",
        "asset_class": "Bond",
        "sector": "High Yield Corporate",
        "country": "USA",
        "currency": "USD",
        "benchmark": "Markit iBoxx USD Liquid High Yield",
        "active": True,
    },
    {
        "ticker": "GLD",
        "name": "SPDR Gold Shares",
        "asset_class": "Commodity",
        "sector": "Precious Metals",
        "country": "USA",
        "currency": "USD",
        "benchmark": "Gold",
        "active": True,
    },
    {
        "ticker": "SLV",
        "name": "iShares Silver Trust",
        "asset_class": "Commodity",
        "sector": "Precious Metals",
        "country": "USA",
        "currency": "USD",
        "benchmark": "Silver",
        "active": True,
    },
    {
        "ticker": "DBC",
        "name": "Invesco DB Commodity Index Tracking Fund",
        "asset_class": "Commodity",
        "sector": "Broad Commodities",
        "country": "USA",
        "currency": "USD",
        "benchmark": "DBIQ Optimum Yield Diversified Commodity Index",
        "active": True,
    },
    {
        "ticker": "VNQ",
        "name": "Vanguard Real Estate ETF",
        "asset_class": "REIT",
        "sector": "Real Estate",
        "country": "USA",
        "currency": "USD",
        "benchmark": "MSCI US Investable Market Real Estate 25/50",
        "active": True,
    },
)


# ======================================================================
# SECTION 3
# PRODUCTION UNIVERSE VALIDATION
# ======================================================================


def _validate_production_definitions() -> None:
    """
    Validate the static canonical production universe.

    This function executes at module load time so a malformed production
    universe cannot silently enter the dependency graph.
    """

    if len(PRODUCTION_ASSETS) != 14:
        raise RuntimeError(
            (
                "Canonical production universe must contain exactly "
                f"14 assets. Got {len(PRODUCTION_ASSETS)}."
            )
        )

    if len(
        set(PRODUCTION_ASSETS)
    ) != len(PRODUCTION_ASSETS):
        raise RuntimeError(
            "Canonical production universe contains duplicate tickers."
        )

    definition_tickers = [
        definition["ticker"]
        for definition in PRODUCTION_ASSET_DEFINITIONS
    ]

    if len(definition_tickers) != 14:
        raise RuntimeError(
            (
                "Canonical production asset definitions must contain "
                f"exactly 14 assets. Got {len(definition_tickers)}."
            )
        )

    if len(
        set(definition_tickers)
    ) != len(definition_tickers):
        raise RuntimeError(
            "Canonical production asset definitions contain duplicates."
        )

    if set(definition_tickers) != set(
        PRODUCTION_ASSETS
    ):
        raise RuntimeError(
            (
                "Production ticker list and production asset "
                "definitions do not contain the same assets."
            )
        )

    for definition in PRODUCTION_ASSET_DEFINITIONS:

        required_fields = {
            "ticker",
            "name",
            "asset_class",
            "sector",
            "country",
            "currency",
            "benchmark",
            "active",
        }

        missing_fields = (
            required_fields
            - set(definition)
        )

        if missing_fields:
            raise RuntimeError(
                (
                    "Production asset definition for "
                    f"{definition.get('ticker', '<unknown>')} "
                    "is missing fields: "
                    + ", ".join(
                        sorted(missing_fields)
                    )
                )
            )


_validate_production_definitions()


# ======================================================================
# SECTION 4
# ASSET UNIVERSE
# ======================================================================


class AssetUniverse:
    """
    Canonical investment universe.

    A generic AssetUniverse is intentionally empty.

    Use:

        AssetUniverse()

    for a custom universe.

    Use:

        AssetUniverse.production()

    for the canonical 14-asset production universe.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (
        "add_asset",
        "remove_asset",
        "get_asset",
        "tickers",
        "metadata",
    )

    PRODUCTION_ASSET_COUNT = (
        PRODUCTION_ASSET_COUNT
    )

    # ==================================================================
    # CONSTRUCTOR
    # ==================================================================

    def __init__(
        self,
    ) -> None:
        """
        Construct an empty generic asset universe.
        """

        self._assets: Dict[str, Asset] = {}

    # ==================================================================
    # PRODUCTION FACTORY
    # ==================================================================

    @classmethod
    def production(
        cls,
    ) -> "AssetUniverse":
        """
        Construct the canonical 14-asset production universe.

        The production universe is generated exclusively from the
        canonical PRODUCTION_ASSET_DEFINITIONS.

        Returns
        -------
        AssetUniverse
            A fully populated and validated 14-asset production
            universe.
        """

        universe = cls()

        for definition in PRODUCTION_ASSET_DEFINITIONS:

            universe.add_asset(
                Asset(
                    **definition
                )
            )

        universe._validate_production_universe()

        return universe

    # ==================================================================
    # PRODUCTION VALIDATION
    # ==================================================================

    def _validate_production_universe(
        self,
    ) -> None:
        """
        Validate that this universe exactly matches the canonical
        production universe.
        """

        if self.size != PRODUCTION_ASSET_COUNT:

            raise RuntimeError(
                (
                    "Production universe must contain exactly "
                    f"{PRODUCTION_ASSET_COUNT} assets. "
                    f"Got {self.size}."
                )
            )

        actual_tickers = set(
            self.tickers
        )

        expected_tickers = set(
            PRODUCTION_ASSETS
        )

        if actual_tickers != expected_tickers:

            missing = sorted(
                expected_tickers
                - actual_tickers
            )

            unexpected = sorted(
                actual_tickers
                - expected_tickers
            )

            raise RuntimeError(
                (
                    "Production universe ticker mismatch. "
                    f"Missing={missing}; "
                    f"Unexpected={unexpected}."
                )
            )

        if not all(
            asset.active
            for asset in self.assets
        ):

            raise RuntimeError(
                "All canonical production assets must be active."
            )

        if not self.health_check():

            raise RuntimeError(
                "Canonical production universe failed health check."
            )

    # ==================================================================
    # ADD
    # ==================================================================

    def add_asset(
        self,
        asset: Asset,
    ) -> None:
        """
        Add one asset to the universe.
        """

        if not isinstance(
            asset,
            Asset,
        ):
            raise TypeError(
                "asset must be an Asset instance."
            )

        ticker = (
            str(asset.ticker)
            .strip()
            .upper()
        )

        if not ticker:
            raise ValueError(
                "Asset ticker cannot be empty."
            )

        if ticker != asset.ticker:
            raise ValueError(
                (
                    "Asset ticker must be normalized to uppercase "
                    "without surrounding whitespace."
                )
            )

        if ticker in self._assets:
            raise ValueError(
                f"Duplicate ticker '{ticker}'."
            )

        self._assets[ticker] = asset

    # ==================================================================
    # REMOVE
    # ==================================================================

    def remove_asset(
        self,
        ticker: str,
    ) -> None:
        """
        Remove an asset by ticker.
        """

        normalized_ticker = (
            str(ticker)
            .strip()
            .upper()
        )

        if normalized_ticker not in self._assets:
            raise KeyError(
                f"{normalized_ticker} not found."
            )

        del self._assets[
            normalized_ticker
        ]

    # ==================================================================
    # GET
    # ==================================================================

    def get_asset(
        self,
        ticker: str,
    ) -> Asset:
        """
        Return an asset by ticker.
        """

        normalized_ticker = (
            str(ticker)
            .strip()
            .upper()
        )

        if normalized_ticker not in self._assets:
            raise KeyError(
                f"{normalized_ticker} not found."
            )

        return self._assets[
            normalized_ticker
        ]

    # ==================================================================
    # TICKERS
    # ==================================================================

    @property
    def tickers(
        self,
    ) -> list[str]:
        """
        Return sorted ticker symbols.
        """

        return sorted(
            self._assets.keys()
        )

    # ==================================================================
    # COUNT
    # ==================================================================

    @property
    def size(
        self,
    ) -> int:
        """
        Return the number of assets.
        """

        return len(
            self._assets
        )

    # ==================================================================
    # METADATA
    # ==================================================================

    @property
    def metadata(
        self,
    ) -> dict[str, Any]:
        """
        Return universe metadata.
        """

        return {
            "version": self.API_VERSION,
            "assets": self.size,
            "active": len(
                self.active_assets
            ),
            "inactive": len(
                self.inactive_assets
            ),
            "asset_classes": self.asset_classes,
            "countries": self.countries,
            "currencies": self.currencies,
            "benchmarks": self.benchmarks,
            "production_asset_count": (
                self.PRODUCTION_ASSET_COUNT
            ),
            "is_production_universe": (
                self.is_production_universe
            ),
        }

    # ==================================================================
    # ALL ASSETS
    # ==================================================================

    @property
    def assets(
        self,
    ) -> list[Asset]:
        """
        Return all registered assets.
        """

        return list(
            self._assets.values()
        )

    # ==================================================================
    # PRODUCTION FLAG
    # ==================================================================

    @property
    def is_production_universe(
        self,
    ) -> bool:
        """
        Return True when the universe exactly matches the canonical
        14-asset production universe.
        """

        if self.size != PRODUCTION_ASSET_COUNT:
            return False

        return set(
            self.tickers
        ) == set(
            PRODUCTION_ASSETS
        )

    # ==================================================================
    # FILTER
    # ==================================================================

    def filter(
        self,
        **criteria: Any,
    ) -> list[Asset]:
        """
        Generic asset filtering.

        Examples
        --------
        filter(asset_class="Equity")

        filter(country="USA")

        filter(currency="USD")
        """

        valid_fields = {
            "ticker",
            "name",
            "asset_class",
            "sector",
            "country",
            "currency",
            "benchmark",
            "active",
        }

        results = self.assets

        for field, value in criteria.items():

            if field not in valid_fields:

                raise AttributeError(
                    (
                        f"Asset has no field '{field}'."
                    )
                )

            results = [
                asset
                for asset in results
                if getattr(
                    asset,
                    field,
                ) == value
            ]

        return results

    # ==================================================================
    # COMMON FILTERS
    # ==================================================================

    def equities(
        self,
    ) -> list[Asset]:
        """
        Return equity assets.
        """

        return self.filter(
            asset_class="Equity"
        )

    def bonds(
        self,
    ) -> list[Asset]:
        """
        Return bond assets.
        """

        return self.filter(
            asset_class="Bond"
        )

    def commodities(
        self,
    ) -> list[Asset]:
        """
        Return commodity assets.
        """

        return self.filter(
            asset_class="Commodity"
        )

    def reits(
        self,
    ) -> list[Asset]:
        """
        Return REIT assets.
        """

        return self.filter(
            asset_class="REIT"
        )

    def cash(
        self,
    ) -> list[Asset]:
        """
        Return cash assets.
        """

        return self.filter(
            asset_class="Cash"
        )

    # ==================================================================
    # ACTIVE
    # ==================================================================

    @property
    def active_assets(
        self,
    ) -> list[Asset]:
        """
        Return active assets.
        """

        return [
            asset
            for asset in self.assets
            if asset.active
        ]

    @property
    def inactive_assets(
        self,
    ) -> list[Asset]:
        """
        Return inactive assets.
        """

        return [
            asset
            for asset in self.assets
            if not asset.active
        ]

    # ==================================================================
    # UNIQUE VALUES
    # ==================================================================

    @property
    def asset_classes(
        self,
    ) -> list[str]:
        """
        Return unique asset classes.
        """

        return sorted(
            {
                asset.asset_class
                for asset in self.assets
            }
        )

    @property
    def sectors(
        self,
    ) -> list[str]:
        """
        Return unique sectors.
        """

        return sorted(
            {
                asset.sector
                for asset in self.assets
            }
        )

    @property
    def countries(
        self,
    ) -> list[str]:
        """
        Return unique countries.
        """

        return sorted(
            {
                asset.country
                for asset in self.assets
            }
        )

    @property
    def currencies(
        self,
    ) -> list[str]:
        """
        Return unique currencies.
        """

        return sorted(
            {
                asset.currency
                for asset in self.assets
            }
        )

    @property
    def benchmarks(
        self,
    ) -> list[str]:
        """
        Return unique benchmarks.
        """

        return sorted(
            {
                asset.benchmark
                for asset in self.assets
            }
        )

    # ==================================================================
    # EXISTS
    # ==================================================================

    def contains(
        self,
        ticker: str,
    ) -> bool:
        """
        Return True when the ticker exists.
        """

        normalized_ticker = (
            str(ticker)
            .strip()
            .upper()
        )

        return (
            normalized_ticker
            in self._assets
        )

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ) -> bool:
        """
        Validate internal consistency of the universe.
        """

        tickers: set[str] = set()

        for asset in self.assets:

            if not isinstance(
                asset,
                Asset,
            ):
                raise RuntimeError(
                    "Universe contains a non-Asset object."
                )

            ticker = asset.ticker

            if ticker in tickers:
                raise RuntimeError(
                    f"Duplicate ticker '{ticker}'."
                )

            tickers.add(
                ticker
            )

            if not ticker:
                raise RuntimeError(
                    "Empty ticker."
                )

            if ticker != ticker.strip():
                raise RuntimeError(
                    (
                        f"{ticker!r}: ticker contains "
                        "surrounding whitespace."
                    )
                )

            if ticker != ticker.upper():
                raise RuntimeError(
                    (
                        f"{ticker}: ticker must be uppercase."
                    )
                )

            if not asset.name:
                raise RuntimeError(
                    f"{ticker}: missing asset name."
                )

            if not asset.asset_class:
                raise RuntimeError(
                    f"{ticker}: missing asset class."
                )

            if not asset.sector:
                raise RuntimeError(
                    f"{ticker}: missing sector."
                )

            if not asset.country:
                raise RuntimeError(
                    f"{ticker}: missing country."
                )

            if not asset.currency:
                raise RuntimeError(
                    f"{ticker}: missing currency."
                )

            if not asset.benchmark:
                raise RuntimeError(
                    f"{ticker}: missing benchmark."
                )

            if not isinstance(
                asset.active,
                bool,
            ):
                raise RuntimeError(
                    f"{ticker}: active must be boolean."
                )

        if len(tickers) != self.size:
            raise RuntimeError(
                "Universe ticker integrity check failed."
            )

        return True

    # ==================================================================
    # TO DICTIONARY
    # ==================================================================

    def to_dict(
        self,
    ) -> dict[str, dict[str, Any]]:
        """
        Serialize the universe to a dictionary keyed by ticker.
        """

        return {
            asset.ticker: asdict(
                asset
            )
            for asset in self.assets
        }

    # ==================================================================
    # FROM DICTIONARY
    # ==================================================================

    @classmethod
    def from_dict(
        cls,
        data: dict[str, dict[str, Any]],
    ) -> "AssetUniverse":
        """
        Restore an AssetUniverse from serialized asset definitions.
        """

        if not isinstance(
            data,
            dict,
        ):
            raise TypeError(
                "data must be a dictionary."
            )

        universe = cls()

        for values in data.values():

            if not isinstance(
                values,
                dict,
            ):
                raise TypeError(
                    "Each asset definition must be a dictionary."
                )

            universe.add_asset(
                Asset(
                    **values
                )
            )

        universe.health_check()

        return universe

    # ==================================================================
    # EXPORT
    # ==================================================================

    def to_dataframe(
        self,
    ):
        """
        Export the universe to a pandas DataFrame.
        """

        import pandas as pd

        return pd.DataFrame(
            [
                asdict(asset)
                for asset in self.assets
            ]
        )


# ======================================================================
# SECTION 5
# REGRESSION TESTS — GENERIC UNIVERSE
# ======================================================================


def test_asset_universe() -> None:
    """
    Verify generic AssetUniverse behaviour.

    This test intentionally remains a five-asset custom universe and
    therefore does not depend on the production universe.
    """

    universe = AssetUniverse()

    # ==================================================================
    # ADD ASSETS
    # ==================================================================

    universe.add_asset(
        Asset(
            ticker="SPY",
            name="SPDR S&P 500 ETF",
            asset_class="Equity",
            sector="Large Cap",
            country="USA",
            currency="USD",
            benchmark="SP500",
        )
    )

    universe.add_asset(
        Asset(
            ticker="TLT",
            name="20+ Year Treasury",
            asset_class="Bond",
            sector="Government",
            country="USA",
            currency="USD",
            benchmark="Bloomberg Treasury",
        )
    )

    universe.add_asset(
        Asset(
            ticker="GLD",
            name="Gold ETF",
            asset_class="Commodity",
            sector="Precious Metals",
            country="USA",
            currency="USD",
            benchmark="Gold",
        )
    )

    universe.add_asset(
        Asset(
            ticker="VNQ",
            name="US REIT",
            asset_class="REIT",
            sector="Real Estate",
            country="USA",
            currency="USD",
            benchmark="US REIT",
        )
    )

    universe.add_asset(
        Asset(
            ticker="CASH",
            name="Cash",
            asset_class="Cash",
            sector="Cash",
            country="USA",
            currency="USD",
            benchmark="Cash",
            active=False,
        )
    )

    # ==================================================================
    # SIZE
    # ==================================================================

    assert universe.size == 5

    assert len(
        universe.assets
    ) == 5

    # ==================================================================
    # LOOKUP
    # ==================================================================

    spy = universe.get_asset(
        "SPY"
    )

    assert spy.name == (
        "SPDR S&P 500 ETF"
    )

    # ==================================================================
    # TICKERS
    # ==================================================================

    assert universe.tickers == [
        "CASH",
        "GLD",
        "SPY",
        "TLT",
        "VNQ",
    ]

    # ==================================================================
    # FILTERS
    # ==================================================================

    assert len(
        universe.equities()
    ) == 1

    assert len(
        universe.bonds()
    ) == 1

    assert len(
        universe.commodities()
    ) == 1

    assert len(
        universe.reits()
    ) == 1

    assert len(
        universe.cash()
    ) == 1

    # ==================================================================
    # ACTIVE
    # ==================================================================

    assert len(
        universe.active_assets
    ) == 4

    assert len(
        universe.inactive_assets
    ) == 1

    # ==================================================================
    # UNIQUE VALUES
    # ==================================================================

    assert "Equity" in (
        universe.asset_classes
    )

    assert "Bond" in (
        universe.asset_classes
    )

    assert "Commodity" in (
        universe.asset_classes
    )

    assert "REIT" in (
        universe.asset_classes
    )

    assert "Cash" in (
        universe.asset_classes
    )

    assert "USA" in (
        universe.countries
    )

    assert "USD" in (
        universe.currencies
    )

    # ==================================================================
    # CONTAINS
    # ==================================================================

    assert universe.contains(
        "SPY"
    )

    assert not universe.contains(
        "QQQ"
    )

    # ==================================================================
    # DATAFRAME
    # ==================================================================

    df = universe.to_dataframe()

    assert df.shape[0] == 5

    assert "ticker" in df.columns

    assert "asset_class" in df.columns

    # ==================================================================
    # METADATA
    # ==================================================================

    metadata = universe.metadata

    assert metadata["version"] == "1.0.0"

    assert metadata["assets"] == 5

    assert metadata[
        "is_production_universe"
    ] is False

    # ==================================================================
    # DUPLICATES
    # ==================================================================

    try:

        universe.add_asset(
            Asset(
                ticker="SPY",
                name="Duplicate",
                asset_class="Equity",
                sector="Large Cap",
                country="USA",
                currency="USD",
                benchmark="SP500",
            )
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:
        pass

    # ==================================================================
    # REMOVE
    # ==================================================================

    universe.remove_asset(
        "CASH"
    )

    assert universe.size == 4

    assert not universe.contains(
        "CASH"
    )

    # ==================================================================
    # HEALTH
    # ==================================================================

    assert universe.health_check()

    # ==================================================================
    # SERIALIZATION
    # ==================================================================

    exported = universe.to_dict()

    restored = (
        AssetUniverse.from_dict(
            exported
        )
    )

    assert restored.size == (
        universe.size
    )

    assert restored.tickers == (
        universe.tickers
    )

    # ==================================================================
    # API FREEZE
    # ==================================================================

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

    # ==================================================================
    # INVALID LOOKUP
    # ==================================================================

    try:

        universe.get_asset(
            "UNKNOWN"
        )

        raise AssertionError(
            "Expected KeyError"
        )

    except KeyError:
        pass

    # ==================================================================
    # INVALID REMOVE
    # ==================================================================

    try:

        universe.remove_asset(
            "UNKNOWN"
        )

        raise AssertionError(
            "Expected KeyError"
        )

    except KeyError:
        pass


# ======================================================================
# SECTION 6
# REGRESSION TESTS — PRODUCTION UNIVERSE
# ======================================================================


def test_production_asset_universe() -> None:
    """
    Verify the canonical 14-asset production universe.
    """

    universe = (
        AssetUniverse.production()
    )

    # ==================================================================
    # SIZE
    # ==================================================================

    assert universe.size == 14

    assert (
        universe.PRODUCTION_ASSET_COUNT
        == 14
    )

    assert (
        PRODUCTION_ASSET_COUNT
        == 14
    )

    # ==================================================================
    # TICKER INTEGRITY
    # ==================================================================

    assert len(
        PRODUCTION_ASSETS
    ) == 14

    assert len(
        set(PRODUCTION_ASSETS)
    ) == 14

    assert set(
        universe.tickers
    ) == set(
        PRODUCTION_ASSETS
    )

    assert (
        universe.tickers
        == sorted(PRODUCTION_ASSETS)
    )

    # ==================================================================
    # ORDERED PRODUCTION REFERENCE
    # ==================================================================

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

    # ==================================================================
    # PRODUCTION FLAG
    # ==================================================================

    assert (
        universe.is_production_universe
        is True
    )

    # ==================================================================
    # ALL ACTIVE
    # ==================================================================

    assert len(
        universe.active_assets
    ) == 14

    assert len(
        universe.inactive_assets
    ) == 0

    # ==================================================================
    # HEALTH
    # ==================================================================

    assert universe.health_check()

    # ==================================================================
    # EXPECTED ASSET CLASSES
    # ==================================================================

    assert (
        len(
            universe.equities()
        )
        == 5
    )

    assert (
        len(
            universe.bonds()
        )
        == 5
    )

    assert (
        len(
            universe.commodities()
        )
        == 3
    )

    assert (
        len(
            universe.reits()
        )
        == 1
    )

    # ==================================================================
    # EXPECTED TICKERS BY CLASS
    # ==================================================================

    assert set(
        asset.ticker
        for asset in universe.equities()
    ) == {
        "SPY",
        "QQQ",
        "IWM",
        "VEA",
        "VWO",
    }

    assert set(
        asset.ticker
        for asset in universe.bonds()
    ) == {
        "TLT",
        "IEF",
        "SHY",
        "LQD",
        "HYG",
    }

    assert set(
        asset.ticker
        for asset in universe.commodities()
    ) == {
        "GLD",
        "SLV",
        "DBC",
    }

    assert set(
        asset.ticker
        for asset in universe.reits()
    ) == {
        "VNQ",
    }

    # ==================================================================
    # LOOKUP
    # ==================================================================

    for ticker in PRODUCTION_ASSETS:

        assert universe.contains(
            ticker
        )

        asset = universe.get_asset(
            ticker
        )

        assert asset.ticker == ticker

        assert asset.active is True

    # ==================================================================
    # NO CASH AS PRODUCTION ASSET
    # ==================================================================

    assert not universe.contains(
        "CASH"
    )

    assert len(
        universe.cash()
    ) == 0

    # ==================================================================
    # METADATA
    # ==================================================================

    metadata = (
        universe.metadata
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
# SECTION 7
# REGRESSION TESTS — PRODUCTION DEFINITIONS
# ======================================================================


def test_production_asset_definitions() -> None:
    """
    Verify the canonical production definitions are complete and
    aligned with the canonical ticker list.
    """

    assert len(
        PRODUCTION_ASSET_DEFINITIONS
    ) == 14

    definition_tickers = [
        definition["ticker"]
        for definition
        in PRODUCTION_ASSET_DEFINITIONS
    ]

    assert len(
        definition_tickers
    ) == 14

    assert len(
        set(definition_tickers)
    ) == 14

    assert set(
        definition_tickers
    ) == set(
        PRODUCTION_ASSETS
    )

    for definition in (
        PRODUCTION_ASSET_DEFINITIONS
    ):

        assert definition[
            "ticker"
        ]

        assert definition[
            "name"
        ]

        assert definition[
            "asset_class"
        ]

        assert definition[
            "sector"
        ]

        assert definition[
            "country"
        ]

        assert definition[
            "currency"
        ]

        assert definition[
            "benchmark"
        ]

        assert definition[
            "active"
        ] is True


# ======================================================================
# SECTION 8
# REGRESSION TESTS — PRODUCTION SERIALIZATION
# ======================================================================


def test_production_asset_universe_serialization() -> None:
    """
    Verify serialization and restoration of the production universe.
    """

    universe = (
        AssetUniverse.production()
    )

    exported = (
        universe.to_dict()
    )

    assert len(
        exported
    ) == 14

    assert set(
        exported.keys()
    ) == set(
        PRODUCTION_ASSETS
    )

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

    assert restored.health_check()

    assert (
        restored.is_production_universe
        is True
    )


# ======================================================================
# SECTION 9
# REGRESSION TESTS — PRODUCTION IMMUTABILITY
# ======================================================================


def test_asset_immutability() -> None:
    """
    Verify Asset instances are immutable.
    """

    asset = Asset(
        ticker="SPY",
        name="SPDR S&P 500 ETF",
        asset_class="Equity",
        sector="Large Cap",
        country="USA",
        currency="USD",
        benchmark="SP500",
    )

    try:

        asset.ticker = "QQQ"

        raise AssertionError(
            "Expected FrozenInstanceError"
        )

    except AttributeError:
        pass


# ======================================================================
# SECTION 10
# REGRESSION ENTRY POINT
# ======================================================================


def run_regression_tests() -> None:
    """
    Run all AssetUniverse regression tests.
    """

    test_asset_universe()

    test_production_asset_universe()

    test_production_asset_definitions()

    test_production_asset_universe_serialization()

    test_asset_immutability()

    print(
        "============================================================"
    )

    print(
        "AssetUniverse regression tests passed."
    )

    print(
        "Canonical production universe: 14 assets."
    )

    print(
        "Production tickers:"
    )

    print(
        PRODUCTION_ASSETS
    )

    print(
        "============================================================"
    )


# ======================================================================
# SECTION 11
# MODULE ENTRY POINT
# ======================================================================


if __name__ == "__main__":

    run_regression_tests()