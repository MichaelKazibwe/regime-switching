import hashlib
import io
import json
from pathlib import Path
from urllib.error import HTTPError

import numpy as np
import pandas as pd
import pytest

from assetuniverse import DIVERSIFIED_ASSETS
from diversifiedregimepolicy import AllocationError
from macrovintage import MacroVintageData
from smartregimeportfolio import (
    PointInTimeMacro, REGIMES, SmartRegimePortfolio, capped_distribution, solve_risk_budget,
)


def macro_archive(tmp_path):
    manifest={'series':{}}
    dates=pd.date_range('2004-01-01','2010-12-01',freq='MS')
    for name,base,slope in [('UNRATE',5,.01),('CPIAUCSL',100,.3),('INDPRO',100,.2)]:
        frame=pd.DataFrame({'date':dates,'realtime_start':dates+pd.Timedelta(days=40),
                            'value':base+slope*np.arange(len(dates))})
        manifest['series'][name]=MacroVintageData(frame).freeze(tmp_path/f'{name}.csv')
    days=pd.bdate_range('2006-01-01','2010-12-31')
    for name,level in [('DGS10',4),('DGS3MO',3)]:
        frame=pd.DataFrame({'date':days,'realtime_start':days+pd.Timedelta(days=1),'value':level})
        manifest['series'][name]=MacroVintageData(frame).freeze(tmp_path/f'{name}.csv')
    path=tmp_path/'manifest.json'
    path.write_text(json.dumps(manifest))
    return path


def test_macro_cache_uses_consistent_timestamp_units_and_rewinds_safely(tmp_path):
    macro=PointInTimeMacro(macro_archive(tmp_path))
    early=macro.features('2008-07-25T20:00:00Z')
    later=macro.features('2009-07-25T20:00:00Z')
    assert early['observation_dates']['UNRATE']<later['observation_dates']['UNRATE']
    assert macro.features('2008-07-25T20:00:00Z')==early


