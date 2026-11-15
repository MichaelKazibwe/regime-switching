"""Recommendation trade-cost estimates; no broker order objects or submission."""

from dataclasses import dataclass
import math

from clientmandate import aware_time, finite


def self_financing_cost(current, target, cost_rate, sale_tax_rates):
    """Costs on dollars actually exchanged after fees, excluding base cash."""
    import numpy as np

    current = np.asarray(current, dtype=float)
    target = np.asarray(target, dtype=float)
    taxes = np.asarray(sale_tax_rates, dtype=float)
    fee = 0.0
    for _ in range(200):
        updated = float(
            cost_rate * np.abs(target[:-1] * (1 - fee) - current[:-1]).sum()
            + np.maximum(current - target * (1 - fee), 0) @ taxes
        )
        if not np.isfinite(updated) or updated < 0 or updated >= 1:
            raise ValueError("Costs exhaust portfolio capital")
        if abs(updated - fee) < 1e-12:
            return updated
        fee = updated
    raise ValueError("Self-financing costs did not converge")


@dataclass(frozen=True)
class MarketQuote:
    bid: float
    ask: float
    average_daily_value: float
    daily_volatility: float
    as_of: str
    currency: str
    source: str

    def estimate(
        self,
        notional,
        decision_time,
        *,
        participation_limit=0.01,
        commission_bps=5.0,
        fx_bps=0.0,
    ):
        for name in ("bid", "ask", "average_daily_value"):
            finite(getattr(self, name), name, 1e-12)
        finite(self.daily_volatility, "daily volatility", 0.0, 1.0)
        finite(notional, "notional", 0.0)
        finite(participation_limit, "participation limit", 1e-6, 0.10)
        finite(commission_bps, "commission", 0.0, 1000.0)
        finite(fx_bps, "FX cost", 0.0, 1000.0)
        if self.bid > self.ask or not self.source.strip() or len(self.currency) != 3:
            raise ValueError("Invalid executable quote")
        age = (aware_time(decision_time) - aware_time(self.as_of)).total_seconds()
        if not 0 <= age <= 60:
            raise ValueError("Stale or future executable quote")
        participation = notional / self.average_daily_value
        if participation > participation_limit:
            return {
                "status": "BLOCKED_CAPACITY",
                "participation": participation,
                "executable": False,
            }
        mid = (self.bid + self.ask) / 2
        half_spread = (self.ask - self.bid) / (2 * mid)
        impact = 0.1 * self.daily_volatility * math.sqrt(participation)
        fraction = commission_bps / 10000 + fx_bps / 10000 + half_spread + impact
        return {
            "status": "COST_ESTIMATE_ONLY",
            "cost": notional * fraction,
            "fraction": fraction,
            "participation": participation,
            "executable": False,
            "model": "UNVALIDATED_SQUARE_ROOT_IMPACT_WITH_OBSERVED_SPREAD",
        }


def conservative_sale_tax_fraction(lots, tax_rate):
    finite(tax_rate, "tax rate", 0.0, 1.0)
    if not lots:
        return 0.0
    costs = []
    for lot in lots:
        basis = finite(lot["basis"], "basis", 0.0)
        value = finite(lot["market_value"], "market value", 1e-12)
        costs.append(max(0.0, (value - basis) / value) * tax_rate)
    return max(costs)  # No assumed loss credits, wash-sale benefits or lot selection.
