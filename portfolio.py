"""
===============================================================
PORTFOLIO

Institutional Portfolio Domain Object

Acts as the canonical representation of an investment
portfolio.

===============================================================
"""

from __future__ import annotations

from testsupport import (
    build_test_universe,
)

import numpy as np

from basecomponent import BaseObject

from assetuniverse import AssetUniverse


# ============================================================
# PORTFOLIO
# ============================================================

class Portfolio(BaseObject):

    """
    Canonical portfolio object.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (

        "set_weights",

        "set_expected_returns",

        "set_covariance",

        "metadata"

    )

    # ========================================================
    # CONSTRUCTOR
    # ========================================================

    def __init__(
        self,
        universe: AssetUniverse
    ):

        super().__init__()

        self.universe = universe

        self._weights = {}

        self.expected_returns = None

        self.covariance = None

    # ========================================================
    # VALIDATION
    # ========================================================

    def validate(self):

        if not isinstance(
            self.universe,
            AssetUniverse
        ):

            raise TypeError(
                "Portfolio requires an AssetUniverse."
            )

        n = self.universe.size

        if (

            self.weights is not None

            and

            len(self.weights) != n

        ):

            raise ValueError(
                "Weights dimension mismatch."
            )

        if (

            self.expected_returns is not None

            and

            len(self.expected_returns) != n

        ):

            raise ValueError(
                "Expected return dimension mismatch."
            )

        if self.covariance is not None:

            if self.covariance.shape != (n, n):

                raise ValueError(
                    "Covariance dimension mismatch."
                )

        return True

    # ========================================================
    # SET WEIGHTS
    # ========================================================

    def set_weights(
        self,
        weights
    ):

        """
        Set portfolio weights.

        Accepts either

            dict
                ticker -> weight

        or

            array-like
                ordered according to universe.tickers
        """

        if isinstance(
            weights,
            dict
        ):

            unknown = set(
                weights
            ) - set(
                self.universe.tickers
            )

            if unknown:

                raise KeyError(

                    f"Unknown tickers: {sorted(unknown)}"

                )

            self._weights = {

                ticker: float(

                    weights.get(
                        ticker,
                        0.0
                    )

                )

                for ticker in self.universe.tickers

            }

        else:

            vector = np.asarray(
                weights,
                dtype=float
            )

            if len(vector) != self.universe.size:

                raise ValueError(
                    "Weights dimension mismatch."
                )

            self._weights = dict(

                zip(

                    self.universe.tickers,

                    vector

                )

            )

        self.validate()

    # ========================================================
    # WEIGHTS
    # ========================================================

    @property
    def weights(
        self
    ):

        if not self._weights:

            return None

        return np.array(

            [

                self._weights[ticker]

                for ticker in self.universe.tickers

            ],

            dtype=float

        )
    
    # ========================================================
    # SET EXPECTED RETURNS
    # ========================================================

    def set_expected_returns(
        self,
        expected_returns
    ):

        self.expected_returns = np.asarray(
            expected_returns,
            dtype=float
        )

        self.validate()

    # ========================================================
    # SET COVARIANCE
    # ========================================================

    def set_covariance(
        self,
        covariance
    ):

        self.covariance = np.asarray(
            covariance,
            dtype=float
        )

        self.validate()

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

                    self.universe.size,

                "weights":

                    self.weights is not None,

                "expected_returns":

                    self.expected_returns is not None,

                "covariance":

                    self.covariance is not None,

                "fully_invested":

                    self.fully_invested,

                "positions":

                    self.number_of_positions,

                "gross_exposure":

                    self.gross_exposure,

                "net_exposure":

                    self.net_exposure

            }

        )

        return metadata

    
    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self
    ):

        self.validate()

        if self.weights is not None:

            if not np.isfinite(
                self.weights
            ).all():

                raise RuntimeError(
                    "Weights contain non-finite values."
                )

        if self.expected_returns is not None:

            if not np.isfinite(
                self.expected_returns
            ).all():

                raise RuntimeError(
                    "Expected returns contain non-finite values."
                )

        if self.covariance is not None:

            if not np.isfinite(
                self.covariance
            ).all():

                raise RuntimeError(
                    "Covariance contains non-finite values."
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

            "weights":

                None

                if self.weights is None

                else self.weights.tolist(),

            "expected_returns":

                None

                if self.expected_returns is None

                else self.expected_returns.tolist(),

            "covariance":

                None

                if self.covariance is None

                else self.covariance.tolist(),

            "holdings":

                self.holdings

        }

    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
        self
    ):

        self._summary = {

            "assets":

                self.universe.size,

            "positions":

                self.number_of_positions,

            "fully_invested":

                self.fully_invested,

            "gross_exposure":

                self.gross_exposure,

            "net_exposure":

                self.net_exposure

        }

        return dict(
            self._summary
        )
    
    # ========================================================
    # HOLDINGS
    # ========================================================

    @property
    def holdings(
    self
    ):
      """
      Return ticker -> weight mapping.
      """

      return dict(
        self._weights
    )

    # ========================================================
    # POSITION
    # ========================================================

    def position(
        self,
        ticker
    ):

        if ticker not in self._weights:

            raise KeyError(
                f"{ticker} not found."
            )

        return self._weights[ticker]

    # ========================================================
    # NORMALIZE WEIGHTS
    # ========================================================

    def normalize_weights(
        self
    ):

        if not self._weights:

            raise RuntimeError(
                "Weights have not been assigned."
            )

        total = sum(
            self._weights.values()
        )

        if np.isclose(
            total,
            0.0
        ):

            raise ValueError(
                "Cannot normalize zero weights."
            )

        for ticker in self._weights:

            self._weights[ticker] /= total

        return self.weights

    # ========================================================
    # FULLY INVESTED
    # ========================================================

    @property
    def fully_invested(
        self
    ):

        if self.weights is None:

            return False

        return bool(

            np.isclose(

                self.weights.sum(),

                1.0,

                atol=1e-8

            )

        )

    # ========================================================
    # NUMBER OF POSITIONS
    # ========================================================

    @property
    def number_of_positions(
        self
    ):

        if self.weights is None:

            return 0

        return int(

            np.count_nonzero(

                np.abs(
                    self.weights
                ) > 1e-12

            )

        )

    # ========================================================
    # LONG ONLY
    # ========================================================

    @property
    def long_only(
        self
    ):

        if self.weights is None:

            return True

        return bool(

            np.all(

                self.weights >= 0

            )

        )

    # ========================================================
    # GROSS EXPOSURE
    # ========================================================

    @property
    def gross_exposure(
        self
    ):

        if self.weights is None:

            return 0.0

        return float(

            np.abs(

                self.weights

            ).sum()

        )

    # ========================================================
    # NET EXPOSURE
    # ========================================================

    @property
    def net_exposure(
        self
    ):

        if self.weights is None:

            return 0.0

        return float(

            self.weights.sum()

        )
    
    
# ============================================================
# REGRESSION TESTS
# ============================================================

def test_portfolio():

    import numpy as np

# ========================================================
# BUILD TEST UNIVERSE
# ========================================================

    universe = build_test_universe()

    # ========================================================
    # CREATE PORTFOLIO
    # ========================================================

    portfolio = Portfolio(

        universe

    )

    assert portfolio.health_check()

    # ========================================================
    # SET WEIGHTS
    # ========================================================

    portfolio.set_weights(

    {

        "SPY": 0.40,

        "QQQ": 0.35,

        "TLT": 0.25

    }

)

    assert portfolio.fully_invested

    assert portfolio.long_only

    assert portfolio.number_of_positions == 3

    assert np.isclose(

        portfolio.net_exposure,

        1.0

    )

    assert np.isclose(

        portfolio.gross_exposure,

        1.0

    )

    # ========================================================
    # HOLDINGS
    # ========================================================

    holdings = portfolio.holdings

    assert holdings["SPY"] == 0.40

    assert holdings["QQQ"] == 0.35

    assert holdings["TLT"] == 0.25

    # ========================================================
    # POSITION LOOKUP
    # ========================================================

    assert np.isclose(

        portfolio.position(

            "QQQ"

        ),

        0.35

    )

    # ========================================================
    # EXPECTED RETURNS
    # ========================================================

    expected = np.array(

        [

            0.08,

            0.11,

            0.04

        ]

    )

    portfolio.set_expected_returns(

        expected

    )

    assert np.allclose(

        portfolio.expected_returns,

        expected

    )

    # ========================================================
    # COVARIANCE
    # ========================================================

    covariance = np.array(

        [

            [0.040,0.012,0.004],

            [0.012,0.060,0.003],

            [0.004,0.003,0.025]

        ]

    )

    portfolio.set_covariance(

        covariance

    )

    assert portfolio.covariance.shape == (

        3,

        3

    )

    # ========================================================
    # NORMALIZATION
    # ========================================================

    portfolio.set_weights(

    {

        "SPY": 4,

        "QQQ": 3,

        "TLT": 3

    }

)

    portfolio.normalize_weights()

    assert np.isclose(

        portfolio.weights.sum(),

        1.0

    )

    # ========================================================
    # METADATA
    # ========================================================

    metadata = portfolio.metadata

    assert metadata["version"] == "1.0.0"

    assert metadata["assets"] == 3

    assert metadata["weights"]

    assert metadata["expected_returns"]

    assert metadata["covariance"]

    # ========================================================
    # SUMMARY
    # ========================================================

    summary = portfolio.summary()

    assert summary["assets"] == 3

    assert summary["positions"] == 3

    # ========================================================
    # SERIALIZATION
    # ========================================================

    exported = portfolio.to_dict()

    assert "metadata" in exported

    assert "weights" in exported

    assert "covariance" in exported

    assert "expected_returns" in exported

    assert "holdings" in exported

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    assert portfolio.health_check()
    
    # ========================================================
    # API FREEZE
    # ========================================================

    assert Portfolio.API_VERSION == "1.0.0"

    assert tuple(

        Portfolio.PUBLIC_METHODS

    ) == (

        "set_weights",

        "set_expected_returns",

        "set_covariance",

        "metadata"

    )
    
    # ========================================================
    # INVALID WEIGHTS
    # ========================================================

    try:

        portfolio.set_weights(

            [1,2]

        )

        raise AssertionError(

            "Expected ValueError"

        )

    except ValueError:

        pass

    # ========================================================
    # INVALID COVARIANCE
    # ========================================================

    try:

        portfolio.set_covariance(

            np.eye(

                5

            )

        )

        raise AssertionError(

            "Expected ValueError"

        )

    except ValueError:

        pass

    # ========================================================
    # INVALID LOOKUP
    # ========================================================

    try:

        portfolio.position(

            "GLD"

        )

        raise AssertionError(

            "Expected KeyError"

        )

    except KeyError:

        pass

    print(

        "Portfolio tests passed."

    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    test_portfolio()