"""Read-only forward outcome, turnover, risk and feature-drift diagnostics."""

import numpy as np
from strategy_monthly_report import read_events


def feature_drift(features, *, minimum=63):
    from fourregimestrategies import FEATURES

    if len(features) < 315:
        return dict(status="INSUFFICIENT_HISTORY", features={})
    recent = [r for r in features[-63:] if r.get("macro_valid", False)]
    reference = [r for r in features[-315:-63] if r.get("macro_valid", False)]
    if min(len(recent), len(reference)) < minimum:
        return dict(
            status="INSUFFICIENT_VALID_INPUTS",
            recent=len(recent),
            reference=len(reference),
            features={},
        )
    output = {}
    for name in FEATURES:
        a = np.array([r[name] for r in reference], float)
        b = np.array([r[name] for r in recent], float)
        if not np.isfinite(a).all() or not np.isfinite(b).all():
            raise ValueError("Nonfinite drift observations")
        bins = np.unique(
            np.r_[
                -np.inf,
                np.quantile(a, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]),
                np.inf,
            ]
        )
        if len(bins) < 3:
            output[name] = None
            continue
        x = np.histogram(a, bins)[0] + 0.5
        y = np.histogram(b, bins)[0] + 0.5
        x = x / x.sum()
        y = y / y.sum()
        output[name] = float(np.sum((y - x) * np.log(y / x)))
    return dict(
        status="DESCRIPTIVE_DRIFT",
        features=output,
        review_features=[k for k, v in output.items() if v is not None and v > 0.2],
        limitation="PSI 0.2 is a declared review heuristic, not a calibrated statistical alarm or permission to refit.",
    )


def analyze(database, *, risk_forecasts=()):
    events = read_events(database)
    if not events:
        return dict(status="NO_OBSERVATIONS", strategies={})
    last = events[-1][0]
    strategies = {}
    for name, state in last["states"].items():
        marks = [m for e, _ in events for m in e["marks"].get(name, [])]
        returns = np.array([m["net_return"] for m in marks])
        if not np.isfinite(returns).all():
            raise ValueError("Invalid forward returns")
        forecast_checks = []
        for f in risk_forecasts:
            if f["strategy"] != name:
                continue
            sample = [
                m
                for m in marks
                if f["first_session"] <= m["session"] <= f["last_session"]
            ]
            from datetime import datetime

            issued = datetime.fromisoformat(f["issued_at"])
            if issued.tzinfo is None or issued.date().isoformat() >= f["first_session"]:
                raise ValueError("Risk forecast must precede its full return session")
            if len(sample) != f["sessions"]:
                forecast_checks.append(
                    dict(id=f["id"], status="PENDING_OR_MISSING_RETURNS")
                )
                continue
            gross = np.array(
                [(1 + m["net_return"]) / (1 - m["fee_fraction"]) - 1 for m in sample]
            )
            predicted = f["annual_volatility"]
            realized = float(gross.std(ddof=1) * np.sqrt(252))
            forecast_checks.append(
                dict(
                    id=f["id"],
                    status="MATURED_GROSS_PRICE_RISK",
                    realized=realized,
                    predicted=predicted,
                    ratio=realized / predicted if predicted > 0 else None,
                )
            )
        strategies[name] = dict(
            return_sessions=len(marks),
            total_return=state["nav"] - 1,
            maximum_drawdown=state["maximum_drawdown"],
            realized_annual_volatility=float(returns.std(ddof=1) * np.sqrt(252))
            if len(returns) >= 21
            else None,
            annual_turnover=float(
                sum(m["traded_notional_fraction"] for m in marks) * 252 / len(marks)
            )
            if len(marks) >= 252
            else None,
            observed_turnover=sum(m["traded_notional_fraction"] for m in marks),
            cost_as_initial_capital=sum(m["cost_as_initial_capital"] for m in marks),
            risk_forecasts=forecast_checks[-64:],
            archived_risk_forecast_count=len(forecast_checks),
        )
    matured = []
    last_target = None
    for f in sorted(last.get("forecasts", []), key=lambda f: f["origin_session"]):
        if (
            f["status"] != "MATURED"
            or last_target
            and f["origin_session"] < last_target
        ):
            continue
        actual = np.eye(4)[f["outcome_quadrant"]]
        model = np.array(f["model"])
        base = np.array(f["baseline"])
        if any(
            a.shape != (4,)
            or not np.isfinite(a).all()
            or (a < 0).any()
            or not np.isclose(a.sum(), 1)
            for a in (model, base)
        ):
            raise ValueError("Invalid frozen probabilities")
        a, b = (
            float(np.square(model - actual).sum()),
            float(np.square(base - actual).sum()),
        )
        if abs(a - f["brier_model"]) > 1e-8 or abs(b - f["brier_baseline"]) > 1e-8:
            raise ValueError("Calibration score mismatch")
        matured.append((a, b))
        last_target = f["target_session"]
    return dict(
        status="FORWARD_DIAGNOSTICS_NOT_APPROVAL",
        session=last["session"],
        chain_head=events[-1][1],
        strategies=strategies,
        calibration=dict(
            nonoverlapping_outcomes=len(matured),
            model_brier=float(np.mean([r[0] for r in matured])) if matured else None,
            baseline_brier=float(np.mean([r[1] for r in matured])) if matured else None,
            status="NO_REGISTERED_PROBABILISTIC_FORECASTS"
            if not last.get("forecasts")
            else "REVIEWABLE"
            if len(matured) >= 12
            else "INSUFFICIENT_MATURED_OUTCOMES",
        ),
        automatic_freeze=False,
        automatic_refit=False,
        automatic_promotion=False,
    )
