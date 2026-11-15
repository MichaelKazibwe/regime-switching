"""Predeclared retrospective walk-forward replay; separate from paper incumbents."""

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
from compare_portfolio_models import rebalance_fee
from institutional_return_engines import (
    context,
    proposal,
    validate_weights,
    limits,
    NAMES,
    VERSION,
    PROTOCOL,
    write_protocol,
)
from growth_resilience import metrics
from portfolio_contract import extended_prices
from strategy_report import load_training_report
from strategy_integrity import file_hash
from strategy_receipts import atomic_json
from economic_design_assessment import replay, paired_interval


class Replay:
    def __init__(self, prices, features):
        self.prices = prices
        self.features = features
        self.daily = prices.pct_change(fill_method=None)
        self.closes = (
            mcal.get_calendar("NYSE")
            .schedule(prices.index[0], prices.index[-1])
            .market_close
        )
        self.contexts = {}
        self.targets = {}

    def ctx(self, i):
        if i not in self.contexts:
            self.contexts[i] = context(
                self.prices, i, self.features, decision_time=self.closes.iloc[i]
            )
        return self.contexts[i]

    def target(self, i, name):
        if (i, name) not in self.targets:
            self.targets[i, name] = proposal(name, self.ctx(i))
        return self.targets[i, name]

    def run(self, start, end, *, cost=0.0015):
        cols = list(self.prices)
        ids = {s: i for i, s in enumerate(cols)}
        frames = {}
        audits = {}
        for name in NAMES:
            w = np.zeros(len(cols))
            nav = peak = 1.0
            rows = []
            trades = []
            counts = Counter()
            for i in range(start, end + 1):
                # Decide from prior-close weights and data, before observing the fill-day return.
                decision = i - 1
                ctx = self.ctx(decision)
                active = [ids[s] for s in ctx["symbols"]]
                current = w[active]
                ceiling, exposure = limits(name, ctx)
                variance = float(current @ ctx["cov"] @ current)
                rc = (
                    current * (ctx["cov"] @ current) / variance
                    if variance > 1e-15
                    else np.zeros(len(active))
                )
                urgent = (
                    w.sum() > exposure + 0.01
                    or w.max(initial=0) > 0.26
                    or variance > (ceiling * 1.10) ** 2
                    or rc.max(initial=0) > 0.30
                )
                scheduled = (i - start) % 21 == 0
                target = None
                status = None
                if scheduled or urgent:
                    result = self.target(decision, name)
                    status = result["status"]
                    counts[status] += 1
                    candidate = np.array([result["weights"].get(s, 0.0) for s in cols])
                    if (
                        urgent
                        or i == start
                        or abs(candidate - w).sum()
                        >= PROTOCOL["discretionary_trade_band"]
                    ):
                        target = candidate
                        if not urgent and i > start:
                            half = (w + candidate) / 2
                            if (
                                validate_weights(half[active], name, ctx)
                                and sum(
                                    half[j]
                                    for j, symbol in enumerate(cols)
                                    if symbol not in ctx["symbols"]
                                )
                                < 1e-12
                            ):
                                target = half
                    else:
                        counts["DISCRETIONARY_NO_TRADE_BAND"] += 1
                # Existing positions earn the observed return; the frozen decision then fills at this close.
                r = self.daily.iloc[i].to_numpy()
                held = w > 0
                if not np.isfinite(r[held]).all() or (r[held] <= -1).any():
                    raise ValueError("Held price missing; no invented return")
                old = nav
                gross = float(w[held] @ r[held])
                gain = 1 + gross
                if gain <= 0:
                    raise ValueError("Insolvent account")
                nav *= gain
                w[held] *= (1 + r[held]) / gain
                fee = turn = 0.0
                if target is not None:
                    fee = rebalance_fee(w, target, cost)
                    turn = float(abs(target * (1 - fee) - w).sum())
                    nav *= 1 - fee
                    w = target
                    trades.append(
                        {
                            "date": str(self.prices.index[i].date()),
                            "decision_session": ctx["decision_session"],
                            "mode": ctx["regime"],
                            "urgent": bool(urgent),
                            "weights": dict(zip(cols, map(float, w))),
                            "cash": float(1 - w.sum()),
                            "fee_fraction": fee,
                            "status": status,
                        }
                    )
                peak = max(peak, nav)
                rows.append(
                    {
                        "date": self.prices.index[i],
                        "return": nav / old - 1,
                        "equity": nav,
                        "gross_return": gross,
                        "cash": float(1 - w.sum()),
                        "turnover": turn,
                        "cost_as_initial_capital": old * gain * fee,
                        "drawdown": nav / peak - 1,
                        "regime": ctx["regime"],
                        "macro_valid": ctx["macro_valid"],
                    }
                )
            frames[name] = pd.DataFrame(rows).set_index("date")
            audits[name] = {"counts": dict(counts), "trades": trades}
            print(f"Replayed {name}, {len(rows)} sessions, cost {cost:.1%}", flush=True)
        return frames, audits


