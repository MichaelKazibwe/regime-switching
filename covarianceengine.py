"""
===============================================================
COVARIANCE ENGINE

Institutional covariance estimation engine.

Provides a unified interface for covariance estimation,
validation, diagnostics and state management.

Current estimators

    • Ledoit-Wolf
    • EWMA
    • Rolling

Future estimators

    • Regime Covariance
    • Factor Covariance
    • Ensemble Covariance

===============================================================
"""

import numpy as np
import pandas as pd

from sklearn.covariance import LedoitWolf


# ============================================================
# COVARIANCE ENGINE
# ============================================================

class CovarianceEngine:

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (

    "estimate",

    "ledoit_wolf",

    "ewma",

    "rolling",

    "validate",

    "diagnostics"

)
    
    @property
    def metadata(self):

     return {

        "version": self.API_VERSION,

        "available_methods": self.available_methods,

        "last_method": self.last_method,

        "dimension": (

            None

            if self.last_covariance is None

            else self.last_covariance.shape[0]

        )

    }

    """
    Institutional covariance estimation engine.

    Public API
    ----------

    estimate()

    ledoit_wolf()

    ewma()

    rolling()

    validate()

    diagnostics()

    available_methods

    Everything beginning with "_"
    is considered private implementation.
    """

    # ========================================================
    # CONSTRUCTOR
    # ========================================================

    def __init__(self):

        self.last_covariance = None

        self.last_method = None

        self.last_diagnostics = None

    # ========================================================
    # INTERNAL HELPERS
    # ========================================================

    @staticmethod
    def _ensure_dataframe(
        returns
    ):

        """
        Convert ndarray into DataFrame.
        """

        if isinstance(
            returns,
            np.ndarray
        ):

            returns = pd.DataFrame(
                returns
            )

        if not isinstance(
            returns,
            pd.DataFrame
        ):

            raise TypeError(
                "Returns must be a pandas DataFrame "
                "or numpy ndarray."
            )

        return returns

    @classmethod
    def _clean_returns(
        cls,
        returns
    ):

        """
        Standard preprocessing.
        """

        returns = cls._ensure_dataframe(
            returns
        )

        returns = returns.dropna()

        if len(
            returns
        ) < 2:

            raise ValueError(
                "Insufficient observations."
            )

        return returns

    @staticmethod
    def _effective_rank(
        covariance
    ):

        """
        Effective matrix rank.

        exp(entropy(eigenvalues))
        """

        eig = np.linalg.eigvalsh(
            covariance
        )

        eig = np.maximum(
            eig,
            0.0
        )

        total = eig.sum()

        if total <= 0:

            return 0.0

        p = eig / total

        p = p[p > 0]

        entropy = -np.sum(
            p * np.log(
                p
            )
        )

        return float(
            np.exp(
                entropy
            )
        )

    # ========================================================
    # VALIDATION
    # ========================================================

    def validate(
        self,
        covariance
    ):

        """
        Validate covariance matrix.
        """

        covariance = np.asarray(
            covariance,
            dtype=float
        )

        if covariance.ndim != 2:

            raise ValueError(
                "Covariance must be two-dimensional."
            )

        rows, cols = covariance.shape

        if rows != cols:

            raise ValueError(
                "Covariance matrix must be square."
            )

        if not np.isfinite(
            covariance
        ).all():

            raise ValueError(
                "Covariance contains non-finite values."
            )

        if not np.allclose(

            covariance,

            covariance.T,

            atol=1e-10

        ):

            raise ValueError(
                "Covariance matrix is not symmetric."
            )

        eigenvalues = np.linalg.eigvalsh(
            covariance
        )

        if eigenvalues.min() < -1e-8:

            raise ValueError(
                "Covariance matrix is not positive semi-definite."
            )

        return covariance

    # ========================================================
    # DIAGNOSTICS
    # ========================================================

    def diagnostics(
        self,
        covariance
    ):

        """
        Compute covariance diagnostics.
        """

        covariance = self.validate(
            covariance
        )

        eigenvalues = np.linalg.eigvalsh(
            covariance
        )

        eigenvalues = np.maximum(
            eigenvalues,
            0.0
        )

        volatility = np.sqrt(
            np.diag(
                covariance
            )
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

        off_diag = correlation[
            ~np.eye(
                correlation.shape[0],
                dtype=bool
            )
        ]

        try:

            inverse = np.linalg.inv(
                covariance
            )

        except np.linalg.LinAlgError:

            inverse = np.linalg.pinv(
                covariance
            )

        diagnostics = {

            "dimension":
                covariance.shape[0],

            "rank":
                int(
                    np.linalg.matrix_rank(
                        covariance
                    )
                ),

            "trace":
                float(
                    np.trace(
                        covariance
                    )
                ),

            "determinant":
                float(
                    np.linalg.det(
                        covariance
                    )
                ),

            "minimum_eigenvalue":
                float(
                    eigenvalues.min()
                ),

            "maximum_eigenvalue":
                float(
                    eigenvalues.max()
                ),

            "effective_rank":
                self._effective_rank(
                    covariance
                ),

            "condition_number":
                float(
                    np.linalg.cond(
                        covariance
                    )
                ),

            "is_positive_semidefinite":
                bool(
                    eigenvalues.min()
                    >=
                    -1e-8
                ),

            "average_volatility":
                float(
                    volatility.mean()
                ),

            "maximum_volatility":
                float(
                    volatility.max()
                ),

            "minimum_volatility":
                float(
                    volatility.min()
                ),

            "average_correlation":
                float(
                    off_diag.mean()
                ),

            "maximum_correlation":
                float(
                    off_diag.max()
                ),

            "minimum_correlation":
                float(
                    off_diag.min()
                ),

            "correlation_matrix":
                correlation,

            "inverse_covariance":
                inverse,

            "volatility_vector":
                volatility,

            "eigenvalues":
                eigenvalues

        }

        self.last_diagnostics = (
            diagnostics
        )

        return diagnostics

    # ========================================================
    # STATE UPDATE
    # ========================================================

    def _update_state(
        self,
        covariance,
        method
    ):

        """
        Persist latest covariance estimate.
        """

        covariance = self.validate(
            covariance
        )

        self.last_covariance = (
            covariance
        )

        self.last_method = (
            method
        )

        self.last_diagnostics = (
            self.diagnostics(
                covariance
            )
        )

        return covariance

    # ========================================================
    # ESTIMATE
    # ========================================================

    def estimate(
        self,
        returns,
        method="ledoit_wolf",
        **kwargs
    ):

        """
        Unified covariance estimation interface.

        Examples
        --------

        estimate(returns)

        estimate(
            returns,
            method="ewma",
            decay=0.97
        )

        estimate(
            returns,
            method="rolling",
            window=126
        )
        """

        method = method.lower().strip()

        dispatch = {

            "ledoit_wolf":

                lambda: self.ledoit_wolf(
                    returns
                ),

            "ewma":

                lambda: self.ewma(

                    returns,

                    decay=kwargs.get(
                        "decay",
                        0.94
                    )

                ),

            "rolling":

                lambda: self.rolling(

                    returns,

                    window=kwargs.get(
                        "window",
                        252
                    )

                )

        }

        if method not in dispatch:

            raise ValueError(

                f"Unknown covariance estimator '{method}'. "

                f"Available methods: "

                f"{', '.join(dispatch.keys())}"

            )

        return dispatch[
            method
        ]()

    # ========================================================
    # LEDOIT-WOLF
    # ========================================================

    def ledoit_wolf(
        self,
        returns
    ):

        """
        Ledoit-Wolf shrinkage covariance estimator.
        """

        returns = self._clean_returns(
            returns
        )

        estimator = LedoitWolf()

        estimator.fit(
            returns.values
        )

        covariance = (
            estimator.covariance_
        )

        return self._update_state(

            covariance,

            "ledoit_wolf"

        )

    # ========================================================
    # EWMA
    # ========================================================

    def ewma(
        self,
        returns,
        decay=0.94
    ):

        """
        Exponentially weighted covariance matrix.
        """

        if not (

            0 < decay < 1

        ):

            raise ValueError(
                "Decay must lie in (0,1)."
            )

        returns = self._clean_returns(
            returns
        )

        x = (
            returns.values.astype(
                float
            )
        )

        x = (

            x

            -

            x.mean(
                axis=0,
                keepdims=True
            )

        )

        n = x.shape[0]

        weights = np.array(

            [

                (1 - decay)

                *

                decay ** (
                    n - i - 1
                )

                for i in range(
                    n
                )

            ],

            dtype=float

        )

        weights /= (
            weights.sum()
        )

        covariance = (

            x.T

            @

            (

                x

                *

                weights.reshape(
                    -1,
                    1
                )

            )

        )

        covariance = (

            covariance
            +
            covariance.T

        ) / 2.0

        return self._update_state(

            covariance,

            "ewma"

        )

    # ========================================================
    # ROLLING
    # ========================================================

    def rolling(
        self,
        returns,
        window=252
    ):

        """
        Rolling sample covariance estimator.
        """

        returns = self._clean_returns(
            returns
        )

        if len(
            returns
        ) < window:

            raise ValueError(

                f"Need at least "

                f"{window} observations."

            )

        covariance = (

            returns

            .iloc[-window:]

            .cov()

            .values

        )

        return self._update_state(

            covariance,

            f"rolling_{window}"

        )

    # ========================================================
    # AVAILABLE METHODS
    # ========================================================

    @property
    def available_methods(
        self
    ):

        return [

            "ledoit_wolf",

            "ewma",

            "rolling"

        ]

# ============================================================
# REGRESSION TESTS
# ============================================================

def test_covariance_engine():

    np.random.seed(42)

    returns = pd.DataFrame(

        np.random.normal(

            0.001,

            0.02,

            size=(750, 12)

        ),

        columns=[

            f"Asset_{i}"

            for i in range(12)

        ]

    )

    engine = CovarianceEngine()

    # ========================================================
    # PUBLIC API
    # ========================================================

    assert isinstance(

        engine.available_methods,

        list

    )

    assert set(

        engine.available_methods

    ) == {

        "ledoit_wolf",

        "ewma",

        "rolling"

    }

    # ========================================================
    # LEDOIT-WOLF
    # ========================================================

    covariance = engine.ledoit_wolf(
        returns
    )

    assert covariance.shape == (
        12,
        12
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

    assert (
        engine.last_method
        ==
        "ledoit_wolf"
    )

    # ========================================================
    # EWMA
    # ========================================================

    covariance = engine.ewma(
        returns
    )

    assert covariance.shape == (
        12,
        12
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

    assert (
        engine.last_method
        ==
        "ewma"
    )

    # ========================================================
    # ROLLING
    # ========================================================

    covariance = engine.rolling(
        returns,
        window=252
    )

    assert covariance.shape == (
        12,
        12
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

    assert (
        engine.last_method
        ==
        "rolling_252"
    )

    # ========================================================
    # ESTIMATE DISPATCHER
    # ========================================================

    for method in engine.available_methods:

        covariance = engine.estimate(

            returns,

            method=method

        )

        assert covariance.shape == (
            12,
            12
        )

    # ========================================================
    # DIAGNOSTICS
    # ========================================================

    diagnostics = (
        engine.last_diagnostics
    )

    required = {

        "dimension",
        "rank",
        "trace",
        "determinant",
        "minimum_eigenvalue",
        "maximum_eigenvalue",
        "effective_rank",
        "condition_number",
        "is_positive_semidefinite",
        "average_volatility",
        "maximum_volatility",
        "minimum_volatility",
        "average_correlation",
        "maximum_correlation",
        "minimum_correlation",
        "correlation_matrix",
        "inverse_covariance",
        "volatility_vector",
        "eigenvalues"

    }

    assert required.issubset(
        diagnostics.keys()
    )

    assert diagnostics[
        "correlation_matrix"
    ].shape == (
        12,
        12
    )

    assert diagnostics[
        "inverse_covariance"
    ].shape == (
        12,
        12
    )

    assert len(
        diagnostics[
            "volatility_vector"
        ]
    ) == 12

    assert len(
        diagnostics[
            "eigenvalues"
        ]
    ) == 12

    # ========================================================
    # INVALID INPUTS
    # ========================================================

    try:

        engine.ewma(

            returns,

            decay=1.2

        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    try:

        engine.rolling(

            returns,

            window=5000

        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    try:

        engine.estimate(

            returns,

            method="unknown"

        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ========================================================
    # API METADATA
    # ========================================================

    assert engine.API_VERSION == "1.0.0"

    assert "estimate" in engine.PUBLIC_METHODS

    assert "ledoit_wolf" in engine.PUBLIC_METHODS

    assert "ewma" in engine.PUBLIC_METHODS

    assert "rolling" in engine.PUBLIC_METHODS

    metadata = engine.metadata

    assert metadata["version"] == "1.0.0"

    assert metadata["last_method"] == "rolling_252"

    assert metadata["dimension"] == 12

    print(
        "CovarianceEngine tests passed."
    )
    