"""Export per-regime reliability and every candidate's capital and risk weights."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from strategy_integrity import strict_json, file_hash
from strategy_receipts import atomic_json


def reliability_by_regime(probabilities, actual):
    p, y = np.asarray(probabilities, float), np.asarray(actual, int)
    if (p.shape != (len(y), 4) or not len(y) or not np.isfinite(p).all()
            or (p < 0).any() or not np.allclose(p.sum(axis=1), 1)):
        raise ValueError("Four-class probabilities and outcomes required")
    result = {}
    for k in range(4):
        bins = []
        for low, high in zip(np.arange(0, 1, 0.2), np.arange(0.2, 1.21, 0.2)):
            mask = (p[:, k] >= low) & (p[:, k] < high if high < 1 else p[:, k] <= 1)
            if mask.any():
                bins.append(dict(low=float(low), high=float(min(high, 1)),
                                 count=int(mask.sum()),
                                 mean_probability=float(p[mask, k].mean()),
                                 observed_frequency=float((y[mask] == k).mean())))
        result[str(k)] = dict(count=len(y), actual_count=int((y == k).sum()), bins=bins)
    return result


def run(assessment, output, *, forecast_path=None):
    assessment, root = Path(assessment).resolve(), Path(output).resolve()
    study = strict_json(assessment)
    if (study["status"] != "COMPLETED_RESEARCH_ONLY"
            or any(file_hash(p) != h for p, h in study["source_hashes"].items())):
        raise ValueError("Completed source-matched study required")
    for name, digest in study["artifacts"].items():
        if Path(name).name != name or file_hash(assessment.parent / name) != digest:
            raise ValueError("Study artifact mismatch")
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    forecast = strict_json(forecast_path) if forecast_path else study["forecast"]
    if forecast_path and (
            forecast["status"] != "COMPLETED_FIXED_CALENDAR_RESEARCH"
            or forecast["bundle_sha256"] != study["bundle_sha256"]
            or any(file_hash(p) != h for p, h in forecast["source_hashes"].items())):
        raise ValueError("Source-matched fixed-calendar forecast evidence required")
    test = forecast["historical_test"]
    reliability = reliability_by_regime(test["probabilities"], test["actual"])
    atomic_json(root / "regime-reliability.json", reliability)
    weights, groups = [], []
    for strategy, record in study["portfolios"].items():
        for variant, candidate in record["latest_candidates"].items():
            for symbol, weight in {**candidate["weights"], "USD_CASH": candidate["cash"]}.items():
                row = dict(strategy=strategy, variant=variant, symbol=symbol,
                           capital_weight=weight, candidate_status=candidate["status"],
                           market_session=study["market_session"])
                for model, diagnostic in candidate["diagnostics"].items():
                    row[model + "_signed_risk_share"] = diagnostic["asset_risk"].get(symbol, 0)
                    row[model + "_volatility"] = diagnostic["volatility"]
                weights.append(row)
            for model, diagnostic in candidate["diagnostics"].items():
                for group, positive in diagnostic["positive_group_risk"].items():
                    groups.append(dict(strategy=strategy, variant=variant, covariance=model,
                                       group=group, positive_risk_share=positive,
                                       signed_risk_share=diagnostic["signed_group_risk"][group]))
    pd.DataFrame(weights).to_csv(root / "capital-and-risk-weights.csv", index=False)
    pd.DataFrame(groups).to_csv(root / "group-risk-weights.csv", index=False)
    result = dict(status="COMPLETED_DIAGNOSTIC_EXPORTS", assessment_sha256=file_hash(assessment),
                  forecast_sha256=file_hash(forecast_path) if forecast_path else None,
                  source_sha256=file_hash(__file__), capital_weight_rows=len(weights),
                  group_risk_rows=len(groups), prospective_performance_claim=False,
                  execution_enabled=False, promotion_enabled=False,
                  artifacts={p.name: file_hash(p) for p in root.iterdir() if p.is_file()})
    atomic_json(root / "assessment.json", result)
    print("Per-regime reliability and capital/group risk weights:", root, flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--forecast", type=Path)
    args = parser.parse_args()
    run(args.assessment, args.output, forecast_path=args.forecast)
