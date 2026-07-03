"""
===============================================================
RISK MODEL

Institutional Portfolio Risk Model

Consumes covariance estimators and produces
portfolio risk analytics.

===============================================================
"""

from __future__ import annotations

import numpy as np

from basecomponent import BaseObject


# ============================================================
# RISK MODEL
# ============================================================

class RiskModel(BaseObject):

    """
    Institutional portfolio risk model.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (

        "portfolio_volatility",

        "portfolio_variance",

        "marginal_risk",

        "component_risk",

        "risk_contributions",

        "metadata"

    )

    # ========================================================
    # CONSTRUCTOR
    # ========================================================

    def __init__(self):

        super().__init__()

        self.last_covariance = None

        self.last_weights = None

        self._summary = {}

    # ========================================================
    # VALIDATION
    # ========================================================

    @staticmethod
    def validate_inputs(
        covariance,
        weights
    ):

        covariance = np.asarray(
            covariance,
            dtype=float
        )

        weights = np.asarray(
            weights,
            dtype=float
        )

        if covariance.ndim != 2:

            raise ValueError(
                "Covariance must be 2-dimensional."
            )

        if covariance.shape[0] != covariance.shape[1]:

            raise ValueError(
                "Covariance must be square."
            )

        if covariance.shape[0] != len(weights):

            raise ValueError(
                "Weights and covariance dimension mismatch."
            )

        if not np.isfinite(covariance).all():

            raise ValueError(
                "Covariance contains non-finite values."
            )

        if not np.isfinite(weights).all():

            raise ValueError(
                "Weights contain non-finite values."
            )

        return covariance, weights

    # ========================================================
    # METADATA
    # ========================================================

    @property
    def metadata(
        self
    ):

        metadata = super().metadata

        dimension = None

        if self.last_covariance is not None:

            dimension = self.last_covariance.shape[0]

        metadata.update(

            {

                "dimension":

                    dimension,

                "has_result":

                    self.last_covariance is not None,

                "analytics": (

                    "variance",

                    "volatility",

                    "marginal",

                    "component",

                    "contributions",

                    "diversification"

                )

            }

        )

        return metadata

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self
    ):

        if self.last_covariance is None:

            return True

        if self.last_weights is None:

            raise RuntimeError(
                "Weights missing."
            )

        if self.last_covariance.shape[0] != len(
            self.last_weights
        ):

            raise RuntimeError(
                "Dimension mismatch."
            )

        if not np.allclose(

            self.last_covariance,

            self.last_covariance.T,

            atol=1e-10

        ):

            raise RuntimeError(
                "Covariance not symmetric."
            )

        return True
    
    # ========================================================
    # PORTFOLIO VARIANCE
    # ========================================================

    def portfolio_variance(
        self,
        covariance,
        weights
    ):

        covariance, weights = self.validate_inputs(
            covariance,
            weights
        )

        variance = float(

            weights.T

            @

            covariance

            @

            weights

        )

        self.last_covariance = covariance

        self.last_weights = weights

        self._summary = {

            "variance": variance

        }

        return variance
    
    # ========================================================
    # PORTFOLIO VOLATILITY
    # ========================================================

    def portfolio_volatility(
        self,
        covariance,
        weights
    ):

        variance = self.portfolio_variance(

            covariance,

            weights

        )

        volatility = float(

            np.sqrt(

                variance

            )

        )

        self._summary.update(

            {

                "volatility":

                    volatility

            }

        )

        return volatility
    
    # ========================================================
    # MARGINAL RISK
    # ========================================================

    def marginal_risk(
        self,
        covariance,
        weights
    ):

        covariance, weights = self.validate_inputs(

            covariance,

            weights

        )

        sigma = self.portfolio_volatility(

            covariance,

            weights

        )

        marginal = (

            covariance

            @

            weights

        ) / sigma

        self._summary.update(

            {

                "marginal_risk":

                    marginal

            }

        )

        return marginal
    
    # ========================================================
    # COMPONENT RISK
    # ========================================================

    def component_risk(
        self,
        covariance,
        weights
    ):

        marginal = self.marginal_risk(

            covariance,

            weights

        )

        component = (

            weights

            *

            marginal

        )

        self._summary.update(

            {

                "component_risk":

                    component

            }

        )

        return component
    
    # ========================================================
    # RISK CONTRIBUTIONS
    # ========================================================

    def risk_contributions(
        self,
        covariance,
        weights
    ):

        component = self.component_risk(

            covariance,

            weights

        )

        total = component.sum()

        contribution = (

            component

            /

            total

        )

        self._summary.update(

            {

                "risk_contributions":

                    contribution

            }

        )

        return contribution

    # ========================================================
    # DIVERSIFICATION RATIO
    # ========================================================

    def diversification_ratio(
        self,
        covariance,
        weights
    ):

        covariance, weights = self.validate_inputs(
            covariance,
            weights
        )

        asset_volatility = np.sqrt(
            np.diag(covariance)
        )

        portfolio_volatility = self.portfolio_volatility(
            covariance,
            weights
        )

        ratio = (

            weights
            @
            asset_volatility

        ) / portfolio_volatility

        self._summary.update(

            {

                "diversification_ratio":

                    float(ratio)

            }

        )

        return float(ratio)
    
    # ========================================================
    # CORRELATION MATRIX
    # ========================================================

    def correlation_matrix(
        self,
        covariance
    ):

        covariance = np.asarray(
            covariance,
            dtype=float
        )

        volatility = np.sqrt(
            np.diag(covariance)
        )

        denominator = np.outer(
            volatility,
            volatility
        )

        correlation = np.divide(

            covariance,

            denominator,

            out=np.zeros_like(
                covariance
            ),

            where=denominator > 0

        )

        np.fill_diagonal(
            correlation,
            1.0
        )

        return correlation
    
# ============================================================
# REGRESSION TESTS
# ============================================================

def test_risk_model():

    np.random.seed(42)

    n_assets = 10

    X = np.random.normal(

        0,

        0.02,

        size=(1000, n_assets)

    )

    covariance = np.cov(

        X,

        rowvar=False

    )

    weights = np.ones(

        n_assets

    ) / n_assets

    risk = RiskModel()

    # ========================================================
    # PORTFOLIO VARIANCE
    # ========================================================

    variance = risk.portfolio_variance(

        covariance,

        weights

    )

    assert variance > 0

    # ========================================================
    # PORTFOLIO VOLATILITY
    # ========================================================

    volatility = risk.portfolio_volatility(

        covariance,

        weights

    )

    assert volatility > 0

    assert np.isclose(

        volatility,

        np.sqrt(variance)

    )

    # ========================================================
    # MARGINAL RISK
    # ========================================================

    marginal = risk.marginal_risk(

        covariance,

        weights

    )

    assert marginal.shape == (

        n_assets,

    )

    assert np.isfinite(

        marginal

    ).all()

    # ========================================================
    # COMPONENT RISK
    # ========================================================

    component = risk.component_risk(

        covariance,

        weights

    )

    assert component.shape == (

        n_assets,

    )

    assert np.isfinite(

        component

    ).all()

    # ========================================================
    # RISK CONTRIBUTIONS
    # ========================================================

    contribution = risk.risk_contributions(

        covariance,

        weights

    )

    assert contribution.shape == (

        n_assets,

    )

    assert np.isclose(

        contribution.sum(),

        1.0,

        atol=1e-8

    )

    # ========================================================
    # EULER DECOMPOSITION
    # ========================================================

    assert np.isclose(

        component.sum(),

        volatility,

        atol=1e-8

    )

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    assert risk.health_check()

    # ========================================================
    # METADATA
    # ========================================================

    metadata = risk.metadata

    assert metadata["version"] == "1.0.0"

    assert metadata["dimension"] == n_assets

    assert metadata["has_result"]

    # ========================================================
    # SUMMARY
    # ========================================================

    summary = risk.summary()

    assert "variance" in summary

    assert "volatility" in summary

    assert "marginal_risk" in summary

    assert "component_risk" in summary

    assert "risk_contributions" in summary

    # ========================================================
    # INVALID DIMENSIONS
    # ========================================================

    try:

        risk.portfolio_variance(

            covariance,

            np.ones(5)

        )

        raise AssertionError(

            "Expected ValueError"

        )

    except ValueError:

        pass

    # ========================================================
    # DIVERSIFICATION
    # ========================================================

    diversification = risk.diversification_ratio(

        covariance,

        weights

    )

    assert diversification >= 1.0

    # ========================================================
    # CORRELATION
    # ========================================================

    correlation = risk.correlation_matrix(

        covariance

    )

    assert correlation.shape == (

        n_assets,

        n_assets

    )

    assert np.allclose(

        np.diag(correlation),

        1.0

    )
    
    
    # ========================================================
    # API FREEZE
    # ========================================================

    assert RiskModel.API_VERSION == "1.0.0"

    assert tuple(
        RiskModel.PUBLIC_METHODS
    ) == (

        "portfolio_volatility",

        "portfolio_variance",

        "marginal_risk",

        "component_risk",

        "risk_contributions",

        "metadata"

    )

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    test_risk_model()