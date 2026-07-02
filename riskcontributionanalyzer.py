import numpy as np
import pandas as pd

# ============================================================
# RISK CONTRIBUTION ANALYTICS
# ============================================================

class RiskContributionAnalytics:

    @staticmethod
    def portfolio_volatility(
        weights,
        covariance
    ):

        weights = np.asarray(
            weights,
            dtype=float
        )

        return float(

            np.sqrt(

                weights.T

                @

                covariance

                @

                weights

            )

        )

    @staticmethod
    def marginal_risk(
        weights,
        covariance
    ):

        weights = np.asarray(
            weights,
            dtype=float
        )

        portfolio_vol = (

            RiskContributionAnalytics
            .portfolio_volatility(
                weights,
                covariance
            )

        )

        return (

            covariance
            @
            weights

        ) / portfolio_vol

    @staticmethod
    def risk_contributions(
        weights,
        covariance
    ):

        mrc = (

            RiskContributionAnalytics
            .marginal_risk(
                weights,
                covariance
            )

        )

        return (
            weights
            *
            mrc
        )

    @staticmethod
    def risk_contribution_pct(
        weights,
        covariance
    ):

        rc = (

            RiskContributionAnalytics
            .risk_contributions(
                weights,
                covariance
            )

        )

        total = rc.sum()

        if total <= 0:

            raise ValueError(
                "Invalid total risk contribution"
            )

        return rc / total

    @staticmethod
    def risk_budget_error(
        weights,
        covariance,
        target_budget
    ):

        actual = (

            RiskContributionAnalytics
            .risk_contribution_pct(
                weights,
                covariance
            )

        )

        target_budget = np.asarray(
            target_budget,
            dtype=float
        )

        return (

            actual
            -
            target_budget

        )
    
class RiskBudgetReport:

    @staticmethod
    def create(
        asset_names,
        weights,
        covariance,
        target_budget
    ):

        actual = (

            RiskContributionAnalytics
            .risk_contribution_pct(
                weights,
                covariance
            )

        )

        target_budget = np.asarray(
            target_budget,
            dtype=float
        )

        report = pd.DataFrame({

            "Asset":
                asset_names,

            "Target":

                target_budget,

            "Actual":

                actual,

            "Difference":

                actual
                -
                target_budget

        })

        return report

