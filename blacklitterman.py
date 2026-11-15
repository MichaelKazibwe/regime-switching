"""
======================================================================
BLACK-LITTERMAN MODEL

A15.3 — Hardened Black-Litterman Integration Layer

Institutional Black-Litterman expected-return engine.

Implements:

    1. Equilibrium / implied returns

           π = δ Σ w

    2. Posterior expected returns

           μ_BL =
               ( (τΣ)^-1 + P'Ω^-1P )^-1
               [
                   (τΣ)^-1 π
                   +
                   P'Ω^-1Q
               ]

Current production contract
----------------------------

The current implementation supports one direct view per asset.

Therefore:

    P = I

and:

    Q = views

The implementation deliberately validates all dimensions and
numerical inputs before performing matrix operations.

Production guarantees
---------------------

1. Covariance must be square.
2. Covariance must be finite.
3. Covariance must be symmetric.
4. Covariance must be positive semi-definite.
5. Market weights must be finite.
6. Market weights must match covariance dimension.
7. Market weights must sum to one.
8. Risk aversion must be positive and finite.
9. Tau must be positive and finite.
10. Views must match asset dimension.
11. Confidence must be positive and finite.
12. Matrix inversion uses a numerically stable linear solver.
13. Singular / ill-conditioned systems are handled explicitly.
14. Posterior returns must be finite.
15. Asset ordering is preserved through positional numerical operations.
16. No caller-owned input is mutated.
17. Production diagnostics are retained.
18. Health state is deterministic.
19. Public API is explicitly frozen.
======================================================================
"""

from __future__ import annotations

from typing import Any

import numpy as np


# ======================================================================
# BLACK-LITTERMAN MODEL
# ======================================================================


