# P0/P1 strengthening execution — 3 November 2026

**Engineering implemented and tested; investment promotion and live release remain blocked.** Broker and Linux host connectivity remain deferred at the owner's request. No order, external alert or customer update was sent. Existing frozen numerical strategies, client plans, prior NAV peaks and sealed cohort events were preserved.

## Scope and completion

| Priority / module group | Implemented and exercised | Evidence still required |
| --- | --- | --- |
| P0 — report integrity | `refresh_strategy_dashboard.py` retires unrefreshed dynamic/engine extensions and their unrelated PDF links before assembling the fresh core bundle; strategy/plan PDFs are regenerated and the complete manifest is verified. The strict coverage check was retained. | A dynamic extension must be separately regenerated against its own current contract before publication. No stale dynamic PDF is relabeled current. |
| P0 — recovery | `observation_recovery.py` verifies current-session capture, training source/artifact integrity, benchmark extension and checkpoint hashes. The daily wrapper reuses verified training after report-stage failure and records the failed/recovered stage. An immediate training checkpoint supports failures before report assembly finishes. | New or altered numerical sources still require new training/cohort review; a checkpoint cannot override source or date checks. |
| P0 — scheduling | Hourly worker has a per-session/source three-attempt budget and local failure records. `observation_process.py` bounds worker lifetimes and cleans up independently grouped report children on timeout/cancellation. Locks prevent overlapping updates. | Mac must be awake/logged in. Off-host availability and recovery remain unqualified. |
| P0 — missed-job monitoring | Separate five-minute macOS watchdog checks core job/receipt health, the full-cycle session and heartbeat freshness. Fresh heartbeat alone cannot declare an invalid core job healthy. | External delivery and off-host monitoring are not configured; the sleeping/offline Mac cannot monitor itself externally. |
| P1 — return engines | `resilient_candidate.py` and `run_p1_refinement.py` evaluate twelve new candidates across four engines alongside four unchanged incumbents. Separate preceding validation and final test slices, 0/15/30 bps costs, turnover, mean cash, regime diagnostics, matched references, paired intervals and raw trade/return artifacts are retained. | All historical windows were previously inspectable. No pristine validation, superior returns, future loss ceiling or automatic promotion is claimed. |
| P1 — macro forecasting | `forecast_calibration.py` tests nine regularization/shrinkage combinations, freezes fitting before evaluation, preserves the actual 63-session horizon across gaps, spaces labels without overlap, and reports baseline Brier scores and reliability bins. Confidence diagnostics require at least twelve quarterly outcomes and use two-quarter blocks. | The five-year calibration test has 17 usable non-overlapping quarterly outcomes; the candidate underperforms its baseline. Activation is blocked; original model/baseline behavior remains unchanged. |
| P1 — financial/data inputs | `market_quality.py` verifies immutable capture lineage and discloses revisions without merging old snapshots. A hash-bound, rights-reviewed independent-file adapter compares compatible daily returns; same-provider substitutes are denied. Financial-evidence files reject symlinks. | No independent provider file or verified cash/cost/holdings/FX/liquidity evidence has been supplied. Their gates remain blocked. |
| P1 — whole-account risk | `portfolio_risk_envelope.py` checks capital concentration, gross exposure, empirical volatility, signed Euler shares, historical ES and full-correlation volatility. `managed_portfolio_risk.py` runs at prepare and dispatch against account-book positions/cash, pending BUYs, filled/pending daily notionals, completed-session risk history, measured duration/FX/country/underlying overlaps and ADV participation. Successful reviews are append-only and bind request, marks, risk history and financial evidence. | Real paper path requires a trusted measured-risk provider, signed limits and verified financial evidence. Cross-currency valuation is blocked pending a qualified FX release. Broker/custody, tax/corporate actions, client-account approvals and independent reviews remain open. |

The runtime/Docker source lists and managed evidence identity include the new modules. No image build, immutable host qualification or clean reviewed commit is asserted.

## Genuine operating result

Recovered the failed 2 November run by reusing its verified training report, regenerating the reports and passing the full artifact audit. Retained job: `var/strategy-operations-integrated-v1/runs/20261102T235326086269Z`.

Original strategies, institutional engines and dynamic blend now each have **two actual decision registrations and one forward return-marking session**. The first mark includes hypothetical entry costs; it is not verified broker performance or a holding-period profitability result. Repeated runs returned already-sealed status and did not add sessions. Current full cycle: `var/live-observation-cycle/latest.json`. Core health and independent watchdog report healthy local observations. The actual hourly LaunchAgent was checked again and exited 0.

