"""Source-bound economic diagnostics; never changes or promotes a strategy.

Fixed-decision cash/cost sensitivities, ex-ante risk-budget references,
observed three-year reference frontiers, and explicit stress review gates.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from compare_portfolio_models import rebalance_fee
from goalportfolio import AccountDrawdownGuard
from live_strategy_training import _metrics
from strategy_integrity import file_hash, strict_json
from strategy_report import load_training_report
from strategy_receipts import atomic_json
from assetuniverse import DIVERSIFIED_ASSETS
from macro_allocation_lab import prepare_lab
from investmentcatalog import catalogue
from assetroles import ASSET_ROLES

REFERENCES = {
    "All_Weather_style_proxy": {
        "SPY": 0.30,
        "TLT": 0.40,
        "IEF": 0.15,
        "GLD": 0.075,
        "DBC": 0.075,
    },
    "Balanced_reference": {"SPY": 0.60, "IEF": 0.40},
    "SPY_reference": {"SPY": 1.0},
}
VOLATILITY_GRID = [0.02, 0.04, 0.06, 0.08, 0.10]
RATE_ASSETS = {"TLT", "IEF", "IGOV", "TIP", "SHY", "SGOV"}


def replay(returns, targets, cash_returns=None, *, cost_rate=0.0015, protect=False):
    """Execution-close targets known before that close; old holdings earn return.

    Optional benchmark guard uses its own peak; reduces on the next close and
    can recover only at a scheduled target. This is not the four-strategy solver.
    """
    if (
        returns.empty
        or returns.index.has_duplicates
        or not returns.index.is_monotonic_increasing
    ):
        raise ValueError("Ordered observed return sessions required")
    if not np.isfinite(cost_rate) or not 0 <= cost_rate <= 0.01:
        raise ValueError("Invalid cost rate")
    symbols = list(returns.columns)
    cash_returns = (
        pd.Series(0.0, index=returns.index)
        if cash_returns is None
        else cash_returns.reindex(returns.index)
    )
    if not np.isfinite(cash_returns).all() or (cash_returns <= -1).any():
        raise ValueError("Complete observed cash returns required")
    w = np.zeros(len(symbols))
    cash = nav = 1.0
    guard = AccountDrawdownGuard(0.02, 0.04)
    factor = 1.0
    pending = None
    rows = []
    for date, observation in returns.iterrows():
        r = observation.to_numpy(dtype=float)
        held = w > 0
        if not np.isfinite(r[held]).all() or (r[held] <= -1).any():
            raise ValueError("Unpriceable held instrument")
        opening = w.copy()
        opening_cash = cash
        old_nav = nav
        asset_pnl = np.zeros(len(w))
        asset_pnl[held] = opening[held] * r[held]
        cash_pnl = opening_cash * float(cash_returns.loc[date])
        growth = 1 + asset_pnl.sum() + cash_pnl
        if not np.isfinite(growth) or growth <= 0:
            raise ValueError("Invalid portfolio growth")
        dollars = opening + asset_pnl
        w = dollars / growth
        cash = opening_cash * (1 + float(cash_returns.loc[date])) / growth
        fee = turnover = 0.0
        target = targets.get(date)
        if target is not None:
            target = np.array([target.get(s, 0.0) for s in symbols]) * factor
        elif protect and pending is not None:
            target = pending
        if target is not None:
            if (
                not np.isfinite(target).all()
                or target.min() < 0
                or target.sum() > 1 + 1e-10
            ):
                raise ValueError("Invalid unlevered target")
            fee = rebalance_fee(w, target, cost_rate)
            turnover = float(np.abs(target * (1 - fee) - w).sum())
            w = target.copy()
            cash = float(1 - w.sum())
        cost = old_nav * growth * fee
        net = growth * (1 - fee) - 1
        nav *= 1 + net
        dd, new_factor = guard.update(nav)
        pending = (
            w * min(1, new_factor / max(factor, 1e-12))
            if protect and new_factor < factor
            else None
        )
        factor = new_factor if protect else 1.0
        row = {
            "date": date,
            "return": net,
            "gross_return": growth - 1,
            "equity": nav,
            "cash": cash,
            "cash_at_open": opening_cash,
            "turnover": turnover,
            "cost_as_initial_capital": cost,
            "cash_profit_initial": old_nav * cash_pnl,
            "account_drawdown": dd,
            "cash_locked": guard.locked if protect else False,
        }
        row.update(
            {f"pnl_{s}": float(old_nav * asset_pnl[j]) for j, s in enumerate(symbols)}
        )
        rows.append(row)
    return pd.DataFrame(rows).set_index("date")


def risk_targets(daily, dates, weights, budgets, *, every=21, execution_dates=None):
    """All vol estimates end at the preceding observed close, never the fill."""
    symbols = list(weights)
    portfolio = (
        daily[symbols].mul(pd.Series(weights)).sum(axis=1, min_count=len(symbols))
    )
    sigma = portfolio.rolling(252, min_periods=252).std(ddof=1).shift(1) * np.sqrt(252)
    result = {}
    allowed = (
        set(execution_dates) if execution_dates is not None else set(dates[::every])
    )
    for date in dates:
        if date not in allowed:
            continue
        budget = float(budgets.loc[date] if isinstance(budgets, pd.Series) else budgets)
        vol = float(sigma.loc[date])
        if not np.isfinite(budget) or budget < 0 or not np.isfinite(vol) or vol <= 0:
            raise ValueError("Prior 252-session volatility history required")
        scale = min(0.95, budget / vol)
        result[date] = {s: float(w * scale) for s, w in weights.items()}
    return result


def load_cash_history(path, dates):
    """Optional operator-attested realized cash history; examples are rejected.

    Authenticates file/evidence hashes, not the economic truth of a bank record.
    User-specific cash sourcing and independent approval remain external gates.
    """
    manifest = strict_json(path)
    root = Path(path).parent
    if (
        manifest.get("schema_version") != 1
        or manifest.get("currency") != "USD"
        or manifest.get("verified") is not True
        or not manifest.get("reviewer")
        or not manifest.get("source")
        or not manifest.get("evidence")
    ):
        raise ValueError("Verified USD cash history and reviewer evidence required")
    for item in [manifest["returns"], *manifest["evidence"]]:
        if (
            Path(item["file"]).name != item["file"]
            or file_hash(root / item["file"]) != item["sha256"]
        ):
            raise ValueError("Cash source integrity failure")
    frame = pd.read_csv(root / manifest["returns"]["file"], parse_dates=["date"])
    if frame.date.duplicated().any() or not frame.date.is_monotonic_increasing:
        raise ValueError("Ordered unique cash dates required")
    rates = pd.Series(pd.to_numeric(frame.net_return).to_numpy(), index=frame.date)
    selected = rates.reindex(dates)
    if not np.isfinite(selected).all() or (selected <= -1).any():
        raise ValueError("Complete finite net cash returns required")
    return selected, {
        "status": "OPERATOR_ATTESTED_OBSERVED_CASH_HISTORY",
        "source": manifest["source"],
        "reviewer": manifest["reviewer"],
        "manifest_sha256": file_hash(path),
        "limitation": "Local source attestation, not independent bank authentication; historical realized accrual, not a forecast.",
    }


def attribution(frame, trades, features):
    reasons = {}
    pending_data_reentry = False
    costs = defaultdict(float)
    events = Counter()
    for trade in trades:
        date = pd.Timestamp(trade["date"])
        decision = str(pd.Timestamp(trade["decision_time"]).date())
        if (
            pd.Timestamp(trade["decision_time"]).tzinfo is None
            or decision >= trade["date"]
        ):
            raise ValueError("Decision must precede execution session")
        signal = features.get(decision, {})
        if signal.get("macro_valid") is False:
            reason = "DATA_QUARANTINE"
            pending_data_reentry = True
        elif (
            pending_data_reentry
            and frame.loc[date, "cash_at_open"] > 0.999
            and sum(trade["weights"].values()) > 0
        ):
            reason = "DATA_RECOVERY_REENTRY"
            pending_data_reentry = False
        elif trade.get("cash_lock"):
            reason = "DRAWDOWN_LOCK"
        elif trade.get("account_drawdown_factor", 1) < 1:
            reason = "DRAWDOWN_SIZING"
        else:
            reason = "JOINT_SCHEDULE_RISK_OR_REGIME"
        reasons[trade["date"]] = reason
        costs[reason] += float(frame.loc[date, "cost_as_initial_capital"])
        events[reason] += 1
    assets = {c[4:]: float(frame[c].sum()) for c in frame if c.startswith("pnl_")}
    cost = float(frame.cost_as_initial_capital.sum())
    cash = float(frame.cash_profit_initial.sum())
    if not np.isclose(
        sum(assets.values()) + cash - cost, float(frame.equity.iloc[-1] - 1), atol=1e-10
    ):
        raise ValueError("Profit attribution failed to reconcile")
    return {
        "asset_profit_starting_capital": assets,
        "cash_profit_starting_capital": cash,
        "cost_starting_capital": cost,
        "cost_by_first_supported_trigger": dict(costs),
        "trade_count_by_first_supported_trigger": dict(events),
        "classification": "Evidence-supported primary tags; joint triggers and causal counterfactuals are not identified.",
        "net_profit_starting_capital": float(frame.equity.iloc[-1] - 1),
    }


def stress_review(weights, covariance, symbols):
    """Explicit hypothetical ETF-return shocks, not estimated durations or probabilities."""
    equity = set(DIVERSIFIED_ASSETS) - {
        "TLT",
        "IEF",
        "SHY",
        "IGOV",
        "SGOV",
        "TIP",
        "LQD",
        "HYG",
        "GLD",
        "SLV",
        "DBC",
    }
    templates = {
        "growth_crash": {
            **dict.fromkeys(equity, -0.30),
            "TLT": 0.12,
            "IEF": 0.05,
            "SHY": 0.005,
            "IGOV": 0.03,
            "SGOV": -0.001,
            "TIP": -0.04,
            "LQD": -0.10,
            "HYG": -0.20,
            "GLD": 0.05,
            "SLV": -0.15,
            "DBC": -0.30,
        },
        "inflation_rate_shock": {
            **dict.fromkeys(equity, -0.18),
            "TLT": -0.25,
            "IEF": -0.12,
            "SHY": -0.02,
            "IGOV": -0.15,
            "SGOV": -0.005,
            "TIP": -0.15,
            "LQD": -0.18,
            "HYG": -0.20,
            "GLD": 0.03,
            "SLV": 0.04,
            "DBC": 0.15,
        },
        "stagflation": {
            **dict.fromkeys(equity, -0.25),
            "TLT": -0.20,
            "IEF": -0.10,
            "SHY": -0.02,
            "IGOV": -0.12,
            "SGOV": -0.005,
            "TIP": -0.06,
            "LQD": -0.16,
            "HYG": -0.22,
            "GLD": 0.10,
            "SLV": 0.05,
            "DBC": 0.15,
        },
        "liquidity_dislocation": {
            **dict.fromkeys(equity, -0.25),
            "TLT": -0.10,
            "IEF": -0.07,
            "SHY": -0.02,
            "IGOV": -0.12,
            "SGOV": -0.005,
            "TIP": -0.10,
            "LQD": -0.15,
            "HYG": -0.25,
            "GLD": -0.12,
            "SLV": -0.25,
            "DBC": -0.20,
        },
    }
    losses = {
        name: -sum(weights.get(s, 0) * shock[s] for s in weights)
        for name, shock in templates.items()
    }
    w = np.array([weights.get(s, 0) for s in symbols])
    variance = float(w @ covariance @ w)
    rc = w * (covariance @ w) / variance if variance > 1e-15 else np.zeros(len(w))
    return {
        "capital_rate_sensitive_and_reserve": sum(
            weights.get(s, 0) for s in RATE_ASSETS
        ),
        "equity_capital": sum(weights.get(s, 0) for s in equity),
        "hypothetical_losses": losses,
        "maximum_hypothetical_loss": max(losses.values()),
        "five_percent_stress_review_pass": max(losses.values()) <= 0.05,
        "per_asset_capital_pass": max(weights.values(), default=0) <= 0.250001,
        "per_asset_variance_pass": float(rc.max()) <= 0.250001,
        "measurement_basis": "Assumed simultaneous close-to-close ETF shocks before fees; not forecasts or calibrated event probabilities.",
        "duration_dv01_fx_limits": "UNVERIFIED_EXPOSURE_METADATA_REQUIRED",
        "scenarios": templates,
    }


def paired_interval(a, b, *, block=21, paths=2000, seed=103126):
    if not a.index.equals(b.index) or len(a) < block or block < 2:
        raise ValueError("Aligned history and valid block length required")
    difference = (a - b).to_numpy(dtype=float)
    if not np.isfinite(difference).all():
        raise ValueError("Finite paired returns required")
    rng = np.random.default_rng(seed)
    n = len(difference)
    count = int(np.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=(paths, count))
    ids = (starts[:, :, None] + np.arange(block)).reshape(paths, -1)[:, :n]
    annual = difference[ids].mean(axis=1) * 252
    return {
        "block_sessions": block,
        "paths": paths,
        "seed": seed,
        "annualized_mean_excess": float(difference.mean() * 252),
        "p025": float(np.quantile(annual, 0.025)),
        "p975": float(np.quantile(annual, 0.975)),
        "interpretation": "Descriptive paired moving-block bootstrap; not independent validation, a forecast or a multiple-testing-adjusted promotion test.",
    }


def menu_review(prices, report):
    panel = prices.pct_change(fill_method=None).tail(252)
    out = []
    proxies = ["SPY", "IEF", "TIP", "GLD", "DBC"]
    x = panel[proxies].to_numpy()
    scale = x.std(axis=0, ddof=0)
    if not np.isfinite(x).all() or (scale <= 0).any():
        raise ValueError("Complete proxy history required")
    z = (x - x.mean(axis=0)) / scale
    for symbol, instrument in catalogue().items():
        series = panel[symbol]
        row = {
            "symbol": symbol,
            "bucket": instrument.bucket,
            "economic_role": ASSET_ROLES[symbol],
            "benchmark_only": instrument.benchmark_only,
            "current_strategy_weights": {
                r["name"]: r["candidate"]["weights"].get(symbol, 0)
                for r in report["strategies"]
            },
        }
        if not np.isfinite(series).all():
            row["status"] = "INCOMPLETE_ACTUAL_252_RETURN_HISTORY"
        else:
            y = series.to_numpy()
            beta = (
                np.linalg.solve(
                    z.T @ z + 10 * np.eye(len(proxies)), z.T @ (y - y.mean())
                )
                / scale
            )
            row.update(
                status="DESCRIPTIVE_OBSERVED_HISTORY",
                annual_volatility=float(series.std() * np.sqrt(252)),
                observed_252_session_return=float(np.prod(1 + y) - 1),
                correlation_to_SPY=float(series.corr(panel.SPY)),
                ridge_proxy_betas=dict(zip(proxies, map(float, beta))),
            )
        out.append(row)
    return {
        "instruments": out,
        "proxy_method": "252 observed returns; standardized ridge with penalty 10 on SPY/IEF/TIP/GLD/DBC. Descriptive correlated ETF proxies, not causal factors, duration, FX decomposition or return forecasts.",
        "selection": "No menu asset promoted; ALLW remains benchmark-only and DBMF remains outside the fixed four-strategy maps.",
    }


def economic_gate(result):
    observed_cash = (
        result["cash_baseline"]["status"] == "OPERATOR_ATTESTED_OBSERVED_CASH_HISTORY"
    )
    rows = []
    for strategy in result["strategies"]:
        flags = {
            "verified_user_cash_history": observed_cash,
            "positive_return_over_zero_cash": strategy["archived_metrics"][
                "total_return"
            ]
            > 0,
            "hypothetical_five_percent_stress_screen": strategy["stress_review"][
                "five_percent_stress_review_pass"
            ],
            "positive_lower_bound_all_declared_reference_sensitivities": all(
                interval["p025"] > 0
                for r in strategy["matched_references"]
                for interval in r["paired_block_intervals"].values()
            ),
        }
        rows.append(
            {
                "strategy": strategy["name"],
                "checks": flags,
                "status": "FAILED_DESCRIPTIVE_SCREEN"
                if not all(flags.values())
                else "INDEPENDENT_REVIEW_REQUIRED",
                "promotion_enabled": False,
            }
        )
    return {
        "status": "BLOCKED",
        "strategies": rows,
        "independent_validation": "NOT_GRANTED_BY_THIS_ASSESSMENT",
        "three_year_live_evidence": "NOT_ESTABLISHED_BY_RETROSPECTIVE_COHORTS",
        "target_loss_combination": "NOT_DEMONSTRATED",
        "reason": "No winner selected, no risk limit relaxed, and no strategy or public release promoted.",
    }


def assess(bundle, output, *, cash_manifest=None):
    own_hash = file_hash(__file__)
    b = strict_json(bundle)
    report = load_training_report(b["training_report"])
    if not report["current_numerical_source_match"]:
        raise ValueError("Current source-matched report required")
    capture = strict_json(b["capture"])
    root = Path(b["capture"]).parent
    if file_hash(b["capture"]) != report["capture_sha256"]:
        raise ValueError("Capture mismatch")
    for name, h in capture["files"].items():
        if Path(name).name != name or file_hash(root / name) != h:
            raise ValueError("Capture integrity failure")
    prices = pd.read_csv(root / "prices.csv", index_col=0, parse_dates=True)
    daily = prices[list(DIVERSIFIED_ASSETS)].pct_change(fill_method=None)
    run = Path(b["training_report"]).parent
    features = {r["date"]: r for r in strict_json(run / "features.json")}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    strategies = []
    lab = prepare_lab(b["capture"], b["training_report"])
    cash_status = {
        "status": "BLOCKED_NO_VERIFIED_USER_CASH_HISTORY",
        "available_comparisons": [
            "ZERO_YIELD_UNINVESTED_CASH",
            "OBSERVED_SGOV_ETF_NOT_CASH",
        ],
    }
    for row in report["strategies"]:
        name = row["name"]
        original = pd.read_csv(run / f"{name}.csv", index_col=0, parse_dates=True)
        trades = strict_json(run / f"{name}-audit.json")["trades"]
        targets = {pd.Timestamp(t["date"]): t["weights"] for t in trades}
        if len(targets) != len(trades):
            raise ValueError("Duplicate trade date")
        returns = daily.reindex(original.index)
        frame = replay(returns, targets)
        for column in [
            "return",
            "equity",
            "cash",
            "cost_as_initial_capital",
            "turnover",
        ]:
            if not np.allclose(frame[column], original[column], atol=1e-10, rtol=1e-9):
                raise ValueError("Independent archived-path replay mismatch: " + column)
        a = attribution(frame, trades, features)
        cash_status_local = cash_status
        sensitivities = {
            "zero_cost_fixed_decisions": _metrics(
                replay(returns, targets, cost_rate=0)
            ),
            "thirty_bps_fixed_decisions": _metrics(
                replay(returns, targets, cost_rate=0.003)
            ),
            "SGOV_linked_cash_sensitivity_NOT_DEPOSIT_OR_EXECUTABLE_FUNDING": _metrics(
                replay(returns, targets, returns.SGOV)
            ),
        }
        if cash_manifest:
            cash_series, cash_status_local = load_cash_history(
                cash_manifest, returns.index
            )
            sensitivities["attested_cash_fixed_decisions"] = _metrics(
                replay(returns, targets, cash_series)
            )
        execution_dates = list(targets)
        budgets = pd.Series(0.0, index=returns.index)
        for t in trades:
            budgets.loc[t["date"]] = float(t.get("calibrated_estimated_volatility", 0))
        comparisons = []
        for ref, weights in REFERENCES.items():
            matched = risk_targets(
                daily, returns.index, weights, budgets, execution_dates=execution_dates
            )
            path = replay(returns, matched, protect=True)
            path.to_csv(output / f"{name}-{ref}-matched.csv")
            intervals = {
                str(block): paired_interval(
                    frame["return"], path["return"], block=block
                )
                for block in [21, 63]
            }
            comparisons.append(
                {
                    "paired_block_intervals": intervals,
                    "name": ref,
                    "mode": "PRIOR_CLOSE_VOL_BUDGET_AND_EXECUTION_DATE_MATCHED_REFERENCE",
                    "metrics": _metrics(path),
                    "mandate_approved": False,
                }
            )
        frame.to_csv(output / f"{name}-reconciled.csv")
        valid = original.macro_quadrant != "DATA_UNAVAILABLE"
        availability = {
            "unavailable_return_sessions": int((~valid).sum()),
            "total_sessions": len(original),
            "observed_net_pnl_unavailable_sessions": float(
                frame.loc[~valid, "return"]
                .mul(frame.equity.shift(1, fill_value=1).loc[~valid])
                .sum()
            ),
            "observed_net_pnl_available_sessions": float(
                frame.loc[valid, "return"]
                .mul(frame.equity.shift(1, fill_value=1).loc[valid])
                .sum()
            ),
            "limitations": "P&L segmentation, not an estimate of hypothetical returns with the missing data repaired.",
        }
        stress = stress_review(
            row["candidate"]["weights"], lab["covariance"], lab["active"]
        )
        strategies.append(
            {
                "name": name,
                "archived_metrics": row["metrics"],
                "replay_reconciled": True,
                "attribution": a,
                "availability": availability,
                "cash_history": cash_status_local,
                "fixed_decision_sensitivities": sensitivities,
                "matched_references": comparisons,
                "stress_review": stress,
                "economic_promotion": "BLOCKED_PENDING_INDEPENDENT_VALIDATION",
            }
        )
    evaluation_dates = pd.DatetimeIndex(
        pd.read_csv(run / "economic_balance.csv", index_col=0, parse_dates=True).index
    )
    baselines = {
        "zero_yield_uninvested_cash": _metrics(replay(daily.loc[evaluation_dates], {})),
        "SGOV_observed_ETF_not_cash": _metrics(
            replay(daily.loc[evaluation_dates], {evaluation_dates[0]: {"SGOV": 1.0}})
        ),
    }
    menu = menu_review(prices, report)
    # Fixed, predeclared grid: no candidate selected or production parameter changed.
    eligible = daily.SGOV.rolling(252, min_periods=252).count() >= 252
    dates = daily.index[eligible]
    frontier = []
    cohorts = []
    for ref, weights in REFERENCES.items():
        print("Evaluating predeclared three-year reference cohorts: " + ref, flush=True)
        for budget in VOLATILITY_GRID:
            for protect in [True, False]:
                cohort_rows = []
                for start in range(0, len(dates) - 755, 21):
                    window = dates[start : start + 756]
                    target = risk_targets(daily, window, weights, budget)
                    path = replay(daily.loc[window], target, protect=protect)
                    m = _metrics(path)
                    record = {
                        "reference": ref,
                        "annual_vol_budget": budget,
                        "protect": protect,
                        "start": str(window[0].date()),
                        "end": str(window[-1].date()),
                        **m,
                        "target_met": m["total_return"] >= 0.5,
                        "drawdown_met": m["max_drawdown"] >= -0.05,
                    }
                    cohort_rows.append(record)
                    cohorts.append(record)
                if not cohort_rows:
                    raise ValueError("Complete observed three-year cohorts required")
                frontier.append(
                    {
                        "reference": ref,
                        "annual_vol_budget": budget,
                        "protect": protect,
                        "cohorts": len(cohort_rows),
                        "median_three_year_return": float(
                            np.median([r["total_return"] for r in cohort_rows])
                        ),
                        "worst_three_year_return": min(
                            r["total_return"] for r in cohort_rows
                        ),
                        "worst_drawdown": min(r["max_drawdown"] for r in cohort_rows),
                        "target_frequency": float(
                            np.mean([r["target_met"] for r in cohort_rows])
                        ),
                        "joint_target_drawdown_frequency": float(
                            np.mean(
                                [
                                    r["target_met"] and r["drawdown_met"]
                                    for r in cohort_rows
                                ]
                            )
                        ),
                        "role": "OVERLAPPING_RETROSPECTIVE_REFERENCE_COHORTS_NOT_DEPLOYABLE_CANDIDATES",
                    }
                )
    pd.DataFrame(cohorts).to_csv(output / "three-year-cohorts.csv", index=False)
    pd.DataFrame(frontier).to_csv(output / "reference-frontier.csv", index=False)
    result = {
        "schema_version": 1,
        "status": "ECONOMIC_ASSESSMENT_SHADOW_ONLY",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market_session": report["market_session"],
        "evaluation": report["evaluation"],
        "strategies": strategies,
        "frontier": frontier,
        "goal": {
            "three_year_return": 0.5,
            "annual_compound_required": 1.5 ** (1 / 3) - 1,
            "drawdown_preference": 0.05,
            "institutional_promotion": "BLOCKED_NO_DEMONSTRATED_ROBUST_FEASIBILITY",
        },
        "observed_baselines": baselines,
        "asset_menu": menu,
        "cash_baseline": cash_status
        if not cash_manifest
        else strategies[0]["cash_history"],
        "sources": {
            "training_report": file_hash(b["training_report"]),
            "capture": file_hash(b["capture"]),
            "module": file_hash(__file__),
        },
        "limitations": [
            "No weights, approved strategy sources, investor plans or prospective cohort changed.",
            "SGOV adjusted ETF returns are observed reserve evidence, not user cash-account returns; linked-cash sensitivity holds original decisions fixed and omits funding trades/risk feedback.",
            "Matched references use only prior-close volatility and archived planned risk budgets/known fill dates; their realized volatility need not exactly match. They are not standalone or mandate-approved portfolios.",
            "Frontier references can exceed per-ETF/factor mandates; no leverage. The grid is descriptive, not an optimizer or promise of feasibility.",
            "Overlapping 756-session cohorts and a retrospectively selected universe are not independent prospective tests. Cash proxy common history excludes pre-SGOV crises.",
            "Guard comparisons retain 2% de-risking and permanent 4% lock; unprotected runs are diagnostics only. No risk preference was relaxed.",
            "Scenario shocks are explicit assumptions before trading costs, not calibrated events or measured DV01. No stress test guarantees a drawdown cap.",
        ],
        "execution_enabled": False,
        "release_approved": False,
    }
    if file_hash(__file__) != own_hash or any(
        file_hash(name) != h for name, h in report["source_hashes"].items()
    ):
        raise ValueError("Assessment source changed during computation")
    result["economic_acceptance"] = economic_gate(result)
    result["sources"]["dependencies"] = {
        name: file_hash(name)
        for name in [
            "compare_portfolio_models.py",
            "goalportfolio.py",
            "live_strategy_training.py",
            "strategy_report.py",
            "strategy_integrity.py",
            "macro_allocation_lab.py",
            "research/four_macro_strategies.json",
            "investmentcatalog.py",
            "assetroles.py",
        ]
    }
    result["artifacts"] = {
        p.name: file_hash(p) for p in output.iterdir() if p.is_file()
    }
    atomic_json(output / "economic-assessment.json", result)
    print(
        pd.DataFrame(
            [
                {
                    "strategy": s["name"],
                    "return": s["archived_metrics"]["total_return"],
                    "cash_SGOV_sensitivity": s["fixed_decision_sensitivities"][
                        "SGOV_linked_cash_sensitivity_NOT_DEPOSIT_OR_EXECUTABLE_FUNDING"
                    ]["total_return"],
                    "unavailable_sessions": s["availability"][
                        "unavailable_return_sessions"
                    ],
                    "worst_hypothetical_loss": s["stress_review"][
                        "maximum_hypothetical_loss"
                    ],
                }
                for s in strategies
            ]
        ).to_string(index=False),
        flush=True,
    )
    print("Assessment:", output / "economic-assessment.json", flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle",
        type=Path,
        default=Path("var/investor-dashboard/latest-strategy-run.json"),
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--cash-manifest", type=Path)
    args = parser.parse_args()
    output = args.output or Path("var/economic-assessments") / datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%S%fZ")
    assess(args.bundle, output, cash_manifest=args.cash_manifest)
