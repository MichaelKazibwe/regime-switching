"""Registry-driven asset universes with separate research and execution eligibility.

AssetUniverse() is an empty configurable universe. diversified() resolves the
versioned global research registry; production() resolves only explicitly
qualified paper instruments. Neither factory imposes an instrument count or
ETF-only restriction. Legacy constant names remain compatibility APIs for the
registry-resolved vectors; historical reports carry their own frozen vectors.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict

from global_asset_registry import load_registry


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
# ORDERED ASSET PROFILES
# ======================================================================


# Registry membership and metadata are authoritative; no fixed ticker array.
_registry = load_registry()
DIVERSIFIED_ASSETS = _registry.symbols("research")
DIVERSIFIED_ASSET_COUNT = len(DIVERSIFIED_ASSETS)
DIVERSIFIED_ASSET_DEFINITIONS = tuple(_registry.instruments[s].asset_definition() for s in DIVERSIFIED_ASSETS)
PRODUCTION_ASSETS = list(_registry.symbols("paper"))
PRODUCTION_ASSET_TUPLE = tuple(PRODUCTION_ASSETS)
PRODUCTION_ASSET_COUNT = len(PRODUCTION_ASSETS)
PRODUCTION_ASSET_DEFINITIONS = tuple(_registry.instruments[s].asset_definition() for s in PRODUCTION_ASSETS)

if (len(set(DIVERSIFIED_ASSETS)) != DIVERSIFIED_ASSET_COUNT
        or tuple(item["ticker"] for item in DIVERSIFIED_ASSET_DEFINITIONS) != DIVERSIFIED_ASSETS):
    raise RuntimeError("Expanded asset list and metadata must match exactly in canonical order")


# ======================================================================
# SECTION 3
# PRODUCTION UNIVERSE VALIDATION
# ======================================================================


def _validate_production_definitions() -> None:
    """
    Validate the static canonical production universe.

    This executes at module import time so a malformed production
    universe cannot silently enter the dependency graph.
    """

    if len(PRODUCTION_ASSETS) != PRODUCTION_ASSET_COUNT or not PRODUCTION_ASSETS:

        raise RuntimeError(
            (
                "Canonical production universe must contain exactly "
                f"the registered qualified assets. Got {len(PRODUCTION_ASSETS)}."
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

    if len(definition_tickers) != PRODUCTION_ASSET_COUNT:

        raise RuntimeError(
            (
                "Canonical production asset definitions must contain "
                f"the registered {PRODUCTION_ASSET_COUNT} assets. Got {len(definition_tickers)}."
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

    for definition in PRODUCTION_ASSET_DEFINITIONS:

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

    for the canonical registry-qualified production universe.
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
        Construct the registry-qualified paper universe.
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

    @classmethod
    def diversified(cls) -> "AssetUniverse":
        """Build the expanded research universe without granting paper eligibility."""
        universe = cls()
        for definition in DIVERSIFIED_ASSET_DEFINITIONS:
            universe.add_asset(Asset(**definition))
        if universe.size != DIVERSIFIED_ASSET_COUNT or not universe.health_check():
            raise RuntimeError("Expanded research universe failed validation")
        return universe

    @staticmethod
    def product_menu():
        """Open registered recommendation menu, separate from paper authorization.

        Includes DBMF and the benchmark-only ALLW. Jurisdiction access and
        public recommendation qualification are assessed by the product service.
        """
        from investmentcatalog import catalogue_payload
        return catalogue_payload()

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
    # ADD ASSET
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
    # REMOVE ASSET
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
    # GET ASSET
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
    # SIZE
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
        registry-qualified production universe.
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
                    f"Asset has no field '{field}'."
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
    # EQUITIES
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

    # ==================================================================
    # BONDS
    # ==================================================================

    def bonds(
        self,
    ) -> list[Asset]:
        """
        Return bond assets.
        """

        return self.filter(
            asset_class="Bond"
        )

    # ==================================================================
    # COMMODITIES
    # ==================================================================

    def commodities(
        self,
    ) -> list[Asset]:
        """
        Return commodity assets.
        """

        return self.filter(
            asset_class="Commodity"
        )

    # ==================================================================
    # REITS
    # ==================================================================

    def reits(
        self,
    ) -> list[Asset]:
        """
        Return REIT assets.
        """

        return self.filter(
            asset_class="REIT"
        )

    # ==================================================================
    # CASH
    # ==================================================================

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
    # ACTIVE ASSETS
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

    # ==================================================================
    # INACTIVE ASSETS
    # ==================================================================

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
    # ASSET CLASSES
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

    # ==================================================================
    # SECTORS
    # ==================================================================

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

    # ==================================================================
    # COUNTRIES
    # ==================================================================

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

    # ==================================================================
    # CURRENCIES
    # ==================================================================

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

    # ==================================================================
    # BENCHMARKS
    # ==================================================================

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
    # CONTAINS
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
    # SERIALIZATION
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
    # DESERIALIZATION
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
    # DATAFRAME EXPORT
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
# MODULE REGRESSION TEST
# ======================================================================


def run_regression_tests() -> None:
    """
    Lightweight production-module regression certification.

    Full pytest coverage belongs in test_assetuniverse.py.
    """

    production = (
        AssetUniverse.production()
    )

    assert production.health_check()

    assert production.size == PRODUCTION_ASSET_COUNT

    assert (
        set(production.tickers)
        == set(PRODUCTION_ASSETS)
    )

    assert (
        production.is_production_universe
        is True
    )

    print(
        "============================================================"
    )

    print(
        "AssetUniverse regression certification: PASS"
    )

    print(
        f"Production asset count: {PRODUCTION_ASSET_COUNT}"
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
# SECTION 6
# MODULE ENTRY POINT
# ======================================================================


if __name__ == "__main__":

    run_regression_tests()
