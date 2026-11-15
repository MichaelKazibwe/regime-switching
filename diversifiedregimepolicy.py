"""Research-only economic-regime allocation with group risk budgets and cash.

No production defaults are changed. This module does not authorize or route
orders. Macro inputs must be standardized, point-in-time signals supplied by
the caller. Capital weights are solved from covariance, not copied from firms.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
from sklearn.covariance import LedoitWolf

from assetuniverse import AssetUniverse, DIVERSIFIED_ASSETS, PRODUCTION_ASSETS
from tradingcalendar import TradingCalendar

DEFAULT_CONFIG = Path(__file__).resolve().parent / "research/diversified_regime_portfolio.json"
DEFAULT_ASSET_CATALOG = Path(__file__).resolve().parent / "research/company_asset_diversity.json"
GROUPS = ("equities", "government_bonds", "inflation_sensitive")


class AllocationError(ValueError):
    pass


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def aware(value):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is None:
        raise AllocationError("Observation and decision times must be timezone-aware")
    return stamp.tz_convert("UTC")


class DiversifiedRegimePolicy:
    def __init__(self, config_path=DEFAULT_CONFIG, *, asset_catalog_path=DEFAULT_ASSET_CATALOG):
        self.config = json.loads(Path(config_path).read_text())
        self.universe_profile = self.config.get("universe_profile", "production")
        if self.universe_profile not in {"production", "diversified_research"}:
            raise AllocationError("Unknown universe profile")
        self.universe = AssetUniverse.diversified() if self.universe_profile == "diversified_research" else AssetUniverse.production()
        self.assets = tuple(DIVERSIFIED_ASSETS if self.universe_profile == "diversified_research" else PRODUCTION_ASSETS)
        self._validate()
        self.asset_catalog_bytes = Path(asset_catalog_path).read_bytes()
        self.asset_catalog = json.loads(self.asset_catalog_bytes)
        self._validate_asset_catalog()

    def _validate_asset_catalog(self):
        catalog = self.asset_catalog
        if catalog.get("schema_version") != 1 or catalog.get("mode") != "RESEARCH_ONLY":
            raise AllocationError("Asset catalogue must remain research-only")
        known = set(PRODUCTION_ASSETS) | {"USD_CASH"}
        research_known = set(DIVERSIFIED_ASSETS) | {"USD_CASH"}
        identifiers = set()
        companies = set()
        for entry in catalog["exposures"]:
            if not entry["id"] or entry["id"] in identifiers:
                raise AllocationError("Asset catalogue exposure IDs must be unique")
            identifiers.add(entry["id"])
            companies.add(entry["company"])
            if entry["source"] not in catalog["sources"]:
                raise AllocationError("Asset catalogue requires a documented source")
            if (len(set(entry["canonical_proxies"])) != len(entry["canonical_proxies"])
                    or not set(entry["canonical_proxies"]) <= known):
                raise AllocationError("Asset catalogue cannot expand the canonical universe")
            if entry["mapping"] not in {"asset_class_proxy", "partial_proxy", "broad_equity_proxy", "missing"}:
                raise AllocationError("Unknown asset catalogue mapping")
            if (entry["mapping"] == "missing") != (not entry["canonical_proxies"]):
                raise AllocationError("Missing exposure mappings must have no canonical proxies")
            proxies = entry.get("research_proxies",entry["canonical_proxies"])
            mapping = entry.get("research_mapping",entry["mapping"])
            if (len(set(proxies)) != len(proxies) or not set(proxies) <= research_known
                    or mapping not in {"asset_class_proxy", "partial_proxy", "broad_equity_proxy", "sector_equity_proxy", "missing"}
                    or (mapping == "missing") != (not proxies)):
                raise AllocationError("Invalid expanded research exposure mapping")
        if companies != {"Bridgewater", "Berkshire Hathaway"}:
            raise AllocationError("Asset catalogue must cover both companies")
        for candidate in catalog["expansion_candidates"]:
            if (candidate["status"] != "WATCHLIST_ONLY" or candidate["symbol"] in known
                    or candidate["exposure_id"] not in identifiers or candidate["source"] not in catalog["sources"]):
                raise AllocationError("Expansion candidates must remain sourced watchlist entries")
        for extension in catalog.get("research_extensions",[]):
            if (extension["status"] != "RESEARCH_ENABLED" or extension["symbol"] not in set(DIVERSIFIED_ASSETS)-set(PRODUCTION_ASSETS)
                    or extension["source"] not in catalog["sources"]):
                raise AllocationError("Research extensions cannot grant production eligibility")

    def asset_diversity_coverage(self, capital_weights, cash_weight):
        """Describe proxy coverage without double-counting broad equity as sectors."""
        if (set(capital_weights) != set(self.assets)
                or any(not finite(value) or value < 0 for value in capital_weights.values())
                or not finite(cash_weight) or cash_weight < 0
                or not math.isclose(sum(capital_weights.values())+cash_weight,1,abs_tol=1e-10,rel_tol=0)):
            raise AllocationError("Coverage requires valid canonical capital weights and cash")
        weights = {**capital_weights, "USD_CASH":cash_weight}
        coverage = []
        for entry in self.asset_catalog["exposures"]:
            expanded = self.universe_profile == "diversified_research"
            proxies = entry.get("research_proxies",entry["canonical_proxies"]) if expanded else entry["canonical_proxies"]
            mapping = entry.get("research_mapping",entry["mapping"]) if expanded else entry["mapping"]
            allocated = [symbol for symbol in proxies if weights[symbol] > 0]
            coverage.append({"id":entry["id"], "company":entry["company"], "mapping":mapping,
                             "status":"missing" if not proxies else "allocated_proxy" if allocated else "available_unallocated",
                             "allocated_proxies":allocated})
        return coverage

    def _validate(self):
        c = self.config
        if c.get("schema_version") != 1 or c.get("mode") != "RESEARCH_ONLY" or c.get("capital_borrowing_allowed") is not False:
            raise AllocationError("Only the research-only, no-borrowing policy is supported")
        if c.get("currency") != "USD" or c.get("covariance_estimator") != "LedoitWolf":
            raise AllocationError("Only USD capital and LedoitWolf covariance are supported")
        for key in ("maximum_asset_weight", "risk_budget_tolerance"):
            if not finite(c[key]) or not 0 < c[key] <= 1:
                raise AllocationError(f"Invalid {key}")
        if c["risk_budget_tolerance"] > 1e-6:
            raise AllocationError("Risk budget tolerance must remain at least as strict as 1e-6")
        if (any(type(c[key]) is not int for key in ("minimum_return_observations", "covariance_lookback_sessions"))
                or c["minimum_return_observations"] < 252 or c["covariance_lookback_sessions"] < c["minimum_return_observations"]):
            raise AllocationError("At least 252 return observations are required")
        conditions = set()
        for profile in c["regimes"].values():
            pair = (profile["growth"], profile["inflation"])
            if pair in conditions or any(item not in {"rising", "falling"} for item in pair):
                raise AllocationError("Regime conditions must be unique rising/falling pairs")
            conditions.add(pair)
            if not finite(profile["minimum_cash"]) or not 0 <= profile["minimum_cash"] < 1:
                raise AllocationError("Invalid cash reserve")
            if not finite(profile["volatility_ceiling"]) or not 0 < profile["volatility_ceiling"] < 1:
                raise AllocationError("Invalid volatility ceiling")
            if set(profile["risk_budgets"]) != set(GROUPS) or set(profile["groups"]) != set(GROUPS):
                raise AllocationError("All three economic groups are required")
            budgets = profile["risk_budgets"].values()
            if any(not finite(value) or value <= 0 for value in budgets) or not math.isclose(sum(budgets), 1, abs_tol=1e-12):
                raise AllocationError("Group risk budgets must be positive and sum to one")
            seen = set()
            for group,weights in profile["groups"].items():
                if not weights or any(symbol not in self.assets or symbol in seen for symbol in weights):
                    raise AllocationError("Unknown or overlapping assets in groups")
                seen.update(weights)
                if any(not finite(weight) or weight < 0 for weight in weights.values()) or not math.isclose(sum(weights.values()), 1, abs_tol=1e-12):
                    raise AllocationError("Within-group capital weights must be nonnegative and sum to one")
                for symbol in weights:
                    asset = self.universe.get_asset(symbol)
                    nominal = asset.asset_class == "Bond" and asset.sector in {
                        "Long Duration Government", "Intermediate Government", "Short Duration Government",
                        "International Government", "Treasury Bills"}
                    inflation = asset.asset_class == "Commodity" or asset.sector == "Inflation Linked Government"
                    if not {"equities":asset.asset_class in {"Equity", "REIT"},
                            "government_bonds":nominal, "inflation_sensitive":inflation}[group]:
                        raise AllocationError(f"Asset {symbol} does not belong in economic group {group}")
        if conditions != {(g,i) for g in ("rising","falling") for i in ("rising","falling")}:
            raise AllocationError("All four economic conditions are required")
        s = c["stress"]
        if any(not finite(s[key]) for key in ("drawdown_entry", "drawdown_exit", "volatility_entry", "volatility_exit",
                                              "maximum_risky_exposure", "volatility_ceiling")):
            raise AllocationError("Stress thresholds must be finite numbers")
        if not (-1 < s["drawdown_entry"] < s["drawdown_exit"] <= 0 and 0 < s["volatility_exit"] < s["volatility_entry"]):
            raise AllocationError("Stress thresholds must provide valid hysteresis")
        if not 0 < s["maximum_risky_exposure"] <= .40 or not 0 < s["volatility_ceiling"] <= .05:
            raise AllocationError("Stress must preserve 40% exposure and 5% volatility ceilings")

    def classify(self, growth_signal, inflation_signal, *, decision_time, observations_available_at,
                 previous_regime=None, deadband=.1):
        if aware(observations_available_at) > aware(decision_time):
            raise AllocationError("Cannot use economic observations unavailable at the decision time")
        if not all(finite(value) for value in (growth_signal,inflation_signal,deadband)) or deadband < 0:
            raise AllocationError("Signals and deadband must be finite")
        if previous_regime is not None and previous_regime not in self.config["regimes"]:
            raise AllocationError("Unknown prior regime")
        previous = self.config["regimes"].get(previous_regime)

        def direction(value, axis):
            if value > deadband:
                return "rising"
            if value < -deadband:
                return "falling"
            if previous is None:
                raise AllocationError("Ambiguous signals require an established prior regime")
            return previous[axis]

        pair = (direction(growth_signal,"growth"),direction(inflation_signal,"inflation"))
        return next(name for name,profile in self.config["regimes"].items() if (profile["growth"],profile["inflation"]) == pair)

    def stress_state(self, drawdown, annualized_volatility, *, previous=False):
        if (not finite(drawdown) or not -1 <= drawdown <= 0 or not finite(annualized_volatility)
                or annualized_volatility < 0 or type(previous) is not bool):
            raise AllocationError("Invalid market stress observations")
        s = self.config["stress"]
        if previous:
            return not (drawdown > s["drawdown_exit"] and annualized_volatility < s["volatility_exit"])
        return drawdown <= s["drawdown_entry"] or annualized_volatility >= s["volatility_entry"]

    def allocate(self, regime, annual_covariance, *, decision_time, covariance_as_of, risk_off=False):
        if regime not in self.config["regimes"] or type(risk_off) is not bool:
            raise AllocationError("Unknown regime or invalid stress flag")
        if aware(covariance_as_of) > aware(decision_time):
            raise AllocationError("Covariance uses observations after the decision time")
        if (not isinstance(annual_covariance,pd.DataFrame) or tuple(annual_covariance.columns) != self.assets
                or tuple(annual_covariance.index) != self.assets):
            raise AllocationError("Covariance labels/order must match the canonical universe")
        covariance = annual_covariance.to_numpy(dtype=float)
        if (not np.isfinite(covariance).all() or not np.allclose(covariance,covariance.T,rtol=1e-10,atol=1e-12)
                or np.linalg.eigvalsh(covariance).min() < -1e-10):
            raise AllocationError("Covariance must be finite, symmetric and positive semidefinite")
        profile = self.config["regimes"][regime]
        matrix = np.array([[profile["groups"][group].get(symbol,0) for symbol in self.assets] for group in GROUPS])
        group_covariance = matrix @ covariance @ matrix.T
        if np.linalg.eigvalsh(group_covariance).min() <= 1e-12:
            raise AllocationError("Economic group covariance must be positive definite")
        budgets = np.array([profile["risk_budgets"][group] for group in GROUPS])
        normalized = group_covariance / np.trace(group_covariance)

        def objective(x):
            return .5 * x @ normalized @ x - np.dot(budgets,np.log(x))

        def gradient(x):
            return normalized @ x - budgets/x

        # Damped Newton solves the strictly convex positive risk-budget problem.
        # Positivity and an Armijo decrease are enforced at every step.
        x = np.sqrt(budgets/np.diag(normalized))
        for _ in range(100):
            grad = gradient(x)
            if np.max(np.abs(x*(normalized @ x)-budgets)) < 1e-11:
                break
            step = np.linalg.solve(normalized+np.diag(budgets/x**2),grad)
            rate = 1.0
            current = objective(x)
            for _ in range(60):
                candidate = x-rate*step
                if (candidate > 0).all() and objective(candidate) <= current-1e-4*rate*np.dot(grad,step)+1e-15:
                    x = candidate
                    break
                rate *= .5
            else:
                raise AllocationError("Group risk-budget line search did not converge")
        else:
            raise AllocationError("Group risk-budget solver did not converge")
        group_weights = x / x.sum()
        unit = group_weights @ matrix
        unit_variance = float(unit @ covariance @ unit)
        target = min(profile["volatility_ceiling"],self.config["stress"]["volatility_ceiling"]) if risk_off else profile["volatility_ceiling"]
        exposure_cap = min(1-profile["minimum_cash"],self.config["stress"]["maximum_risky_exposure"]) if risk_off else 1-profile["minimum_cash"]
        scale = min(exposure_cap,target/math.sqrt(unit_variance),self.config["maximum_asset_weight"]/float(unit.max()))
        weights = unit * scale
        variance = float(weights @ covariance @ weights)
        risk = weights * (covariance @ weights) / variance
        realized_group = (group_weights * (group_covariance @ group_weights)) / float(group_weights @ group_covariance @ group_weights)
        error = float(np.max(np.abs(realized_group-budgets)))
        if error > self.config["risk_budget_tolerance"]:
            raise AllocationError(f"Risk budget error {error} exceeds tolerance")
        return {"mode":"RESEARCH_ONLY","universe_profile":self.universe_profile,"regime":regime,"risk_off":risk_off,
                "capital_weights":{symbol:float(value) for symbol,value in zip(self.assets,weights)},
                "cash_weight":float(1-weights.sum()),"gross_asset_exposure":float(weights.sum()),
                "estimated_annual_volatility":math.sqrt(variance),"volatility_ceiling":target,
                "group_risk_targets":dict(zip(GROUPS,map(float,budgets))),
                "group_risk_shares":dict(zip(GROUPS,map(float,realized_group))),
                "asset_risk_shares":dict(zip(self.assets,map(float,risk))),"risk_budget_error":error,
                "asset_diversity_coverage":self.asset_diversity_coverage(dict(zip(self.assets,map(float,weights))),float(1-weights.sum())),
                "covariance_as_of":aware(covariance_as_of).isoformat(),"decision_time":aware(decision_time).isoformat(),
                "assumptions":["Cash has zero market-price variance in this model, not zero inflation or currency risk.",
                               "Volatility is estimated, not guaranteed. Capital weights are not risk-budget percentages."]}

    def estimate_covariance(self, prices, *, decision_time):
        if (not isinstance(prices,pd.DataFrame) or tuple(prices.columns) != self.assets
                or prices.empty or not isinstance(prices.index,pd.DatetimeIndex) or prices.index.hasnans
                or not prices.index.is_unique or not prices.index.is_monotonic_increasing):
            raise AllocationError("Prices must use ordered, unique dates and the canonical asset columns")
        if prices.index.tz is None:
            index = prices.index.tz_localize("America/New_York")
        else:
            index = prices.index.tz_convert("America/New_York")
        if (index != index.normalize()).any():
            raise AllocationError("Daily prices must be indexed by session date, not intraday time")
        expected = mcal.get_calendar("NYSE").schedule(start_date=index[0].date(),end_date=index[-1].date()).index
        if list(index.date) != list(expected.date):
            raise AllocationError("Price history must contain each NYSE session exactly once")
        latest = TradingCalendar().latest_completed_session(aware(decision_time))
        if latest is None or index[-1].date() != latest.tz_convert("America/New_York").date():
            raise AllocationError("Prices must end at the latest completed NYSE session")
        values = prices.to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values <= 0).any():
            raise AllocationError("Price history cannot contain missing, infinite or nonpositive observations")
        returns = prices.pct_change(fill_method=None).iloc[1:].tail(self.config["covariance_lookback_sessions"])
        if len(returns) < self.config["minimum_return_observations"]:
            raise AllocationError("Insufficient history for covariance estimation")
        model = LedoitWolf().fit(returns.to_numpy())
        covariance = pd.DataFrame(model.covariance_*252,index=self.assets,columns=self.assets)
        return covariance,{"as_of":latest.isoformat(),"observations":len(returns),"shrinkage":float(model.shrinkage_),"estimator":"LedoitWolf"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,default=DEFAULT_CONFIG)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--prices-csv",type=Path)
    source.add_argument("--fetch",action="store_true",help="Fetch public Yahoo adjusted daily history for research")
    parser.add_argument("--output",type=Path,default=Path("var/research/diversified-regime-expanded"))
    args = parser.parse_args()
    policy = DiversifiedRegimePolicy(args.config)
    now = datetime.now(timezone.utc)
    if args.fetch:
        import yfinance as yf

        frame = yf.download(list(policy.assets),period="5y",interval="1d",auto_adjust=True,
                            threads=4,progress=False,timeout=20)
        prices = frame["Close"].reindex(columns=policy.assets)
        latest = TradingCalendar().latest_completed_session(now)
        dates = prices.index.tz_localize(None) if prices.index.tz else prices.index
        prices = prices.loc[dates.date <= latest.tz_convert("America/New_York").date()]
    else:
        prices = pd.read_csv(args.prices_csv,index_col=0,parse_dates=True)
    covariance,metadata = policy.estimate_covariance(prices,decision_time=now)
    allocations = {regime:policy.allocate(regime,covariance,decision_time=now,covariance_as_of=metadata["as_of"])
                   for regime in policy.config["regimes"]}
    stressed = {regime:policy.allocate(regime,covariance,decision_time=now,covariance_as_of=metadata["as_of"],risk_off=True)
                for regime in policy.config["regimes"]}
    args.output.mkdir(parents=True,exist_ok=True)
    prices_path = args.output / "observed-prices.csv"
    prices.to_csv(prices_path)
    covariance.to_csv(args.output / "annual-covariance.csv")
    rows = [{"regime":name,"risk_off":stress,**allocation["capital_weights"],"USD_CASH":allocation["cash_weight"],
             "estimated_annual_volatility":allocation["estimated_annual_volatility"]}
            for stress,profiles in ((False,allocations),(True,stressed)) for name,allocation in profiles.items()]
    pd.DataFrame(rows).to_csv(args.output / "weights.csv",index=False)
    report = {"status":"RESEARCH_ONLY","universe_profile":policy.universe_profile,"assets":list(policy.assets),
              "generated_at":now.isoformat(),"covariance":metadata,
              "price_file_sha256":hashlib.sha256(prices_path.read_bytes()).hexdigest(),
              "configuration_sha256":hashlib.sha256(args.config.read_bytes()).hexdigest(),
              "asset_catalog_sha256":hashlib.sha256(policy.asset_catalog_bytes).hexdigest(),
              "asset_catalog":policy.asset_catalog,
              "allocations":allocations,"stress_allocations":stressed,
              "not_qualified":["No out-of-sample return acceptance yet.","No automatic macro signal feed or production activation."]}
    (args.output / "allocations.json").write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n")
    print(json.dumps({"status":"RESEARCH_ONLY","output":str(args.output / "allocations.json"),"observations":metadata["observations"]}))


if __name__ == "__main__":
    main()
