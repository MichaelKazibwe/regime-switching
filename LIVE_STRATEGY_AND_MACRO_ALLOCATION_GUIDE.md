# Fresh-data strategy training and macro-driven allocations

> **Universe policy update (2026-11-17):** Current portfolios and strategies resolve a configurable global instrument registry, with no fixed ETF-count limit. Numeric universe counts below describe this document's historical implementation or experiment. See [the current global-universe policy](GLOBAL_ASSET_UNIVERSE.md).

## Dynamic portfolio extension — 31 October 2026

See [DYNAMIC_PORTFOLIO.md](DYNAMIC_PORTFOLIO.md). The four institutional-method engines already update their underlying allocations from market and macro inputs. `dynamic_portfolio.py` adds a separately identified blend with independent aggregate risk projection. The 1 November follow-through adds a separate dashboard view, contract-bound PDF and unapproved prospective cohort, with this exact blend's reconciled historical replay. Forecast simulation qualification and independent acceptance remain open. The fixed benchmark remains a reference; component performance must not be presented as the blend's performance. Current verification: 1,415 full-suite tests passed; see [LIVE_UPGRADE_EXECUTION.md](LIVE_UPGRADE_EXECUTION.md).

**Private shadow system, not an approved investment release.** This implements the owner's requests to train on current observations, integrate the results, calculate macro-conditioned capital/risk allocations, explain asset roles and simulate/export the complete candidate portfolio. Existing investor plans, financial loss capacity and execution authority are unchanged.

## Open the workspace

Open `var/investor-dashboard/strategy-workspace.html` or `var/investor-dashboard/investor-dashboard.html`.

- **Trained strategies:** dated training/evaluation boundaries, net-of-modeled-trading-cost results for all four strategies and references, forecast validation gates, data-quarantine count, wealth/drawdown charts and source integrity.
- **Macro outlook → Automatic strategy allocation lab:** choose a strategy and the latest gated forecast or one of the supplied quarterly macro scenarios. Capital weights, signed Euler variance shares, risk budgets, all asset roles and the corresponding 500-path conditional portfolio simulation update together.
- **Portfolio:** the ordinary holdings table also shows each instrument's economic role, separately from allocation/eligibility status.
- **PDF:** `output/pdf/investor-macro-risk-report.pdf` now includes a separate fresh-strategy appendix with every asset role, current candidate capital/risk allocations, forecast mixture, scenario metrics and training evidence. The older investor illustration is still dated separately. Each strategy has its own current-snapshot PDF in the dashboard folder.

All 26 core assets are shown, plus DBMF, benchmark-only ALLW and cash. The four existing strategies deliberately use a subset of the menu; a zero weight is not a missing allocation. No portfolio is forced to hold every ETF.

## Automatic recalculation modes

**Saved-file mode:** switching strategy or supplied quarterly forecast automatically displays its fully calculated constrained allocation and simulation. Twenty strategy/forecast combinations are available. These are dated snapshots, not a running data feed. Custom weights/horizons are disabled until the local calculation service is connected. Other scenarios can be printed/saved as PDF; current-model snapshots have downloadable strategy PDFs.

**Local calculation mode:** start the authenticated loopback service:

```sh
python3 strategy_dashboard_server.py
```

The default command reads `var/investor-dashboard/latest-strategy-run.json`, keeping the service and dashboard on the same verified run. Open the private launch URL printed by the process. Its random token stays in a URL fragment/session storage and Authorization headers, not server request URLs. The unauthenticated HTML shell contains no financial payload. Keep this single-operator service local; it is not a public multi-tenant application.

Custom scenario weights automatically recalculate after a short input debounce. Inputs are normalized to a four-regime mixture. The backend reruns the existing constrained allocation/risk solver and a bounded 500-path simulation; it does not just change chart labels. One-, two- and four-quarter horizons are available. PDF export uses the exact calculated result. A new request does not reset the evaluation account's peak, clear a cash lock, raise a risk cap or bypass missing inputs.

The default latest-model mode honors the predictive gate. Manually supplied or quarterly mixtures are explicitly hypothetical scenario inputs, not validated model alpha. The strategy's forecast tilt remains at its existing 20% setting. There is no order submission or modification of actual account holdings.

