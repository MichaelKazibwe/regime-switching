"""Cycle-aware, point-in-time macro portfolio research. No broker integration."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
from sklearn.covariance import LedoitWolf

from assetuniverse import DIVERSIFIED_ASSETS, PRODUCTION_ASSETS
from compare_portfolio_models import metrics, rebalance_fee
from diversifiedregimepolicy import AllocationError
from optimize_hybrid_portfolio import rebased
from smartregimeportfolio import DEFAULT_SMART_CONFIG, PointInTimeMacro, SmartRegimePortfolio
from stress_test_models import common_history, monte_carlo


def prepare_states(prices, macro, policy, *, macro_enabled=True):
    daily=prices.pct_change(fill_method=None)
    closes=mcal.get_calendar('NYSE').schedule(prices.index[0].date(),prices.index[-1].date()).market_close
    if list(prices.index)!=list(closes.index):
        raise ValueError('Missing or nontrading price dates')
    states={}
    features=[]
    risk_assets=set(s for group in policy.config['risk_groups'].values() for s in group)
    for i in range(252,len(prices)-1):
        date=prices.index[i]
        history=daily.iloc[i-251:i+1]
        eligible=[s for s in DIVERSIFIED_ASSETS if s in risk_assets and np.isfinite(history[s].to_numpy()).all()]
        active=history[eligible]
        values=active.to_numpy()
        std=values.std(axis=0,ddof=0)
        estimate=LedoitWolf().fit((values-values.mean(axis=0))/std).covariance_
        correlation=estimate/np.sqrt(np.outer(np.diag(estimate),np.diag(estimate)))
        covariance=correlation*np.outer(std,std)*252
        spy=prices.SPY.iloc[:i+1]
        market={'trend':float((spy.iloc[-1]/spy.iloc[-64]-1)/(daily.SPY.iloc[i-62:i+1].std()*np.sqrt(63))),
                'as_of':closes.iloc[i].isoformat(),
                'breadth':float(np.mean([prices[s].iloc[i]>prices[s].iloc[max(0,i-126):i+1].mean() for s in ('SPY','QQQ','IWM','VEA','VWO')])),
                'drawdown':float(spy.iloc[-1]/spy.tail(252).max()-1),
                'volatility':float(daily.SPY.iloc[i-19:i+1].std()*np.sqrt(252)),
                'credit_relative':float(prices.HYG.iloc[i]/prices.HYG.iloc[i-63]-prices.LQD.iloc[i]/prices.LQD.iloc[i-63])}
        macro_features=macro.features(closes.iloc[i])
        if not macro_enabled:
            macro_features={**macro_features,'ip_growth':0.0,'unemployment_change':0.0,
                            'inflation_change':0.0,'yield_curve':0.0}
        signal=policy.classify(macro_features,market,decision_time=closes.iloc[i])
        states[date]={'i':i,'eligible':eligible,'covariance':covariance,'signal':signal,'stamp':closes.iloc[i]}
        features.append({'date':str(date.date()),**macro_features,**market,**signal})
    return daily,states,features


def run_strategy(prices, daily, states, policy, schedule, *, cost_rate=.0015):
    weights=np.zeros(len(DIVERSIFIED_ASSETS))
    nav=peak=1.0
    cash=1.0
    records=[]
    trades=[]
    failures=[]
    pending=None
    previous_regime=None
    nav_history=[1.0]
    dates=prices.index
    for i in range(252,len(prices)):
        date=dates[i]
        if i>252:
            observed=daily.iloc[i].to_numpy()
            held=weights>0
            if not np.isfinite(observed[held]).all():
                raise ValueError('Missing returns for held instruments; valuation cannot continue')
            dollars=np.zeros(len(weights))
            dollars[held]=weights[held]*(1+observed[held])
            growth=float(dollars.sum()+cash)
            weights=dollars/growth
            cash/=growth
            fee=turnover=0.0
            if pending is not None:
                target=np.array([pending['weights'][s] for s in DIVERSIFIED_ASSETS])
                fee=rebalance_fee(weights,target,cost_rate)
                turnover=float(np.abs(target*(1-fee)-weights).sum())
                weights=target
                cash=1-weights.sum()
                trades.append({'execution_date':str(date.date()),**pending})
            cost=nav*growth*fee
            net=growth*(1-fee)-1
            nav*=1+net
            peak=max(peak,nav)
            nav_history.append(nav)
            records.append({'date':date,'return':net,'equity':nav,'cash':cash,'turnover':turnover,
                            'cost_as_initial_capital':cost,'regime':states[dates[i-1]]['signal']['regime'],
                            'macro_quadrant':max(states[dates[i-1]]['signal']['probabilities'],key=states[dates[i-1]]['signal']['probabilities'].get)})
        pending=None
        if date not in states:
            continue
        state=states[date]
        signal=state['signal']
        params=schedule(date)
        window=policy.config.get('drawdown_control_window')
        control_peak=max(nav_history[-window:]) if window else peak
        drawdown=nav/control_peak-1
        exposure,ceiling=policy.risk_limits(signal,params,drawdown)
        columns=[list(DIVERSIFIED_ASSETS).index(s) for s in state['eligible']]
        if any(weights[j]>0 for j,s in enumerate(DIVERSIFIED_ASSETS) if s not in state['eligible']):
            raise ValueError('A held instrument has insufficient risk-estimation data')
        w=weights[columns]
        volatility=float(np.sqrt(w@state['covariance']@w))
        breach=weights.sum()>exposure+1e-10 or weights.max()>.25+1e-10 or volatility>ceiling+1e-10
        due=(i-252)%policy.config['rebalance_sessions']==0 or signal['regime']!=previous_regime or breach
        if due:
            try:
                proposal=policy.allocate(daily.iloc[i-251:i+1][state['eligible']],signal,params,
                                         account_drawdown=drawdown,decision_time=state['stamp'])
                target=np.array([proposal['weights'][s] for s in DIVERSIFIED_ASSETS])
                if breach or np.abs(target-weights).sum()>=policy.config['minimum_trade_notional']:
                    pending=proposal
            except AllocationError as exc:
                failures.append({'date':str(date.date()),'reason':str(exc)})
        previous_regime=signal['regime']
    return pd.DataFrame(records).set_index('date'),trades,failures


def quarter_loss_frequency(returns):
    values=np.asarray(returns)
    quarters=len(values)//63
    if not quarters:
        return None
    compounded=np.prod(1+values[:quarters*63].reshape(quarters,63),axis=1)-1
    return float(np.mean(compounded<0))


def choose_candidates(bank, candidates, policy):
    dates=next(iter(bank.values())).index
    training=policy.config['training_sessions']
    choices=[]
    trials=[]
    for boundary in range(training,len(dates),policy.config['selection_interval_sessions']):
        sample=dates[boundary-training:boundary]
        scores=[]
        for j,frame in bank.items():
            window=rebased(frame.loc[sample])
            result=metrics(window,pd.Series(0.0,index=sample))
            loss=quarter_loss_frequency(window['return'])
            score=result['cagr']-2*abs(result['max_drawdown'])-.15*loss
            row={'candidate':j,'parameters':candidates[j],'training_start':str(sample[0].date()),
                 'training_end':str(sample[-1].date()),'evaluation_start':str(dates[boundary].date()),
                 'quarter_loss_frequency':loss,'objective':score,**result}
            scores.append(row)
            trials.append(row)
        choices.append(max(scores,key=lambda row:(row['objective'],-row['annual_traded_notional'],-row['candidate'])))
    return choices,trials


def business_cycle(date):
    # Retrospective NBER labels are reporting-only and never classifier inputs.
    date=pd.Timestamp(date)
    if pd.Timestamp('2008-01-01')<=date<=pd.Timestamp('2009-06-30') or pd.Timestamp('2020-03-01')<=date<=pd.Timestamp('2020-04-30'):
        return 'NBER recession'
    if pd.Timestamp('2009-07-01')<=date<=pd.Timestamp('2010-06-30') or pd.Timestamp('2020-05-01')<=date<=pd.Timestamp('2021-04-30'):
        return 'First year after NBER trough'
    return 'Other NBER expansion'


def regime_report(frame):
    rows=[]
    account_drawdown=frame.equity/np.maximum.accumulate(np.r_[1.0,frame.equity.to_numpy()])[1:]-1
    for dimension,labels in [('regime',frame.regime),('macro_quadrant',frame.macro_quadrant),
                             ('business_cycle',pd.Series([business_cycle(d) for d in frame.index],index=frame.index))]:
        for label in sorted(labels.unique()):
            selected=labels==label
            r=frame.loc[selected,'return']
            rows.append({'dimension':dimension,'label':label,'sessions':len(r),
                         'conditional_compounded_return':float(np.prod(1+r)-1),
                         'mean_daily_return':float(r.mean()),'daily_loss_frequency':float((r<0).mean()),
                         'worst_account_drawdown_on_labelled_days':float(account_drawdown.loc[selected].min())})
    return pd.DataFrame(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prices',type=Path,default=Path('var/research/horizon-analysis/observed-history.csv'))
    parser.add_argument('--macro',type=Path,default=Path('var/research/smart-macro-vintages/manifest.json'))
    parser.add_argument('--config',type=Path,default=DEFAULT_SMART_CONFIG)
    parser.add_argument('--output',type=Path,default=Path('var/research/smart-portfolio'))
    args=parser.parse_args()
    raw=pd.read_csv(args.prices,index_col=0,parse_dates=True)
    reserved=pd.Timestamp('2025-10-30')
    base=common_history(raw,PRODUCTION_ASSETS,end_before=reserved)
    prices=raw.loc[base.index,list(DIVERSIFIED_ASSETS)]
    policy=SmartRegimePortfolio(args.config)
    macro=PointInTimeMacro(args.macro)
    print('Preparing actual point-in-time macro and market states; reserved dates excluded.',flush=True)
    daily,states,features=prepare_states(prices,macro,policy)
    grid=policy.config['candidate_grid']
    candidates=[dict(zip(grid,values)) for values in itertools.product(*grid.values())]
    bank={}
    for j,params in enumerate(candidates):
        print(f'Training research variant {j+1}/{len(candidates)}: {params}',flush=True)
        bank[j],_,errors=run_strategy(prices,daily,states,policy,lambda date,p=params:p,cost_rate=.003)
        if errors:
            raise RuntimeError(f'Rejected {len(errors)} allocation proposals; research comparison stopped for review')
    choices,trials=choose_candidates(bank,candidates,policy)
    def schedule(date):
        available=[choice for choice in choices if pd.Timestamp(choice['training_end'])<=date]
        return available[-1]['parameters'] if available else candidates[0]
    print('Running chronological adaptive strategy and doubled-cost sensitivity.',flush=True)
    result,trades,errors=run_strategy(prices,daily,states,policy,schedule)
    doubled,_,double_errors=run_strategy(prices,daily,states,policy,schedule,cost_rate=.003)
    if errors or double_errors:
        raise RuntimeError('One or more final risk proposals failed; acceptance cannot be inferred')
    print('Running macro-feature ablation with the same selected parameters and risk controls.',flush=True)
    ablation_policy=SmartRegimePortfolio(args.config)
    _,ablation_states,_=prepare_states(prices,PointInTimeMacro(args.macro),ablation_policy,macro_enabled=False)
    ablated,_,ablation_errors=run_strategy(prices,daily,ablation_states,ablation_policy,schedule)
    if ablation_errors:
        raise RuntimeError('Ablation proposals failed validation; comparison stopped')
    args.output.mkdir(parents=True,exist_ok=True)
    result.to_csv(args.output/'daily-results.csv')
    ablated.to_csv(args.output/'macro-ablated-daily-results.csv')
    (args.output/'switching-state.json').write_text(json.dumps(policy.export_state(),indent=2,allow_nan=False)+'\n')
    report=regime_report(result)
    report.to_csv(args.output/'regime-cycle-results.csv',index=False)
    for name,value in [('selections.json',choices),('trials.json',trials),('decision-audit.json',trades),('features.json',features)]:
        (args.output/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    rows=[]
    zero=pd.Series(0.0,index=result.index)
    rows.append({'model':'Smart macro/risk candidate','start':str(result.index[0].date()),'end':str(result.index[-1].date()),**metrics(result,zero)})
    prior=pd.read_csv('var/research/horizon-analysis/14-etf-long-history.csv',index_col=0,parse_dates=True)
    matched=prior.loc[result.index]
    rows.append({'model':'14-ETF price-proxy baseline','start':str(result.index[0].date()),'end':str(result.index[-1].date()),**metrics(rebased(matched),zero)})
    short=pd.read_csv('var/research/horizon-analysis/calibration-net-returns.csv',index_col=0,parse_dates=True)
    common=result.index.intersection(short.index)
    for name in short:
        frame=pd.DataFrame({'return':short.loc[common,name],'equity':(1+short.loc[common,name]).cumprod(),
                            'cash':0.0,'turnover':0.0,'cost_as_initial_capital':0.0},index=common)
        row=metrics(frame,pd.Series(0.0,index=common))
        row['mean_cash']=row['annual_traded_notional']=row['cost_pct_initial_capital']=None
        rows.append({'model':name,'start':str(common[0].date()),'end':str(common[-1].date()),**row})
    rows.append({'model':'Smart macro/risk candidate (matched)','start':str(common[0].date()),'end':str(common[-1].date()),
                 **metrics(rebased(result.loc[common]),pd.Series(0.0,index=common))})
    comparison=pd.DataFrame(rows)
    comparison.to_csv(args.output/'comparison.csv',index=False)
    calibrated=short.loc[common].copy()
    calibrated['Smart macro/risk candidate']=result.loc[common,'return']
    mc,_=monte_carlo(calibrated,paths=10000,years=1,seed=314159)
    mc.to_csv(args.output/'one-year-loss-simulation.csv',index=False)
    metadata={'status':'RESEARCH_CANDIDATE_NOT_ACCEPTED','production_activation':False,'orders_submitted':0,
              'start':str(result.index[0].date()),'end':str(result.index[-1].date()),'reserved_start':str(reserved.date()),
              'candidate_count':len(candidates),'prior_research_variant_runs':8 if policy.config.get('research_revision')==3 else 4 if policy.config.get('research_revision')==2 else 0,
              'seed_parameters':candidates[0],'latest_parameters':choices[-1]['parameters'],
              'latest_selection_as_of':choices[-1]['training_end'],'doubled_cost_metrics':metrics(doubled,zero),
              'macro_ablated_metrics':metrics(ablated,zero),
              'max_budget_error':max(t['risk_budget_error'] for t in trades),
              'rejected_proposals':len(errors),'trade_events':len(trades),'quarter_loss_frequency':quarter_loss_frequency(result['return']),
              'config_path':str(args.config),
              'hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.prices,args.macro,args.config,
                  Path('smartregimeportfolio.py'),Path(__file__))},
              'limitations':['Current ETF list and model design were selected retrospectively; no pristine out-of-sample claim.',
                             'Historically eligible ETF subset changes only after 252 complete returns; no pre-inception returns.',
                             'NBER cycle labels are retrospective reporting-only; earliest recession coverage is partial.',
                             'Adjusted-close execution and zero cash returns are research assumptions.',
                             'Soft regime weights are not calibrated recession or financial-loss probabilities.',
                             'Budget, volatility and expected-shortfall estimates are not realized loss guarantees.',
                             'New expanded-universe account risk budgets require formal acceptance and authorization integration.']}
    (args.output/'research-model.json').write_text(json.dumps(metadata,indent=2,allow_nan=False)+'\n')
    lines=['='*110,'SMART MACRO / MARKET PORTFOLIO — ACTUAL MACRO VINTAGES, RESEARCH ONLY','='*110,
           'Historical releases available only after next New York midnight; no revised-data substitution.',
           'Asset eligibility is historical; no pre-inception prices; risk budgets enforced to 1e-6 on every proposal.',
           '15 bps trading costs, zero cash interest, next-session-close fill proxies; final reserved year excluded.']
    display=comparison[['model','start','end','cagr','volatility','max_drawdown']].copy()
    for col in ('cagr','volatility','max_drawdown'):
        display[col]=display[col].map(lambda x:f'{x:.2%}')
    lines.append(display.to_string(index=False))
    lines+=['','REGIME / BUSINESS CYCLE ATTRIBUTION (noncontiguous rows are not standalone strategies)']
    display=report.copy()
    for col in ('conditional_compounded_return','mean_daily_return','daily_loss_frequency','worst_account_drawdown_on_labelled_days'):
        display[col]=display[col].map(lambda x:f'{x:.2%}')
    lines.append(display.to_string(index=False))
    lines+=['',f"Doubled-cost CAGR: {metadata['doubled_cost_metrics']['cagr']:.2%}; drawdown: {metadata['doubled_cost_metrics']['max_drawdown']:.2%}",
            f"Macro-feature ablation (same parameter schedule): CAGR {metadata['macro_ablated_metrics']['cagr']:.2%}; drawdown {metadata['macro_ablated_metrics']['max_drawdown']:.2%}",
            f"Largest asset risk-budget error: {metadata['max_budget_error']:.3g}; rejected proposals: {len(errors)}.",
            f'Latest chronologically selected parameters: {metadata["latest_parameters"]}',
            'JOINT ONE-YEAR BLOCK-BOOTSTRAP LOSS ESTIMATES (conditional, not real-world probabilities):',
            mc[['model','probability_terminal_loss','p95_drawdown_magnitude']].to_string(index=False),
            'No production activation. Independent prospective validation and the new account risk-contract gate remain required.',
            f'Detailed allocation/risk audits, features, trials and cycle results: {args.output}']
    text='\n'.join(lines)+'\n'
    (args.output/'terminal-results.txt').write_text(text)
    print(text)


if __name__=='__main__':
    main()
