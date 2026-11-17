from copy import deepcopy
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from macro_alpha import components, predict, record
from strategy_integrity import fingerprint


def history(n=300):
    dates=pd.bdate_range('2025-01-01',periods=n)
    return [dict(date=str(d.date()),macro_valid=True,ip_growth=float(1 if i%4<2 else -1),
                 unemployment_change=0.,inflation_change=float(1 if i%2 else -1),yield_curve=i/1000)
            for i,d in enumerate(dates)]


def test_partial_model_excludes_missing_features_and_preserves_label_purge():
    rows=history()
    current=dict(ip_growth=1.,unemployment_change=0.,yield_curve=.2)
    settings=dict(horizon_sessions=10,training_sessions=200,minimum_training=20,regularization_C=1.,probability_shrink=.25)
    result=predict(rows,current,settings)
    assert result['feature_names']==sorted(current)
    assert result['last_training_label_date'] < rows[-1]['date']
    assert np.isclose(sum(result['probabilities']),1)
    assert np.min(result['probabilities'])>=0
    changed=deepcopy(rows)
    changed[-1].update(ip_growth=-500.,inflation_change=500.)
    assert predict(changed,current,settings)==result
    assert predict(rows,{},settings)['probabilities'] is None


def test_missing_cpi_keeps_other_valid_components_without_filling():
    monthly=pd.date_range('2025-01-01','2026-10-01',freq='MS')
    views={k:pd.Series(100.+np.arange(len(monthly)),index=monthly) for k in ['UNRATE','INDPRO','CPIAUCSL']}
    views['CPIAUCSL']=views['CPIAUCSL'].drop(pd.Timestamp('2025-10-01'))
    for k,v in [('DGS10',4.),('DGS3MO',3.)]:
        views[k]=pd.Series([v],index=pd.to_datetime(['2026-11-13']))
    values,missing,periods=components(views,'2026-11-16T21:00:00Z')
    assert set(values)=={'ip_growth','unemployment_change','yield_curve'}
    assert values['yield_curve']==1.
    assert '2025-10' in missing['inflation_change']
    assert 'CPIAUCSL' not in periods
    views['DGS10']=pd.Series([4.],index=pd.to_datetime(['2026-10-01']))
    assert 'yield_curve' in components(views,'2026-11-16T21:00:00Z')[1]


def forecast(session):
    result=dict(market_session=session,as_of=session+'T21:00:00+00:00',protocol_id='a'*64,
                prediction=dict(probabilities=[.4,.3,.2,.1],baseline=[.25]*4,settings=dict(horizon_sessions=3)))
    result['forecast_id']=fingerprint(result)
    return result


def test_receipts_idempotent_no_backfill_no_rewrite_and_mature_only(tmp_path):
    rows=history()
    rows=[{**rows[i], 'date':str(d.date())} for i,d in enumerate(pd.bdate_range('2026-11-10','2026-11-16'))]
    first=forecast('2026-11-10')
    now=datetime(2026,11,10,22,tzinfo=timezone.utc)
    original=record(first,rows[:1],tmp_path,now=now)
    assert original['pending']==1 and original['matured']==0
    assert record(first,rows[:1],tmp_path,now=now)==original
    with pytest.raises(ValueError,match='genuine'):
        record(first,rows,tmp_path,now=datetime(2026,11,16,22,tzinfo=timezone.utc))
    changed=deepcopy(first)
    changed['prediction']['probabilities']=[.1,.2,.3,.4]
    changed['forecast_id']=fingerprint({k:v for k,v in changed.items() if k!='forecast_id'})
    with pytest.raises(ValueError,match='already sealed'):
        record(changed,rows,tmp_path,now=now)
    second=forecast('2026-11-16')
    result=record(second,rows,tmp_path,now=datetime(2026,11,16,22,tzinfo=timezone.utc))
    assert result['observed_forecasts']==2 and result['matured']==1 and result['pending']==1
    assert result['outcomes'][0]['outcome_session']=='2026-11-13'
    assert not result['alpha_established']
    rows[3]['macro_valid']=False
    unavailable=record(second,rows,tmp_path,now=datetime(2026,11,16,22,tzinfo=timezone.utc))
    assert unavailable['matured']==0 and unavailable['matured_unscorable']==1
    assert unavailable['observed_forecasts']==2
