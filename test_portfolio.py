"""
======================================================================
PORTFOLIO REGRESSION TESTS
======================================================================

Dedicated regression coverage for the production Portfolio domain
object. Test infrastructure is intentionally kept outside portfolio.py.
======================================================================
"""

from __future__ import annotations

import numpy as np

from portfolio import Portfolio
from testsupport import build_test_universe


# ======================================================================
# SECTION 1
# CORE PORTFOLIO REGRESSION
# ======================================================================

def test_portfolio() -> None:
    """Exercise the canonical Portfolio production contract."""

    universe = build_test_universe()
    portfolio = Portfolio(universe)

    assert portfolio.health_check()

    # ==================================================================
    # WEIGHTS
    # ==================================================================

    portfolio.set_weights(
        {
            "SPY": 0.40,
            "QQQ": 0.35,
            "TLT": 0.25,
        }
    )

    assert portfolio.fully_invested
    assert portfolio.long_only
    assert portfolio.number_of_positions == 3
    assert np.isclose(portfolio.net_exposure, 1.0)
    assert np.isclose(portfolio.gross_exposure, 1.0)

    holdings = portfolio.holdings

    assert holdings["SPY"] == 0.40
    assert holdings["QQQ"] == 0.35
    assert holdings["TLT"] == 0.25

    assert np.isclose(portfolio.position("QQQ"), 0.35)

    # ==================================================================
    # EXPECTED RETURNS
    # ==================================================================

    expected = np.array([0.08, 0.11, 0.04])

    portfolio.set_expected_returns(expected)

    assert np.allclose(portfolio.expected_returns, expected)

    # ==================================================================
    # COVARIANCE
    # ==================================================================

    covariance = np.array(
        [
            [0.040, 0.012, 0.004],
            [0.012, 0.060, 0.003],
            [0.004, 0.003, 0.025],
        ]
    )

    portfolio.set_covariance(covariance)

    assert portfolio.covariance.shape == (3, 3)

    # ==================================================================
    # NORMALIZATION
    # ==================================================================

    portfolio.set_weights(
        {
            "SPY": 4,
            "QQQ": 3,
            "TLT": 3,
        }
    )

    portfolio.normalize_weights()

    assert np.isclose(portfolio.weights.sum(), 1.0)

    # ==================================================================
    # METADATA
    # ==================================================================

    metadata = portfolio.metadata

    assert metadata["version"] == "1.0.0"
    assert metadata["assets"] == 3
    assert metadata["weights"]
    assert metadata["expected_returns"]
    assert metadata["covariance"]

    # ==================================================================
    # SUMMARY
    # ==================================================================

    summary = portfolio.summary()

    assert summary["assets"] == 3
    assert summary["positions"] == 3

    # ==================================================================
    # SERIALIZATION
    # ==================================================================

    exported = portfolio.to_dict()

    assert "metadata" in exported
    assert "weights" in exported
    assert "covariance" in exported
    assert "expected_returns" in exported
    assert "holdings" in exported

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    assert portfolio.health_check()

    # ==================================================================
    # API FREEZE
    # ==================================================================

    assert Portfolio.API_VERSION == "1.0.0"

    assert tuple(Portfolio.PUBLIC_METHODS) == (
        "set_weights",
        "set_expected_returns",
        "set_covariance",
        "metadata",
    )

    # ==================================================================
    # INVALID WEIGHTS
    # ==================================================================

    try:
        portfolio.set_weights([1, 2])
        raise AssertionError("Expected ValueError")
    except ValueError:
        pass

    # ==================================================================
    # INVALID COVARIANCE
    # ==================================================================

    try:
        portfolio.set_covariance(np.eye(5))
        raise AssertionError("Expected ValueError")
    except ValueError:
        pass

    # ==================================================================
    # INVALID LOOKUP
    # ==================================================================

    try:
        portfolio.position("GLD")
        raise AssertionError("Expected KeyError")
    except KeyError:
        pass
