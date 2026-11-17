"""Balanced research benchmark, frozen validation selection and cycle stress."""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from institutional_return_engines import GROUPS, CATALOGUE
from institutionalportfolio import calibrated_covariance
from fourregimestrategies import quadrant
from portfolio_contract import extended_prices
from portfolio_risk_envelope import assess
from economic_design_assessment import replay
from performance_portfolios import risk_diagnostics
from growth_resilience import metrics, WEIGHTS
from compare_portfolio_models import rebalance_fee
from strategy_report import load_training_report
from strategy_integrity import strict_json, file_hash, fingerprint
from strategy_receipts import atomic_json
from global_asset_registry import load_registry

BUDGETS = {
    "balanced": dict(equity=0.45, government=0.30, real_assets=0.15, credit=0.05, alternative=0.05),
    "defensive": dict(equity=0.35, government=0.40, real_assets=0.15, credit=0.05, alternative=0.05),
    "inflation_diversified": dict(equity=0.35, government=0.25, real_assets=0.30, credit=0.05, alternative=0.05),
}
CAPS = dict(equity=0.60, government=0.55, real_assets=0.35, credit=0.10, alternative=0.15)
GUARDS = {"none": None, "moderate": [0.05, 0.10], "wide": [0.08, 0.15]}
REGIMES = ("disinflationary_growth", "inflationary_growth", "stagflation", "deflationary_slowdown")


def allocate(history, budget, volatility):
    symbols = list(history)
    market = history.SPY if "SPY" in history else history.mean(axis=1)
    stressed = history.loc[market <= market.quantile(0.2)].dropna()
    cov, _ = calibrated_covariance(history.tail(252), stressed.tail(252), stress_weight=0.25)
    stress, _ = calibrated_covariance(history.tail(252), stressed.tail(252), stress_weight=0.50)
    raw = history.tail(252).cov().to_numpy() * 252
    masks = {g: np.array([GROUPS[s] == g for s in symbols], float) for g in CAPS}
    inverse = 1 / np.sqrt(np.diag(cov))
    target = np.zeros(len(symbols))
    for g, share in budget.items():
        ids = masks[g] > 0
        if ids.any():
            target[ids] = share * inverse[ids] / inverse[ids].sum()
    target *= min(0.95 / target.sum(), volatility / np.sqrt(target @ cov @ target))
    satellite = np.array([CATALOGUE[s].satellite for s in symbols], float)

    def residual(w):
        values = [0.95 - w.sum(), 0.30 - satellite @ w]
        values.extend(cap - masks[g] @ w for g, cap in CAPS.items())
        for matrix in (cov, stress, raw):
            variance = float(w @ matrix @ w)
            values.append(volatility**2 - variance)
            values.extend(0.25 * variance - w * (matrix @ w))
        return np.array(values)

    def objective(w):
        variance = float(w @ cov @ w)
        rc = w * (cov @ w) / max(variance, 1e-15)
        return float(sum((masks[g] @ rc - budget[g])**2 for g in CAPS)
                     + 0.02 * np.sum((w - target)**2 / (target + 0.02)))

    fit = minimize(objective, target, method="SLSQP", bounds=[(0, 0.25)] * len(symbols),
                   constraints={"type": "ineq", "fun": residual},
                   options=dict(ftol=1e-12, maxiter=500))
    w = np.maximum(fit.x, 0)
    checks = assess(dict(zip(symbols, w)), history.tail(252),
                    limits=dict(volatility=volatility, positive_euler=0.25))
    if (not fit.success or residual(w).min() < -1e-8 or w.sum() < 0.01
            or checks["status"] == "REJECT"):
        raise ValueError("Benchmark risk problem did not produce a verified feasible allocation")
    diag = risk_diagnostics(w, cov, symbols)
    return dict(weights=dict(zip(symbols, map(float, w))), cash=float(1 - w.sum()),
                forecast_volatility=diag["volatility"], risk_shares=diag["asset_risk"],
                group_risk=diag["signed_group_risk"],
                stress_risk=risk_diagnostics(w, stress, symbols), independent_risk=checks)