The service rejects a stale completed-session snapshot, untrusted Host/Origin, missing token, oversized/nonfinite input, concurrent computation and unknown routes. API output is not cached publicly. Stop the foreground process when finished. A fresh session requires a new capture/training bundle and service restart; a browser does not silently retrain or rewrite approved portfolios.

## Refresh from current external data

One command captures, trains, evaluates, recalculates the supplied scenarios and updates the private dashboard/PDF:

```sh
python3 refresh_strategy_dashboard.py --download
```

This uses the protected existing FRED configuration. It downloads adjusted historical ETF data and actual ALFRED releases. The latest completed NYSE session, after a 15-minute publication buffer, is the usable market cutoff. In-progress daily bars are excluded; missing ETF prices are never interpolated or forward-filled.

For a completely offline regeneration from verified snapshots:

```sh
python3 refresh_strategy_dashboard.py \
  --capture var/strategy-training-snapshots/20261030T201909466391Z/capture.json \
  --training-report var/strategy-training-runs/20261030T210916293673Z/training-report.json \
  --latest-macro-features var/macro-repairs/20261030T210915901130Z/features.json
```

Omit `--training-report` to retrain on the supplied immutable capture. Each capture/run has a separate directory and hashes. A partial or rejected run cannot become a completed training report. The dashboard loader verifies the completed run's artifacts and preserves saved client-plan data while attaching the independent strategy lab.

This work **does not install an unattended scheduler**. The one-shot command can be scheduled only after host, secrets, monitoring, recovery and data-rights qualification. A new data/model run requires reviewed promotion before becoming investor-facing advice.

## What was trained and evaluated

The existing four allocation maps were retained: Economic Balance, Defensive Growth, Inflation Resilience and Tail-Aware Ensemble. Their shared regularized macro regime classifier was trained with a training-only scaler and a 63-session label purge. Risk/covariance estimates use observations available at each decision. The final 252-session evaluation used a frozen classifier; a separate latest-data refit produced the current shadow candidates. The later refit is not credited with the frozen model's evaluation performance.

Market capture: **4,233 sessions, 28 instruments, through 30 October 2026**. The final capture occurred after the 30 October close and its publication buffer; the earlier 29 October snapshot/run remains archived. Capture and completed report locations are in the launch commands above. The raw inputs and source/model coefficients are private, hashed and retained for review; no pickle from an untrusted source is loaded.

Evaluation dates: **30 October 2025–30 October 2026**, 252 market sessions. These are later-period results, not pristine prospective evidence: the universe and strategy designs were developed retrospectively. Returns below include modeled 15 bps traded-notional costs, assume zero uninvested cash yield and precede investor taxes/platform fees. Doubled-cost sensitivities are retained in the report.

| Strategy | Evaluation total return | Maximum drawdown | Annual volatility | Rejected allocations |
|---|---:|---:|---:|---:|
| Economic Balance | -2.00% | -2.78% | 3.00% | 0 |
| Defensive Growth | -1.97% | -2.66% | 3.73% | 0 |
| Inflation Resilience | -0.81% | -2.11% | 2.48% | 0 |
| Tail-Aware Ensemble | -1.80% | -2.42% | 2.88% | 0 |

The latest classifier gate remained **OFF**. Latest gate Brier scores were approximately 0.7310 for the model versus 0.7264 for the baseline; the later frozen-model evaluation also underperformed its baseline. Training therefore does **not** demonstrate improved returns or justify turning on predictive alpha. The existing three-year 50% return / 5% decline aspiration remains unsupported.

## Missing macro periods: fail closed without inventing data

The captured UNRATE and CPI archives omit October 2025. The older generic 16-consecutive-month requirement blocked even calculations that did not mathematically need that missing period. `training_macro.py` instead requires the actual calendar periods used:

- Unemployment momentum: six consecutive observed months.
- CPI year-over-year/momentum: the exact current, 12-month, 3-month and 15-month endpoints.
- Industrial-production growth: current and six-month endpoints.
- Treasury curve: actual aligned 10-year and three-month observations.

The same 90-day monthly / 14-day Treasury staleness gates remain. Missing required endpoints still quarantine the decision. No missing October observation is fabricated, and no stale release is declared current. **130 evaluation decision sessions were quarantined**; the account reduced to cash at the declared next-close timing. Unavailable macro rows are excluded from fitting/labels while retaining the true trading-session clock, so a 63-session target is never compressed across a gap.