def run(bundle, output):
    bundle = Path(bundle)
    b = json.loads(bundle.read_text())
    report = load_training_report(b["training_report"])
    if not report["current_numerical_source_match"]:
        raise ValueError("Source-matched market/macro report required")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    protocol = write_protocol(root / "protocol.json")
    prices = extended_prices(b["capture"], b["benchmark_extension"]).drop(
        columns=["XLV"]
    )
    features = {
        r["date"]: r
        for r in json.loads(
            (Path(b["training_report"]).parent / "features.json").read_text()
        )
    }
    replay_engine = Replay(prices, features)
    start = prices.index.searchsorted(pd.Timestamp("2011-01-04"))
    end = len(prices) - 1
    protocol["evaluation"] = {
        "start": str(prices.index[start].date()),
        "end": str(prices.index[end].date()),
        "design_declared_at": datetime.now(timezone.utc).isoformat(),
        "parameter_search": False,
        "windows": [
            ["2011", "2015"],
            ["2016", "2019"],
            ["2020", "2022"],
            ["2023", "2024"],
            ["2025", "2026"],
        ],
        "warning": "Design was chosen after historical data existed. All historical windows, including the reused latest year, are retrospective, not untouched validation.",
    }
    atomic_json(root / "protocol.json", protocol)
    base, audits = replay_engine.run(start, end)
    references = {
        "SPY": {"SPY": 1.0},
        "60_40": {"SPY": 0.6, "IEF": 0.4},
        "All_Weather_style": {
            "SPY": 0.3,
            "TLT": 0.4,
            "IEF": 0.15,
            "GLD": 0.075,
            "DBC": 0.075,
        },
    }
    obs = replay_engine.daily.iloc[start : end + 1]
    ref_frames = {}
    for key, weights in references.items():
        ref_frames[key] = replay(
            obs, {date: weights for date in obs.index[::21]}, cost_rate=0.0015
        )

    def score(f):
        return metrics(
            f.equity.to_numpy(), f["return"].to_numpy(), f["turnover"].to_numpy()
        )

    results = []
    for name, f in base.items():
        f.to_csv(root / f"{name}.csv")
        atomic_json(root / f"{name}-audit.json", audits[name])
        windows = {}
        for a, z in protocol["evaluation"]["windows"]:
            selected = f.loc[a:z].copy()
            if len(selected) > 1:
                selected["equity"] = (1 + selected["return"]).cumprod()
                windows[f"{a}-{z}"] = score(selected)
        attribution = {}
        for regime, g in f.groupby("regime"):
            attribution[regime] = {
                "sessions": len(g),
                "mean_daily_return": float(g["return"].mean()),
                "positive_session_frequency": float((g["return"] > 0).mean()),
                "note": "Non-contiguous conditional observations, not a tradable regime portfolio CAGR.",
            }
        results.append(
            {
                "name": name,
                "metrics": score(f),
                "windows": windows,
                "regimes": attribution,
                "diagnostics": audits[name]["counts"],
                "paired_60_40_intervals": [
                    paired_interval(f["return"], ref_frames["60_40"]["return"], block=x)
                    for x in [21, 63]
                ],
            }
        )
    reset_start = prices.index.get_loc(pd.Timestamp(report["evaluation"]["start"]))
    cost_sens = {}
    for cost in [0.0, 0.0015, 0.003]:
        frames, _ = replay_engine.run(reset_start, end, cost=cost)
        cost_sens[str(cost)] = {n: score(f) for n, f in frames.items()}
    for row in results:
        row["latest_year_reset"] = cost_sens["0.0015"][row["name"]]
        row["incumbent_latest_year"] = next(
            x["metrics"] for x in report["strategies"] if x["name"] == row["name"]
        )
        row["cost_sensitivity_latest_year"] = {
            k: v[row["name"]] for k, v in cost_sens.items()
        }
        row["candidate"] = proposal(row["name"], replay_engine.ctx(end))
    result = {
        "schema_version": 1,
        "version": VERSION,
        "status": "RETROSPECTIVE_UNAPPROVED_RETURN_ENGINE_CANDIDATES",
        "market_session": str(prices.index[-1].date()),
        "protocol": protocol,
        "strategies": results,
        "references": {n: score(f) for n, f in ref_frames.items()},
        "inputs": {
            "bundle_sha256": file_hash(bundle),
            "report_sha256": file_hash(b["training_report"]),
        },
        "source_hashes": {
            p: file_hash(p)
            for p in [
                "institutional_return_engines.py",
                __file__,
                "institutionalportfolio.py",
                "compare_portfolio_models.py",
            ]
        },
        "execution_enabled": False,
        "promotion_enabled": False,
        "public_recommendations_enabled": False,
        "limitations": [
            "Institutional-method adaptation, not a proprietary strategy replica or verified return forecast.",
            "No shorting/leverage; no historical pre-inception ETF filling. ETF histories and universe selection are retrospective.",
            "Macro-unavailable periods use this separately declared market-only degraded design; incumbent fail-closed cohorts remain untouched.",
            "No verified investor fees, taxes, duration/FX or instrument access evidence; deposit cash earns zero. Reserve ETFs are traded instruments, not deposit cash.",
            "Historical positive returns do not establish future profitability. New prospective registration and independent review remain required.",
        ],
    }
    if file_hash("institutional_return_engines.py") != protocol["code_sha256"]:
        raise ValueError("Engine code changed during evaluation")
    atomic_json(root / "assessment.json", result)
    print(
        "\nEngine                       CAGR       Vol        Max DD     Latest year / incumbent",
        flush=True,
    )
    for r in results:
        print(
            f"{r['name']:27s} {r['metrics']['cagr']:9.2%} {r['metrics']['annual_volatility']:9.2%} {r['metrics']['maximum_drawdown']:10.2%} {r['latest_year_reset']['total_return']:9.2%} / {r['incumbent_latest_year']['total_return']:7.2%}",
            flush=True,
        )
    return result


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--bundle", default="var/investor-dashboard/latest-strategy-run.json"
    )
    p.add_argument("--output", default="var/institutional-return-engines/v1")
    a = p.parse_args()
    run(a.bundle, a.output)
