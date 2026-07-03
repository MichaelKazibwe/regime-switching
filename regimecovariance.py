import numpy as np

import pandas as pd

from covarianceengine import CovarianceEngine

"""
===============================================================
REGIME COVARIANCE

Institutional regime-aware covariance estimator.

Given historical returns and regime labels, estimates a
covariance matrix using only observations belonging to the
requested regime.

Public API

    fit()

    estimate()

    summary()

    available_regimes

===============================================================
"""

# ============================================================
# REGIME COVARIANCE
# ============================================================

class RegimeCovariance:

    """
    Regime-specific covariance estimator.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (

        "fit",

        "estimate",

        "summary"

    )

    # ========================================================
    # CONSTRUCTOR
    # ========================================================

    def __init__(self):

        self.engine = CovarianceEngine()

        self.returns = None

        self.regimes = None

        self.last_covariance = None

        self.last_regime = None

        self.last_observations = None

        self.last_summary = None

    # ========================================================
    # INTERNAL HELPERS
    # ========================================================

    @staticmethod
    def _ensure_dataframe(
        returns
    ):

        if not isinstance(
            returns,
            pd.DataFrame
        ):

            raise TypeError(
                "Returns must be a pandas DataFrame."
            )

        return returns

    @staticmethod
    def _ensure_series(
        regimes
    ):

        if isinstance(
            regimes,
            list
        ):

            regimes = pd.Series(
                regimes
            )

        if not isinstance(
            regimes,
            pd.Series
        ):

            raise TypeError(
                "Regimes must be a pandas Series."
            )

        return regimes

    def _validate_lengths(
        self,
        returns,
        regimes
    ):

        if len(
            returns
        ) != len(
            regimes
        ):

            raise ValueError(

                "Returns and regimes "

                "must have identical length."

            )

    def _select_regime(
        self,
        regime
    ):

        mask = (
            self.regimes
            ==
            regime
        )

        subset = self.returns.loc[
            mask
        ]

        if subset.empty:

            raise ValueError(

                f"No observations found "

                f"for regime '{regime}'."

            )

        return subset

    # ========================================================
    # FIT
    # ========================================================

    def fit(
        self,
        returns,
        regimes
    ):

        returns = self._ensure_dataframe(
            returns
        )

        regimes = self._ensure_series(
            regimes
        )

        self._validate_lengths(

            returns,

            regimes

        )

        self.returns = (
            returns.copy()
        )

        self.regimes = (
            regimes.copy()
        )

        return self

    # ========================================================
    # AVAILABLE REGIMES
    # ========================================================

    @property
    def available_regimes(
        self
    ):

        if self.regimes is None:

            return []

        return sorted(

            self.regimes
            .unique()
            .tolist()

        )
    
    # ========================================================
    # ESTIMATE
    # ========================================================

    def estimate(
        self,
        regime,
        method="ledoit_wolf",
        **kwargs
    ):

        """
        Estimate a covariance matrix using only
        observations belonging to the requested regime.

        Parameters
        ----------
        regime : str
            Regime label.

        method : str
            Covariance estimation method.

        kwargs
            Additional arguments passed directly
            to CovarianceEngine.
        """

        if self.returns is None:

            raise RuntimeError(
                "fit() must be called before estimate()."
            )

        subset = self._select_regime(
            regime
        )

        covariance = self.engine.estimate(

            subset,

            method=method,

            **kwargs

        )

        self.last_covariance = covariance

        self.last_regime = regime

        self.last_observations = len(
            subset
        )

        self.last_summary = {

            "regime": regime,

            "method": method,

            "observations": len(
                subset
            ),

            "dimension": covariance.shape[0]

        }

        return covariance

    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
        self
    ):

        """
        Return information describing the most
        recent estimation.
        """

        if self.last_summary is None:

            raise RuntimeError(
                "No covariance has been estimated."
            )

        return dict(
            self.last_summary
        )

    # ========================================================
    # METADATA
    # ========================================================

    @property
    def metadata(
        self
    ):

        return {

            "version":
                self.API_VERSION,

            "available_regimes":
                self.available_regimes,

            "last_regime":
                self.last_regime,

            "last_observations":
                self.last_observations

        }
    
# ============================================================
# REGRESSION TESTS
# ============================================================

def test_regime_covariance():

    np.random.seed(42)

    returns = pd.DataFrame(

        np.random.normal(

            0.001,

            0.02,

            size=(900, 10)

        ),

        columns=[

            f"Asset_{i}"

            for i in range(10)

        ]

    )

    regimes = pd.Series(

        (

            ["Expansion"] * 300 +

            ["Recession"] * 300 +

            ["Recovery"] * 300

        )

    )

    engine = RegimeCovariance()

    # ========================================================
    # FIT
    # ========================================================

    engine.fit(

        returns,

        regimes

    )

    assert len(
        engine.available_regimes
    ) == 3

    assert set(
        engine.available_regimes
    ) == {

        "Expansion",

        "Recession",

        "Recovery"

    }

    # ========================================================
    # LEDOIT-WOLF
    # ========================================================

    covariance = engine.estimate(

        "Expansion"

    )

    assert covariance.shape == (
        10,
        10
    )

    assert np.isfinite(
        covariance
    ).all()

    assert np.allclose(

        covariance,

        covariance.T,

        atol=1e-10

    )

    # ========================================================
    # EWMA
    # ========================================================

    covariance = engine.estimate(

        "Recession",

        method="ewma"

    )

    assert covariance.shape == (
        10,
        10
    )

    # ========================================================
    # ROLLING
    # ========================================================

    covariance = engine.estimate(

        "Recovery",

        method="rolling",

        window=126

    )

    assert covariance.shape == (
        10,
        10
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    summary = engine.summary()

    assert summary["regime"] == "Recovery"

    assert summary["method"] == "rolling"

    assert summary["dimension"] == 10

    assert summary["observations"] == 300

    # ========================================================
    # METADATA
    # ========================================================

    metadata = engine.metadata

    assert metadata["version"] == "1.0.0"

    assert metadata["last_regime"] == "Recovery"

    assert metadata["last_observations"] == 300

    # ========================================================
    # API
    # ========================================================

    assert RegimeCovariance.API_VERSION == "1.0.0"

    assert "fit" in RegimeCovariance.PUBLIC_METHODS

    assert "estimate" in RegimeCovariance.PUBLIC_METHODS

    assert "summary" in RegimeCovariance.PUBLIC_METHODS

    # ========================================================
    # INVALID REGIME
    # ========================================================

    try:

        engine.estimate(

            "Crash"

        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ========================================================
    # ESTIMATE BEFORE FIT
    # ========================================================

    try:

        RegimeCovariance().estimate(

            "Expansion"

        )

        raise AssertionError(
            "Expected RuntimeError"
        )

    except RuntimeError:

        pass

    # ========================================================
    # LENGTH MISMATCH
    # ========================================================

    try:

        RegimeCovariance().fit(

            returns,

            regimes.iloc[:-1]

        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    print(
        "RegimeCovariance tests passed."
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    test_regime_covariance()