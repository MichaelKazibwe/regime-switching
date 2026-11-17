import json

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
import pytest

from diversifiedregimepolicy import AllocationError, DiversifiedRegimePolicy, DEFAULT_CONFIG, DEFAULT_ASSET_CATALOG


@pytest.fixture
def policy():
    return DiversifiedRegimePolicy()


def covariance(policy):
    volatility = np.array([.18,.24,.25,.20,.25,.16,.07,.02,.08,.14,.15,.30,.20,.22,
                           .07,.09,.003,.20,.15,.25,.15,.20,.22,.25,.20,.20])
    volatility = np.r_[volatility, np.full(max(0,len(policy.assets)-len(volatility)),.20)][:len(policy.assets)]
    n=len(policy.assets)
    correlation = .25*np.ones((n,n))+.75*np.eye(n)
    return pd.DataFrame(correlation*np.outer(volatility,volatility),index=policy.assets,columns=policy.assets)


@pytest.mark.parametrize("regime",["disinflationary_growth","inflationary_growth","stagflation","deflationary_slowdown"])
@pytest.mark.parametrize("risk_off",[False,True])
def test_allocations_meet_group_risk_budgets_cash_volatility_and_concentration(policy,regime,risk_off):
    result = policy.allocate(regime,covariance(policy),decision_time="2026-10-30T12:00:00Z",covariance_as_of="2026-10-29T20:00:00Z",risk_off=risk_off)
    weights = result["capital_weights"]
    assert result["mode"] == "RESEARCH_ONLY"
    assert tuple(weights) == policy.assets
    assert all(0 <= value <= policy.config["maximum_asset_weight"]+1e-10 for value in weights.values())
    assert sum(weights.values())+result["cash_weight"] == pytest.approx(1)
    assert result["cash_weight"] >= policy.config["regimes"][regime]["minimum_cash"]-1e-10
    assert result["estimated_annual_volatility"] <= result["volatility_ceiling"]+1e-10
    assert sum(result["asset_risk_shares"].values()) == pytest.approx(1)
    assert result["risk_budget_error"] <= 1e-6
    for group,target in result["group_risk_targets"].items():
        assert result["group_risk_shares"][group] == pytest.approx(target,abs=1e-6)
    if risk_off:
        assert result["gross_asset_exposure"] <= .40+1e-10
        assert result["cash_weight"] >= .60-1e-10
        assert result["estimated_annual_volatility"] <= .05+1e-10


def test_selection_uses_available_signals_and_deadband_hysteresis(policy):
    kwargs={"decision_time":"2026-10-30T12:00:00Z","observations_available_at":"2026-10-29T12:00:00Z"}
    assert policy.classify(1,-1,**kwargs) == "disinflationary_growth"
    assert policy.classify(1,1,**kwargs) == "inflationary_growth"
    assert policy.classify(-1,1,**kwargs) == "stagflation"
    assert policy.classify(-1,-1,**kwargs) == "deflationary_slowdown"
    assert policy.classify(.02,-.02,previous_regime="stagflation",**kwargs) == "stagflation"
    with pytest.raises(AllocationError,match="Ambiguous"):
        policy.classify(0,0,**kwargs)
    with pytest.raises(AllocationError,match="unavailable"):
        policy.classify(1,1,**{**kwargs,"observations_available_at":"2026-10-31T12:00:00Z"})


def test_stress_entry_and_exit_do_not_chatter_at_the_same_threshold(policy):
    assert policy.stress_state(-.11,.15) is True
    assert policy.stress_state(-.08,.21,previous=True) is True
    assert policy.stress_state(-.06,.19,previous=True) is False
    assert policy.stress_state(-.01,.26) is True
    with pytest.raises(AllocationError):
        policy.stress_state(float("nan"),.2)


