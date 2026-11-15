# Strategy dashboard: acceptance and deployment gates

Updated 30 October 2026. Owner: Michael Kazibwe. Scope: private portfolio recommendations, scenarios and reports. No managed accounts, broker orders or automatic model promotion.

## Six workstreams

| Priority | Workstream | Implemented / evidence | Remaining gate |
|---|---|---|---|
| P0 | Data-quality investigation | `strategy_operations.py`; verifies capture/report hashes and counts exact evaluation failures | External missing observations must arrive as authenticated releases; do not fabricate missing periods |
| P0 | End-to-end acceptance | Four real custom allocations, risk/capital reconciliation and calculation-specific PDF exports; regression authentication/input tests | Repeat on target container and host |
| P0 | Scheduled shadow refresh | Locked isolated candidate jobs, failures recorded, systemd service/timer and hardened Docker Compose job | Host provisioning, pinned image build and protected FRED secret; timer is supplied, not installed |
| P1 | Prospective observation | Immutable, one-record-per-current-market-session ledger; no backfill, duplicate count or automatic approval | At least 20 actual trading-session observations and operator review |
| P1 | Docker qualification | Dedicated source-selected image recipe, non-root/read-only constrained batch container, no exposed port | Docker unavailable locally; build, scan, smoke-test and recovery drill on Linux host |
| P0 | Predictive/model promotion control | Existing predictive gate retained; scheduled output isolated from investor workspace and approvals | Independent chronological advantage, operational review, and explicit approval; no automatic promotion |

## Run locally

```sh
python3 strategy_operations.py --observe
python3 scheduled_strategy_validation.py
```

Both verify the current workspace without downloading. The scheduled wrapper records a completed local job and idempotently counts the session. `--observe` rejects stale or failed acceptance and conflicting rewrites. These are operational observations of dated snapshots, not newly realized investment returns. Historical evaluation metrics do not become forward returns by being recorded daily.

For a fresh candidate after each usable close:

```sh
python3 scheduled_strategy_validation.py --refresh
```

This downloads inputs, trains/evaluates, and computes the full lab in `var/strategy-operations/runs/<UTC timestamp>/dashboard/`. It leaves the existing investor dashboard, saved client plans and launch bundle unchanged. A lock prevents overlapping jobs, refresh is bounded to two hours, and a session already observed is skipped before another download. Failed jobs remain recorded with nonzero process status; no failed run can count. Logs and evidence are private. This command requires the existing protected FRED configuration and market-provider connectivity. Do not run competing training or mutate numerical sources during a refresh.

The job does not hot-reload a running service. Review the new candidate and restart a private calculation service with that candidate's matching `--dashboard` and `--bundle` if using it. Never mix an older dashboard with a newer calculation bundle.

## Data-quality findings

The completed evaluation through 30 October 2026 has **130 rejected macro-decision sessions**:

| Rejection | Sessions |
|---|---:|
| Missing required UNRATE calendar period | 76 |
| Stale/missing UNRATE | 27 |
| Missing required CPIAUCSL calendar period | 17 |
| Stale/missing INDPRO | 8 |
| Stale/missing CPIAUCSL | 2 |

These counts describe the first failing check in each rejected session; several inputs may be unavailable simultaneously. The archives omit October 2025 UNRATE/CPI observations. This is an observed archive gap, not proof of an ingestion defect or a particular external cause. Original releases and vintages must be independently reconciled before any repair. Keep exact-period requirements and existing 90-day monthly / 14-day yield freshness checks. The current snapshot passes macro availability. Do not relax historical gates to improve reported returns. Raw quarantine dates/reasons and all twenty scenario checks are in `var/strategy-operations/acceptance.json`.

## Observation protocol

The initial 30 October 2026 snapshot is observation **1 of 20**. Subsequent observations require actual later completed exchange sessions; holidays and repeated runs do not increase the count. Review `observation-status.json`, per-session records and `latest-job.json` daily. Run `python3 strategy_healthcheck.py` after the scheduled job: it exits nonzero on a missing current-session receipt or failed latest job. Run monitoring after 22:45 UTC to allow the scheduled refresh; a check immediately after market close can correctly report that the receipt is still pending. Failure, missing daily receipt, source mismatch, stale data or a PDF/allocation discrepancy requires investigation before counting a session. Overlapping frozen evaluation windows are not independent performance evidence.

At review, reconcile session continuity against NYSE dates, refresh success, input delays, rejected allocations, cash-lock behavior, turnover/cost sensitivity, risk-cap breaches, forecast scores and portfolio changes. Compare unchanged strategies against the predeclared references over the same observed dates. Preserve any change of parameters as a new candidate with its own prospective review; do not quietly optimize the observation window. Twenty sessions can qualify operational reliability, not long-run returns or calibrated loss probabilities.

