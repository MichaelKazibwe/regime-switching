# Live-trading checklist P1: items 25–26

3 November 2026. **Local engineering implemented; qualification remains OPEN.** This implements the two P1 rows in `LIVE_TRADING_UPGRADE_ROADMAP.md`, not the separately completed economic P0/P1 study. No live account, broker permission, sender credential, independently reviewed release or deployment host was inferred from the request. No external alert, order, cancellation or model promotion occurred.

## Item 25 — observability and recovery

| Responsibility | Implementation / local evidence | Qualification still open |
| --- | --- | --- |
| Freshness/execution SLOs | `live_p1_service.py` persists prospective SLO declarations, worker freshness, post-close delivery latency, ack/callback percentiles and cost-over-model checks. Old sessions remain pre-policy diagnostics. Missing broker evidence is unavailable, not a zero-latency PASS. | Actual single-host pilot and enough measured execution samples; clock/resource/outage drills on the intended host. |
| Retained metrics/logs | `operational_metrics.py` stores timestamped finite, bounded-cardinality metrics and conflict-checked JSON records in SQLite; private run records and worker logs are retained. `metrics.prom` is a local Prometheus text artifact, not a public listener. | Off-host collection, storage/retention review, capacity monitoring and independent operational review. No automatic deletion of observations/logs is enabled. |
| External escalation | `operational_escalation.py` persists incidents, acknowledgements and delivery state before I/O. Primary and overdue secondary notifications have distinct identities; interrupted/ambiguous sends become UNKNOWN and are not blindly retried. The configured adapter reuses TLS `EmailTransport`. | Protected SMTP configuration, explicit recipients/authorization and actual receipt/acknowledgement evidence. Currently disabled/unconfigured; queued incidents are not reported delivered. |
| Backup objectives | `operational_recovery.py` reuses complete shadow bundle backups, verifies all three committed heads and replays recorded NAV/peaks after isolated restore. Same-head snapshots are verified rather than recopied each tick. | Off-host backup/restore, independent market/strategy reconstruction and explicit path rebinding before a real restart. Same-Mac copies do not survive loss of the Mac. |
| Managed state restoration | `managed_disaster_recovery.py` uses SQLite online backup, checks hashed records, restores only to a new isolated directory, freezes every account, invalidates writer epochs and clears stale reconciliation. Synthetic account-store tests verify source preservation. | No actual managed broker database is configured in this monitor. Broker/custody reconciliation and real controlled restart drills remain required. |
| Writer fencing | `writer_fencing.py` provides account-scoped monotonically increasing epochs, bounded leases and renewal. Real paper mutations/dispatch and post-send acknowledgement persistence check the current lease; intents bind their prepared epoch. Stale owners cannot post financial events or resume accounts. In-flight dispatch blocks takeover until quarantined; an expired send acknowledgement becomes UNKNOWN. | One authoritative SQLite state database only. This is not distributed consensus, database-replica protection or broker-side fencing. Already-sent broker requests cannot be recalled by a local epoch. Genuine sandbox race qualification remains open. Emergency freeze/unknown quarantine remain available as safety actions. |

Default objectives: post-close delivery within 7,200 seconds, worker heartbeat within 7,200 seconds, ack/callback p95 within five seconds, review when filled shortfall exceeds modeled cost by ten bps, local restore within 900 seconds, escalation after 900 seconds. These are prospective engineering targets, not achieved long-term statistics or financial guarantees. Changing them requires a new monitor directory/version.

The first genuine local drill restored **core, institutional engines and dynamic cohorts**, each with two events, and reconciled **13 recorded NAV/peak marks** in approximately **0.22 seconds**. It met the 15-minute local restore target with zero missing events at those saved heads. This is recorded-return replay; it does not independently rerun alpha decisions or reconstruct asset prices. The original ledgers were not altered. No off-host RPO/RTO certificate is issued.

## Item 26 — strategy and execution degradation

