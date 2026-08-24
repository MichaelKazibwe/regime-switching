from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


# ============================================================
# RISK CONTRIBUTION ANALYTICS
# ============================================================


class RiskContributionAnalytics:
    """
    Production-grade portfolio risk-contribution analytics.

    Mathematical convention
    ------------------------
    Portfolio variance:

        sigma_p^2 = w' Sigma w

    Portfolio volatility:

        sigma_p = sqrt(w' Sigma w)

    Marginal risk contribution:

        MRC = Sigma w / sigma_p

    Component risk contribution:

        RC_i = w_i * MRC_i

    Percentage risk contribution:

        RC_pct_i = RC_i / sigma_p

    The implementation preserves Euler homogeneity:

        sum(RC_i) = sigma_p

    Notes
    -----
    The covariance matrix and portfolio weights must use the same
    return-frequency convention.

    For example:

        daily covariance -> daily portfolio volatility
        annual covariance -> annual portfolio volatility

    This class does not silently annualize or de-annualize covariance.
    Frequency conversion belongs to the covariance/risk pipeline.
    """

    DEFAULT_TOLERANCE = 1e-10
    PSD_TOLERANCE = 1e-8

    # ============================================================
    # VALIDATION HELPERS
    # ============================================================

    @staticmethod
    def _validate_weights(
        weights: Any,
    ) -> np.ndarray:
        """
        Validate and normalize the portfolio-weight vector.
        """

        weights = np.asarray(
            weights,
            dtype=float,
        ).reshape(-1)

        if weights.size == 0:
            raise ValueError(
                "Weights cannot be empty."
            )

        if not np.isfinite(weights).all():
            raise ValueError(
                "Weights contain non-finite values."
            )

        return weights

    @staticmethod
    def _validate_covariance(
        covariance: Any,
        dimension: int,
    ) -> np.ndarray:
        """
        Validate covariance dimensions, finiteness,
        symmetry and positive-semidefiniteness.
        """

        covariance = np.asarray(
            covariance,
            dtype=float,
        )

        if covariance.ndim != 2:
            raise ValueError(
                "Covariance must be two-dimensional."
            )

        if (
            covariance.shape[0]
            != covariance.shape[1]
        ):
            raise ValueError(
                "Covariance matrix must be square."
            )

        if covariance.shape[0] != dimension:
            raise ValueError(
                "Weights and covariance dimension mismatch: "
                f"weights={dimension}, "
                f"covariance={covariance.shape}."
            )

        if not np.isfinite(covariance).all():
            raise ValueError(
                "Covariance contains non-finite values."
            )

        if not np.allclose(
            covariance,
            covariance.T,
            atol=1e-10,
            rtol=0.0,
        ):
            raise ValueError(
                "Covariance matrix is not symmetric."
            )

        # Remove harmless floating-point asymmetry.
        covariance = (
            covariance
            + covariance.T
        ) / 2.0

        eigenvalues = np.linalg.eigvalsh(
            covariance
        )

        minimum_eigenvalue = float(
            eigenvalues.min()
        )

        if minimum_eigenvalue < -RiskContributionAnalytics.PSD_TOLERANCE:
            raise ValueError(
                "Covariance matrix is not "
                "positive semidefinite. "
                f"Minimum eigenvalue="
                f"{minimum_eigenvalue:.6e}."
            )

        # Numerical cleanup for extremely small
        # negative eigenvalue artefacts.
        if minimum_eigenvalue < 0.0:
            covariance = (
                covariance
                + np.eye(dimension)
                * (-minimum_eigenvalue + 1e-12)
            )

        return covariance

    @classmethod
    def _validate_inputs(
        cls,
        weights: Any,
        covariance: Any,
    ) -> tuple[
        np.ndarray,
        np.ndarray,
    ]:
        """
        Validate the complete risk-calculation input.
        """

        weights = cls._validate_weights(
            weights
        )

        covariance = cls._validate_covariance(
            covariance,
            weights.size,
        )

        return (
            weights,
            covariance,
        )

    @staticmethod
    def _portfolio_variance(
        weights: np.ndarray,
        covariance: np.ndarray,
    ) -> float:
        """
        Calculate portfolio variance with numerical protection.
        """

        variance = float(
            weights
            @ covariance
            @ weights
        )

        if not np.isfinite(variance):
            raise ValueError(
                "Portfolio variance is non-finite."
            )

        # A PSD covariance matrix cannot generate a materially
        # negative quadratic form. Tiny negatives can arise from
        # floating-point arithmetic.
        if variance < 0.0:

            if variance < -1e-12:
                raise ValueError(
                    "Portfolio variance is materially negative: "
                    f"{variance:.12e}."
                )

            variance = 0.0

        return variance

    # ============================================================
    # PORTFOLIO VOLATILITY
    # ============================================================

    @classmethod
    def portfolio_volatility(
        cls,
        weights,
        covariance,
    ) -> float:
        """
        Calculate portfolio volatility.

        The result has the same frequency convention as the
        supplied covariance matrix.
        """

        weights, covariance = (
            cls._validate_inputs(
                weights,
                covariance,
            )
        )

        variance = cls._portfolio_variance(
            weights,
            covariance,
        )

        return float(
            np.sqrt(variance)
        )

    # ============================================================
    # MARGINAL RISK
    # ============================================================

    @classmethod
    def marginal_risk(
        cls,
        weights,
        covariance,
    ) -> np.ndarray:
        """
        Calculate marginal risk contributions.

        MRC_i = (Sigma w)_i / sigma_p
        """

        weights, covariance = (
            cls._validate_inputs(
                weights,
                covariance,
            )
        )

        portfolio_volatility = (
            cls.portfolio_volatility(
                weights,
                covariance,
            )
        )

        if (
            portfolio_volatility
            <= cls.DEFAULT_TOLERANCE
        ):
            raise ValueError(
                "Marginal risk is undefined for "
                "a zero-volatility portfolio."
            )

        marginal = (
            covariance
            @ weights
        ) / portfolio_volatility

        if not np.isfinite(
            marginal
        ).all():
            raise ValueError(
                "Marginal risk contains "
                "non-finite values."
            )

        return marginal

    # ============================================================
    # COMPONENT RISK
    # ============================================================

    @classmethod
    def risk_contributions(
        cls,
        weights,
        covariance,
    ) -> np.ndarray:
        """
        Calculate absolute/component risk contributions.

        RC_i = w_i * MRC_i

        Euler invariant:

            sum(RC_i) = portfolio volatility
        """

        weights, covariance = (
            cls._validate_inputs(
                weights,
                covariance,
            )
        )

        marginal = cls.marginal_risk(
            weights,
            covariance,
        )

        contributions = (
            weights
            * marginal
        )

        if not np.isfinite(
            contributions
        ).all():
            raise ValueError(
                "Risk contributions contain "
                "non-finite values."
            )

        portfolio_volatility = (
            cls.portfolio_volatility(
                weights,
                covariance,
            )
        )

        contribution_sum = float(
            contributions.sum()
        )

        if not np.isclose(
            contribution_sum,
            portfolio_volatility,
            atol=1e-8,
            rtol=1e-8,
        ):
            raise ValueError(
                "Euler risk decomposition failed. "
                f"Component risk sum="
                f"{contribution_sum:.12e}, "
                f"portfolio volatility="
                f"{portfolio_volatility:.12e}."
            )

        return contributions

    # ============================================================
    # PERCENTAGE RISK CONTRIBUTIONS
    # ============================================================

    @classmethod
    def risk_contribution_pct(
        cls,
        weights,
        covariance,
    ) -> np.ndarray:
        """
        Calculate percentage risk contributions.

        RC_pct_i = RC_i / portfolio_volatility

        The resulting vector must sum to one.

        Negative component contributions are mathematically
        possible when an asset provides diversification through
        covariance with the rest of the portfolio. They are
        therefore NOT artificially clipped to zero.
        """

        contributions = (
            cls.risk_contributions(
                weights,
                covariance,
            )
        )

        portfolio_volatility = (
            cls.portfolio_volatility(
                weights,
                covariance,
            )
        )

        if (
            portfolio_volatility
            <= cls.DEFAULT_TOLERANCE
        ):
            raise ValueError(
                "Percentage risk contributions are undefined "
                "for a zero-volatility portfolio."
            )

        percentages = (
            contributions
            / portfolio_volatility
        )

        if not np.isfinite(
            percentages
        ).all():
            raise ValueError(
                "Percentage risk contributions contain "
                "non-finite values."
            )

        if not np.isclose(
            percentages.sum(),
            1.0,
            atol=1e-8,
            rtol=1e-8,
        ):
            raise ValueError(
                "Percentage risk contributions "
                "do not sum to one. "
                f"Sum={percentages.sum():.12f}."
            )

        return percentages

    # ============================================================
    # RISK BUDGET VALIDATION
    # ============================================================

    @staticmethod
    def _validate_target_budget(
        target_budget: Any,
        dimension: int,
    ) -> np.ndarray:
        """
        Validate a target risk-budget vector.
        """

        target_budget = np.asarray(
            target_budget,
            dtype=float,
        ).reshape(-1)

        if target_budget.size != dimension:
            raise ValueError(
                "Target risk-budget dimension mismatch: "
                f"target={target_budget.size}, "
                f"assets={dimension}."
            )

        if not np.isfinite(
            target_budget
        ).all():
            raise ValueError(
                "Target risk budget contains "
                "non-finite values."
            )

        if np.any(
            target_budget < -1e-12
        ):
            raise ValueError(
                "Target risk budget contains "
                "negative values."
            )

        target_budget = np.maximum(
            target_budget,
            0.0,
        )

        total = float(
            target_budget.sum()
        )

        if total <= 0.0:
            raise ValueError(
                "Target risk budget must have "
                "a positive total."
            )

        target_budget /= total

        if not np.isclose(
            target_budget.sum(),
            1.0,
            atol=1e-10,
        ):
            raise ValueError(
                "Normalized target risk budget "
                "does not sum to one."
            )

        return target_budget

    # ============================================================
    # RISK BUDGET ERROR
    # ============================================================

    @classmethod
    def risk_budget_error(
        cls,
        weights,
        covariance,
        target_budget,
    ) -> np.ndarray:
        """
        Calculate actual minus target risk budget.
        """

        weights = cls._validate_weights(
            weights
        )

        target_budget = (
            cls._validate_target_budget(
                target_budget,
                weights.size,
            )
        )

        actual = (
            cls.risk_contribution_pct(
                weights,
                covariance,
            )
        )

        error = (
            actual
            - target_budget
        )

        if not np.isfinite(
            error
        ).all():
            raise ValueError(
                "Risk-budget error contains "
                "non-finite values."
            )

        return error


