"""Product instrument catalogue; eligibility is separate from trading authority."""

from dataclasses import asdict, dataclass

from assetuniverse import PRODUCTION_ASSETS
from global_asset_registry import load_registry


@dataclass(frozen=True)
class ProductInstrument:
    symbol: str
    bucket: str
    satellite: bool = False
    benchmark_only: bool = False
    listing_currency: str = "USD"
    verified_domicile: str | None = None
    # No jurisdiction is automatically declared suitable or legally approved.
    approved_jurisdictions: tuple[str, ...] = ()
    asset_type: str = "etf"
    venue: str = "XNYS"
    calendar: str = "NYSE"
    region: str = "unknown"
    quote_unit: str = "USD"
    price_multiplier: float = 1.0
    pricing_model: str = "adjusted_close"
    research_enabled: bool = True
    name: str = ""

    @property
    def legacy_paper_eligible(self):
        return self.symbol in PRODUCTION_ASSETS


def catalogue():
    registry = load_registry()
    return {s: ProductInstrument(symbol=s, bucket=i.bucket, satellite=i.satellite,
                benchmark_only=i.benchmark_only, listing_currency=i.listing_currency,
                asset_type=i.asset_type, venue=i.venue, calendar=i.calendar, region=i.region,
                quote_unit=i.quote_unit, price_multiplier=i.price_multiplier,
                pricing_model=i.pricing_model, research_enabled=i.research_enabled, name=i.name)
            for s in registry.symbols("product") for i in [registry.instruments[s]]}


def catalogue_payload():
    return [
        dict(asdict(i), legacy_paper_eligible=i.legacy_paper_eligible)
        for i in catalogue().values()
    ]
