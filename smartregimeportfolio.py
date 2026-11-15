"""Point-in-time macro/market allocation with explicit asset risk budgets.

Research only. Soft regime weights are uncalibrated allocation scores, not
probabilities of recession or future financial loss. No order authorization.
"""

from __future__ import annotations

import json
from copy import deepcopy
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf

from assetuniverse import DIVERSIFIED_ASSETS
from diversifiedregimepolicy import AllocationError, aware
from macrovintage import MacroVintageData

DEFAULT_SMART_CONFIG=Path(__file__).resolve().parent/'research/smart_regime_portfolio.json'
REGIMES=('disinflationary_growth','inflationary_growth','stagflation','deflationary_slowdown')


class PointInTimeMacro:
    def __init__(self, manifest_path):
        self.manifest=json.loads(Path(manifest_path).read_text())
        self.data={key:MacroVintageData.from_csv(Path(value['path']),expected_sha256=value['sha256'])
                   for key,value in self.manifest['series'].items()}
        if set(self.data)!={'UNRATE','CPIAUCSL','INDPRO','DGS10','DGS3MO'}:
            raise AllocationError('All five archived macro series are required')
        self.times={key:pd.DatetimeIndex(sorted(data.releases.available_at.unique())).as_unit('ns').asi8
                    for key,data in self.data.items()}
        self.cache={}

    def features(self, decision_time):
        stamp=aware(decision_time)
        views={}
        dates={}
        for key,data in self.data.items():
            signature=int(np.searchsorted(self.times[key],stamp.value,side='right'))
            if signature==0:
                raise AllocationError(f'Macro history unavailable: {key}')
            if key not in self.cache or self.cache[key][0]!=signature:
                self.cache[key]=(signature,data.as_of(stamp).dropna())
            series=self.cache[key][1]
            is_daily=key in {'DGS10','DGS3MO'}
            minimum=2 if is_daily else 16
            max_age=14 if is_daily else 90
            if len(series)<minimum or (stamp.tz_convert('America/New_York').date()-series.index[-1].date()).days>max_age:
                raise AllocationError(f'Macro series missing or stale: {key}')
            if not is_daily and not np.all(np.diff(series.index[-16:].to_period('M').asi8)==1):
                raise AllocationError(f'Nonconsecutive monthly macro history: {key}')
            views[key]=series
            dates[key]=str(series.index[-1].date())
        ip=views['INDPRO']
        cpi=views['CPIAUCSL']
        u=views['UNRATE']
        if (ip.iloc[-7:]<=0).any() or (cpi.iloc[-16:]<=0).any():
            raise AllocationError('Invalid nonpositive macro index')
        ip_growth=float(100*((ip.iloc[-1]/ip.iloc[-7])**2-1))
        unemployment=float(u.iloc[-3:].mean()-u.iloc[-6:-3].mean())
        inflation=float(100*(cpi.iloc[-1]/cpi.iloc[-13]-1))
        inflation_change=float(inflation-100*(cpi.iloc[-4]/cpi.iloc[-16]-1))
        yields=pd.concat([views['DGS10'],views['DGS3MO']],axis=1,join='inner').dropna()
        if yields.empty:
            raise AllocationError('No aligned released Treasury observations')
        curve=float(yields.iloc[-1,0]-yields.iloc[-1,1])
        return {'ip_growth':ip_growth,'unemployment_change':unemployment,'inflation_yoy':inflation,
                'inflation_change':inflation_change,'yield_curve':curve,'observation_dates':dates,
                'as_of':stamp.isoformat()}


def capped_distribution(preference, total, cap):
    p=np.asarray(preference,dtype=float)
    if p.size==0 or not np.isfinite(p).all() or (p<0).any() or p.sum()<=0 or total>len(p)*cap+1e-12:
        raise AllocationError('Infeasible capped risk distribution')
    values=np.zeros(len(p))
    available=np.ones(len(p),dtype=bool)
    remaining=float(total)
    for _ in range(len(p)+1):
        if remaining<=1e-14:
            break
        shares=p[available]/p[available].sum()*remaining
        indices=np.flatnonzero(available)
        over=shares>cap+1e-14
        if not over.any():
            values[indices]=shares
            break
        values[indices[over]]=cap
        available[indices[over]]=False
        remaining=total-values.sum()
    if not np.isclose(values.sum(),total,atol=1e-12) or values.max()>cap+1e-12:
        raise AllocationError('Risk distribution did not reconcile')
    return values


