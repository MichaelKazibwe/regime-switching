"""
======================================================================
MARKET DATA LOADER TEST SUITE
======================================================================

Purpose
-------
Production regression and contract tests for MarketDataLoader.

This test suite verifies the market-data ingestion boundary without
weakening production behavior to accommodate an incorrect test.

Core contracts
--------------
The suite explicitly verifies that:

    1. Requested assets are normalized deterministically.
    2. Yahoo Finance Close extraction works for supported layouts.
    3. Batched downloads are attempted correctly.
    4. Individual recovery retries correctly.
    5. Completely missing assets may be recovered.
    6. Entirely NaN assets may be recovered.
    7. Partially missing assets are NOT recovered.
    8. Partial historical NaNs are never interpolated.
    9. Partial historical NaNs are never forward-filled.
   10. Partial historical NaNs are never backward-filled.
   11. Existing valid observations are never overwritten.
   12. No synthetic historical observations are created.
   13. Requested asset ordering is deterministic.
   14. Finalization correctly tracks incomplete assets.
   15. Price validation boundaries remain intact.
   16. Return calculation remains intact.
   17. Health state remains deterministic.
   18. The public API version remains frozen at 2.0.0.

Critical Recovery Contract
--------------------------
Recovery is permitted only when an asset is genuinely missing:

    * the asset column does not exist; or
    * the asset column exists but contains no valid observations.

A partially missing series is intentionally preserved.

For example:

    Original:

        100
        NaN
        102
        NaN
        104

    Recovery data:

        110
        111
        112
        113
        114

    Correct result:

        100
        NaN
        102
        NaN
        104

The recovery mechanism MUST NOT use the second series to fill the
historical gaps.

Author
------
Portfolio System Engineering

Phase
-----
Production Hardening
======================================================================
"""


from __future__ import annotations


# ======================================================================
# SECTION 1
# IMPORTS
# ======================================================================


import numpy as np
import pandas as pd
import pytest


from exceptions import DataValidationError
from marketdataloader import MarketDataLoader


# ======================================================================
# SECTION 2
# TEST HELPERS
# ======================================================================


def make_index(
    periods: int = 5,
) -> pd.DatetimeIndex:
    """
    Create a deterministic daily test index.
    """

    return pd.date_range(
        "2026-01-01",
        periods=periods,
        freq="D",
    )


def make_prices(
    columns=("SPY", "TLT"),
    periods: int = 5,
) -> pd.DataFrame:
    """
    Create a deterministic positive price matrix.
    """

    index = make_index(
        periods
    )

    values = np.arange(
        periods * len(columns),
        dtype=float,
    ).reshape(
        periods,
        len(columns),
    )

    values = values + 100.0

    return pd.DataFrame(
        values,
        index=index,
        columns=columns,
    )


# ======================================================================
# SECTION 3
# CONFIGURATION
# ======================================================================


def test_default_assets_are_loaded_from_configuration():
    """
    Explicit assets must be normalized correctly.
    """

    loader = MarketDataLoader(
        assets=["spy"]
    )

    assert loader.assets == [
        "SPY"
    ]


def test_asset_normalization():
    """
    Asset normalization must strip, uppercase, deduplicate, and
    preserve first-seen order.
    """

    loader = MarketDataLoader(
        assets=[
            " spy ",
            "TLT",
            "spy",
            "efa",
        ]
    )

    assert loader.assets == [
        "SPY",
        "TLT",
        "EFA",
    ]


def test_empty_assets_are_rejected():
    """
    An empty requested universe is invalid.
    """

    with pytest.raises(
        ValueError,
        match="requires at least one asset",
    ):

        MarketDataLoader(
            assets=[]
        )


def test_blank_assets_are_rejected():
    """
    A universe containing only blank tickers is invalid.
    """

    with pytest.raises(
        ValueError,
        match="requires at least one asset",
    ):

        MarketDataLoader(
            assets=[
                "",
                "   ",
            ]
        )


def test_retry_count_is_nonnegative():
    """
    Negative retry counts must be normalized to zero.
    """

    loader = MarketDataLoader(
        assets=["SPY"],
        max_retries=-10,
    )

    assert loader.max_retries == 0


