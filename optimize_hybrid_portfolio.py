"""Chronological hybrid research using the two existing allocation modules.

No orders, no production activation and no scoring of the final 20% of dates.
Previously inspected development dates are not a pristine out-of-sample test.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

from assetuniverse import DIVERSIFIED_ASSETS
from compare_portfolio_models import build_targets, metrics, rebalance_fee, simulate
from diversifiedregimepolicy import DiversifiedRegimePolicy
from hybridportfoliopolicy import DEFAULT_HYBRID_CONFIG, HybridPortfolioPolicy, scale_preserving_covariance


def parameter_grid(policy):
    grid=policy.config['candidate_grid']
    return [dict(zip(grid,values)) for values in itertools.product(*grid.values())]


def market_states(prices, audit, hybrid):
    records={pd.Timestamp(a['decision_date']):a for a in audit if not a.get('skipped')}
    states={}
    parent=None
    stress=False
    control=DiversifiedRegimePolicy()
    closes=mcal.get_calendar('NYSE').schedule(prices.index[0].date(),prices.index[-1].date()).market_close
    daily=prices.pct_change(fill_method=None).iloc[1:]
    for i in range(252,len(prices)-1):
        date=prices.index[i]
        if date in records:
            parent=records[date]
            if parent['26_budget_error'] > 1e-6 or (parent['14_accepted'] and parent['14_budget_error'] > 1e-6):
                raise ValueError('Unvalidated parent allocation')
        if parent is None:
            continue
        spy=prices.SPY.iloc[:i+1]
        history=daily.loc[:date]
        stress=control.stress_state(float(spy.iloc[-1]/spy.tail(252).max()-1),
                                    float(history.SPY.tail(20).std()*np.sqrt(252)),previous=stress)
        uptrend=bool(spy.iloc[-1]>=spy.tail(hybrid.config['trend_window']).mean()
                     and parent['price_proxy_regime'] in {'disinflationary_growth','inflationary_growth'})
        cov=scale_preserving_covariance(history.tail(hybrid.config['covariance_window']))
        states[date]={'covariance':cov,'uptrend':uptrend,'stress':stress,'decision_time':closes.iloc[i],
                      'sources_available_at':closes.loc[pd.Timestamp(parent['decision_date'])],
                      'parent14':parent.get('14_weights') if parent['14_accepted'] else None,
                      'parent26':parent['26_weights']}
    return states


def hybrid_simulation(prices, states, policy, parameter_schedule, *, cost_rate, cash_proxy=False):
    returns=prices.pct_change(fill_method=None).iloc[253:]
    weights=np.zeros(len(DIVERSIFIED_ASSETS))
    cash=nav=1.0
    rows=[]
    decisions=[]
    pending=None
    first_decision=prices.index[252]

    def decision(date):
        if date not in states:
            return None
        state=states[date]
        return policy.allocate(state['parent14'],state['parent26'],state['covariance'],parameter_schedule(date),
                               uptrend=state['uptrend'],stress=state['stress'],decision_time=state['decision_time'],
                               sources_available_at=state['sources_available_at'],covariance_as_of=state['decision_time'])

    pending=decision(first_decision)
    previous_date=first_decision
    for date,r in returns.iterrows():
        dollars=weights*(1+r.to_numpy())
        cash_dollars=cash*(1+float(r.SGOV) if cash_proxy else 1)
        growth=float(dollars.sum()+cash_dollars)
        weights=dollars/growth
        cash=cash_dollars/growth
        fee=turnover=0.0
        if pending is not None:
            target=pending['weights']
            cov=states[previous_date]['covariance'].to_numpy()
            breach=(weights.sum()>pending['exposure_ceiling']+1e-10
                    or weights.max()>policy.config['maximum_asset_weight']+1e-10
                    or np.sqrt(weights@cov@weights)>pending['volatility_ceiling']+1e-10)
            if breach or np.abs(target-weights).sum() >= policy.config['minimum_trade_notional']:
                fee=rebalance_fee(weights,target,cost_rate)
                turnover=float(np.abs(target*(1-fee)-weights).sum())
                weights=target.copy()
                cash=float(1-weights.sum())
                decisions.append({'decision_date':str(previous_date.date()),'execution_date':str(date.date()),
                                  'parameters':parameter_schedule(previous_date),'cash':cash,
                                  'stress':pending['stress'],'uptrend':pending['uptrend'],
                                  'parent14_fraction':pending['parent14_fraction'],
                                  'estimated_volatility':pending['estimated_volatility'],
                                  'weights':dict(zip(DIVERSIFIED_ASSETS,map(float,weights)))})
        cost=nav*growth*fee
        net=growth*(1-fee)-1
        nav*=1+net
        assert abs(weights.sum()+cash-1)<1e-10
        rows.append({'date':date,'return':net,'equity':nav,'cash':cash,'turnover':turnover,'cost_as_initial_capital':cost})
        pending=decision(date)
        previous_date=date
    return pd.DataFrame(rows).set_index('date'),decisions


def rebased(frame):
    frame=frame.copy()
    initial=float(frame.equity.iloc[0]/(1+frame['return'].iloc[0]))
    frame.equity/=initial
    frame.cost_as_initial_capital/=initial
    return frame


def select_parameters(candidate_frames, candidates, policy):
    """Each selection sees only its prior training window, including that close."""
    dates=next(iter(candidate_frames.values())).index
    training=policy.config['training_sessions']
    interval=policy.config['selection_interval_sessions']
    selections=[]
    trials=[]
    for boundary in range(training,len(dates),interval):
        training_dates=dates[boundary-training:boundary]
        scores=[]
        for index,candidate in enumerate(candidates):
            frame=rebased(candidate_frames[index].loc[training_dates])
            result=metrics(frame,pd.Series(0.0,index=frame.index))
            feasible=abs(result['max_drawdown'])<=policy.config['selection_drawdown_limit']
            score=result['cagr'] if feasible else result['cagr']-2*abs(result['max_drawdown'])
            row={'candidate':index,'training_start':str(training_dates[0].date()),
                 'training_end':str(training_dates[-1].date()),'evaluation_start':str(dates[boundary].date()),
                 'parameters':candidate,'feasible':feasible,'score':score,**result}
            scores.append(row)
            trials.append(row)
        eligible=[row for row in scores if row['feasible']] or scores
        winner=max(eligible,key=lambda row:(row['score'],-row['annual_traded_notional'],-row['candidate']))
        selections.append(winner)
    return selections,trials


def selected_schedule(date, selections, candidates):
    available=[s for s in selections if pd.Timestamp(s['training_end'])<=date]
    return available[-1]['parameters'] if available else candidates[0]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prices',type=Path,default=Path('var/research/diversified-regime-expanded/observed-prices.csv'))
    parser.add_argument('--output',type=Path,default=Path('var/research/hybrid-optimization'))
    args=parser.parse_args()
    prices=pd.read_csv(args.prices,index_col=0,parse_dates=True)
    if (tuple(prices.columns)!=DIVERSIFIED_ASSETS or not prices.index.is_unique or not prices.index.is_monotonic_increasing
            or not np.isfinite(prices.to_numpy()).all() or (prices<=0).any().any()):
        raise ValueError('Complete canonical adjusted daily prices are required')
    split=int(.8*len(prices))
    development=prices.iloc[:split].copy()
    policy=HybridPortfolioPolicy()
    candidates=parameter_grid(policy)
    if len(development)<253+policy.config['training_sessions']+126:
        raise ValueError('Insufficient chronological research data')
    print(f'Building parent proposals and daily risk inputs; {len(candidates)} predeclared candidates.',flush=True)
    targets,audit=build_targets(development,DiversifiedRegimePolicy())
    states=market_states(development,audit,policy)
    bank={}
    for i,parameters in enumerate(candidates):
        bank[i],_=hybrid_simulation(development,states,policy,lambda date,p=parameters:p,cost_rate=.003)
    selections,trials=select_parameters(bank,candidates,policy)
    def schedule(date):
        return selected_schedule(date,selections,candidates)
    evaluation_start=pd.Timestamp(selections[0]['evaluation_start'])
    all_returns=development.pct_change(fill_method=None).iloc[253:]
    rows=[]
    curves={}
    chosen_decisions=[]
    for carry in (False,True):
        cash_returns=all_returns.SGOV if carry else pd.Series(0.0,index=all_returns.index)
        for cost in (.0015,.003):
            frame,decisions=hybrid_simulation(development,states,policy,schedule,cost_rate=cost,cash_proxy=carry)
            models={'Chronologically selected hybrid':frame}
            for name in ('14 production allocator*','26 diversified allocator*','SPY buy and hold'):
                models[name]=simulate(all_returns,targets[name],cost_rate=cost,cash_returns=cash_returns)
            for name,full in models.items():
                evaluated=rebased(full.loc[evaluation_start:])
                rows.append({'model':name,'cash_proxy':carry,'cost_bps':cost*10000,**metrics(evaluated,all_returns.SGOV.loc[evaluation_start:])})
                curves[f'{name}|cash={carry}|cost={cost}']=evaluated
            if not carry and cost==.0015:
                chosen_decisions=decisions
    table=pd.DataFrame(rows)
    args.output.mkdir(parents=True,exist_ok=True)
    table.to_csv(args.output/'comparison.csv',index=False)
    pd.concat(curves,names=['experiment','date']).to_csv(args.output/'daily-results.csv')
    (args.output/'parameter-trials.json').write_text(json.dumps(trials,indent=2,allow_nan=False)+'\n')
    (args.output/'selections.json').write_text(json.dumps(selections,indent=2,allow_nan=False)+'\n')
    (args.output/'hybrid-decisions.json').write_text(json.dumps(chosen_decisions,indent=2,allow_nan=False)+'\n')
    (args.output/'parent-proposals.json').write_text(json.dumps(audit,indent=2,allow_nan=False)+'\n')
    metadata={'status':'EXPLORATORY_RESEARCH_ONLY','production_activation':False,'orders_submitted':0,
              'candidate_count':len(candidates),'evaluation_start':str(evaluation_start.date()),
              'evaluation_end':str(development.index[-1].date()),'reserved_start':str(prices.index[split].date()),
              'reserved_end':str(prices.index[-1].date()),'selection_uses':'Prior 252 sessions; doubled costs; zero cash return',
              'latest_research_parameters':selections[-1]['parameters'],'latest_selection_as_of':selections[-1]['training_end'],
              'initial_warmup_parameters':candidates[0],
              'hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (
                  args.prices,DEFAULT_HYBRID_CONFIG,Path('hybridportfoliopolicy.py'),Path(__file__),
                  Path('compare_portfolio_models.py'),Path('research/diversified_regime_portfolio.json'))},
              'limitations':['Development history was previously inspected; not a pristine out-of-sample evaluation.',
                             'Price-based macro proxies and adjusted-close fill proxies remain.',
                             'Parent allocators retain their existing covariance estimates, including SGOV sensitivity; only hybrid risk controls use scale-preserving covariance.',
                             'Blending does not preserve parent account-level risk budgets; new strategy acceptance and authorization integration are required.',
                             'Daily risk checks and drawdown-aware selection do not guarantee a maximum loss or higher future returns.']}
    (args.output/'research-model.json').write_text(json.dumps(metadata,indent=2,allow_nan=False)+'\n')
    lines=['='*110,'HYBRID RETURN / DRAWDOWN RESEARCH — CHRONOLOGICAL PARAMETER SELECTION','='*110,
           f'Evaluation: {metadata["evaluation_start"]} through {metadata["evaluation_end"]}; all models on identical dates.',
           f'Reserved final 20% NOT scored: {metadata["reserved_start"]} through {metadata["reserved_end"]}.',
           f'{len(candidates)} configurations, selection every 126 sessions using only the prior 252 sessions.',
           'Selection: maximize net training CAGR subject to <=6% training drawdown; otherwise CAGR - 2*|drawdown|.',
           'Daily trend/volatility/stress checks; next-session-close fills; 3% trade band; no leverage.',
           'Research only. Prior development data were already inspected; this is not an untouched holdout.']
    for carry in (False,True):
        lines+=['',f'CASH: {"SGOV return proxy" if carry else "zero return"}; 15 bps commission + slippage']
        display=table[(table.cash_proxy==carry)&(table.cost_bps==15)][['model','cagr','volatility','max_drawdown','sharpe_over_sgov','annual_traded_notional','final_value_1m']].copy()
        for col in ('cagr','volatility','max_drawdown','annual_traded_notional'):
            display[col]=display[col].map(lambda value:f'{100*value:.2f}%')
        display.sharpe_over_sgov=display.sharpe_over_sgov.map(lambda value:f'{value:.3f}')
        display.final_value_1m=display.final_value_1m.map(lambda value:f'${value:,.0f}')
        lines.append(display.to_string(index=False))
    lines+=['','LATEST RESEARCH PARAMETERS (not a current live allocation):',json.dumps(selections[-1]['parameters'],sort_keys=True),
            'BASELINE PARENT BUDGETS WERE NOT RELAXED. Hybrid account-level budgets need separate acceptance.',
            f'Detailed trials, folds, decisions and cost sensitivities: {args.output}']
    terminal='\n'.join(lines)+'\n'
    (args.output/'terminal-results.txt').write_text(terminal)
    print(terminal)


if __name__=='__main__':
    main()