def solve_risk_budget(covariance, budgets):
    c=np.asarray(covariance,dtype=float)
    b=np.asarray(budgets,dtype=float)
    if (c.shape!=(len(b),len(b)) or not np.isfinite(c).all() or not np.isfinite(b).all()
            or not np.allclose(c,c.T,atol=1e-12) or np.linalg.eigvalsh(c).min()<=0
            or (b<=0).any() or not np.isclose(b.sum(),1,atol=1e-12)):
        raise AllocationError('Invalid covariance or asset risk budgets')
    c=c/np.trace(c)
    x=np.sqrt(b/np.diag(c))
    def objective(z):
        return .5*z@c@z-b@np.log(z)
    for _ in range(100):
        if np.max(np.abs(x*(c@x)-b))<1e-11:
            return x/x.sum()
        gradient=c@x-b/x
        direction=np.linalg.solve(c+np.diag(b/x**2),gradient)
        rate=1.0
        value=objective(x)
        for _ in range(60):
            candidate=x-rate*direction
            if (candidate>0).all() and objective(candidate)<=value-1e-4*rate*(gradient@direction)+1e-15:
                x=candidate
                break
            rate*=.5
        else:
            raise AllocationError('Risk-budget line search failed')
    raise AllocationError('Risk-budget optimization failed')


