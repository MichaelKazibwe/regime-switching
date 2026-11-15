import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
import pytest

from assetuniverse import DIVERSIFIED_ASSETS
from compare_portfolio_models import build_targets, rebalance_fee, simulate
from diversifiedregimepolicy import DiversifiedRegimePolicy


def test_next_close_execution_does_not_receive_the_pre_execution_return():
    dates=pd.date_range('2025-01-01',periods=3)
    returns=pd.DataFrame({'ETF':[.10,.20,.30]},index=dates)
    results=simulate(returns,{dates[1]:np.array([1.0])},cost_rate=0,
                     cash_returns=pd.Series(0.0,index=dates))
    assert results['return'].tolist() == pytest.approx([0,0,.30])
    assert results.equity.iloc[-1] == pytest.approx(1.30)


def test_transaction_fees_balance_actual_cash_and_dollars_traded():
    current=np.array([.2,.4])
    target=np.array([.5,.25])
    rate=.003
    fee=rebalance_fee(current,target,rate)
    actual_trade=target*(1-fee)-current
    assert fee == pytest.approx(rate*np.abs(actual_trade).sum(),abs=1e-13)
    final_cash=.4-actual_trade.sum()-fee
    assert final_cash == pytest.approx((1-target.sum())*(1-fee),abs=1e-13)


def test_initial_fill_and_rebalance_use_drifted_holdings_for_costs():
    dates=pd.date_range('2025-01-01',periods=2)
    returns=pd.DataFrame({'ETF':[0,.2]},index=dates)
    targets={date:np.array([.5]) for date in dates}
    frame=simulate(returns,targets,cost_rate=.0015,cash_returns=pd.Series(0.0,index=dates))
    entry_fee=.0015*.5/(1+.0015*.5)
    assert frame.equity.iloc[0] == pytest.approx(1-entry_fee)
    assert frame.turnover.iloc[1] > 0
    assert frame.equity.iloc[-1] < (1-entry_fee)*1.10
    assert frame.cash.iloc[-1] == pytest.approx(.5)


def test_future_price_changes_cannot_change_prior_targets():
    dates=mcal.get_calendar('NYSE').schedule('2023-01-01','2024-08-01').index
    rng=np.random.default_rng(218)
    returns=rng.normal(.0003,.008,(len(dates),len(DIVERSIFIED_ASSETS)))
    prices=pd.DataFrame(100*np.exp(np.cumsum(returns,axis=0)),index=dates,columns=DIVERSIFIED_ASSETS)
    modified=prices.copy()
    modified.iloc[330:]*=np.linspace(1,2,len(modified)-330)[:,None]
    first,_=build_targets(prices,DiversifiedRegimePolicy())
    second,_=build_targets(modified,DiversifiedRegimePolicy())
    comparisons=0
    for name,targets in first.items():
        for date,target in targets.items():
            if date < dates[330]:
                assert date in second[name]
                assert np.allclose(target,second[name][date],atol=1e-12,rtol=0)
                comparisons+=1
    assert comparisons >= 10
