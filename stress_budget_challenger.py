"""Independent stress-budgeted shadow challenger, never an order authorizer."""

from copy import deepcopy
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from economic_design_assessment import stress_review
from investmentcatalog import catalogue
from productallocation import PRIORS
from strategy_integrity import fingerprint


def shock_matrix(symbols):
    templates = stress_review({"SPY": 0.0}, np.eye(1), ["SPY"])["scenarios"]
    for name, shock in templates.items():
        shock["DBMF"] = -0.15 if name == "liquidity_dislocation" else -0.10
    if "ALLW" in symbols or any(s not in catalogue() for s in symbols):
        raise ValueError(
            "Eligible component instruments required; ALLW is benchmark-only"
        )
    return -np.array(
        [[shock[s] for s in symbols] for shock in templates.values()], dtype=float
    )


def checks(w, cov, symbols, config, *, drawdown=0.0, degraded=False):
    w = np.asarray(w, dtype=float)
    cov = np.asarray(cov, dtype=float)
    if (
        len(w) != len(symbols)
        or cov.shape != (len(w), len(w))
        or not np.isfinite(w).all()
        or not np.isfinite(cov).all()
        or not -1 < drawdown <= 0
    ):
        raise ValueError("Finite account, weights and covariance required")
    if np.linalg.eigvalsh(cov).min() < -1e-10:
        raise ValueError("Positive semidefinite covariance required")
    var = float(w @ cov @ w)
    rc = w * (cov @ w) / var if var > 1e-15 else np.zeros(len(w))
    cat = catalogue()
    limits = {
        b: config[b + "_cap"]
        for b in ["equity", "government", "real_assets", "credit", "alternative"]
    }
    exposure = {
        b: float(sum(w[i] for i, s in enumerate(symbols) if cat[s].bucket == b))
        for b in limits
    }
    foreign = sum(
        w[i] for i, s in enumerate(symbols) if s in {"VEA", "VWO", "IGOV", "EWJ"}
    )
    shock = shock_matrix(symbols) @ w
    # Reserve two full-notional modeled trades before the declared shock.
    cost_allowance = 2 * config["modeled_cost_rate"]
    account_loss = 1 - (1 + drawdown) * (1 - cost_allowance) * (1 - shock)
    ceiling = (
        config["degraded_stress_ceiling"] if degraded else config["stress_loss_ceiling"]
    )
    flags = {
        "capital": bool(
            w.min(initial=0) >= -1e-9
            and w.max(initial=0) <= config["asset_cap"] + 1e-7
            and w.sum() <= 1 - config["minimum_cash"] + 1e-7
        ),
        "euler": bool(rc.max(initial=0) <= config["euler_cap"] + 1e-6),
        "volatility": bool(var <= config["volatility_ceiling"] ** 2 + 1e-9),
        "shock_budget": bool(shock.max() <= ceiling + 1e-7),
        "account_loss_budget": bool(
            config.get("account_drawdown_preference") is None
            or account_loss.max() <= config["account_drawdown_preference"] + 1e-7
        ),
        "bucket_concentration": all(
            exposure[b] <= limit + 1e-7 for b, limit in limits.items()
        ),
        "foreign_capital_proxy": bool(
            foreign <= config["foreign_capital_proxy_cap"] + 1e-7
        ),
        "degraded_exposure": bool(
            not degraded or w.sum() <= config["degraded_exposure_ceiling"] + 1e-7
        ),
    }
    return {
        "passed": all(flags.values()),
        "checks": flags,
        "volatility": float(np.sqrt(max(0, var))),
        "risk_shares": dict(zip(symbols, map(float, rc)))
        if var > 1e-15
        else dict.fromkeys(symbols, None),
        "shock_losses": shock.tolist(),
        "account_shock_drawdowns_including_cost_allowance": account_loss.tolist(),
        "bucket_exposures": exposure,
        "foreign_capital_proxy": float(foreign),
        "cash": float(1 - w.sum()),
    }