class SmartRegimePortfolio:
    def __init__(self, config_path=DEFAULT_SMART_CONFIG):
        self.config=json.loads(Path(config_path).read_text())
        self.configuration_sha256=hashlib.sha256(Path(config_path).read_bytes()).hexdigest()
        c=self.config
        if c.get('schema_version')!=1 or c.get('mode')!='RESEARCH_ONLY' or c.get('production_activation') is not False:
            raise AllocationError('Smart strategy must remain research-only')
        if not 0<c['risk_budget_tolerance']<=1e-6 or not 0<c['maximum_asset_weight']<=.25:
            raise AllocationError('Invalid risk-contract limits')
        if not 0<c['maximum_asset_risk_share']<=.25:
            raise AllocationError('Invalid individual asset risk cap')
        if c['stress_exposure_ceiling']>.4 or c['stress_volatility_ceiling']>.05:
            raise AllocationError('Stress limits cannot be relaxed')
        for key in ('probability_smoothing','switch_confidence','switch_advantage','normal_exposure_ceiling',
                    'neutral_exposure_ceiling','defensive_exposure_ceiling','stress_exposure_ceiling',
                    'stress_volatility_ceiling','neutral_volatility_ceiling','defensive_volatility_ceiling',
                    'daily_expected_shortfall_ceiling','stress_daily_expected_shortfall_ceiling','minimum_trade_notional'):
            if type(c[key]) not in (int,float) or not np.isfinite(c[key]) or not 0<c[key]<1:
                raise AllocationError(f'Invalid policy limit: {key}')
        if c['hard_account_drawdown'] is not None and not -1<c['hard_account_drawdown']<c['soft_account_drawdown']<0:
            raise AllocationError('Invalid account drawdown thresholds')
        if c.get('drawdown_control_window') is not None and (type(c['drawdown_control_window']) is not int or c['drawdown_control_window']<21):
            raise AllocationError('Invalid drawdown control reference window')
        assigned=[s for group in c['risk_groups'].values() for s in group]
        if (len(assigned)!=len(set(assigned)) or set(assigned)&set(c['excluded_from_risk_budget'])
                or set(assigned)|set(c['excluded_from_risk_budget'])!=set(DIVERSIFIED_ASSETS)):
            raise AllocationError('Risk groups must partition the declared universe')
        for budgets in c['economic_group_budgets'].values():
            if (set(budgets)!=set(c['risk_groups']) or not np.isfinite(list(budgets.values())).all()
                    or min(budgets.values())<=0 or not np.isclose(sum(budgets.values()),1)):
                raise AllocationError('Invalid economic group budgets')
        for key,values in c['candidate_grid'].items():
            if not values or len(values)!=len(set(values)) or any(type(v) not in (int,float) or not np.isfinite(v) or v<0 or v>1 for v in values):
                raise AllocationError(f'Invalid candidate values: {key}')
        self.probabilities=None
        self.normal_regime=REGIMES[0]
        self.pending=None
        self.confirmations=0
        self.residence=0
        self.stress=False
        self.last_decision_time=None
        self.last_fingerprint=None
        self.last_signal=None

    def export_state(self):
        return {'schema_version':1,'configuration_sha256':self.configuration_sha256,
                'probabilities':None if self.probabilities is None else self.probabilities.tolist(),
                'normal_regime':self.normal_regime,'pending':self.pending,'confirmations':self.confirmations,
                'residence':self.residence,'stress':self.stress,'last_decision_time':self.last_decision_time,
                'last_fingerprint':self.last_fingerprint,'last_signal':deepcopy(self.last_signal)}

    def restore_state(self, state):
        if state.get('schema_version')!=1 or state.get('configuration_sha256')!=self.configuration_sha256:
            raise AllocationError('State configuration or schema mismatch')
        p=state['probabilities']
        if p is not None and (len(p)!=4 or not np.isfinite(p).all() or min(p)<0 or not np.isclose(sum(p),1,atol=1e-12)):
            raise AllocationError('Invalid persisted regime scores')
        if (state['normal_regime'] not in REGIMES or state['pending'] not in (*REGIMES,None)
                or type(state['stress']) is not bool
                or any(type(state[k]) is not int or state[k]<0 for k in ('confirmations','residence'))):
            raise AllocationError('Invalid persisted switching state')
        if p is not None:
            stamp=aware(state['last_decision_time']).isoformat()
            if (not isinstance(state['last_signal'],dict) or state['last_signal'].get('as_of')!=stamp
                    or state['last_signal'].get('regime') not in (*REGIMES,'crisis')
                    or not isinstance(state['last_fingerprint'],str)):
                raise AllocationError('Incomplete persisted decision state')
        self.probabilities=None if p is None else np.array(p,dtype=float)
        for key in ('normal_regime','pending','confirmations','residence','stress','last_decision_time','last_fingerprint','last_signal'):
            setattr(self,key,deepcopy(state[key]))

    def classify(self, macro, market, *, decision_time):
        if aware(macro['as_of'])>aware(decision_time):
            raise AllocationError('Macro input contains future information')
        if aware(market['as_of'])>aware(decision_time):
            raise AllocationError('Market input contains future information')
        if any((aware(decision_time)-aware(source)).total_seconds()>4*86400 for source in (macro['as_of'],market['as_of'])):
            raise AllocationError('Regime features are stale')
        stamp=aware(decision_time)
        fingerprint=hashlib.sha256(json.dumps([macro,market],sort_keys=True,allow_nan=False).encode()).hexdigest()
        if self.last_decision_time is not None:
            prior=aware(self.last_decision_time)
            if stamp<prior:
                raise AllocationError('Regime decisions must be chronological')
            if stamp.tz_convert('America/New_York').date()==prior.tz_convert('America/New_York').date():
                if stamp!=prior or fingerprint!=self.last_fingerprint:
                    raise AllocationError('Only one finalized regime observation per session is supported')
                return deepcopy(self.last_signal)
        numeric=[macro[k] for k in ('ip_growth','unemployment_change','inflation_change','yield_curve')]
        numeric += [market[k] for k in ('trend','breadth','drawdown','volatility','credit_relative')]
        if not np.isfinite(numeric).all():
            raise AllocationError('Nonfinite regime features')
        growth=(.5*np.tanh(macro['ip_growth']/4)-.3*np.tanh(macro['unemployment_change']/.3)
                +.2*np.tanh(macro['yield_curve']/.75))
        growth+=.25*np.tanh(market['trend'])+.15*(2*market['breadth']-1)
        inflation=np.tanh(macro['inflation_change'])
        p_growth=1/(1+np.exp(-2*growth))
        p_inflation=1/(1+np.exp(-2*inflation))
        raw=np.array([p_growth*(1-p_inflation),p_growth*p_inflation,
                      (1-p_growth)*p_inflation,(1-p_growth)*(1-p_inflation)])
        a=self.config['probability_smoothing']
        self.probabilities=raw if self.probabilities is None else (1-a)*self.probabilities+a*raw
        label=REGIMES[int(np.argmax(self.probabilities))]
        current=REGIMES.index(self.normal_regime)
        self.residence+=1
        confident=(self.probabilities.max()>=self.config['switch_confidence']
                   and self.probabilities.max()-self.probabilities[current]>=self.config['switch_advantage'])
        if label!=self.normal_regime and confident:
            self.confirmations=self.confirmations+1 if self.pending==label else 1
            self.pending=label
            if self.confirmations>=self.config['switch_confirmation_sessions'] and self.residence>=self.config['minimum_residence_sessions']:
                self.normal_regime=label
                self.residence=0
                self.confirmations=0
        else:
            self.confirmations=0
            self.pending=None
        if self.stress:
            self.stress=not(market['drawdown']>-.07 and market['volatility']<.20 and market['credit_relative']>-.03)
        else:
            self.stress=(market['drawdown']<=-.10 or market['volatility']>=.25
                         or (market['credit_relative']<=-.05 and market['breadth']<.4))
        result={'regime':'crisis' if self.stress else self.normal_regime,'stress':bool(self.stress),
                'probabilities':dict(zip(REGIMES,map(float,self.probabilities))),
                'growth_score':float(growth),'inflation_score':float(inflation),
                'growth_weight':float(self.probabilities[:2].sum()),'as_of':aware(decision_time).isoformat()}
        self.last_decision_time=stamp.isoformat()
        self.last_fingerprint=fingerprint
        self.last_signal=deepcopy(result)
        return result

    def risk_limits(self, signal, parameters, account_drawdown):
        c=self.config
        growth=signal['growth_weight']
        exposure=c['normal_exposure_ceiling'] if growth>.65 else c['neutral_exposure_ceiling'] if growth>.45 else c['defensive_exposure_ceiling']
        ceiling=parameters['growth_volatility_ceiling'] if growth>.65 else c['neutral_volatility_ceiling'] if growth>.45 else c['defensive_volatility_ceiling']
        if signal['stress']:
            exposure=min(exposure,c['stress_exposure_ceiling'])
            ceiling=min(ceiling,c['stress_volatility_ceiling'])
        if c['soft_account_drawdown'] is not None and account_drawdown<=c['soft_account_drawdown']:
            exposure=min(exposure,.60)
            ceiling=min(ceiling,.07)
        if c['hard_account_drawdown'] is not None and account_drawdown<=c['hard_account_drawdown']:
            exposure=min(exposure,.25)
            ceiling=min(ceiling,.04)
        return exposure,ceiling

    def allocate(self, returns, signal, parameters, *, account_drawdown, decision_time):
        if aware(signal['as_of'])>aware(decision_time):
            raise AllocationError('Future allocation signal')
        if (set(parameters)!=set(self.config['candidate_grid'])
                or any(type(parameters[k]) not in (int,float) or parameters[k] not in self.config['candidate_grid'][k] for k in parameters)):
            raise AllocationError('Unknown predeclared parameters')
        if not -1<=account_drawdown<=0:
            raise AllocationError('Invalid account drawdown')
        if (not isinstance(returns,pd.DataFrame) or not isinstance(returns.index,pd.DatetimeIndex)
                or not returns.index.is_unique or not returns.index.is_monotonic_increasing or not returns.columns.is_unique
                or len(returns)<252 or not np.isfinite(returns.to_numpy()).all() or (returns<=-1).any().any()):
            raise AllocationError('Complete past-only eligible-asset history is required')
        probabilities=signal['probabilities']
        if (set(probabilities)!=set(REGIMES) or not np.isfinite(list(probabilities.values())).all()
                or min(probabilities.values())<0 or not np.isclose(sum(probabilities.values()),1,atol=1e-12)
                or type(signal['stress']) is not bool or not np.isclose(signal['growth_weight'],sum(probabilities[r] for r in REGIMES[:2]),atol=1e-12)):
            raise AllocationError('Invalid normalized regime scores')
        last=pd.Timestamp(returns.index[-1]).date()
        if last>aware(decision_time).tz_convert('America/New_York').date():
            raise AllocationError('Return history contains future sessions')
        c=self.config
        groups=c['risk_groups']
        eligible=set(returns.columns)
        if not eligible<=set(DIVERSIFIED_ASSETS) or not all(eligible&set(group) for group in groups.values()):
            raise AllocationError('Every economic risk group needs eligible instruments')
        matrix=returns.to_numpy()
        std=matrix.std(axis=0,ddof=0)
        if (std<=1e-12).any():
            raise AllocationError('Zero-variance instruments cannot receive risk budgets')
        estimate=LedoitWolf().fit((matrix-matrix.mean(axis=0))/std).covariance_
        correlation=estimate/np.sqrt(np.outer(np.diag(estimate),np.diag(estimate)))
        covariance=correlation*np.outer(std,std)*252
        if signal['stress']:
            group_budgets=c['economic_group_budgets']['crisis']
        else:
            group_budgets={g:sum(signal['probabilities'][r]*c['economic_group_budgets'][r][g] for r in REGIMES) for g in groups}
        budgets={s:0.0 for s in returns.columns}
        for group,members in groups.items():
            symbols=[s for s in members if s in eligible]
            if group=='equities':
                core=[s for s in symbols if s in c['core_equity_risk_weights']]
                satellites=[s for s in symbols if s not in core]
                preference=np.array([.7*c['core_equity_risk_weights'][s]/sum(c['core_equity_risk_weights'][t] for t in core)
                                     if s in core else .3/len(satellites) for s in symbols])
                if not satellites:
                    preference/=preference.sum()
                horizon=returns.iloc[-126:-21][symbols]
                momentum=np.log1p(horizon).sum().to_numpy()/(returns[symbols].std().to_numpy()*np.sqrt(len(horizon)))
                tilt=np.exp(np.clip(momentum,-2,2))
                tilt/=tilt.sum()
                q=parameters['momentum_risk_tilt']
                preference=(1-q)*preference+q*tilt
            elif group=='nominal_bonds':
                preference=np.array([{'TLT':.3,'IEF':.4,'IGOV':.3}[s] for s in symbols])
            elif group=='inflation_sensitive':
                tip=parameters.get('tip_risk_preference',.4)
                preference=np.array([{'GLD':(1-tip)/2,'DBC':(1-tip)/2,'TIP':tip}[s] for s in symbols])
            else:
                high_yield=.05+.25*signal['growth_weight']
                preference=np.array([high_yield if s=='HYG' else 1-high_yield for s in symbols])
            shares=capped_distribution(preference,group_budgets[group],c['maximum_asset_risk_share'])
            budgets.update(dict(zip(symbols,map(float,shares))))
        active=[s for s in returns if budgets[s]>0]
        indices=[returns.columns.get_loc(s) for s in active]
        cov=covariance[np.ix_(indices,indices)]
        b=np.array([budgets[s] for s in active])
        unit=solve_risk_budget(cov,b)
        exposure,ceiling=self.risk_limits(signal,parameters,account_drawdown)
        volatility=float(np.sqrt(unit@cov@unit))
        losses=-(returns[active].to_numpy()@unit)
        tail=np.sort(losses)[-max(1,int(np.ceil(.05*len(losses)))):]
        es=max(float(tail.mean()),0.0)
        es_limit=c['stress_daily_expected_shortfall_ceiling'] if signal['stress'] else c['daily_expected_shortfall_ceiling']
        scale=min(exposure,ceiling/volatility,c['maximum_asset_weight']/unit.max(),es_limit/es if es else 1.0)
        w=unit*scale
        risk=w*(cov@w)/float(w@cov@w)
        error=float(np.max(np.abs(risk-b)))
        if error>c['risk_budget_tolerance']:
            raise AllocationError('Strict asset risk-budget validation failed')
        full={s:0.0 for s in DIVERSIFIED_ASSETS}
        full.update(dict(zip(active,map(float,w))))
        return {'mode':'RESEARCH_ONLY','weights':full,'cash':float(1-w.sum()),'regime':signal['regime'],
                'asset_risk_targets':dict(zip(active,map(float,b))),'asset_risk_shares':dict(zip(active,map(float,risk))),
                'group_risk_targets':group_budgets,'risk_budget_error':error,'estimated_volatility':volatility*scale,
                'estimated_daily_es95':es*scale,'exposure_ceiling':exposure,'volatility_ceiling':ceiling,
                'active_assets':active,'decision_time':aware(decision_time).isoformat()}
