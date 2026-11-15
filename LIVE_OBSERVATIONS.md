# Genuine market observation and validation

**5 November recovery:** collection is restored through the completed 4 November session. Fixed the missing `cwd` argument to the bounded report worker and aligned the acceptance audit's quarantine window with the training decision-input window (`new_account_start` inclusive, final close exclusive). The network-enabled run captured 4,236 sessions for 28 instruments and five macro series; recovery reused its verified training checkpoint. The complete cycle passed for original strategies, institutional engines and dynamic blend, each now with three decision registrations and three return-marking sessions. The missed 3 November decision is disclosed; catch-up marks existing positions without inventing that decision. Watchdog reports `HEALTHY_LOCAL_OBSERVATIONS`; a repeat scheduler tick reports `CURRENT_SESSION_ALREADY_VALIDATED`. Focused regression: 36 passed; changed Python files pass Ruff. Trading and promotion remain disabled. These current receipts supersede the older health/session counts below.

**3 November update:** the manifest failure is repaired. All three cohorts have two decision registrations and one return-marking session; repeated runs add none. The hourly service is healthy, the separate five-minute local watchdog is enabled, and bounded weekly candidate research is enabled but awaits the week's final completed exchange session. See [P0_P1_STRENGTHENING_EXECUTION.md](P0_P1_STRENGTHENING_EXECUTION.md) for the current modules, measured results and blocked evidence gates. Older one-observation/zero-return figures below describe registration history.

The investor dashboard now includes an authenticated live-observation monitor with minute-level runtime refresh, scheduler timestamps, forward-session counts and matured forecast scores. See [DASHBOARD_DIGITAL_REVIEW.md](DASHBOARD_DIGITAL_REVIEW.md) for interaction checks and scope. Runtime reads do not change saved allocations or create observations.

## Local scheduling activated — 2 November 2026

The macOS login service `com.regime.live-observations` is installed in `~/Library/LaunchAgents` and enabled. It checks hourly and at login. `local_observation_scheduler.py` invokes the integrated cycle only when its latest successful session differs from the latest eligible completed US session; failures retry at a later tick. A singleton lock prevents overlapping ticks and the underlying cycle/cohorts retain their own locks. Per-run logs and `var/local-observation-scheduler/heartbeat.json` retain local status. The initial launchd run exited 0 at 14:59 Europe/Warsaw, with `CURRENT_SESSION_ALREADY_VALIDATED` for 30 October. Five scheduler/integration tests passed; no external monitoring or deployment image was qualified.

This supersedes older statements below that no scheduler is enabled: the **local Mac service is active**, while the Linux Docker/systemd recipe remains uninstalled. The Mac must be awake and logged in with network access; missed intervals coalesce on wake rather than manufacturing missed observations. The tick allows up to 7,500 seconds for a cycle. Trading, automatic parameter promotion and external messaging remain disabled.

Inspect: `launchctl print gui/$(id -u)/com.regime.live-observations`.
Stop for the current login: `launchctl bootout gui/$(id -u)/com.regime.live-observations`.
To prevent loading again at login, also disable it with `launchctl disable gui/$(id -u)/com.regime.live-observations`. Preserve all observation ledgers when stopping.

The LaunchAgent source files are portable templates. `deploy/install_local_observations.py` resolves the current project/interpreter paths and refuses to overwrite a different existing configuration. Re-render and review the configuration if either path moves. Installed agents are separate from these source templates.

2 November 2026. Public market collection is available without IBKR or a Docker host. Broker and host connectivity are explicitly deferred at the owner's request. No broker fills, execution costs or account performance are verified by this market-data process.

## Current evidence

An actual network download succeeded at `var/live-market-observations/20261102T134833594043Z/capture.json`: 4,233 sessions through 30 October 2026, 28 instruments including DBMF/ALLW references, with five archived point-in-time macro series. Files are hashed. The earlier sandbox DNS failure remains an incomplete capture and contributes no observation. Historical adjusted vendor data can be revised; this is a current retrieval of observed history, not a streaming feed or a new prospective return.

