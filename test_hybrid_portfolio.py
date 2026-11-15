import json

import numpy as np
import pandas as pd
import pytest

from assetuniverse import DIVERSIFIED_ASSETS, PRODUCTION_ASSETS
from diversifiedregimepolicy import AllocationError
from hybridportfoliopolicy import DEFAULT_HYBRID_CONFIG, HybridPortfolioPolicy, scale_preserving_covariance
from optimize_hybrid_portfolio import hybrid_simulation, parameter_grid, select_parameters, selected_schedule


def inputs():
    policy=HybridPortfolioPolicy()
    w14=dict.fromkeys(PRODUCTION_ASSETS,1/len(PRODUCTION_ASSETS))
    w26=dict.fromkeys(DIVERSIFIED_ASSETS,1/len(DIVERSIFIED_ASSETS))
    cov=pd.DataFrame(np.eye(26)*.04,index=DIVERSIFIED_ASSETS,columns=DIVERSIFIED_ASSETS)
    times={'decision_time':'2025-01-15T21:00:00Z','sources_available_at':'2025-01-02T21:00:00Z',
           'covariance_as_of':'2025-01-15T21:00:00Z'}
    return policy,w14,w26,cov,times


@pytest.mark.parametrize('uptrend,stress',[(True,False),(False,False),(True,True),(False,True)])
def test_all_hybrid_candidates_obey_accounting_and_risk_ceilings(uptrend,stress):
    policy,w14,w26,cov,times=inputs()
    for params in parameter_grid(policy):
        r=policy.allocate(w14,w26,cov,params,uptrend=uptrend,stress=stress,**times)
        w=r['weights']
        assert r['mode']=='RESEARCH_ONLY'
        assert w.min()>=0
        assert w.max()<=.25+1e-10
        assert w.sum()+r['cash']==pytest.approx(1)
        assert w.sum()<=r['exposure_ceiling']+1e-10
        assert np.sqrt(w@cov.to_numpy()@w)<=r['volatility_ceiling']+1e-10
        if stress:
            assert r['cash']>=.60-1e-10


def test_rejected_parent_uses_diversified_source_without_a_budget_bypass():
    policy,_,w26,cov,times=inputs()
    result=policy.allocate(None,w26,cov,parameter_grid(policy)[-1],uptrend=True,stress=False,**times)
    assert result['parent14_fraction']==0
    assert np.allclose(result['weights']/result['weights'].sum(),np.full(26,1/26))


def test_unknown_assets_future_information_and_stale_sources_fail_closed():
    policy,w14,w26,cov,times=inputs()
    params=parameter_grid(policy)[0]
    for replacement in ({'sources_available_at':'2025-01-16T21:00:00Z'},
                        {'covariance_as_of':'2025-01-16T21:00:00Z'},
                        {'sources_available_at':'2024-10-01T21:00:00Z'}):
        with pytest.raises(AllocationError):
            policy.allocate(w14,w26,cov,params,uptrend=True,stress=False,**{**times,**replacement})
    with pytest.raises(AllocationError,match='parent capital'):
        policy.allocate(w14,{**w26,'UNKNOWN':.01},cov,params,uptrend=True,stress=False,**times)


def test_correlation_shrinkage_preserves_treasury_bill_variance_scale():
    rng=np.random.default_rng(45)
    scales=np.linspace(.006,.018,26)
    scales[list(DIVERSIFIED_ASSETS).index('SGOV')]=.00015
    returns=pd.DataFrame(rng.normal(size=(300,26))*scales,columns=DIVERSIFIED_ASSETS)
    cov=scale_preserving_covariance(returns)
    empirical=returns.var(ddof=0)*252
    assert np.allclose(np.diag(cov),empirical.to_numpy(),rtol=1e-12)
    assert np.linalg.eigvalsh(cov).min()>0
    assert np.sqrt(cov.loc['SGOV','SGOV'])<.005
    with pytest.raises(AllocationError):
        scale_preserving_covariance(returns.iloc[:100])


def test_parameter_selection_cannot_see_changed_future_performance():
    policy=HybridPortfolioPolicy()
    candidates=parameter_grid(policy)
    dates=pd.bdate_range('2023-01-01',periods=520)
    frames={}
    for i in range(len(candidates)):
        returns=np.full(len(dates),.0001+i*.00001)
        frames[i]=pd.DataFrame({'return':returns,'equity':np.cumprod(1+returns),'cash':.1,
                                'turnover':0.0,'cost_as_initial_capital':0.0},index=dates)
    selections,_=select_parameters(frames,candidates,policy)
    changed={i:frame.copy() for i,frame in frames.items()}
    changed[0].loc[dates[252]:,'return']=.10
    changed[0]['equity']=(1+changed[0]['return']).cumprod()
    altered,_=select_parameters(changed,candidates,policy)
    assert selections[0]==altered[0]
    assert pd.Timestamp(selections[0]['training_end'])<pd.Timestamp(selections[0]['evaluation_start'])
    assert selected_schedule(dates[0],selections,candidates)==candidates[0]


def test_hybrid_configuration_cannot_enable_production(tmp_path):
    config=json.loads(DEFAULT_HYBRID_CONFIG.read_text())
    config['production_activation']=True
    path=tmp_path/'hybrid.json'
    path.write_text(json.dumps(config))
    with pytest.raises(AllocationError,match='research-only'):
        HybridPortfolioPolicy(path)


def test_hybrid_executes_after_old_holdings_accrue_the_next_session_return():
    policy,w14,w26,cov,_=inputs()
    dates=pd.bdate_range('2023-01-01',periods=255)
    prices=pd.DataFrame(100.0,index=dates,columns=DIVERSIFIED_ASSETS)
    prices.iloc[253]=110.0
    prices.iloc[254]=132.0
    states={}
    for i in (252,253):
        stamp=dates[i].tz_localize('UTC')+pd.Timedelta(hours=21)
        states[dates[i]]={'parent14':w14,'parent26':w26,'covariance':cov,'uptrend':True,'stress':False,
                          'decision_time':stamp,'sources_available_at':stamp}
    parameters={'growth_model_fraction':1.0,'defensive_model_fraction':0.0,'growth_volatility_ceiling':.12}
    result,decisions=hybrid_simulation(prices,states,policy,lambda date:parameters,cost_rate=0)
    assert result['return'].iloc[0]==pytest.approx(0)
    assert result['return'].iloc[1]==pytest.approx(.98*.20)
    assert decisions[0]['decision_date']<decisions[0]['execution_date']
