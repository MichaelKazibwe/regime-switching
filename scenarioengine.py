"""
===============================================================
SCENARIO ENGINE

Institutional Scenario Analysis Engine

Applies deterministic shocks to portfolio expected-return
assumptions, with validation and serialization support.

NOTE:
Shocks are additive changes to expected returns. This component
does not simulate asset prices, covariance changes, or portfolio
P&L paths.
===============================================================
"""

from __future__ import annotations

from copy import deepcopy
from math import isfinite
from numbers import Real

from basecomponent import BaseObject
from portfolio import Portfolio


class ScenarioEngine(BaseObject):
    """Register, apply, compare, and report deterministic scenarios."""

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (
        "add_scenario",
        "remove_scenario",
        "apply",
        "summary",
        "metadata",
    )

    def __init__(self):
        super().__init__()
        self.scenarios = {}
        self.last_result = None
        self.last_report = None
        self.last_scenario = None

    # ========================================================
    # INTERNAL VALIDATION
    # ========================================================

    @staticmethod
    def _validate_name(name):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Scenario name must be a non-empty string.")

    @staticmethod
    def _validate_shocks(shocks):
        if not isinstance(shocks, dict):
            raise TypeError("Scenario shocks must be a dictionary.")

        validated = {}

        for ticker, shock in shocks.items():
            if not isinstance(ticker, str) or not ticker.strip():
                raise ValueError(
                    "Every scenario ticker must be a non-empty string."
                )

            if isinstance(shock, bool) or not isinstance(shock, Real):
                raise TypeError(
                    f"{ticker}: shock must be a real numeric value."
                )

            shock = float(shock)

            if not isfinite(shock):
                raise ValueError(
                    f"{ticker}: shock must be finite; got {shock!r}."
                )

            validated[ticker] = shock

        return validated

    @staticmethod
    def _validate_portfolio(portfolio):
        if not isinstance(portfolio, Portfolio):
            raise TypeError("Expected Portfolio.")

        universe = getattr(portfolio, "universe", None)
        tickers = getattr(universe, "tickers", None)

        if tickers is None:
            raise ValueError("Portfolio must have a universe with tickers.")

        if len(tickers) != len(set(tickers)):
            raise ValueError("Portfolio universe contains duplicate tickers.")

        expected = getattr(portfolio, "expected_returns", None)

        if expected is not None:
            try:
                values = expected.tolist()
            except AttributeError:
                values = list(expected)

            if len(values) != len(tickers):
                raise ValueError(
                    "Expected-return length does not match portfolio universe."
                )

            for ticker, value in zip(tickers, values):
                if isinstance(value, bool) or not isinstance(value, Real):
                    raise ValueError(
                        f"{ticker}: expected return must be numeric."
                    )

                if not isfinite(float(value)):
                    raise ValueError(
                        f"{ticker}: expected return must be finite."
                    )

        return tuple(tickers)

    # ========================================================
    # ADD SCENARIO
    # ========================================================

    def add_scenario(self, name, shocks):
        """
        Register a scenario.

        Parameters
        ----------
        name : str
            Non-empty scenario name.
        shocks : dict[str, real]
            Ticker -> additive expected-return shock.

        Example
        -------
        {"SPY": -0.20, "QQQ": -0.30}

        Existing scenario names are replaced, preserving the
        original component's overwrite behavior.
        """
        self._validate_name(name)
        validated_shocks = self._validate_shocks(shocks)

        # Commit only after all inputs pass validation.
        self.scenarios[name] = validated_shocks

    # ========================================================
    # REMOVE SCENARIO
    # ========================================================

    def remove_scenario(self, name):
        """Remove a registered scenario by name."""
        if name not in self.scenarios:
            raise KeyError(f"Scenario '{name}' not found.")

        del self.scenarios[name]

    # ========================================================
    # APPLY SCENARIO
    # ========================================================

    def apply(self, portfolio: Portfolio, name):
        """
        Apply a registered scenario to a copy of a portfolio.

        Each matching expected return is adjusted additively.
        The original portfolio is not modified.
        """
        tickers = self._validate_portfolio(portfolio)

        if name not in self.scenarios:
            raise KeyError(f"Scenario '{name}' not found.")

        shocks = self._validate_shocks(self.scenarios[name])

        unknown_tickers = sorted(set(shocks) - set(tickers))
        if unknown_tickers:
            raise ValueError(
                f"Scenario '{name}' contains tickers absent from the "
                f"portfolio universe: {unknown_tickers}"
            )

        shocked = deepcopy(portfolio)

        if shocked.expected_returns is not None:
            expected = shocked.expected_returns.copy()

            for index, ticker in enumerate(tickers):
                if ticker in shocks:
                    expected[index] += shocks[ticker]

            # Reject overflow or invalid output before committing state.
            for ticker, value in zip(tickers, expected):
                if not isfinite(float(value)):
                    raise ValueError(
                        f"Scenario '{name}' produced a non-finite "
                        f"expected return for {ticker}."
                    )

            shocked.expected_returns = expected

        report = {
            "scenario": name,
            "assets_shocked": len(shocks),
            "matched_assets": sum(ticker in shocks for ticker in tickers),
            "unmatched_assets": 0,
            "expected_returns_adjusted": (
                shocked.expected_returns is not None
            ),
        }

        # Update state only after successful validation and calculation.
        self.last_scenario = name
        self.last_result = shocked
        self.last_report = report

        return shocked

    # ========================================================
    # COMPARE
    # ========================================================

    def compare(self, original: Portfolio, shocked: Portfolio):
        """Compare expected returns and basic exposure information."""
        original_tickers = self._validate_portfolio(original)
        shocked_tickers = self._validate_portfolio(shocked)

        if original_tickers != shocked_tickers:
            raise ValueError(
                "Cannot compare portfolios with different ticker order "
                "or universes."
            )

        report = {}

        original_returns = original.expected_returns
        shocked_returns = shocked.expected_returns

        if original_returns is not None and shocked_returns is not None:
            report["expected_return_change"] = (
                shocked_returns - original_returns
            )

        report["positions"] = original.number_of_positions
        report["gross_exposure"] = original.gross_exposure

        return report

    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(self):
        """Return a compact summary of registered and last-used scenarios."""
        return {
            "registered": len(self.scenarios),
            "last_scenario": self.last_scenario,
            "has_result": self.last_result is not None,
            "scenario_names": sorted(self.scenarios.keys()),
        }

    # ========================================================
    # METADATA
    # ========================================================

    @property
    def metadata(self):
        metadata = dict(super().metadata)
        metadata.update(self.summary())
        return metadata

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(self):
        """Raise an error if the scenario registry is invalid."""
        if not isinstance(self.scenarios, dict):
            raise RuntimeError("Scenario registry corrupted.")

        for name, shocks in self.scenarios.items():
            if not isinstance(name, str) or not name.strip():
                raise RuntimeError(
                    "Scenario names must be non-empty strings."
                )

            if not isinstance(shocks, dict):
                raise RuntimeError(f"Scenario '{name}' is invalid.")

            for ticker, shock in shocks.items():
                if not isinstance(ticker, str) or not ticker.strip():
                    raise RuntimeError(
                        "Ticker names must be non-empty strings."
                    )

                if isinstance(shock, bool) or not isinstance(shock, Real):
                    raise RuntimeError(f"{ticker}: invalid shock type.")

                if not isfinite(float(shock)):
                    raise RuntimeError(f"{ticker}: shock must be finite.")

        if self.last_scenario is not None:
            if not isinstance(self.last_scenario, str):
                raise RuntimeError("Last scenario name must be a string.")

        return True

    # ========================================================
    # SERIALIZATION
    # ========================================================

    def to_dict(self):
        """Export serializable scenario-engine state."""
        return {
            "metadata": self.metadata,
            "scenarios": deepcopy(self.scenarios),
            "last_scenario": self.last_scenario,
        }

    @classmethod
    def from_dict(cls, data):
        """Restore a scenario engine from its exported dictionary."""
        if not isinstance(data, dict):
            raise TypeError("ScenarioEngine.from_dict expects a dictionary.")

        engine = cls()
        scenarios = data.get("scenarios", {})

        if not isinstance(scenarios, dict):
            raise TypeError("Serialized scenarios must be a dictionary.")

        restored = {}

        for name, shocks in scenarios.items():
            engine._validate_name(name)
            restored[name] = engine._validate_shocks(shocks)

        engine.scenarios = restored

        last_scenario = data.get("last_scenario")
        if last_scenario is not None:
            engine._validate_name(last_scenario)
            if last_scenario not in engine.scenarios:
                raise ValueError(
                    "Serialized last_scenario is not in the scenario registry."
                )

        engine.last_scenario = last_scenario
        # The last portfolio result is deliberately not serialized.
        engine.last_result = None
        engine.last_report = None

        return engine