def allocate(
    history,
    cov,
    config,
    *,
    current=None,
    drawdown=0.0,
    macro_valid=True,
    market_fallback=False,
    locked=False,
):
    symbols = list(history.columns)
    if (
        len(history) < 252
        or not np.isfinite(history).all().all()
        or (history <= -1).any().any()
    ):
        raise ValueError("252 complete actual returns required")
    if len(symbols) != len(set(symbols)):
        raise ValueError("Unique instruments required")
    if locked or (not macro_valid and not market_fallback):
        w = np.zeros(len(symbols))
        reason = "PERSISTENT_CASH_LOCK" if locked else "STRICT_MACRO_QUARANTINE"
        return {
            "status": "SHADOW_CASH",
            "reason": reason,
            "weights": dict(zip(symbols, w.tolist())),
            "cash": 1.0,
            "execution_enabled": False,
        }
    degraded = not macro_valid
    cat = catalogue()
    n = len(symbols)
    loss = shock_matrix(symbols)
    old = np.array([(current or {}).get(s, 0.0) for s in symbols])
    if not np.isfinite(old).all() or old.min(initial=0) < 0 or old.sum() > 1 + 1e-8:
        raise ValueError("Invalid current portfolio")
    prior = np.array([PRIORS[cat[s].bucket][0] for s in symbols])
    uncertainty = np.array([PRIORS[cat[s].bucket][1] for s in symbols])
    observed = (
        np.clip(
            history.to_numpy(),
            history.quantile(0.01).to_numpy(),
            history.quantile(0.99).to_numpy(),
        ).mean(axis=0)
        * 252
    )
    mu = (
        0.9 * prior
        + 0.1 * observed
        - config["robust_uncertainty_penalty"] * uncertainty
    )
    if degraded:
        mu = mu * 0.5  # No unavailable macro value is inferred or imputed.

    def objective(w):
        trading = np.sqrt((w - old) ** 2 + 1e-12).sum() * config["modeled_cost_rate"]
        return float(-mu @ w + config["variance_aversion"] * (w @ cov @ w) + trading)

    ceiling = (
        config["degraded_stress_ceiling"] if degraded else config["stress_loss_ceiling"]
    )
    exposure = (
        config["degraded_exposure_ceiling"] if degraded else 1 - config["minimum_cash"]
    )

    def feasible_vector(w):
        var = float(w @ cov @ w)
        rc = w * (cov @ w) / var if var > 1e-15 else np.zeros(n)
        residual = [exposure - w.sum(), config["volatility_ceiling"] ** 2 - var]
        residual.extend(ceiling - loss @ w)
        account_loss = 1 - (1 + drawdown) * (1 - 2 * config["modeled_cost_rate"]) * (
            1 - loss @ w
        )
        if config["account_drawdown_preference"] is not None:
            residual.extend(config["account_drawdown_preference"] - account_loss)
        residual.extend(config["euler_cap"] - config["target_euler_buffer"] - rc)
        for bucket in ["equity", "government", "real_assets", "credit", "alternative"]:
            residual.append(
                config[bucket + "_cap"]
                - config["target_bucket_buffer"]
                - sum(w[i] for i, s in enumerate(symbols) if cat[s].bucket == bucket)
            )
        residual.append(
            config["foreign_capital_proxy_cap"]
            - sum(
                w[i]
                for i, s in enumerate(symbols)
                if s in {"VEA", "VWO", "IGOV", "EWJ"}
            )
        )
        return np.array(residual)

    inverse = 1 / np.sqrt(np.maximum(np.diag(cov), 1e-12))
    seed = inverse / inverse.sum() * 0.10
    solutions = []
    for initial in [seed, np.full(n, 0.10 / n)]:
        fit = minimize(
            objective,
            initial,
            method="SLSQP",
            bounds=[(0, config["asset_cap"] - config["target_asset_buffer"])] * n,
            constraints=[{"type": "ineq", "fun": feasible_vector}],
            options={"maxiter": 160, "ftol": 1e-10},
        )
        verified = checks(
            fit.x, cov, symbols, config, drawdown=drawdown, degraded=degraded
        )
        if fit.success and verified["passed"]:
            solutions.append((objective(fit.x), fit.x, verified))
    if not solutions:
        w = np.zeros(n)
        verified = checks(w, cov, symbols, config, drawdown=drawdown, degraded=degraded)
        return {
            "status": "BLOCKED_SOLVER_OR_ACCOUNT_REVIEW",
            "weights": dict(zip(symbols, w.tolist())),
            "cash": 1.0,
            "validation": verified,
            "execution_enabled": False,
        }
    _, w, verified = min(solutions, key=lambda x: x[0])
    result = {
        "status": "UNAPPROVED_STRESS_BUDGET_SHADOW",
        "mode": "MARKET_ONLY_DEGRADED" if degraded else "MACRO_AVAILABLE",
        "weights": dict(zip(symbols, map(float, w))),
        "cash": float(1 - w.sum()),
        "validation": verified,
        "expected_returns": dict(zip(symbols, map(float, mu))),
        "expected_return_method": "90% existing unvalidated bucket priors, 10% clipped historical mean, minus fixed uncertainty penalty; not certified alpha.",
        "metadata_approval": "BLOCKED_UNVERIFIED_CASH_COST_DURATION_FX_EVIDENCE",
        "execution_enabled": False,
        "promotion_enabled": False,
    }
    result["calculation_id"] = fingerprint(result)
    return result


