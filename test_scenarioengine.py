"""
======================================================================
SCENARIO ENGINE REGRESSION TESTS
======================================================================

Dedicated regression coverage for ScenarioEngine. Scenario test
construction belongs in test infrastructure, not production code.
======================================================================
"""

from __future__ import annotations

import numpy as np

from portfolio import Portfolio
from scenarioengine import ScenarioEngine
from testsupport import build_test_universe


# ======================================================================
# SECTION 1
# SCENARIO ENGINE REGRESSION
# ======================================================================

def test_scenario_engine() -> None:
    """Exercise the canonical ScenarioEngine contract."""

    engine = ScenarioEngine()

    # ==================================================================
    # REGISTER SCENARIO
    # ==================================================================

    engine.add_scenario(
        "Equity Crash",
        {
            "SPY": -0.20,
            "QQQ": -0.30,
        },
    )

    assert len(engine.scenarios) == 1

    # ==================================================================
    # BUILD PORTFOLIO
    # ==================================================================

    portfolio = Portfolio(build_test_universe())

    portfolio.set_weights(
        {
            "SPY": 0.40,
            "QQQ": 0.35,
            "TLT": 0.25,
        }
    )

    portfolio.set_expected_returns(
        np.array(
            [
                0.08,
                0.10,
                0.03,
            ]
        )
    )

    # ==================================================================
    # APPLY SCENARIO
    # ==================================================================

    shocked = engine.apply(
        portfolio,
        "Equity Crash",
    )

    assert shocked is not portfolio
    assert shocked.expected_returns is not None

    # ==================================================================
    # ORIGINAL PORTFOLIO UNCHANGED
    # ==================================================================

    assert np.allclose(
        portfolio.expected_returns,
        np.array(
            [
                0.08,
                0.10,
                0.03,
            ]
        ),
    )

    # ==================================================================
    # SHOCKED PORTFOLIO CHANGED
    # ==================================================================

    assert not np.allclose(
        portfolio.expected_returns,
        shocked.expected_returns,
    )

    # ==================================================================
    # COMPARISON
    # ==================================================================

    report = engine.compare(
        portfolio,
        shocked,
    )

    assert "expected_return_change" in report
    assert "positions" in report
    assert "gross_exposure" in report

    # ==================================================================
    # SUMMARY
    # ==================================================================

    summary = engine.summary()

    assert summary["registered"] == 1
    assert summary["has_result"]
    assert summary["last_scenario"] == "Equity Crash"

    # ==================================================================
    # HEALTH
    # ==================================================================

    assert engine.health_check()

    # ==================================================================
    # SERIALIZATION
    # ==================================================================

    exported = engine.to_dict()

    assert "metadata" in exported
    assert "scenarios" in exported

    restored = ScenarioEngine.from_dict(exported)

    assert restored.scenarios == engine.scenarios

    # ==================================================================
    # API FREEZE
    # ==================================================================

    assert ScenarioEngine.API_VERSION == "1.0.0"

    assert tuple(ScenarioEngine.PUBLIC_METHODS) == (
        "add_scenario",
        "remove_scenario",
        "apply",
        "summary",
        "metadata",
    )

    # ==================================================================
    # REMOVE
    # ==================================================================

    engine.remove_scenario("Equity Crash")

    assert len(engine.scenarios) == 0