`python3 live_observation_cycle.py` successfully verified the existing completed-session observation and all three cohorts' sealed status. Each has one actual decision registration and zero forward-return sessions. Today's US session is incomplete at this run. No same-session duplicate is counted, no freeze date is backdated, and no history is inserted as newly observed investment performance.

## Daily operation

Run `python3 live_observation_cycle.py` after completed US sessions and the publication buffer. The command serializes execution and:

1. Reuses the existing validated daily job or downloads a new complete market/macro snapshot, trains the classifier, evaluates frozen strategy maps and audits isolated dashboard/PDF artifacts.
2. Advances the original strategies, the four institutional engines and the dynamic blend in separate immutable cohorts. Sealed sessions are not retrained or rewritten. Forward NAV uses declared hypothetical execution rules, not broker fills.
3. Writes a private timestamped receipt and `var/live-observation-cycle/latest.json`, including failures, forecast maturity, return/drawdown/volatility/cost diagnostics and data bindings. Completed upstream stages are not falsely rolled back or reported as an entirely atomic cross-cohort transaction. Retries use the cohort ledgers' duplicate protection.
4. Leaves the accepted investor dashboard, saved client plans, approved parameters and all order gates unchanged. Engine preview publication is disabled in this path so audited observation artifacts remain intact.

The existing Docker/systemd recipe now calls this integrated command at 22:30 UTC on weekdays. It has **not** been installed or enabled; continuous operation needs an available, qualified host. The laptop command only runs when invoked. No background worker or external heartbeat receipt is claimed. Do not run the old and integrated schedules concurrently against the same ledgers.

## Learning and adjustment

The shared classifier refits on historical available labels; risk estimates and allocations recalculate from past market/macro observations. Quarterly forecast scoring waits for the actual 63-session outcome. Compare model and frequency-baseline Brier scores, macro-disabled ablations, turnover and net costs before proposing changes. Twenty observed sessions is an operational gate, not enough to establish long-term investment superiority or calibrate quarterly predictions.

Use matured forward evidence to diagnose drift and define separate candidate experiments. Predeclare finite ranges, training/validation windows and cost stresses; preserve the current cohort and register changed source/parameters as a new version. Never select parameters on the sealed forward evaluation results and then call that same history an untouched test. Daily loss chasing and automatic promotion are disabled. Cash yield, actual spreads/fees and execution evidence remain unverified until supplied; simulated costs are labeled assumptions.

The original 50% return/5% drawdown targets are retired; neither is imposed by this observation cycle. Economic exposure, liquidity, data-quality and authorization controls remain active.

## Fresh training result

`var/live-market-training-runs/20261102T135038497311Z/training-report.json` evaluated 252 later sessions, 30 October 2025–30 October 2026, with a 28 October 2025 classifier freeze and training labels strictly before it. This is a historical chronological evaluation, not prospective account performance. The new candidate refit remains isolated.

| Strategy | Total return | Annualized volatility | Maximum drawdown |
| --- | ---: | ---: | ---: |
| Economic balance | −1.43% | 3.27% | −2.75% |
| Defensive growth | −1.68% | 4.13% | −2.92% |
| Inflation resilience | −0.82% | 2.48% | −2.09% |
| Tail-aware ensemble | −1.68% | 3.03% | −2.57% |

All four had zero allocation rejections. Results assume 15 bps turnover costs and zero cash yield. The classifier's evaluation Brier score was 0.998 versus 0.714 for the baseline (lower is better); the latest model gate also failed to beat its baseline and remains disabled. Consequently the baseline forecast is used. This evidence does not support enabling macro alpha or promoting these maps as superior return engines. Next experiments should isolate cash drag, defensive exposure and turnover with matched benchmarks and realistic verified costs, preserving these results and the prospective cohorts.

Verification: 19 focused tests passed; Ruff passed; the existing daily job health remained `HEALTHY_SHADOW_JOB` after the integrated run. The scheduler recipe was updated, not activated.

Final repository regression after these changes: **1,450 passed**. This does not qualify the unbuilt Docker image or deferred broker/host deployment.
