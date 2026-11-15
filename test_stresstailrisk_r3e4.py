from __future__ import annotations

import numpy as np
import pandas as pd

from stresstailrisk import (
    StressTailRiskEngine,
    StressTailRiskError,
)


def build_returns() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SPY": [
                0.01,
                -0.20,
                -0.05,
                0.02,
            ],
            "TLT": [
                0.00,
                -0.05,
                0.01,
                -0.01,
            ],
        },
        index=pd.to_datetime(
            [
                "2020-01-01",
                "2020-01-02",
                "2020-01-03",
                "2020-01-04",
            ]
        ),
    )


def test_worst_historical_scenario() -> None:
    engine = StressTailRiskEngine()

    returns = build_returns()

    result = engine.historical_stress(
        returns=returns,
        weights={
            "SPY": 0.60,
            "TLT": 0.40,
        },
        initial_equity=100_000.0,
        top_n=2,
    )

    assert result["observations"] == 4
    assert result["assets"] == 2

    worst = result["worst_scenario"]

    expected_return = (
        0.60 * -0.20
        + 0.40 * -0.05
    )

    expected_pnl = (
        100_000.0
        * expected_return
    )

    assert np.isclose(
        worst["portfolio_return"],
        expected_return,
    )

    assert np.isclose(
        worst["portfolio_pnl"],
        expected_pnl,
    )

    assert np.isclose(
        worst["portfolio_loss"],
        14_000.0,
    )

    assert np.isclose(
        worst["stressed_equity"],
        86_000.0,
    )

    assert (
        worst["largest_loss_contributor"]
        == "SPY"
    )


def test_asset_contributions_sum_to_portfolio() -> None:
    engine = StressTailRiskEngine()

    returns = build_returns()

    result = engine.historical_stress(
        returns=returns,
        weights={
            "SPY": 0.60,
            "TLT": 0.40,
        },
        initial_equity=100_000.0,
        top_n=1,
    )

    scenario = result["worst_scenario"]

    total_pnl = sum(
        item["pnl"]
        for item in scenario[
            "asset_contributions"
        ]
    )

    assert np.isclose(
        total_pnl,
        scenario["portfolio_pnl"],
    )


def test_top_n_ordering() -> None:
    engine = StressTailRiskEngine()

    returns = build_returns()

    result = engine.historical_stress(
        returns=returns,
        weights={
            "SPY": 0.60,
            "TLT": 0.40,
        },
        initial_equity=100_000.0,
        top_n=3,
    )

    scenarios = result["scenarios"]

    losses = [
        scenario["portfolio_loss"]
        for scenario in scenarios
    ]

    assert losses == sorted(
        losses,
        reverse=True,
    )


def test_historical_stress_alias() -> None:
    engine = StressTailRiskEngine()

    returns = build_returns()

    direct = engine.historical_stress(
        returns,
        {
            "SPY": 0.60,
            "TLT": 0.40,
        },
        initial_equity=100_000.0,
        top_n=2,
    )

    alias = engine.historical_stress_scenarios(
        returns,
        {
            "SPY": 0.60,
            "TLT": 0.40,
        },
        initial_equity=100_000.0,
        top_n=2,
    )

    assert (
        direct["worst_loss"]
        == alias["worst_loss"]
    )


def test_missing_asset_fails() -> None:
    engine = StressTailRiskEngine()

    returns = build_returns()

    try:
        engine.historical_stress(
            returns,
            {
                "SPY": 0.60,
            },
        )

        raise AssertionError(
            "Expected StressTailRiskError"
        )

    except StressTailRiskError:
        pass


def test_invalid_top_n_fails() -> None:
    engine = StressTailRiskEngine()

    returns = build_returns()

    try:
        engine.historical_stress(
            returns,
            {
                "SPY": 0.60,
                "TLT": 0.40,
            },
            top_n=0,
        )

        raise AssertionError(
            "Expected StressTailRiskError"
        )

    except StressTailRiskError:
        pass


def test_invalid_equity_fails() -> None:
    engine = StressTailRiskEngine()

    returns = build_returns()

    try:
        engine.historical_stress(
            returns,
            {
                "SPY": 0.60,
                "TLT": 0.40,
            },
            initial_equity=0.0,
        )

        raise AssertionError(
            "Expected StressTailRiskError"
        )

    except StressTailRiskError:
        pass


def run_tests() -> None:
    tests = (
        test_worst_historical_scenario,
        test_asset_contributions_sum_to_portfolio,
        test_top_n_ordering,
        test_historical_stress_alias,
        test_missing_asset_fails,
        test_invalid_top_n_fails,
        test_invalid_equity_fails,
    )

    passed = 0

    for test in tests:
        test()
        passed += 1

    print(
        f"StressTailRiskEngine R3E.4 tests: "
        f"{passed}/{len(tests)} passed."
    )

    print(
        "R3E.4 STATUS: PASS"
    )


if __name__ == "__main__":
    run_tests()