def trade_decision(
    current,
    target,
    cov,
    history,
    config,
    *,
    drawdown=0.0,
    macro_valid=True,
    market_fallback=False,
    sessions_since_trade=21,
    cost_aware=True,
    locked=False,
):
    symbols = list(history)
    before = np.array([current.get(s, 0.0) for s in symbols])
    after = np.array([target["weights"].get(s, 0.0) for s in symbols])
    urgent = (
        target["status"].startswith("BLOCKED")
        or locked
        or (not macro_valid and not market_fallback)
        or not checks(
            before, cov, symbols, config, drawdown=drawdown, degraded=not macro_valid
        )["passed"]
    )
    drift = float(np.abs(after - before).sum())
    cost = drift * config["modeled_cost_rate"]
    mu = np.array([target.get("expected_returns", {}).get(s, 0.0) for s in symbols])
    benefit = float((after - before) @ mu) * config["benefit_horizon_years"]
    accept = urgent or (
        drift >= config["minimum_discretionary_drift"]
        and sessions_since_trade >= config["minimum_discretionary_sessions"]
        and (not cost_aware or benefit >= config["cost_hurdle_multiplier"] * cost)
    )
    return {
        "trade": bool(accept and drift > 1e-10),
        "urgent": bool(urgent),
        "drift": drift,
        "modeled_cost": cost,
        "unvalidated_expected_benefit": benefit,
        "reason": "PROTECTIVE_OVERRIDE"
        if urgent
        else "DISCRETIONARY_ACCEPT"
        if accept
        else "HYSTERESIS_OR_COST_REJECTION",
    }


def finalize_target(target, cov, symbols, config, *, factor, drawdown, degraded):
    """Recalculate disclosure metrics after protective scaling; no stale ID."""
    if not np.isfinite(factor) or not 0 <= factor <= 1:
        raise ValueError("Invalid protective factor")
    result = deepcopy(target)
    result["weights"] = {s: w * factor for s, w in result["weights"].items()}
    result["cash"] = 1 - sum(result["weights"].values())
    result["validation"] = checks(
        np.array([result["weights"].get(s, 0.0) for s in symbols]),
        cov,
        symbols,
        config,
        drawdown=drawdown,
        degraded=degraded,
    )
    result.pop("calculation_id", None)
    result["calculation_id"] = fingerprint(result)
    return result


def reviewed_unlock(state, receipt, *, cohort, session, config, now=None):
    """Explicit local review receipt; never clears the carried high-water mark."""
    now = now or datetime.now(timezone.utc)
    if not state.get("locked"):
        raise ValueError("Locked account required")
    if (
        not isinstance(receipt, dict)
        or receipt.get("status") != "APPROVED_SHADOW_RECOVERY"
        or receipt.get("cohort") != cohort
        or receipt.get("session") != session
        or receipt.get("state_sha256") != fingerprint(state)
        or receipt.get("config_sha256") != fingerprint(config)
        or not isinstance(receipt.get("reviewer"), str)
        or not receipt["reviewer"].strip()
        or not receipt.get("evidence_sha256")
        or receipt.get("reuse_allowed") is not False
    ):
        raise ValueError("State/cohort/config-bound recovery approval required")
    stamp = pd.Timestamp(receipt["recorded_at"])
    expiry = pd.Timestamp(receipt["expires_at"])
    if (
        stamp.tzinfo is None
        or expiry.tzinfo is None
        or not stamp <= pd.Timestamp(now) <= expiry
    ):
        raise ValueError("Invalid recovery clock")
    if (
        config.get("protective_start") is not None
        and state["nav"] / state["peak"] - 1 < -config["protective_start"]
    ):
        raise ValueError(
            "Account has not recovered inside the original protective-start threshold"
        )
    if receipt.get("valid_market_sessions", 0) < 10:
        raise ValueError("Ten confirmed market sessions required for reviewed recovery")
    used = state.get("used_review_ids", [])
    if fingerprint(receipt) in used:
        raise ValueError("Recovery approval already consumed")
    result = deepcopy(state)
    result["used_review_ids"] = [*used, fingerprint(receipt)]
    result["locked"] = False
    result["recovery_review_sha256"] = fingerprint(receipt)
    result["recovery_exposure_ceiling"] = 0.10
    return result