# ============================================================
# RISK BUDGET REPORT
# ============================================================


class RiskBudgetReport:
    """
    Production risk-budget reporting layer.

    Preserves the existing report schema:

        Asset
        Target
        Actual
        Difference
    """

    @staticmethod
    def create(
        asset_names,
        weights,
        covariance,
        target_budget,
    ) -> pd.DataFrame:

        asset_names = list(
            asset_names
        )

        weights = np.asarray(
            weights,
            dtype=float,
        ).reshape(-1)

        if len(asset_names) != weights.size:
            raise ValueError(
                "Asset-name count does not match "
                "weight count: "
                f"assets={len(asset_names)}, "
                f"weights={weights.size}."
            )

        target_budget = (
            RiskContributionAnalytics
            ._validate_target_budget(
                target_budget,
                weights.size,
            )
        )

        actual = (
            RiskContributionAnalytics
            .risk_contribution_pct(
                weights,
                covariance,
            )
        )

        difference = (
            actual
            - target_budget
        )

        report = pd.DataFrame(
            {
                "Asset": asset_names,
                "Target": target_budget,
                "Actual": actual,
                "Difference": difference,
            }
        )

        if not np.isfinite(
            report[
                [
                    "Target",
                    "Actual",
                    "Difference",
                ]
            ].to_numpy(
                dtype=float
            )
        ).all():
            raise ValueError(
                "Risk-budget report contains "
                "non-finite numerical values."
            )

        return report


