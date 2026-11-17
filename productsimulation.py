"""Seeded joint asset-block scenarios for recommendation plans, not promises."""

import numpy as np


def simulate_plans(
    returns,
    plans,
    expected_annual,
    *,
    years=3,
    paths=1000,
    seed=72031,
    cost_rate=0.0015,
    initial_costs=None,
):
    values = returns.to_numpy(dtype=float)
    periods = returns.attrs.get("periods_per_year", 252)
    if type(periods) is not int or not 1 <= periods <= 366:
        raise ValueError("Qualified annual valuation-session count required")
    rebalance = max(1, round(periods / 12))
    mu = np.asarray(expected_annual, dtype=float)
    if (
        len(values) < 252
        or not np.isfinite(values).all()
        or (values <= -1).any()
        or mu.shape != (values.shape[1],)
        or not np.isfinite(mu).all()
        or (mu <= -1).any()
        or not isinstance(years, int)
        or isinstance(years, bool)
        or not 1 <= years <= 10
        or not isinstance(paths, int)
        or isinstance(paths, bool)
        or not 100 <= paths <= 10000
        or not np.isfinite(cost_rate)
        or not 0 <= cost_rate <= 0.02
    ):
        raise ValueError("Invalid simulation inputs")
    targets = np.array(list(plans.values()), dtype=float)
    if (
        targets.ndim != 2
        or targets.shape[1] != values.shape[1]
        or not np.isfinite(targets).all()
        or (targets < 0).any()
        or not np.allclose(targets.sum(axis=1), 1, atol=1e-12, rtol=0)
    ):
        raise ValueError("Simulated target portfolios must reconcile")
    if initial_costs is not None and (
        set(initial_costs) != set(plans)
        or any(not np.isfinite(v) or not 0 <= v < 1 for v in initial_costs.values())
    ):
        raise ValueError("Invalid initial portfolio costs")
    logs = np.log1p(values)
    centered = logs - logs.mean(axis=0)
    rng = np.random.default_rng(seed)
    horizon = years * periods
    curves = np.empty((len(targets), paths, horizon))
    for start in range(0, paths, 64):
        count = min(64, paths - start)

        def indices(length):
            starts = rng.integers(
                0, len(values), size=(count, int(np.ceil(length / rebalance)))
            )
            return ((starts[:, :, None] + np.arange(rebalance)) % len(values)).reshape(
                count, -1
            )[:, :length]

        calibration = indices(len(values))
        exponential_moment = np.log(np.exp(centered).mean(axis=0))
        drift = (
            np.log1p(mu) / periods
            - exponential_moment
            + 0.5 * (logs[calibration].mean(axis=1) - logs.mean(axis=0))
        )
        sampled = centered[indices(horizon)] + drift[:, None, :]
        # Constant observed cash-rate assumption is explicit; it is not a yield forecast.
        sampled[:, :, -1] = np.log1p(mu[-1]) / periods
        growth = np.exp(sampled)
        for j, target in enumerate(targets):
            initial = (
                initial_costs[list(plans)[j]]
                if initial_costs is not None
                else cost_rate * target[:-1].sum() / (1 + cost_rate * target[:-1].sum())
            )
            nav = np.full(count, 1 - initial)
            weights = np.broadcast_to(target, (count, len(target))).copy()
            for day in range(horizon):
                dollars = weights * growth[:, day, :]
                factor = dollars.sum(axis=1)
                weights = dollars / factor[:, None]
                nav *= factor
                if (day + 1) % rebalance == 0:
                    fee = np.zeros(count)
                    for _ in range(20):
                        updated = cost_rate * np.abs(
                            target[None, :-1] * (1 - fee[:, None]) - weights[:, :-1]
                        ).sum(axis=1)
                        if np.max(np.abs(updated - fee)) < 1e-12:
                            fee = updated
                            break
                        fee = updated
                    nav *= 1 - fee
                    weights[:] = target
                curves[j, start : start + count, day] = nav
    summaries = {}
    fan = {}
    for j, name in enumerate(plans):
        nav = curves[j]
        peaks = np.maximum.accumulate(np.maximum(nav, 1), axis=1)
        drawdown = (nav / peaks - 1).min(axis=1)
        terminal = nav[:, -1] - 1
        summaries[name] = {
            "median_total_return": float(np.median(terminal)),
            "p05_total_return": float(np.quantile(terminal, 0.05)),
            "p95_total_return": float(np.quantile(terminal, 0.95)),
            "terminal_loss_frequency": float(np.mean(terminal < 0)),
            "p95_drawdown_magnitude": float(np.quantile(-drawdown, 0.95)),
            "joint_50pct_return_5pct_drawdown_frequency": float(
                np.mean((terminal >= 0.5) & (drawdown >= -0.05))
            ),
            "interpretation": "Conditional planning-prior scenarios with joint blocks and drift uncertainty; not calibrated probabilities or dynamic strategy forecasts",
        }
        fan[name] = np.quantile(nav, [0.05, 0.5, 0.95], axis=0).tolist()
    return {
        "years": years,
        "paths": paths,
        "seed": seed,
        "summary": summaries,
        "fan": fan,
        "assumptions": [
            f"{rebalance}-valuation-session target rebalancing after old holdings earn the return; {periods} annual valuation sessions; constant modeled trading costs.",
            "No withdrawals, contributions, future tax-lot realization or future macro strategy reoptimization.",
            "Constant supplied net cash yield; asset growth priors are unvalidated planning assumptions.",
            "Annual asset-growth priors use an empirical exponential-moment adjustment when converted to daily log drift.",
            "Historical block sampling does not bound losses, capture every crisis or establish future probabilities.",
        ],
    }
