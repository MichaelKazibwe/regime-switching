
"""
================================================================
RISK MODEL

Institutional Portfolio Risk Model

Consumes covariance estimators and produces
portfolio risk analytics.

R3A RISK-FREQUENCY CONTRACT
---------------------------
The covariance matrix retains the frequency of the return
observations from which it was estimated.

Therefore:

    portfolio_variance()
        -> variance in covariance frequency

    portfolio_volatility()
        -> volatility in covariance frequency

    annualized_portfolio_variance()
        -> annualized variance

    annualized_portfolio_volatility()
        -> annualized volatility

Annualization is explicit and never implicit.
================================================================
"""

from __future__ import annotations

import numpy as np

from basecomponent import BaseObject
from core_constants import TRADING_DAYS


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
        "metadata",
    )

    DEFAULT_PERIODS_PER_YEAR = TRADING_DAYS

    TOLERANCE = 1e-12

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

    @classmethod
    def validate_inputs(
        cls,
        covariance,
        weights,
    ):
        covariance = np.asarray(
            covariance,
            dtype=float,
        )

        weights = np.asarray(
            weights,
            dtype=float,
        ).reshape(-1)

        if covariance.ndim != 2:
            raise ValueError(
                "Covariance must be 2-dimensional."
            )

        if (
            covariance.shape[0]
            != covariance.shape[1]
        ):
            raise ValueError(
                "Covariance must be square."
            )

        if (
            covariance.shape[0]
            != len(weights)
        ):
            raise ValueError(
                "Weights and covariance "
                "dimension mismatch."
            )

        if not np.isfinite(
            covariance
        ).all():
            raise ValueError(
                "Covariance contains "
                "non-finite values."
            )

        if not np.isfinite(
            weights
        ).all():
            raise ValueError(
                "Weights contain "
                "non-finite values."
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
            covariance,
            weights,
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

        try:
            value = int(
                periods_per_year
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "periods_per_year must be "
                "a positive integer."
            ) from exc

        if value <= 0:
            raise ValueError(
                "periods_per_year must be positive."
            )

        return value

    # ========================================================
    # COVARIANCE ANNUALIZATION
    # ========================================================

    @classmethod
    def annualize_covariance(
        cls,
        covariance,
        periods_per_year=DEFAULT_PERIODS_PER_YEAR,
    ):
        """
        Convert covariance from its native observation
        frequency to annual covariance.

            Sigma_annual
                = Sigma_period * periods_per_year
        """

        periods_per_year = (
            cls._validate_periods_per_year(
                periods_per_year
            )
        )

        covariance, _ = (
            cls.validate_inputs(
                covariance,
                np.ones(
                    np.asarray(
                        covariance
                    ).shape[0]
                ),
            )
        )

        return (
            covariance
            * periods_per_year
        )

    # ========================================================
    # METADATA
    # ========================================================

    @property
    def metadata(
        self,
    ):

        metadata = super().metadata

        dimension = None

        if (
            self.last_covariance
            is not None
        ):
            dimension = (
                self.last_covariance.shape[0]
            )

        metadata.update(
            {
                "dimension": dimension,

                "has_result": (
                    self.last_covariance
                    is not None
                ),

                "analytics": (
                    "variance",
                    "volatility",
                    "marginal",
                    "component",
                    "contributions",
                    "diversification",
                ),

                "risk_frequency_contract": (
                    "portfolio risk is expressed "
                    "in the frequency of supplied covariance"
                ),

                "annualization": (
                    "explicit"
                ),

                "default_periods_per_year": (
                    self.DEFAULT_PERIODS_PER_YEAR
                ),
            }
        )

        return metadata

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self,
    ):

        if self.last_covariance is None:
            return True

        if self.last_weights is None:
            raise RuntimeError(
                "Weights missing."
            )

        if (
            self.last_covariance.shape[0]
            != len(
                self.last_weights
            )
        ):
            raise RuntimeError(
                "Dimension mismatch."
            )

        if not np.allclose(
            self.last_covariance,
            self.last_covariance.T,
            atol=1e-10,
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
        weights,
    ):

        covariance, weights = (
            self.validate_inputs(
                covariance,
                weights,
            )
        )

        variance = float(
            weights.T
            @ covariance
            @ weights
        )

        if (
            variance < 0.0
            and variance > -1e-12
        ):
            variance = 0.0

        if variance < 0.0:
            raise ValueError(
                "Portfolio variance is materially negative."
            )

        self.last_covariance = (
            covariance
        )

        self.last_weights = (
            weights
        )

        self._summary = {
            "variance": variance,
        }

        return variance

    # ========================================================
    # PORTFOLIO VOLATILITY
    # ========================================================

    def portfolio_volatility(
        self,
        covariance,
        weights,
    ):

        variance = (
            self.portfolio_variance(
                covariance,
                weights,
            )
        )

        volatility = float(
            np.sqrt(
                variance
            )
        )

        self._summary.update(
            {
                "volatility":
                    volatility,
            }
        )

        return volatility

    # ========================================================
    # ANNUALIZED VARIANCE
    # ========================================================

    def annualized_portfolio_variance(
        self,
        covariance,
        weights,
        periods_per_year=DEFAULT_PERIODS_PER_YEAR,
    ):
        """
        Calculate annualized portfolio variance.

            Var_annual
                = Var_period * periods_per_year
        """

        periods_per_year = (
            self._validate_periods_per_year(
                periods_per_year
            )
        )

        variance = (
            self.portfolio_variance(
                covariance,
                weights,
            )
        )

        annualized = float(
            variance
            * periods_per_year
        )

        self._summary.update(
            {
                "annualized_variance":
                    annualized,
                "periods_per_year":
                    periods_per_year,
            }
        )

        return annualized

    # ========================================================
    # ANNUALIZED VOLATILITY
    # ========================================================

    def annualized_portfolio_volatility(
        self,
        covariance,
        weights,
        periods_per_year=DEFAULT_PERIODS_PER_YEAR,
    ):
        """
        Calculate annualized portfolio volatility.

            sigma_annual
                = sigma_period * sqrt(periods_per_year)
        """

        annualized_variance = (
            self.annualized_portfolio_variance(
                covariance,
                weights,
                periods_per_year,
            )
        )

        volatility = float(
            np.sqrt(
                annualized_variance
            )
        )

        self._summary.update(
            {
                "annualized_volatility":
                    volatility,
            }
        )

        return volatility

    # ========================================================
    # MARGINAL RISK
    # ========================================================

    def marginal_risk(
        self,
        covariance,
        weights,
    ):

        covariance, weights = (
            self.validate_inputs(
                covariance,
                weights,
            )
        )

        sigma = (
            self.portfolio_volatility(
                covariance,
                weights,
            )
        )

        if sigma <= self.TOLERANCE:
            raise ValueError(
                "Portfolio volatility must be positive."
            )

        marginal = (
            covariance
            @ weights
        ) / sigma

        self._summary.update(
            {
                "marginal_risk":
                    marginal,
            }
        )

        return marginal

    # ========================================================
    # COMPONENT RISK
    # ========================================================

    def component_risk(
        self,
        covariance,
        weights,
    ):

        marginal = (
            self.marginal_risk(
                covariance,
                weights,
            )
        )

        component = (
            weights
            * marginal
        )

        self._summary.update(
            {
                "component_risk":
                    component,
            }
        )

        return component

    # ========================================================
    # RISK CONTRIBUTIONS
    # ========================================================

    def risk_contributions(
        self,
        covariance,
        weights,
    ):

        component = (
            self.component_risk(
                covariance,
                weights,
            )
        )

        total = float(
            component.sum()
        )

        if (
            not np.isfinite(total)
            or total <= self.TOLERANCE
        ):
            raise ValueError(
                "Total portfolio risk "
                "must be positive."
            )

        contribution = (
            component
            / total
        )

        self._summary.update(
            {
                "risk_contributions":
                    contribution,
            }
        )

        return contribution

    # ========================================================
    # DIVERSIFICATION RATIO
    # ========================================================

    def diversification_ratio(
        self,
        covariance,
        weights,
    ):

        covariance, weights = (
            self.validate_inputs(
                covariance,
                weights,
            )
        )

        asset_volatility = np.sqrt(
            np.maximum(
                np.diag(covariance),
                0.0,
            )
        )

        portfolio_volatility = (
            self.portfolio_volatility(
                covariance,
                weights,
            )
        )

        if (
            portfolio_volatility
            <= self.TOLERANCE
        ):
            raise ValueError(
                "Portfolio volatility must be positive."
            )

        ratio = (
            weights
            @ asset_volatility
        ) / portfolio_volatility

        self._summary.update(
            {
                "diversification_ratio":
                    float(ratio),
            }
        )

        return float(ratio)

    # ========================================================
    # CORRELATION MATRIX
    # ========================================================

    def correlation_matrix(
        self,
        covariance,
    ):

        covariance = np.asarray(
            covariance,
            dtype=float,
        )

        if covariance.ndim != 2:
            raise ValueError(
                "Covariance must be 2-dimensional."
            )

        if (
            covariance.shape[0]
            != covariance.shape[1]
        ):
            raise ValueError(
                "Covariance must be square."
            )

        if not np.isfinite(
            covariance
        ).all():
            raise ValueError(
                "Covariance contains "
                "non-finite values."
            )

        volatility = np.sqrt(
            np.maximum(
                np.diag(covariance),
                0.0,
            )
        )

        denominator = np.outer(
            volatility,
            volatility,
        )

        correlation = np.divide(
            covariance,
            denominator,
            out=np.zeros_like(
                covariance
            ),
            where=denominator > 0,
        )

        np.fill_diagonal(
            correlation,
            1.0,
        )

        return correlation