# ======================================================================
# SECTION 4
# CLOSE EXTRACTION
# ======================================================================


def test_extract_close_single_ticker():
    """
    A standard single-ticker Close column must be extracted.
    """

    index = make_index()

    frame = pd.DataFrame(
        {
            "Open": [1, 2, 3, 4, 5],
            "Close": [10, 11, 12, 13, 14],
        },
        index=index,
    )

    result = MarketDataLoader._extract_close(
        frame
    )

    assert list(
        result.columns
    ) == [
        "UNKNOWN"
    ]

    assert result[
        "UNKNOWN"
    ].tolist() == [
        10,
        11,
        12,
        13,
        14,
    ]


def test_extract_close_price_first_multiindex():
    """
    Price-first Yahoo MultiIndex output must be supported.
    """

    index = make_index()

    columns = pd.MultiIndex.from_tuples(
        [
            ("Open", "SPY"),
            ("Close", "SPY"),
            ("Open", "TLT"),
            ("Close", "TLT"),
        ]
    )

    frame = pd.DataFrame(
        [
            [1, 10, 2, 20],
            [2, 11, 3, 21],
            [3, 12, 4, 22],
            [4, 13, 5, 23],
            [5, 14, 6, 24],
        ],
        index=index,
        columns=columns,
    )

    result = MarketDataLoader._extract_close(
        frame
    )

    assert list(
        result.columns
    ) == [
        "SPY",
        "TLT",
    ]

    assert result[
        "SPY"
    ].tolist() == [
        10,
        11,
        12,
        13,
        14,
    ]


def test_extract_close_ticker_first_multiindex():
    """
    Ticker-first Yahoo MultiIndex output must be supported.
    """

    index = make_index()

    columns = pd.MultiIndex.from_tuples(
        [
            ("SPY", "Open"),
            ("SPY", "Close"),
            ("TLT", "Open"),
            ("TLT", "Close"),
        ]
    )

    frame = pd.DataFrame(
        [
            [1, 10, 2, 20],
            [2, 11, 3, 21],
            [3, 12, 4, 22],
            [4, 13, 5, 23],
            [5, 14, 6, 24],
        ],
        index=index,
        columns=columns,
    )

    result = MarketDataLoader._extract_close(
        frame
    )

    assert list(
        result.columns
    ) == [
        "SPY",
        "TLT",
    ]

    assert result[
        "TLT"
    ].tolist() == [
        20,
        21,
        22,
        23,
        24,
    ]


def test_extract_close_returns_empty_when_close_is_missing():
    """
    A MultiIndex frame without Close data must return an empty frame.
    """

    index = make_index()

    columns = pd.MultiIndex.from_tuples(
        [
            ("SPY", "Open"),
            ("SPY", "High"),
        ]
    )

    frame = pd.DataFrame(
        np.ones(
            (5, 2)
        ),
        index=index,
        columns=columns,
    )

    result = MarketDataLoader._extract_close(
        frame
    )

    assert result.empty


def test_extract_close_handles_empty_frame():
    """
    Empty input must produce empty output.
    """

    result = MarketDataLoader._extract_close(
        pd.DataFrame()
    )

    assert result.empty


def test_extract_close_handles_none():
    """
    None input must produce empty output.
    """

    result = MarketDataLoader._extract_close(
        None
    )

    assert result.empty


# ======================================================================
# SECTION 5
# BATCH DOWNLOAD
# ======================================================================


def test_batch_download_normalizes_columns_and_index(
    monkeypatch,
):
    """
    Batch download must normalize ticker names and timestamps.
    """

    loader = MarketDataLoader(
        assets=[
            "SPY",
            "TLT",
        ]
    )

    raw = make_prices(
        columns=[
            "spy",
            "tlt",
        ]
    )

    def fake_download(
        _tickers,
    ):
        return raw

    monkeypatch.setattr(
        loader,
        "_download",
        fake_download,
    )

    result = loader._download_batch()

    assert list(
        result.columns
    ) == [
        "SPY",
        "TLT",
    ]

    assert result.index.is_monotonic_increasing

    assert loader.last_batch_error is None


