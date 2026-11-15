
from __future__ import annotations

import numpy as np
import pandas as pd

from core_constants import TRADING_DAYS


# ============================================================
# RISK CONTRIBUTION ANALYTICS
# ============================================================

class RiskContributionAnalytics:

    TRADING_DAYS = TRADING_DAYS

    TOLERANCE = 1e-12

    # ========================================================
    # VALIDATION
    # ========================================================

    @classmethod
    def _validate_inputs(
        cls,
        weights,
        covariance,
    ) -> tuple[
        np.ndarray,
        np.ndarray,
    ]:

        weights = np.asarray(
            weights,
            dtype=float,
        ).reshape(-1)

        covariance = np.asarray(
            covariance,
            dtype=float,
        )

        if weights.size == 0:
            raise ValueError(
                "Weights cannot be empty."
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

        if (
            covariance.shape[0]
            != weights.size
        ):
            raise ValueError(
                "Weights and covariance dimensions "
                "must match."
            )

        if not np.isfinite(
            weights
        ).all():
            raise ValueError(
                "Weights contain non-finite values."
            )

        if not np.isfinite(
            covariance
        ).all():
            raise ValueError(
                "Covariance contains non-finite values."
            )

        covariance = (
            covariance
            + covariance.T
        ) / 2.0

        eigenvalues = np.linalg.eigvalsh(
            covariance
        )

        if eigenvalues.min() < -1e-10:
            raise ValueError(
                "Covariance matrix is not "
                "positive semi-definite."
            )

        return (
            weights,
            covariance,
        )

    # ========================================================
    # PERIOD VALIDATION
    # ========================================================

    @classmethod
    def _validate_periods_per_year(
        cls,
        periods_per_year,
    ) -> int:

        if isinstance(
            periods_per_year,
            bool,
        ):
            raise TypeError(
                "periods_per_year must be "
                "a positive integer."
            )

        value = int(
            periods_per_year
        )

        if value <= 0:
            raise ValueError(
                "periods_per_year must be positive."
            )

        return value

    # ========================================================
    # COVARIANCE SCALING
    # ========================================================

    @classmethod
    def _prepare_covariance(
        cls,
        covariance,
        annualize: bool = False,
        periods_per_year: int = TRADING_DAYS,
    ) -> np.ndarray:

        if not isinstance(
            annualize,
            bool,
        ):
            raise TypeError(
                "annualize must be boolean."
            )

        periods_per_year = (
            cls._validate_periods_per_year(
                periods_per_year
            )
        )

        covariance = np.asarray(
            covariance,
            dtype=float,
        )

        if annualize:
            covariance = (
                covariance
                * periods_per_year
            )

        return covariance

    # ========================================================
    # PORTFOLIO VARIANCE
    # ========================================================

    @classmethod
    def portfolio_variance(
        cls,
        weights,
        covariance,
        annualize: bool = False,
        periods_per_year: int = TRADING_DAYS,
    ) -> float:

        weights, covariance = (
            cls._validate_inputs(
                weights,
                covariance,
            )
        )

        covariance = (
            cls._prepare_covariance(
                covariance,
                annualize=annualize,
                periods_per_year=periods_per_year,
            )
        )

        variance = float(
            weights.T
            @ covariance
            @ weights
        )

        if not np.isfinite(
            variance
        ):
            raise ValueError(
                "Portfolio variance is non-finite."
            )

        if variance < 0.0:

            if variance > -1e-12:
                variance = 0.0

            else:
                raise ValueError(
                    "Portfolio variance is materially negative."
                )

        return variance

    # ========================================================
    # PORTFOLIO VOLATILITY
    # ========================================================

    @classmethod
    def portfolio_volatility(
        cls,
        weights,
        covariance,
        annualize: bool = False,
        periods_per_year: int = TRADING_DAYS,
    ) -> float:

        variance = (
            cls.portfolio_variance(
                weights,
                covariance,
                annualize=annualize,
                periods_per_year=periods_per_year,
            )
        )

        return float(
            np.sqrt(
                variance
            )
        )

    # ========================================================
    # MARGINAL RISK
    # ========================================================

    @classmethod
    def marginal_risk(
        cls,
        weights,
        covariance,
        annualize: bool = False,
        periods_per_year: int = TRADING_DAYS,
    ) -> np.ndarray:

        weights, covariance = (
            cls._validate_inputs(
                weights,
                covariance,
            )
        )

        covariance = (
            cls._prepare_covariance(
                covariance,
                annualize=annualize,
                periods_per_year=periods_per_year,
            )
        )

        portfolio_volatility = (
            cls.portfolio_volatility(
                weights,
                covariance,
                annualize=False,
                periods_per_year=periods_per_year,
            )
        )

        if (
            portfolio_volatility
            <= cls.TOLERANCE
        ):
            raise ValueError(
                "Portfolio volatility must be positive."
            )

        return (
            covariance
            @ weights
        ) / portfolio_volatility

    # ========================================================
    # ABSOLUTE RISK CONTRIBUTIONS
    # ========================================================

    @classmethod
    def risk_contributions(
        cls,
        weights,
        covariance,
        annualize: bool = False,
        periods_per_year: int = TRADING_DAYS,
    ) -> np.ndarray:

        weights, covariance = (
            cls._validate_inputs(
                weights,
                covariance,
            )
        )

        covariance = (
            cls._prepare_covariance(
                covariance,
                annualize=annualize,
                periods_per_year=periods_per_year,
            )
        )

        marginal = (
            cls.marginal_risk(
                weights,
                covariance,
                annualize=False,
                periods_per_year=periods_per_year,
            )
        )

        return (
            weights
            * marginal
        )

    # ========================================================
    # RISK CONTRIBUTION %
    # ========================================================

    @classmethod
    def risk_contribution_pct(
        cls,
        weights,
        covariance,
        annualize: bool = False,
        periods_per_year: int = TRADING_DAYS,
    ) -> np.ndarray:

        rc = (
            cls.risk_contributions(
                weights,
                covariance,
                annualize=annualize,
                periods_per_year=periods_per_year,
            )
        )

        total = float(
            rc.sum()
        )

        if not np.isfinite(
            total
        ):
            raise ValueError(
                "Total risk contribution "
                "is non-finite."
            )

        if (
            total
            <= cls.TOLERANCE
        ):
            raise ValueError(
                "Total portfolio risk "
                "must be positive."
            )

        return (
            rc
            / total
        )

    # ========================================================
    # ABSOLUTE RISK CONTRIBUTION %
    # ========================================================

    @classmethod
    def absolute_risk_contribution_pct(
        cls,
        weights,
        covariance,
        annualize: bool = False,
        periods_per_year: int = TRADING_DAYS,
    ) -> np.ndarray:

        rc = (
            cls.risk_contributions(
                weights,
                covariance,
                annualize=annualize,
                periods_per_year=periods_per_year,
            )
        )

        absolute_rc = np.abs(
            rc
        )

        total = float(
            absolute_rc.sum()
        )

        if (
            total
            <= cls.TOLERANCE
        ):
            raise ValueError(
                "Absolute risk contribution "
                "must be positive."
            )

        return (
            absolute_rc
            / total
        )

    # ========================================================
    # RISK BUDGET ERROR
    # ========================================================

    @classmethod
    def risk_budget_error(
        cls,
        weights,
        covariance,
        target_budget,
        annualize: bool = False,
        periods_per_year: int = TRADING_DAYS,
    ) -> np.ndarray:

        actual = (
            cls.risk_contribution_pct(
                weights,
                covariance,
                annualize=annualize,
                periods_per_year=periods_per_year,
            )
        )

        target_budget = np.asarray(
            target_budget,
            dtype=float,
        ).reshape(-1)

        if (
            target_budget.size
            != actual.size
        ):
            raise ValueError(
                "Target risk budget dimension "
                "does not match portfolio."
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
                "Target risk budget cannot "
                "contain negative values."
            )

        total = float(
            target_budget.sum()
        )

        if (
            total
            <= cls.TOLERANCE
        ):
            raise ValueError(
                "Target risk budget must have "
                "a positive total."
            )

        target_budget = (
            target_budget
            / total
        )

        return (
            actual
            - target_budget
        )


# ============================================================
# RISK BUDGET REPORT
# ============================================================

class RiskBudgetReport:

    @staticmethod
    def create(
        asset_names,
        weights,
        covariance,
        target_budget,
        annualize: bool = False,
        periods_per_year: int = TRADING_DAYS,
    ):

        actual = (
            RiskContributionAnalytics
            .risk_contribution_pct(
                weights,
                covariance,
                annualize=annualize,
                periods_per_year=periods_per_year,
            )
        )

        target_budget = np.asarray(
            target_budget,
            dtype=float,
        ).reshape(-1)

        if (
            len(asset_names)
            != actual.size
        ):
            raise ValueError(
                "Asset names and portfolio "
                "dimensions must match."
            )

        if (
            target_budget.size
            != actual.size
        ):
            raise ValueError(
                "Target budget and portfolio "
                "dimensions must match."
            )

        total = float(
            target_budget.sum()
        )

        if total <= 1e-12:
            raise ValueError(
                "Target budget must have "
                "a positive total."
            )

        target_budget = (
            target_budget
            / total
        )

        return pd.DataFrame(
            {
                "Asset":
                    asset_names,

                "Target":
                    target_budget,

                "Actual":
                    actual,

                "Difference":
                    actual
                    - target_budget,
            }
        )


# ============================================================
# REGRESSION TESTS
# ============================================================

def test_risk_contribution_analytics():

    covariance = np.array([
        [0.04, 0.01],
        [0.01, 0.09],
    ])

    weights = np.array([
        0.60,
        0.40,
    ])

    # --------------------------------------------------------
    # DAILY / NATIVE RISK
    # --------------------------------------------------------

    daily_variance = (
        RiskContributionAnalytics
        .portfolio_variance(
            weights,
            covariance,
        )
    )

    daily_volatility = (
        RiskContributionAnalytics
        .portfolio_volatility(
            weights,
            covariance,
        )
    )

    assert np.isclose(
        daily_volatility,
        np.sqrt(
            daily_variance
        ),
    )

    # --------------------------------------------------------
    # ANNUALIZED RISK
    # --------------------------------------------------------

    annual_variance = (
        RiskContributionAnalytics
        .portfolio_variance(
            weights,
            covariance,
            annualize=True,
        )
    )

    annual_volatility = (
        RiskContributionAnalytics
        .portfolio_volatility(
            weights,
            covariance,
            annualize=True,
        )
    )

    assert np.isclose(
        annual_variance,
        daily_variance
        * TRADING_DAYS,
    )

    assert np.isclose(
        annual_volatility,
        daily_volatility
        * np.sqrt(
            TRADING_DAYS
        ),
    )

    # --------------------------------------------------------
    # RISK CONTRIBUTIONS
    # --------------------------------------------------------

    rc_daily = (
        RiskContributionAnalytics
        .risk_contributions(
            weights,
            covariance,
        )
    )

    rc_annual = (
        RiskContributionAnalytics
        .risk_contributions(
            weights,
            covariance,
            annualize=True,
        )
    )

    assert np.isclose(
        rc_daily.sum(),
        daily_volatility,
        atol=1e-10,
    )

    assert np.isclose(
        rc_annual.sum(),
        annual_volatility,
        atol=1e-10,
    )

    # --------------------------------------------------------
    # CONTRIBUTION PERCENTAGES
    # --------------------------------------------------------

    pct_daily = (
        RiskContributionAnalytics
        .risk_contribution_pct(
            weights,
            covariance,
        )
    )

    pct_annual = (
        RiskContributionAnalytics
        .risk_contribution_pct(
            weights,
            covariance,
            annualize=True,
        )
    )

    assert np.isclose(
        pct_daily.sum(),
        1.0,
        atol=1e-10,
    )

    assert np.isclose(
        pct_annual.sum(),
        1.0,
        atol=1e-10,
    )

    # Annualization changes absolute risk but
    # NOT percentage risk contributions.

    assert np.allclose(
        pct_daily,
        pct_annual,
        atol=1e-10,
    )

    # --------------------------------------------------------
    # BUDGET ERROR
    # --------------------------------------------------------

    target = np.array([
        0.50,
        0.50,
    ])

    error = (
        RiskContributionAnalytics
        .risk_budget_error(
            weights,
            covariance,
            target,
            annualize=True,
        )
    )

    assert error.shape == (
        2,
    )

    assert np.isfinite(
        error
    ).all()

    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    report = (
        RiskBudgetReport.create(
            ["A", "B"],
            weights,
            covariance,
            target,
            annualize=True,
        )
    )

    assert len(report) == 2

    assert (
        "Target"
        in report.columns
    )

    assert (
        "Actual"
        in report.columns
    )

    assert (
        "Difference"
        in report.columns
    )

    print(
        "RiskContributionAnalytics tests passed."
    )


if __name__ == "__main__":
    test_risk_contribution_analytics()