# ============================================================
# REGRESSION TESTS
# ============================================================

def test_risk_model():

    np.random.seed(42)

    n_assets = 10

    X = np.random.normal(
        0.0,
        0.02,
        size=(
            1000,
            n_assets,
        ),
    )

    covariance = np.cov(
        X,
        rowvar=False,
    )

    weights = (
        np.ones(
            n_assets
        )
        / n_assets
    )

    risk = RiskModel()

    # --------------------------------------------------------
    # NATIVE VARIANCE
    # --------------------------------------------------------

    variance = (
        risk.portfolio_variance(
            covariance,
            weights,
        )
    )

    assert variance > 0

    # --------------------------------------------------------
    # NATIVE VOLATILITY
    # --------------------------------------------------------

    volatility = (
        risk.portfolio_volatility(
            covariance,
            weights,
        )
    )

    assert volatility > 0

    assert np.isclose(
        volatility,
        np.sqrt(
            variance
        ),
    )

    # --------------------------------------------------------
    # ANNUALIZED VARIANCE
    # --------------------------------------------------------

    annual_variance = (
        risk.annualized_portfolio_variance(
            covariance,
            weights,
        )
    )

    assert np.isclose(
        annual_variance,
        variance
        * TRADING_DAYS,
    )

    # --------------------------------------------------------
    # ANNUALIZED VOLATILITY
    # --------------------------------------------------------

    annual_volatility = (
        risk.annualized_portfolio_volatility(
            covariance,
            weights,
        )
    )

    assert np.isclose(
        annual_volatility,
        volatility
        * np.sqrt(
            TRADING_DAYS
        ),
    )

    # --------------------------------------------------------
    # MARGINAL
    # --------------------------------------------------------

    marginal = (
        risk.marginal_risk(
            covariance,
            weights,
        )
    )

    assert marginal.shape == (
        n_assets,
    )

    assert np.isfinite(
        marginal
    ).all()

    # --------------------------------------------------------
    # COMPONENT
    # --------------------------------------------------------

    component = (
        risk.component_risk(
            covariance,
            weights,
        )
    )

    assert component.shape == (
        n_assets,
    )

    assert np.isfinite(
        component
    ).all()

    assert np.isclose(
        component.sum(),
        volatility,
        atol=1e-8,
    )

    # --------------------------------------------------------
    # CONTRIBUTIONS
    # --------------------------------------------------------

    contribution = (
        risk.risk_contributions(
            covariance,
            weights,
        )
    )

    assert np.isclose(
        contribution.sum(),
        1.0,
        atol=1e-8,
    )

    # --------------------------------------------------------
    # DIVERSIFICATION
    # --------------------------------------------------------

    diversification = (
        risk.diversification_ratio(
            covariance,
            weights,
        )
    )

    assert diversification >= 1.0

    # --------------------------------------------------------
    # CORRELATION
    # --------------------------------------------------------

    correlation = (
        risk.correlation_matrix(
            covariance
        )
    )

    assert correlation.shape == (
        n_assets,
        n_assets,
    )

    assert np.allclose(
        np.diag(
            correlation
        ),
        1.0,
    )

    # --------------------------------------------------------
    # HEALTH
    # --------------------------------------------------------

    assert risk.health_check()

    # --------------------------------------------------------
    # METADATA
    # --------------------------------------------------------

    metadata = risk.metadata

    assert (
        metadata["version"]
        == "1.0.0"
    )

    assert (
        metadata["dimension"]
        == n_assets
    )

    assert metadata[
        "has_result"
    ]

    assert (
        metadata[
            "annualization"
        ]
        == "explicit"
    )

    # --------------------------------------------------------
    # API FREEZE
    # --------------------------------------------------------

    assert (
        RiskModel.API_VERSION
        == "1.0.0"
    )

    assert tuple(
        RiskModel.PUBLIC_METHODS
    ) == (
        "portfolio_volatility",
        "portfolio_variance",
        "marginal_risk",
        "component_risk",
        "risk_contributions",
        "metadata",
    )

    print(
        "RiskModel tests passed."
    )


if __name__ == "__main__":
    test_risk_model()