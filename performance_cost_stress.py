"""All-trial cost stress with frozen decisions, independent of trial selection."""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import numpy as np

from economic_design_assessment import replay
from performance_portfolios import VARIANTS, summarize
from institutional_return_engines import NAMES
from portfolio_contract import extended_prices
from strategy_integrity import file_hash, strict_json
from strategy_receipts import atomic_json


def run(assessment, output, *, bundle_path=None):
    assessment, root = Path(assessment).resolve(), Path(output).resolve()
    study = strict_json(assessment)
    if (study["status"] != "COMPLETED_RESEARCH_ONLY"
            or any(file_hash(p) != h for p, h in study["source_hashes"].items())):
        raise ValueError("Completed source-matched study required")
    for name, digest in study["artifacts"].items():
        if Path(name).name != name or file_hash(assessment.parent / name) != digest:
            raise ValueError("Study artifact mismatch")
    bundle = Path(bundle_path) if bundle_path else Path(
        strict_json("var/dashboard-live/latest.json")["bundle"])
    if file_hash(bundle) != study["bundle_sha256"]:
        raise ValueError("Use the same captured bundle for cost stress")
    b = strict_json(bundle)
    prices = extended_prices(b["capture"], b["benchmark_extension"]).drop(columns=["XLV"])
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    protocol = dict(version="ALL_TRIAL_FROZEN_DECISION_COST_STRESS_V1",
                    declared_at=datetime.now(timezone.utc).isoformat(),
                    assessment_sha256=file_hash(assessment), source_sha256=file_hash(__file__),
                    cost_rates=[0.0, 0.0015, 0.003], trials=list(VARIANTS),
                    design="Hold every dated decision fixed; isolate transaction-cost effects. No selection on these results.",
                    execution_enabled=False, promotion_enabled=False)
    atomic_json(root / "protocol.json", protocol)
    results = {}
    for name in NAMES:
        results[name] = {}
        for variant in VARIANTS:
            original = pd.read_csv(assessment.parent / f"{name}-{variant}-15bps.csv",
                                   index_col=0, parse_dates=True)
            trades = strict_json(assessment.parent / f"{name}-{variant}-trades.json")
            targets = {pd.Timestamp(t["date"]): t["weights"] for t in trades}
            if any(t["decision_session"] >= t["date"] for t in trades):
                raise ValueError("Every decision must predate its fill")
            values = {}
            for rate in protocol["cost_rates"]:
                frame = replay(prices.pct_change(fill_method=None).loc[original.index],
                               targets, cost_rate=rate)
                frame["filled"] = frame.index.isin(targets)
                if rate == 0.0015 and not np.allclose(frame.equity, original.equity,
                                                     rtol=1e-9, atol=1e-10):
                    raise ValueError("Frozen-decision reference does not reconcile")
                frame.to_csv(root / f"{name}-{variant}-{rate}.csv")
                values[str(rate)] = summarize(frame)
            if not (values["0.0"]["total_return"] >= values["0.0015"]["total_return"]
                    >= values["0.003"]["total_return"]):
                raise ValueError("Fixed-decision cost monotonicity failed")
            results[name][variant] = values
    result = dict(status="COMPLETED_FROZEN_DECISION_COST_STRESS", protocol=protocol,
                  results=results, execution_enabled=False, promotion_enabled=False,
                  artifacts={p.name: file_hash(p) for p in root.iterdir() if p.is_file()})
    atomic_json(root / "assessment.json", result)
    print("All 32 strategy/design combinations stressed at 0, 15 and 30 bps:", root, flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    run(args.assessment, args.output, bundle_path=args.bundle)
