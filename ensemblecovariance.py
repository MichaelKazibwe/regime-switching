"""
================================================================
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

Design principles

    1. Declared model weights are preserved.
    2. Normalization occurs across the complete registered model set.
    3. Sequential model registration must not distort weights.
    4. Covariance matrices must be valid, symmetric and finite.
    5. Model dimensions must match.
    6. Empty ensembles are invalid.

================================================================
"""

# ==================================================================
# SECTION 1
# IMPORTS
# ==================================================================

import numpy as np


# ==================================================================
# SECTION 2
# ENSEMBLE COVARIANCE
# ==================================================================


class EnsembleCovariance:
    """
    Production covariance ensemble.

    The ensemble maintains two representations of model weights:

        _raw_weights
            Declared production weights.

        weights
            Normalized weights used for estimation.

    This distinction is important because normalizing after every
    model registration would distort explicitly declared weights.

    Example
    -------

        add_model("base", base, weight=0.60)
        add_model("regime", regime, weight=0.40)

    Produces:

        base   = 0.60
        regime = 0.40
    """

    # ==============================================================
    # SECTION 2.1
    # API METADATA
    # ==============================================================

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (
        "add_model",
        "remove_model",
        "estimate",
        "summary",
    )

    SUPPORTED_MODEL_TYPES = (
        "CovarianceEngine",
        "RegimeCovariance",
        "FactorCovariance",
    )

    # ==============================================================
    # SECTION 2.2
    # CONSTRUCTOR
    # ==============================================================

    def __init__(
        self,
    ) -> None:

        self.models = {}

        # ----------------------------------------------------------
        # RAW DECLARED WEIGHTS
        # ----------------------------------------------------------

        self._raw_weights = {}

        # ----------------------------------------------------------
        # NORMALIZED PRODUCTION WEIGHTS
        # ----------------------------------------------------------

        self.weights = {}

        self.last_covariance = None

        self.last_summary = None

    # ==================================================================
    # SECTION 3
    # VALIDATION
    # ==================================================================

    # ------------------------------------------------------------------
    # 3.1 WEIGHT VALIDATION
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_weight(
        weight,
    ) -> float:
        """
        Validate one declared model weight.
        """

        try:

            weight = float(
                weight
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise TypeError(
                "Model weight must be numeric."
            ) from exc

        if not np.isfinite(
            weight
        ):

            raise ValueError(
                "Model weight must be finite."
            )

        if weight < 0:

            raise ValueError(
                "Model weight cannot be negative."
            )

        if weight == 0:

            raise ValueError(
                "Model weight must be positive."
            )

        return weight

    # ------------------------------------------------------------------
    # 3.2 WEIGHT NORMALIZATION
    # ------------------------------------------------------------------

    @classmethod
    def _normalize_weights(
        cls,
        weights,
    ):
        """
        Normalize a complete set of declared weights.

        Normalization occurs only after considering the complete
        registered model set.
        """

        if not weights:

            return {}

        validated = {
            key: cls._validate_weight(
                value
            )
            for key, value in weights.items()
        }

        total = sum(
            validated.values()
        )

        if total <= 0:

            raise ValueError(
                "Weights must sum to a positive value."
            )

        return {
            key: value / total
            for key, value in validated.items()
        }

    # ------------------------------------------------------------------
    # 3.3 COVARIANCE VALIDATION
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_covariance(
        covariance,
    ):
        """
        Validate a covariance matrix.
        """

        covariance = np.asarray(
            covariance,
            dtype=float,
        )

        if covariance.ndim != 2:

            raise ValueError(
                "Covariance must be two-dimensional."
            )

        rows, cols = (
            covariance.shape
        )

        if rows != cols:

            raise ValueError(
                "Covariance matrix must be square."
            )

        if rows == 0:

            raise ValueError(
                "Covariance matrix cannot be empty."
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
            atol=1e-10,
        ):

            raise ValueError(
                "Covariance matrix is not symmetric."
            )

        eigenvalues = np.linalg.eigvalsh(
            covariance
        )

        if eigenvalues.min() < -1e-8:

            raise ValueError(
                "Covariance matrix is not "
                "positive semi-definite."
            )

        return covariance

    # ==================================================================
    # SECTION 4
    # MODEL REGISTRATION
    # ==================================================================

    # ------------------------------------------------------------------
    # 4.1 ADD MODEL
    # ------------------------------------------------------------------

    def add_model(
        self,
        name,
        model,
        weight=1.0,
    ):
        """
        Register a covariance model.

        The supplied weight is stored exactly as declared.

        Normalized weights are recalculated across the complete
        registered model set.

        This prevents sequential registration from distorting
        production weights.
        """

        if not isinstance(
            name,
            str,
        ) or not name.strip():

            raise ValueError(
                "Model name must be a non-empty string."
            )

        if not hasattr(
            model,
            "estimate",
        ):

            raise TypeError(
                "Model must implement 'estimate()'."
            )

        weight = self._validate_weight(
            weight
        )

        self.models[
            name
        ] = model

        self._raw_weights[
            name
        ] = weight

        self.weights = (
            self._normalize_weights(
                self._raw_weights
            )
        )

    # ------------------------------------------------------------------
    # 4.2 REMOVE MODEL
    # ------------------------------------------------------------------

    def remove_model(
        self,
        name,
    ):
        """
        Remove a registered covariance model.
        """

        if name not in self.models:

            raise KeyError(
                f"{name} not registered."
            )

        del self.models[
            name
        ]

        del self._raw_weights[
            name
        ]

        self.weights = (
            self._normalize_weights(
                self._raw_weights
            )
        )

    # ==================================================================
    # SECTION 5
    # INFORMATION
    # ==================================================================

    # ------------------------------------------------------------------
    # 5.1 AVAILABLE MODELS
    # ------------------------------------------------------------------

    @property
    def available_models(
        self,
    ):

        return sorted(
            self.models.keys()
        )

    # ------------------------------------------------------------------
    # 5.2 METADATA
    # ------------------------------------------------------------------

    @property
    def metadata(
        self,
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

            "raw_weights":
                dict(
                    self._raw_weights
                ),

            "model_count":
                len(
                    self.models
                ),

            "supported_models":
                list(
                    self.SUPPORTED_MODEL_TYPES
                ),
        }

# ==================================================================
# SECTION 6
# HEALTH CHECK
# ==================================================================

    # ------------------------------------------------------------------
    # 6.1 INTERNAL CONSISTENCY CHECK
    # ------------------------------------------------------------------

    def health_check(
        self,
    ) -> bool:
        """
        Verify that the covariance ensemble is internally consistent.

        Returns
        -------
        bool
            True when the ensemble is valid and internally consistent.

        Raises
        ------
        RuntimeError
            If the ensemble has no registered models or its internal
            model/weight registries are inconsistent.
        """

        if not self.models:

            raise RuntimeError(
                "No models have been registered."
            )

        if set(
            self.models.keys()
        ) != set(
            self._raw_weights.keys()
        ):

            raise RuntimeError(
                "Model registry and raw-weight registry "
                "are inconsistent."
            )

        if set(
            self.models.keys()
        ) != set(
            self.weights.keys()
        ):

            raise RuntimeError(
                "Model registry and normalized-weight registry "
                "are inconsistent."
            )

        if not np.isclose(
            sum(
                self.weights.values()
            ),
            1.0,
        ):

            raise RuntimeError(
                "Model weights do not sum to one."
            )

        for name in self.models:

            if name not in self.weights:

                raise RuntimeError(
                    f"Missing normalized weight for model '{name}'."
                )

            if name not in self._raw_weights:

                raise RuntimeError(
                    f"Missing raw weight for model '{name}'."
                )

        return True

    # ==================================================================
    # SECTION 7
    # ESTIMATION
    # ==================================================================

    def estimate(
        self,
        model_kwargs=None,
    ):
        """
        Estimate the ensemble covariance matrix.

        Parameters
        ----------
        model_kwargs : dict

            Dictionary keyed by model name.

        Example
        -------

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

        self.health_check()

        if model_kwargs is None:

            model_kwargs = {}

        ensemble = None

        dimension = None

        for (
            name,
            model,
        ) in self.models.items():

            kwargs = model_kwargs.get(
                name,
                {},
            )

            covariance = model.estimate(
                **kwargs
            )

            covariance = (
                self._validate_covariance(
                    covariance
                )
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
                    * covariance
                )

            else:

                ensemble += (
                    weight
                    * covariance
                )

        ensemble = (
            ensemble
            + ensemble.T
        ) / 2.0

        ensemble = (
            self._validate_covariance(
                ensemble
            )
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

            "raw_weights":
                dict(
                    self._raw_weights
                ),

            "dimension":
                ensemble.shape[0],
        }

        return ensemble

    # ==================================================================
    # SECTION 8
    # SUMMARY
    # ==================================================================

    def summary(
        self,
    ):
        """
        Return information describing the most recent estimation.
        """

        if self.last_summary is None:

            raise RuntimeError(
                "No covariance has been estimated."
            )

        return dict(
            self.last_summary
        )


# ======================================================================
# SECTION 9
# REGRESSION TESTS
# ======================================================================


class DummyModel:
    """
    Simple covariance model used for regression tests.

    This test-only object is deliberately isolated from the
    production composition boundary.
    """

    def __init__(
        self,
        covariance,
    ):

        self.covariance = np.asarray(
            covariance,
            dtype=float,
        )

    def estimate(
        self,
        **kwargs,
    ):

        return self.covariance


# ----------------------------------------------------------------------
# 9.1 ENSEMBLE REGRESSION TEST
# ----------------------------------------------------------------------


def test_ensemble_covariance():

    covariance1 = np.eye(
        5
    )

    covariance2 = (
        2.0
        * np.eye(5)
    )

    covariance3 = (
        3.0
        * np.eye(5)
    )

    ensemble = (
        EnsembleCovariance()
    )

    # ==============================================================
    # EMPTY ENSEMBLE
    # ==============================================================

    try:

        ensemble.estimate()

        raise AssertionError(
            "Expected RuntimeError"
        )

    except RuntimeError:

        pass

    # ==============================================================
    # MODEL REGISTRATION
    # ==============================================================

    ensemble.add_model(
        "base",
        DummyModel(
            covariance1
        ),
        weight=0.50,
    )

    ensemble.add_model(
        "regime",
        DummyModel(
            covariance2
        ),
        weight=0.30,
    )

    ensemble.add_model(
        "factor",
        DummyModel(
            covariance3
        ),
        weight=0.20,
    )

    assert set(
        ensemble.available_models
    ) == {
        "base",
        "factor",
        "regime",
    }

    # ==============================================================
    # WEIGHT NORMALIZATION
    # ==============================================================

    assert np.isclose(
        sum(
            ensemble.weights.values()
        ),
        1.0,
    )

    assert np.isclose(
        ensemble.weights[
            "base"
        ],
        0.50,
    )

    assert np.isclose(
        ensemble.weights[
            "regime"
        ],
        0.30,
    )

    assert np.isclose(
        ensemble.weights[
            "factor"
        ],
        0.20,
    )

    # ==============================================================
    # ENSEMBLE ESTIMATION
    # ==============================================================

    covariance = (
        ensemble.estimate()
    )

    expected = (
        0.50
        * covariance1
        + 0.30
        * covariance2
        + 0.20
        * covariance3
    )

    assert np.allclose(
        covariance,
        expected,
    )

    # ==============================================================
    # HEALTH
    # ==============================================================

    assert (
        ensemble.health_check()
        is True
    )


# ======================================================================
# SECTION 10
# MODULE REGRESSION ENTRY POINT
# ======================================================================


def run_regression_tests():

    test_ensemble_covariance()

    print(
        "EnsembleCovariance tests passed."
    )


# ======================================================================
# SECTION 11
# MODULE ENTRY POINT
# ======================================================================


if __name__ == "__main__":

    print(
        "============================================================"
    )

    print(
        "ENSEMBLE COVARIANCE"
    )

    print(
        "============================================================"
    )

    ensemble = (
        EnsembleCovariance()
    )

    print()
    print(
        "METADATA:"
    )

    print(
        ensemble.metadata
    )

    print()

    run_regression_tests()
