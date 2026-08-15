# ======================================================================
# REGIME COVARIANCE
# ======================================================================

"""
Institutional regime-aware covariance estimator.

Estimates covariance using observations belonging to the requested
macro regime.
"""

# ======================================================================
# SECTION 1
# IMPORTS
# ======================================================================

from __future__ import annotations

import numpy as np
import pandas as pd

from covarianceengine import (
    CovarianceEngine,
)


# ======================================================================
# SECTION 2
# REGIME COVARIANCE
# ======================================================================


class RegimeCovariance:
    """
    Regime-specific covariance estimator.
    """

    # ------------------------------------------------------------------
    # 2.1 API METADATA
    # ------------------------------------------------------------------

    API_VERSION = (
        "1.0.0"
    )

    PUBLIC_METHODS = (
        "fit",
        "estimate",
        "summary",
        "health_check",
    )

    # ==================================================================
    # 2.2 CONSTRUCTOR
    # ==================================================================

    def __init__(
        self,
    ) -> None:

        self.engine = (
            CovarianceEngine()
        )

        self.returns = (
            None
        )

        self.regimes = (
            None
        )

        self.last_covariance = (
            None
        )

        self.last_regime = (
            None
        )

        self.last_observations = (
            None
        )

        self.last_summary = (
            None
        )

    # ==================================================================
    # SECTION 3
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ) -> dict:
        """
        Validate the production regime-covariance component.

        The component is healthy before fitting because fitting is a
        runtime data operation, not a construction requirement.
        """

        try:

            if not hasattr(
                self.engine,
                "estimate",
            ):

                return {
                    "api_version": (
                        self.API_VERSION
                    ),
                    "component": (
                        self.__class__.__name__
                    ),
                    "healthy": False,
                    "error": (
                        "Underlying CovarianceEngine "
                        "does not provide estimate()."
                    ),
                }

            if not hasattr(
                self.engine,
                "health_check",
            ):

                return {
                    "api_version": (
                        self.API_VERSION
                    ),
                    "component": (
                        self.__class__.__name__
                    ),
                    "healthy": False,
                    "error": (
                        "Underlying CovarianceEngine "
                        "does not provide health_check()."
                    ),
                }

            engine_health = (
                self.engine.health_check()
            )

            if not engine_health.get(
                "healthy",
                False,
            ):

                return {
                    "api_version": (
                        self.API_VERSION
                    ),
                    "component": (
                        self.__class__.__name__
                    ),
                    "healthy": False,
                    "error": (
                        "Underlying CovarianceEngine "
                        "is unhealthy."
                    ),
                    "engine_health": (
                        engine_health
                    ),
                }

            return {
                "api_version": (
                    self.API_VERSION
                ),
                "component": (
                    self.__class__.__name__
                ),
                "healthy": True,
                "fitted": (
                    self.returns is not None
                    and self.regimes is not None
                ),
                "available_regimes": (
                    self.available_regimes
                ),
                "last_regime": (
                    self.last_regime
                ),
                "last_observations": (
                    self.last_observations
                ),
            }

        except Exception as exc:

            return {
                "api_version": (
                    self.API_VERSION
                ),
                "component": (
                    self.__class__.__name__
                ),
                "healthy": False,
                "error": str(
                    exc
                ),
            }


    # ==================================================================
    # SECTION 4
    # INTERNAL HELPERS
    # ==================================================================

    @staticmethod
    def _ensure_dataframe(
        returns,
    ):
        """
        Validate that returns are provided as a pandas DataFrame.
        """

        if not isinstance(
            returns,
            pd.DataFrame,
        ):

            raise TypeError(
                "Returns must be a pandas DataFrame."
            )

        return returns

    @staticmethod
    def _ensure_series(
        regimes,
    ):
        """
        Validate and canonicalize regime labels.

        Regime labels are normalized to lowercase strings so that
        historical data, production model output, and enum values
        use the same internal representation.

        Examples
        --------
        "Expansion"      -> "expansion"
        "EXPANSION"      -> "expansion"
        Regime.EXPANSION -> "expansion"
        """

        if isinstance(
            regimes,
            list,
        ):

            regimes = pd.Series(
                regimes
            )

        if not isinstance(
            regimes,
            pd.Series,
        ):

            raise TypeError(
                "Regimes must be a pandas Series."
            )

        regimes = regimes.map(
            lambda value: (
                value.value
                if hasattr(
                    value,
                    "value",
                )
                else str(
                    value
                ).strip().lower()
            )
        )

        return regimes

    def _validate_lengths(
        self,
        returns,
        regimes,
    ):
        """
        Validate that returns and regime observations are aligned.
        """

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
        regime,
    ):
        """
        Select observations belonging to the requested regime.

        The requested regime is canonicalized before comparison so
        that labels such as 'Expansion', 'expansion', and
        'EXPANSION' all resolve to the same internal regime.
        """

        canonical_regime = (
            regime.value
            if hasattr(
                regime,
                "value",
            )
            else str(
                regime
            ).strip().lower()
        )

        mask = (
            self.regimes
            == canonical_regime
        )

        subset = (
            self.returns.loc[
                mask
            ]
        )

        if subset.empty:

            raise ValueError(
                f"No observations found "
                f"for regime '{canonical_regime}'."
            )

        return subset
 
    # ==================================================================
    # SECTION 5
    # FIT
    # ==================================================================

    def fit(
        self,
        returns,
        regimes,
    ):

        returns = (
            self._ensure_dataframe(
                returns
            )
        )

        regimes = (
            self._ensure_series(
                regimes
            )
        )

        self._validate_lengths(
            returns,
            regimes,
        )

        self.returns = (
            returns.copy()
        )

        self.regimes = (
            regimes.copy()
        )

        return self

    # ==================================================================
    # SECTION 6
    # AVAILABLE REGIMES
    # ==================================================================

    @property
    def available_regimes(
        self,
    ):

        if self.regimes is None:

            return []

        return sorted(
            self.regimes
            .unique()
            .tolist()
        )

    # ==================================================================
    # SECTION 7
    # ESTIMATE
    # ==================================================================

    def estimate(
        self,
        regime,
        method="ledoit_wolf",
        **kwargs,
    ):

        if self.returns is None:

            raise RuntimeError(
                "fit() must be called before estimate()."
            )

        subset = (
            self._select_regime(
                regime
            )
        )

        covariance = (
            self.engine.estimate(
                subset,
                method=method,
                **kwargs,
            )
        )

        self.last_covariance = (
            covariance
        )

        self.last_regime = (
            regime
        )

        self.last_observations = (
            len(subset)
        )

        self.last_summary = {
            "regime": regime,
            "method": method,
            "observations": (
                len(subset)
            ),
            "dimension": (
                covariance.shape[0]
            ),
        }

        return covariance

    # ==================================================================
    # SECTION 8
    # SUMMARY
    # ==================================================================

    def summary(
        self,
    ):

        if self.last_summary is None:

            raise RuntimeError(
                "No covariance has been estimated."
            )

        return dict(
            self.last_summary
        )

    # ==================================================================
    # SECTION 9
    # METADATA
    # ==================================================================

    @property
    def metadata(
        self,
    ) -> dict:

        return {
            "version": (
                self.API_VERSION
            ),
            "available_regimes": (
                self.available_regimes
            ),
            "last_regime": (
                self.last_regime
            ),
            "last_observations": (
                self.last_observations
            ),
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
        "expansion",
        "recession",
        "recovery",
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