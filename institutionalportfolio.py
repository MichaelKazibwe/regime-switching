"""Research risk-balanced core with a fully attributed Treasury reserve.

The contract normalizes core Euler contributions including reserve cross-risk.
It never hides Treasury risk or treats invested reserve ETFs as cash.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import xlogy
from scipy.stats import binomtest, chi2, norm
from sklearn.covariance import LedoitWolf

from assetuniverse import DIVERSIFIED_ASSETS
from diversifiedregimepolicy import AllocationError, aware
from smartregimeportfolio import REGIMES, solve_risk_budget

DEFAULT_PLAN = (
    Path(__file__).resolve().parent / "research/institutional_refinement_plan.json"
)


def calibrated_covariance(
    returns, stress_returns=None, half_life=63, stress_weight=0.25
):
    if not np.isfinite(half_life) or half_life <= 0 or not 0 <= stress_weight <= 1:
        raise AllocationError("Invalid covariance controls")
    values = np.asarray(returns, dtype=float)
    if (
        values.ndim != 2
        or len(values) < 252
        or not np.isfinite(values).all()
        or (values <= -1).any()
    ):
        raise AllocationError("Complete actual return history is required")
    std = values.std(axis=0, ddof=0)
    if (std <= 1e-12).any():
        raise AllocationError("Zero-variance instruments cannot be risk-estimated")

    def correlation(x):
        s = x.std(axis=0, ddof=0)
        if (s <= 1e-12).any():
            raise AllocationError("Degenerate stress sample")
        c = LedoitWolf().fit((x - x.mean(axis=0)) / s).covariance_
        return c / np.sqrt(np.outer(np.diag(c), np.diag(c)))

    corr = correlation(values)
    stress_used = False
    if stress_returns is not None and len(stress_returns) >= 40:
        stress = np.asarray(stress_returns, dtype=float)
        if stress.shape[1] != values.shape[1] or not np.isfinite(stress).all():
            raise AllocationError("Invalid past stress sample")
        corr = (1 - stress_weight) * corr + stress_weight * correlation(stress)
        stress_used = True
    decay = np.exp(-np.log(2) * np.arange(len(values) - 1, -1, -1) / half_life)
    decay /= decay.sum()
    mean = decay @ values
    fast = np.sqrt(decay @ ((values - mean) ** 2))
    scales = np.maximum(std, fast)
    return corr * np.outer(scales, scales) * 252, stress_used


def conditional_core_weights(cov, cross, reserve_weight, budgets, core_exposure):
    """Positive Newton solve: w_i*(Cw+q*c)_i = lambda*b_i, sum(w)=e."""
    c = np.asarray(cov, dtype=float)
    b = np.asarray(budgets, dtype=float)
    cross = np.asarray(cross, dtype=float)
    if (
        core_exposure <= 0
        or reserve_weight < 0
        or c.shape != (len(b), len(b))
        or cross.shape != b.shape
        or not np.isfinite(cross).all()
    ):
        raise AllocationError("Invalid conditional risk problem")
    trace = float(np.trace(c))
    if not np.isfinite(trace) or trace <= 0:
        raise AllocationError("Invalid covariance scale")
    unit = solve_risk_budget(c, b)
    c = c / trace
    background = reserve_weight * cross / trace
    w = unit * core_exposure
    lam = float(w @ (c @ w + background))
    if lam <= 0:
        raise AllocationError("Nonpositive core risk with reserve")
    z = np.r_[w, lam]

    def residual(z):
        x = z[:-1]
        return np.r_[x * (c @ x + background) - z[-1] * b, x.sum() - core_exposure]

    for _ in range(100):
        f = residual(z)
        if np.max(np.abs(f)) < 1e-12:
            return z[:-1]
        x = z[:-1]
        jac = np.zeros((len(z), len(z)))
        jac[:-1, :-1] = np.diag(c @ x + background) + np.diag(x) @ c
        jac[:-1, -1] = -b
        jac[-1, :-1] = 1
        direction = np.linalg.solve(jac, f)
        rate = 1.0
        for _ in range(60):
            candidate = z - rate * direction
            if (candidate > 0).all() and np.linalg.norm(
                residual(candidate)
            ) < np.linalg.norm(f):
                z = candidate
                break
            rate *= 0.5
        else:
            raise AllocationError("Conditional core risk solve failed")
    raise AllocationError("Conditional core risk solve exceeded iterations")


class ForecastCalibration:
    def __init__(self, half_life=63, warmup=63, maximum=2.0):
        if (
            not np.isfinite(half_life)
            or half_life <= 0
            or warmup < 1
            or not np.isfinite(maximum)
            or maximum < 1
        ):
            raise AllocationError("Invalid calibration controls")
        self.alpha = 1 - np.exp(-np.log(2) / half_life)
        self.warmup = warmup
        self.maximum = maximum
        self.mean_square = 1.0
        self.count = 0

    def observe(self, realized_return, raw_daily_variance):
        if (
            not np.isfinite(realized_return)
            or not np.isfinite(raw_daily_variance)
            or raw_daily_variance < 0
        ):
            raise AllocationError("Invalid realized/forecast risk pair")
        if raw_daily_variance > 1e-14:
            square = min(realized_return**2 / raw_daily_variance, 36.0)
            self.mean_square = (1 - self.alpha) * self.mean_square + self.alpha * square
            self.count += 1

    @property
    def multiplier(self):
        return (
            float(np.clip(np.sqrt(self.mean_square), 1, self.maximum))
            if self.count >= self.warmup
            else 1.0
        )


def coverage_report(realized, forecast_sigma):
    r = np.asarray(realized, dtype=float)
    s = np.asarray(forecast_sigma, dtype=float)
    valid = np.isfinite(r) & np.isfinite(s) & (s > 1e-8)
    r, s = r[valid], s[valid]
    if len(r) < 63:
        raise AllocationError("Insufficient risk forecast outcomes")
    exceed = r < -norm.ppf(0.95) * s
    hits = int(exceed.sum())
    n = len(r)
    frequency = hits / n
    eps = 1e-15
    phat = np.clip(frequency, eps, 1 - eps)
    lr = -2 * (
        (n - hits) * np.log(0.95)
        + hits * np.log(0.05)
        - (n - hits) * np.log(1 - phat)
        - hits * np.log(phat)
    )
    interval = binomtest(hits, n, 0.05).proportion_ci(confidence_level=0.95)
    transitions = np.array(
        [
            [np.sum((exceed[:-1] == i) & (exceed[1:] == j)) for j in (False, True)]
            for i in (False, True)
        ]
    )

    def fitted_log_likelihood(counts):
        total = counts.sum()
        if total == 0:
            return 0.0
        return float(np.sum(xlogy(counts, counts / total)))

    independent = fitted_log_likelihood(transitions.sum(axis=0))
    markov = sum(fitted_log_likelihood(row) for row in transitions)
    independence_lr = max(0.0, 2 * (markov - independent))
    return {
        "observations": n,
        "var95_exceedances": hits,
        "var95_exceedance_frequency": frequency,
        "binomial_frequency_ci95": [float(interval.low), float(interval.high)],
        "kupiec_unconditional_coverage_pvalue": float(chi2.sf(max(lr, 0), 1)),
        "christoffersen_independence_pvalue": float(chi2.sf(independence_lr, 1)),
        "christoffersen_conditional_coverage_pvalue": float(
            chi2.sf(max(lr, 0) + independence_lr, 2)
        ),
        "exceedance_transitions": transitions.tolist(),
        "realized_to_forecast_volatility_ratio": float(
            r.std(ddof=1) / np.sqrt(np.mean(s * s))
        ),
        "interpretation": "Coverage diagnostic under a normal zero-mean VaR model; not an institutional certification",
    }


class InstitutionalPortfolio:
    def __init__(self, plan_path=DEFAULT_PLAN):
        from global_asset_registry import resolve_policy
        self.config = resolve_policy(json.loads(Path(plan_path).read_text()))
        c = self.config
        if (
            c.get("mode") != "RESEARCH_ONLY"
            or c.get("production_activation") is not False
        ):
            raise AllocationError("Refinement must remain research-only")
        if (
            not 0 < c["risk_budget_tolerance"] <= 1e-6
            or not 0 < c["maximum_asset_weight"] <= 0.25
        ):
            raise AllocationError("Risk limits cannot be loosened")
        if c["stress_exposure_ceiling"] > 0.4 or c["stress_volatility_ceiling"] > 0.05:
            raise AllocationError("Stress limits cannot be loosened")
        for name in ("maximum_full_account_risk_share", "maximum_reserve_weight"):
            if not 0 < c[name] <= 0.25:
                raise AllocationError("Risk and reserve caps cannot be loosened")
        if not 0.05 <= c["minimum_cash"] < 1 or c["rebalance_sessions"] < 1:
            raise AllocationError("Invalid cash or scheduling controls")
        for weights in list(c["anchors"].values()) + list(c["macro_views"].values()):
            if (
                len(weights) != 5
                or min(weights) <= 0
                or not np.isclose(sum(weights), 1, atol=1e-12)
            ):
                raise AllocationError("Invalid economic risk anchor")

    def allocate(
        self,
        returns,
        covariance,
        signal,
        parameters,
        *,
        reserve_symbol,
        account_drawdown,
        calibration_multiplier,
        decision_time,
        use_trend=True,
    ):
        if aware(signal["as_of"]) > aware(decision_time):
            raise AllocationError("Future regime signal")
        if (
            not isinstance(returns, pd.DataFrame)
            or not isinstance(returns.index, pd.DatetimeIndex)
            or not returns.index.is_unique
            or not returns.index.is_monotonic_increasing
            or len(returns) < 252
            or not returns.columns.is_unique
            or not set(returns.columns) <= set(DIVERSIFIED_ASSETS)
            or not np.isfinite(returns.to_numpy()).all()
            or (returns <= -1).any().any()
            or pd.Timestamp(returns.index[-1]).date()
            > aware(decision_time).tz_convert("America/New_York").date()
        ):
            raise AllocationError("Invalid historical risk inputs")
        if (
            reserve_symbol not in {"SGOV", "SHY", None}
            or reserve_symbol is not None
            and reserve_symbol not in returns
        ):
            raise AllocationError("Invalid eligible Treasury reserve")
        if set(parameters) != set(self.config["candidate_grid"]) or any(
            parameters[k] not in self.config["candidate_grid"][k] for k in parameters
        ):
            raise AllocationError("Unknown refinement parameters")
        if (
            not 1
            <= calibration_multiplier
            <= self.config["maximum_calibration_multiplier"]
            or not -1 <= account_drawdown <= 0
        ):
            raise AllocationError("Invalid risk controller inputs")
        c = self.config
        symbols = list(returns.columns)
        matrix = np.asarray(covariance, dtype=float)
        if (
            matrix.shape != (len(symbols), len(symbols))
            or not np.isfinite(matrix).all()
            or not np.allclose(matrix, matrix.T, atol=1e-12)
            or np.linalg.eigvalsh(matrix).min() <= 0
        ):
            raise AllocationError("Invalid institutional covariance")
        probabilities = np.array([signal["probabilities"][r] for r in REGIMES])
        if (
            not np.isfinite(probabilities).all()
            or (probabilities < 0).any()
            or not np.isclose(probabilities.sum(), 1, atol=1e-12)
        ):
            raise AllocationError("Invalid macro allocation scores")
        core = [s for sleeve in c["sleeves"].values() for s in sleeve if s in symbols]
        indices = [symbols.index(s) for s in core]
        cc = matrix[np.ix_(indices, indices)]
        anchor = np.array(c["anchors"][parameters["anchor"]])
        view = sum(
            signal["probabilities"][r] * np.array(c["macro_views"][r]) for r in REGIMES
        )
        fraction = parameters["macro_view_weight"]
        exposure = 1 - c["minimum_cash"]
        ceiling = parameters["volatility_ceiling"]
        if signal["stress"]:
            exposure = min(exposure, c["stress_exposure_ceiling"])
            ceiling = min(ceiling, c["stress_volatility_ceiling"])
        if c.get("maximum_drawdown") is not None and account_drawdown <= -0.05:
            ceiling = min(ceiling, 0.04)
        if c.get("maximum_drawdown") is not None and account_drawdown <= -0.08:
            exposure = min(exposure, 0.25)
            ceiling = min(ceiling, 0.03)
        for _ in range(8):
            sleeve_b = (1 - fraction) * anchor + fraction * view
            # A modest long-only trend overlay changes risk budgets, not observed returns.
            if use_trend and signal.get("trend_weak", False):
                reduction = 0.5 * sleeve_b[0]
                sleeve_b[0] -= reduction
                sleeve_b[1:] += reduction * sleeve_b[1:] / sleeve_b[1:].sum()
            # Bound single-instrument sleeves before solving, leaving room for
            # cross-risk from the separately invested Treasury reserve.
            caps = np.array(
                [
                    0.24 if len([s for s in group if s in core]) == 1 else 1.0
                    for group in c["sleeves"].values()
                ]
            )
            free = np.ones(5, dtype=bool)
            bounded = np.zeros(5)
            for _cap in range(6):
                trial = sleeve_b[free] / sleeve_b[free].sum() * (1 - bounded.sum())
                ids = np.flatnonzero(free)
                over = trial > caps[free]
                if not over.any():
                    bounded[ids] = trial
                    break
                bounded[ids[over]] = caps[ids[over]]
                free[ids[over]] = False
            sleeve_b = bounded
            budgets = {}
            for j, members in enumerate(c["sleeves"].values()):
                eligible = [s for s in members if s in core]
                if not eligible:
                    raise AllocationError("Missing required All Weather proxy sleeve")
                total = sum(members[s] for s in eligible)
                budgets.update({s: sleeve_b[j] * members[s] / total for s in eligible})
            b = np.array([budgets[s] for s in core])
            unit = solve_risk_budget(cc, b)
            initial = min(
                exposure,
                ceiling / (np.sqrt(unit @ cc @ unit) * calibration_multiplier),
                c["maximum_asset_weight"] / unit.max(),
            )
            reserve = (
                min(c["maximum_reserve_weight"], max(0, exposure - initial))
                if reserve_symbol
                else 0.0
            )
            ri = symbols.index(reserve_symbol) if reserve_symbol else None
            cross = matrix[indices, ri] if ri is not None else np.zeros(len(core))
            w = (
                conditional_core_weights(cc, cross, reserve, b, initial)
                if reserve
                else unit * initial
            )
            full = np.zeros(len(symbols))
            full[indices] = w
            if ri is not None:
                full[ri] = reserve
            raw_vol = float(np.sqrt(full @ matrix @ full))
            losses = -(returns.to_numpy() @ full)
            es = max(
                float(np.sort(losses)[-int(np.ceil(0.05 * len(losses))) :].mean()), 0
            )
            es_cap = (
                c["stress_expected_shortfall_daily_ceiling"]
                if signal["stress"]
                else c["expected_shortfall_daily_ceiling"]
            )
            scale = min(
                1.0,
                exposure / full.sum(),
                c["maximum_asset_weight"] / full.max(),
                ceiling / (raw_vol * calibration_multiplier),
                es_cap / es if es else 1.0,
            )
            full *= scale
            variance = float(full @ matrix @ full)
            account_rc = full * (matrix @ full) / variance
            conditional = account_rc[indices] / account_rc[indices].sum()
            error = float(np.max(np.abs(conditional - b)))
            if error > c["risk_budget_tolerance"]:
                raise AllocationError(
                    "Conditional core risk-budget reconciliation failed"
                )
            if account_rc.max() <= c["maximum_full_account_risk_share"] + 1e-6:
                weights = {s: 0.0 for s in DIVERSIFIED_ASSETS}
                weights.update(dict(zip(symbols, map(float, full))))
                return {
                    "mode": "RESEARCH_ONLY",
                    "risk_contract": c["risk_contract"],
                    "weights": weights,
                    "cash": float(1 - full.sum()),
                    "reserve_symbol": reserve_symbol,
                    "reserve_weight": float(full[ri]) if ri is not None else 0.0,
                    "core_risk_targets": budgets,
                    "conditional_core_risk_shares": dict(
                        zip(core, map(float, conditional))
                    ),
                    "full_account_risk_shares": dict(
                        zip(symbols, map(float, account_rc))
                    ),
                    "risk_budget_error": error,
                    "raw_estimated_volatility": raw_vol * scale,
                    "calibrated_estimated_volatility": raw_vol
                    * scale
                    * calibration_multiplier,
                    "estimated_daily_es95": es * scale,
                    "calibration_multiplier": calibration_multiplier,
                    "effective_macro_view_weight": fraction,
                    "exposure_ceiling": exposure,
                    "volatility_ceiling": ceiling,
                    "regime": signal["regime"],
                    "decision_time": aware(decision_time).isoformat(),
                }
            fraction *= 0.5
        raise AllocationError(
            "Full-account risk cap is infeasible; views were not authorized"
        )