## P1 study results

Source/artifact-bound report: `var/p1-refinement/20261103-completed/assessment.json`. Its status is `COMPLETED_REVIEW_ONLY`; no deployment or investment approval is granted.

The continuous retrospective replay spans 1,260 sessions, 26 October 2021–2 November 2026. Selection uses the 252 sessions preceding the final 252-session slice. The following final slice is **31 October 2025–2 November 2026**, at 15 bps modeled trading cost and zero unverified cash yield. These are slices of continuous portfolios, not newly reset evaluation accounts; they are not directly comparable with the earlier reset-account negative-return table.

| Engine | Validation selection retained for review | Final-slice return | Maximum drawdown | Mean uninvested cash |
| --- | --- | ---: | ---: | ---: |
| Economic balance | Incumbent institutional engine | 5.25% | −4.33% | 25.9% |
| Defensive growth | Incumbent institutional engine | 4.97% | −4.57% | 29.1% |
| Inflation resilience | Incumbent institutional engine | 8.38% | −3.91% | 26.6% |
| Tail-aware ensemble | Observed-macro ablation candidate | 7.12% | −4.23% | 49.6% |

No candidate is promoted. All four paired intervals versus the matched balanced reference include zero. High cash exposure remains an economic weakness. The report's 2%/4% cash-carry figures are arithmetic sensitivities, not measured interest, full strategy reruns or forecasts. ALLW remains benchmark-only; the matched All Weather reference is a transparent proxy, not Bridgewater performance. No pre-inception history was filled.

A one-year calibration screen was explicitly superseded because it cannot supply twelve independent quarterly outcomes. The final calibration study uses a separate five-year window, frozen on 28 July 2021 with training labels through 27 July 2021. It has 17 usable non-overlapping quarterly outcomes: model Brier 0.732 versus baseline 0.687, with a one-sided 95% lower bound on improvement of −0.103 under two-quarter block resampling. The activation gate is false. This is a different evaluation protocol from the one-year portfolio comparisons above and remains retrospective, not independently certified predictive evidence. The source training run quarantined 130 of 252 evaluation sessions; missing point-in-time macro inputs remain missing.

Comparing fresh and prior adjusted vendor histories disclosed 76,812 changed cells, with maximum relative change approximately 0.0323%. Adjustment revisions are disclosed as lineage changes, not automatically labeled vendor errors or used to rewrite prior cohort events. An independent source has not confirmed them.

## Active local jobs

| LaunchAgent | Cadence | Current state |
| --- | --- | --- |
| `com.regime.live-observations` | Hourly, new completed session only | Enabled; repaired check exited 0 |
| `com.regime.observation-watchdog` | Every five minutes | Enabled; healthy local observation record |
| `com.regime.p1-research` | Checks every six hours; studies only after the week's final NYSE session | Enabled; waiting for weekly close |

Weekly research is limited to one completed study per exchange week/source identity, with at most two failed attempts. It verifies source stability, bundle identity and artifact hashes, retains all trials, and cannot publish allocations, submit orders or issue approval receipts. Frequent checks are not additional financial observations. Do not run duplicate schedulers against the same account ledgers.

## Verification and remaining gates

Full regression: **1,469 passed**. Repository Ruff passed. The focused P0/P1 set passed 13 tests after the final watchdog grace-state adjustment, including distinguishing a legitimately pending job from an alert. Focused tests exercise retired PDF bindings, checkpoint tampering, duplicate observations, retry exhaustion, timeout cleanup, causal candidate inputs, pending concentration, missing/stale/misbound risk evidence, daily notional caps, blocked financial evidence, watchdog false-health prevention and weekly source binding/idempotence.

Remaining qualification dependencies: verified financial inputs and independent feed/rights review; matured forward observations; independent model/security/operations review; actual broker qualification; clean immutable runtime/host and off-host alert/recovery evidence; managed-client legal/mandate/access approvals. These were not fabricated or bypassed. Financial uncertainty and loss remain possible; the retired 5% drawdown and fixed return constraints were not reinstated.

Managed source candidate: `var/releases/managed-p0-p1-20261103-v2`, identity `3270fdef825ea4bd8e00cda937a937fc924052a33e26053cfdb12a19a82d6c8a`. Integrity verified; dirty-tree review candidate, not deployment-qualified. Archived investor dashboard financial data/PDFs remain unchanged; only their local viewer validation metadata was refreshed for current operational code. The accepted observation artifacts were not resealed or rewritten.
