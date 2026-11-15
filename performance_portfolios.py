"""Finite, isolated return/turnover/reserve and group-risk experiments."""

from copy import deepcopy
import numpy as np
import pandas as pd
from scipy.optimize import minimize

from compare_portfolio_models import rebalance_fee
from evaluate_institutional_engines import Replay
from institutional_return_engines import (
    GROUPS, CATALOGUE, SETTINGS, proposal, limits, validate_weights,
)
from institutionalportfolio import calibrated_covariance
from portfolio_risk_envelope import assess
from economic_design_assessment import replay, paired_interval
from growth_resilience import metrics

VARIANTS = {
    "incumbent": dict(band=0.04, partial=0.5, covariance="base", reserve=False, groups=False),
    "wide_band": dict(band=0.08, partial=0.5, covariance="base", reserve=False, groups=False),
    "patient_rebalance": dict(band=0.08, partial=0.25, covariance="base", reserve=False, groups=False),
    "observed_reserve": dict(band=0.04, partial=0.5, covariance="base", reserve=True, groups=False),
    "normal_covariance": dict(band=0.04, partial=0.5, covariance="normal", reserve=False, groups=False),
    "stress_covariance": dict(band=0.04, partial=0.5, covariance="stress", reserve=False, groups=False),
    "group_risk": dict(band=0.04, partial=0.5, covariance="stress", reserve=False, groups=True),
    "combined": dict(band=0.08, partial=0.25, covariance="stress", reserve=True, groups=True),
}
GROUP_RISK_CAPS = dict(equity=0.60, government=0.55, real_assets=0.45,
                       credit=0.15, alternative=0.25)


def risk_diagnostics(weights, covariance, symbols):
    w = np.asarray(weights, float)
    variance = float(w @ covariance @ w)
    rc = w * (covariance @ w) / variance if variance > 1e-15 else np.zeros(len(w))
    return dict(volatility=float(np.sqrt(max(0, variance))),
                asset_risk=dict(zip(symbols, map(float, rc))),
                signed_group_risk={g: float(sum(rc[i] for i, s in enumerate(symbols)
                                               if GROUPS[s] == g)) for g in GROUP_RISK_CAPS},
                positive_group_risk={g: float(sum(max(rc[i], 0) for i, s in enumerate(symbols)
                                                 if GROUPS[s] == g)) for g in GROUP_RISK_CAPS})


def summarize(frame):
    r = frame["return"].to_numpy()
    return dict(**metrics(np.cumprod(1 + r), r, frame.turnover.to_numpy()),
                mean_cash=float(frame.cash.mean()),
                cost_as_initial_capital=float(frame.cost_as_initial_capital.sum()
                                              / (frame.equity.iloc[0] / (1 + r[0]))),
                fills=int(frame.filled.sum()))