def test_covariance_rejects_future_labels_and_degenerate_risk_groups(policy):
    matrix=covariance(policy)
    with pytest.raises(AllocationError,match="after the decision"):
        policy.allocate("stagflation",matrix,decision_time="2026-10-29T12:00:00Z",covariance_as_of="2026-10-30T20:00:00Z")
    with pytest.raises(AllocationError,match="labels/order"):
        policy.allocate("stagflation",matrix.iloc[::-1],decision_time="2026-10-30T12:00:00Z",covariance_as_of="2026-10-29T20:00:00Z")
    with pytest.raises(AllocationError,match="positive definite"):
        policy.allocate("stagflation",matrix*0,decision_time="2026-10-30T12:00:00Z",covariance_as_of="2026-10-29T20:00:00Z")


def test_covariance_estimation_rejects_missing_sessions_and_stale_prices(policy):
    dates=mcal.get_calendar("NYSE").schedule("2025-01-01","2026-10-29").index
    rng=np.random.default_rng(12)
    prices=pd.DataFrame(100*np.exp(np.cumsum(rng.normal(0,.01,(len(dates),len(policy.assets))),axis=0)),index=dates,columns=policy.assets)
    matrix,meta=policy.estimate_covariance(prices,decision_time="2026-10-30T12:00:00Z")
    assert matrix.shape == (len(policy.assets),len(policy.assets))
    assert meta["observations"] >= 252
    with pytest.raises(AllocationError,match="each NYSE session"):
        policy.estimate_covariance(prices.drop(prices.index[20]),decision_time="2026-10-30T12:00:00Z")
    with pytest.raises(AllocationError,match="latest completed"):
        policy.estimate_covariance(prices.iloc[:-1],decision_time="2026-10-30T12:00:00Z")


def test_invalid_research_config_cannot_enable_borrowing_or_loosen_risk_tolerance(tmp_path):
    document=json.loads(DEFAULT_CONFIG.read_text())
    path=tmp_path / "policy.json"
    document["capital_borrowing_allowed"]=True
    path.write_text(json.dumps(document))
    with pytest.raises(AllocationError,match="no-borrowing"):
        DiversifiedRegimePolicy(path)
    document["capital_borrowing_allowed"]=False
    document["risk_budget_tolerance"]=.01
    path.write_text(json.dumps(document))
    with pytest.raises(AllocationError,match="strict"):
        DiversifiedRegimePolicy(path)


def test_empty_prices_fail_with_explicit_validation(policy):
    prices=pd.DataFrame(columns=policy.assets,index=pd.DatetimeIndex([]))
    with pytest.raises(AllocationError,match="Prices must"):
        policy.estimate_covariance(prices,decision_time="2026-10-30T12:00:00Z")


@pytest.mark.parametrize("seed",range(10))
def test_risk_budgets_survive_different_correlations_and_volatility_scales(policy,seed):
    rng=np.random.default_rng(seed)
    n=len(policy.assets)
    factors=rng.normal(size=(n,5))
    matrix=factors@factors.T+np.eye(n)*.1
    vol=rng.uniform(.03,.50,n)
    matrix=matrix/np.sqrt(np.outer(np.diag(matrix),np.diag(matrix)))*np.outer(vol,vol)
    matrix=pd.DataFrame(matrix,index=policy.assets,columns=policy.assets)
    for regime in policy.config["regimes"]:
        result=policy.allocate(regime,matrix,decision_time="2026-10-30T12:00:00Z",
                               covariance_as_of="2026-10-29T20:00:00Z",risk_off=True)
        assert result["risk_budget_error"] <= 1e-6
        assert result["estimated_annual_volatility"] <= .05+1e-10
        assert result["cash_weight"] >= .60-1e-10


def test_company_diversity_reports_gaps_without_claiming_exact_sector_holdings(policy):
    result=policy.allocate("stagflation",covariance(policy),decision_time="2026-10-30T12:00:00Z",
                           covariance_as_of="2026-10-29T20:00:00Z")
    coverage={entry["id"]:entry for entry in result["asset_diversity_coverage"]}
    assert coverage["bw_inflation_linked_bonds"]["allocated_proxies"] == ["TIP"]
    assert coverage["bw_global_nominal_bonds"]["allocated_proxies"] == ["IGOV"]
    assert coverage["bh_insurance"]["allocated_proxies"] == ["KIE"]
    assert coverage["bh_liquidity"]["allocated_proxies"] == ["USD_CASH","SGOV"]
    assert coverage["bh_energy_equity"]["mapping"] == "sector_equity_proxy"
    assert coverage["bh_energy_equity"]["allocated_proxies"] == ["XLE"]
    assert result["capital_weights"]["TIP"] > 0
    assert len(result["capital_weights"]) == len(policy.assets)


