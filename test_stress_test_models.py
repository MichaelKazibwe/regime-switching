import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
import pytest

from assetuniverse import PRODUCTION_ASSETS
from compare_portfolio_models import build_targets
from diversifiedregimepolicy import DiversifiedRegimePolicy
from stress_test_models import block_indices, common_history, monte_carlo, parametric_projection


def test_preinception_prices_are_not_fabricated_and_internal_gaps_fail():
    dates=pd.bdate_range('2020-01-01',periods=10)
    raw=pd.DataFrame({'A':np.arange(10)+100.0,'B':[np.nan]*3+list(np.arange(7)+100.0)},index=dates)
    common=common_history(raw,('A','B'),end_before=dates[-1])
    assert common.index[0]==dates[3]
    assert common.index[-1]==dates[-2]
    raw.loc[dates[5],'A']=np.nan
    with pytest.raises(ValueError,match='Missing'):
        common_history(raw,('A','B'),end_before=dates[-1])


def test_circular_blocks_preserve_contiguous_observations():
    indices=block_indices(np.random.default_rng(5),23,20,3,7)
    assert indices.shape==(3,20)
    assert ((indices>=0)&(indices<23)).all()
    assert np.array_equal((indices[:,1:7]-indices[:,:6])%23,np.ones((3,6),dtype=int))
    with pytest.raises(ValueError):
        block_indices(np.random.default_rng(5),2,5,3,7)


def test_monte_carlo_constant_streams_have_exact_terminal_returns_and_drawdowns():
    returns=pd.DataFrame({'zero':np.zeros(252),'gain':np.full(252,.001),'loss':np.full(252,-.001)})
    result,details=monte_carlo(returns,paths=200,years=1,block_length=21,seed=10)
    result=result.set_index('model')
    assert result.loc['zero','median_final_1m']==pytest.approx(1e6)
    assert result.loc['zero','median_max_drawdown']==pytest.approx(0)
    assert result.loc['gain','median_final_1m']==pytest.approx(1e6*1.001**252)
    assert result.loc['gain','median_max_drawdown']==pytest.approx(0)
    assert result.loc['loss','median_max_drawdown']==pytest.approx(.999**252-1)
    assert result.loc['loss','probability_terminal_loss']==1
    assert len(details)==600


def test_joint_simulation_is_reproducible_and_identical_models_share_paths():
    rng=np.random.default_rng(101)
    stream=rng.normal(.0002,.008,300)
    returns=pd.DataFrame({'first':stream,'second':stream})
    first,paths1=monte_carlo(returns,paths=200,years=1,seed=22)
    second,paths2=monte_carlo(returns,paths=200,years=1,seed=22)
    pd.testing.assert_frame_equal(first,second)
    pd.testing.assert_frame_equal(paths1,paths2)
    a=paths1[paths1.model=='first'].terminal_factor.to_numpy()
    b=paths1[paths1.model=='second'].terminal_factor.to_numpy()
    assert np.array_equal(a,b)


def test_projection_rejects_invalid_observations_and_handles_zero_drift():
    returns=pd.DataFrame({'flat':np.zeros(252)})
    result=parametric_projection(returns)
    assert result.iloc[0].median_final_1m==pytest.approx(1e6)
    assert result.iloc[0].p05_final_1m==pytest.approx(1e6)
    with pytest.raises(ValueError):
        parametric_projection(returns,years=-1)
    returns.iloc[0,0]=-1.0
    with pytest.raises(ValueError):
        monte_carlo(returns,paths=100)


def test_production_only_history_does_not_require_or_invent_the_new_etfs():
    dates=mcal.get_calendar('NYSE').schedule('2007-08-01','2008-11-01').index
    rng=np.random.default_rng(441)
    prices=pd.DataFrame(100*np.exp(np.cumsum(rng.normal(.0003,.007,(len(dates),14)),axis=0)),
                        index=dates,columns=PRODUCTION_ASSETS)
    targets,audit=build_targets(prices,DiversifiedRegimePolicy(),include_diversified=False)
    assert set(targets)=={'14 production allocator*','14 equal weight','SPY buy and hold'}
    assert audit
    assert all('26_weights' not in row for row in audit)
    assert all(len(weights)==14 for weights in targets['14 equal weight'].values())
