"""
===============================================================
PORTFOLIO

Institutional Portfolio Domain Object

Acts as the canonical representation of an investment
portfolio.

===============================================================
"""

from __future__ import annotations

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
