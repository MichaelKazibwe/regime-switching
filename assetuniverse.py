"""
===============================================================
ASSET UNIVERSE

Institutional Asset Universe

Maintains the canonical list of investable assets together
with their metadata.

All portfolio construction, forecasting, optimization,
risk modelling and execution modules should consume this
class instead of maintaining their own ticker lists.

===============================================================
"""

from dataclasses import dataclass
from typing import Dict


# ============================================================
# ASSET
# ============================================================

@dataclass(frozen=True)
class Asset:

    ticker: str

    name: str

    asset_class: str

    sector: str

    country: str

    currency: str

    benchmark: str

    active: bool = True


# ============================================================
# ASSET UNIVERSE
# ============================================================

class AssetUniverse:

    """
    Canonical investment universe.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (

        "add_asset",

        "remove_asset",

        "get_asset",

        "tickers",

        "metadata"

    )

    # ========================================================
    # CONSTRUCTOR
    # ========================================================

    def __init__(self):

        self._assets: Dict[str, Asset] = {}

    # ========================================================
    # ADD
    # ========================================================

    def add_asset(
        self,
        asset: Asset
    ):

        if asset.ticker in self._assets:

            raise ValueError(

                f"Duplicate ticker '{asset.ticker}'."

            )

        self._assets[asset.ticker] = asset

    # ========================================================
    # REMOVE
    # ========================================================

    def remove_asset(
        self,
        ticker: str
    ):

        if ticker not in self._assets:

            raise KeyError(

                f"{ticker} not found."

            )

        del self._assets[ticker]

    # ========================================================
    # GET
    # ========================================================

    def get_asset(
        self,
        ticker: str
    ) -> Asset:

        if ticker not in self._assets:

            raise KeyError(

                f"{ticker} not found."

            )

        return self._assets[ticker]

    # ========================================================
    # TICKERS
    # ========================================================

    @property
    def tickers(
        self
    ):

        return sorted(

            self._assets.keys()

        )

    # ========================================================
    # COUNT
    # ========================================================

    @property
    def size(
        self
    ):

        return len(

            self._assets

        )

    # ========================================================
    # METADATA
    # ========================================================

    @property
    def metadata(
        self
    ):

        return {

            "version":

                self.API_VERSION,

            "assets":

                self.size,

            "active":

                len(
                    self.active_assets
                ),

            "inactive":

                len(
                    self.inactive_assets
                ),

            "asset_classes":

                self.asset_classes,

            "countries":

                self.countries,

            "currencies":

                self.currencies

        }

    # ========================================================
    # ALL ASSETS
    # ========================================================

    @property
    def assets(
        self
    ):

        """
        Return all registered assets.
        """

        return list(

            self._assets.values()

        )

    # ========================================================
    # FILTER
    # ========================================================

    def filter(
        self,
        **criteria
    ):

        """
        Generic filtering.

        Example

        filter(asset_class="Equity")

        filter(country="USA")

        filter(currency="USD")
        """

        results = self.assets

        for field, value in criteria.items():

            results = [

                asset

                for asset in results

                if getattr(

                    asset,

                    field

                ) == value

            ]

        return results

    # ========================================================
    # COMMON FILTERS
    # ========================================================

    def equities(
        self
    ):

        return self.filter(

            asset_class="Equity"

        )

    def bonds(
        self
    ):

        return self.filter(

            asset_class="Bond"

        )

    def commodities(
        self
    ):

        return self.filter(

            asset_class="Commodity"

        )

    def reits(
        self
    ):

        return self.filter(

            asset_class="REIT"

        )

    def cash(
        self
    ):

        return self.filter(

            asset_class="Cash"

        )

    # ========================================================
    # ACTIVE
    # ========================================================

    @property
    def active_assets(
        self
    ):

        return [

            asset

            for asset in self.assets

            if asset.active

        ]

    @property
    def inactive_assets(
        self
    ):

        return [

            asset

            for asset in self.assets

            if not asset.active

        ]

    # ========================================================
    # UNIQUE VALUES
    # ========================================================

    @property
    def asset_classes(
        self
    ):

        return sorted(

            {

                asset.asset_class

                for asset in self.assets

            }

        )

    @property
    def sectors(
        self
    ):

        return sorted(

            {

                asset.sector

                for asset in self.assets

            }

        )

    @property
    def countries(
        self
    ):

        return sorted(

            {

                asset.country

                for asset in self.assets

            }

        )

    @property
    def currencies(
        self
    ):

        return sorted(

            {

                asset.currency

                for asset in self.assets

            }

        )

    @property
    def benchmarks(
        self
    ):

        return sorted(

            {

                asset.benchmark

                for asset in self.assets

            }

        )

    # ========================================================
    # EXISTS
    # ========================================================

    def contains(
        self,
        ticker
    ):

        return ticker in self._assets

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self
    ):

        """
        Validate the internal consistency of the universe.
        """

        tickers = set()

        for asset in self.assets:

            if asset.ticker in tickers:

                raise RuntimeError(

                    f"Duplicate ticker '{asset.ticker}'."

                )

            tickers.add(
                asset.ticker
            )

            if not asset.ticker:

                raise RuntimeError(
                    "Empty ticker."
                )

            if not asset.asset_class:

                raise RuntimeError(
                    f"{asset.ticker}: missing asset class."
                )

            if not asset.currency:

                raise RuntimeError(
                    f"{asset.ticker}: missing currency."
                )

        return True
    
    # ========================================================
    # TO DICTIONARY
    # ========================================================

    def to_dict(
        self
    ):

        return {

            asset.ticker:

                vars(asset)

            for asset in self.assets

        }
    
    # ========================================================
    # FROM DICTIONARY
    # ========================================================

    @classmethod
    def from_dict(
        cls,
        data
    ):

        universe = cls()

        for values in data.values():

            universe.add_asset(

                Asset(

                    **values

                )

            )

        return universe
    
    # ========================================================
    # EXPORT
    # ========================================================

    def to_dataframe(
        self
    ):

        import pandas as pd

        return pd.DataFrame(

            [

                vars(asset)

                for asset in self.assets

            ]

        )
    
# ============================================================
# REGRESSION TESTS
# ============================================================

def test_asset_universe():

    universe = AssetUniverse()

    # ========================================================
    # ADD ASSETS
    # ========================================================

    universe.add_asset(

        Asset(

            ticker="SPY",

            name="SPDR S&P 500 ETF",

            asset_class="Equity",

            sector="Large Cap",

            country="USA",

            currency="USD",

            benchmark="SP500"

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

            benchmark="Bloomberg Treasury"

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

            benchmark="Gold"

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

            benchmark="US REIT"

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

            active=False

        )

    )

    # ========================================================
    # SIZE
    # ========================================================

    assert universe.size == 5

    assert len(

        universe.assets

    ) == 5

    # ========================================================
    # LOOKUP
    # ========================================================

    spy = universe.get_asset(

        "SPY"

    )

    assert spy.name == "SPDR S&P 500 ETF"

    # ========================================================
    # TICKERS
    # ========================================================

    assert universe.tickers == [

        "CASH",

        "GLD",

        "SPY",

        "TLT",

        "VNQ"

    ]

    # ========================================================
    # FILTERS
    # ========================================================

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

    # ========================================================
    # ACTIVE
    # ========================================================

    assert len(

        universe.active_assets

    ) == 4

    assert len(

        universe.inactive_assets

    ) == 1

    # ========================================================
    # UNIQUE VALUES
    # ========================================================

    assert "Equity" in universe.asset_classes

    assert "Bond" in universe.asset_classes

    assert "Commodity" in universe.asset_classes

    assert "REIT" in universe.asset_classes

    assert "Cash" in universe.asset_classes

    assert "USA" in universe.countries

    assert "USD" in universe.currencies

    # ========================================================
    # CONTAINS
    # ========================================================

    assert universe.contains(

        "SPY"

    )

    assert not universe.contains(

        "QQQ"

    )

    # ========================================================
    # DATAFRAME
    # ========================================================

    df = universe.to_dataframe()

    assert df.shape[0] == 5

    assert "ticker" in df.columns

    assert "asset_class" in df.columns

    # ========================================================
    # METADATA
    # ========================================================

    metadata = universe.metadata

    assert metadata["version"] == "1.0.0"

    assert metadata["assets"] == 5

    # ========================================================
    # DUPLICATES
    # ========================================================

    try:

        universe.add_asset(

            Asset(

                ticker="SPY",

                name="Duplicate",

                asset_class="Equity",

                sector="Large Cap",

                country="USA",

                currency="USD",

                benchmark="SP500"

            )

        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ========================================================
    # REMOVE
    # ========================================================

    universe.remove_asset(

        "CASH"

    )

    assert universe.size == 4

    assert not universe.contains(

        "CASH"

    )

    # ========================================================
    # HEALTH
    # ========================================================

    assert universe.health_check()

    # ========================================================
    # SERIALIZATION
    # ========================================================

    exported = universe.to_dict()

    restored = AssetUniverse.from_dict(
        exported
    )

    assert restored.size == universe.size

    assert restored.tickers == universe.tickers

    # ========================================================
    # API FREEZE
    # ========================================================

    assert AssetUniverse.API_VERSION == "1.0.0"

    assert tuple(
        AssetUniverse.PUBLIC_METHODS
    ) == (

        "add_asset",

        "remove_asset",

        "get_asset",

        "tickers",

        "metadata"

    )
    
    # ========================================================
    # INVALID LOOKUP
    # ========================================================

    try:

        universe.get_asset(

            "UNKNOWN"

        )

        raise AssertionError(
            "Expected KeyError"
        )

    except KeyError:

        pass

    # ========================================================
    # INVALID REMOVE
    # ========================================================

    try:

        universe.remove_asset(

            "UNKNOWN"

        )

        raise AssertionError(
            "Expected KeyError"
        )

    except KeyError:

        pass

    print(
        "AssetUniverse tests passed."
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    test_asset_universe()