def test_future_macro_revisions_do_not_change_prior_features(tmp_path):
    path=macro_archive(tmp_path)
    prior=PointInTimeMacro(path).features('2008-07-25T20:00:00Z')
    manifest=json.loads(path.read_text())
    target=Path(manifest['series']['INDPRO']['path'])
    frame=pd.read_csv(target)
    frame.loc[len(frame)]=['2008-06-01','2030-01-01',9999]
    frame.to_csv(target,index=False)
    manifest['series']['INDPRO']['sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    path.write_text(json.dumps(manifest))
    assert PointInTimeMacro(path).features('2008-07-25T20:00:00Z')==prior


def test_stale_macro_observations_fail_closed(tmp_path):
    macro=PointInTimeMacro(macro_archive(tmp_path))
    with pytest.raises(AllocationError,match='stale'):
        macro.features('2012-01-01T21:00:00Z')


def test_capped_budget_distribution_preserves_total_and_rejects_infeasibility():
    result=capped_distribution([.3,.4],.5,.25)
    assert np.allclose(result,[.25,.25])
    with pytest.raises(AllocationError):
        capped_distribution([1,1],.6,.25)


@pytest.mark.parametrize('regime',list(REGIMES)+['crisis'])
@pytest.mark.parametrize('revision',[1,3])
def test_exact_asset_risk_accounting_position_caps_and_tail_limits(regime,revision):
    config='research/smart_regime_portfolio_v3.json' if revision==3 else 'research/smart_regime_portfolio.json'
    policy=SmartRegimePortfolio(config)
    active=[s for s in DIVERSIFIED_ASSETS if s not in policy.config['excluded_from_risk_budget']]
    dates=pd.bdate_range('2023-01-01',periods=252)
    rng=np.random.default_rng(74)
    data=rng.normal(.0002,.01,(252,len(active)))
    data[-3:]-=.10
    returns=pd.DataFrame(data,index=dates,columns=active)
    probs={r:float(r==(regime if regime!='crisis' else REGIMES[0])) for r in REGIMES}
    stamp=dates[-1].tz_localize('UTC')+pd.Timedelta(hours=22)
    signal={'regime':regime,'stress':regime=='crisis','probabilities':probs,
            'growth_weight':sum(probs[r] for r in REGIMES[:2]),'as_of':stamp.isoformat()}
    parameters={k:v[0] for k,v in policy.config['candidate_grid'].items()}
    a=policy.allocate(returns,signal,parameters,account_drawdown=0,decision_time=stamp)
    assert sum(a['weights'].values())+a['cash']==pytest.approx(1)
    assert a['risk_budget_error']<=1e-6
    assert max(a['weights'].values())<=.25+1e-10
    assert max(a['asset_risk_shares'].values())<=.25+1e-6
    assert a['estimated_volatility']<=a['volatility_ceiling']+1e-10
    assert a['estimated_daily_es95']<=policy.config['stress_daily_expected_shortfall_ceiling']+1e-10 if regime=='crisis' else a['estimated_daily_es95']<=.02+1e-10
    for group,members in policy.config['risk_groups'].items():
        assert sum(a['asset_risk_shares'].get(s,0) for s in members)==pytest.approx(a['group_risk_targets'][group],abs=1e-6)
    if regime=='crisis':
        assert a['cash']>=.60-1e-10


def test_classifier_has_confirmation_and_immediate_crisis_override():
    policy=SmartRegimePortfolio()
    stamp='2024-01-15T21:00:00Z'
    macro={'ip_growth':-8,'unemployment_change':1,'inflation_change':3,'yield_curve':-1,'as_of':stamp}
    market={'trend':-.5,'breadth':.2,'drawdown':-.01,'volatility':.1,'credit_relative':0,'as_of':stamp}
    first=policy.classify(macro,market,decision_time=stamp)
    assert first['regime']=='disinflationary_growth'
    for date in pd.bdate_range('2024-01-16',periods=15):
        stamp=(date.tz_localize('UTC')+pd.Timedelta(hours=21)).isoformat()
        macro={**macro,'as_of':stamp}
        market={**market,'as_of':stamp}
        latest=policy.classify(macro,market,decision_time=stamp)
    assert latest['regime']=='stagflation'
    stamp=(pd.Timestamp(stamp)+pd.Timedelta(days=1)).isoformat()
    macro={**macro,'as_of':stamp}
    market={**market,'as_of':stamp}
    crisis=policy.classify(macro,{**market,'drawdown':-.2},decision_time=stamp)
    assert crisis['regime']=='crisis'
    with pytest.raises(AllocationError,match='future'):
        policy.classify({**macro,'as_of':'2025-01-01T21:00:00Z'},market,decision_time=stamp)


def test_risk_solver_matches_budgets_with_hedging_correlations():
    covariance=np.array([[.04,-.008,.005],[-.008,.01,.001],[.005,.001,.03]])
    budgets=np.array([.5,.3,.2])
    w=solve_risk_budget(covariance,budgets)
    assert np.allclose(w*(covariance@w)/(w@covariance@w),budgets,atol=1e-6)


def test_macro_http_failures_do_not_expose_configured_key(monkeypatch):
    import fetch_strategy_macro as fetch

    fake_key='private_test_token'
    monkeypatch.setattr(fetch.settings,'fred_api_key',fake_key)
    def rejected(*args,**kwargs):
        raise HTTPError('https://example.invalid',400,'rejected',{},io.BytesIO(json.dumps({'error_message':fake_key}).encode()))
    monkeypatch.setattr(fetch,'urlopen',rejected)
    with pytest.raises(RuntimeError) as error:
        fetch.fetch_series('UNRATE','2025-10-29')
    assert fake_key not in str(error.value)
    assert '[REDACTED]' in str(error.value)


def test_future_market_prices_do_not_change_prior_states_and_ipos_are_not_filled(tmp_path):
    from optimize_smart_portfolio import prepare_states

    import pandas_market_calendars as mcal
    dates=mcal.get_calendar('NYSE').schedule('2007-08-01','2009-01-01').index
    rng=np.random.default_rng(443)
    prices=pd.DataFrame(100*np.exp(np.cumsum(rng.normal(.0001,.007,(len(dates),len(DIVERSIFIED_ASSETS))),axis=0)),index=dates,columns=DIVERSIFIED_ASSETS)
    prices.loc[dates[:280],'IGOV']=np.nan
    path=macro_archive(tmp_path)
    _,first,_=prepare_states(prices,PointInTimeMacro(path),SmartRegimePortfolio())
    changed=prices.copy()
    changed.iloc[330:]*=np.linspace(1,2,len(changed)-330)[:,None]
    _,second,_=prepare_states(changed,PointInTimeMacro(path),SmartRegimePortfolio())
    for date,state in first.items():
        if date<dates[330]:
            assert state['signal']==second[date]['signal']
            assert np.array_equal(state['covariance'],second[date]['covariance'])
            assert 'IGOV' not in state['eligible']


def test_parameter_selection_does_not_use_future_scores():
    from optimize_smart_portfolio import choose_candidates

    policy=SmartRegimePortfolio()
    params=[{'growth_volatility_ceiling':.1,'momentum_risk_tilt':q} for q in [0.0,.3]]
    dates=pd.bdate_range('2010-01-01',periods=1010)
    bank={}
    for i in range(2):
        r=np.full(len(dates),.0001+i*.00001)
        bank[i]=pd.DataFrame({'return':r,'equity':np.cumprod(1+r),'cash':.1,'turnover':0.,'cost_as_initial_capital':0.},index=dates)
    before,_=choose_candidates(bank,params,policy)
    bank[0].loc[dates[756]:,'return']=.10
    bank[0]['equity']=(1+bank[0]['return']).cumprod()
    after,_=choose_candidates(bank,params,policy)
    assert before[0]==after[0]
    assert before[0]['training_end']<before[0]['evaluation_start']


def test_switching_state_restarts_and_duplicate_sessions_do_not_confirm_again():
    p=SmartRegimePortfolio()
    stamp='2024-01-16T21:00:00Z'
    macro={'ip_growth':3,'unemployment_change':-.2,'inflation_change':-1,'yield_curve':1,'as_of':stamp}
    market={'trend':1,'breadth':.8,'drawdown':-.02,'volatility':.12,'credit_relative':0,'as_of':stamp}
    first=p.classify(macro,market,decision_time=stamp)
    snapshot=p.export_state()
    assert p.classify(macro,market,decision_time=stamp)==first
    assert p.export_state()==snapshot
    restored=SmartRegimePortfolio()
    restored.restore_state(json.loads(json.dumps(snapshot)))
    assert restored.classify(macro,market,decision_time=stamp)==first
    with pytest.raises(AllocationError,match='one finalized'):
        restored.classify(macro,{**market,'drawdown':-.20},decision_time=stamp)
    snapshot['configuration_sha256']='wrong'
    with pytest.raises(AllocationError,match='mismatch'):
        restored.restore_state(snapshot)
