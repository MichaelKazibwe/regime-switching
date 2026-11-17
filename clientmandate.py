"""Explicit client planning constraints; no automatic jurisdiction approval."""

from dataclasses import dataclass
from datetime import datetime, timezone
import math


PROFILES = {"preservation", "balanced", "growth"}


def finite(value, name, minimum=0.0, maximum=float("inf")):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"Invalid {name}")
    return float(value)


def aware_time(value):
    stamp = (
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, str)
        else value
    )
    if not isinstance(stamp, datetime) or stamp.tzinfo is None:
        raise ValueError("Aware timestamp required")
    return stamp.astimezone(timezone.utc)


@dataclass(frozen=True)
class ClientMandate:
    client_id: str
    profile: str
    base_currency: str
    tax_residence: str
    jurisdiction: str
    horizon_years: float
    account_value: float
    financial_loss_capacity: float
    drawdown_preference: float
    target_total_return: float | None = None
    near_term_liquidity: float = 0.0
    investment_experience: str = "unspecified"
    allow_alternatives: bool = False
    tax_account_type: str = "unspecified"
    annual_platform_fee: float = 0.0

    def validate(self):
        if not self.client_id.strip() or self.profile not in PROFILES:
            raise ValueError("Known profile and client identifier required")
        if (
            len(self.base_currency) != 3
            or not self.base_currency.isalpha()
            or self.base_currency != self.base_currency.upper()
        ):
            raise ValueError("ISO-style base currency required")
        finite(self.horizon_years, "horizon", 0.01, 100)
        finite(self.account_value, "account value", 1.0)
        finite(self.financial_loss_capacity, "financial loss capacity", 0.0, 1.0)
        finite(self.drawdown_preference, "drawdown preference", 0.0, 1.0)
        finite(self.near_term_liquidity, "liquidity", 0.0, self.account_value)
        finite(self.annual_platform_fee, "annual platform fee", 0.0, 0.05)
        if self.target_total_return is not None:
            finite(self.target_total_return, "return target", 0.0, 100.0)
        if not isinstance(self.allow_alternatives, bool):
            raise ValueError("Alternative permission must be boolean")
        if self.tax_account_type not in {
            "unspecified",
            "taxable",
            "tax_deferred",
            "tax_exempt",
        }:
            raise ValueError("Invalid tax account type")
        return self

    def assessment(self):
        self.validate()
        reasons = []
        loss = self.financial_loss_capacity
        if loss <= 0.05 and self.profile != "preservation":
            reasons.append("LOW_LOSS_CAPACITY_REQUIRES_PRESERVATION_REVIEW")
        if self.horizon_years < 3 and self.profile == "growth":
            reasons.append("GROWTH_HORIZON_TOO_SHORT")
        if not self.jurisdiction.strip() or not self.tax_residence.strip():
            reasons.append("JURISDICTION_OR_TAX_RESIDENCE_MISSING")
        if self.investment_experience == "unspecified":
            reasons.append("INVESTMENT_EXPERIENCE_MISSING")
        if self.tax_account_type == "unspecified":
            reasons.append("TAX_ACCOUNT_TYPE_MISSING")
        # Removed owner return/drawdown targets; actual financial capacity remains a separate client constraint.
        annual = None
        return {
            "planning_reasons": reasons,
            "effective_loss_preference": loss,
            "fixed_return_target": None,
            "maximum_account_drawdown": None,
            "required_annual_return": annual,
            "loss_bound_guaranteed": False,
            "individualized_advice_authorized": False,
        }


@dataclass(frozen=True)
class CashRate:
    currency: str
    annual_effective_net_rate: float
    as_of: str
    source: str
    verified: bool = False

    def daily_rate(self, decision_time, periods_per_year=252):
        if not isinstance(self.verified, bool):
            raise ValueError("Cash source verification must be boolean")
        finite(self.annual_effective_net_rate, "cash rate", -0.20, 0.50)
        if not self.source.strip() or aware_time(self.as_of) > aware_time(
            decision_time
        ):
            raise ValueError("Invalid or future cash rate source")
        if (
            aware_time(decision_time) - aware_time(self.as_of)
        ).total_seconds() > 7 * 86400:
            raise ValueError("Cash rate is stale")
        if type(periods_per_year) is not int or not 1 <= periods_per_year <= 366:
            raise ValueError("Qualified annual valuation-session count required")
        return math.expm1(math.log1p(self.annual_effective_net_rate) / periods_per_year)