def test_batch_download_failure_is_recorded(
    monkeypatch,
):
    """
    Batch exceptions must be recorded rather than hidden.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    def broken_download(
        _tickers,
    ):
        raise RuntimeError(
            "network failure"
        )

    monkeypatch.setattr(
        loader,
        "_download",
        broken_download,
    )

    result = loader._download_batch()

    assert result.empty

    assert (
        loader.last_batch_error
        == "network failure"
    )


def test_batch_download_empty_response(
    monkeypatch,
):
    """
    An empty Yahoo response must be recorded as a batch error.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    monkeypatch.setattr(
        loader,
        "_download",
        lambda _tickers: pd.DataFrame(),
    )

    result = loader._download_batch()

    assert result.empty

    assert (
        "empty price frame"
        in loader.last_batch_error.lower()
    )


# ======================================================================
# SECTION 6
# SINGLE-TICKER DOWNLOAD
# ======================================================================


def test_single_ticker_download_extracts_unknown_close(
    monkeypatch,
):
    """
    Single-ticker download must support normal Close responses.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    index = make_index()

    raw = pd.DataFrame(
        {
            "Close": [
                100,
                101,
                102,
                103,
                104,
            ]
        },
        index=index,
    )

    monkeypatch.setattr(
        loader,
        "_download",
        lambda _ticker: raw,
    )

    result = loader._download_single(
        "SPY"
    )

    assert result is not None

    assert result.name == "SPY"

    assert result.tolist() == [
        100,
        101,
        102,
        103,
        104,
    ]


def test_single_ticker_download_retries(
    monkeypatch,
):
    """
    Individual downloads must retry up to max_retries.
    """

    loader = MarketDataLoader(
        assets=["SPY"],
        max_retries=2,
    )

    calls = {
        "count": 0
    }

    raw = pd.DataFrame(
        {
            "Close": [
                100,
                101,
                102,
            ]
        },
        index=make_index(
            3
        ),
    )

    def flaky_download(
        _ticker,
    ):

        calls["count"] += 1

        if calls["count"] < 3:

            raise RuntimeError(
                "temporary failure"
            )

        return raw

    monkeypatch.setattr(
        loader,
        "_download",
        flaky_download,
    )

    result = loader._download_single(
        "SPY"
    )

    assert result is not None

    assert calls["count"] == 3


def test_single_ticker_download_returns_none_after_retries(
    monkeypatch,
):
    """
    Persistent individual download failure must return None after all
    retry attempts.
    """

    loader = MarketDataLoader(
        assets=["SPY"],
        max_retries=2,
    )

    calls = {
        "count": 0
    }

    def broken_download(
        _ticker,
    ):

        calls["count"] += 1

        raise RuntimeError(
            "permanent failure"
        )

    monkeypatch.setattr(
        loader,
        "_download",
        broken_download,
    )

    result = loader._download_single(
        "SPY"
    )

    assert result is None

    assert calls["count"] == 3


def test_single_ticker_download_does_not_accept_all_nan_series(
    monkeypatch,
):
    """
    An entirely NaN downloaded series cannot be considered recovered.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    raw = pd.DataFrame(
        {
            "Close": [
                np.nan,
                np.nan,
                np.nan,
            ]
        },
        index=make_index(
            3
        ),
    )

    monkeypatch.setattr(
        loader,
        "_download",
        lambda _ticker: raw,
    )

    result = loader._download_single(
        "SPY"
    )

    assert result is None


# ======================================================================
# SECTION 7
# RECOVERY — MISSING ASSETS
# ======================================================================


def test_missing_asset_is_recovered(
    monkeypatch,
):
    """
    An absent asset column may be recovered individually.
    """

    loader = MarketDataLoader(
        assets=[
            "SPY",
            "TLT",
        ]
    )

    original = make_prices(
        columns=["SPY"]
    )

    recovered = pd.Series(
        [
            200,
            201,
            202,
            203,
            204,
        ],
        index=make_index(),
        name="TLT",
    )

    calls: list[str] = []

    def fake_single(
        ticker,
    ):

        calls.append(
            ticker
        )

        return recovered

    monkeypatch.setattr(
        loader,
        "_download_single",
        fake_single,
    )

    result = loader._recover_missing_assets(
        original
    )

    assert list(
        result.columns
    ) == [
        "SPY",
        "TLT",
    ]

    assert result[
        "TLT"
    ].tolist() == [
        200,
        201,
        202,
        203,
        204,
    ]

    assert calls == [
        "TLT"
    ]

    assert (
        loader.last_recovered_assets
        == ("TLT",)
    )


