"""Independent trade replay and ex-ante risk-matched diagnostics for challengers."""

from pathlib import Path
import json
import numpy as np
import pandas as pd
from evaluate_institutional_engines import Replay
from economic_design_assessment import replay, paired_interval
from growth_resilience import metrics
from portfolio_contract import extended_prices
from strategy_integrity import file_hash
from strategy_receipts import atomic_json


def assess(assessment, bundle, output):
    assessment = Path(assessment)
    a = json.loads(assessment.read_text())
    b = json.loads(Path(bundle).read_text())
    if (
        any(file_hash(p) != h for p, h in a["source_hashes"].items())
        or file_hash(bundle) != a["inputs"]["bundle_sha256"]
    ):
        raise ValueError("Frozen challenger sources or bundle changed")
    prices = extended_prices(b["capture"], b["benchmark_extension"]).drop(
        columns=["XLV"]
    )
    features = {
        r["date"]: r
        for r in json.loads(
            (Path(b["training_report"]).parent / "features.json").read_text()
        )
    }
    engine = Replay(prices, features)
    rows = []
    hashes = {str(assessment): file_hash(assessment)}
    for s in a["strategies"]:
        p = assessment.parent / f"{s['name']}.csv"
        q = assessment.parent / f"{s['name']}-audit.json"
        f = pd.read_csv(p, index_col=0, parse_dates=True)
        trades = json.loads(q.read_text())["trades"]
        targets = {pd.Timestamp(t["date"]): t["weights"] for t in trades}
        for t in trades:
            if t["decision_session"] >= t["date"]:
                raise ValueError("Same-close trade timing")
        observed = engine.daily.loc[f.index]
        replica = replay(observed, targets, cost_rate=0.0015, protect=False)
        if not np.allclose(replica["return"], f["return"], atol=1e-10, rtol=0):
            raise ValueError("Challenger trade path fails independent replay")
        matched = {}
        for t in trades:
            date = pd.Timestamp(t["date"])
            i = prices.index.get_loc(pd.Timestamp(t["decision_session"]))
            ctx = engine.ctx(i)
            w = np.array([t["weights"].get(s, 0.0) for s in ctx["symbols"]])
            base = np.array(
                [
                    0.6 if s == "SPY" else 0.4 if s == "IEF" else 0.0
                    for s in ctx["symbols"]
                ]
            )
            sigma = float(np.sqrt(w @ ctx["cov"] @ w))
            bs = float(np.sqrt(base @ ctx["cov"] @ base))
            scale = min(0.95, sigma / bs)
            matched[date] = {"SPY": 0.6 * scale, "IEF": 0.4 * scale}
        reference = replay(observed, matched, cost_rate=0.0015, protect=False)
        refmetrics = metrics(
            reference.equity.to_numpy(),
            reference["return"].to_numpy(),
            reference.turnover.to_numpy(),
        )
        intervals = [
            paired_interval(f["return"], reference["return"], block=block)
            for block in [21, 63]
        ]
        episodes = {}
        for name, start, end in [
            ("euro_debt_2011", "2011-07-01", "2011-10-31"),
            ("tightening_2018", "2018-10-01", "2018-12-31"),
            ("covid_crash", "2020-02-19", "2020-03-23"),
            ("covid_recovery", "2020-03-24", "2020-12-31"),
            ("inflation_2022", "2022-01-01", "2022-12-31"),
        ]:
            x = f.loc[start:end]
            curve = (1 + x["return"]).cumprod().to_numpy()
            episodes[name] = metrics(curve, x["return"].to_numpy())
        rows.append(
            {
                "name": s["name"],
                "trade_replay_reconciled": True,
                "risk_matched_60_40": refmetrics,
                "paired_intervals": intervals,
                "robust_positive_lower_bound": all(i["p025"] > 0 for i in intervals),
                "episodes": episodes,
            }
        )
        hashes.update({str(p): file_hash(p), str(q): file_hash(q)})
    result = {
        "schema_version": 1,
        "assessment": str(assessment.resolve()),
        "assessment_sha256": file_hash(assessment),
        "source_artifacts": hashes,
        "strategies": rows,
        "promotion_enabled": False,
        "execution_enabled": False,
        "interpretation": "Ex-ante risk match uses calibrated covariance ending at the prior decision close and the challenger target/trade dates. This is a descriptive control, not an independently tradable strategy or adjusted significance test.",
    }
    atomic_json(output, result)
    for r in rows:
        print(
            r["name"],
            "reconciled; matched 60/40 CAGR",
            f"{r['risk_matched_60_40']['cagr']:.2%}",
            "positive lower bound",
            r["robust_positive_lower_bound"],
            flush=True,
        )
    return result


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--assessment",
        default="var/institutional-return-engines/v1-validated/assessment.json",
    )
    p.add_argument(
        "--bundle", default="var/investor-dashboard/latest-strategy-run.json"
    )
    p.add_argument(
        "--output",
        default="var/institutional-return-engines/v1-validated/robustness.json",
    )
    a = p.parse_args()
    assess(a.assessment, a.bundle, a.output)