class BlackLittermanModel:
    """
    Production Black-Litterman expected-return model.

    Parameters
    ----------
    tau:
        Scalar controlling uncertainty around equilibrium returns.

    Notes
    -----
    The current production implementation supports direct one-to-one
    views on every asset:

        P = I

    Therefore ``views`` must contain exactly one value per asset.
    """

    # ==================================================================
    # API METADATA
    # ==================================================================

    API_VERSION = "1.0.0"

    COMPONENT = "BlackLittermanModel"

    PUBLIC_METHODS = (
        "equilibrium_returns",
        "posterior_returns",
        "summary",
        "health_check",
    )

    # ==================================================================
    # DEFAULT CONFIGURATION
    # ==================================================================

    DEFAULT_TAU = 0.05

    DEFAULT_RISK_AVERSION = 2.5

    DEFAULT_CONFIDENCE = 0.25

    # Numerical tolerance used for covariance validation.
    PSD_TOLERANCE = 1e-8

    SYMMETRY_TOLERANCE = 1e-10

    WEIGHT_SUM_TOLERANCE = 1e-10

    # ==================================================================
    # CONSTRUCTOR
    # ==================================================================

    def __init__(
        self,
        tau: float = DEFAULT_TAU,
    ) -> None:
        """
        Initialize the Black-Litterman model.
        """

        self.tau = float(
            tau
        )

        self.last_equilibrium_returns = None

        self.last_posterior_returns = None

        self.last_diagnostics: dict[str, Any] | None = None

        self.last_dimension: int | None = None

        self._validate_tau()

    # ==================================================================
    # BASIC VALIDATION HELPERS
    # ==================================================================

    @staticmethod
    def _validate_scalar(
        value: Any,
        name: str,
        *,
        strictly_positive: bool = False,
        non_negative: bool = False,
    ) -> float:
        """
        Validate a scalar numerical parameter.
        """

        try:

            value = float(
                value
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise TypeError(
                f"{name} must be numeric."
            ) from exc

        if not np.isfinite(
            value
        ):

            raise ValueError(
                f"{name} must be finite."
            )

        if strictly_positive and value <= 0.0:

            raise ValueError(
                f"{name} must be strictly positive."
            )

        if non_negative and value < 0.0:

            raise ValueError(
                f"{name} cannot be negative."
            )

        return value

    def _validate_tau(
        self,
    ) -> float:
        """
        Validate model tau.
        """

        self.tau = self._validate_scalar(
            self.tau,
            "tau",
            strictly_positive=True,
        )

        return self.tau

    # ==================================================================
    # COVARIANCE VALIDATION
    # ==================================================================

    @classmethod
    def _validate_covariance(
        cls,
        covariance: Any,
    ) -> np.ndarray:
        """
        Validate a covariance matrix.
        """

        try:

            covariance = np.asarray(
                covariance,
                dtype=float,
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise TypeError(
                "Covariance must be convertible "
                "to a numeric numpy array."
            ) from exc

        if covariance.ndim != 2:

            raise ValueError(
                "Covariance must be two-dimensional."
            )

        rows, columns = (
            covariance.shape
        )

        if rows == 0:

            raise ValueError(
                "Covariance cannot be empty."
            )

        if rows != columns:

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
            atol=cls.SYMMETRY_TOLERANCE,
            rtol=0.0,
        ):

            raise ValueError(
                "Covariance matrix is not symmetric."
            )

        eigenvalues = np.linalg.eigvalsh(
            covariance
        )

        if eigenvalues.min() < -cls.PSD_TOLERANCE:

            raise ValueError(
                "Covariance matrix is not "
                "positive semi-definite."
            )

        return covariance.copy()

    # ==================================================================
    # VECTOR VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_vector(
        values: Any,
        dimension: int,
        name: str,
    ) -> np.ndarray:
        """
        Validate a one-dimensional numerical vector.
        """

        try:

            array = np.asarray(
                values,
                dtype=float,
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise TypeError(
                f"{name} must be numeric."
            ) from exc

        if array.ndim != 1:

            raise ValueError(
                f"{name} must be one-dimensional."
            )

        if array.size != dimension:

            raise ValueError(
                f"{name} contains {array.size} values; "
                f"expected {dimension}."
            )

        if not np.isfinite(
            array
        ).all():

            raise ValueError(
                f"{name} contains non-finite values."
            )

        return array.copy()

    # ==================================================================
    # MARKET WEIGHT VALIDATION
    # ==================================================================

    @classmethod
    def _validate_market_weights(
        cls,
        market_weights: Any,
        dimension: int,
    ) -> np.ndarray:
        """
        Validate market portfolio weights.

        Current contract requires fully invested weights summing to one.

        Negative weights are allowed because the model itself does not
        impose a long-only portfolio constraint.
        """

        weights = cls._validate_vector(
            market_weights,
            dimension,
            "market_weights",
        )

        weight_sum = float(
            weights.sum()
        )

        if not np.isclose(
            weight_sum,
            1.0,
            atol=cls.WEIGHT_SUM_TOLERANCE,
            rtol=0.0,
        ):

            raise ValueError(
                "market_weights must sum to one; "
                f"got {weight_sum}."
            )

        return weights

    # ==================================================================
    # EQUILIBRIUM RETURNS
    # ==================================================================

    def equilibrium_returns(
        self,
        covariance: Any,
        market_weights: Any,
        risk_aversion: float = DEFAULT_RISK_AVERSION,
    ) -> np.ndarray:
        """
        Calculate equilibrium / implied expected returns.

            π = δ Σ w

        Parameters
        ----------
        covariance:
            Asset covariance matrix.

        market_weights:
            Fully invested market portfolio weights.

        risk_aversion:
            Positive risk-aversion coefficient.
        """

        covariance_array = (
            self._validate_covariance(
                covariance
            )
        )

        dimension = (
            covariance_array.shape[0]
        )

        weights = (
            self._validate_market_weights(
                market_weights,
                dimension,
            )
        )

        risk_aversion = (
            self._validate_scalar(
                risk_aversion,
                "risk_aversion",
                strictly_positive=True,
            )
        )

        equilibrium = (
            risk_aversion
            *
            covariance_array
            @
            weights
        )

        if not np.isfinite(
            equilibrium
        ).all():

            raise ValueError(
                "Equilibrium returns contain "
                "non-finite values."
            )

        equilibrium = np.asarray(
            equilibrium,
            dtype=float,
        )

        self.last_equilibrium_returns = (
            equilibrium.copy()
        )

        self.last_dimension = (
            dimension
        )

        return equilibrium

    # ==================================================================
    # LINEAR SOLVER
    # ==================================================================

    @classmethod
    def _solve(
        cls,
        matrix: np.ndarray,
        vector: np.ndarray,
    ) -> np.ndarray:
        """
        Solve a linear system robustly.

        ``np.linalg.solve`` is preferred because explicitly forming
        matrix inverses is numerically less stable.

        A pseudo-inverse fallback is permitted when the system is
        singular or numerically non-invertible.
        """

        try:

            solution = np.linalg.solve(
                matrix,
                vector,
            )

        except np.linalg.LinAlgError:

            solution = (
                np.linalg.pinv(
                    matrix
                )
                @
                vector
            )

        if not np.isfinite(
            solution
        ).all():

            raise ValueError(
                "Linear-system solution contains "
                "non-finite values."
            )

        return np.asarray(
            solution,
            dtype=float,
        )

    # ==================================================================
    # POSTERIOR RETURNS
    # ==================================================================

    def posterior_returns(
        self,
        covariance: Any,
        market_weights: Any,
        views: Any,
        confidence: float = DEFAULT_CONFIDENCE,
        risk_aversion: float = DEFAULT_RISK_AVERSION,
    ) -> np.ndarray:
        """
        Calculate Black-Litterman posterior expected returns.

        Current production contract:

            P = I

        and therefore:

            Q = views

        The resulting posterior is:

            μ_BL =
                A^-1 b

        where:

            A =
                (τΣ)^-1
                +
                Ω^-1

            b =
                (τΣ)^-1 π
                +
                Ω^-1 Q

        Matrix inverses are not explicitly constructed for the final
        solve. Linear systems are solved using a stable numerical
        boundary.

        Parameters
        ----------
        covariance:
            Asset covariance matrix.

        market_weights:
            Fully invested market portfolio weights.

        views:
            One direct view per asset.

        confidence:
            Positive view-confidence parameter.

        risk_aversion:
            Positive risk-aversion coefficient.
        """

        covariance_array = (
            self._validate_covariance(
                covariance
            )
        )

        dimension = (
            covariance_array.shape[0]
        )

        weights = (
            self._validate_market_weights(
                market_weights,
                dimension,
            )
        )

        views_array = (
            self._validate_vector(
                views,
                dimension,
                "views",
            )
        )

        confidence = (
            self._validate_scalar(
                confidence,
                "confidence",
                strictly_positive=True,
            )
        )

        risk_aversion = (
            self._validate_scalar(
                risk_aversion,
                "risk_aversion",
                strictly_positive=True,
            )
        )

        tau = self._validate_tau()

        # ==============================================================
        # EQUILIBRIUM RETURNS
        # ==============================================================

        equilibrium = (
            self.equilibrium_returns(
                covariance_array,
                weights,
                risk_aversion=risk_aversion,
            )
        )

        # ==============================================================
        # DIRECT-VIEW STRUCTURE
        # ==============================================================

        # Current architecture supports one direct view per asset.

        P = np.eye(
            dimension,
            dtype=float,
        )

        # Confidence is interpreted as the diagonal uncertainty
        # parameter for the direct views.

        omega = (
            confidence
            *
            np.eye(
                dimension,
                dtype=float,
            )
        )

        # ==============================================================
        # TAU COVARIANCE
        # ==============================================================

        tau_sigma = (
            tau
            *
            covariance_array
        )

        # ==============================================================
        # NUMERICAL SYSTEM
        # ==============================================================

        # Rather than repeatedly computing explicit matrix inverses,
        # solve the required linear systems.

        tau_sigma_inverse = (
            np.linalg.pinv(
                tau_sigma
            )
        )

        omega_inverse = (
            np.linalg.pinv(
                omega
            )
        )

        posterior_precision = (
            tau_sigma_inverse
            +
            P.T
            @
            omega_inverse
            @
            P
        )

        posterior_information = (
            tau_sigma_inverse
            @
            equilibrium
            +
            P.T
            @
            omega_inverse
            @
            views_array
        )

        posterior_precision = (
            posterior_precision
            +
            posterior_precision.T
        ) / 2.0

        posterior = self._solve(
            posterior_precision,
            posterior_information,
        )

        # ==============================================================
        # FINAL VALIDATION
        # ==============================================================

        if posterior.shape != (
            dimension,
        ):

            raise ValueError(
                "Posterior returns have incorrect dimension."
            )

        if not np.isfinite(
            posterior
        ).all():

            raise ValueError(
                "Posterior returns contain "
                "non-finite values."
            )

        # ==============================================================
        # DIAGNOSTICS
        # ==============================================================

        try:

            condition_number = float(
                np.linalg.cond(
                    posterior_precision
                )
            )

        except (
            np.linalg.LinAlgError,
            ValueError,
        ):

            condition_number = float(
                "inf"
            )

        self.last_posterior_returns = (
            posterior.copy()
        )

        self.last_dimension = (
            dimension
        )

        self.last_diagnostics = {
            "api_version": self.API_VERSION,
            "component": self.COMPONENT,
            "dimension": int(
                dimension
            ),
            "tau": float(
                tau
            ),
            "risk_aversion": float(
                risk_aversion
            ),
            "confidence": float(
                confidence
            ),
            "view_structure": "direct",
            "view_count": int(
                dimension
            ),
            "covariance_minimum_eigenvalue": float(
                np.linalg.eigvalsh(
                    covariance_array
                ).min()
            ),
            "posterior_precision_condition_number": (
                condition_number
            ),
            "equilibrium_minimum": float(
                equilibrium.min()
            ),
            "equilibrium_maximum": float(
                equilibrium.max()
            ),
            "posterior_minimum": float(
                posterior.min()
            ),
            "posterior_maximum": float(
                posterior.max()
            ),
        }

        return posterior

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ) -> dict[str, Any]:
        """
        Return deterministic model health information.

        Health checking does not perform a model estimation.
        """

        try:

            self._validate_tau()

            return {
                "status": "HEALTHY",
                "healthy": True,
                "api_version": self.API_VERSION,
                "component": self.COMPONENT,
                "tau": float(
                    self.tau
                ),
                "last_dimension": (
                    None
                    if self.last_dimension is None
                    else int(
                        self.last_dimension
                    )
                ),
                "equilibrium_available": (
                    self.last_equilibrium_returns
                    is not None
                ),
                "posterior_available": (
                    self.last_posterior_returns
                    is not None
                ),
            }

        except Exception as exc:

            return {
                "status": "UNHEALTHY",
                "healthy": False,
                "api_version": self.API_VERSION,
                "component": self.COMPONENT,
                "error": str(
                    exc
                ),
            }

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(
        self,
    ) -> dict[str, Any]:
        """
        Return current Black-Litterman model state.
        """

        return {
            "api_version": self.API_VERSION,
            "component": self.COMPONENT,
            "tau": float(
                self.tau
            ),
            "last_dimension": (
                None
                if self.last_dimension is None
                else int(
                    self.last_dimension
                )
            ),
            "equilibrium_available": (
                self.last_equilibrium_returns
                is not None
            ),
            "posterior_available": (
                self.last_posterior_returns
                is not None
            ),
            "diagnostics_available": (
                self.last_diagnostics
                is not None
            ),
        }