def test_entirely_nan_asset_is_recovered(
    monkeypatch,
):
    """
    An asset column containing only NaNs may be recovered individually.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    original = pd.DataFrame(
        {
            "SPY": [
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
            ]
        },
        index=make_index(),
    )

    recovered = pd.Series(
        [
            110,
            111,
            112,
            113,
            114,
        ],
        index=make_index(),
        name="SPY",
    )

    calls: list[str] = []

    def fake_single(
        ticker,
    ):

        calls.append(
            ticker
        )

        return recovered

    monkeypatch.setattr(
        loader,
        "_download_single",
        fake_single,
    )

    result = loader._recover_missing_assets(
        original
    )

    assert result[
        "SPY"
    ].tolist() == [
        110,
        111,
        112,
        113,
        114,
    ]

    assert calls == [
        "SPY"
    ]

    assert (
        loader.last_recovered_assets
        == ("SPY",)
    )


# ======================================================================
# SECTION 8
# RECOVERY — PARTIAL MISSING DATA
# ======================================================================


def test_partial_missing_asset_is_not_recovered(
    monkeypatch,
):
    """
    A partially missing asset must NOT be downloaded again.

    This is the critical production recovery invariant.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    original = pd.DataFrame(
        {
            "SPY": [
                100,
                np.nan,
                102,
                np.nan,
                104,
            ]
        },
        index=make_index(),
    )

    calls: list[str] = []

    def forbidden_download(
        ticker,
    ):

        calls.append(
            ticker
        )

        return pd.Series(
            [
                110,
                111,
                112,
                113,
                114,
            ],
            index=make_index(),
            name=ticker,
        )

    monkeypatch.setattr(
        loader,
        "_download_single",
        forbidden_download,
    )

    result = loader._recover_missing_assets(
        original
    )

    assert calls == []

    assert result[
        "SPY"
    ].isna().sum() == 2

    assert result[
        "SPY"
    ].tolist()[0] == 100

    assert result[
        "SPY"
    ].tolist()[2] == 102

    assert result[
        "SPY"
    ].tolist()[4] == 104

    assert (
        loader.last_recovered_assets
        == ()
    )


def test_partial_missing_asset_preserves_original_values(
    monkeypatch,
):
    """
    Recovery must never overwrite existing valid observations in a
    partially missing series.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    original = pd.DataFrame(
        {
            "SPY": [
                100,
                np.nan,
                102,
                np.nan,
                104,
            ]
        },
        index=make_index(),
    )

    replacement = pd.Series(
        [
            999,
            888,
            777,
            666,
            555,
        ],
        index=make_index(),
        name="SPY",
    )

    monkeypatch.setattr(
        loader,
        "_download_single",
        lambda _ticker: replacement,
    )

    result = loader._recover_missing_assets(
        original
    )

    assert result.loc[
        make_index()[0],
        "SPY",
    ] == 100

    assert result.loc[
        make_index()[2],
        "SPY",
    ] == 102

    assert result.loc[
        make_index()[4],
        "SPY",
    ] == 104

    assert result[
        "SPY"
    ].isna().sum() == 2


def test_partial_missing_asset_does_not_use_recovery_values(
    monkeypatch,
):
    """
    Recovery values must not be used to fill partial historical gaps.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    original = pd.DataFrame(
        {
            "SPY": [
                100,
                np.nan,
                102,
                np.nan,
                104,
            ]
        },
        index=make_index(),
    )

    replacement = pd.Series(
        [
            110,
            111,
            112,
            113,
            114,
        ],
        index=make_index(),
        name="SPY",
    )

    monkeypatch.setattr(
        loader,
        "_download_single",
        lambda _ticker: replacement,
    )

    result = loader._recover_missing_assets(
        original
    )

    assert pd.isna(
        result.loc[
            make_index()[1],
            "SPY",
        ]
    )

    assert pd.isna(
        result.loc[
            make_index()[3],
            "SPY",
        ]
    )