class Experiments:
    def __init__(self, prices, features):
        self.runner = Replay(prices, features)
        self.prices, self.daily = prices, self.runner.daily
        self.covariances, self.targets = {}, {}

    def covariances_at(self, i):
        ctx = self.runner.ctx(i)
        if i not in self.covariances:
            history = self.daily[ctx["symbols"]].iloc[i - 251:i + 1]
            stress = history.loc[history.SPY <= history.SPY.quantile(0.2)]
            self.covariances[i] = dict(
                base=ctx["cov"],
                normal=calibrated_covariance(history, stress, stress_weight=0.0)[0],
                stress=calibrated_covariance(history, stress, stress_weight=0.5)[0],
                observed=history.cov().to_numpy() * 252)
        return self.covariances[i]

    def valid(self, w, name, ctx, variant, covariances):
        cfg = VARIANTS[variant]
        if not validate_weights(w, name, ctx):
            return False
        if cfg["reserve"]:
            i = self.prices.index.get_loc(pd.Timestamp(ctx["decision_session"]))
            original = self.runner.target(i, name)
            base = np.array([original["weights"][s] for s in ctx["symbols"]])
            if float(w @ ctx["cov"] @ w) > float(base @ ctx["cov"] @ base) + 1e-10:
                return False
        if cfg["covariance"] != "base" and not validate_weights(
                w, name, {**ctx, "cov": covariances[cfg["covariance"]]}):
            return False
        if (cfg["reserve"] or cfg["covariance"] != "base" or cfg["groups"]) and not validate_weights(
                w, name, {**ctx, "cov": covariances["observed"]}):
            return False
        if cfg["groups"]:
            for covariance in covariances.values():
                diag = risk_diagnostics(w, covariance, ctx["symbols"])
                if any(diag["positive_group_risk"][g] > cap + 1e-7
                       for g, cap in GROUP_RISK_CAPS.items()):
                    return False
        return True

    def target(self, i, name, variant):
        key = (i, name, variant)
        if key in self.targets:
            return self.targets[key]
        ctx = self.runner.ctx(i)
        cfg = VARIANTS[variant]
        covariances = self.covariances_at(i)
        base = self.runner.target(i, name)
        if cfg["covariance"] == "base":
            result = deepcopy(base)
        else:
            result = proposal(name, {**ctx, "cov": covariances[cfg["covariance"]]})
        symbols = ctx["symbols"]
        if result["status"].startswith("BLOCKED"):
            self.targets[key] = dict(weights=dict.fromkeys(symbols, 0.0), cash=1.0,
                                     status="BLOCKED_RISK_CASH_ONLY", review=None,
                                     reserve_status="UPSTREAM_SOLVE_BLOCKED",
                                     execution_enabled=False, promotion_enabled=False)
            return self.targets[key]
        target = np.array([result["weights"][s] for s in symbols])
        reserve = ctx["reserve"]
        reserve_applied = bool(cfg["reserve"] and reserve == "SGOV")
        if reserve_applied:
            j = symbols.index(reserve)
            _, exposure = limits(name, ctx)
            target[j] += max(0, min(0.25 - target[j], exposure - target.sum()))
        if not self.valid(target, name, ctx, variant, covariances):
            ceiling, exposure = limits(name, ctx)
            group_caps = dict(equity=SETTINGS[name]["equity_cap"], government=0.55,
                              real_assets=0.35, credit=0.1, alternative=0.15)
            mask = {g: np.array([GROUPS[s] == g for s in symbols], float)
                    for g in group_caps}
            satellite = np.array([CATALOGUE[s].satellite for s in symbols], float)
            matrices = [ctx["cov"]]
            if cfg["covariance"] != "base":
                matrices.append(covariances[cfg["covariance"]])
            if cfg["reserve"] or cfg["covariance"] != "base" or cfg["groups"]:
                matrices.append(covariances["observed"])
            if cfg["groups"]:
                matrices += [covariances["normal"], covariances["stress"]]

            def residual(w):
                values = [exposure - w.sum(), 0.30 - satellite @ w]
                if cfg["reserve"]:
                    base_w = np.array([base["weights"][s] for s in symbols])
                    values.append(float(base_w @ ctx["cov"] @ base_w - w @ ctx["cov"] @ w))
                values.extend(cap - mask[g] @ w for g, cap in group_caps.items())
                for cov in matrices:
                    variance = float(w @ cov @ w)
                    contributions = w * (cov @ w)
                    values.append(ceiling**2 - variance)
                    values.extend(0.25 * variance - contributions)
                    if cfg["groups"]:
                        values.extend(cap * variance - mask[g] @ np.maximum(contributions, 0)
                                      for g, cap in GROUP_RISK_CAPS.items())
                return np.array(values)

            fit = minimize(lambda w: float(np.sum((w - target)**2 / (target + 0.02))),
                           target, method="SLSQP", bounds=[(0, 0.25)] * len(symbols),
                           constraints={"type": "ineq", "fun": residual},
                           options=dict(ftol=1e-12, maxiter=250))
            w = np.maximum(fit.x, 0)
            okay = bool(fit.success and self.valid(w, name, ctx, variant, covariances))
        else:
            w, okay = target, True
        # Independent observed-history checks are required for every new design.
        review = None
        if okay:
            review = assess(dict(zip(symbols, w)),
                            self.daily[symbols].iloc[i - 251:i + 1],
                            limits=dict(volatility=limits(name, ctx)[0], positive_euler=0.25))
            if cfg["reserve"] or cfg["covariance"] != "base" or cfg["groups"]:
                okay = review["status"] != "REJECT"
        if not okay:
            w = np.zeros(len(symbols))
        result = dict(weights=dict(zip(symbols, map(float, w))), cash=float(1 - w.sum()),
                      status="RESEARCH_RISK_PASS" if okay else "BLOCKED_RISK_CASH_ONLY",
                      reserve_status="OBSERVED_SGOV_ALLOCATION" if reserve_applied
                      else "NOT_REQUESTED_OR_NO_OBSERVED_SGOV",
                      review=review, execution_enabled=False, promotion_enabled=False)
        self.targets[key] = result
        return result

    def run(self, name, variant, start, end, *, cost=0.0015, selection=None):
        symbols = list(self.prices)
        w = np.zeros(len(symbols))
        nav = peak = 1.0
        rows, trades = [], []
        last_variant = None
        for i in range(start, end + 1):
            active_variant = selection[i] if selection else variant
            cfg = VARIANTS[active_variant]
            ctx = self.runner.ctx(i - 1)
            ids = [symbols.index(s) for s in ctx["symbols"]]
            c = w[ids]
            ceiling, exposure = limits(name, ctx)
            variance = float(c @ ctx["cov"] @ c)
            rc = c * (ctx["cov"] @ c) / variance if variance > 1e-15 else np.zeros(len(c))
            urgent = bool(w.sum() > exposure + 0.01 or w.max(initial=0) > 0.26
                          or variance > (ceiling * 1.10)**2 or rc.max(initial=0) > 0.30
                          or any(w[j] > 1e-12 for j, s in enumerate(symbols)
                                 if s not in ctx["symbols"]))
            # Tighter research group/stress limits also trigger risk-reduction trades.
            covs = self.covariances_at(i - 1)
            if cfg["groups"] or cfg["covariance"] != "base":
                urgent |= not self.valid(c, name, ctx, active_variant, covs)
            changed = last_variant is not None and active_variant != last_variant
            target, status = None, "NO_TRADE"
            if (i - start) % 21 == 0 or urgent or changed:
                result = self.target(i - 1, name, active_variant)
                status = result["status"]
                desired = np.array([result["weights"].get(s, 0) for s in symbols])
                if urgent or changed or i == start or abs(desired - w).sum() >= cfg["band"]:
                    target = desired
                    if not urgent and not changed and i > start:
                        partial = w + cfg["partial"] * (desired - w)
                        if self.valid(partial[ids], name, ctx, active_variant, covs):
                            target = partial
            observed = self.daily.iloc[i].to_numpy()
            held = w > 0
            if not np.isfinite(observed[held]).all() or (observed[held] <= -1).any():
                raise ValueError("Missing held price; no return imputation")
            old = nav
            gain = 1 + float(w[held] @ observed[held])
            if gain <= 0:
                raise ValueError("Insolvent research portfolio")
            w[held] *= (1 + observed[held]) / gain
            nav *= gain
            fee = turn = 0.0
            if target is not None:
                fee = rebalance_fee(w, target, cost)
                turn = float(abs(target * (1 - fee) - w).sum())
                nav *= 1 - fee
                w = target
                trades.append(dict(date=str(self.prices.index[i].date()),
                                   decision_session=ctx["decision_session"],
                                   variant=active_variant, urgent=urgent,
                                   weights=dict(zip(symbols, map(float, w))),
                                   status=status, fee_fraction=fee))
            peak = max(peak, nav)
            rows.append(dict(date=self.prices.index[i], equity=nav, **{"return": nav / old - 1},
                             cash=float(1 - w.sum()), turnover=turn, drawdown=nav / peak - 1,
                             cost_as_initial_capital=old * gain * fee, filled=target is not None,
                             macro_valid=ctx["macro_valid"], variant=active_variant,
                             target_status=status))
            last_variant = active_variant
        return pd.DataFrame(rows).set_index("date"), trades


