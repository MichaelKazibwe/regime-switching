# Dynamic strategies and adaptive portfolio

The existing four institutional-method strategies already recalculate capital weights from observed 63/126/252-session trends, relative momentum, covariance and released macro conditions. Their policy parameters remain frozen; their allocations are dynamic. The fixed Growth & Resilience reference remains a benchmark.

`dynamic_portfolio.py` adds **Dynamic Growth & Resilience**, a separately identified recommendation candidate combining all four engines. Its strategy blend responds to the observed economic quadrant:

| Regime | Economic Balance | Defensive Growth | Inflation Resilience | Tail Aware |
| --- | ---: | ---: | ---: | ---: |
| Disinflationary growth | 25% | 40% | 10% | 25% |
| Inflationary growth | 20% | 25% | 35% | 20% |
| Stagflation | 15% | 10% | 40% | 35% |
| Deflationary slowdown | 35% | 10% | 10% | 45% |
| Explicit market-only degraded state | 30% | 10% | 20% | 40% |

These are declared design weights, not optimized or calibrated forecasts. No historical performance from a component or fixed benchmark is attributed to this new blend.

Each refresh recomputes the component portfolios, blends them and performs a separate constrained risk projection. Limits include 25% per instrument and positive Euler variance contribution, 60% equity, sector/bucket limits, 30% satellites, no leverage/shorting, at least 5% cash and an 8% estimated annual volatility ceiling. Missing macro uses the engines' explicitly declared degraded state, capped at 65% invested exposure and 7% forecast volatility. Risk solve failure blocks publication. These are model constraints, not guarantees of realized volatility or drawdown.

Only the latest completed exchange-session, source-matched verified bundle is accepted. No missing prices or macro observations are invented. Outputs contain all four component allocations, combined weights, cash, signed risk shares, source hashes, dated contract and snapshot identity. No fixed return target or maximum account drawdown constraint is introduced. Existing ledgers and incumbent policies remain separate.

Run against the latest captured observations:

```sh
python3 dynamic_portfolio.py --output var/institutional-return-engines/dynamic-latest.json
```

The existing `run_return_engine_cycle.py` now also generates this snapshot after a successful challenger cycle, including cached same-bundle evaluations. Refresh market/macro inputs with the existing verified data pipeline before the next completed session's cycle. No unattended host job has been installed; opening the dashboard alone does not refresh data.

As of 1 November, the dashboard has a separate Dynamic portfolio view and contract-bound PDF, published by `dynamic_preview.py`. Its historical chart uses this exact design's reconciled replay. `dynamic_forward.py` registers a separate unapproved prospective cohort: one observation, zero return sessions at registration. Exact-design forecast simulations and independent acceptance remain open; other strategies' simulations are not attributed to this blend. Public release, execution and automatic promotion remain disabled. See [LIVE_UPGRADE_EXECUTION.md](LIVE_UPGRADE_EXECUTION.md) for validation and remaining requirements.
