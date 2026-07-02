import numpy as np

from core_constants import settings

# ============================================================
# PORTFOLIO CONSTRAINTS
# ============================================================

class PortfolioConstraints:

    MAX_WEIGHT = (
        settings.max_position_weight
    )

    MIN_WEIGHT = 0.0

    MAX_LEVERAGE = (
        settings.max_leverage
    )

    @staticmethod
    def enforce(weights):

        weights = np.array(
            weights,
            dtype=float
        )

        max_w = (
            PortfolioConstraints.MAX_WEIGHT
        )

        if weights.sum() <= 0:

            return {
                "weights": weights,
                "cash": 1.0
            }

        # ============================================================
        # NORMALIZE
        # ============================================================

        weights = (
            weights
            /
            weights.sum()
        )

        # ============================================================
        # REDISTRIBUTE EXCESS ABOVE MAX_WEIGHT
        # ============================================================

        max_iterations = 100

        for _ in range(
            max_iterations
        ):

            over = (
                weights > max_w
            )

            if not np.any(over):
                break

            excess = (
                weights[over]
                - max_w
            ).sum()

            weights[over] = max_w

            eligible = (
                weights < max_w
            )

            if not np.any(eligible):
                break

            eligible_sum = (
                weights[eligible]
                .sum()
            )

            if eligible_sum <= 0:
                break

            weights[eligible] += (
                excess
                *
                weights[eligible]
                /
                eligible_sum
            )

        # ============================================================
        # FINAL SAFETY CAP
        # ============================================================

        weights = np.minimum(
            weights,
            max_w
        )

        # ============================================================
        # CASH SLEEVE
        # ============================================================

        cash = (
            1.0
            - weights.sum()
        )

        cash = max(
            cash,
            0.0
        )

        # ============================================================
        # INVARIANT CHECKS
        # ============================================================

        assert np.isfinite(
            weights
        ).all()

        assert (
            weights >= 0
        ).all()

        assert np.isfinite(
            cash
        )

        assert cash >= 0

        assert (
            weights <= max_w + 1e-12
        ).all()

        assert (
            weights.sum()
            + cash
            <= 1.000001
        )

        return {
            "weights": weights,
            "cash": cash
        }