def test_recovery_does_not_interpolate():
    """
    Partial historical gaps must remain NaN rather than being
    interpolated.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    original = pd.DataFrame(
        {
            "SPY": [
                100,
                np.nan,
                102,
                np.nan,
                104,
            ]
        },
        index=make_index(),
    )

    result = loader._recover_missing_assets(
        original
    )

    assert result[
        "SPY"
    ].isna().sum() == 2


def test_recovery_does_not_forward_fill():
    """
    Forward-fill must never occur during recovery.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    original = pd.DataFrame(
        {
            "SPY": [
                100,
                np.nan,
                102,
            ]
        },
        index=make_index(
            3
        ),
    )

    result = loader._recover_missing_assets(
        original
    )

    assert pd.isna(
        result.iloc[
            1
        ]["SPY"]
    )


def test_recovery_does_not_backward_fill():
    """
    Backward-fill must never occur during recovery.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    original = pd.DataFrame(
        {
            "SPY": [
                np.nan,
                101,
                102,
            ]
        },
        index=make_index(
            3
        ),
    )

    result = loader._recover_missing_assets(
        original
    )

    assert pd.isna(
        result.iloc[
            0
        ]["SPY"]
    )


def test_recovery_does_not_create_synthetic_prices():
    """
    Recovery must not manufacture values when no actual download is
    requested.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    original = pd.DataFrame(
        {
            "SPY": [
                100,
                np.nan,
                102,
            ]
        },
        index=make_index(
            3
        ),
    )

    result = loader._recover_missing_assets(
        original
    )

    pd.testing.assert_series_equal(
        result["SPY"],
        original["SPY"],
    )


# ======================================================================
# SECTION 9
# RECOVERY TARGET SELECTION
# ======================================================================


def test_recovery_attempts_only_missing_assets(
    monkeypatch,
):
    """
    Only absent asset columns should trigger individual recovery.
    """

    loader = MarketDataLoader(
        assets=[
            "SPY",
            "TLT",
        ]
    )

    prices = make_prices(
        columns=[
            "SPY",
        ]
    )

    calls: list[str] = []

    def fake_single(
        ticker,
    ):

        calls.append(
            ticker
        )

        return pd.Series(
            [
                200,
                201,
                202,
                203,
                204,
            ],
            index=make_index(),
            name=ticker,
        )

    monkeypatch.setattr(
        loader,
        "_download_single",
        fake_single,
    )

    loader._recover_missing_assets(
        prices
    )

    assert calls == [
        "TLT"
    ]


def test_recovery_skips_complete_assets(
    monkeypatch,
):
    """
    Complete assets must never trigger individual recovery.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    prices = make_prices(
        columns=["SPY"]
    )

    calls: list[str] = []

    monkeypatch.setattr(
        loader,
        "_download_single",
        lambda ticker: calls.append(
            ticker
        ),
    )

    result = loader._recover_missing_assets(
        prices
    )

    assert calls == []

    pd.testing.assert_frame_equal(
        result,
        prices,
    )


def test_recovery_skips_partial_assets(
    monkeypatch,
):
    """
    Partially observed assets must never trigger recovery.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    prices = pd.DataFrame(
        {
            "SPY": [
                100,
                np.nan,
                102,
            ]
        },
        index=make_index(
            3
        ),
    )

    calls: list[str] = []

    monkeypatch.setattr(
        loader,
        "_download_single",
        lambda ticker: calls.append(
            ticker
        ),
    )

    loader._recover_missing_assets(
        prices
    )

    assert calls == []


# ======================================================================
# SECTION 10
# FINALIZATION / REQUESTED ORDER
# ======================================================================


def test_finalize_preserves_requested_asset_order():
    """
    Finalization must restore the requested asset ordering.
    """

    loader = MarketDataLoader(
        assets=[
            "TLT",
            "SPY",
        ]
    )

    prices = make_prices(
        columns=[
            "SPY",
            "TLT",
        ]
    )

    result = loader._finalize(
        prices
    )

    assert list(
        result.columns
    ) == [
        "TLT",
        "SPY",
    ]


