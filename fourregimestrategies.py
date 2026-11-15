"""Four fixed macro-aware challengers, never order-authorizing portfolios."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from diversifiedregimepolicy import AllocationError, aware
from institutionalportfolio import InstitutionalPortfolio
from smartregimeportfolio import REGIMES, capped_distribution

PLAN = Path("research/four_macro_strategies.json")
FEATURES = (
    "ip_growth",
    "unemployment_change",
    "inflation_change",
    "yield_curve",
    "trend",
    "breadth",
    "volatility",
    "credit_relative",
)


def quadrant(row):
    growth = row["ip_growth"] > 0 and row["unemployment_change"] < 0.25
    inflation = row["inflation_change"] > 0
    return (1 if inflation else 0) if growth else (2 if inflation else 3)


def macro_forecasts(features, settings):
    """Purged monthly forecasts of future released-condition quadrants, not NBER recessions."""
    rows = sorted(features, key=lambda r: r["date"])
    x = np.array([[r[k] for k in FEATURES] for r in rows], dtype=float)
    if not np.isfinite(x).all() or len({r["date"] for r in rows}) != len(rows):
        raise AllocationError("Invalid macro forecast feature history")
    y = np.array([quadrant(r) for r in rows])
    h = settings["horizon_sessions"]
    forecasts = {}
    evaluated = []
    current = None
    for i, row in enumerate(rows):
        if i % settings["refit_sessions"] == 0 or current is None:
            # Train only labels strictly observed before this decision close.
            end = i - h
            start = max(0, end - settings["training_sessions"])
            indices = np.arange(start, max(start, end))
            target = y[indices + h]
            counts = np.bincount(target, minlength=4) + 1
            baseline = counts / counts.sum()
            estimate = baseline.copy()
            trained = False
            if (
                len(indices) >= settings["minimum_training"]
                and len(np.unique(target)) >= 2
            ):
                model = make_pipeline(
                    StandardScaler(),
                    LogisticRegression(C=settings["regularization_C"], max_iter=1000),
                )
                model.fit(x[indices], target)
                predicted = np.zeros(4)
                predicted[model[-1].classes_] = model.predict_proba(x[[i]])[0]
                estimate = (
                    settings["model_weight"] * predicted
                    + (1 - settings["model_weight"]) * baseline
                )
                trained = True
            mature = [p for p in evaluated if p["index"] + h < i and p["trained"]]
            mature = mature[-252:]

            def brier(p, key):
                actual = np.eye(4)[y[p["index"] + h]]
                return float(np.square(np.array(p[key]) - actual).sum())

            enabled = bool(
                trained
                and len(mature) >= settings["minimum_mature_predictions"]
                and np.mean([brier(p, "model") for p in mature])
                < np.mean([brier(p, "baseline") for p in mature])
            )
            current = {
                "as_of": row["as_of"],
                "model": estimate.tolist(),
                "baseline": baseline.tolist(),
                "used": (estimate if enabled else baseline).tolist(),
                "trained": trained,
                "enabled": enabled,
                "training_last_feature_date": rows[indices[-1]]["date"]
                if len(indices)
                else None,
                "training_last_label_date": rows[indices[-1] + h]["date"]
                if len(indices)
                else None,
                "mature_gate_observations": len(mature),
                "index": i,
            }
            evaluated.append(current.copy())
        forecasts[pd.Timestamp(row["date"])] = deepcopy(current)
    scores = []
    for p in evaluated:
        if p["index"] + h >= len(rows) or not p["trained"]:
            continue
        actual = np.eye(4)[y[p["index"] + h]]
        scores.append(
            {
                "date": rows[p["index"]]["date"],
                "outcome_date": rows[p["index"] + h]["date"],
                "enabled": p["enabled"],
                "brier_model": float(np.square(np.array(p["model"]) - actual).sum()),
                "brier_baseline": float(
                    np.square(np.array(p["baseline"]) - actual).sum()
                ),
                "brier_used": float(np.square(np.array(p["used"]) - actual).sum()),
            }
        )
    return forecasts, scores


class FourMacroStrategies(InstitutionalPortfolio):
    def __init__(self, path=PLAN):
        super().__init__(path)
        if len(self.config["strategies"]) != 4:
            raise AllocationError("Exactly four frozen strategies are required")
        for spec in self.config["strategies"].values():
            if set(spec["risk_budgets"]) != set(REGIMES) or set(
                spec["volatility_ceilings"]
            ) != set(REGIMES):
                raise AllocationError("All four economic quadrants must be specified")
            for b in spec["risk_budgets"].values():
                if (
                    len(b) != 5
                    or min(b) <= 0
                    or not np.isfinite(b).all()
                    or not np.isclose(sum(b), 1, atol=1e-12)
                ):
                    raise AllocationError("Invalid declared economic risk budgets")
            if any(not 0 < v <= 0.10 for v in spec["volatility_ceilings"].values()):
                raise AllocationError("Invalid strategy volatility ceiling")

    def mixture(self, signal):
        current = np.array([signal["probabilities"][r] for r in REGIMES])
        forecast = signal["macro_forecast"]
        if aware(forecast["as_of"]) > aware(signal["as_of"]):
            raise AllocationError("Future macro forecast")
        predicted = np.array(forecast["used"])
        for p in (current, predicted):
            if (
                p.shape != (4,)
                or not np.isfinite(p).all()
                or min(p) < 0
                or not np.isclose(p.sum(), 1, atol=1e-12)
            ):
                raise AllocationError("Invalid quadrant weights")
        alpha = self.config["macro_forecast"]["allocation_forecast_weight"]
        return (1 - alpha) * current + alpha * predicted

    def volatility_ceiling(self, name, signal):
        spec = self.config["strategies"][name]
        p = self.mixture(signal)
        ceiling = float(p @ np.array([spec["volatility_ceilings"][r] for r in REGIMES]))
        return min(ceiling, 0.05) if signal["stress"] else ceiling


def strategy_proposal(
    base,
    history,
    covariance,
    signal,
    parameters,
    trends,
    *,
    reserve_symbol,
    drawdown,
    factor,
):
    name = parameters["strategy"]
    if name not in base.config["strategies"] or not 0 <= factor <= 1:
        raise AllocationError("Unknown strategy or invalid exposure factor")
    probabilities = base.mixture(signal)
    if factor == 0:
        return {
            "weights": {s: 0.0 for s in history},
            "cash": 1.0,
            "risk_budget_error": 0.0,
            "cash_lock": True,
        }
    spec = base.config["strategies"][name]
    budgets = probabilities @ np.array([spec["risk_budgets"][r] for r in REGIMES])
    if signal["stress"]:
        budgets = 0.5 * (
            np.array(spec["risk_budgets"]["stagflation"])
            + np.array(spec["risk_budgets"]["deflationary_slowdown"])
        )
        if budgets[0] > 0.15:
            released = budgets[0] - 0.15
            budgets[0] = 0.15
            budgets[1:] += released * budgets[1:] / budgets[1:].sum()
    if spec["trend_overlay"]:
        if set(trends) != set(history) or any(
            not np.isfinite(v) or not 0 <= v <= 1 for v in trends.values()
        ):
            raise AllocationError("Invalid market trend features")
        strength = np.array(
            [
                np.mean([trends[s] for s in group if s in history])
                for group in base.config["sleeves"].values()
            ]
        )
        budgets *= 0.5 + 0.5 * strength
        budgets /= budgets.sum()
    ceiling = base.volatility_ceiling(name, signal)
    policy = object.__new__(InstitutionalPortfolio)
    policy.config = deepcopy(base.config)
    # Trend and macro mixtures can concentrate a multi-asset sleeve beyond its
    # per-asset capacity. Project declared budgets before the strict solve;
    # never accept an invalid proposal or relax the account contribution cap.
    core = []
    desired = []
    groups = list(policy.config["sleeves"].items())
    for j, (group, members) in enumerate(groups):
        eligible = [s for s in members if s in history]
        if not eligible:
            raise AllocationError("Missing required economic sleeve")
        total = sum(members[s] for s in eligible)
        core.extend(eligible)
        desired.extend(budgets[j] * members[s] / total for s in eligible)
    feasible = capped_distribution(
        desired, 1.0, 0.96 * base.config["maximum_full_account_risk_share"]
    )
    asset_budgets = dict(zip(core, map(float, feasible)))
    feasible_groups = []
    for group, members in groups:
        mapped = {s: asset_budgets[s] for s in members if s in asset_budgets}
        policy.config["sleeves"][group] = mapped
        feasible_groups.append(sum(mapped.values()))
    policy.config["anchors"] = {"active": feasible_groups}
    policy.config["candidate_grid"] = {
        "anchor": ["active"],
        "volatility_ceiling": [ceiling],
        "macro_view_weight": [0.0],
    }
    calibration = (
        parameters.get("tail_multiplier", 1.0) if spec["tail_feedback"] else 1.0
    )
    arguments = {
        "account_drawdown": drawdown,
        "calibration_multiplier": calibration,
        "decision_time": signal["as_of"],
        "use_trend": False,
    }
    params = {
        "anchor": "active",
        "volatility_ceiling": ceiling,
        "macro_view_weight": 0.0,
    }
    try:
        result = policy.allocate(
            history,
            covariance,
            signal,
            params,
            reserve_symbol=reserve_symbol,
            **arguments,
        )
    except AllocationError as exc:
        if reserve_symbol is None:
            raise
        result = policy.allocate(
            history, covariance, signal, params, reserve_symbol=None, **arguments
        )
        result["reserve_fallback_reason"] = str(exc)
    for symbol in result["weights"]:
        result["weights"][symbol] *= factor
    result["cash"] = 1 - sum(result["weights"].values())
    for key in (
        "reserve_weight",
        "raw_estimated_volatility",
        "calibrated_estimated_volatility",
        "estimated_daily_es95",
    ):
        result[key] *= factor
    result.update(
        strategy=name,
        forecast_quadrant_weights=probabilities.tolist(),
        account_drawdown_factor=factor,
        cash_lock=False,
        requested_sleeve_risk_budgets=budgets.tolist(),
        feasible_sleeve_risk_budgets=feasible_groups,
    )
    return result
