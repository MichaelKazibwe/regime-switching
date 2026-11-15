"""Constrained macro-scenario allocations and joint-asset portfolio simulations.

All outputs are shadow candidates for hypothetical evaluation accounts. No
client state, approval, routing or broker authority is created.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from assetuniverse import DIVERSIFIED_ASSETS
from diversifiedregimepolicy import AllocationError
from fourregimestrategies import FourMacroStrategies, strategy_proposal
from institutionalportfolio import calibrated_covariance
from productreport import private_write
from smartregimeportfolio import REGIMES
from strategy_report import load_training_report

from assetroles import ASSET_ROLES
from portfolio_objectives import drawdown_factor


def validate_forecast(weights):
    if set(weights) != set(REGIMES):
        raise ValueError("All four regime weights required")
    values = np.array([weights[r] for r in REGIMES], dtype=float)
    if (
        any(isinstance(weights[r], bool) for r in REGIMES)
        or not np.isfinite(values).all()
        or (values < 0).any()
        or not np.isclose(values.sum(), 1, atol=1e-9, rtol=0)
    ):
        raise ValueError("Regime weights must be finite, nonnegative and sum to one")
    return values


def prepare_lab(capture_path, training_path):
    report = load_training_report(training_path)
    capture_path = Path(capture_path)
    capture = json.loads(capture_path.read_text())
    if (
        hashlib.sha256(capture_path.read_bytes()).hexdigest()
        != report["capture_sha256"]
    ):
        raise ValueError("Training/capture mismatch")
    root = capture_path.parent.resolve()
    for name, digest in capture["files"].items():
        p = root / name
        if (
            Path(name).name != name
            or p.is_symlink()
            or hashlib.sha256(p.read_bytes()).hexdigest() != digest
        ):
            raise ValueError("Changed capture input")
    prices = pd.read_csv(root / "prices.csv", index_col=0, parse_dates=True)
    daily = prices[list(DIVERSIFIED_ASSETS)].pct_change(fill_method=None)
    features = json.loads((Path(training_path).parent / "features.json").read_text())
    latest = features[-1]
    if latest["date"] != report["market_session"]:
        raise ValueError("Latest feature/market session mismatch")
    policy = FourMacroStrategies()
    risk = set(s for group in policy.config["sleeves"].values() for s in group) | {
        "SHY",
        "SGOV",
    }
    active = [
        s
        for s in DIVERSIFIED_ASSETS
        if s in risk and np.isfinite(daily[s].tail(252)).all()
    ]
    past = daily[active].tail(1260)
    stressed = past.loc[
        (daily.SPY.rolling(20).std() * np.sqrt(252)).reindex(past.index) > 0.25
    ].dropna()
    covariance, _ = calibrated_covariance(
        past.tail(252),
        stressed,
        half_life=policy.config["volatility_half_life"],
        stress_weight=policy.config["stress_correlation_weight"],
    )
    trends = {
        s: float(
            np.mean(
                [prices[s].iloc[-1] > prices[s].iloc[-1 - h] for h in (63, 126, 252)]
            )
        )
        for s in active
    }
    signals = {pd.Timestamp(r["date"]): r for r in features}
    pools = {r: [] for r in REGIMES}
    values = past.to_numpy()
    for i in range(1, len(past) - 20):
        # Feature date precedes the sampled return block. No revised feature substitution.
        prior = signals.get(past.index[i - 1])
        if (
            prior
            and prior.get("macro_valid", True)
            and np.isfinite(values[i : i + 21]).all()
        ):
            label = max(prior["probabilities"], key=prior["probabilities"].get)
            pools[label].append(i)
    accounts = {}
    for row in report["strategies"]:
        frame = pd.read_csv(
            Path(training_path).parent / f"{row['name']}.csv",
            index_col=0,
            parse_dates=True,
        )
        sigma = float(frame.raw_daily_sigma.iloc[-1])
        es = float(frame.filtered_es95.iloc[-1])
        accounts[row["name"]] = {
            "drawdown": row["candidate"]["drawdown"],
            "locked": row["candidate"]["cash_locked"],
            "guard_start": policy.config["protective_drawdown_start"],
            "guard_lock": policy.config["protective_cash_lock"],
            "tail_multiplier": float(np.clip(es / (2.062713 * sigma), 1, 2))
            if sigma > 1e-8
            else 1.0,
        }
    return {
        "report": report,
        "policy": policy,
        "active": active,
        "history": past.tail(252),
        "sample_history": past,
        "covariance": covariance,
        "trends": trends,
        "signal": latest,
        "pools": pools,
        "accounts": accounts,
    }


def simulate_candidate(
    lab, weights, cash, forecast_weights, account, *, quarters=4, paths=500, seed=103026
):
    if (
        isinstance(quarters, bool)
        or not isinstance(quarters, int)
        or not 1 <= quarters <= 4
        or isinstance(paths, bool)
        or not isinstance(paths, int)
        or not 100 <= paths <= 1000
    ):
        raise ValueError("Simulation resource bounds exceeded")
    probabilities = validate_forecast(forecast_weights)
    missing = [
        r
        for r, p in zip(REGIMES, probabilities)
        if p > 1e-9 and len(lab["pools"][r]) < 5
    ]
    if missing:
        return {
            "status": "BLOCKED_SCENARIO_COVERAGE",
            "missing_regimes": missing,
            "paths": paths,
            "quarters": quarters,
        }
    active = lab["active"]
    target = np.array([weights.get(s, 0) for s in active])
    values = lab["sample_history"].to_numpy()
    rng = np.random.default_rng(seed)
    horizon = quarters * 63
    count = int(np.ceil(horizon / 21))
    labels = rng.choice(4, size=(paths, count), p=probabilities)
    indices = np.empty((paths, count, 21), dtype=int)
    for k, r in enumerate(REGIMES):
        locations = np.where(labels == k)
        if len(locations[0]):
            indices[locations] = rng.choice(lab["pools"][r], size=len(locations[0]))[
                :, None
            ] + np.arange(21)
    sampled = values[indices.reshape(paths, -1)[:, :horizon]]
    w = np.zeros((paths, len(active)))
    nav = np.ones(paths)
    peak = np.full(paths, 1 / (1 + account["drawdown"]))
    locked = np.full(paths, account["locked"], dtype=bool)
    maximum = np.zeros(paths)
    curves = np.empty((paths, horizon))
    pending = np.broadcast_to(target, w.shape).copy()
    fill = np.ones(paths, dtype=bool)
    initial_factor = drawdown_factor(
        account["drawdown"],
        account["guard_start"],
        account["guard_lock"],
        locked=account["locked"],
    )
    for day in range(horizon):
        dollars = w * (1 + sampled[:, day, :])
        growth = 1 - w.sum(axis=1) + dollars.sum(axis=1)
        w = dollars / growth[:, None]
        nav *= growth
        fee = np.zeros(paths)
        if fill.any():
            selected = w[fill]
            t = pending[fill]
            f = np.zeros(len(selected))
            for _ in range(20):
                update = 0.0015 * np.abs(t * (1 - f[:, None]) - selected).sum(axis=1)
                if np.max(np.abs(update - f)) < 1e-12:
                    f = update
                    break
                f = update
            fee[fill] = f
            w[fill] = t
        nav *= 1 - fee
        peak = np.maximum(peak, nav)
        dd = nav / peak - 1
        maximum = np.minimum(maximum, dd)
        if account["guard_lock"] is not None:
            locked |= dd <= -account["guard_lock"]
            factor = np.where(
                locked,
                0,
                np.clip(
                    (account["guard_lock"] + dd)
                    / (account["guard_lock"] - account["guard_start"]),
                    0,
                    1,
                ),
            )
        else:
            factor = np.where(locked, 0.0, 1.0)
        scale = (
            np.minimum(1, factor / max(initial_factor, 1e-12))
            if initial_factor > 0
            else np.zeros(paths)
        )
        pending = target[None, :] * scale[:, None]
        fill = (np.abs(pending - w).sum(axis=1) >= 0.04) | (
            (pending.sum(axis=1) < w.sum(axis=1) - 1e-8) & (scale < 1)
        )
        if (day + 1) % 21 == 0:
            fill[:] = True
        curves[:, day] = nav
    terminal = nav - 1
    threshold = np.quantile(terminal, 0.05)
    daily = np.diff(
        np.concatenate([np.ones((paths, 1)), curves], axis=1), axis=1
    ) / np.concatenate([np.ones((paths, 1)), curves[:, :-1]], axis=1)
    return {
        "status": "CONDITIONAL_RESEARCH_SCENARIOS",
        "quarters": quarters,
        "paths": paths,
        "seed": seed,
        "median_return": float(np.median(terminal)),
        "p05_return": float(np.quantile(terminal, 0.05)),
        "p95_return": float(np.quantile(terminal, 0.95)),
        "median_annualized_volatility": float(
            np.median(daily.std(axis=1, ddof=1) * np.sqrt(252))
        ),
        "p95_max_drawdown": float(np.quantile(-maximum, 0.95)),
        "terminal_loss_frequency": float(np.mean(terminal < 0)),
        "horizon_var95_loss": max(0, -float(threshold)),
        "horizon_es95_loss": max(0, -float(terminal[terminal <= threshold].mean())),
        "five_percent_drawdown_exceedance": float(np.mean(maximum < -0.05)),
        "fan": [q.tolist() for q in np.quantile(curves, [0.05, 0.5, 0.95], axis=0)],
        "source_blocks": {r: len(lab["pools"][r]) for r in REGIMES},
        "assumptions": [
            "Joint 21-session historical asset blocks sampled conditionally on prior-known macro regime; overlapping blocks are not independent observations.",
            f"Conditional samples cover {lab['sample_history'].index[0].date()} to {lab['sample_history'].index[-1].date()}; recent eligible joint history does not contain every financial crisis.",
            "Selected forecast regime mixture held fixed over the chosen horizon; not a refit of future macro models or a full adaptive strategy backtest.",
            "Latest constrained target with reduce-only drawdown sizing, optional legacy cash lock (disabled in the current policy), next-close proxies, 15 bps traded notional costs and zero cash yield.",
            "Drawdowns include the carried hypothetical evaluation-account high-water mark. Risk forecasts/thresholds do not guarantee loss limits.",
            "Before investor taxes/platform fees; conditional frequencies and fan bands are not calibrated real-world probabilities.",
        ],
    }


def recalculate(
    lab, strategy, forecast_weights, *, quarters=4, paths=500, mode="user_scenario"
):
    probabilities = validate_forecast(forecast_weights)
    policy = lab["policy"]
    if strategy not in policy.config["strategies"] or mode not in {
        "latest_model",
        "user_scenario",
        "quarter_scenario",
    }:
        raise ValueError("Unknown strategy/scenario mode")
    if mode == "latest_model":
        expected = lab["report"]["classifier"]["latest_forecast"]["used"]
        if not np.allclose(probabilities, expected, atol=1e-9, rtol=0):
            raise ValueError("Latest-model mode must honor its validation gate")
    account = lab["accounts"][strategy]
    factor = (
        0.0
        if not lab["signal"].get("macro_valid", True)
        else drawdown_factor(
            account["drawdown"],
            policy.config["protective_drawdown_start"],
            policy.config["protective_cash_lock"],
            locked=account["locked"],
        )
    )
    signal = deepcopy(lab["signal"])
    calculated_at = datetime.now(timezone.utc).isoformat()
    signal["as_of"] = calculated_at
    signal["macro_forecast"] = {
        **lab["report"]["classifier"]["latest_forecast"],
        "used": probabilities.tolist(),
    }
    if mode != "latest_model":
        signal["macro_forecast"]["as_of"] = calculated_at
    spec = policy.config["strategies"][strategy]
    params = {
        "strategy": strategy,
        "volatility_ceiling": max(spec["volatility_ceilings"].values()),
        "tail_multiplier": account["tail_multiplier"],
    }
    try:
        proposal = strategy_proposal(
            policy,
            lab["history"],
            lab["covariance"],
            signal,
            params,
            lab["trends"],
            reserve_symbol="SGOV" if "SGOV" in lab["active"] else "SHY",
            drawdown=account["drawdown"],
            factor=factor,
        )
    except AllocationError as exc:
        return {
            "status": "BLOCKED_RISK_REVIEW",
            "strategy": strategy,
            "reason": str(exc),
            "weights": None,
        }
    weights = {s: float(proposal["weights"].get(s, 0)) for s in DIVERSIFIED_ASSETS}
    cash = float(proposal["cash"])
    w = np.array([weights[s] for s in lab["active"]])
    variance = float(w @ lab["covariance"] @ w)
    shares = w * (lab["covariance"] @ w) / variance if variance > 1e-15 else None
    if (
        min([*weights.values(), cash]) < -1e-8
        or max(weights.values()) > 0.250001
        or not np.isclose(sum(weights.values()) + cash, 1, atol=1e-6)
    ):
        raise ValueError("Constrained capital reconciliation failed")
    if shares is not None and (
        shares.max() > 0.250001 or not np.isclose(shares.sum(), 1, atol=1e-6)
    ):
        raise ValueError("Whole-account risk-share gate failed")
    contributions = {
        s: float(shares[lab["active"].index(s)])
        if shares is not None and s in lab["active"]
        else 0.0
        if shares is not None
        else None
        for s in [*DIVERSIFIED_ASSETS, "DBMF", "ALLW", "USD_CASH"]
    }
    result = {
        "status": "SHADOW_SCENARIO_CANDIDATE",
        "strategy": strategy,
        "mode": mode,
        "market_session": lab["report"]["market_session"],
        "macro_as_of": lab["signal"]["as_of"],
        "calculated_at": calculated_at,
        "forecast_supplied_at": calculated_at
        if mode != "latest_model"
        else lab["report"]["classifier"]["latest_forecast"]["as_of"],
        "forecast_weights": dict(zip(REGIMES, map(float, probabilities))),
        "forecast_tilt_weight": policy.config["macro_forecast"][
            "allocation_forecast_weight"
        ],
        "weights": weights,
        "cash": cash,
        "risk_contributions": contributions,
        "forecast_annual_volatility": float(np.sqrt(variance)),
        "risk_budget_error": float(proposal.get("risk_budget_error", 0)),
        "requested_risk_budgets": proposal.get("requested_sleeve_risk_budgets"),
        "feasible_risk_budgets": proposal.get("feasible_sleeve_risk_budgets"),
        "account": account,
        "roles": ASSET_ROLES,
        "execution_enabled": False,
        "public_recommendations_enabled": False,
        "simulation": simulate_candidate(
            lab,
            weights,
            cash,
            forecast_weights,
            account,
            quarters=quarters,
            paths=paths,
        ),
    }
    result["result_id"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    return result


def build_lab_payload(capture_path, training_path, *, quarterly=None, output=None):
    lab = prepare_lab(capture_path, training_path)
    presets = [
        {
            "id": "latest_model",
            "label": "Validation-gated latest model",
            "mode": "latest_model",
            "weights": dict(
                zip(REGIMES, lab["report"]["classifier"]["latest_forecast"]["used"])
            ),
        }
    ]
    for q in quarterly or []:
        presets.append(
            {
                "id": q["quarter"],
                "label": q["quarter"] + " conditional macro scenario",
                "mode": "quarter_scenario",
                "weights": q["regime_frequencies"],
            }
        )
    results = {}
    for strategy in lab["policy"].config["strategies"]:
        results[strategy] = {}
        for preset in presets:
            print(f"Recalculating {strategy} / {preset['id']}.", flush=True)
            results[strategy][preset["id"]] = recalculate(
                lab, strategy, preset["weights"], mode=preset["mode"]
            )
    payload = {
        "status": "SHADOW_ALLOCATION_LAB",
        "market_session": lab["report"]["market_session"],
        "training_run": lab["report"]["run_id"],
        "presets": presets,
        "results": results,
        "roles": ASSET_ROLES,
        "regimes": list(REGIMES),
        "hypothetical_accounts_only": True,
        "execution_enabled": False,
        "automatic_investor_promotion": False,
    }
    if output:
        private_write(output, json.dumps(payload, allow_nan=False))
    return lab, payload