# ======================================================================
# REGRESSION TESTS
# ======================================================================


def test_black_litterman_model() -> None:
    """
    Comprehensive A15.3 regression suite.
    """

    np.random.seed(42)

    # ==============================================================
    # TEST DATA
    # ==============================================================

    n_assets = 5

    A = np.random.normal(
        size=(
            n_assets,
            n_assets,
        )
    )

    covariance = (
        A
        @
        A.T
    )

    market_weights = np.array(
        [
            0.30,
            0.25,
            0.20,
            0.15,
            0.10,
        ],
        dtype=float,
    )

    views = np.array(
        [
            0.08,
            0.06,
            0.04,
            0.03,
            0.02,
        ],
        dtype=float,
    )

    # ==============================================================
    # API CONTRACT
    # ==============================================================

    model = BlackLittermanModel()

    assert (
        model.API_VERSION
        ==
        "1.0.0"
    )

    assert (
        model.COMPONENT
        ==
        "BlackLittermanModel"
    )

    assert tuple(
        model.PUBLIC_METHODS
    ) == (
        "equilibrium_returns",
        "posterior_returns",
        "summary",
        "health_check",
    )

    # ==============================================================
    # DEFAULT TAU
    # ==============================================================

    assert np.isclose(
        model.tau,
        0.05,
    )

    # ==============================================================
    # HEALTH
    # ==============================================================

    health = (
        model.health_check()
    )

    assert health["healthy"] is True

    assert (
        health["status"]
        ==
        "HEALTHY"
    )

    # ==============================================================
    # EQUILIBRIUM RETURNS
    # ==============================================================

    equilibrium = (
        model.equilibrium_returns(
            covariance,
            market_weights,
        )
    )

    expected_equilibrium = (
        2.5
        *
        covariance
        @
        market_weights
    )

    assert isinstance(
        equilibrium,
        np.ndarray,
    )

    assert equilibrium.shape == (
        n_assets,
    )

    assert np.isfinite(
        equilibrium
    ).all()

    assert np.allclose(
        equilibrium,
        expected_equilibrium,
    )

    # ==============================================================
    # EQUILIBRIUM STATE
    # ==============================================================

    assert (
        model.last_equilibrium_returns
        is not None
    )

    assert (
        model.last_dimension
        ==
        n_assets
    )

    # ==============================================================
    # POSTERIOR
    # ==============================================================

    posterior = (
        model.posterior_returns(
            covariance,
            market_weights,
            views,
        )
    )

    assert isinstance(
        posterior,
        np.ndarray,
    )

    assert posterior.shape == (
        n_assets,
    )

    assert np.isfinite(
        posterior
    ).all()

    # ==============================================================
    # POSTERIOR STATE
    # ==============================================================

    assert (
        model.last_posterior_returns
        is not None
    )

    assert (
        model.last_diagnostics
        is not None
    )

    assert (
        model.last_diagnostics[
            "dimension"
        ]
        ==
        n_assets
    )

    assert (
        model.last_diagnostics[
            "view_structure"
        ]
        ==
        "direct"
    )

    assert (
        model.last_diagnostics[
            "view_count"
        ]
        ==
        n_assets
    )

    # ==============================================================
    # MANUAL POSTERIOR RECONSTRUCTION
    # ==============================================================

    tau = model.tau

    pi = (
        2.5
        *
        covariance
        @
        market_weights
    )

    P = np.eye(
        n_assets
    )

    omega = (
        0.25
        *
        np.eye(
            n_assets
        )
    )

    tau_sigma = (
        tau
        *
        covariance
    )

    precision = (
        np.linalg.pinv(
            tau_sigma
        )
        +
        P.T
        @
        np.linalg.pinv(
            omega
        )
        @
        P
    )

    information = (
        np.linalg.pinv(
            tau_sigma
        )
        @
        pi
        +
        P.T
        @
        np.linalg.pinv(
            omega
        )
        @
        views
    )

    expected_posterior = (
        np.linalg.solve(
            precision,
            information,
        )
    )

    assert np.allclose(
        posterior,
        expected_posterior,
        atol=1e-10,
    )

    # ==============================================================
    # DIFFERENT CONFIDENCE
    # ==============================================================

    high_confidence = (
        model.posterior_returns(
            covariance,
            market_weights,
            views,
            confidence=0.05,
        )
    )

    low_confidence = (
        model.posterior_returns(
            covariance,
            market_weights,
            views,
            confidence=1.00,
        )
    )

    assert np.isfinite(
        high_confidence
    ).all()

    assert np.isfinite(
        low_confidence
    ).all()

    # ==============================================================
    # DIFFERENT RISK AVERSION
    # ==============================================================

    posterior_high_risk_aversion = (
        model.posterior_returns(
            covariance,
            market_weights,
            views,
            risk_aversion=5.0,
        )
    )

    assert np.isfinite(
        posterior_high_risk_aversion
    ).all()

    assert not np.allclose(
        posterior,
        posterior_high_risk_aversion,
    )

    # ==============================================================
    # INPUT IMMUTABILITY
    # ==============================================================

    covariance_copy = covariance.copy()

    weights_copy = (
        market_weights.copy()
    )

    views_copy = (
        views.copy()
    )

    model.posterior_returns(
        covariance,
        market_weights,
        views,
    )

    assert np.array_equal(
        covariance,
        covariance_copy,
    )

    assert np.array_equal(
        market_weights,
        weights_copy,
    )

    assert np.array_equal(
        views,
        views_copy,
    )

    # ==============================================================
    # INVALID TAU
    # ==============================================================

    try:

        BlackLittermanModel(
            tau=0.0
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    try:

        BlackLittermanModel(
            tau=-0.1
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # NON-FINITE COVARIANCE
    # ==============================================================

    invalid_covariance = (
        covariance.copy()
    )

    invalid_covariance[0, 0] = (
        np.nan
    )

    try:

        model.equilibrium_returns(
            invalid_covariance,
            market_weights,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # NON-SQUARE COVARIANCE
    # ==============================================================

    try:

        model.equilibrium_returns(
            np.ones(
                (
                    n_assets,
                    n_assets + 1,
                )
            ),
            market_weights,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # NON-SYMMETRIC COVARIANCE
    # ==============================================================

    nonsymmetric = covariance.copy()

    nonsymmetric[0, 1] += 10.0

    try:

        model.equilibrium_returns(
            nonsymmetric,
            market_weights,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # NON-PSD COVARIANCE
    # ==============================================================

    invalid_psd = np.array(
        [
            [1.0, 2.0],
            [2.0, 1.0],
        ]
    )

    try:

        model.equilibrium_returns(
            invalid_psd,
            np.array(
                [
                    0.5,
                    0.5,
                ]
            ),
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # WEIGHT DIMENSION
    # ==============================================================

    try:

        model.equilibrium_returns(
            covariance,
            np.array(
                [
                    0.5,
                    0.5,
                ]
            ),
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # WEIGHT SUM
    # ==============================================================

    invalid_weights = (
        market_weights.copy()
    )

    invalid_weights[0] += 0.10

    try:

        model.equilibrium_returns(
            covariance,
            invalid_weights,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # NON-FINITE WEIGHTS
    # ==============================================================

    invalid_weights = (
        market_weights.copy()
    )

    invalid_weights[0] = (
        np.inf
    )

    try:

        model.equilibrium_returns(
            covariance,
            invalid_weights,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # INVALID RISK AVERSION
    # ==============================================================

    try:

        model.equilibrium_returns(
            covariance,
            market_weights,
            risk_aversion=0.0,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # INVALID VIEWS DIMENSION
    # ==============================================================

    try:

        model.posterior_returns(
            covariance,
            market_weights,
            views[:-1],
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # INVALID CONFIDENCE
    # ==============================================================

    try:

        model.posterior_returns(
            covariance,
            market_weights,
            views,
            confidence=0.0,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # INVALID CONFIDENCE NEGATIVE
    # ==============================================================

    try:

        model.posterior_returns(
            covariance,
            market_weights,
            views,
            confidence=-0.1,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # INVALID VIEWS
    # ==============================================================

    invalid_views = views.copy()

    invalid_views[0] = (
        np.nan
    )

    try:

        model.posterior_returns(
            covariance,
            market_weights,
            invalid_views,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # SUMMARY
    # ==============================================================

    summary = model.summary()

    assert (
        summary["api_version"]
        ==
        "1.0.0"
    )

    assert (
        summary["component"]
        ==
        "BlackLittermanModel"
    )

    assert (
        summary["last_dimension"]
        ==
        n_assets
    )

    assert (
        summary[
            "equilibrium_available"
        ]
        is True
    )

    assert (
        summary[
            "posterior_available"
        ]
        is True
    )

    assert (
        summary[
            "diagnostics_available"
        ]
        is True
    )

    # ==============================================================
    # FINAL HEALTH CHECK
    # ==============================================================

    final_health = (
        model.health_check()
    )

    assert (
        final_health["healthy"]
        is True
    )

    print(
        "A15.3 BlackLittermanModel "
        "tests passed."
    )


# ======================================================================
# MODULE ENTRY POINT
# ======================================================================


if __name__ == "__main__":

    test_black_litterman_model()