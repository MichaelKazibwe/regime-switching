"""
===============================================================
ENSEMBLE COVARIANCE

Institutional covariance ensemble engine.

Combines multiple covariance estimators into a single
production covariance matrix using configurable weights.

Current compatible models

    • CovarianceEngine
    • RegimeCovariance

Future compatible models

    • FactorCovariance
    • HMMCovariance
    • GARCHCovariance
    • DynamicCovariance

===============================================================
"""
import numpy as np

# ============================================================
# ENSEMBLE COVARIANCE
# ============================================================

class EnsembleCovariance:

    """
    Production covariance ensemble.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (

        "add_model",

        "remove_model",

        "estimate",

        "summary"

    )

    SUPPORTED_MODEL_TYPES = (

        "CovarianceEngine",

        "RegimeCovariance",

        "FactorCovariance"

    )

    # ========================================================
    # CONSTRUCTOR
    # ========================================================

    def __init__(self):

        self.models = {}

        self.weights = {}

        self.last_covariance = None

        self.last_summary = None

    # ========================================================
    # VALIDATION
    # ========================================================

    @staticmethod
    def _validate_weights(
        weights
    ):

        total = sum(
            weights.values()
        )

        if total <= 0:

            raise ValueError(
                "Weights must sum to a positive value."
            )

        return {

            key: value / total

            for key, value

            in weights.items()

        }

    @staticmethod
    def _validate_covariance(
        covariance
    ):

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

        return covariance

    # ========================================================
    # MODEL REGISTRATION
    # ========================================================

    def add_model(
        self,
        name,
        model,
        weight=1.0
    ):

        if not hasattr(
            model,
            "estimate"
        ):

            raise TypeError(

                "Model must implement "

                "'estimate()'."

            )

        self.models[
            name
        ] = model

        self.weights[
            name
        ] = float(
            weight
        )

        self.weights = self._validate_weights(
            self.weights
        )

    def remove_model(
        self,
        name
    ):

        if name not in self.models:

            raise KeyError(
                f"{name} not registered."
            )

        del self.models[
            name
        ]

        del self.weights[
            name
        ]

        if self.weights:

            self.weights = self._validate_weights(
                self.weights
            )

    # ========================================================
    # INFORMATION
    # ========================================================

    @property
    def available_models(
        self
    ):

        return sorted(
            self.models.keys()
        )

    @property
    def metadata(
        self
    ):

        return {

            "version":
                self.API_VERSION,

            "models":
                self.available_models,

            "weights":
                dict(
                    self.weights
                ),

            "model_count":
                len(
                    self.models
                ),

            "supported_models":
                list(
                    self.SUPPORTED_MODEL_TYPES
                )

        }
    
    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self
    ):

        """
        Verify that the ensemble is internally consistent.
        """

        if not self.models:

            raise RuntimeError(
                "No models have been registered."
            )

        if not np.isclose(

            sum(
                self.weights.values()
            ),

            1.0

        ):

            raise RuntimeError(
                "Model weights do not sum to one."
            )

        for name in self.models:

            if name not in self.weights:

                raise RuntimeError(

                    f"Missing weight for model '{name}'."

                )

        return True
    
    # ========================================================
    # ESTIMATE
    # ========================================================

    def estimate(
        self,
        model_kwargs=None
    ):

        """
        Estimate an ensemble covariance matrix.

        Parameters
        ----------
        model_kwargs : dict

            Dictionary keyed by model name.

            Example

            {
                "base": {
                    "returns": returns,
                    "method": "ledoit_wolf"
                },

                "regime": {
                    "regime": "Expansion",
                    "method": "ewma"
                }
            }
        """

        if not self.models:

            raise RuntimeError(
                "No models have been registered."
            )

        if model_kwargs is None:

            model_kwargs = {}

        ensemble = None

        dimension = None

        for name, model in self.models.items():

            kwargs = model_kwargs.get(
                name,
                {}
            )

            covariance = model.estimate(
                **kwargs
            )

            covariance = self._validate_covariance(
                covariance
            )

            if dimension is None:

                dimension = covariance.shape

            elif covariance.shape != dimension:

                raise ValueError(

                    "Covariance dimensions "

                    "do not match."

                )

            weight = self.weights[
                name
            ]

            if ensemble is None:

                ensemble = (

                    weight
                    *
                    covariance

                )

            else:

                ensemble += (

                    weight
                    *
                    covariance

                )

        ensemble = (

            ensemble
            +
            ensemble.T

        ) / 2.0

        ensemble = self._validate_covariance(
            ensemble
        )

        self.last_covariance = (
            ensemble
        )

        self.last_summary = {

            "models":

                self.available_models,

            "weights":

                dict(
                    self.weights
                ),

            "dimension":

                ensemble.shape[0]

        }

        return ensemble

    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
        self
    ):

        if self.last_summary is None:

            raise RuntimeError(
                "No ensemble estimate available."
            )

        return dict(
            self.last_summary
        )
    
# ============================================================
# REGRESSION TESTS
# ============================================================

class DummyModel:

    """
    Simple covariance model used for regression tests.
    """

    def __init__(
        self,
        covariance
    ):

        self.covariance = np.asarray(
            covariance,
            dtype=float
        )

    def estimate(
        self,
        **kwargs
    ):

        return self.covariance


# ============================================================

def test_ensemble_covariance():

    covariance1 = np.eye(5)

    covariance2 = 2.0 * np.eye(5)

    covariance3 = 3.0 * np.eye(5)

    ensemble = EnsembleCovariance()

    # ========================================================
    # EMPTY ENSEMBLE
    # ========================================================

    try:

        ensemble.estimate()

        raise AssertionError(
            "Expected RuntimeError"
        )

    except RuntimeError:

        pass

    # ========================================================
    # MODEL REGISTRATION
    # ========================================================

    ensemble.add_model(

        "base",

        DummyModel(
            covariance1
        ),

        weight=0.50

    )

    ensemble.add_model(

        "regime",

        DummyModel(
            covariance2
        ),

        weight=0.30

    )

    ensemble.add_model(

        "factor",

        DummyModel(
            covariance3
        ),

        weight=0.20

    )

    assert set(

        ensemble.available_models

    ) == {

        "base",

        "factor",

        "regime"

    }

    # ========================================================
    # WEIGHT NORMALIZATION
    # ========================================================

    assert np.isclose(

        sum(
            ensemble.weights.values()
        ),

        1.0

    )

    # ========================================================
    # ENSEMBLE ESTIMATION
    # ========================================================

    covariance = ensemble.estimate()

    expected = (

        ensemble.weights["base"]

        * covariance1

        +

        ensemble.weights["regime"]

        * covariance2

        +

        ensemble.weights["factor"]

        * covariance3

    )

    assert np.allclose(

        covariance,

        expected

    )

    assert covariance.shape == (

        5,

        5

    )

    assert np.allclose(

        covariance,

        covariance.T,

        atol=1e-10

    )

    assert np.isfinite(

        covariance

    ).all()

    # ========================================================
    # SUMMARY
    # ========================================================

    summary = ensemble.summary()

    assert summary["dimension"] == 5

    assert set(

        summary["models"]

    ) == {

        "base",

        "factor",

        "regime"

    }

    # ========================================================
    # METADATA
    # ========================================================

    metadata = ensemble.metadata

    assert metadata["version"] == "1.0.0"

    assert set(

        metadata["models"]

    ) == {

        "base",

        "factor",

        "regime"

    }

    # ========================================================
    # MODEL REMOVAL
    # ========================================================

    ensemble.remove_model(
        "factor"
    )

    assert set(

        ensemble.available_models

    ) == {

        "base",

        "regime"

    }

    assert np.isclose(

        sum(
            ensemble.weights.values()
        ),

        1.0

    )

    # ========================================================
    # INVALID MODEL
    # ========================================================

    class InvalidModel:

        pass

    try:

        ensemble.add_model(

            "bad",

            InvalidModel()

        )

        raise AssertionError(
            "Expected TypeError"
        )

    except TypeError:

        pass

    # ========================================================
    # DIMENSION MISMATCH
    # ========================================================

    ensemble = EnsembleCovariance()

    ensemble.add_model(

        "a",

        DummyModel(
            np.eye(4)
        )

    )

    ensemble.add_model(

        "b",

        DummyModel(
            np.eye(5)
        )

    )

    try:

        ensemble.estimate()

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    assert ensemble.health_check()

    # ========================================================
    # METADATA
    # ========================================================

    metadata = ensemble.metadata

    assert metadata["version"] == "1.0.0"

    assert metadata["model_count"] == 2

    assert "CovarianceEngine" in metadata["supported_models"]

    assert "RegimeCovariance" in metadata["supported_models"]

    assert "FactorCovariance" in metadata["supported_models"]

    # ========================================================
    # API_FREEZE
    # ========================================================

    assert EnsembleCovariance.API_VERSION == "1.0.0"

    assert tuple(
        EnsembleCovariance.PUBLIC_METHODS
    ) == (

        "add_model",

        "remove_model",

        "estimate",

        "summary"

    )
    
    # ========================================================
    # API FREEZE
    # ========================================================

    assert EnsembleCovariance.API_VERSION == "1.0.0"

    assert "add_model" in EnsembleCovariance.PUBLIC_METHODS

    assert "remove_model" in EnsembleCovariance.PUBLIC_METHODS

    assert "estimate" in EnsembleCovariance.PUBLIC_METHODS

    assert "summary" in EnsembleCovariance.PUBLIC_METHODS

    print(
        "EnsembleCovariance tests passed."
    )

    
# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    test_ensemble_covariance()