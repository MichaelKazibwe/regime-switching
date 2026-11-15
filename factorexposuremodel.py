"""
===============================================================
FACTOR EXPOSURE MODEL

Institutional Factor Exposure Engine

Computes portfolio exposure to systematic risk factors.

===============================================================
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from basecomponent import BaseObject

from portfolio import Portfolio

# ============================================================
# FACTOR EXPOSURE MODEL
# ============================================================

class FactorExposureModel(BaseObject):

    """
    Institutional factor exposure engine.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (

        "fit",

        "portfolio_exposure",

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

        self.factor_returns = None

        self.factor_loadings = None

        self.asset_loadings = None

        self.last_summary = None

    # ========================================================
    # FIT
    # ========================================================

    def fit(
        self,
        factor_returns: pd.DataFrame,
        asset_returns: pd.DataFrame
    ):

        """
        Store factor and asset return matrices.

        Statistical estimation is added in Part 2.
        """

        if not isinstance(
            factor_returns,
            pd.DataFrame
        ):

            raise TypeError(
                "factor_returns must be a DataFrame."
            )

        if not isinstance(
            asset_returns,
            pd.DataFrame
        ):

            raise TypeError(
                "asset_returns must be a DataFrame."
            )

        if len(
            factor_returns
        ) != len(
            asset_returns
        ):

            raise ValueError(
                "Factor and asset returns must have the same number of observations."
            )

        self.factor_returns = factor_returns.copy()

        self.asset_returns = asset_returns.copy()

        return self

    # ========================================================
    # ESTIMATE LOADINGS
    # ========================================================

    def estimate_loadings(
        self
    ):

        """
        Estimate factor loadings using
        Ordinary Least Squares.

        For each asset

            asset = factors * beta + residual
        """

        if self.factor_returns is None:

            raise RuntimeError(
                "Model has not been fitted."
            )

        X = self.factor_returns.values

        X = np.column_stack(

            [

                np.ones(
                    len(X)
                ),

                X

            ]

        )

        loadings = {}

        for asset in self.asset_returns.columns:

            y = self.asset_returns[
                asset
            ].values

            beta, *_ = np.linalg.lstsq(

                X,

                y,

                rcond=None

            )

            loadings[asset] = beta[1:]

        self.asset_loadings = pd.DataFrame(

            loadings,

            index=self.factor_returns.columns

        ).T

        return self.asset_loadings
    
    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
        self
    ):

        self.last_summary = {

            "fitted":

                self.factor_returns is not None,

            "estimated":

                self.asset_loadings is not None,

            "factors":

                0

                if self.factor_returns is None

                else self.factor_returns.shape[1],

            "assets":

                0

                if self.asset_returns is None

                else self.asset_returns.shape[1],

            "observations":

                0

                if self.factor_returns is None

                else len(
                    self.factor_returns
                )

        }

        return dict(
            self.last_summary
        )

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

        if self.factor_returns is not None:

            if not np.isfinite(

                self.factor_returns.values

            ).all():

                raise RuntimeError(

                    "Invalid factor returns."

                )

        if self.asset_returns is not None:

            if not np.isfinite(

                self.asset_returns.values

            ).all():

                raise RuntimeError(

                    "Invalid asset returns."

                )

        if self.asset_loadings is not None:

            if not np.isfinite(

                self.asset_loadings.values

            ).all():

                raise RuntimeError(

                    "Invalid factor loadings."

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

            "factor_loadings":

                None

                if self.asset_loadings is None

                else self.asset_loadings.to_dict(),

            "factor_covariance":

                None

                if self.factor_returns is None

                else self.factor_covariance().to_dict()

        }

    # ========================================================
    # FROM DICTIONARY
    # ========================================================

    @classmethod
    def from_dict(
        cls,
        data
    ):

        model = cls()

        return model
    
    # ========================================================
    # PORTFOLIO EXPOSURE
    # ========================================================

    def portfolio_exposure(
        self,
        portfolio: Portfolio
    ):

        """
        Compute portfolio factor exposure.

        exposure = wᵀ β
        """

        if self.asset_loadings is None:

            raise RuntimeError(
                "Factor loadings have not been estimated."
            )

        weights = pd.Series(

            portfolio.holdings

        )

        weights = weights.reindex(

            self.asset_loadings.index

        ).fillna(

            0.0

        )

        exposure = (

            weights.values

            @

            self.asset_loadings.values

        )

        return pd.Series(

            exposure,

            index=self.asset_loadings.columns,

            name="Exposure"

        )
    
    # ========================================================
    # SPECIFIC RETURNS
    # ========================================================

    def specific_returns(
        self
    ):

        """
        Residual returns after removing
        systematic factor effects.
        """

        if self.asset_loadings is None:

            raise RuntimeError(
                "Estimate loadings first."
            )

        X = self.factor_returns.values

        X = np.column_stack(

            [

                np.ones(
                    len(X)
                ),

                X

            ]

        )

        residuals = {}

        for asset in self.asset_returns.columns:

            beta = np.concatenate(

                [

                    [0.0],

                    self.asset_loadings.loc[
                        asset
                    ].values

                ]

            )

            fitted = X @ beta

            residuals[asset] = (

                self.asset_returns[
                    asset
                ].values

                -

                fitted

            )

        return pd.DataFrame(

            residuals,

            index=self.asset_returns.index

        )
    
    # ========================================================
    # FACTOR COVARIANCE
    # ========================================================

    def factor_covariance(
        self
    ):

        """
        Covariance matrix of factors.
        """

        if self.factor_returns is None:

            raise RuntimeError(
                "Model has not been fitted."
            )

        return self.factor_returns.cov()
