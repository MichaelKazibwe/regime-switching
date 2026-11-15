"""Historical coverage, actual-history tests and conditional forward simulations.

Never fabricates pre-inception ETF returns or calls synthetic paths backtests.
Uses a fixed prior holdout boundary and submits no orders.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from assetuniverse import DIVERSIFIED_ASSETS, PRODUCTION_ASSETS
from compare_portfolio_models import build_targets, metrics, simulate
from diversifiedregimepolicy import DiversifiedRegimePolicy
from hybridportfoliopolicy import HybridPortfolioPolicy
from optimize_hybrid_portfolio import (
    hybrid_simulation, market_states, parameter_grid, rebased, select_parameters, selected_schedule,
)
from tradingcalendar import TradingCalendar

MODELS=('14 production allocator*','26 diversified allocator*','Chronologically selected hybrid')


def common_history(raw, assets, *, end_before):
    frame=raw.loc[raw.index<pd.Timestamp(end_before),list(assets)]
    first=frame.apply(lambda s:s.first_valid_index())
    last=frame.apply(lambda s:s.last_valid_index())
    if first.isna().any() or last.isna().any():
        raise ValueError('One or more requested tickers have no usable history')
    frame=frame.loc[max(first):min(last)]
    if (not np.isfinite(frame.to_numpy()).all() or (frame<=0).any().any()
            or not frame.index.is_unique or not frame.index.is_monotonic_increasing):
        raise ValueError('Missing, invalid or unordered observations inside the common history')
    return frame


def block_indices(rng, observations, length, paths, block_length):
    if min(observations,length,paths,block_length)<=0 or block_length>observations:
        raise ValueError('Invalid moving-block bootstrap dimensions')
    starts=rng.integers(0,observations,size=(paths,int(np.ceil(length/block_length))))
    return ((starts[:,:,None]+np.arange(block_length))%observations).reshape(paths,-1)[:,:length]


def monte_carlo(returns, *, paths=10000, years=5, block_length=21, seed=271828):
    """Joint circular block bootstrap, including bootstrap uncertainty in drift.

    Three return streams share sampled dates. Portfolios are not reoptimized
    on simulated asset prices. Each path draws a bootstrap calibration mean
    and an independent sequence of centered future return blocks.
    """
    if not isinstance(returns,pd.DataFrame):
        raise ValueError('Simulation requires labelled portfolio return columns')
    values=np.asarray(returns,dtype=float)
    if (values.ndim!=2 or len(values)<252 or not np.isfinite(values).all()
            or (values<=-1).any() or paths<2 or years<1):
        raise ValueError('Simulation requires complete valid portfolio returns and sufficient history')
    logs=np.log1p(values)
    residuals=logs-logs.mean(axis=0)
    rng=np.random.default_rng(seed)
    terminal=np.empty((paths,values.shape[1]))
    drawdown=np.empty_like(terminal)
    length=int(years*252)
    for start in range(0,paths,128):
        count=min(128,paths-start)
        calibration=block_indices(rng,len(logs),len(logs),count,block_length)
        drift=logs[calibration].mean(axis=1)
        indices=block_indices(rng,len(logs),length,count,block_length)
        cumulative=np.cumsum(residuals[indices]+drift[:,None,:],axis=1)
        peak=np.maximum.accumulate(np.maximum(cumulative,0),axis=1)
        terminal[start:start+count]=np.exp(cumulative[:,-1,:])
        drawdown[start:start+count]=np.expm1(cumulative-peak).min(axis=1)
    summaries=[]
    for i,name in enumerate(returns.columns):
        factors=terminal[:,i]
        summaries.append({'model':name,'median_final_1m':float(np.median(factors)*1e6),
                          'p05_final_1m':float(np.quantile(factors,.05)*1e6),'p95_final_1m':float(np.quantile(factors,.95)*1e6),
                          'probability_terminal_loss':float(np.mean(factors<1)),
                          'median_max_drawdown':float(np.median(drawdown[:,i])),
                          'p95_drawdown_magnitude':float(np.quantile(-drawdown[:,i],.95)),
                          'probability_drawdown_over_10pct':float(np.mean(drawdown[:,i]<-.1))})
    details=pd.concat([pd.DataFrame({'path':np.arange(paths),'model':name,'terminal_factor':terminal[:,i],
                                     'max_drawdown':drawdown[:,i]}) for i,name in enumerate(returns.columns)],ignore_index=True)
    return pd.DataFrame(summaries),details


def parametric_projection(returns, years=5):
    if (not isinstance(returns,pd.DataFrame) or not np.isfinite(returns.to_numpy()).all()
            or (returns<=-1).any().any() or len(returns)<252 or not np.isfinite(years) or years<=0):
        raise ValueError('Projection requires at least 252 complete valid return observations')
    logs=np.log1p(returns)
    horizon=252*years
    result=[]
    for name in returns:
        mu=float(logs[name].mean())
        sigma=float(logs[name].std(ddof=1))
        spread=norm.ppf(.95)*sigma*np.sqrt(horizon)
        result.append({'model':name,'historical_log_drift_annual':mu*252,
                       'median_final_1m':float(1e6*np.exp(mu*horizon)),
                       'p05_final_1m':float(1e6*np.exp(mu*horizon-spread)),
                       'p95_final_1m':float(1e6*np.exp(mu*horizon+spread)),
                       'half_drift_median_final_1m':float(1e6*np.exp(.5*mu*horizon))})
    return pd.DataFrame(result)


def fetch_history(path, as_of):
    import yfinance as yf

    frame=yf.download(list(DIVERSIFIED_ASSETS),start=str((as_of-pd.DateOffset(years=51)).date()),
                      end=str((as_of+pd.Timedelta(days=1)).date()),auto_adjust=True,progress=False,threads=4,timeout=30)
    prices=frame['Close'].reindex(columns=DIVERSIFIED_ASSETS)
    if prices.index.tz is not None:
        prices.index=prices.index.tz_localize(None)
    latest=TradingCalendar().latest_completed_session(as_of.tz_localize('UTC'))
    prices=prices.loc[prices.index.date<=latest.tz_convert('America/New_York').date()]
    if prices.empty or prices.isna().all().any():
        raise ValueError('Historical download did not return every ETF')
    prices.to_csv(path)
    return prices


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch',action='store_true')
    parser.add_argument('--as-of',default='2026-10-30',help='Client-date start of nominal five-year projection')
    parser.add_argument('--paths',type=int,default=10000)
    parser.add_argument('--seed',type=int,default=271828)
    parser.add_argument('--output',type=Path,default=Path('var/research/horizon-analysis'))
    args=parser.parse_args()
    if not 100<=args.paths<=100000:
        raise ValueError('Use between 100 and 100000 Monte Carlo paths')
    as_of=pd.Timestamp(args.as_of).normalize()
    args.output.mkdir(parents=True,exist_ok=True)
    raw_path=args.output/'observed-history.csv'
    if args.fetch:
        print('Downloading actual ETF histories; no pre-inception observations will be manufactured.',flush=True)
        raw=fetch_history(raw_path,as_of)
    else:
        raw=pd.read_csv(raw_path,index_col=0,parse_dates=True)
    prior=json.loads(Path('var/research/hybrid-optimization/research-model.json').read_text())
    reserved_start=pd.Timestamp(prior['reserved_start'])
    if as_of<=reserved_start:
        raise ValueError('Projection date must follow the preserved research boundary')
    coverage=[]
    for symbol in DIVERSIFIED_ASSETS:
        series=raw[symbol].dropna()
        coverage.append({'asset':symbol,'first_observed':str(series.index[0].date()),'last_observed':str(series.index[-1].date())})
    pd.DataFrame(coverage).to_csv(args.output/'coverage.csv',index=False)
    requested_start=as_of-pd.DateOffset(years=50)
    statuses=[{'model':name,'requested_start':str(requested_start.date()),'requested_end':str(as_of.date()),
               'status':'UNAVAILABLE_PREINCEPTION_DATA','metrics':None,
               'reason':'The model instruments did not exist for 50 years. No approved complete pre-inception proxy panel is available.'}
              for name in MODELS]
    (args.output/'50-year-backtest-status.json').write_text(json.dumps(statuses,indent=2)+'\n')

    print('Running longest 14-ETF actual-history allocator test (price-proxy regimes).',flush=True)
    history14=common_history(raw,PRODUCTION_ASSETS,end_before=reserved_start)
    policy=DiversifiedRegimePolicy()
    targets14,audit14=build_targets(history14,policy,include_diversified=False)
    r14=history14.pct_change(fill_method=None).iloc[253:]
    zero14=pd.Series(0.0,index=r14.index)
    long_result=simulate(r14,targets14[MODELS[0]],cost_rate=.0015,cash_returns=zero14)
    long_metrics=metrics(long_result,zero14)
    long_metrics['sharpe_over_zero']=long_metrics.pop('sharpe_over_sgov')
    long_projection=parametric_projection(long_result[['return']].rename(columns={'return':MODELS[0]}))
    long_projection.to_csv(args.output/'14-etf-long-calibration-projection-sensitivity.csv',index=False)
    long_result.to_csv(args.output/'14-etf-long-history.csv')
    (args.output/'14-etf-decision-audit.json').write_text(json.dumps(audit14,indent=2,allow_nan=False)+'\n')

    print('Running all three models on common actual history; hybrid selection remains chronological.',flush=True)
    common=common_history(raw,DIVERSIFIED_ASSETS,end_before=reserved_start)
    targets,audit=build_targets(common,policy)
    hybrid=HybridPortfolioPolicy()
    states=market_states(common,audit,hybrid)
    candidates=parameter_grid(hybrid)
    bank={}
    for index,params in enumerate(candidates):
        bank[index],_=hybrid_simulation(common,states,hybrid,lambda date,p=params:p,cost_rate=.003)
    selections,trials=select_parameters(bank,candidates,hybrid)
    def schedule(date):
        return selected_schedule(date,selections,candidates)
    hybrid_frame,decisions=hybrid_simulation(common,states,hybrid,schedule,cost_rate=.0015)
    evaluation_start=pd.Timestamp(selections[0]['evaluation_start'])
    asset_returns=common.pct_change(fill_method=None).iloc[253:]
    zero=pd.Series(0.0,index=asset_returns.index)
    frames={MODELS[2]:rebased(hybrid_frame.loc[evaluation_start:])}
    for name in MODELS[:2]:
        frames[name]=rebased(simulate(asset_returns,targets[name],cost_rate=.0015,cash_returns=zero).loc[evaluation_start:])
    calibration=pd.DataFrame({name:frames[name]['return'] for name in MODELS})
    historical=pd.DataFrame([{'model':name,**metrics(frames[name],asset_returns.SGOV.loc[calibration.index])} for name in MODELS])
    historical.to_csv(args.output/'common-history-metrics.csv',index=False)
    calibration.to_csv(args.output/'calibration-net-returns.csv')
    pd.concat(frames,names=['model','date']).to_csv(args.output/'common-daily-results.csv')
    for filename,document in [('hybrid-trials.json',trials),('hybrid-selections.json',selections),
                              ('hybrid-decisions.json',decisions),('parent-proposals.json',audit)]:
        (args.output/filename).write_text(json.dumps(document,indent=2,allow_nan=False)+'\n')
    projection=parametric_projection(calibration)
    projection.to_csv(args.output/'five-year-conditional-projection.csv',index=False)
    print(f'Running {args.paths:,} joint five-year Monte Carlo paths with drift uncertainty.',flush=True)
    mc,paths=monte_carlo(calibration,paths=args.paths,seed=args.seed)
    mc.to_csv(args.output/'five-year-monte-carlo.csv',index=False)
    paths.to_csv(args.output/'monte-carlo-path-outcomes.csv',index=False)
    # Block-length sensitivity shares models and seed, without selecting a winner.
    sensitivity=[]
    for block in (5,63):
        result,_=monte_carlo(calibration,paths=args.paths,seed=args.seed,block_length=block)
        result['block_sessions']=block
        sensitivity.append(result)
    pd.concat(sensitivity).to_csv(args.output/'block-length-sensitivity.csv',index=False)
    metadata={'status':'EXPLORATORY_NOT_DEPLOYMENT_QUALIFICATION','backtest_50_years':'UNAVAILABLE_PREINCEPTION_DATA',
              'actual_14_start':str(long_result.index[0].date()),'actual_14_end':str(long_result.index[-1].date()),
              'common_start':str(calibration.index[0].date()),'common_end':str(calibration.index[-1].date()),
              'calibration_sessions':len(calibration),'reserved_start':str(reserved_start.date()),
              'projection_start':str(as_of.date()),'projection_end':str((as_of+pd.DateOffset(years=5)).date()),
              'forecast_trading_sessions':1260,'monte_carlo_paths':args.paths,'seed':args.seed,'block_sessions':21,
              'monte_carlo_method':'Joint circular block bootstrap with independently bootstrapped drift-estimation uncertainty',
              'cost_bps_embedded':15,'cash_return_assumption':0,'orders_submitted':0,
              'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (
                  raw_path,Path(__file__),Path('compare_portfolio_models.py'),Path('hybridportfoliopolicy.py'),
                  Path('optimize_hybrid_portfolio.py'),Path('research/hybrid_portfolio.json'),
                  Path('research/diversified_regime_portfolio.json'))},
              'long_14_metrics':long_metrics,
              'limitations':['All strategy runs still use price-based macro proxies and adjusted-close fill proxies.',
                             'Model and ETF selection occurred after much of this history; no pristine out-of-sample claim.',
                             'The reserved history remains excluded from return scoring and forward calibration.',
                             'Forward nominal window begins at client date but is calibrated only through the prior research boundary; not a current-market forecast.',
                             'Gaussian projection assumes stationary independent log returns and excludes drift-estimation uncertainty.',
                             'Monte Carlo resamples net portfolio returns, not a rerun of strategy decisions on simulated asset prices.',
                             'Limited calibration history cannot represent all possible crises; simulated frequencies are conditional model outputs, not actual probabilities.',
                             'Costs are embedded from historical trading, not recomputed as future trade costs; future cash rates, inflation and taxes are not forecast.',
                             'Neither projections nor Monte Carlo paths constitute a 50-year historical backtest.']}
    (args.output/'methodology.json').write_text(json.dumps(metadata,indent=2,allow_nan=False)+'\n')
    lines=['='*118,'THREE-MODEL HISTORY, FIVE-YEAR PROJECTION AND MONTE CARLO','='*118,
           f'Requested 50-year window: {requested_start.date()} to {as_of.date()}',
           '50-YEAR ACTUAL BACKTEST: UNAVAILABLE for all three models — instruments did not exist; no fabricated proxy returns.',
           f"14-ETF longest actual test: {metadata['actual_14_start']} to {metadata['actual_14_end']}",
           f"  CAGR {long_metrics['cagr']:.2%}; volatility {long_metrics['volatility']:.2%}; max drawdown {long_metrics['max_drawdown']:.2%}; final $1m = ${long_metrics['final_value_1m']:,.0f}",
           f"COMMON-DATE ACTUAL TEST: {metadata['common_start']} to {metadata['common_end']} ({len(calibration)} sessions)",
           'Actual price histories; exploratory price-based regimes, NOT a complete macro-driven production backtest.',
           '15 bps ETF trading costs; zero cash interest; causal selection and next-session-close fill proxies.']
    display=historical[['model','cagr','volatility','max_drawdown','final_value_1m']].copy()
    for col in ('cagr','volatility','max_drawdown'):
        display[col]=display[col].map(lambda v:f'{v:.2%}')
    display.final_value_1m=display.final_value_1m.map(lambda v:f'${v:,.0f}')
    lines.append(display.to_string(index=False))
    lines += [f"14-ETF longer-calibration sensitivity (2008-2025): five-year median = ${long_projection.iloc[0].median_final_1m:,.0f}; illustrates drift/lookback uncertainty."]
    lines+=['',f"FIVE-YEAR CONDITIONAL PROJECTION: {metadata['projection_start']} to {metadata['projection_end']} (~1,260 sessions)",
            f"Calibration ends {metadata['common_end']}; reserved data from {metadata['reserved_start']} NOT used.",
            'Gaussian log-return extrapolation; nominal USD; not a reliable current-market prediction.']
    display=projection.drop(columns=['historical_log_drift_annual']).copy()
    for col in display.columns[1:]:
        display[col]=display[col].map(lambda v:f'${v:,.0f}')
    lines.append(display.to_string(index=False))
    lines+=['',f'MONTE CARLO: {args.paths:,} joint paths/model, five years, seed {args.seed}, 21-session blocks',
            'Includes bootstrap uncertainty in drift. Resamples strategy returns; does not rerun allocators on future asset paths.']
    display=mc[['model','median_final_1m','p05_final_1m','p95_final_1m']].copy()
    for col in ('median_final_1m','p05_final_1m','p95_final_1m'):
        display[col]=display[col].map(lambda v:f'${v:,.0f}')
    lines.append(display.to_string(index=False))
    display=mc[['model','probability_terminal_loss','median_max_drawdown','p95_drawdown_magnitude','probability_drawdown_over_10pct']].copy()
    for col in display.columns[1:]:
        display[col]=display[col].map(lambda v:f'{v:.2%}')
    lines.append(display.to_string(index=False))
    lines+=['','p05/p95 are conditional outcome percentiles, not guarantees or confidence intervals for expected return.',
            'Historical drift is uncertain and may not persist. A few years of returns cannot establish 50-year resilience.',
            f'Results, per-ETF coverage, audits, 5/63-day block sensitivity and raw path outcomes: {args.output}']
    terminal='\n'.join(lines)+'\n'
    (args.output/'terminal-results.txt').write_text(terminal)
    print(terminal)


if __name__=='__main__':
    main()