@pytest.mark.parametrize("problem",["unknown_proxy","duplicate_id","live_candidate","unknown_source"])
def test_asset_catalogue_cannot_bypass_universe_or_provenance(tmp_path,problem):
    catalog=json.loads(DEFAULT_ASSET_CATALOG.read_text())
    if problem == "unknown_proxy":
        catalog["exposures"][0]["canonical_proxies"].append("TIP")
    elif problem == "duplicate_id":
        catalog["exposures"][1]["id"]=catalog["exposures"][0]["id"]
    elif problem == "live_candidate":
        catalog["research_extensions"][0]["status"]="ACTIVE"
    else:
        catalog["exposures"][0]["source"]="unverified"
    path=tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog))
    with pytest.raises(AllocationError):
        DiversifiedRegimePolicy(asset_catalog_path=path)


def test_coverage_rejects_noncanonical_or_incomplete_capital(policy):
    weights=dict.fromkeys(policy.assets,0.0)
    coverage=policy.asset_diversity_coverage(weights,1.0)
    assert next(e for e in coverage if e["id"] == "bw_us_equities")["status"] == "available_unallocated"
    with pytest.raises(AllocationError,match="canonical capital"):
        policy.asset_diversity_coverage({**weights,"UNKNOWN":0.1},.9)
    with pytest.raises(AllocationError,match="canonical capital"):
        policy.asset_diversity_coverage(weights,.9)


def test_inflation_linked_bonds_cannot_be_misclassified_as_nominal_bonds(tmp_path):
    config=json.loads(DEFAULT_CONFIG.read_text())
    groups=config["regimes"]["stagflation"]["groups"]
    weight=groups["inflation_sensitive"].pop("TIP")
    groups["inflation_sensitive"]["GLD"]+=weight
    groups["government_bonds"]={"TIP":1.0}
    path=tmp_path / "policy.json"
    path.write_text(json.dumps(config))
    with pytest.raises(AllocationError,match="does not belong"):
        DiversifiedRegimePolicy(path)


def test_expanded_allocation_round_trips_through_portfolio_and_constraints(policy):
    from constraints import PortfolioConstraints
    from portfolio import Portfolio

    cov=covariance(policy)
    result=policy.allocate("inflationary_growth",cov,decision_time="2026-10-30T12:00:00Z",
                           covariance_as_of="2026-10-29T20:00:00Z",risk_off=True)
    portfolio=Portfolio(policy.universe)
    portfolio.set_weights(result["capital_weights"])
    ordered=policy.universe.tickers
    portfolio.set_covariance(cov.loc[ordered,ordered].to_numpy())
    assert portfolio.validate()
    assert portfolio.universe.size == len(policy.assets)
    assert portfolio.weights.sum()+result["cash_weight"] == pytest.approx(1)
    variance=float(portfolio.weights@portfolio.covariance@portfolio.weights)
    assert variance == pytest.approx(result["estimated_annual_volatility"]**2)
    constrained=PortfolioConstraints.enforce(portfolio.weights)
    assert np.allclose(constrained["weights"],portfolio.weights)
    assert constrained["cash"] == pytest.approx(result["cash_weight"])


@pytest.mark.parametrize("weights",[[.1,.1,.1],[.4,.1,.1],[0,0,0],[2,1,1]])
def test_constraints_preserve_cash_and_do_not_increase_invested_exposure(weights):
    from constraints import PortfolioConstraints

    result=PortfolioConstraints.enforce(weights)
    assert result["weights"].sum() <= min(sum(weights),1)+1e-10
    assert result["weights"].max() <= PortfolioConstraints.MAX_WEIGHT+1e-10
    assert result["weights"].sum()+result["cash"] == pytest.approx(1)
