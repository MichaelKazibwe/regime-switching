"""Frozen chronological portfolio research; no adoption based on reused test history."""

from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from weekly_portfolios import allocate, POLICIES, statistics
from portfolio_contract import extended_prices
from investmentcatalog import catalogue
from strategy_integrity import strict_json, file_hash
from strategy_receipts import atomic_json


DESIGNS = ("incumbent", "uncertainty_shrink")


def replay(
    history, policy, *, estimator, cost_rate=0.0015, cash_annual=0.0, tax_annual=0.0
):
    if (
        estimator not in DESIGNS
        or not 0 <= cost_rate <= 0.05
        or not 0 <= cash_annual <= 0.2
        or not 0 <= tax_annual <= 0.1
    ):
        raise ValueError("Declared bounded research assumptions required")
    assets = np.zeros(len(history.columns))
    cash = 1.0
    nav = 1.0
    pending = None
    values = []
    turnover = 0.0
    for i in range(104, len(history)):
        assets *= 1 + history.iloc[i].to_numpy()
        cash *= (1 + cash_annual) ** (1 / 52)
        assets *= (1 - tax_annual) ** (1 / 52)
        before = float(assets.sum() + cash)
        if pending is not None:
            after = before
            for _ in range(100):
                updated = before - cost_rate * np.abs(pending * after - assets).sum()
                if abs(updated - after) < 1e-13:
                    break
                after = updated
            else:
                raise ValueError("Cost replay failed to converge")
            after = updated
            turnover += float(np.abs(pending * after - assets).sum())
            assets = pending * after
            cash = (1 - pending.sum()) * after
        else:
            after = before
        values.append(
            dict(date=str(history.index[i].date()), return_value=after / nav - 1)
        )
        nav = after
        pending = allocate(
            history.iloc[: i + 1],
            policy,
            return_estimator=estimator,
            previous_weights=pending if estimator == "uncertainty_shrink" else None,
        )[0]
    return dict(
        rows=values,
        turnover=turnover,
        metrics=statistics([r["return_value"] for r in values]),
    )


def run(bundle, output):
    bundle = Path(bundle)
    b = strict_json(bundle)
    prices = extended_prices(b["capture"], b["benchmark_extension"])
    menu = catalogue()
    weekly = (
        prices.groupby(prices.index.to_period("W-FRI"))
        .tail(1)
        .pct_change(fill_method=None)
    )
    eligible = [
        s
        for s in weekly
        if s in menu
        and menu[s].research_enabled
        and not menu[s].benchmark_only
        and weekly[s].tail(260).notna().all()
    ]
    history = weekly[eligible].dropna()
    # The capture can end midweek; only complete exchange weeks are evaluable.
    import pandas as pd
    import pandas_market_calendars as mcal

    schedule = mcal.get_calendar("NYSE").schedule(
        prices.index[0].date(), (prices.index[-1] + pd.Timedelta(days=7)).date()
    )
    week_closes = schedule.groupby(schedule.index.to_period("W-FRI")).tail(1).index
    history = history.loc[history.index.intersection(week_closes)]
    if len(history) < 208 or len(eligible) < 8:
        raise ValueError(
            "At least 208 complete observed weeks and eight eligible instruments required"
        )
    # Fixed design and coefficients; no model selection on the reported test.
    validation_start = len(history) - 104
    test_start = len(history) - 52
    results = []
    for name, policy in POLICIES.items():
        for estimator in DESIGNS:
            base = replay(history, policy, estimator=estimator)
            for period, start, end in [
                ("validation", validation_start, test_start),
                ("test", test_start, len(history)),
            ]:
                dates = set(str(d.date()) for d in history.index[start:end])
                values = [r["return_value"] for r in base["rows"] if r["date"] in dates]
                results.append(
                    dict(
                        policy=name,
                        estimator=estimator,
                        period=period,
                        metrics=statistics(values),
                    )
                )
    sensitivity = []
    # Declared adverse cost/tax assumptions are sensitivities, not observed costs.
    for name, policy in POLICIES.items():
        for cost, cash, tax in [
            (0.003, 0.0, 0.0),
            (0.005, 0.0, 0.01),
            (0.0015, 0.02, 0.0),
        ]:
            value = replay(
                history.tail(156),
                policy,
                estimator="uncertainty_shrink",
                cost_rate=cost,
                cash_annual=cash,
                tax_annual=tax,
            )
            sensitivity.append(
                dict(
                    policy=name,
                    cost_rate=cost,
                    cash_annual=cash,
                    tax_annual=tax,
                    **value["metrics"],
                )
            )
    sources = {
        p: file_hash(p)
        for p in [
            "portfolio_research.py",
            "weekly_portfolios.py",
            "portfolio_contract.py",
            "research/global_asset_registry.json",
        ]
    }
    result = dict(
        status="RETROSPECTIVE_RESEARCH_COMPARISON",
        created_at=datetime.now(timezone.utc).isoformat(),
        market_session=str(prices.index[-1].date()),
        eligible=eligible,
        protocol=dict(
            designs=list(DESIGNS),
            training_lookback_weeks=104,
            validation_weeks=52,
            test_weeks=52,
            sampling_prior_std=0.03,
            turnover_penalty=0.01,
            parameters_selected_on_test=False,
            current_universe_selection_bias_disclosed=True,
            untouched_prospective_evidence=False,
        ),
        results=results,
        sensitivities=sensitivity,
        source_hashes=sources,
        bundle_sha256=file_hash(bundle),
        adoption_enabled=False,
        execution_enabled=False,
        limitations=[
            "Reused retrospective history is not a new untouched test.",
            "Look-through, venue costs, taxes and cash yields require separately qualified evidence.",
            "Sensitivity taxes are declared drag assumptions, not client tax calculations.",
            "No favorable result automatically changes portfolio weights.",
        ],
    )
    atomic_json(output, result)
    return result


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    print(run(args.bundle, args.output)["status"])
