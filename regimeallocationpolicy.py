"""
======================================================================
REGIME ALLOCATION POLICY
======================================================================

Maps macroeconomic regimes into strategic portfolio preferences.

The policy does NOT directly override the optimizer.

Instead it creates regime-aware target preferences that become inputs
to the optimization process.

Design principles
-----------------
1. Regime determines strategic preference.
2. Optimizer determines final weights.
3. Constraints remain authoritative.
4. No leverage is introduced.
5. Weights always sum to 1.
6. Unknown regimes fail safely.
======================================================================
"""

from __future__ import annotations

from typing import Any


class RegimeAllocationPolicy:
    """
    Strategic regime-aware allocation policy.

    The policy supplies target preferences rather than blindly forcing
    portfolio weights.
    """

    API_VERSION = "1.0.0"

    DEFAULT_POLICY = {
        "expansion": {
            "SPY": 0.40,
            "EFA": 0.20,
            "EEM": 0.15,
            "TLT": 0.05,
            "IEF": 0.05,
            "GLD": 0.05,
            "DBC": 0.10,
        },
        "slowdown": {
            "SPY": 0.20,
            "EFA": 0.10,
            "EEM": 0.05,
            "TLT": 0.20,
            "IEF": 0.20,
            "GLD": 0.15,
            "DBC": 0.10,
        },
        "recession": {
            "SPY": 0.05,
            "EFA": 0.05,
            "EEM": 0.025,
            "TLT": 0.30,
            "IEF": 0.25,
            "GLD": 0.20,
            "DBC": 0.125,
        },
        "recovery": {
            "SPY": 0.30,
            "EFA": 0.20,
            "EEM": 0.15,
            "TLT": 0.10,
            "IEF": 0.10,
            "GLD": 0.075,
            "DBC": 0.075,
        },
    }

    def __init__(
        self,
        policy: dict[str, dict[str, float]] | None = None,
    ) -> None:

        self.policy = (
            policy
            if policy is not None
            else self.DEFAULT_POLICY
        )

        self._validate_policy()

    # ==================================================================
    # VALIDATION
    # ==================================================================

    def _validate_policy(self) -> None:

        if not self.policy:
            raise ValueError(
                "Regime allocation policy cannot be empty."
            )

        for regime, weights in self.policy.items():

            if not weights:
                raise ValueError(
                    f"Allocation policy for '{regime}' is empty."
                )

            total = sum(
                float(value)
                for value in weights.values()
            )

            if abs(total - 1.0) > 1e-8:
                raise ValueError(
                    (
                        f"Allocation policy for '{regime}' "
                        f"must sum to 1.0; got {total}."
                    )
                )

            for ticker, weight in weights.items():

                weight = float(weight)

                if weight < 0:
                    raise ValueError(
                        (
                            f"Negative weight for "
                            f"{ticker} in {regime}."
                        )
                    )

    # ==================================================================
    # PUBLIC API
    # ==================================================================

    def target_weights(
        self,
        regime: str,
        tickers: list[str],
    ) -> dict[str, float]:

        if regime is None:
            raise ValueError(
                "Regime cannot be None."
            )

        regime_key = str(
            regime
        ).lower()

        if regime_key not in self.policy:
            raise ValueError(
                f"Unsupported regime: {regime}"
            )

        source = self.policy[
            regime_key
        ]

        selected = {
            ticker: float(
                source.get(
                    ticker,
                    0.0,
                )
            )
            for ticker in tickers
        }

        total = sum(
            selected.values()
        )

        if total <= 0:
            raise ValueError(
                (
                    f"No allocation exists for regime "
                    f"'{regime}' across supplied tickers."
                )
            )

        return {
            ticker: weight / total
            for ticker, weight in selected.items()
        }

    # ==================================================================
    # PREFERENCE SCORES
    # ==================================================================

    def preference_scores(
        self,
        regime: str,
        tickers: list[str],
    ) -> dict[str, float]:

        weights = self.target_weights(
            regime,
            tickers,
        )

        minimum = min(
            weights.values()
        )

        maximum = max(
            weights.values()
        )

        if maximum <= minimum:
            return {
                ticker: 0.0
                for ticker in tickers
            }

        return {
            ticker: (
                weight - minimum
            ) / (
                maximum - minimum
            )
            for ticker, weight in weights.items()
        }

    # ==================================================================
    # HEALTH
    # ==================================================================

    def health_check(
        self,
    ) -> dict[str, Any]:

        return {
            "api_version": self.API_VERSION,
            "component": self.__class__.__name__,
            "healthy": True,
            "available_regimes": sorted(
                self.policy.keys()
            ),
        }