def account(returns, weights, *, guard=None, cost=0.0015):
    symbols = list(returns)
    base = np.array([weights.get(s, 0) for s in symbols])
    w, nav, peak, factor = np.zeros(len(symbols)), 1.0, 1.0, 1.0
    rows, targets = [], {}
    for i, (date, observed) in enumerate(returns.iterrows()):
        prior_dd = nav / peak - 1
        requested = 1.0
        if guard:
            soft, full = guard
            requested = float(np.clip((full + prior_dd) / (full - soft), 0.25, 1))
        target = None
        if i % 21 == 0 or requested < factor - 0.05:
            target = base * requested
            factor = requested
            targets[date] = dict(zip(symbols, map(float, target)))
        r = observed.to_numpy()
        held = w > 0
        if not np.isfinite(r[held]).all() or (r[held] <= -1).any():
            raise ValueError("Missing held benchmark price")
        old = nav
        gain = 1 + float(w[held] @ r[held])
        w[held] *= (1 + r[held]) / gain
        fee = turn = 0.0
        if target is not None:
            fee = rebalance_fee(w, target, cost)
            turn = float(abs(target * (1 - fee) - w).sum())
            w = target
        nav *= gain * (1 - fee)
        peak = max(peak, nav)
        rows.append(dict(date=date, equity=nav, **{"return": nav / old - 1},
                         cash=float(1 - w.sum()), turnover=turn, drawdown=nav / peak - 1))
    frame = pd.DataFrame(rows).set_index("date")
    other = replay(returns, targets, cost_rate=cost)
    if not all(np.allclose(frame[k], other[k], rtol=1e-9, atol=1e-10)
               for k in ("equity", "return", "cash", "turnover")):
        raise ValueError("Benchmark independent accounting reconciliation failed")
    return frame, metrics(frame.equity.to_numpy(), frame["return"].to_numpy(), frame.turnover.to_numpy())


def simulate(blocks, transition, weights, guard, sequence, *, paths=500, seed=141126):
    rng = np.random.default_rng(seed)
    required = range(4) if sequence is None else set(sequence)
    if any(not len(blocks[k]) for k in required):
        return dict(status="UNAVAILABLE", reason="At least one cycle lacks complete observed historical blocks")
    symbols = len(weights)
    data = np.empty((paths, 252, symbols))
    state = rng.choice(4, size=paths)
    for quarter in range(4):
        if sequence is not None:
            state[:] = sequence[quarter]
        elif quarter:
            state = np.array([rng.choice(4, p=transition[s]) for s in state])
        for k in range(4):
            ids = np.flatnonzero(state == k)
            if not len(ids):
                continue
            choices = rng.integers(0, len(blocks[k]), size=(len(ids), 3))
            data[ids, quarter*63:(quarter+1)*63] = blocks[k][choices].reshape(len(ids), 63, symbols)
    w = np.zeros((paths, symbols))
    nav = peak = np.ones(paths)
    maximum_dd = np.zeros(paths)
    factor = np.ones(paths)
    fans = [[1.0], [1.0], [1.0]]
    for day in range(252):
        prior_dd = nav / peak - 1
        requested = np.ones(paths) if guard is None else np.clip((guard[1] + prior_dd) / (guard[1] - guard[0]), .25, 1)
        trade = np.ones(paths, bool) if day % 21 == 0 else requested < factor - .05
        target = requested[:, None] * weights
        gain = 1 + np.sum(w * data[:, day], axis=1)
        w *= (1 + data[:, day]) / gain[:, None]
        nav = nav * gain
        if trade.any():
            a, b = w[trade], target[trade]
            lo, hi = np.zeros(trade.sum()), np.full(trade.sum(), .01)
            for _ in range(35):
                fee = (lo + hi) / 2
                residual = .0015 * np.abs(b * (1 - fee[:, None]) - a).sum(axis=1) - fee
                lo = np.where(residual > 0, fee, lo)
                hi = np.where(residual > 0, hi, fee)
            nav[trade] *= 1 - (lo + hi) / 2
            w[trade] = b
            factor[trade] = requested[trade]
        peak = np.maximum(peak, nav)
        maximum_dd = np.minimum(maximum_dd, nav / peak - 1)
        for j, value in enumerate(np.quantile(nav, [.05, .5, .95])):
            fans[j].append(float(value))
    return dict(status="SIMULATED", paths=paths, fan=fans,
                median_return=float(np.median(nav) - 1), p05_return=float(np.quantile(nav, .05) - 1),
                p95_return=float(np.quantile(nav, .95) - 1),
                p95_drawdown=float(np.quantile(-maximum_dd, .95)),
                probability_loss_10pct=float(np.mean(nav < .9)))


