"""
======================================================================
FACTOR EXPOSURE MODEL REGRESSION TESTS
======================================================================

Dedicated regression coverage for FactorExposureModel. Test utilities
remain in testsupport.py rather than production modules.
======================================================================
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from factorexposuremodel import FactorExposureModel
from portfolio import Portfolio
from testsupport import build_test_universe


# ======================================================================
# SECTION 1
# FACTOR EXPOSURE REGRESSION
# ======================================================================

def test_factor_exposure_model() -> None:
    """Exercise the canonical FactorExposureModel contract."""

    np.random.seed(42)

    factor_returns = pd.DataFrame(
        np.random.normal(
            0,
            0.01,
            size=(500, 3),
        ),
        columns=[
            "Market",
            "Value",
            "Momentum",
        ],
    )

    asset_returns = pd.DataFrame(
        np.random.normal(
            0,
            0.02,
            size=(500, 3),
        ),
        columns=[
            "QQQ",
            "SPY",
            "TLT",
        ],
    )

    model = FactorExposureModel()

    model.fit(
        factor_returns,
        asset_returns,
    )

    assert model.health_check()

    # ==================================================================
    # LOADINGS
    # ==================================================================

    loadings = model.estimate_loadings()

    assert loadings.shape == (3, 3)
    assert np.isfinite(loadings.values).all()

    # ==================================================================
    # FACTOR COVARIANCE
    # ==================================================================

    covariance = model.factor_covariance()

    assert covariance.shape == (3, 3)
    assert np.allclose(
        covariance,
        covariance.T,
        atol=1e-10,
    )

    # ==================================================================
    # PORTFOLIO
    # ==================================================================

    portfolio = Portfolio(build_test_universe())

    portfolio.set_weights(
        {
            "QQQ": 0.35,
            "SPY": 0.40,
            "TLT": 0.25,
        }
    )

    exposure = model.portfolio_exposure(portfolio)

    assert len(exposure) == 3
    assert exposure.index.tolist() == [
        "Market",
        "Value",
        "Momentum",
    ]

    # ==================================================================
    # SPECIFIC RETURNS
    # ==================================================================

    residuals = model.specific_returns()

    assert residuals.shape == (500, 3)
    assert np.isfinite(residuals.values).all()

    # ==================================================================
    # SUMMARY
    # ==================================================================

    summary = model.summary()

    assert summary["fitted"]
    assert summary["estimated"]
    assert summary["factors"] == 3
    assert summary["assets"] == 3

    # ==================================================================
    # METADATA
    # ==================================================================

    metadata = model.metadata

    assert metadata["version"] == "1.0.0"

    # ==================================================================
    # SERIALIZATION
    # ==================================================================

    exported = model.to_dict()

    assert "metadata" in exported
    assert "factor_loadings" in exported
    assert "factor_covariance" in exported

    # ==================================================================
    # API FREEZE
    # ==================================================================

    assert FactorExposureModel.API_VERSION == "1.0.0"

    assert tuple(FactorExposureModel.PUBLIC_METHODS) == (
        "fit",
        "portfolio_exposure",
        "summary",
        "metadata",
    )

    # ==================================================================
    # HEALTH
    # ==================================================================

    assert model.health_check()