## Conditional simulation interpretation

Each candidate is simulated jointly across its held assets using observed 21-session blocks, selected by the regime known before the historical block. Current simulations use up to 1,260 recent joint sessions; these do not include every crisis. Overlapping source blocks are not independent samples. Fewer than five eligible blocks for a positive-weight regime blocks that scenario.

The supplied forecast mixture is held fixed over the chosen horizon. Targets are recalculated for that mixture, with constrained covariance/risk allocations, then paths apply the latest target plus reduce-only drawdown sizing, persistent 4% cash lock, next-close fills and 15 bps costs. The carried hypothetical account peak remains in force. This is **not** a simulation that retrains future macro models and optimizes a new regime policy at every future step.

Reported quantities include total-return percentiles, annualized volatility, 95th-percentile maximum account drawdown, horizon VaR/expected shortfall, terminal-loss frequency and 5% drawdown-exceedance frequency. These are conditional sample estimates, not calibrated future probabilities, protection against all gaps or a guaranteed maximum loss. No positive result is selected for presentation by hiding unfavorable scenarios.

## Implementation map

- `strategy_training_data.py`: immutable current market/vintage capture and completed-session checks.
- `training_macro.py`: exact-period release-aware features; explicit unavailable states.
- `live_strategy_training.py`: purged chronological fitting, frozen evaluation, gated latest refit, source/model evidence and strict candidates.
- `fourstrategysimulation.py`: optional unavailable-macro flag forces reduce-to-cash planning; normal existing behavior remains unchanged.
- `strategy_report.py`: completed-report, date, capital and artifact verification before display.
- `macro_allocation_lab.py`: constrained reallocation and bounded joint-asset conditional scenarios.
- `assetroles.py`, `macro_lab_pdf.py`: common asset roles and calculation-specific PDF output.
- `strategy_dashboard_server.py`: authenticated local API, no financial data in the unauthenticated shell, no account or broker APIs.
- `refresh_strategy_dashboard.py`: reusable one-shot integration pipeline; no installed background job.

Time-ordered fitting follows the principle documented by [scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html). Release-aware macro handling uses [FRED real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) and [vintage observation controls](https://fred.stlouisfed.org/docs/api/fred/series_observations.html).

Local checks include regression tests for frozen scalers/label maturity, missing-period rejection, publication delays, macro-scenario weight changes, capital/risk reconciliation, source coverage/resource bounds and authentication. A real authenticated local API call recomputed a custom one-quarter allocation, checked capital/risk limits and exported a PDF. No packages, public service, broker orders or user email delivery were installed/enabled.

Final local verification: **1,280 pytest cases passed**, Ruff passed, and both the saved dashboard script and authenticated service bootstrap parsed in JavaScriptCore. The current seven-page investor PDF was rendered for visual review. The temporary QA service was stopped; start the command above for custom-input recalculation.

## Operational follow-through

The scheduler is now supplied as an isolated candidate job in `scheduled_strategy_validation.py` with Docker/systemd templates; it is still not installed on an unattended host. Acceptance and the one-per-session prospective ledger are implemented in `strategy_operations.py`. See [STRATEGY_DEPLOYMENT_ACCEPTANCE.md](STRATEGY_DEPLOYMENT_ACCEPTANCE.md) for evidence and remaining gates.

## Exact-calendar macro repair

See [MACRO_CALENDAR_REPAIR.md](MACRO_CALENDAR_REPAIR.md) for the shared current/vintage contract, corrected CPI endpoints and regenerated artifacts. The earlier 1,280-test checkpoint above is historical; the repair passed 1,293 tests. Current quarterly fitting preserves calendar gaps and uses only complete observed transitions/residual blocks.

## Repairs 2–4 checkpoint — 31 October 2026

See [REPAIRS_2_3_4_VALIDATION.md](REPAIRS_2_3_4_VALIDATION.md) for strict CSV/scenario/PDF reconciliation, durable v2 job/observation receipts, watchdog and explicit quarantine recovery, and prospective NAV/forecast accounting. Use `var/strategy-operations-v2` for new observations; the prior v1 root remains archived and untrusted for migration. Current v2 state is 1 operational observation and **0 forward return sessions**, not a completed observation period. No timers, external alerts or public deployment were enabled.