def reconciliation(prices, frame, trades, cost):
    targets = {pd.Timestamp(t["date"]): t["weights"] for t in trades}
    independent = replay(prices.pct_change(fill_method=None).loc[frame.index], targets,
                         cost_rate=cost)
    for key in ("return", "equity", "cash", "turnover"):
        if not np.allclose(frame[key], independent[key], rtol=1e-9, atol=1e-10):
            raise ValueError("Independent replay mismatch: " + key)
    return dict(status="INDEPENDENTLY_RECONCILED", sessions=len(frame), fills=len(trades))


def objective(values):
    return values["cagr"] - 0.5 * values["annual_volatility"]**2 + 0.2 * values["maximum_drawdown"]


def cash_attribution(frame):
    result = {}
    for label, subset in (("macro_available", frame.loc[frame.macro_valid]),
                          ("macro_missing", frame.loc[~frame.macro_valid])):
        result[label] = dict(sessions=len(subset),
                             average_cash=float(subset.cash.mean()) if len(subset) else None,
                             net_return_sum=float(subset["return"].sum()),
                             cost_as_initial_capital=float(subset.cost_as_initial_capital.sum()))
    return dict(by_input_availability=result,
                interpretation="Conditional accounting attribution, not a causal estimate of missing-macro opportunity cost")


def paired(a, b):
    return paired_interval(a["return"], b["return"])
