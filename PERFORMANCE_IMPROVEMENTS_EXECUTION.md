# Performance improvements execution — 12 November 2026

The finite improvement plan is implemented in isolated research modules. Active strategies, predictive gates, parameters, client plans, published dashboard and existing forward cohorts are not edited by these commands.

## Implemented and completed

- `performance_forecasts.py`: configured rolling-window as-of classifier refits; frequency, smoothed current-regime persistence and learned transition benchmarks; nine regularization/shrinkage trials selected on earlier validation data; 63-session nonoverlapping outcomes; Brier, log loss and reliability; simultaneous one-sided uncertainty diagnostics against all three benchmarks. Training labels strictly predate each forecast origin.
- `performance_portfolios.py`: eight declared designs across four strategies. Wider 8% aggregate trading bands and 25% partial rebalances; observed SGOV reserve allocation under unchanged capital caps and no higher baseline estimated variance; normal and 50% stress-correlation covariance; aggregate positive group-risk caps with signed hedge risk reported separately. Risk breaches override discretionary trading bands. Every new risk/reserve solve retains the existing asset, bucket, exposure, volatility and Euler caps and receives independent empirical-history checks.
- `run_performance_improvements.py`: three successive 252-session tests, each selected only on the preceding 252 sessions. Selected paths are replayed continuously, including switching costs, at 15 and 30 bps. Every path reconciles with a separate accounting replay. Saved original-strategy cash is attributed to available versus quarantined decision inputs without calling this causal opportunity cost.
- `performance_cost_stress.py`: every strategy/design pair is also tested at 0, 15 and 30 bps with frozen decisions, isolating fees from selection. The 15 bps path must reconcile with the original run and fixed-decision terminal NAV must decline monotonically with increasing costs.
- `performance_evidence.py`: per-regime reliability bins, all candidate capital weights, signed asset risk shares, signed and positive group risk shares, and normal/stress/observed covariance diagnostics.

Protocol and intermediate artifacts: `var/performance-improvements/20261112-v1`. The protocol is written before the study executes. Historical data were previously inspected; these results must not be presented as untouched forward performance.

## Cash evidence

No verified account cash-return series is available, so the actual account-yield comparison remains blocked. No 2%/4% assumption is credited to cash. SGOV is an invested ETF with observed returns, capital/risk limits and trading costs. Optional `--cash-returns` and `--cash-evidence` accept a complete USD `cash_return` CSV and a hash-bound reviewer/source/timestamp attestation. Such an attestation is labeled supplied evidence, not independently established provenance. Fixed-decision sensitivities do not claim a reoptimized or executable account result.

## Reproduce

```sh
python3 run_performance_improvements.py --output var/performance-improvements/NEW_UNIQUE_RUN
python3 performance_cost_stress.py --assessment var/performance-improvements/NEW_UNIQUE_RUN/assessment.json --output var/performance-improvements/NEW_UNIQUE_RUN-costs
python3 performance_evidence.py --assessment var/performance-improvements/NEW_UNIQUE_RUN/assessment.json --output var/performance-improvements/NEW_UNIQUE_RUN-exports
```

Outputs refuse to overwrite existing run directories. Input artifacts and source releases are hash-checked. Prospective candidate snapshots use actual registration timestamps, future fill sessions and a current-session check; historical snapshots cannot silently become new forward performance. No automatic promotion or order capability is added.

## Authoritative fixed-calendar forecast result

A sampling issue was identified in the portfolio engine's inherited forecast diagnostic: origins shift around missing future observations. `performance_forecast_calendar.py` fixes this by preserving 20 scheduled origins and disclosing three unavailable outcomes, leaving 17 scored outcomes. C=0.01 and 50% shrinkage are selected using only earlier validation data. Candidate Brier is 0.7576 versus frequency 0.7430, persistence 1.2827 and transition 0.7618. Candidate log loss is 1.3675 versus 1.3710, 2.7274 and 1.3824. The simultaneous uncertainty gate fails. The preliminary 0.6844/0.7040 availability-adaptive result is preserved as a diagnostic but is superseded for forecasting conclusions.

The canonical all-workstream entry point is `execute_performance_improvements.py`, which always runs the fixed-calendar scoring, all-trial cost stresses and risk/reliability exports. The completed isolated portfolio engine remains source-frozen; no portfolio choice uses its embedded preliminary forecast diagnostic.

```sh
python3 execute_performance_improvements.py --output var/performance-improvements/NEW_COMPLETE_RUN
```

All workstreams completed in `var/performance-improvements/complete-20261114/`. See `report.md` and the source-bound assessment, fixed-calendar forecast, all-trial costs, and allocation/risk exports. None of the four selected portfolio paths beat its incumbent across the declared historical screen; the forecasting uncertainty gate also failed. No automatic promotion is justified. The completed portfolio engine is preserved unchanged for reproducibility.

## Completion audit — 14 November 2026

Verified 232 source/artifact hashes against the completed execution and underlying portfolio study; all matched. All 96 frozen-decision cost paths are present (eight designs × four strategies × three cost levels). Audit receipt: `var/performance-improvements/completion-audit-20261114.json`. These experiments use the frozen November 11 research session; the dashboard's November 13 data refresh is a separate operational run. Actual account-yield comparison still requires verified account cash inputs, and prospective superiority still requires future observations. Neither is marked completed or bypassed.