- `strategy_degradation.py` reads validated forward chains and reports net outcomes, recorded turnover/costs and drawdowns. Volatility requires at least 21 return sessions; annualized turnover requires 252. The current single return mark is not annualized into a credible performance statistic.
- `risk_forecast_registry.py` archives hash-checked, separately versioned risk estimates for strictly future full close-to-close windows. The 21-session gross-price-risk estimate uses observed covariance and registered starting/next-fill weights. Future rebalancing can change realized risk. No historical prediction is backdated to fit an observed result.
- Matured risk windows compare realized gross price-risk volatility with their prior estimate. Macro probabilities are independently rescored only after recorded outcomes mature, using non-overlapping horizons. Core has no matured quarterly forecast outcomes yet. Engines/dynamic without registered probabilistic forecasts are explicitly not assigned synthetic calibration results.
- Feature drift compares disjoint observed windows with a declared PSI review heuristic. The current data flagged drift in the eight monitored features. This requests review; it is not a calibrated error probability and does not freeze/refit a strategy automatically.
- `execution_degradation.py` reuses `ExecutionAnalytics.calculate_implementation_shortfall`, adds explicit fees, deduplicates individual execution IDs, rejects conflicting/future/overfilled events, keeps currencies separate and measures broker ack/callback times. Unfilled opportunity cost, FX and taxes remain unavailable rather than assumed zero. Actual broker evidence is currently absent, so no measured shortfall or live-performance claim is made.
- `operational_model_review.py` records OS-identified local review requests bound to the exact report and cohort heads. Refits require a new candidate version; freeze requests require a strategy scope. Requests never apply trading changes or grant release authority. Actual freezes/resumes use the separately authenticated managed-operations boundary and current writer/risk permissions.

## Running and configuration

```sh
python3 live_p1_runner.py
python3 live_p1_service.py --root var/live-upgrade-p1
python3 live_upgrade_status.py
```

The recurring local job uses `live_p1_runner.py`, a 900-second process bound and exclusive service lock. Status, incidents, SLO targets, risk forecasts, retained telemetry, backups and isolated drill copies are under `var/live-upgrade-p1/`. The metrics/backup service never places orders. A Mac login service requires the Mac to remain awake, logged in and online; no Linux host is configured.

`deploy/live-p1-monitor.example.json` has delivery disabled. Copy it into an owner-only protected file and supply genuine broker evidence and sender configuration privately when available. Keep passwords in protected process environment/configuration, not chat or source control. Do not enable both the default service and a second differently configured worker for the same monitor root. No dummy sender or receipt is considered external qualification.

Local acknowledgement: `python3 live_p1_service.py --ack-incident INCIDENT_ID`. Acknowledgement is distinct from resolution or delivery. A review example is `python3 live_p1_service.py --review-decision REQUEST_REFIT --candidate-version NEW_VERSION --reason "Reason based on current evidence"`. A request records intent only; it does not run the refit or release it.

Broker-evidence input is a protected JSON export with mode `BROKER_PAPER`/`BROKER_LIVE`, named local review, matched reconciliation, dated export, hash-bound raw files, account-scoped orders and individual fill IDs. Orders include arrival/submission/ack clocks and prices, quantity/currency/side; fills include execution/receipt clocks, quantity/price/fee/currency. Adjusted research bars or synthetic fixtures cannot substitute for this export. Paper execution does not qualify live execution.

## Readiness boundary

The inventory retains both qualification rows OPEN and records `IMPLEMENTED_LOCAL_QUALIFICATION_PARTIAL`. Remaining dependencies are actual single-host pilot/host review, configured external delivery and receipt, off-host recovery, genuine broker execution evidence, matured forward risk/calibration windows and independent operational/model sign-off. Profitable-looking historical experiments cannot approve themselves. All execution/release flags remain false.

## Verification and local activation

The local `com.regime.live-p1-monitor` LaunchAgent is enabled at a 300-second interval; its bounded worker completed with exit code zero. The final full regression suite passed 1,481 tests in 69.30 seconds after dependency-closure repair; 13 focused release/P1 tests also passed. Repository-wide Ruff passed. A staged-source smoke check now imports the monitor and runner outside the working tree. Both research Docker source lists include the monitor's local import dependencies; image build/runtime qualification remains pending.

The source candidate is `var/releases/managed-roadmap-p1-20261103` (release ID `1ce7adbe1115edfefe1582376a55572ddaafda6d516b4681b59f33f739c6d9bf`). Its manifest verifies the staged files; dirty-tree candidate status grants no deployment authority.

Managed execution integrations must acquire an account-scoped `writer_fencing.claim` lease, assign it to the coordinator's `writer_lease`, and renew before expiry using the returned token. A prepared order binds that lease epoch; takeover requires preparing a new authorized intent after ambiguity is resolved. Never bypass fencing with simulation mode for a real adapter.
