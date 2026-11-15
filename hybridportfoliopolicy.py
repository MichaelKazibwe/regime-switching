"""Research-only capital ensemble of validated parent allocations.

Parent risk budgets do not survive blending as an account-level budget.
This composite has its own explicit position, cash and volatility constraints
and cannot authorize execution through the production pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf

from assetuniverse import DIVERSIFIED_ASSETS, PRODUCTION_ASSETS
from diversifiedregimepolicy import AllocationError, aware

DEFAULT_HYBRID_CONFIG = Path(__file__).resolve().parent / 'research/hybrid_portfolio.json'


def scale_preserving_covariance(returns):
    """Shrink correlations; retain each asset's separately estimated variance."""
    if (not isinstance(returns,pd.DataFrame) or tuple(returns.columns) != DIVERSIFIED_ASSETS
            or len(returns) < 252 or not np.isfinite(returns.to_numpy()).all()):
        raise AllocationError('Covariance requires at least 252 complete canonical returns')
    values=returns.to_numpy()
    centered=values-values.mean(axis=0)
    std=centered.std(axis=0,ddof=0)
    if (std <= 1e-12).any():
        raise AllocationError('Cannot estimate risk for an asset with zero historical variance')
    estimate=LedoitWolf().fit(centered/std).covariance_
    correlation=estimate/np.sqrt(np.outer(np.diag(estimate),np.diag(estimate)))
    covariance=correlation*np.outer(std,std)*252
    return pd.DataFrame(covariance,index=DIVERSIFIED_ASSETS,columns=DIVERSIFIED_ASSETS)


class HybridPortfolioPolicy:
    def __init__(self, config_path=DEFAULT_HYBRID_CONFIG):
        self.config=json.loads(Path(config_path).read_text())
        c=self.config
        if c.get('mode') != 'RESEARCH_ONLY' or c.get('production_activation') is not False or c.get('schema_version') != 1:
            raise AllocationError('Hybrid policy must remain research-only')
        for key in ('maximum_asset_weight','minimum_normal_cash','defensive_exposure_ceiling',
                    'defensive_volatility_ceiling','stress_exposure_ceiling','stress_volatility_ceiling','minimum_trade_notional'):
            if type(c[key]) not in (int,float) or not np.isfinite(c[key]) or not 0 < c[key] < 1:
                raise AllocationError(f'Invalid hybrid limit: {key}')
        if c['maximum_asset_weight'] > .25 or c['stress_exposure_ceiling'] > .4 or c['stress_volatility_ceiling'] > .05:
            raise AllocationError('Hybrid limits cannot loosen position or stress ceilings')
        if c['covariance_window'] < 252 or c['training_sessions'] < 252:
            raise AllocationError('At least 252 estimation and selection observations are required')
        if type(c['selection_interval_sessions']) is not int or c['selection_interval_sessions'] <= 0:
            raise AllocationError('Invalid chronological selection interval')
        grid=c['candidate_grid']
        if set(grid) != {'growth_model_fraction','defensive_model_fraction','growth_volatility_ceiling'}:
            raise AllocationError('Invalid hybrid candidate grid')
        for key,values in grid.items():
            if (not values or any(type(v) not in (int,float) or not np.isfinite(v) or v < 0 or v > 1 for v in values)
                    or len(set(values)) != len(values)):
                raise AllocationError('Invalid or duplicate hybrid grid choices')
        if any(not 0 < v <= .15 for v in grid['growth_volatility_ceiling']):
            raise AllocationError('Invalid growth volatility ceiling')
        if type(c['maximum_source_age_days']) is not int or not 0 < c['maximum_source_age_days'] <= 35:
            raise AllocationError('Invalid parent observation age limit')

    @staticmethod
    def _weights(mapping, *, production=False):
        expected=set(PRODUCTION_ASSETS if production else DIVERSIFIED_ASSETS)
        if (not isinstance(mapping,dict) or set(mapping) != expected
                or any(type(v) not in (int,float) or not np.isfinite(v) or v < 0 for v in mapping.values())
                or sum(mapping.values()) > 1+1e-10 or max(mapping.values()) > .25+1e-10):
            raise AllocationError('Invalid parent capital allocation')
        return np.array([mapping.get(s,0.0) for s in DIVERSIFIED_ASSETS])

    def allocate(self, parent14, parent26, covariance, parameters, *, uptrend, stress,
                 decision_time, sources_available_at, covariance_as_of):
        if aware(sources_available_at) > aware(decision_time):
            raise AllocationError('Parent allocations cannot be used before they are available')
        if aware(covariance_as_of) > aware(decision_time):
            raise AllocationError('Covariance cannot include future observations')
        if (aware(decision_time)-aware(sources_available_at)).total_seconds() > self.config['maximum_source_age_days']*86400:
            raise AllocationError('Parent allocations are stale')
        if type(uptrend) is not bool or type(stress) is not bool:
            raise AllocationError('Trend and stress flags must be boolean')
        if (not isinstance(covariance,pd.DataFrame) or tuple(covariance.index) != DIVERSIFIED_ASSETS
                or tuple(covariance.columns) != DIVERSIFIED_ASSETS):
            raise AllocationError('Hybrid covariance must use the canonical research order')
        matrix=covariance.to_numpy()
        if (not np.isfinite(matrix).all() or not np.allclose(matrix,matrix.T,atol=1e-12,rtol=1e-10)
                or np.linalg.eigvalsh(matrix).min() < -1e-10):
            raise AllocationError('Invalid hybrid covariance')
        grid=self.config['candidate_grid']
        if (set(parameters) != set(grid)
                or any(type(parameters[k]) not in (int,float) or parameters[k] not in grid[k] for k in grid)):
            raise AllocationError('Parameters must belong to the predeclared candidate grid')
        w26=self._weights(parent26)
        w14=self._weights(parent14,production=True) if parent14 is not None else np.zeros(len(w26))
        fraction=parameters['growth_model_fraction'] if uptrend and not stress else parameters['defensive_model_fraction']
        if parent14 is None:
            fraction=0.0
        weights=fraction*w14+(1-fraction)*w26
        c=self.config
        exposure=1-c['minimum_normal_cash']
        ceiling=parameters['growth_volatility_ceiling']
        if not uptrend:
            exposure=min(exposure,c['defensive_exposure_ceiling'])
            ceiling=min(ceiling,c['defensive_volatility_ceiling'])
        if stress:
            exposure=min(exposure,c['stress_exposure_ceiling'])
            ceiling=min(ceiling,c['stress_volatility_ceiling'])
        variance=float(weights@matrix@weights)
        if weights.sum() <= 0 or variance <= 0:
            raise AllocationError('Hybrid requires a nonzero risk-bearing allocation')
        scale=min(1.0,exposure/weights.sum(),c['maximum_asset_weight']/weights.max(),ceiling/np.sqrt(variance))
        weights*=scale
        return {'mode':'RESEARCH_ONLY','weights':weights,'cash':float(1-weights.sum()),
                'parent14_fraction':fraction,'estimated_volatility':float(np.sqrt(weights@matrix@weights)),
                'exposure_ceiling':exposure,'volatility_ceiling':ceiling,
                'uptrend':uptrend,'stress':stress,'decision_time':aware(decision_time).isoformat()}