def run(bundle, output):
    bundle, root = Path(bundle).resolve(), Path(output).resolve()
    b = strict_json(bundle)
    report = load_training_report(b["training_report"])
    if not report["current_numerical_source_match"]:
        raise ValueError("Source-matched completed training required")
    prices = extended_prices(b["capture"], b["benchmark_extension"])
    prices = prices[[s for s in prices if s in CATALOGUE and CATALOGUE[s].research_enabled and not CATALOGUE[s].benchmark_only]]
    daily = prices.pct_change(fill_method=None)
    train_end, validation_end = len(prices) - 504, len(prices) - 252
    training = daily.iloc[train_end - 1260:train_end]
    eligible = [s for s in training if np.isfinite(training[s].tail(252)).all()]
    training = training[eligible]
    features = {r["date"]: r for r in strict_json(Path(b["training_report"]).parent / "features.json")}
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    sources = {p: file_hash(p) for p in ["cycle_benchmark.py", "institutionalportfolio.py",
                                       "institutional_return_engines.py", "portfolio_risk_envelope.py",
                                       "economic_design_assessment.py", "growth_resilience.py",
                                       "fourregimestrategies.py", "performance_portfolios.py",
                                       "global_asset_registry.py", "global_market_panel.py",
                                       "research/global_asset_registry.json"]}
    protocol = dict(universe_contract=load_registry().payload(), objective="Validation CAGR - 0.5 annual variance + 0.5 max drawdown - daily ES95",
                    budgets=BUDGETS, volatility_grid=[.06, .08, .10], drawdown_overlays=GUARDS,
                    guard_floor=.25, guard_reentry="Monthly only; prior-close drawdown",
                    capital_caps=CAPS, maximum_asset=.25, minimum_cash=.05,
                    train_end=str(prices.index[train_end-1].date()),
                    validation_end=str(prices.index[validation_end-1].date()),
                    test_start=str(prices.index[validation_end].date()),
                    cost_bps=15, source_hashes=sources, bundle_sha256=file_hash(bundle),
                    selection_uses_test=False, no_drawdown_guarantee=True,
                    limitation="Finite retrospective candidates; not a global optimum or untouched prospective validation")
    atomic_json(root / "protocol.json", protocol)
    trials = []
    for budget_name, budget in BUDGETS.items():
        for vol in protocol["volatility_grid"]:
            try:
                allocation = allocate(training, budget, vol)
            except ValueError:
                trials.append(dict(name=f"{budget_name}-{vol}", status="INFEASIBLE_RISK_SOLVE"))
                continue
            for guard_name, guard in GUARDS.items():
                name = f"{budget_name}-{vol}-{guard_name}"
                _, validation = account(daily.iloc[train_end:validation_end][eligible], allocation["weights"], guard=guard)
                score = (validation["cagr"] - .5 * validation["annual_volatility"]**2
                         + .5 * validation["maximum_drawdown"] - validation["daily_expected_shortfall95"])
                trials.append(dict(name=name, status="VALIDATED", budget=budget_name, volatility=vol,
                                   guard=guard_name, allocation=allocation, validation=validation, objective=score))
    feasible = [r for r in trials if r["status"] == "VALIDATED"]
    if not feasible:
        raise ValueError("No feasible benchmark design")
    selected = max(feasible, key=lambda row: row["objective"])
    test_frame, test = account(daily.iloc[validation_end:][eligible], selected["allocation"]["weights"],
                               guard=GUARDS[selected["guard"]])
    test_frame.to_csv(root / "held-out-test.csv")
    _, doubled_cost = account(daily.iloc[validation_end:][eligible], selected["allocation"]["weights"],
                               guard=GUARDS[selected["guard"]], cost=.003)
    references = {}
    for name, weights in {"balanced_60_40": {"SPY": .6, "IEF": .4}, "growth_resilience": WEIGHTS,
                          "all_weather_proxy": dict(SPY=.3, TLT=.4, IEF=.15, GLD=.075, DBC=.075)}.items():
        _, value = account(daily.iloc[validation_end:][eligible], weights)
        references[name] = value
    current = daily[eligible].tail(1260)
    latest = allocate(current, BUDGETS[selected["budget"]], selected["volatility"])
    blocks = [[] for _ in range(4)]
    for i in range(1, len(training) - 21, 21):
        prior = features.get(str(training.index[i-1].date()), {})
        values = training.iloc[i:i+21].to_numpy()
        if prior.get("macro_valid", False) and np.isfinite(values).all():
            state = quadrant(prior)
            blocks[state].append(values)
    transition = np.ones((4, 4))
    transitions = 0
    for i in range(1, len(training) - 63, 63):
        before = features.get(str(training.index[i-1].date()), {})
        after = features.get(str(training.index[i+62].date()), {})
        if before.get("macro_valid", False) and after.get("macro_valid", False):
            transition[quadrant(before), quadrant(after)] += 1
            transitions += 1
    transition /= transition.sum(axis=1, keepdims=True)
    arrays = [np.array(values) for values in blocks]
    sequences = {name: [i]*4 for i, name in enumerate(REGIMES)}
    sequences.update(inflation_shock_then_stagflation=[0, 1, 2, 2],
                     recession_then_recovery=[2, 3, 3, 0],
                     full_cycle_switches=[0, 1, 2, 3], historical_markov_switches=None)
    weight_vector = np.array([latest["weights"][s] for s in eligible])
    scenarios = {name: simulate(arrays, transition, weight_vector, GUARDS[selected["guard"]], seq)
                 for name, seq in sequences.items()}
    shocks = {}
    for name, rates in {"growth_recession": dict(equity=-.20, government=.06, real_assets=-.10, credit=-.10, alternative=.02),
                         "inflation_rates_shock": dict(equity=-.10, government=-.12, real_assets=.12, credit=-.10, alternative=.03),
                         "liquidity_and_correlation": dict(equity=-.25, government=-.06, real_assets=-.18, credit=-.15, alternative=-.08)}.items():
        pnl = sum(w * (0 if s == "SGOV" else rates[GROUPS[s]]) for s, w in latest["weights"].items())
        shocks[name] = dict(hypothetical_return_before_tax=pnl, basis="Declared instantaneous asset-group shock; cash/SGOV flat")
    if any(file_hash(p) != h for p, h in sources.items()):
        raise ValueError("Benchmark sources changed during evaluation")
    result = dict(status="RESEARCH_BENCHMARK", benchmark_id=fingerprint(dict(protocol=protocol, selected=selected["name"], latest=latest)),
                  created_at=datetime.now(timezone.utc).isoformat(), market_session=report["market_session"],
                  protocol=protocol, selected=selected, trials=trials, test=test, doubled_cost_test=doubled_cost,
                  references=references, latest=latest, scenarios=scenarios, shocks=shocks,
                  conditional_blocks={REGIMES[i]: len(blocks[i]) for i in range(4)},
                  transition_matrix=transition.tolist(),
                  transition_horizon_sessions=63, observed_training_transitions=transitions,
                  scenario_basis="Joint observed 21-session blocks from training-only history; prescribed and smoothed historical regime switches; not calibrated predictions",
                  current_allocation_performance="Latest refit differs from frozen held-out allocation; no retrospective performance claim for current weights",
                  reconciliation=dict(status="INDEPENDENTLY_RECONCILED", sessions=len(test_frame)),
                  source_hashes=sources, execution_enabled=False, promotion_enabled=False)
    atomic_json(root / "benchmark.json", result)
    atomic_json(root.parent / "latest.json", dict(benchmark=str(root / "benchmark.json"), sha256=file_hash(root / "benchmark.json")))
    print("Cycle benchmark:", root / "benchmark.json", flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bundle = args.bundle or Path(strict_json("var/dashboard-live/latest.json")["bundle"])
    run(bundle, args.output)