# ============================================================
# REGRESSION TESTS
# ============================================================


def test_risk_contribution_analytics() -> None:
    """
    Comprehensive deterministic regression test.
    """

    rng = np.random.default_rng(
        20260823
    )

    n_assets = 14

    # ------------------------------------------------------------
    # Deterministic positive-definite covariance
    # ------------------------------------------------------------

    factor_matrix = rng.normal(
        0.0,
        0.02,
        size=(n_assets, 4),
    )

    idiosyncratic = np.diag(
        rng.uniform(
            0.0001,
            0.0009,
            size=n_assets,
        )
    )

    covariance = (
        factor_matrix
        @ factor_matrix.T
        + idiosyncratic
    )

    covariance = (
        covariance
        + covariance.T
    ) / 2.0

    # ------------------------------------------------------------
    # Long-only production-style weights
    # ------------------------------------------------------------

    raw_weights = rng.uniform(
        0.01,
        1.0,
        size=n_assets,
    )

    weights = (
        raw_weights
        / raw_weights.sum()
    )

    # ------------------------------------------------------------
    # Portfolio volatility
    # ------------------------------------------------------------

    volatility = (
        RiskContributionAnalytics
        .portfolio_volatility(
            weights,
            covariance,
        )
    )

    assert np.isfinite(
        volatility
    )

    assert volatility > 0.0

    # ------------------------------------------------------------
    # Marginal risk
    # ------------------------------------------------------------

    marginal = (
        RiskContributionAnalytics
        .marginal_risk(
            weights,
            covariance,
        )
    )

    assert marginal.shape == (
        n_assets,
    )

    assert np.isfinite(
        marginal
    ).all()

    # ------------------------------------------------------------
    # Component risk
    # ------------------------------------------------------------

    component = (
        RiskContributionAnalytics
        .risk_contributions(
            weights,
            covariance,
        )
    )

    assert component.shape == (
        n_assets,
    )

    assert np.isfinite(
        component
    ).all()

    # Euler decomposition
    assert np.isclose(
        component.sum(),
        volatility,
        atol=1e-8,
        rtol=1e-8,
    )

    # ------------------------------------------------------------
    # Percentage risk contribution
    # ------------------------------------------------------------

    percentage = (
        RiskContributionAnalytics
        .risk_contribution_pct(
            weights,
            covariance,
        )
    )

    assert percentage.shape == (
        n_assets,
    )

    assert np.isfinite(
        percentage
    ).all()

    assert np.isclose(
        percentage.sum(),
        1.0,
        atol=1e-8,
        rtol=1e-8,
    )

    # ------------------------------------------------------------
    # Risk budget
    # ------------------------------------------------------------

    target_budget = (
        np.ones(n_assets)
        / n_assets
    )

    error = (
        RiskContributionAnalytics
        .risk_budget_error(
            weights,
            covariance,
            target_budget,
        )
    )

    assert error.shape == (
        n_assets,
    )

    assert np.isfinite(
        error
    ).all()

    assert np.isclose(
        error.sum(),
        0.0,
        atol=1e-8,
    )

    # ------------------------------------------------------------
    # Risk report
    # ------------------------------------------------------------

    assets = [
        f"Asset_{i}"
        for i in range(n_assets)
    ]

    report = (
        RiskBudgetReport.create(
            assets,
            weights,
            covariance,
            target_budget,
        )
    )

    assert list(
        report.columns
    ) == [
        "Asset",
        "Target",
        "Actual",
        "Difference",
    ]

    assert len(
        report
    ) == n_assets

    assert list(
        report["Asset"]
    ) == assets

    assert np.isclose(
        report["Target"].sum(),
        1.0,
        atol=1e-10,
    )

    assert np.isclose(
        report["Actual"].sum(),
        1.0,
        atol=1e-8,
    )

    assert np.allclose(
        report["Difference"].to_numpy(
            dtype=float
        ),
        (
            report["Actual"].to_numpy(
                dtype=float
            )
            -
            report["Target"].to_numpy(
                dtype=float
            )
        ),
        atol=1e-12,
    )

    # ------------------------------------------------------------
    # Invalid dimensions
    # ------------------------------------------------------------

    try:
        RiskContributionAnalytics.portfolio_volatility(
            np.ones(5),
            covariance,
        )
        raise AssertionError(
            "Expected dimension mismatch."
        )
    except ValueError:
        pass

    # ------------------------------------------------------------
    # Invalid covariance
    # ------------------------------------------------------------

    asymmetric = covariance.copy()

    asymmetric[0, 1] += 0.01

    try:
        RiskContributionAnalytics.portfolio_volatility(
            weights,
            asymmetric,
        )
        raise AssertionError(
            "Expected asymmetric covariance failure."
        )
    except ValueError:
        pass

    # ------------------------------------------------------------
    # Invalid target budget
    # ------------------------------------------------------------

    try:
        RiskContributionAnalytics.risk_budget_error(
            weights,
            covariance,
            np.ones(5),
        )
        raise AssertionError(
            "Expected risk-budget dimension failure."
        )
    except ValueError:
        pass

    # ------------------------------------------------------------
    # Zero-volatility portfolio
    # ------------------------------------------------------------

    zero_covariance = np.zeros(
        (n_assets, n_assets)
    )

    try:
        RiskContributionAnalytics.risk_contribution_pct(
            weights,
            zero_covariance,
        )
        raise AssertionError(
            "Expected zero-volatility failure."
        )
    except ValueError:
        pass

    print(
        "Risk contribution analytics tests passed."
    )


# ============================================================
# MAIN
# ============================================================


if __name__ == "__main__":
    test_risk_contribution_analytics()