def test_finalize_sorts_index():
    """
    Finalization must sort historical observations chronologically.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    index = pd.to_datetime(
        [
            "2026-01-03",
            "2026-01-01",
            "2026-01-02",
        ]
    )

    prices = pd.DataFrame(
        {
            "SPY": [
                103,
                101,
                102,
            ]
        },
        index=index,
    )

    result = loader._finalize(
        prices
    )

    assert result.index.tolist() == list(
        pd.to_datetime(
            [
                "2026-01-01",
                "2026-01-02",
                "2026-01-03",
            ]
        )
    )


def test_finalize_removes_duplicate_timestamps():
    """
    Duplicate timestamps must be removed deterministically.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    index = pd.to_datetime(
        [
            "2026-01-01",
            "2026-01-01",
            "2026-01-02",
        ]
    )

    prices = pd.DataFrame(
        {
            "SPY": [
                100,
                101,
                102,
            ]
        },
        index=index,
    )

    result = loader._finalize(
        prices
    )

    assert not result.index.duplicated().any()

    assert len(result) == 2


def test_finalize_marks_missing_assets():
    """
    Missing requested assets must be recorded as incomplete and failed.
    """

    loader = MarketDataLoader(
        assets=[
            "SPY",
            "TLT",
        ]
    )

    prices = make_prices(
        columns=["SPY"]
    )

    result = loader._finalize(
        prices
    )

    assert "TLT" in (
        loader.last_incomplete_assets
    )

    assert "TLT" in (
        loader.last_failed_assets
    )

    assert list(
        result.columns
    ) == [
        "SPY",
        "TLT",
    ]


def test_finalize_marks_partial_series_incomplete():
    """
    A partially missing series remains incomplete after finalization.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    prices = pd.DataFrame(
        {
            "SPY": [
                100,
                np.nan,
                102,
            ]
        },
        index=make_index(
            3
        ),
    )

    loader._finalize(
        prices
    )

    assert (
        "SPY"
        in loader.last_incomplete_assets
    )

    assert (
        "SPY"
        in loader.last_failed_assets
    )


# ======================================================================
# SECTION 11
# PUBLIC PRICE API
# ======================================================================


def test_load_prices_validates_final_dataset(
    monkeypatch,
):
    """
    load_prices must return the finalized validated price matrix.
    """

    loader = MarketDataLoader(
        assets=[
            "SPY",
            "TLT",
        ]
    )

    prices = make_prices()

    monkeypatch.setattr(
        loader,
        "_download_batch",
        lambda: prices,
    )

    monkeypatch.setattr(
        loader,
        "_recover_missing_assets",
        lambda frame: frame,
    )

    result = loader.load_prices()

    assert isinstance(
        result,
        pd.DataFrame,
    )

    assert list(
        result.columns
    ) == [
        "SPY",
        "TLT",
    ]


def test_load_prices_can_skip_external_validation(
    monkeypatch,
):
    """
    validate=False must preserve the explicit research/data-inspection
    path.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    prices = make_prices(
        columns=["SPY"]
    )

    monkeypatch.setattr(
        loader,
        "_download_batch",
        lambda: prices,
    )

    monkeypatch.setattr(
        loader,
        "_recover_missing_assets",
        lambda frame: frame,
    )

    result = loader.load_prices(
        validate=False
    )

    pd.testing.assert_frame_equal(
        result,
        prices,
    )


def test_load_prices_rejects_empty_final_dataset(
    monkeypatch,
):
    """
    Empty final price data must fail closed.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    monkeypatch.setattr(
        loader,
        "_download_batch",
        lambda: pd.DataFrame(),
    )

    monkeypatch.setattr(
        loader,
        "_recover_missing_assets",
        lambda frame: frame,
    )

    with pytest.raises(
        DataValidationError,
        match="No historical price data",
    ):

        loader.load_prices(
            validate=False
        )


# ======================================================================
# SECTION 12
# RETURNS
# ======================================================================


def test_load_returns_produces_percentage_returns(
    monkeypatch,
):
    """
    Returns must be calculated as percentage price changes.
    """

    loader = MarketDataLoader(
        assets=[
            "SPY",
            "TLT",
        ]
    )

    prices = pd.DataFrame(
        {
            "SPY": [
                100,
                110,
                121,
            ],
            "TLT": [
                100,
                105,
                110,
            ],
        },
        index=make_index(
            3
        ),
    )

    monkeypatch.setattr(
        loader,
        "load_prices",
        lambda: prices,
    )

    result = loader.load_returns()

    assert result.shape == (
        2,
        2,
    )

    assert np.isclose(
        result.iloc[
            0
        ]["SPY"],
        0.10,
    )


def test_load_returns_rejects_empty_returns(
    monkeypatch,
):
    """
    A single-observation price series cannot produce a valid return
    matrix.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    prices = pd.DataFrame(
        {
            "SPY": [
                100,
            ]
        },
        index=make_index(
            1
        ),
    )

    monkeypatch.setattr(
        loader,
        "load_prices",
        lambda: prices,
    )

    with pytest.raises(
        RuntimeError,
        match="Return series is empty",
    ):

        loader.load_returns()