The latest predictive gate remains OFF: model Brier approximately 0.7310 vs baseline 0.7264. Historical strategy returns were negative. No predictive alpha or return target is accepted on these results. Model promotion requires sufficient mature, purged outcomes, cost-aware benchmark comparison, independent validation and recorded human review. Completion of the observation counter never enables deployment or promotion.

## Linux Docker host qualification

No host has been selected or provisioned. Docker is not available in the current workstation's command path. Nothing here is publicly deployed.

1. Stage a reviewed source checkout at `/opt/regime`, install Docker Engine/Compose through the host administrator, and create a dedicated restricted operator. Restrict Docker socket membership; it provides root-equivalent authority.
2. Build `Dockerfile.strategy-validation` with the committed hashed dependency lock. Run dependency checks, vulnerability scanning and applicable tests in the resulting Linux/Python 3.12 environment. Record the actual immutable image digest. Image construction has not been tested on this workstation.
3. Seed `var/` with the verified research macro archive and dashboard/product template inputs needed for refresh. Source CSV manifests use project-relative paths. The old workstation launch bundle contains absolute workstation paths: do not use it as a container launch bundle. A successful in-container refresh generates a candidate bundle with `/app/...` paths. Give UID/GID 10001 ownership of writable `var/` and `output/`; retain restrictive permissions.
4. Store `FRED_API_KEY` privately in `/etc/regime/strategy.env` (0600). Store `STRATEGY_IMAGE=<reviewed image digest>` and `STRATEGY_SECRET_FILE=/etc/regime/strategy.env` in `/etc/regime/strategy-image.env` (0600). Compose requires these variables; the image does not embed secrets.
5. From `/opt/regime`, load the image environment securely and run `docker compose -f compose.strategy.yaml run --rm validation`. Confirm a full fresh candidate, acceptance evidence, PDF exports, no source mutation and no exposed ports. Review provider data rights before user distribution. This image is a batch validation job; it does not provide a public dashboard service.
6. Drill provider outage, stale prices, invalid forecast, corrupt artifact, concurrent run and failed refresh. Confirm nonzero exit, retained failure evidence and no promotion. Test restoration of an encrypted backup of the private input/evidence folders into an isolated directory; verify hashes and rerun acceptance. Record recovery time and acceptable data-loss window. Existing paper-broker backup routines alone do not qualify this separate recommendation workspace.
7. Configure host monitoring to alert the operator on service failure, missing daily receipt and disk exhaustion. The nominated test recipient is Michael Kazibwe (`kazibwekawumi@gmail.com`); no alert has been sent or delivery verified. Use an authenticated configured transport and a reviewed test message. Local failure receipts and journald exist; external alert delivery remains a host acceptance gate.
8. Only after a successful manual run and monitoring/recovery checks, install `deploy/systemd/strategy-validation.service` and `.timer`, reload systemd and enable the timer. It runs weekdays at 22:30 UTC plus up to two minutes jitter, safely after the US close in either daylight-saving season. The application uses NYSE sessions and its 15-minute publication delay; repeated holiday sessions are skipped.
9. Public access is a separate release: specify jurisdiction, data licensing and audience; implement qualified multi-user identity/authorization, HTTPS ingress, privacy controls and tenant isolation. Keep `strategy_dashboard_server.py` loopback-only. A random local token is not a public multi-user identity system.

No host, image, external alert delivery, recovery drill or 20-session observation is marked passed without actual evidence. The private dashboard remains available while these gates are pending.

## Verified local results

- Full regression suite: **1,284 passed**; Ruff passed.
- All twenty saved allocation scenarios reconciled capital/risk constraints and artifact integrity.
- Four real custom one-quarter calculations exported matching calculation-specific PDFs successfully.
- Daily wrapper completed successfully, health check passed, and a repeated refresh skipped the already-observed session.
- Observation ledger: **1 of 20 actual sessions**. No timer, public endpoint, external alert or broker operation was installed/enabled.
- Deployment gates are recorded explicitly in `var/strategy-operations/deployment-gates.json`.

## Repairs 2–4 checkpoint — 31 October 2026

See [REPAIRS_2_3_4_VALIDATION.md](REPAIRS_2_3_4_VALIDATION.md) for strict CSV/scenario/PDF reconciliation, durable v2 job/observation receipts, watchdog and explicit quarantine recovery, and prospective NAV/forecast accounting. Use `var/strategy-operations-v2` for new observations; the prior v1 root remains archived and untrusted for migration. Current v2 state is 1 operational observation and **0 forward return sessions**, not a completed observation period. No timers, external alerts or public deployment were enabled.
