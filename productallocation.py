"""Cost-aware mean/CVaR planning with strategic bands; never an order intent."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from sklearn.covariance import LedoitWolf

from investmentcatalog import catalogue
from productexecutioncost import self_financing_cost


POLICIES = {
    "preservation": {
        "cash": 0.70,
        "equity": (0.0, 0.0),
        "government": (0.90, 1.0),
        "credit": (0.0, 0.0),
        "real_assets": (0.0, 0.10),
        "alternative": (0.0, 0.0),
        "risk_aversion": 6.0,
    },
    "balanced": {
        "cash": 0.05,
        "equity": (0.35, 0.60),
        "government": (0.15, 0.40),
        "credit": (0.0, 0.10),
        "real_assets": (0.08, 0.25),
        "alternative": (0.0, 0.15),
        "risk_aversion": 3.0,
    },
    "growth": {
        "cash": 0.05,
        "equity": (0.55, 0.80),
        "government": (0.05, 0.25),
        "credit": (0.0, 0.10),
        "real_assets": (0.05, 0.20),
        "alternative": (0.0, 0.15),
        "risk_aversion": 2.0,
    },
}
# Conservative planning priors, not estimates certified for public advice.
PRIORS = {
    "equity": (0.06, 0.025),
    "government": (0.03, 0.015),
    "credit": (0.04, 0.025),
    "real_assets": (0.03, 0.025),
    "alternative": (0.04, 0.03),
}


@dataclass(frozen=True)
class PlanningCosts:
    commission: float = 0.0005
    half_spread: float = 0.001
    fx: float = 0.0
    market_impact: float = 0.0
    source: str = "ILLUSTRATIVE_NOT_EXECUTABLE"

    def total(self):
        values = np.array(
            [self.commission, self.half_spread, self.fx, self.market_impact]
        )
        if (
            not np.isfinite(values).all()
            or (values < 0).any()
            or (values > 0.05).any()
            or not self.source.strip()
        ):
            raise ValueError("Invalid planning costs")
        return float(values.sum())


def base_currency_prices(prices, currency, fx_to_base=None):
    cat = catalogue()
    native = {cat[s].listing_currency for s in prices}
    if isinstance(fx_to_base, pd.Series):
        if native != {"USD"} or currency == "USD":
            raise ValueError("A single FX series is only valid for USD listings converted to a foreign base")
        rates = {"USD": fx_to_base}
    elif fx_to_base is None:
        rates = {}
    elif isinstance(fx_to_base, dict):
        rates = fx_to_base
        if currency in rates:
            raise ValueError("Do not apply an extra FX conversion to base-currency prices")
    else:
        raise ValueError("Aligned historical base-currency units per listing currency required")
    if set(rates) != native - {currency}:
        raise ValueError("Aligned base-currency FX series must match the required listing currencies exactly")
    converted = prices.copy()
    for symbol in prices:
        item = cat[symbol]
        converted[symbol] = prices[symbol] * item.price_multiplier
        if item.listing_currency == currency:
            continue
        rate = rates.get(item.listing_currency)
        if (not isinstance(rate, pd.Series) or not rate.index.equals(prices.index)
                or not np.isfinite(rate).all() or (rate <= 0).any()):
            raise ValueError(f"Aligned historical base-currency units per {item.listing_currency} required")
        converted[symbol] *= rate
    return converted


def fx_source_hash(fx):
    if fx is None:
        return None
    if isinstance(fx, pd.Series):
        content = fx.to_csv()
    elif isinstance(fx, dict):
        content = pd.DataFrame({k: fx[k] for k in sorted(fx)}).to_csv()
    else:
        raise ValueError("FX must be an aligned series or currency mapping")
    return hashlib.sha256(content.encode()).hexdigest()


def read_fx_csv(path):
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    if all(isinstance(k, str) and len(k) == 3 and k.isalpha() and k.isupper() for k in frame):
        return {k: frame[k] for k in frame}
    if len(frame.columns) == 1:
        return frame.iloc[:, 0]
    raise ValueError("Multi-currency FX columns must use ISO currency codes")


def estimate_inputs(prices, mandate, cash_rate, decision_time, fx_to_base=None):
    if (
        not isinstance(prices, pd.DataFrame)
        or not isinstance(prices.index, pd.DatetimeIndex)
        or not prices.index.is_unique
        or not prices.index.is_monotonic_increasing
        or not prices.columns.is_unique
        or not set(prices) <= set(catalogue())
        or len(prices) < 253
    ):
        raise ValueError("Complete ordered product price history required")
    from clientmandate import aware_time

    if (
        prices.index.tz is not None
        or prices.index[-1].date() > aware_time(decision_time).date()
    ):
        raise ValueError("Naive session dates and no future prices required")
    if cash_rate.currency != mandate.base_currency:
        raise ValueError("Cash yield must match client base currency")
    converted = base_currency_prices(prices, mandate.base_currency, fx_to_base)
    eligible = []
    excluded = {}
    cat = catalogue()
    for s in prices:
        recent = converted[s].tail(253)
        if cat[s].benchmark_only:
            excluded[s] = "COMPOSITE_BENCHMARK_NOT_A_COMPONENT"
        elif len(recent) < 253 or not np.isfinite(recent).all() or (recent <= 0).any():
            excluded[s] = "INSUFFICIENT_COMPLETE_ACTUAL_PRICES"
        elif cat[s].bucket == "alternative" and not mandate.allow_alternatives:
            excluded[s] = "ALTERNATIVES_NOT_PERMITTED"
        elif cat[s].pricing_model not in {"adjusted_close", "total_return", "net_asset_value"}:
            excluded[s] = "RETURN_ACCOUNTING_ADAPTER_NOT_QUALIFIED"
        else:
            eligible.append(s)
    if not eligible:
        raise ValueError("No eligible price histories")
    first = max(converted[s].first_valid_index() for s in eligible)
    panel = converted.loc[first:, eligible].tail(1261)
    if not np.isfinite(panel.to_numpy()).all() or (panel <= 0).any().any():
        raise ValueError("Interior missing prices cannot be forward filled")
    r = panel.pct_change(fill_method=None).iloc[1:]
    values = r.to_numpy()
    if not np.isfinite(values).all() or (values <= -1).any():
        raise ValueError("Invalid asset returns")
    recent_values = values[-252:]
    from global_asset_registry import periods_per_year
    annual_sessions = periods_per_year(eligible, prices.index[-1])
    scale = recent_values.std(axis=0, ddof=0)
    if (scale <= 1e-10).any():
        raise ValueError("Unestimable zero-variance instrument")
    shrink = (
        LedoitWolf()
        .fit((recent_values - recent_values.mean(axis=0)) / scale)
        .covariance_
    )
    corr = shrink / np.sqrt(np.outer(np.diag(shrink), np.diag(shrink)))
    covariance = corr * np.outer(scale, scale) * annual_sessions
    observed = annual_sessions * np.clip(
        values, np.quantile(values, 0.01, axis=0), np.quantile(values, 0.99, axis=0)
    ).mean(axis=0)
    prior = np.array([PRIORS[cat[s].bucket][0] for s in eligible])
    uncertainty = np.array([PRIORS[cat[s].bucket][1] for s in eligible])
    # No fitted macro alpha in the product default: prior research failed its baseline.
    mu = 0.90 * prior + 0.10 * observed
    cash_daily = cash_rate.daily_rate(decision_time, annual_sessions)
    r["USD_CASH" if mandate.base_currency == "USD" else "BASE_CASH"] = cash_daily
    r.attrs["periods_per_year"] = annual_sessions
    mu = np.r_[mu, cash_rate.annual_effective_net_rate]
    uncertainty = np.r_[uncertainty, 0.0]
    matrix = np.zeros((len(mu), len(mu)))
    matrix[:-1, :-1] = covariance
    return r, mu, uncertainty, matrix, excluded


def stress_matrix(symbols, base_currency="USD"):
    cat = catalogue()
    result = []
    for scenario in ("growth_crash", "inflation_shock", "liquidity_shock"):
        values = []
        for s in symbols:
            if s.endswith("CASH"):
                values.append(0.0)
                continue
            bucket = cat[s].bucket
            shock = {
                "equity": -0.15,
                "government": 0.02,
                "credit": -0.10,
                "real_assets": -0.05,
                "alternative": -0.08,
            }[bucket]
            if scenario == "inflation_shock":
                shock = {
                    "equity": -0.10,
                    "government": -0.08,
                    "credit": -0.10,
                    "real_assets": 0.03,
                    "alternative": -0.06,
                }[bucket]
            if scenario == "liquidity_shock":
                shock = {
                    "equity": -0.20,
                    "government": -0.08,
                    "credit": -0.15,
                    "real_assets": -0.15,
                    "alternative": -0.12,
                }[bucket]
            if s == "SGOV":
                shock = -0.002
            if s == "SHY":
                shock = -0.015
            if s == "TIP":
                shock = -0.06 if scenario != "growth_crash" else -0.03
            values.append(shock)
        result.append(values)
    if base_currency != "USD":
        result.append([0.0 if s.endswith("CASH") else -0.10 for s in symbols])
    return np.array(result)


def strategic_target(symbols, profile, cash_floor, alternatives):
    groups = {
        "equity": {"SPY": 0.5, "VEA": 0.3, "VWO": 0.2},
        "government": {"SGOV": 0.3, "SHY": 0.2, "IEF": 0.4, "TLT": 0.1},
        "real_assets": {"TIP": 0.4, "GLD": 0.4, "DBC": 0.2},
        "alternative": {"DBMF": 1.0},
    }
    mix = {
        "preservation": {"government": 1.0},
        "balanced": {
            "equity": 0.48,
            "government": 0.30,
            "real_assets": 0.12,
            "alternative": 0.10,
        },
        "growth": {
            "equity": 0.68,
            "government": 0.12,
            "real_assets": 0.10,
            "alternative": 0.10,
        },
    }[profile].copy()
    if not alternatives or "DBMF" not in symbols:
        mix["government"] = mix.get("government", 0) + mix.pop("alternative", 0)
    target = np.zeros(len(symbols))
    target[-1] = cash_floor
    if cash_floor >= 1 - 1e-12:
        return target
    for group, fraction in mix.items():
        available = {s: v for s, v in groups[group].items() if s in symbols}
        if not available:
            raise ValueError(f"Strategic bucket unavailable: {group}")
        for s, v in available.items():
            target[symbols.index(s)] += (
                (1 - cash_floor) * fraction * v / sum(available.values())
            )
    return target


def allocate_plan(
    returns,
    mu,
    uncertainty,
    covariance,
    mandate,
    *,
    current=None,
    costs=PlanningCosts(),
    sell_tax_rates=None,
    exposure_multiplier=1.0,
    _cash_override=0.0,
    _stress_override=None,
    _depth=0,
):
    mandate.validate()
    symbols = list(returns)
    n = len(symbols)
    cat = catalogue()
    if (
        not symbols[-1].endswith("CASH")
        or not set(symbols[:-1]) <= set(cat)
        or any(cat[s].benchmark_only for s in symbols[:-1])
        or not returns.columns.is_unique
    ):
        raise ValueError("Invalid component universe")
    samples = returns.to_numpy(dtype=float)
    if len(samples) < 252 or not np.isfinite(samples).all() or (samples <= -1).any():
        raise ValueError("Complete scenarios required")
    mu = np.asarray(mu, dtype=float)
    uncertainty = np.asarray(uncertainty, dtype=float)
    covariance = np.asarray(covariance, dtype=float)
    if (
        mu.shape != (n,)
        or uncertainty.shape != (n,)
        or covariance.shape != (n, n)
        or not np.isfinite(mu).all()
        or not np.isfinite(uncertainty).all()
        or (uncertainty < 0).any()
        or not np.isfinite(covariance).all()
        or not np.allclose(covariance, covariance.T, atol=1e-12)
        or np.linalg.eigvalsh(covariance).min() < -1e-10
    ):
        raise ValueError("Invalid return/risk model inputs")
    w0 = np.zeros(n) if current is None else np.asarray(current, dtype=float)
    if current is None:
        w0[-1] = 1.0
    if (
        w0.shape != (n,)
        or not np.isfinite(w0).all()
        or (w0 < 0).any()
        or not np.isclose(w0.sum(), 1, atol=1e-12, rtol=0)
    ):
        raise ValueError("Current weights must reconcile")
    taxes = (
        np.zeros(n)
        if sell_tax_rates is None
        else np.asarray(sell_tax_rates, dtype=float)
    )
    if (
        taxes.shape != (n,)
        or not np.isfinite(taxes).all()
        or (taxes < 0).any()
        or (taxes > 1).any()
        or taxes[-1] != 0
    ):
        raise ValueError("Invalid conservative realized-gain tax costs")
    policy = POLICIES[mandate.profile]
    if not np.isfinite(exposure_multiplier) or not 0.1 <= exposure_multiplier <= 1:
        raise ValueError("Invalid risk exposure multiplier")
    floor = max(
        policy["cash"],
        1 - (1 - policy["cash"]) * exposure_multiplier,
        mandate.near_term_liquidity / mandate.account_value,
        _cash_override,
    )
    try:
        target = strategic_target(
            symbols, mandate.profile, floor, mandate.allow_alternatives
        )
    except ValueError as exc:
        return {
            "status": "BLOCKED_INFEASIBLE_MANDATE",
            "reason": str(exc),
            "weights": None,
            "executable": False,
        }
    m = len(samples)
    # x = weights, VaR threshold, tail slacks, tracking deviations, turnover, sales.
    eta = n
    tail = n + 1
    track = tail + m
    turn = track + n
    sales = turn + n
    size = sales + n
    objective = np.zeros(size)
    periods = returns.attrs.get("periods_per_year", 252)
    objective[:n] = -(mu - 0.5 * uncertainty) * max(1, round(periods / 12)) / periods
    objective[eta] = policy["risk_aversion"]
    objective[tail : tail + m] = policy["risk_aversion"] / (0.05 * m)
    objective[track : track + n] = 0.02
    objective[turn : turn + n] = costs.total()
    objective[turn + n - 1] = 0.0  # Cash transfers are not ETF trades.
    objective[sales : sales + n] = taxes
    constraints = []
    bounds_rhs = []

    def row(coeff, rhs):
        constraints.append(coeff)
        bounds_rhs.append(rhs)

    for j, values in enumerate(samples):
        a = np.zeros(size)
        a[:n] = -values
        a[eta] = -1
        a[tail + j] = -1
        row(a, 0.0)
    for j in range(n):
        for sign in (1.0, -1.0):
            a = np.zeros(size)
            a[j] = sign
            a[track + j] = -1
            row(a, sign * target[j])
            a = np.zeros(size)
            a[j] = sign
            a[turn + j] = -1
            row(a, sign * w0[j])
        a = np.zeros(size)
        a[j] = -1
        a[sales + j] = -1
        row(a, -w0[j])
    invest = 1 - floor
    for bucket in ("equity", "government", "credit", "real_assets", "alternative"):
        indices = [
            j
            for j, s in enumerate(symbols[:-1])
            if cat[s].bucket == bucket or bucket == "real_assets" and s == "TIP"
        ]
        # TIP belongs to government for credit-quality accounting but is included
        # only in the inflation/real-assets capital bucket for this mandate.
        if bucket == "government":
            indices = [j for j in indices if symbols[j] != "TIP"]
        lo, hi = policy[bucket]
        if bucket == "alternative" and not mandate.allow_alternatives:
            lo = hi = 0.0
        a = np.zeros(size)
        a[indices] = 1
        row(a, hi * invest)
        row(-a, -lo * invest)
    satellites = [j for j, s in enumerate(symbols[:-1]) if cat[s].satellite]
    a = np.zeros(size)
    a[satellites] = 1
    row(a, 0.10 * invest)
    if "HYG" in symbols:
        a = np.zeros(size)
        a[symbols.index("HYG")] = 1
        row(a, 0.05 * invest)
    shocks = stress_matrix(symbols, mandate.base_currency)
    loss_preference = mandate.financial_loss_capacity
    stress_budget = (
        min(loss_preference, _stress_override)
        if _stress_override is not None
        else loss_preference
    )
    for shock in shocks:
        a = np.zeros(size)
        a[:n] = -shock
        a[turn : turn + n - 1] = costs.total()
        a[sales : sales + n] = taxes
        row(a, stress_budget)
    eq = np.zeros((1, size))
    eq[0, :n] = 1
    variable_bounds = (
        [(0.0, 0.25) for _ in range(n - 1)]
        + [(floor, 1.0)]
        + [(None, None)]
        + [(0.0, None)] * (size - n - 1)
    )
    result = linprog(
        objective,
        A_ub=np.array(constraints),
        b_ub=np.array(bounds_rhs),
        A_eq=eq,
        b_eq=[1.0],
        bounds=variable_bounds,
        method="highs",
    )
    if not result.success:
        return {
            "status": "BLOCKED_INFEASIBLE_MANDATE",
            "reason": result.message,
            "weights": None,
            "executable": False,
        }
    w = result.x[:n]
    baseline_objective = np.zeros(size)
    baseline_objective[track : track + n] = 1.0
    baseline = linprog(
        baseline_objective,
        A_ub=np.array(constraints),
        b_ub=np.array(bounds_rhs),
        A_eq=eq,
        b_eq=[1.0],
        bounds=variable_bounds,
        method="highs",
    )
    if not baseline.success:
        raise ValueError("Feasible strategic reference could not be constructed")
    reference = baseline.x[:n]
    residual = max(
        float(np.max(np.array(constraints) @ result.x - np.array(bounds_rhs))),
        abs(w.sum() - 1),
    )
    if residual > 1e-6 or w.min() < -1e-9 or w[:-1].max() > 0.25 + 1e-6:
        raise ValueError("Optimizer reconciliation failed")
    for vector in (w, reference):
        vector[np.abs(vector) < 1e-12] = 0.0
        vector[-1] = 1 - float(vector[:-1].sum())
    variance = float(w @ covariance @ w)
    contributions = w * (covariance @ w) / variance if variance > 1e-15 else np.zeros(n)
    losses = -(samples @ w)
    tail_loss = float(np.sort(losses)[-int(np.ceil(0.05 * m)) :].mean())
    estimated_trade_cost = float(
        np.abs(w[:-1] - w0[:-1]).sum() * costs.total() + np.maximum(w0 - w, 0) @ taxes
    )
    # No-trade is considered only if existing weights satisfy all portfolio bands.
    existing_valid = w0[-1] >= floor - 1e-10 and w0[:-1].max() <= 0.25 + 1e-10
    for bucket in ("equity", "government", "credit", "real_assets", "alternative"):
        total = sum(
            w0[j]
            for j, s in enumerate(symbols[:-1])
            if (("real_assets" if s == "TIP" else cat[s].bucket) == bucket)
        )
        lo, hi = policy[bucket]
        if bucket == "alternative" and not mandate.allow_alternatives:
            lo = hi = 0.0
        existing_valid = (
            existing_valid and lo * invest - 1e-10 <= total <= hi * invest + 1e-10
        )
    existing_valid = (
        existing_valid and sum(w0[j] for j in satellites) <= 0.10 * invest + 1e-10
    )
    existing_valid = existing_valid and np.max(-shocks @ w0) <= loss_preference + 1e-10
    if "HYG" in symbols:
        existing_valid = (
            existing_valid and w0[symbols.index("HYG")] <= 0.05 * invest + 1e-10
        )
    hold = bool(existing_valid and np.abs(w - w0).sum() < 0.04)
    if hold:
        w = w0.copy()
        variance = float(w @ covariance @ w)
        contributions = (
            w * (covariance @ w) / variance if variance > 1e-15 else np.zeros(n)
        )
        losses = -(samples @ w)
        tail_loss = float(np.sort(losses)[-int(np.ceil(0.05 * m)) :].mean())
        estimated_trade_cost = 0.0
    try:
        estimated_trade_cost = self_financing_cost(w0, w, costs.total(), taxes)
        reference_cost = self_financing_cost(w0, reference, costs.total(), taxes)
    except ValueError as exc:
        return {
            "status": "BLOCKED_COST_RECONCILIATION",
            "weights": None,
            "executable": False,
            "reason": str(exc),
        }
    maximum_fee = max(estimated_trade_cost, reference_cost)
    required_cash = mandate.near_term_liquidity / (
        mandate.account_value * (1 - maximum_fee)
    )
    maximum_stress = max(
        float(
            np.max(estimated_trade_cost + (1 - estimated_trade_cost) * (-shocks @ w))
        ),
        float(np.max(reference_cost + (1 - reference_cost) * (-shocks @ reference))),
    )
    if (
        required_cash > min(w[-1], reference[-1]) + 1e-10
        or maximum_stress > loss_preference + 1e-8
    ):
        if _depth >= 8 or required_cash > 1 or maximum_fee > loss_preference:
            return {
                "status": "BLOCKED_COST_RECONCILIATION",
                "weights": None,
                "executable": False,
                "reason": "Cash needs and stress preferences cannot be reconciled after costs",
            }
        return allocate_plan(
            returns,
            mu,
            uncertainty,
            covariance,
            mandate,
            current=w0,
            costs=costs,
            sell_tax_rates=taxes,
            exposure_multiplier=exposure_multiplier,
            _cash_override=max(floor, required_cash + 1e-10),
            _stress_override=max(
                0.0,
                min(stress_budget, (loss_preference - maximum_fee) / (1 - maximum_fee)),
            ),
            _depth=_depth + 1,
        )
    return {
        "status": "PLANNING_PREVIEW",
        "executable": False,
        "risk_contract": "PRODUCT_CAPITAL_BANDS_V1_NOT_LEGACY_RISK_BUDGET_AUTHORIZATION",
        "weights": dict(zip(symbols, map(float, w))),
        "strategic_reference": dict(zip(symbols, map(float, reference))),
        "unconstrained_policy_anchor": dict(zip(symbols, map(float, target))),
        "variance_contributions": dict(zip(symbols, map(float, contributions))),
        "planning_expected_annual_return": float(w @ mu),
        "planning_annual_volatility": float(np.sqrt(max(variance, 0))),
        "historical_daily_es95": tail_loss,
        "expected_shortfall_is_loss_bound": False,
        "hypothetical_stress_losses": list(map(float, -shocks @ w)),
        "estimated_rebalance_cost_fraction": estimated_trade_cost,
        "strategic_reference_initial_cost_fraction": reference_cost,
        "hypothetical_stress_losses_including_costs": list(
            map(
                float, estimated_trade_cost + (1 - estimated_trade_cost) * (-shocks @ w)
            )
        ),
        "constraint_residual": residual,
        "recommendation_action": "HOLD" if hold else "REVIEW_REBALANCE",
        "no_trade_band_candidate": hold,
        "cash_floor": floor,
        "macro_alpha_enabled": False,
        "assumptions_status": "UNVALIDATED_PLANNING_PRIORS",
        "cost_source": costs.source,
        "optimizer": "LINEAR_MEAN_CVAR_TRACKING_TURNOVER_TAX_COST",
    }
