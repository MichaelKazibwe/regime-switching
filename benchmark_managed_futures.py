"""Fixed 10% actual DBMF sleeve illustration. Benchmark only; no fund selection."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from compare_portfolio_models import metrics, simulate
from evaluate_three_year_goal import OUT, rolling_goal


def build_comparison(raw, managed_prices):
    if (
        not isinstance(managed_prices.index, pd.DatetimeIndex)
        or not managed_prices.index.is_unique
        or not managed_prices.index.is_monotonic_increasing
        or not np.isfinite(managed_prices).all()
        or (managed_prices <= 0).any()
        or managed_prices.index.max() >= pd.Timestamp("2025-10-30")
    ):
        raise ValueError("Invalid managed-futures benchmark prices")
    symbols = ["SPY", "VEA", "VWO", "IEF", "TLT", "GLD"]
    prices = raw.loc[raw.index < pd.Timestamp("2025-10-30"), symbols].join(
        managed_prices.rename("DBMF"), how="inner"
    )
    if (
        len(prices) < 253
        or not np.isfinite(prices.to_numpy()).all()
        or (prices <= 0).any().any()
    ):
        raise ValueError("Insufficient complete observed overlap")
    returns = prices.pct_change(fill_method=None).iloc[253:]
    frames = {}
    table = []
    for share in (0.0, 0.10):
        target = np.array([(0.70 - share) / 3] * 3 + [0.09, 0.06, 0.10, share])
        targets = {returns.index[i]: target for i in range(0, len(returns), 21)}
        frame = simulate(
            returns,
            targets,
            cost_rate=0.0015,
            cash_returns=pd.Series(0.0, index=returns.index),
        )
        name = "10pct_actual_DBMF" if share else "growth_reference"
        frames[name] = frame
        result = metrics(frame, pd.Series(0.0, index=frame.index))
        result["sharpe_over_zero_cash"] = result.pop("sharpe_over_sgov")
        windows = rolling_goal(frame)
        table.append(
            {
                "model": name,
                "start": str(frame.index[0].date()),
                "end": str(frame.index[-1].date()),
                **result,
                "rolling_joint_success_frequency": float(windows.joint_success.mean())
                if len(windows)
                else None,
            }
        )
    return pd.DataFrame(table), frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    path = OUT / "dbmf-observed-prices.csv"
    if args.fetch:
        import yfinance as yf

        prices = yf.download(
            "DBMF",
            start="2019-05-07",
            end="2025-10-30",
            auto_adjust=True,
            progress=False,
            threads=False,
            timeout=30,
        )["Close"]
        if isinstance(prices, pd.DataFrame):
            prices = prices["DBMF"]
        prices = prices.dropna().rename("DBMF")
        if prices.empty:
            raise ValueError("No actual DBMF history returned")
        OUT.mkdir(parents=True, exist_ok=True)
        prices.to_csv(path)
    raw = pd.read_csv(
        "var/research/horizon-analysis/observed-history.csv",
        index_col=0,
        parse_dates=True,
    )
    managed = pd.read_csv(path, index_col=0, parse_dates=True).DBMF
    table, frames = build_comparison(raw, managed)
    for name, frame in frames.items():
        frame.to_csv(OUT / f"managed-futures-{name}.csv")
    table.to_csv(OUT / "managed-futures-comparison.csv", index=False)
    provenance = {
        "role": "BENCHMARK_ONLY_NOT_AUTHORIZED",
        "source": "Yahoo adjusted close via yfinance; embedded fund expenses",
        "official_reference": "https://www.imgp.com/us/fund/US53700T8273/",
        "source_hash": hashlib.sha256(path.read_bytes()).hexdigest(),
        "script_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "design": "Fixed 10% DBMF replacing equity; no parameter search; 252-return eligibility lag",
        "limitations": [
            "Actual fund history only; no pre-inception or proprietary index backfill.",
            "Short overlap, retrospective instrument choice and differing risk; no alpha inference.",
            "Adjusted-close next-close fills and constant transaction costs.",
            "An ETF implementation is not qualification of a direct futures strategy.",
        ],
    }
    (OUT / "managed-futures-provenance.json").write_text(
        json.dumps(provenance, indent=2)
    )
    print(
        table[
            [
                "model",
                "start",
                "end",
                "cagr",
                "max_drawdown",
                "rolling_joint_success_frequency",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