def test_load_returns_propagates_runtime_errors(
    monkeypatch,
):
    """
    Runtime errors from the price boundary must propagate.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    def broken_load():

        raise RuntimeError(
            "Yahoo unavailable"
        )

    monkeypatch.setattr(
        loader,
        "load_prices",
        broken_load,
    )

    with pytest.raises(
        RuntimeError,
        match="Yahoo unavailable",
    ):

        loader.load_returns()


# ======================================================================
# SECTION 13
# VALIDATION BOUNDARIES
# ======================================================================


def test_nan_prices_remain_visible_after_finalize():
    """
    Finalization must not hide or repair missing observations.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    prices = pd.DataFrame(
        {
            "SPY": [
                100,
                np.nan,
                102,
            ]
        },
        index=make_index(
            3
        ),
    )

    result = loader._finalize(
        prices
    )

    assert result[
        "SPY"
    ].isna().sum() == 1

    assert (
        "SPY"
        in loader.last_incomplete_assets
    )


def test_non_numeric_values_are_coerced_to_nan():
    """
    Invalid numeric values must become NaN rather than fabricated
    prices.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    prices = pd.DataFrame(
        {
            "SPY": [
                "100",
                "invalid",
                "102",
            ]
        },
        index=make_index(
            3
        ),
    )

    result = loader._finalize(
        prices
    )

    assert result[
        "SPY"
    ].dtype.kind == "f"

    assert pd.isna(
        result.loc[
            make_index(3)[1],
            "SPY",
        ]
    )


def test_no_fabricated_prices_are_created():
    """
    Missing historical observations must remain missing.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    prices = pd.DataFrame(
        {
            "SPY": [
                100,
                np.nan,
                102,
            ]
        },
        index=make_index(
            3
        ),
    )

    result = loader._finalize(
        prices
    )

    assert pd.isna(
        result.iloc[
            1
        ]["SPY"]
    )


# ======================================================================
# SECTION 14
# DATA INTEGRITY
# ======================================================================


def test_recovery_does_not_modify_input_dataframe(
    monkeypatch,
):
    """
    Recovery must operate on a copy and must not mutate the original
    caller-owned DataFrame.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    original = pd.DataFrame(
        {
            "SPY": [
                100,
                np.nan,
                102,
            ]
        },
        index=make_index(
            3
        ),
    )

    original_copy = original.copy(
        deep=True
    )

    monkeypatch.setattr(
        loader,
        "_download_single",
        lambda _ticker: pd.Series(
            [
                999,
                888,
                777,
            ],
            index=make_index(
                3
            ),
            name="SPY",
        ),
    )

    loader._recover_missing_assets(
        original
    )

    pd.testing.assert_frame_equal(
        original,
        original_copy,
    )


def test_partial_missing_asset_is_not_marked_recovered():
    """
    A partially missing series must not be reported as recovered.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    prices = pd.DataFrame(
        {
            "SPY": [
                100,
                np.nan,
                102,
            ]
        },
        index=make_index(
            3
        ),
    )

    result = loader._recover_missing_assets(
        prices
    )

    assert (
        loader.last_recovered_assets
        == ()
    )

    assert result[
        "SPY"
    ].isna().sum() == 1


# ======================================================================
# SECTION 15
# HEALTH CHECK / STATE
# ======================================================================


