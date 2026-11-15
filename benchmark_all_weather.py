"""Descriptive actual ALLW overlap; never used to select or tune the candidate."""

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from compare_portfolio_models import metrics
from optimize_hybrid_portfolio import rebased
from refine_institutional_portfolio import OUT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    path = OUT / "allw-observed-prices.csv"
    if args.fetch:
        import yfinance as yf

        prices = yf.download(
            "ALLW",
            start="2025-03-06",
            end="2025-10-30",
            auto_adjust=True,
            progress=False,
            threads=False,
            timeout=30,
        )["Close"]
        if isinstance(prices, pd.DataFrame):
            prices = prices["ALLW"]
        prices = prices.rename("ALLW").dropna()
        if prices.empty or prices.index[-1] >= pd.Timestamp("2025-10-30"):
            raise ValueError("Invalid or empty ALLW benchmark response")
        OUT.mkdir(parents=True, exist_ok=True)
        prices.to_csv(path)
    prices = pd.read_csv(path, index_col=0, parse_dates=True).ALLW
    r = prices.pct_change(fill_method=None).dropna()
    # Charge entry at the first aligned close; a held account has no exit trade.
    from compare_portfolio_models import rebalance_fee

    fee = rebalance_fee(
        pd.Series([0.0]).to_numpy(), pd.Series([1.0]).to_numpy(), 0.0015
    )
    actual = pd.DataFrame(
        {"return": r, "cash": 0.0, "turnover": 0.0, "cost_as_initial_capital": 0.0}
    )
    actual.iloc[0, actual.columns.get_loc("return")] = (1 + r.iloc[0]) * (1 - fee) - 1
    actual.iloc[0, actual.columns.get_loc("turnover")] = 1 - fee
    actual.iloc[0, actual.columns.get_loc("cost_as_initial_capital")] = (
        1 + r.iloc[0]
    ) * fee
    actual["equity"] = (1 + actual["return"]).cumprod()
    rows = []
    frames = {"Actual ALLW buy and hold": actual}
    for name, filename in [
        ("Refined V4", "refined-v4.csv"),
        ("Prior macro V3", "prior-macro-v3.csv"),
        ("All Weather-inspired proxy", "all-weather-inspired-proxy.csv"),
    ]:
        frame = pd.read_csv(OUT / filename, index_col=0, parse_dates=True)
        frames[name] = rebased(frame.loc[r.index])
    for name, frame in frames.items():
        m = metrics(frame, pd.Series(0.0, index=frame.index))
        m["sharpe_over_zero_cash"] = m.pop("sharpe_over_sgov")
        rows.append(
            {
                "model": name,
                "start": str(r.index[0].date()),
                "end": str(r.index[-1].date()),
                "sessions": len(r),
                **m,
            }
        )
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "actual-allw-overlap.csv", index=False)
    (OUT / "actual-allw-provenance.json").write_text(
        json.dumps(
            {
                "source": "Yahoo adjusted close via yfinance; fund expenses embedded in prices",
                "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "official_reference": "https://www.ssga.com/us/en/intermediary/etfs/state-street-bridgewater-all-weather-etf-allw",
                "role": "Descriptive overlap only; excluded from candidate selection",
                "limitations": [
                    "Short sample; annualized statistics are unstable.",
                    "ALLW uses derivatives and differing exposure; this is not risk-matched.",
                    "Existing candidates enter overlap with established holdings; ALLW entry cost is included.",
                    "Actual ALLW is not Bridgewater private-fund performance.",
                ],
            },
            indent=2,
        )
    )
    print(
        table[
            [
                "model",
                "start",
                "end",
                "total_return",
                "cagr",
                "volatility",
                "max_drawdown",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
