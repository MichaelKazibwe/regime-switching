"""Fresh-data shadow training and frozen chronological evaluation of four strategies.

Fixed strategy risk maps are preserved. Only the shared regime classifier is
fitted; risk estimates use past observations. No investor state or orders.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from assetuniverse import DIVERSIFIED_ASSETS
from compare_portfolio_models import metrics, rebalance_fee
from diversifiedregimepolicy import AllocationError
from fourregimestrategies import (
    FEATURES,
    FourMacroStrategies,
    quadrant,
    strategy_proposal,
)
from fourstrategysimulation import simulate_strategy
from goalportfolio import AccountDrawdownGuard
from institutionalportfolio import calibrated_covariance
from productreport import private_write
from smartregimeportfolio import SmartRegimePortfolio
from training_macro import TrainingMacro
from strategy_training_data import validate_prices

SOURCES = (
    "live_strategy_training.py",
    "strategy_training_data.py",
    "training_macro.py",
    "macro_feature_contract.py",
    "assetuniverse.py",
    "fourregimestrategies.py",
    "fourstrategysimulation.py",
    "smartregimeportfolio.py",
    "institutionalportfolio.py",
    "goalportfolio.py",
    "portfolio_objectives.py",
    "macrovintage.py",
    "compare_portfolio_models.py",
    "diversifiedregimepolicy.py",
    "research/four_macro_strategies.json",
    "research/smart_regime_portfolio_v3.json",
)


def fit_classifier(features, decision_index, settings):
    """All target outcomes strictly precede the freeze; scaler sees training X only."""
    horizon = settings["horizon_sessions"]
    stop = decision_index - horizon
    ids = np.arange(max(0, stop - settings["training_sessions"]), max(0, stop))
    ids = np.array(
        [
            i
            for i in ids
            if features[i].get("macro_valid", True)
            and features[i + horizon].get("macro_valid", True)
        ],
        dtype=int,
    )
    x = np.array([[r[k] for k in FEATURES] for r in features], dtype=float)
    valid = [i for i, r in enumerate(features) if r.get("macro_valid", True)]
    if not np.isfinite(x[valid]).all():
        raise ValueError("Nonfinite classifier features")
    target = np.array([quadrant(features[i + horizon]) for i in ids], dtype=int)
    baseline = (np.bincount(target, minlength=4) + 1) / (len(target) + 4)
    model = None
    if len(ids) >= settings["minimum_training"] and len(np.unique(target)) >= 2:
        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=settings["regularization_C"], max_iter=1000),
        )
        model.fit(x[ids], target)
    metadata = {
        "training_examples": len(ids),
        "horizon_sessions": horizon,
        "freeze_date": features[decision_index]["date"],
        "first_training_feature_date": features[ids[0]]["date"] if len(ids) else None,
        "last_training_feature_date": features[ids[-1]]["date"] if len(ids) else None,
        "last_training_label_date": features[ids[-1] + horizon]["date"]
        if len(ids)
        else None,
        "baseline": baseline.tolist(),
        "feature_names": list(FEATURES),
        "trained": model is not None,
    }
    if model:
        metadata.update(
            scaler_mean=model[0].mean_.tolist(),
            scaler_scale=model[0].scale_.tolist(),
            coefficients=model[-1].coef_.tolist(),
            intercepts=model[-1].intercept_.tolist(),
            classes=model[-1].classes_.tolist(),
        )
    return model, baseline, metadata


def forecast(model, baseline, row, settings, enabled, metadata):
    probabilities = baseline.copy()
    input_valid = row.get("macro_valid", True)
    if model is not None and input_valid:
        learned = np.zeros(4)
        learned[model[-1].classes_] = model.predict_proba([[row[k] for k in FEATURES]])[
            0
        ]
        probabilities = (
            settings["model_weight"] * learned
            + (1 - settings["model_weight"]) * baseline
        )
    return {
        "as_of": row["as_of"],
        "model": probabilities.tolist(),
        "baseline": baseline.tolist(),
        "used": (
            probabilities if enabled and model is not None and input_valid else baseline
        ).tolist(),
        "trained": model is not None,
        "enabled": bool(enabled and model is not None and input_valid),
        "input_valid": input_valid,
        "training_last_feature_date": metadata["last_training_feature_date"],
        "training_last_label_date": metadata["last_training_label_date"],
    }


def predictive_gate(scores, cutoff, minimum):
    prior = [s for s in scores if s["outcome_date"] < cutoff][-252:]
    enabled = bool(
        len(prior) >= minimum
        and np.mean([s["brier_model"] for s in prior])
        < np.mean([s["brier_baseline"] for s in prior])
    )
    return {
        "enabled": enabled,
        "mature_predictions": len(prior),
        "brier_model": float(np.mean([s["brier_model"] for s in prior]))
        if prior
        else None,
        "brier_baseline": float(np.mean([s["brier_baseline"] for s in prior]))
        if prior
        else None,
    }


def walk_forward_forecasts(features, settings):
    """Mature labels only, keeping the trading-session horizon across macro gaps."""
    result = {}
    evaluated = []
    current = None
    horizon = settings["horizon_sessions"]
    for i, row in enumerate(features):
        if i % settings["refit_sessions"] == 0 or current is None:
            model, baseline, metadata = fit_classifier(features, i, settings)
            prior = []
            for j, p in evaluated:
                if (
                    j + horizon >= i
                    or not p["trained"]
                    or not features[j + horizon].get("macro_valid", True)
                    or not features[j].get("macro_valid", True)
                ):
                    continue
                actual = np.eye(4)[quadrant(features[j + horizon])]
                prior.append(
                    {
                        "outcome_date": features[j + horizon]["date"],
                        "brier_model": float(
                            np.square(np.array(p["model"]) - actual).sum()
                        ),
                        "brier_baseline": float(
                            np.square(np.array(p["baseline"]) - actual).sum()
                        ),
                    }
                )
            gate = predictive_gate(
                prior, row["date"], settings["minimum_mature_predictions"]
            )
            current = (model, baseline, metadata, gate)
            prediction = forecast(
                model, baseline, row, settings, gate["enabled"], metadata
            )
            evaluated.append((i, prediction))
        model, baseline, metadata, gate = current
        result[pd.Timestamp(row["date"])] = forecast(
            model, baseline, row, settings, gate["enabled"], metadata
        )
    scores = []
    for i, p in evaluated:
        if (
            i + horizon >= len(features)
            or not p["trained"]
            or not features[i].get("macro_valid", True)
            or not features[i + horizon].get("macro_valid", True)
        ):
            continue
        actual = np.eye(4)[quadrant(features[i + horizon])]
        scores.append(
            {
                "date": features[i]["date"],
                "outcome_date": features[i + horizon]["date"],
                **{
                    f"brier_{k}": float(np.square(np.array(p[k]) - actual).sum())
                    for k in ("model", "baseline", "used")
                },
            }
        )
    return result, scores


def prepare_states(prices, macro, policy):
    signal_policy = SmartRegimePortfolio(
        Path("research/smart_regime_portfolio_v3.json")
    )
    daily = prices[list(DIVERSIFIED_ASSETS)].pct_change(fill_method=None)
    closes = (
        mcal.get_calendar("NYSE")
        .schedule(prices.index[0], prices.index[-1])
        .market_close
    )
    risk = set(s for group in policy.config["sleeves"].values() for s in group) | {
        "SHY",
        "SGOV",
    }
    states = {}
    features = []
    spy_vol = daily.SPY.rolling(20).std() * np.sqrt(252)
    for i in range(252, len(prices)):
        date = prices.index[i]
        history = daily.iloc[i - 251 : i + 1]
        active = [
            s for s in DIVERSIFIED_ASSETS if s in risk and np.isfinite(history[s]).all()
        ]
        past = daily.iloc[max(1, i - 1259) : i + 1][active]
        stress = past.loc[spy_vol.reindex(past.index) > 0.25].dropna()
        cov, _ = calibrated_covariance(
            history[active],
            stress,
            half_life=policy.config["volatility_half_life"],
            stress_weight=policy.config["stress_correlation_weight"],
        )
        spy = prices.SPY.iloc[: i + 1]
        market = {
            "trend": float(
                (spy.iloc[-1] / spy.iloc[-64] - 1)
                / (daily.SPY.iloc[i - 62 : i + 1].std() * np.sqrt(63))
            ),
            "as_of": closes.iloc[i].isoformat(),
            "breadth": float(
                np.mean(
                    [
                        prices[s].iloc[i]
                        > prices[s].iloc[max(0, i - 126) : i + 1].mean()
                        for s in ("SPY", "QQQ", "IWM", "VEA", "VWO")
                    ]
                )
            ),
            "drawdown": float(spy.iloc[-1] / spy.tail(252).max() - 1),
            "volatility": float(spy_vol.iloc[i]),
            "credit_relative": float(
                prices.HYG.iloc[i] / prices.HYG.iloc[i - 63]
                - prices.LQD.iloc[i] / prices.LQD.iloc[i - 63]
            ),
        }
        try:
            mf = macro.features(closes.iloc[i])
            signal = {
                **mf,
                **market,
                **signal_policy.classify(mf, market, decision_time=closes.iloc[i]),
            }
            unavailable = False
        except AllocationError as exc:
            mf = {
                k: None
                for k in (
                    "ip_growth",
                    "unemployment_change",
                    "inflation_yoy",
                    "inflation_change",
                    "yield_curve",
                )
            }
            mf.update(observation_dates={}, macro_unavailable_reason=str(exc))
            signal = {
                **mf,
                **market,
                "regime": "DATA_UNAVAILABLE",
                "stress": True,
                "probabilities": {
                    r: 0.25
                    for r in (
                        "disinflationary_growth",
                        "inflationary_growth",
                        "stagflation",
                        "deflationary_slowdown",
                    )
                },
                "growth_score": 0.0,
                "inflation_score": 0.0,
                "growth_weight": 0.5,
                "macro_unavailable": True,
            }
            unavailable = True
        signal["trend_weak"] = signal["trend"] < 0 and signal["breadth"] < 0.4
        states[date] = {
            "i": i,
            "macro_unavailable": unavailable,
            "symbols": active,
            "covariance": cov,
            "signal": signal,
            "reserve": "SGOV" if "SGOV" in active else "SHY",
            "trends": {
                s: float(
                    np.mean(
                        [
                            prices[s].iloc[i] > prices[s].iloc[i - h]
                            for h in (63, 126, 252)
                        ]
                    )
                )
                for s in active
            },
        }
        features.append(
            {
                "date": str(date.date()),
                **mf,
                **market,
                **signal,
                "macro_valid": not unavailable,
            }
        )
        if (i - 252) % 750 == 0:
            print(
                f"Prepared {i - 251} dated market/macro states through {date.date()}.",
                flush=True,
            )
    return daily, states, features


def benchmark(daily, dates, target, cost=0.0015):
    symbols = list(target)
    w = np.zeros(len(symbols))
    nav = 1.0
    rows = []
    for j, date in enumerate(dates):
        dollars = w * (1 + daily.loc[date, symbols].to_numpy())
        growth = 1 - w.sum() + dollars.sum()
        w = dollars / growth
        fee = turnover = 0.0
        if j % 21 == 0:
            t = np.array(list(target.values()))
            fee = rebalance_fee(w, t, cost)
            turnover = float(np.abs(t * (1 - fee) - w).sum())
            w = t
        value = nav * growth * fee
        ret = growth * (1 - fee) - 1
        nav *= 1 + ret
        rows.append(
            {
                "date": date,
                "return": ret,
                "equity": nav,
                "cash": 1 - w.sum(),
                "turnover": turnover,
                "cost_as_initial_capital": value,
            }
        )
    return pd.DataFrame(rows).set_index("date")


def _metrics(frame):
    result = metrics(frame, pd.Series(0.0, index=frame.index))
    result["sharpe_over_zero_cash"] = result.pop("sharpe_over_sgov")
    return result


def _history(frame):
    peak = frame.equity.cummax().clip(lower=1)
    return [
        [str(d.date()), float(r.equity), float(r.equity / peak.loc[d] - 1)]
        for d, r in frame.iterrows()
    ]


def train(capture_path, output, *, test_sessions=252):
    if (
        isinstance(test_sessions, bool)
        or not isinstance(test_sessions, int)
        or not 126 <= test_sessions <= 504
    ):
        raise ValueError("Evaluation requires 126-504 sessions")
    capture_path = Path(capture_path)
    capture = json.loads(capture_path.read_text())
    capture_root = capture_path.parent.resolve()
    if capture["status"] != "CAPTURED_FOR_SHADOW_TRAINING":
        raise ValueError("Complete immutable capture required")
    for name, digest in capture["files"].items():
        p = capture_root / name
        if (
            Path(name).name != name
            or p.is_symlink()
            or not p.is_file()
            or hashlib.sha256(p.read_bytes()).hexdigest() != digest
        ):
            raise ValueError("Training input checksum mismatch")
    if (
        Path(capture["prices"]).resolve() != capture_root / "prices.csv"
        or Path(capture["macro_manifest"]).resolve()
        != capture_root / "macro-manifest.json"
    ):
        raise ValueError(
            "Capture paths must reference their verified snapshot directory"
        )
    prices = validate_prices(
        pd.read_csv(capture_root / "prices.csv", index_col=0, parse_dates=True),
        pd.Timestamp(capture["price_session"]),
    )
    hashes = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in SOURCES}
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%S%fZ")
    root = Path(output) / run_id
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    policy = FourMacroStrategies()
    protocol = {
        "status": "SHADOW_ONLY",
        "test_sessions": test_sessions,
        "cost_rate": 0.0015,
        "risk_maps": "UNCHANGED",
        "method": "Latest-window frozen classifier evaluation; training labels purged by 63 sessions. Separate latest-data refit is not credited with evaluation returns.",
        "source_hashes": hashes,
        "capture_sha256": hashlib.sha256(capture_path.read_bytes()).hexdigest(),
    }
    private_write(root / "protocol.json", json.dumps(protocol, indent=2))
    daily, states, features = prepare_states(
        prices, TrainingMacro(capture["macro_manifest"]), policy
    )
    private_write(root / "features.json", json.dumps(features, allow_nan=False))
    settings = policy.config["macro_forecast"]
    print(
        "Fitting chronological regime models, preserving the 63-session label purge.",
        flush=True,
    )
    historical, scores = walk_forward_forecasts(features, settings)
    split = len(features) - test_sessions - 1
    if split <= settings["minimum_training"] + settings["horizon_sessions"]:
        raise ValueError("Insufficient separate training/evaluation history")
    frozen, baseline, model_info = fit_classifier(features, split - 1, settings)
    freeze_gate = predictive_gate(
        scores, features[split]["date"], settings["minimum_mature_predictions"]
    )
    test_forecasts = {}
    for i, row in enumerate(features):
        prediction = (
            forecast(
                frozen, baseline, row, settings, freeze_gate["enabled"], model_info
            )
            if i >= split
            else historical[pd.Timestamp(row["date"])]
        )
        states[pd.Timestamp(row["date"])]["signal"]["macro_forecast"] = prediction
        if i >= split:
            test_forecasts[i] = prediction
    eval_scores = []
    horizon = settings["horizon_sessions"]
    for i, prediction in test_forecasts.items():
        if (
            i + horizon >= len(features)
            or not features[i].get("macro_valid", True)
            or not features[i + horizon].get("macro_valid", True)
        ):
            continue
        target = np.eye(4)[quadrant(features[i + horizon])]
        eval_scores.append(
            {
                "feature_date": features[i]["date"],
                "outcome_date": features[i + horizon]["date"],
                **{
                    f"brier_{k}": float(
                        np.square(np.array(prediction[k]) - target).sum()
                    )
                    for k in ("model", "baseline", "used")
                },
            }
        )
    latest_model, latest_base, latest_info = fit_classifier(
        features, len(features) - 1, settings
    )
    latest_gate = predictive_gate(
        scores, features[-1]["date"], settings["minimum_mature_predictions"]
    )
    latest_forecast = forecast(
        latest_model,
        latest_base,
        features[-1],
        settings,
        latest_gate["enabled"],
        latest_info,
    )
    private_write(
        root / "models.json",
        json.dumps(
            {
                "frozen_evaluation_model": model_info,
                "latest_candidate_model": latest_info,
            },
            indent=2,
            allow_nan=False,
        ),
    )
    start = pd.Timestamp(features[split]["date"])
    end = prices.index[-1]
    rows = []
    for name, spec in policy.config["strategies"].items():
        print(f"Evaluating {name} on {test_sessions} later sessions.", flush=True)
        params = {
            "strategy": name,
            "volatility_ceiling": max(spec["volatility_ceilings"].values()),
        }
        frame, trades, info = simulate_strategy(
            prices, daily, states, policy, params, start=start, end=end
        )
        if len(frame) != test_sessions:
            raise ValueError("Evaluation session count does not reconcile")
        private_write(root / f"{name}.csv", frame.to_csv())
        private_write(
            root / f"{name}-audit.json",
            json.dumps({"trades": trades, **info}, allow_nan=False),
        )
        doubled, _, doubled_info = simulate_strategy(
            prices, daily, states, policy, params, start=start, end=end, cost_rate=0.003
        )
        # Keep the evaluation account's high-water mark and any cash lock for the latest proposal.
        guard = AccountDrawdownGuard(
            policy.config["protective_drawdown_start"],
            policy.config["protective_cash_lock"],
        )
        for nav in frame.equity:
            drawdown, factor = guard.update(float(nav))
        latest = deepcopy(states[end])
        if latest.get("macro_unavailable"):
            factor = 0.0
        latest["signal"]["macro_forecast"] = latest_forecast
        sigma = float(frame.raw_daily_sigma.iloc[-1])
        es = float(frame.filtered_es95.iloc[-1])
        multiplier = (
            float(np.clip(es / (2.062713 * sigma), 1, 2)) if sigma > 1e-8 else 1.0
        )
        try:
            proposal = strategy_proposal(
                policy,
                daily.iloc[latest["i"] - 251 : latest["i"] + 1][latest["symbols"]],
                latest["covariance"],
                latest["signal"],
                {**params, "tail_multiplier": multiplier},
                latest["trends"],
                reserve_symbol=latest["reserve"],
                drawdown=drawdown,
                factor=factor,
            )
            candidate = {
                "status": "DATA_QUARANTINE_CASH_ONLY"
                if latest.get("macro_unavailable")
                else "SHADOW_CANDIDATE_NOT_APPROVED",
                "weights": {
                    s: float(proposal["weights"].get(s, 0)) for s in DIVERSIFIED_ASSETS
                },
                "cash": float(proposal["cash"]),
                "risk_budget_error": float(proposal.get("risk_budget_error", 0)),
                "forecast_volatility": proposal.get(
                    "calibrated_estimated_volatility", 0
                ),
                "cash_locked": guard.locked,
                "drawdown": drawdown,
            }
            if min(
                [*candidate["weights"].values(), candidate["cash"]]
            ) < -1e-8 or not np.isclose(
                sum(candidate["weights"].values()) + candidate["cash"], 1, atol=1e-6
            ):
                raise ValueError("Latest candidate weights do not reconcile")
        except AllocationError as exc:
            candidate = {
                "status": "BLOCKED_RISK_REVIEW",
                "weights": None,
                "reason": str(exc),
                "cash_locked": guard.locked,
                "drawdown": drawdown,
            }
        rows.append(
            {
                "name": name,
                "role": "FIXED_STRATEGY_SHADOW_EVALUATION",
                "metrics": _metrics(frame),
                "history": _history(frame),
                "double_cost_metrics": _metrics(doubled),
                "rejections": len(info["rejections"]),
                "double_cost_rejections": len(doubled_info["rejections"]),
                "cash_lock_date": info["lock_date"],
                "trade_events": len(trades),
                "candidate": candidate,
            }
        )
    dates = frame.index
    references = []
    for name, target in [
        ("SPY_reference", {"SPY": 1.0}),
        (
            "All_Weather_style_proxy",
            {"SPY": 0.3, "TLT": 0.4, "IEF": 0.15, "GLD": 0.075, "DBC": 0.075},
        ),
        ("Balanced_reference", {"SPY": 0.6, "IEF": 0.4}),
    ]:
        reference = benchmark(daily, dates, target)
        private_write(root / f"{name}.csv", reference.to_csv())
        references.append(
            {
                "name": name,
                "role": "BENCHMARK_NOT_MANDATE_APPROVED",
                "metrics": _metrics(reference),
                "history": _history(reference),
            }
        )
    report = {
        "schema_version": 1,
        "status": "COMPLETED_SHADOW_EVALUATION",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market_session": capture["price_session"],
        "captured_at": capture["captured_at"],
        "price_sessions": len(prices),
        "macro_quarantined_sessions": sum(
            not r.get("macro_valid", True) for r in features
        ),
        "evaluation_quarantined_sessions": sum(
            not r.get("macro_valid", True) for r in features[split:-1]
        ),
        "latest_macro_available": features[-1].get("macro_valid", True),
        "core_universe": list(DIVERSIFIED_ASSETS),
        "evaluation": {
            "start": str(dates[0].date()),
            "end": str(dates[-1].date()),
            "sessions": len(dates),
            "freeze_date": model_info["freeze_date"],
            "last_training_label_date": model_info["last_training_label_date"],
            "new_account_start": str(start.date()),
            "cost_bps": 15,
            "cash_yield": 0.0,
        },
        "classifier": {
            "frozen_gate": freeze_gate,
            "latest_gate": latest_gate,
            "horizon_sessions": horizon,
            "evaluation_mature_forecasts": len(eval_scores),
            "evaluation_brier": {
                k: float(np.mean([s[f"brier_{k}"] for s in eval_scores]))
                if eval_scores
                else None
                for k in ("model", "baseline", "used")
            },
            "latest_refit_date": latest_info["freeze_date"],
            "latest_training_last_label_date": latest_info["last_training_label_date"],
            "latest_forecast": latest_forecast,
        },
        "strategies": rows,
        "benchmarks": references,
        "source_hashes": hashes,
        "capture_sha256": protocol["capture_sha256"],
        "execution_enabled": False,
        "public_recommendations_enabled": False,
        "promotion": "NONE",
        "limitations": [
            "Downloaded adjusted end-of-day market data, not a streaming execution feed.",
            "Chronological frozen-model evaluation of predeclared strategies; the history and universe are not pristine prospective evidence.",
            "63-session outcomes overlap; forecast scores do not establish calibrated recession or loss probabilities.",
            "Latest candidate refit consumes more recent labels after evaluation; it is a different model from the one evaluated.",
            "The latest 26-asset maps belong to hypothetical evaluation accounts; no investor account state or approved allocation is changed.",
            "No fixed return target, maximum account drawdown or automatic drawdown cash lock. Allocation/volatility/data-quality controls remain.",
            "15 bps adjusted-next-close fill proxies; doubled-cost sensitivity; zero uninvested cash yield; before investor taxes and platform fees.",
            "All Weather-style proxy is not official Bridgewater or ALLW fund performance.",
            "No timer, external alerts, automatic promotion or broker submission enabled.",
        ],
        "environment": {
            "python": platform.python_version(),
            **{
                name: __import__("importlib.metadata").metadata.version(name)
                for name in ("numpy", "pandas", "scipy", "scikit-learn", "yfinance")
            },
        },
    }
    private_write(
        root / "forecast-evaluation.json", json.dumps(eval_scores, allow_nan=False)
    )
    for p, h in hashes.items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest() != h:
            raise ValueError("Training source changed during execution")
    report["artifacts"] = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.iterdir()
        if p.is_file()
    }
    private_write(
        root / "training-report.json", json.dumps(report, indent=2, allow_nan=False)
    )
    print(
        pd.DataFrame(
            [
                {
                    "strategy": r["name"],
                    **{
                        k: r["metrics"][k]
                        for k in ("total_return", "volatility", "max_drawdown")
                    },
                    "rejections": r["rejections"],
                }
                for r in rows
            ]
        ).to_string(index=False),
        flush=True,
    )
    print(f"Training report: {root / 'training-report.json'}", flush=True)
    return root / "training-report.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=Path("var/strategy-training-runs")
    )
    parser.add_argument("--test-sessions", type=int, default=252)
    parser.add_argument(
        "--dashboard",
        type=Path,
        help="Attach results to this existing private dashboard, preserving its saved plans",
    )
    args = parser.parse_args()
    report = train(args.capture, args.output, test_sessions=args.test_sessions)
    if args.dashboard:
        from investor_dashboard import attach_training_report

        attach_training_report(args.dashboard, report, args.dashboard)


if __name__ == "__main__":
    main()
