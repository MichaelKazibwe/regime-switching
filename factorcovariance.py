"""
===============================================================
FACTOR COVARIANCE

Institutional factor-model covariance estimator.

Implements the classical decomposition

    Σ = B F B' + D

where

    B : factor loadings
    F : factor covariance
    D : specific risk

===============================================================
"""

import numpy as np

from basecovariancemodel import BaseCovarianceModel

# ============================================================
# FACTOR COVARIANCE
# ============================================================

class FactorCovariance(BaseCovarianceModel):

    """
    Factor-model covariance estimator.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (

        "fit",

        "estimate",

        "summary",

        "metadata"

    )

    SUPPORTED_FACTOR_MODEL = (

    "B F B' + D"

    )

    # ========================================================
    # CONSTRUCTOR
    # ========================================================

    def __init__(self):

        super().__init__()

        self.factor_loadings = None

        self.factor_covariance = None

        self.specific_risk = None

        self.asset_names = None

        self.factor_names = None

    # ========================================================
    # FIT
    # ========================================================

    def fit(

        self,

        factor_loadings,

        factor_covariance,

        specific_risk

    ):

        self.factor_loadings = np.asarray(

            factor_loadings,

            dtype=float

        )

        self.factor_covariance = np.asarray(

            factor_covariance,

            dtype=float

        )

        self.specific_risk = np.asarray(

            specific_risk,

            dtype=float

        )

        n_assets, n_factors = (

            self.factor_loadings.shape

        )

        if self.factor_covariance.shape != (

            n_factors,

            n_factors

        ):

            raise ValueError(

                "Factor covariance dimensions do not match."

            )

        if self.specific_risk.shape != (

            n_assets,

            n_assets

        ):

            raise ValueError(

                "Specific risk dimensions do not match."

            )

        self.asset_names = [

            f"Asset_{i}"

            for i in range(

                n_assets

            )

        ]

        self.factor_names = [

            f"Factor_{i}"

            for i in range(

                n_factors

            )

        ]

        return self

    # ========================================================
    # AVAILABLE
    # ========================================================

    @property
    def n_assets(
        self
    ):

        if self.factor_loadings is None:

            return 0

        return self.factor_loadings.shape[0]

    @property
    def n_factors(
        self
    ):

        if self.factor_loadings is None:

            return 0

        return self.factor_loadings.shape[1]

    # ========================================================
    # METADATA
    # ========================================================

    @property
    def metadata(
        self
    ):

        metadata = super().metadata

        metadata.update(

            {

                "assets":

                    self.n_assets,

                "factors":

                    self.n_factors,

                "factor_model":

                    self.SUPPORTED_FACTOR_MODEL,

                "is_fitted":

                    self.factor_loadings is not None

            }

        )

        return metadata
    
    # ========================================================
    # ESTIMATE
    # ========================================================

    def estimate(
        self
    ):

        """
        Estimate the asset covariance matrix.

        Σ = B F B' + D
        """

        if self.factor_loadings is None:

            raise RuntimeError(
                "Factor model has not been fitted."
            )

        covariance = (

            self.factor_loadings

            @

            self.factor_covariance

            @

            self.factor_loadings.T

        )

        covariance += self.specific_risk

        covariance = (

            covariance
            +
            covariance.T

        ) / 2.0

        eigenvalues = np.linalg.eigvalsh(
            covariance
        )

        if eigenvalues.min() < -1e-8:

            raise ValueError(
                "Covariance matrix is not positive semi-definite."
            )

        self.last_covariance = covariance

        self.last_summary = {

            "assets":

                self.n_assets,

            "factors":

                self.n_factors,

            "minimum_eigenvalue":

                float(
                    eigenvalues.min()
                ),

            "maximum_eigenvalue":

                float(
                    eigenvalues.max()
                ),

            "trace":

                float(
                    np.trace(
                        covariance
                    )
                ),

            "condition_number":

                float(
                    np.linalg.cond(
                        covariance
                    )
                )

        }

        return covariance

    # ========================================================
    # FACTOR CONTRIBUTION
    # ========================================================

    @property
    def factor_component(
        self
    ):

        if self.factor_loadings is None:

            raise RuntimeError(
                "Factor model has not been fitted."
            )

        return (

            self.factor_loadings

            @

            self.factor_covariance

            @

            self.factor_loadings.T

        )

    # ========================================================
    # SPECIFIC COMPONENT
    # ========================================================

    @property
    def specific_component(
        self
    ):

        if self.specific_risk is None:

            raise RuntimeError(
                "Factor model has not been fitted."
            )

        return self.specific_risk.copy()
    
    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self
    ):

        """
        Validate the internal state of the factor model.
        """

        if self.factor_loadings is None:

            raise RuntimeError(
                "Model has not been fitted."
            )

        if self.factor_covariance is None:

            raise RuntimeError(
                "Missing factor covariance."
            )

        if self.specific_risk is None:

            raise RuntimeError(
                "Missing specific risk."
            )

        if self.factor_loadings.shape[1] != (
            self.factor_covariance.shape[0]
        ):

            raise RuntimeError(
                "Factor dimensions inconsistent."
            )

        if self.factor_loadings.shape[0] != (
            self.specific_risk.shape[0]
        ):

            raise RuntimeError(
                "Asset dimensions inconsistent."
            )

        return True

# ============================================================
# REGRESSION TESTS
# ============================================================

def test_factor_covariance():

    np.random.seed(42)

    n_assets = 12
    n_factors = 5

    # ========================================================
    # SYNTHETIC FACTOR MODEL
    # ========================================================

    factor_loadings = np.random.normal(

        0.0,

        1.0,

        size=(n_assets, n_factors)

    )

    A = np.random.normal(

        size=(n_factors, n_factors)

    )

    factor_covariance = (

        A @ A.T

    )

    specific_risk = np.diag(

        np.random.uniform(

            0.01,

            0.05,

            size=n_assets

        )

    )

    engine = FactorCovariance()

    # ========================================================
    # FIT
    # ========================================================

    engine.fit(

        factor_loadings,

        factor_covariance,

        specific_risk

    )

    assert engine.n_assets == n_assets

    assert engine.n_factors == n_factors

    # ========================================================
    # ESTIMATE
    # ========================================================

    covariance = engine.estimate()

    assert covariance.shape == (

        n_assets,

        n_assets

    )

    assert np.isfinite(

        covariance

    ).all()

    assert np.allclose(

        covariance,

        covariance.T,

        atol=1e-10

    )

    eig = np.linalg.eigvalsh(

        covariance

    )

    assert eig.min() >= -1e-8

    # ========================================================
    # FACTOR COMPONENT
    # ========================================================

    factor_component = (

        engine.factor_component

    )

    assert factor_component.shape == (

        n_assets,

        n_assets

    )

    assert np.allclose(

        factor_component,

        factor_component.T,

        atol=1e-10

    )

    # ========================================================
    # SPECIFIC COMPONENT
    # ========================================================

    specific_component = (

        engine.specific_component

    )

    assert specific_component.shape == (

        n_assets,

        n_assets

    )

    assert np.allclose(

        specific_component,

        specific_component.T,

        atol=1e-10

    )

    # ========================================================
    # RECONSTRUCTION
    # ========================================================

    reconstructed = (

        factor_component

        +

        specific_component

    )

    assert np.allclose(

        covariance,

        reconstructed,

        atol=1e-10

    )

    # ========================================================
    # SUMMARY
    # ========================================================

    summary = engine.summary()

    assert summary["assets"] == n_assets

    assert summary["factors"] == n_factors

    assert summary["minimum_eigenvalue"] >= -1e-8

    # ========================================================
    # METADATA
    # ========================================================

    metadata = engine.metadata

    assert metadata["version"] == "1.0.0"

    assert metadata["assets"] == n_assets

    assert metadata["factors"] == n_factors

    # ========================================================
    # ESTIMATE BEFORE FIT
    # ========================================================

    try:

        FactorCovariance().estimate()

        raise AssertionError(
            "Expected RuntimeError"
        )

    except RuntimeError:

        pass

    # ========================================================
    # INVALID FACTOR COVARIANCE
    # ========================================================

    try:

        FactorCovariance().fit(

            factor_loadings,

            np.eye(3),

            specific_risk

        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    assert engine.health_check()

    # ========================================================
    # API FREEZE
    # ========================================================

    assert FactorCovariance.API_VERSION == "1.0.0"

    assert tuple(
        FactorCovariance.PUBLIC_METHODS
    ) == (

        "fit",

        "estimate",

        "summary",

        "metadata"

    )

    # ========================================================
    # METADATA
    # ========================================================

    metadata = engine.metadata

    assert metadata["version"] == "1.0.0"

    assert metadata["assets"] == n_assets

    assert metadata["factors"] == n_factors

    assert metadata["is_fitted"]

    assert metadata["factor_model"] == (

        "B F B' + D"

    )
    
    # ========================================================
    # INVALID SPECIFIC RISK
    # ========================================================

    try:

        FactorCovariance().fit(

            factor_loadings,

            factor_covariance,

            np.eye(5)

        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    print(
        "FactorCovariance tests passed."
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    test_factor_covariance()