"""Exact-design retrospective dynamic replay; no promotion or forward evidence."""

import argparse
from pathlib import Path
import numpy as np
import pandas as pd

from dynamic_portfolio import allocate, VERSION
from evaluate_institutional_engines import Replay
from institutional_return_engines import validate_weights
from compare_portfolio_models import rebalance_fee
from growth_resilience import metrics
from portfolio_contract import extended_prices
from strategy_integrity import strict_json, file_hash
from strategy_receipts import atomic_json
from strategy_report import load_training_report


def replay_dynamic(prices, features, *, start=253, cost=0.0015):
    if not 253 <= start < len(prices) or not 0 <= cost <= 0.01:
        raise ValueError("Observed warmup and valid cost required")
    runner = Replay(prices, features)
    symbols = list(prices)
    daily = prices.pct_change(fill_method=None)
    w = np.zeros(len(symbols))
    nav = peak = 1.0
    rows, trades = [], []
    for i in range(start, len(prices)):
        ctx = runner.ctx(i - 1)
        active = [symbols.index(s) for s in ctx["symbols"]]
        urgent = not validate_weights(w[active], "economic_balance", ctx)
        urgent |= any(
            w[j] > 1e-12 for j, s in enumerate(symbols) if s not in ctx["symbols"]
        )
        target = None
        if (i - start) % 21 == 0 or urgent:
            candidate = allocate(ctx)
            desired = np.array([candidate["weights"].get(s, 0) for s in symbols])
            if urgent or i == start or abs(desired - w).sum() >= 0.04:
                target = desired
        # Held positions receive fill-day returns before the prior decision fills.
        r = daily.iloc[i].to_numpy()
        held = w > 0
        if not np.isfinite(r[held]).all() or (r[held] <= -1).any():
            raise ValueError("Missing held price or insolvent instrument")
        old = nav
        gain = 1 + float(w[held] @ r[held])
        if gain <= 0:
            raise ValueError("Insolvent portfolio")
        nav *= gain
        w[held] *= (1 + r[held]) / gain
        fee = turnover = 0.0
        if target is not None:
            fee = rebalance_fee(w, target, cost)
            turnover = float(abs(target * (1 - fee) - w).sum())
            nav *= 1 - fee
            w = target
            trades.append(
                dict(
                    decision_session=ctx["decision_session"],
                    fill_session=str(prices.index[i].date()),
                    weights=dict(zip(symbols, map(float, w))),
                    cash=float(1 - w.sum()),
                    fee=fee,
                    urgent=bool(urgent),
                )
            )
        peak = max(peak, nav)
        rows.append(
            dict(
                date=prices.index[i],
                equity=nav,
                **{"return": nav / old - 1},
                drawdown=nav / peak - 1,
                turnover=turnover,
                cash=float(1 - w.sum()),
                regime=ctx["regime"],
                macro_valid=ctx["macro_valid"],
            )
        )
    return pd.DataFrame(rows).set_index("date"), trades


def evaluate(bundle, output):
    b = strict_json(bundle)
    report = load_training_report(b["training_report"])
    if not report["current_numerical_source_match"]:
        raise ValueError("Source-matched verified report required")
    prices = extended_prices(b["capture"], b["benchmark_extension"]).drop(
        columns=["XLV"]
    )
    features = {
        r["date"]: r
        for r in strict_json(Path(b["training_report"]).parent / "features.json")
    }
    start = max(253, prices.index.searchsorted(pd.Timestamp("2011-01-04")))
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    frames = {}
    for cost in (0.0, 0.0015, 0.003):
        frame, trades = replay_dynamic(prices, features, start=start, cost=cost)
        key = str(round(cost * 10000)) + "bps"
        path = root / (key + ".csv")
        frame.to_csv(path)
        atomic_json(root / (key + "-trades.json"), trades)
        frames[key] = frame

    def score(frame):
        return metrics(
            frame.equity.to_numpy(),
            frame["return"].to_numpy(),
            frame.turnover.to_numpy(),
        )

    base = frames["15bps"]
    result = dict(
        version=VERSION,
        status="RETROSPECTIVE_DYNAMIC_REPLAY_ONLY",
        start=str(base.index[0].date()),
        end=str(base.index[-1].date()),
        metrics={k: score(f) for k, f in frames.items()},
        regime_sessions=base.regime.value_counts().to_dict(),
        degraded_sessions=int((~base.macro_valid).sum()),
        execution_enabled=False,
        release_approved=False,
        warning="Design chosen after history existed; not untouched or prospective validation. No client fees/taxes/verified execution costs. Independent acceptance remains open.",
        source_hashes={
            p: file_hash(p)
            for p in (
                str(bundle),
                __file__,
                "dynamic_portfolio.py",
                "institutional_return_engines.py",
                "evaluate_institutional_engines.py",
            )
        },
        artifacts={p.name: file_hash(p) for p in root.iterdir() if p.is_file()},
    )
    atomic_json(root / "assessment.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle", default="var/investor-dashboard/latest-strategy-run.json"
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(evaluate(args.bundle, args.output))
