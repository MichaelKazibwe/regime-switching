"""
===============================================================
SCENARIO ENGINE

Institutional Scenario Analysis Engine

Applies deterministic market scenarios to portfolios.

===============================================================
"""

from __future__ import annotations

from copy import deepcopy

from basecomponent import BaseObject

from portfolio import Portfolio

import numpy as np

# ============================================================
# SCENARIO ENGINE
# ============================================================

class ScenarioEngine(BaseObject):

    """
    Institutional scenario engine.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (

        "add_scenario",

        "remove_scenario",

        "apply",

        "summary",

        "metadata"

    )

    # ========================================================
    # CONSTRUCTOR
    # ========================================================

    def __init__(
        self
    ):

        super().__init__()

        self.scenarios = {}

        self.last_result = None

        self.last_report = None

        self.last_scenario = None

    # ========================================================
    # ADD
    # ========================================================

    def add_scenario(
        self,
        name,
        shocks
    ):

        """
        Register a scenario.

        shocks

            ticker -> return shock

        Example

            {
                "SPY": -0.20,
                "QQQ": -0.30
            }
        """

        if not isinstance(
            shocks,
            dict
        ):

            raise TypeError(
                "Scenario shocks must be a dictionary."
            )

        self.scenarios[name] = dict(
            shocks
        )

    # ========================================================
    # REMOVE
    # ========================================================

    def remove_scenario(
        self,
        name
    ):

        if name not in self.scenarios:

            raise KeyError(
                f"Scenario '{name}' not found."
            )

        del self.scenarios[name]

    # ========================================================
    # APPLY
    # ========================================================

    def apply(
        self,
        portfolio: Portfolio,
        name
    ):

        """
        Apply a registered scenario.

        Returns a shocked portfolio.
        """

        if not isinstance(
            portfolio,
            Portfolio
        ):

            raise TypeError(
                "Expected Portfolio."
            )

        if name not in self.scenarios:

            raise KeyError(
                f"Scenario '{name}' not found."
            )

        shocked = deepcopy(
            portfolio
        )

        shocks = self.scenarios[
            name
        ]

        # -----------------------------------------------
        # Expected Returns
        # -----------------------------------------------

        if shocked.expected_returns is not None:

            expected = shocked.expected_returns.copy()

            for i, ticker in enumerate(
                shocked.universe.tickers
            ):

                if ticker in shocks:

                    expected[i] += shocks[ticker]

            shocked.expected_returns = expected

        self.last_scenario = name

        self.last_result = shocked

        self.last_report = {

            "scenario": name,

            "assets_shocked": len(shocks)

        }

        return shocked
    
    # ========================================================
    # COMPARE
    # ========================================================

    def compare(
        self,
        original: Portfolio,
        shocked: Portfolio
    ):

        """
        Compare two portfolios.
        """

        report = {}

        if (
            original.expected_returns is not None
            and
            shocked.expected_returns is not None
        ):

            report[
                "expected_return_change"
            ] = (
                shocked.expected_returns
                -
                original.expected_returns
            )

        report["positions"] = (
            original.number_of_positions
        )

        report["gross_exposure"] = (
            original.gross_exposure
        )

        return report
        
    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
        self
    ):

        return {

            "registered":

                len(
                    self.scenarios
                ),

            "last_scenario":

                self.last_scenario,

            "has_result":

                self.last_result is not None,

            "scenario_names":

                sorted(

                    self.scenarios.keys()

                )

        }

    # ========================================================
    # METADATA
    # ========================================================

    @property
    def metadata(
        self
    ):

        metadata = super().metadata

        metadata.update(

            self.summary()

        )

        return metadata

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self
    ):

        if not isinstance(
            self.scenarios,
            dict
        ):

            raise RuntimeError(
                "Scenario registry corrupted."
            )

        for name, shocks in self.scenarios.items():

            if not isinstance(
                name,
                str
            ):

                raise RuntimeError(
                    "Scenario names must be strings."
                )

            if not isinstance(
                shocks,
                dict
            ):

                raise RuntimeError(
                    f"Scenario '{name}' is invalid."
                )

            for ticker, shock in shocks.items():

                if not isinstance(
                    ticker,
                    str
                ):

                    raise RuntimeError(
                        "Ticker names must be strings."
                    )

                if not isinstance(
                    shock,
                    (
                        int,
                        float
                    )
                ):

                    raise RuntimeError(
                        f"{ticker}: invalid shock."
                    )

        return True
    
    # ========================================================
    # TO DICTIONARY
    # ========================================================

    def to_dict(
        self
    ):

        return {

            "metadata":

                self.metadata,

            "scenarios":

                dict(
                    self.scenarios
                ),

            "last_scenario":

                self.last_scenario

        }

    # ========================================================
    # FROM DICTIONARY
    # ========================================================

    @classmethod
    def from_dict(
        cls,
        data
    ):

        engine = cls()

        engine.scenarios = dict(

            data.get(

                "scenarios",

                {}

            )

        )

        engine.last_scenario = data.get(

            "last_scenario"

        )

        return engine

# ============================================================
# REGRESSION TESTS
# ============================================================

def test_scenario_engine():

    from testsupport import build_test_universe

    engine = ScenarioEngine()

    # ========================================================
    # REGISTER SCENARIO
    # ========================================================

    engine.add_scenario(

        "Equity Crash",

        {

            "SPY": -0.20,

            "QQQ": -0.30

        }

    )

    assert len(

        engine.scenarios

    ) == 1

    # ========================================================
    # BUILD PORTFOLIO
    # ========================================================

    portfolio = Portfolio(

        build_test_universe()

    )

    portfolio.set_weights(

        {

            "SPY": 0.40,

            "QQQ": 0.35,

            "TLT": 0.25

        }

    )

    portfolio.set_expected_returns(

        np.array(

            [

                0.08,

                0.10,

                0.03

            ]

        )

    )

    # ========================================================
    # APPLY SCENARIO
    # ========================================================

    shocked = engine.apply(

        portfolio,

        "Equity Crash"

    )

    assert shocked is not portfolio

    assert shocked.expected_returns is not None

    # ========================================================
    # ORIGINAL PORTFOLIO UNCHANGED
    # ========================================================

    assert np.allclose(

        portfolio.expected_returns,

        np.array(

            [

                0.08,

                0.10,

                0.03

            ]

        )

    )

    # ========================================================
    # SHOCKED PORTFOLIO CHANGED
    # ========================================================

    assert not np.allclose(

        portfolio.expected_returns,

        shocked.expected_returns

    )

    # ========================================================
    # COMPARISON
    # ========================================================

    report = engine.compare(

        portfolio,

        shocked

    )

    assert "expected_return_change" in report

    assert "positions" in report

    assert "gross_exposure" in report

    # ========================================================
    # SUMMARY
    # ========================================================

    summary = engine.summary()

    assert summary["registered"] == 1

    assert summary["has_result"]

    assert summary["last_scenario"] == "Equity Crash"

    # ========================================================
    # HEALTH
    # ========================================================

    assert engine.health_check()

    # ========================================================
    # SERIALIZATION
    # ========================================================

    exported = engine.to_dict()

    assert "metadata" in exported

    assert "scenarios" in exported

    restored = ScenarioEngine.from_dict(

        exported

    )

    assert restored.scenarios == engine.scenarios

    # ========================================================
    # API FREEZE
    # ========================================================

    assert ScenarioEngine.API_VERSION == "1.0.0"

    assert tuple(

        ScenarioEngine.PUBLIC_METHODS

    ) == (

        "add_scenario",

        "remove_scenario",

        "apply",

        "summary",

        "metadata"

    )
    
    # ========================================================
    # REMOVE
    # ========================================================

    engine.remove_scenario(

        "Equity Crash"

    )

    assert len(

        engine.scenarios

    ) == 0

    print(

        "ScenarioEngine tests passed."

    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    test_scenario_engine()