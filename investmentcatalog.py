"""Product instrument catalogue; eligibility is separate from trading authority."""

from dataclasses import asdict, dataclass

from assetuniverse import DIVERSIFIED_ASSETS, PRODUCTION_ASSETS


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

    @property
    def legacy_paper_eligible(self):
        return self.symbol in PRODUCTION_ASSETS


def catalogue():
    groups = {
        "equity": (
            "SPY",
            "VEA",
            "VWO",
            "QQQ",
            "IWM",
            "EWJ",
            "XLF",
            "XLP",
            "XLE",
            "XLU",
            "XLI",
            "KIE",
            "ITB",
            "XLY",
            "VNQ",
        ),
        "government": ("TLT", "IEF", "SHY", "IGOV", "TIP", "SGOV"),
        "credit": ("LQD", "HYG"),
        "real_assets": ("GLD", "SLV", "DBC"),
        "alternative": ("DBMF",),
        "composite": ("ALLW",),
    }
    instruments = {
        s: ProductInstrument(
            s,
            bucket,
            satellite=bucket == "equity" and s not in {"SPY", "VEA", "VWO"},
            benchmark_only=s == "ALLW",
        )
        for bucket, names in groups.items()
        for s in names
    }
    expected = set(DIVERSIFIED_ASSETS) | {"DBMF", "ALLW"}
    if set(instruments) != expected or len(instruments) != 28:
        raise ValueError("Product catalogue must account for all 28 instruments")
    return instruments


def catalogue_payload():
    return [
        dict(asdict(i), legacy_paper_eligible=i.legacy_paper_eligible)
        for i in catalogue().values()
    ]