def test_initial_health_is_healthy():
    """
    A newly initialized loader has no failed state.
    """

    loader = MarketDataLoader(
        assets=[
            "SPY",
            "TLT",
        ]
    )

    health = loader.health_check()

    assert health[
        "api_version"
    ] == "2.0.0"

    assert health[
        "component"
    ] == "MarketDataLoader"

    assert health[
        "healthy"
    ] is True

    assert health[
        "asset_count"
    ] == 2

    assert health[
        "failed_assets"
    ] == []


def test_health_becomes_unhealthy_when_assets_fail():
    """
    Recorded failed assets must make health false.
    """

    loader = MarketDataLoader(
        assets=[
            "SPY",
            "TLT",
        ]
    )

    loader.last_failed_assets = (
        "TLT",
    )

    health = loader.health_check()

    assert health[
        "healthy"
    ] is False

    assert health[
        "failed_assets"
    ] == [
        "TLT"
    ]


def test_health_reports_recovery_state():
    """
    Successful recovery state must be exposed through health_check().
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    loader.last_recovered_assets = (
        "SPY",
    )

    health = loader.health_check()

    assert health[
        "recovered_assets"
    ] == [
        "SPY"
    ]


def test_health_reports_incomplete_state():
    """
    Incomplete assets must be exposed through health_check().
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    loader.last_incomplete_assets = (
        "SPY",
    )

    health = loader.health_check()

    assert health[
        "incomplete_assets"
    ] == [
        "SPY"
    ]


# ======================================================================
# SECTION 16
# API FREEZE
# ======================================================================


def test_api_version():
    """
    The MarketDataLoader API version remains frozen at 2.0.0.

    Internal hardening must not silently constitute an API-version
    change.
    """

    assert (
        MarketDataLoader.API_VERSION
        == "2.0.0"
    )


def test_required_public_methods_exist():
    """
    Required production methods must remain available.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    required_methods = {
        "load_prices",
        "load_returns",
        "health_check",
    }

    for method in required_methods:

        assert hasattr(
            loader,
            method,
        )

        assert callable(
            getattr(
                loader,
                method,
            )
        )


# ======================================================================
# SECTION 17
# DETERMINISM
# ======================================================================


def test_asset_order_is_deterministic():
    """
    Asset normalization must be deterministic.
    """

    loader = MarketDataLoader(
        assets=[
            "TLT",
            "SPY",
            "EFA",
        ]
    )

    assert loader.assets == [
        "TLT",
        "SPY",
        "EFA",
    ]

    first = loader.assets.copy()

    second = loader.assets.copy()

    assert first == second


def test_finalize_is_deterministic():
    """
    Repeated finalization of the same input must produce identical
    results.
    """

    loader = MarketDataLoader(
        assets=[
            "SPY",
            "TLT",
        ]
    )

    prices = make_prices(
        columns=[
            "TLT",
            "SPY",
        ]
    )

    first = loader._finalize(
        prices
    )

    second = loader._finalize(
        prices
    )

    pd.testing.assert_frame_equal(
        first,
        second,
    )


def test_recovery_is_deterministic_for_partial_series():
    """
    Partial-series recovery must produce identical results because no
    external recovery is attempted.
    """

    loader = MarketDataLoader(
        assets=["SPY"]
    )

    prices = pd.DataFrame(
        {
            "SPY": [
                100,
                np.nan,
                102,
                np.nan,
                104,
            ]
        },
        index=make_index(),
    )

    first = loader._recover_missing_assets(
        prices
    )

    second = loader._recover_missing_assets(
        prices
    )

    pd.testing.assert_frame_equal(
        first,
        second,
    )


# ======================================================================
# SECTION 18
# MODULE REGRESSION ENTRY POINT
# ======================================================================


def test_market_data_exception():
    """
    The module-level failure boundary must propagate RuntimeError.
    """

    class BrokenLoader(
        MarketDataLoader
    ):

        def load_prices(
            self,
            validate: bool = True,
        ):

            raise RuntimeError(
                "Yahoo unavailable"
            )

    with pytest.raises(
        RuntimeError,
        match="Yahoo unavailable",
    ):

        BrokenLoader(
            assets=["SPY"]
        ).load_returns()


# ======================================================================
# SECTION 19
# MAIN
# ======================================================================


if __name__ == "__main__":

    pytest.main(
        [
            __file__,
            "-v",
        ]
    )