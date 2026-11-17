"""Recommendations/simulations workflow. Deliberately has no order API."""

from dataclasses import asdict
import hashlib
import json
from datetime import datetime, timezone

import numpy as np

from clientmandate import aware_time
from productallocation import PlanningCosts, allocate_plan, estimate_inputs, fx_source_hash
from productrelease import readiness, release_manifest
from productsimulation import simulate_plans
from recommendationrisk import RecommendationRiskState


def recommend(
    mandate,
    prices,
    cash_rate,
    *,
    decision_time,
    fx_to_base=None,
    current=None,
    costs=PlanningCosts(),
    sell_tax_rates=None,
    risk_state=None,
    equity_fraction=1.0,
    trend_confirmed=False,
    historical_preview=False,
    approval_root=None,
    paths=1000,
    annual_tax_drag=None,
    annual_fund_expenses=None,
    clock=None,
    lookthrough_records=None,
):
    mandate.validate()
    now = aware_time(decision_time)
    if not historical_preview:
        actual_now = aware_time(clock() if clock else datetime.now(timezone.utc))
        if abs((actual_now - now).total_seconds()) > 300:
            raise ValueError(
                "Use explicit historical preview for a non-current decision clock"
            )
        from global_asset_registry import common_sessions
        from datetime import timedelta
        latest = common_sessions(list(prices), (now - timedelta(days=31)).date(), now.date(), completed_at=now)[-1]
        if prices.index[-1].date() != latest.date():
            raise ValueError(
                "Current recommendations require the latest completed market session"
            )
        recent = prices.index[-1261:]
        expected = common_sessions(list(prices), recent[0].date(), recent[-1].date(), completed_at=now)
        if list(recent) != list(expected):
            raise ValueError(
                "Complete common exchange sessions required for the selected global instruments"
            )
    state = (
        RecommendationRiskState()
        if risk_state is None
        else RecommendationRiskState.restore(risk_state)
    )
    risk = state.update(
        equity_fraction,
        str(prices.index[-1].date()),
        loss_preference=None,
        trend_confirmed=trend_confirmed,
    )
    returns, mu, uncertainty, covariance, excluded = estimate_inputs(
        prices, mandate, cash_rate, decision_time, fx_to_base
    )
    if annual_fund_expenses is not None:
        if set(annual_fund_expenses) != set(returns):
            raise ValueError(
                "Fund expenses must cover all model instruments and zero-cost base cash"
            )
        expenses = np.array([annual_fund_expenses[s] for s in returns], dtype=float)
        if (
            not np.isfinite(expenses).all()
            or (expenses < 0).any()
            or (expenses > 0.10).any()
            or expenses[-1] != 0
        ):
            raise ValueError("Invalid annual fund expense inputs")
        # Observed returns already embed expenses. Charge only the gross prior.
        mu = mu - 0.9 * expenses
    if annual_tax_drag is not None:
        if set(annual_tax_drag) != set(returns):
            raise ValueError(
                "Annual tax drag must cover the complete planning universe"
            )
        drag = np.array([annual_tax_drag[s] for s in returns], dtype=float)
        if (
            not np.isfinite(drag).all()
            or (drag < 0).any()
            or (drag > 0.50).any()
            or drag[-1] != 0
        ):
            raise ValueError("Invalid annual tax drag or duplicated cash taxation")
        mu = mu - drag
    mu = (1 + mu) * (1 - mandate.annual_platform_fee) - 1
    if current is not None:
        if set(current) != set(returns):
            raise ValueError(
                "Current holdings must cover exactly the eligible model instruments and base cash"
            )
        current = np.array([current[s] for s in returns], dtype=float)
    allocation = allocate_plan(
        returns,
        mu,
        uncertainty,
        covariance,
        mandate,
        current=current,
        costs=costs,
        sell_tax_rates=sell_tax_rates,
        exposure_multiplier=risk["exposure_multiplier"],
    )
    manifest = release_manifest()
    invested = (
        []
        if allocation["weights"] is None
        else [
            s
            for s, w in allocation["weights"].items()
            if w > 1e-8 and not s.endswith("CASH")
        ]
    )
    gate = readiness(manifest, mandate, invested, now=now, root=approval_root)
    hard_blocks = []
    if historical_preview:
        hard_blocks.append("HISTORICAL_OPERATOR_PREVIEW")
    if not cash_rate.verified:
        hard_blocks.append("CASH_YIELD_UNVERIFIED")
    if costs.source == "ILLUSTRATIVE_NOT_EXECUTABLE":
        hard_blocks.append("TRADING_COST_INPUTS_ILLUSTRATIVE")
    if annual_fund_expenses is None:
        hard_blocks.append("FUND_EXPENSE_INPUTS_UNVERIFIED")
    if allocation["weights"] is None:
        hard_blocks.append("INFEASIBLE_PLANNING_CONSTRAINTS")
    if state.review_required:
        hard_blocks.append("RISK_BREACH_OR_OPERATIONAL_REVIEW_REQUIRED")
    if mandate.tax_account_type == "taxable" and annual_tax_drag is None:
        hard_blocks.append("ANNUAL_TAX_DRAG_UNAVAILABLE")
    if (
        mandate.tax_account_type == "taxable"
        and current is not None
        and sell_tax_rates is None
    ):
        hard_blocks.append("TAX_LOT_COSTS_UNAVAILABLE")
    # Priors/cost assumptions need independent validation for this release; no
    # software test or sample report is automatically recorded as approval.
    if hard_blocks:
        gate["public_recommendations_enabled"] = False
        gate["status"] = "OPERATOR_PREVIEW_ONLY"
    simulations = None
    if allocation["weights"] is not None:
        w = np.array([allocation["weights"][s] for s in returns])
        reference = np.array([allocation["strategic_reference"][s] for s in returns])
        simulations = simulate_plans(
            returns,
            {"proposed": w, "strategic_reference": reference},
            mu,
            years=min(10, max(1, int(round(mandate.horizon_years)))),
            paths=paths,
            cost_rate=costs.total(),
            initial_costs={
                "proposed": allocation["estimated_rebalance_cost_fraction"],
                "strategic_reference": allocation[
                    "strategic_reference_initial_cost_fraction"
                ],
            },
        )
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "mandate": asdict(mandate),
                "decision_time": now.isoformat(),
                "release_id": manifest["release_id"],
                "prices_sha256": hashlib.sha256(prices.to_csv().encode()).hexdigest(),
                "cash_rate": asdict(cash_rate),
                "fx_sha256": fx_source_hash(fx_to_base),
                "current_weights": current.tolist() if current is not None else None,
                "costs": asdict(costs),
                "sale_tax_rates": np.asarray(sell_tax_rates).tolist()
                if sell_tax_rates is not None
                else None,
                "annual_tax_drag": annual_tax_drag,
                "annual_fund_expenses": annual_fund_expenses,
                "effective_risk_state": state.payload(),
                "equity_fraction": equity_fraction,
                "trend_confirmed": trend_confirmed,
                "historical_preview": historical_preview,
                "paths": paths,
                "lookthrough_records": lookthrough_records,
                "qualification": gate,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return {
        "schema_version": 1,
        "kind": "NON_EXECUTABLE_PORTFOLIO_RECOMMENDATION",
        "economic_exposures": __import__('portfolio_exposures').assess_exposures(allocation['weights'],lookthrough_records,now.date().isoformat()) if lookthrough_records is not None else dict(status='NOT_SUPPLIED',execution_qualified=False),
        "universe_contract": __import__("global_asset_registry").load_registry().payload(),
        "recommendation_id": fingerprint,
        "service_mode": manifest["service_mode"],
        "as_of": now.isoformat(),
        "price_session": str(prices.index[-1].date()),
        "historical_preview": historical_preview,
        "mandate": asdict(mandate),
        "mandate_assessment": mandate.assessment(),
        "release": manifest,
        "qualification": gate,
        "hard_blocks": hard_blocks,
        "excluded_instruments": excluded,
        "allocation": allocation,
        "risk_state": state.payload(),
        "simulations": simulations,
        "limitations": [
            "No forecast or stop guarantees minimal loss or the requested return.",
            "Planning priors, square-root-impact coefficients and stress scenarios require independent validation.",
            "Registry inclusion does not establish instrument access, data qualification or suitable currency exposure.",
            "No broker, custody, order submission, tax advice or legal approval is provided by this service.",
        ],
    }
