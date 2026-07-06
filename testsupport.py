"""
===============================================================
TEST SUPPORT

Shared regression test utilities.

Every production module should use these builders instead of
duplicating synthetic data generation.

===============================================================
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from assetuniverse import (
    Asset,
    AssetUniverse,
)


# ============================================================
# RANDOM SEED
# ============================================================

DEFAULT_RANDOM_SEED = 42


# ============================================================
# TEST UNIVERSE
# ============================================================

def build_test_universe():

    universe = AssetUniverse()

    universe.add_asset(

        Asset(

            ticker="SPY",

            name="SPDR S&P 500 ETF",

            asset_class="Equity",

            sector="Large Cap",

            country="USA",

            currency="USD",

            benchmark="SP500"

        )

    )

    universe.add_asset(

        Asset(

            ticker="QQQ",

            name="NASDAQ 100 ETF",

            asset_class="Equity",

            sector="Technology",

            country="USA",

            currency="USD",

            benchmark="NASDAQ100"

        )

    )

    universe.add_asset(

        Asset(

            ticker="TLT",

            name="20+ Year Treasury",

            asset_class="Bond",

            sector="Government",

            country="USA",

            currency="USD",

            benchmark="Treasury"

        )

    )

    return universe


# ============================================================
# TEST RETURNS
# ============================================================

def build_test_returns(

    observations=1000,

    assets=3,

    seed=DEFAULT_RANDOM_SEED

):

    np.random.seed(

        seed

    )

    data = np.random.normal(

        0.001,

        0.02,

        size=(

            observations,

            assets

        )

    )

    columns = [

        f"Asset_{i}"

        for i in range(

            assets

        )

    ]

    return pd.DataFrame(

        data,

        columns=columns

    )


# ============================================================
# TEST COVARIANCE
# ============================================================

def build_test_covariance(

    observations=1000,

    assets=3,

    seed=DEFAULT_RANDOM_SEED

):

    returns = build_test_returns(

        observations,

        assets,

        seed

    )

    return returns.cov().values


# ============================================================
# EQUAL WEIGHTS
# ============================================================

def build_equal_weights(

    assets=3

):

    return np.ones(

        assets

    ) / assets

# ============================================================
# REGRESSION TESTS
# ============================================================

def test_support():

    universe = build_test_universe()

    assert universe.size == 3

    returns = build_test_returns()

    assert returns.shape == (

        1000,

        3

    )

    covariance = build_test_covariance()

    assert covariance.shape == (

        3,

        3

    )

    weights = build_equal_weights()

    assert len(

        weights

    ) == 3

    assert np.isclose(

        weights.sum(),

        1.0

    )

    print(

        "TestSupport tests passed."

    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    test_support()