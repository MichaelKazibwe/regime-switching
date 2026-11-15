"""Finite P1 study: candidates, matched costs, macro calibration and data lineage."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

from evaluate_institutional_engines import Replay
from institutional_return_engines import NAMES
from resilient_candidate import propose, VARIANTS
from portfolio_contract import extended_prices
from growth_resilience import metrics
from economic_design_assessment import replay, paired_interval
from economic_evidence import verify
from forecast_calibration import study
from market_quality import review
from strategy_report import load_training_report
from strategy_receipts import atomic_json
from strategy_integrity import strict_json, file_hash


class CandidateReplay(Replay):
    def __init__(self, prices, features, variants):
        super().__init__(prices, features)
        self.variants = variants

    def target(self, i, name):
        if (i, name) not in self.targets:
            self.targets[i, name] = propose(
                name,
                self.ctx(i),
                self.daily.iloc[max(1, i - 251) : i + 1],
                self.variants[name],
            )
        return self.targets[i, name]


def score(frame):
    r = frame["return"].to_numpy()
    curve = np.cumprod(1 + r)
    opening = float(frame.equity.iloc[0] / (1 + r[0]))
    return {
        **metrics(curve, r, frame["turnover"].to_numpy()),
        "mean_cash": float(frame.cash.mean()),
        "cost_as_initial_capital": float(frame.cost_as_initial_capital.sum() / opening),
        "cash_exposure_times_hypothetical_2pct_not_replay": float(
            frame.cash.mean() * 0.02
        ),
        "cash_exposure_times_hypothetical_4pct_not_replay": float(
            frame.cash.mean() * 0.04
        ),
    }


def run(bundle, output):
    bundle = Path(bundle)
    b = strict_json(bundle)
    report = load_training_report(b["training_report"])
    if not report["current_numerical_source_match"]:
        raise ValueError("Source-matched training required")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    protocol = dict(
        version="P1_FINITE_STUDY_V1",
        declared_at=datetime.now(timezone.utc).isoformat(),
        variants=VARIANTS,
        selection="Validation CAGR minus half variance minus 0.2 times drawdown magnitude; test unused for selection",
        validation_sessions=252,
        test_sessions=252,
        cost_rates=[0.0, 0.0015, 0.003],
        universe="26 core ETFs plus DBMF; ALLW comparison only; no pre-inception filling",
        promotion_enabled=False,
        execution_enabled=False,
        limitation="Design follows previously inspected history; chronological retrospective evidence, not untouched or prospective validation.",
    )
    atomic_json(root / "protocol.json", protocol)
    prices = extended_prices(b["capture"], b["benchmark_extension"]).drop(
        columns=["XLV"]
    )
    features_list = strict_json(Path(b["training_report"]).parent / "features.json")
    features = {r["date"]: r for r in features_list}
    end = len(prices) - 1
    start = max(253, len(prices) - 1260)
    reference_model = Replay(prices, features)
    incumbent, incumbent_audit = reference_model.run(start, end)
    atomic_json(root / "incumbent-trades.json", incumbent_audit)
    frames = {"incumbent": incumbent}
    audits = {}
    for variant in VARIANTS:
        model = CandidateReplay(prices, features, dict.fromkeys(NAMES, variant))
        model.contexts = reference_model.contexts
        frames[variant], audits[variant] = model.run(start, end)
        atomic_json(root / f"{variant}-trades.json", audits[variant])
    rows = []
    selected = {}
    for name in NAMES:
        candidates = []
        for variant, group in frames.items():
            frame = group[name]
            frame.to_csv(root / f"{name}-{variant}.csv")
            validation = score(frame.iloc[-504:-252])
            test = score(frame.iloc[-252:])
            candidates.append(dict(variant=variant, validation=validation, test=test))
        # Include unchanged incumbent as the default; ties favor it.
        pick = max(
            candidates,
            key=lambda r: (
                r["validation"]["cagr"]
                - 0.5 * r["validation"]["annual_volatility"] ** 2
                + 0.2 * r["validation"]["maximum_drawdown"]
            ),
        )
        selected[name] = pick["variant"]
        chosen = frames[pick["variant"]][name]
        references = {}
        obs = prices.pct_change(fill_method=None).loc[chosen.index]
        for key, w in dict(
            balanced={"SPY": 0.6, "IEF": 0.4},
            all_weather={
                "SPY": 0.3,
                "TLT": 0.4,
                "IEF": 0.15,
                "GLD": 0.075,
                "DBC": 0.075,
            },
        ).items():
            ref = replay(obs, {d: w for d in obs.index[::21]}, cost_rate=0.0015)
            reference = metrics(
                ref.equity.to_numpy(), ref["return"].to_numpy(), ref.turnover.to_numpy()
            )
            references[key] = dict(
                metrics=reference,
                test_paired_interval=paired_interval(
                    chosen["return"].iloc[-252:],
                    ref["return"].iloc[-252:],
                ),
            )
        rows.append(
            dict(
                name=name,
                selection=pick["variant"],
                selected_full_history=score(chosen),
                trials=candidates,
                references=references,
                regimes={
                    g: dict(
                        sessions=len(f),
                        mean_daily_return=float(f["return"].mean()),
                        annualized_volatility=float(f["return"].std() * np.sqrt(252)),
                    )
                    for g, f in chosen.groupby("regime")
                    if len(f) > 1
                },
                latest_weights=(
                    (
                        incumbent_audit
                        if pick["variant"] == "incumbent"
                        else audits[pick["variant"]]
                    )
                    .get(name, {})
                    .get("trades")
                    or [{}]
                )[-1].get("weights"),
                promotion_enabled=False,
            )
        )

    # Re-run every selected design under identical higher/lower costs, retaining all trials.
    class SelectedReplay(CandidateReplay):
        def target(self, i, name):
            return (
                Replay.target(self, i, name)
                if self.variants[name] == "incumbent"
                else super().target(i, name)
            )

    sensitivity = {}
    selected_model = SelectedReplay(prices, features, selected)
    selected_model.contexts = reference_model.contexts
    for cost in (0.0, 0.003):
        result, cost_audit = selected_model.run(start, end, cost=cost)
        atomic_json(root / f"selected-cost-{cost}-trades.json", cost_audit)
        for name, frame in result.items():
            frame.to_csv(root / f"selected-{name}-cost-{cost}.csv")
        sensitivity[str(cost)] = {n: score(f.iloc[-252:]) for n, f in result.items()}
    settings = strict_json("research/four_macro_strategies.json")["macro_forecast"]
    calibration = study(features_list, settings)
    old = strict_json("var/investor-dashboard/latest-strategy-run.json")["capture"]
    quality = review(b["capture"], old)
    evidence = verify(None, list(prices), prices.index)
    result = dict(
        status="COMPLETED_REVIEW_ONLY",
        protocol=protocol,
        strategies=rows,
        cost_sensitivity=sensitivity,
        calibration=calibration,
        data_quality=quality,
        financial_evidence=evidence,
        source_hashes={
            p: file_hash(p)
            for p in (
                __file__,
                "resilient_candidate.py",
                "forecast_calibration.py",
                "portfolio_risk_envelope.py",
                "market_quality.py",
                "institutional_return_engines.py",
                "evaluate_institutional_engines.py",
                "portfolio_contract.py",
                "growth_resilience.py",
                "economic_design_assessment.py",
                "economic_evidence.py",
                "live_strategy_training.py",
                "research/four_macro_strategies.json",
                "compare_portfolio_models.py",
                "institutionalportfolio.py",
            )
        },
        bundle_sha256=file_hash(bundle),
        artifacts={p.name: file_hash(p) for p in root.iterdir() if p.is_file()},
        promotion_enabled=False,
        execution_enabled=False,
        evidence_gaps=[
            "No independent provider capture",
            "No verified cash/cost/holdings/FX/liquidity evidence",
            "No matured quarterly prospective calibration",
            "No customer deployment approval",
        ],
    )
    atomic_json(root / "assessment.json", result)
    for row in rows:
        trial = next(t for t in row["trials"] if t["variant"] == row["selection"])
        print(row["name"], row["selection"], "test", trial["test"], flush=True)
    print("P1 study:", root / "assessment.json", flush=True)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    run(a.bundle, a.output)
