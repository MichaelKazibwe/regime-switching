
from __future__ import annotations

import numpy as np

from core_constants import settings


# ============================================================
# PORTFOLIO CONSTRAINTS
# ============================================================

class PortfolioConstraints:
    """
    Production portfolio constraints.

    Responsibilities
    -----------------
    - Enforce long-only portfolio weights.
    - Enforce maximum individual position weight.
    - Redistribute excess weight where possible.
    - Preserve a cash sleeve when total investable weight
      is below 1.0.

    Leverage is deliberately NOT enforced here.

    Portfolio leverage is handled by the portfolio optimizer
    and volatility-targeting/risk-control layers.
    """

    MAX_WEIGHT = float(
        settings.max_position_weight
    )

    MIN_WEIGHT = 0.0

    MAX_LEVERAGE = float(
        settings.max_leverage
    )

    TOLERANCE = 1e-12

    # ========================================================
    # VALIDATION
    # ========================================================

    @classmethod
    def _validate_weights(
        cls,
        weights,
    ) -> np.ndarray:
        """
        Convert and validate a weight vector.
        """

        values = np.asarray(
            weights,
            dtype=float,
        ).reshape(-1)

        if values.size == 0:
            raise ValueError(
                "Portfolio weights cannot be empty."
            )

        if not np.isfinite(
            values
        ).all():
            raise ValueError(
                "Portfolio weights contain non-finite values."
            )

        if np.any(
            values < -cls.TOLERANCE
        ):
            raise ValueError(
                "PortfolioConstraints only supports "
                "long-only weights."
            )

        return np.maximum(
            values,
            0.0,
        )

    # ========================================================
    # REDISTRIBUTION
    # ========================================================

    @classmethod
    def _redistribute_excess(
        cls,
        weights: np.ndarray,
    ) -> np.ndarray:
        """
        Redistribute weight above MAX_WEIGHT to eligible
        positions proportionally.

        The procedure terminates when:
        - no position exceeds MAX_WEIGHT, or
        - no eligible position remains.
        """

        weights = weights.copy()

        max_iterations = max(
            100,
            weights.size * 20,
        )

        for _ in range(
            max_iterations
        ):
            over = (
                weights
                > cls.MAX_WEIGHT
                + cls.TOLERANCE
            )

            if not np.any(over):
                break

            excess = float(
                (
                    weights[over]
                    - cls.MAX_WEIGHT
                ).sum()
            )

            weights[over] = (
                cls.MAX_WEIGHT
            )

            if excess <= cls.TOLERANCE:
                break

            eligible = (
                weights
                < cls.MAX_WEIGHT
                - cls.TOLERANCE
            )

            if not np.any(eligible):
                break

            eligible_sum = float(
                weights[eligible].sum()
            )

            # If all eligible positions have zero
            # weight, there is nowhere to redistribute
            # proportionally.
            if eligible_sum <= cls.TOLERANCE:
                break

            weights[eligible] += (
                excess
                * weights[eligible]
                / eligible_sum
            )

        return np.minimum(
            weights,
            cls.MAX_WEIGHT,
        )

    # ========================================================
    # ENFORCE
    # ========================================================

    @classmethod
    def enforce(
        cls,
        weights,
    ):
        """
        Enforce portfolio constraints.

        Returns
        -------
        dict
            {
                "weights": constrained_weights,
                "cash": cash_weight
            }
        """

        weights = cls._validate_weights(
            weights
        )

        total = float(
            weights.sum()
        )

        # ----------------------------------------------------
        # ZERO PORTFOLIO
        # ----------------------------------------------------

        if total <= cls.TOLERANCE:
            return {
                "weights": np.zeros_like(
                    weights
                ),
                "cash": 1.0,
            }

        # ----------------------------------------------------
        # NORMALIZE
        # ----------------------------------------------------

        # Preserve explicitly reserved cash. Normalizing an underinvested
        # allocation back to 100% would undo volatility and stress controls.
        if total > 1.0:
            weights = weights / total

        # ----------------------------------------------------
        # POSITION CAP
        # ----------------------------------------------------

        weights = cls._redistribute_excess(
            weights
        )

        # ----------------------------------------------------
        # FINAL SAFETY CAP
        # ----------------------------------------------------

        weights = np.minimum(
            weights,
            cls.MAX_WEIGHT,
        )

        weights = np.maximum(
            weights,
            0.0,
        )

        # ----------------------------------------------------
        # CASH SLEEVE
        # ----------------------------------------------------

        invested = float(
            weights.sum()
        )

        cash = max(
            0.0,
            1.0 - invested,
        )

        # ----------------------------------------------------
        # INVARIANTS
        # ----------------------------------------------------

        if not np.isfinite(
            weights
        ).all():
            raise RuntimeError(
                "Constraint engine produced non-finite weights."
            )

        if np.any(
            weights < -cls.TOLERANCE
        ):
            raise RuntimeError(
                "Constraint engine produced negative weights."
            )

        if np.any(
            weights
            > cls.MAX_WEIGHT
            + cls.TOLERANCE
        ):
            raise RuntimeError(
                "Constraint engine violated MAX_WEIGHT."
            )

        if not np.isfinite(
            cash
        ):
            raise RuntimeError(
                "Constraint engine produced non-finite cash."
            )

        if cash < -cls.TOLERANCE:
            raise RuntimeError(
                "Constraint engine produced negative cash."
            )

        if (
            weights.sum()
            + cash
            > 1.0
            + 1e-9
        ):
            raise RuntimeError(
                "Portfolio weights plus cash exceed 100%."
            )

        return {
            "weights": weights,
            "cash": float(
                max(cash, 0.0)
            ),
        }


# ============================================================
# REGRESSION TEST
# ============================================================

def test_portfolio_constraints():

    # --------------------------------------------------------
    # NORMAL PORTFOLIO
    # --------------------------------------------------------

    weights = np.array([
        0.10,
        0.20,
        0.30,
        0.40,
    ])

    result = (
        PortfolioConstraints
        .enforce(weights)
    )

    constrained = result[
        "weights"
    ]

    cash = result[
        "cash"
    ]

    assert np.isfinite(
        constrained
    ).all()

    assert np.isfinite(
        cash
    )

    assert (
        constrained >= 0
    ).all()

    assert (
        constrained
        <= PortfolioConstraints.MAX_WEIGHT
        + 1e-12
    ).all()

    assert np.isclose(
        constrained.sum()
        + cash,
        1.0,
        atol=1e-10,
    )

    # --------------------------------------------------------
    # ZERO PORTFOLIO
    # --------------------------------------------------------

    zero = (
        PortfolioConstraints
        .enforce(
            np.zeros(4)
        )
    )

    assert np.allclose(
        zero["weights"],
        0.0,
    )

    assert np.isclose(
        zero["cash"],
        1.0,
    )

    # --------------------------------------------------------
    # NEGATIVE INPUT
    # --------------------------------------------------------

    try:
        PortfolioConstraints.enforce(
            np.array([
                0.5,
                -0.1,
                0.6,
            ])
        )

        raise AssertionError(
            "Expected ValueError."
        )

    except ValueError:
        pass

    print(
        "PortfolioConstraints tests passed."
    )


if __name__ == "__main__":
    test_portfolio_constraints()
