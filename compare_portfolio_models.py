"""Exploratory allocator comparison, printed to the terminal; never places orders.

Historical macro vintages are unavailable. Price-derived indicators are explicit
test inputs, not historical economic regimes or a full production backtest.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
from sklearn.covariance import LedoitWolf

from assetuniverse import DIVERSIFIED_ASSETS, PRODUCTION_ASSETS
from core_constants import REGIME_MAX_LEVERAGE, REGIME_RISK_BUDGETS, REGIME_VOL_TARGETS
from diversifiedregimepolicy import DiversifiedRegimePolicy, DEFAULT_CONFIG
from productioncomposition import ProductionComposition


def rebalance_fee(current, target, cost_rate):
    """Solve costs on actual ETF dollars traded, allowing buys and sells."""
    fee = 0.0
    for _ in range(100):
        updated = cost_rate*float(np.abs(target*(1-fee)-current).sum())
        if abs(updated-fee) < 1e-14:
            return updated
        fee = updated
    raise ValueError("Transaction-cost accounting did not converge")


def simulate(returns, targets, *, cost_rate, cash_returns):
    """Targets keyed by execution close; accrue old holdings before that fill."""
    weights = np.zeros(returns.shape[1])
    cash = 1.0
    nav = 1.0
    rows = []
    for date, asset_returns in returns.iterrows():
        dollars = weights*(1+asset_returns.to_numpy())
        cash_dollars = cash*(1+float(cash_returns.loc[date]))
        growth = float(dollars.sum()+cash_dollars)
        weights = dollars/growth
        cash = cash_dollars/growth
        fee = turnover = 0.0
        if date in targets:
            target = targets[date]
            if (not np.isfinite(target).all() or target.min() < 0 or target.sum() > 1+1e-10):
                raise ValueError("Invalid simulated target weights")
            fee = rebalance_fee(weights,target,cost_rate)
            turnover = float(np.abs(target*(1-fee)-weights).sum())
            weights = target.copy()
            cash = float(1-weights.sum())
        daily_return = growth*(1-fee)-1
        cost_dollars = nav*growth*fee
        nav *= 1+daily_return
        assert abs(weights.sum()+cash-1) < 1e-10
        rows.append({"date":date,"return":daily_return,"equity":nav,"cash":cash,
                     "turnover":turnover,"cost_as_initial_capital":cost_dollars})
    return pd.DataFrame(rows).set_index("date")


def metrics(frame, risk_free):
    r = frame["return"]
    years = len(r)/252
    equity = frame.equity.to_numpy()
    peak = np.maximum.accumulate(np.r_[1.0,equity])[1:]
    excess = r-risk_free
    vol = float(r.std(ddof=1)*np.sqrt(252))
    excess_vol = float(excess.std(ddof=1)*np.sqrt(252))
    return {"total_return":float(equity[-1]-1),"cagr":float(equity[-1]**(1/years)-1),
            "volatility":vol,"sharpe_over_sgov":float(excess.mean()*252/excess_vol) if excess_vol else None,
            "max_drawdown":float(np.min(equity/peak-1)),"mean_cash":float(frame.cash.mean()),
            "annual_traded_notional":float(frame.turnover.sum()/years),
            "cost_pct_initial_capital":float(frame.cost_as_initial_capital.sum()),
            "final_value_1m":float(equity[-1]*1_000_000)}


def build_targets(prices, policy, *, include_diversified=True):
    assets = list(DIVERSIFIED_ASSETS if include_diversified else PRODUCTION_ASSETS)
    columns = {s:i for i,s in enumerate(assets)}
    names=("14 production allocator*","14 equal weight","SPY buy and hold")
    if include_diversified:
        names+=("26 diversified allocator*","26 equal weight")
    targets = {name:{} for name in names}
    components = ProductionComposition().build_components()
    closes = mcal.get_calendar("NYSE").schedule(prices.index[0].date(),prices.index[-1].date())["market_close"]
    if list(prices.index.date) != list(closes.index.date):
        raise ValueError("Expected a complete NYSE daily price history")
    audit = []
    previous = None
    stress = False
    for i in range(252,len(prices)-1,21):
        history = prices.iloc[:i+1]
        daily = history.pct_change(fill_method=None).iloc[1:]
        lookback = daily.tail(policy.config["covariance_lookback_sessions"])
        spy = history.SPY
        growth = float((spy.iloc[-1]/spy.iloc[-64]-1)/(daily.SPY.tail(63).std()*np.sqrt(63)))
        spread = daily.DBC-daily.IEF
        inflation = float(((history.DBC.iloc[-1]/history.DBC.iloc[-64]-1)
                           -(history.IEF.iloc[-1]/history.IEF.iloc[-64]-1))/(spread.tail(63).std()*np.sqrt(63)))
        stamp = closes.iloc[i]
        # Initial ambiguous observations remain all-cash, without an invented label.
        try:
            regime = policy.classify(growth,inflation,decision_time=stamp,observations_available_at=stamp,
                                     previous_regime=previous)
        except ValueError as exc:
            if "Ambiguous" not in str(exc):
                raise
            audit.append({"decision_date":str(history.index[-1].date()),"reason":str(exc),"skipped":True})
            continue
        previous = regime
        stress = policy.stress_state(float(spy.iloc[-1]/spy.tail(252).max()-1),
                                     float(daily.SPY.tail(20).std()*np.sqrt(252)),previous=stress)
        production_regime = "crisis" if stress else "bull" if policy.config["regimes"][regime]["growth"] == "rising" else "neutral"
        execution_date = prices.index[i+1]
        record = {"decision_date":str(history.index[-1].date()),"execution_date":str(execution_date.date()),
                  "training_last_date":str(lookback.index[-1].date()),"training_observations":len(lookback),
                  "price_proxy_regime":regime,"production_proxy_regime":production_regime,"stress":stress,
                  "growth_market_indicator":growth,"inflation_market_indicator":inflation}
        if include_diversified:
            annual_cov = pd.DataFrame(LedoitWolf().fit(lookback[assets].to_numpy()).covariance_*252,index=assets,columns=assets)
            a = policy.allocate(regime,annual_cov,decision_time=stamp,covariance_as_of=stamp,risk_off=stress)
            targets["26 diversified allocator*"][execution_date] = np.array([a["capital_weights"][s] for s in assets])
            record.update({"26_weights":a["capital_weights"],"26_cash":a["cash_weight"],"26_budget_error":a["risk_budget_error"]})
        # Production optimizer consumes DAILY covariance; the research allocator
        # consumes ANNUAL covariance. Never pass annual units into production.
        daily_cov = LedoitWolf().fit(lookback[PRODUCTION_ASSETS].to_numpy()).covariance_
        try:
            result = components.optimizer.optimize(covariance=daily_cov,regime=production_regime,
                                                   asset_order=PRODUCTION_ASSETS,prices=history[PRODUCTION_ASSETS])
            w = np.asarray(result["weights"],dtype=float)
            variance = float(w@daily_cov@w)
            if not np.isfinite(variance) or variance <= 0:
                raise ValueError("Nonpositive or invalid production portfolio variance")
            shares = w*(daily_cov@w)/variance
            budgets = np.array([REGIME_RISK_BUDGETS[production_regime][s] for s in PRODUCTION_ASSETS])
            error = float(np.max(np.abs(shares-budgets)))
            record["14_budget_error"] = error
            if (not np.isfinite(w).all() or not np.isfinite(shares).all() or not np.isfinite(error)
                    or w.min() < 0 or w.max() > components.constraints.MAX_WEIGHT+1e-10
                    or w.sum() > REGIME_MAX_LEVERAGE[production_regime]+1e-10
                    or np.sqrt(variance*252) > REGIME_VOL_TARGETS[production_regime]+1e-8 or error > 1e-6):
                raise ValueError(f"Strict final allocation constraints failed; budget error={error:.8g}")
            full = np.zeros(len(assets))
            for s,value in zip(PRODUCTION_ASSETS,w):
                full[columns[s]] = value
            targets["14 production allocator*"][execution_date] = full
            record.update({"14_accepted":True,"14_weights":dict(zip(PRODUCTION_ASSETS,map(float,w)))})
        except Exception as exc:
            # No bypass or forced liquidation: retain prior positions on rejection.
            record.update({"14_accepted":False,"14_rejection":f"{type(exc).__name__}: {exc}"})
        benchmarks=[(PRODUCTION_ASSETS,"14 equal weight")]
        if include_diversified:
            benchmarks.append((assets,"26 equal weight"))
        for symbols,name in benchmarks:
            full = np.zeros(len(assets))
            for s in symbols:
                full[columns[s]] = 1/len(symbols)
            targets[name][execution_date] = full
        if not targets["SPY buy and hold"]:
            full = np.zeros(len(assets))
            full[columns["SPY"]] = 1
            targets["SPY buy and hold"][execution_date] = full
        audit.append(record)
    return targets,audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prices",type=Path,default=Path("var/research/diversified-regime-expanded/observed-prices.csv"))
    parser.add_argument("--output",type=Path,default=Path("var/research/model-comparison"))
    args = parser.parse_args()
    prices = pd.read_csv(args.prices,index_col=0,parse_dates=True)
    if (tuple(prices.columns) != DIVERSIFIED_ASSETS or not prices.index.is_monotonic_increasing
            or not prices.index.is_unique or not np.isfinite(prices.to_numpy()).all() or (prices<=0).any().any()):
        raise ValueError("Complete, positive, ordered prices for the declared registry universe are required")
    split = int(len(prices)*.8)
    development = prices.iloc[:split].copy()
    if len(development) < 505:
        raise ValueError("Insufficient development history after the 20% reserve")
    policy = DiversifiedRegimePolicy()
    targets,audit = build_targets(development,policy)
    returns = development.pct_change(fill_method=None).iloc[253:]
    args.output.mkdir(parents=True,exist_ok=True)
    all_metrics=[]
    curves={}
    for cash_mode in ("ZERO_CASH_RETURN","SGOV_RETURN_PROXY"):
        cash_returns = returns.SGOV if cash_mode == "SGOV_RETURN_PROXY" else pd.Series(0.0,index=returns.index)
        for cost in (.0015,.0030):
            for name,model_targets in targets.items():
                frame = simulate(returns,model_targets,cost_rate=cost,cash_returns=cash_returns)
                row = {"model":name,"cash_assumption":cash_mode,"cost_bps":cost*10000,**metrics(frame,returns.SGOV)}
                all_metrics.append(row)
                curves[f"{name}|{cash_mode}|{cost}"] = frame
    table = pd.DataFrame(all_metrics)
    table.to_csv(args.output/'metrics.csv',index=False)
    pd.concat(curves,names=['experiment','date']).to_csv(args.output/'daily-results.csv')
    (args.output/'decision-audit.json').write_text(json.dumps(audit,indent=2,allow_nan=False)+'\n')
    metadata = {"status":"EXPLORATORY_PRICE_PROXY_ALLOCATOR_COMPARISON","orders_submitted":0,
                "prices_sha256":hashlib.sha256(args.prices.read_bytes()).hexdigest(),
                "configuration_sha256":hashlib.sha256(DEFAULT_CONFIG.read_bytes()).hexdigest(),
                "source_sha256":{name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in (
                    "compare_portfolio_models.py","assetuniverse.py","core_constants.py","constraints.py",
                    "diversifiedregimepolicy.py","productioncomposition.py","portfoliooptimizer.py",
                    "riskbudgetengine.py","volatilitytargeting.py","expectedreturnforecaster.py","blacklitterman.py")},
                "scored_start":str(returns.index[0].date()),"scored_end":str(returns.index[-1].date()),
                "reserved_start":str(prices.index[split].date()),"reserved_end":str(prices.index[-1].date()),
                "warmup_returns":252,"rebalance_sessions":21,"maximum_covariance_returns":756,
                "signals":"63-session SPY trend and DBC-minus-IEF relative performance, standardized using past volatility; deadband 0.1",
                "stress":"SPY trailing-252-session drawdown and 20-session volatility, using configured hysteresis",
                "execution":"Decision after close, fill at next session adjusted close after old holdings accrue that session return",
                "production_filter":"Actual production optimizer; final weights checked for exact 1e-6 budgets, position/exposure/volatility caps; rejected proposals retain previous holdings",
                "limitations":["Not the complete production pipeline, macro classifier or execution authorization replay.",
                               "No historical macro vintages; price signals are not economic growth/inflation observations.",
                               "Adjusted closes are research fill proxies, not executable historical quotes.",
                               "Research parameters were chosen after some of these dates; no pristine out-of-sample claim.",
                               "Most recent 20% excluded from return scoring; previously used in covariance snapshot research.",
                               "SGOV carry sensitivity uses ETF total returns, not actual broker cash interest.",
                               "Known covariance-shrinkage sensitivity is retained; no strategy tuning in this comparison."]}
    (args.output/'methodology.json').write_text(json.dumps(metadata,indent=2)+'\n')
    lines = ["="*114,"QUALIFIED PAPER ALLOCATOR vs REGISTRY RESEARCH ALLOCATOR", "EXPLORATORY PRICE-SIGNAL COMPARISON — NOT A FULL PRODUCTION STRATEGY BACKTEST",'='*114,
             f"Scored: {metadata['scored_start']} to {metadata['scored_end']} | {len(returns)} sessions | initial capital $1,000,000",
             f"Excluded from return scoring: {metadata['reserved_start']} to {metadata['reserved_end']} (final 20%)",
             "252-return warmup; rolling covariance <=756 returns; rebalance every 21 sessions; next-session-close fills.",
             "Risk budgets and strategy limits unchanged. No orders submitted. Sharpe uses daily SGOV excess returns."]
    for cash_mode in ("ZERO_CASH_RETURN","SGOV_RETURN_PROXY"):
        lines += ['',f"CASH ASSUMPTION: {cash_mode} | commission+slippage: 15 bps per dollar of ETF trading"]
        selected=table[(table.cash_assumption==cash_mode)&(table.cost_bps==15)]
        display=selected[['model','total_return','cagr','volatility','sharpe_over_sgov','max_drawdown','mean_cash','final_value_1m']].copy()
        for col in ['total_return','cagr','volatility','max_drawdown','mean_cash']:
            display[col]=display[col].map(lambda v:f'{100*v:.2f}%')
        display.sharpe_over_sgov=display.sharpe_over_sgov.map(lambda v:f'{v:.3f}')
        display.final_value_1m=display.final_value_1m.map(lambda v:f'${v:,.0f}')
        lines.append(display.to_string(index=False))
    lines += ['',"DOUBLED-COST SENSITIVITY: CAGR at 30 bps (zero cash return)"]
    selected=table[(table.cash_assumption=='ZERO_CASH_RETURN')&(table.cost_bps==30)]
    lines += [f"  {row.model:30s} {row.cagr:8.2%}" for row in selected.itertuples()]
    lines += ['',"TRADING ACTIVITY: base 15 bps, zero cash return (buy + sell notional)"]
    selected=table[(table.cash_assumption=='ZERO_CASH_RETURN')&(table.cost_bps==15)]
    lines += [f"  {row.model:30s} annual traded {row.annual_traded_notional:7.2%}; total costs {row.cost_pct_initial_capital:6.2%} of initial capital" for row in selected.itertuples()]
    records=[a for a in audit if not a.get('skipped')]
    accepted=sum(a['14_accepted'] for a in records)
    lines += ['',f"Production allocator proposals: {len(records)}; strict-filter accepted: {accepted}; rejected: {len(records)-accepted}.",
              "Rejected proposals place no trades and retain existing positions; retained weights can drift outside a later regime's limits.",
              f"Price-derived regimes: {dict(Counter(a['price_proxy_regime'] for a in records))}",
              "* Allocators use proxy market signals. Complete macro-driven production-model performance is NOT established.",
              "Equal-weight benchmarks help separate universe effects from differences in allocation and risk limits.",
              "Known SGOV covariance distortion remains. This run is exploratory, not deployment qualification.",
              f"Detailed metrics, daily returns, decision audit and methodology: {args.output}"]
    terminal='\n'.join(lines)+'\n'
    (args.output/'terminal-results.txt').write_text(terminal)
    print(terminal)


if __name__ == '__main__':
    main()
