# Paper Trading Deployment Gap Audit

**Audit date:** 2026-10-29
**Scope:** Current repository implementation and evidence for a single-host, scheduled, paper-only deployment. Live brokerage qualification is out of scope.

## Executive assessment

The repository contains the main application path required for a paper pilot: market and macro ingestion, regime and portfolio decisions, risk authorization, simulated OMS/broker execution, accounting and reconciliation, durable state, event audit, reports/dashboard, alerting, snapshot/replay, a one-shot worker, Docker Compose packaging, a systemd schedule, and operational procedures.

The largest remaining gaps are **release and host qualification**. The repository is **not yet qualified for unattended deployment** because the exact Python 3.12/container release has no recorded successful hosted run, the owner confirmed no host exists, and alert/backup/recovery/soak evidence must be produced there. The local GitHub authentication token is invalid. Strategy return acceptance is a separate research gate; passing software checks does not establish investment performance.

The implementation following the audit passes **1,032 pytest tests** locally on Python 3.14.3. It adds release staging/integrity checks, an evidence ledger and assessor, complete backup/restore and exact replay drills, a historical FRED vintage adapter, hash-checked candidate dependency locks, and an explicit strategy acceptance protocol. These local results do not replace Python 3.12/container/host qualification. Earlier 999/1,011/1,014 counts are historical checkpoints. See [PAPER_DEPLOYMENT_GUIDE.md](PAPER_DEPLOYMENT_GUIDE.md) for executable procedures and [STRATEGY_ACCEPTANCE.md](STRATEGY_ACCEPTANCE.md) for research acceptance.

### Research update — 30 October 2026

The current development suite passes **1,132 tests**. Actual archived unemployment, CPI, industrial-production and Treasury releases are frozen for the new macro/market research engine. [SMART_REGIME_PORTFOLIO_ASSESSMENT.md](SMART_REGIME_PORTFOLIO_ASSESSMENT.md) records cycle tests, exact asset/group risk reconciliation, chronological optimization, a macro ablation and conditional loss simulations. The candidate remains **unaccepted for replacement**: lower drawdown has not established higher profit or lower loss frequency.

The exploratory legacy-allocator path accepted only **40 of 207** proposals under its strict final-budget filter, first trading in June 2015. This path used daily Ledoit-Wolf covariance and price-derived regimes, so it is not a full production-pipeline rejection study. It does expose a material feasibility question that must be checked under the actual pipeline before strategy acceptance. Preserve fail-closed tolerance; do not treat inactive-history returns or passing software tests as proof of deployment readiness. The new macro state/risk contract is not wired into production authorization.

## Existing deployment modules

| Capability | Existing implementation | Audit finding |
|---|---|---|
| Market data and freshness | `marketdataloader.py`, `paperdata.py`, `tradingcalendar.py` | Yahoo Finance ETF prices and FRED macro data are fetched and validated; completed NYSE session and stale data checks exist. Provider terms, availability, rate limits, and the deployment secret still need qualification. |
| Regime and portfolio decision | `macroregime.py`, `regimeforecastengine.py`, `portfoliodecisionengine.py`, `productioncomposition.py`, `productionpipelineintegration.py` | Production decision/risk path exists. Return quality and point-in-time research acceptance remain open. |
| Order safety and paper execution | `authorizedorderintent.py`, authorized handoff modules, `brokerrouter.py`, `paperbroker.py`, `paperexecution.py`, `oms.py`, `reconciliationengine.py` | Paper lifecycle and safety boundary exist; live submission is disabled for the worker. Adjusted-close simulated fills are not realistic spread, depth, queue, or market-impact fills. |
| Persistence and replay | `paperstore.py`, `paper_runtime.py`, `researchdatastore.py`, `researchreplay.py` | SQLite state, event integrity, snapshots, and read-only decision replay exist. Backups and replay still need a target-host restore drill. |
| Operations | `paper_service.py`, `paper_admin.py`, `paperalerts.py`, `paper_dashboard.py`, `structuredlogging.py`, `operationalhealth.py` | One-shot cycle, reports, dashboard, local alert log, optional SMTP, and admin checks exist. Delivery and escalation have not been qualified with the named operator. |
| Packaging and schedule | `Dockerfile`, `compose.paper.yaml`, `.env.paper.example`, `deploy/systemd/*` | Rootless-in-container restrictions, persistent volume, read-only root filesystem, dropped capabilities, and single-host timer configuration are present. Host provisioning and actual scheduled operation remain unproven. |
| CI/security | `.github/workflows/paper-ci.yml`, `.github/dependabot.yml`, plain and hashed requirement locks | CI installs using artifact hashes, tests, audits, builds a manifest-verified image, scans it and exports that exact image with SBOM/checksum/identity. Published PyPI hashes have been fetched and lock consistency is tested; Python 3.12 compatibility and hosted execution remain unverified. |
| Release and qualification | `paper_release.py`, `paper_qualification.py` | Import-graph source staging excludes backups/secrets; file hashes and clean-commit status are bound to release identity. Receipts require a named reviewer and hashed artifacts. The assessor refuses missing evidence, dirty candidates, insufficient/gapped observations, synthetic data or mismatched release provenance. |
| Complete recovery | `paper_backup.py` | Uses the worker lock, bundles SQLite plus all runtime artifacts, verifies hashes/audit/event chains/snapshot references, and restores only to new destinations. Local tests restore and replay an actual deterministic paper lifecycle without orders. Target-host rehearsal remains open. |
| Historical macro research | `macrovintage.py` | Selects only releases available by the research decision time, uses conservative next-New-York-midnight availability for date-only FRED releases, and freezes/checksums datasets. Real historical vintage collection and research results remain open. |

## Prioritized gaps and exit criteria

### P0 — Required before unattended paper operation

1. **Establish a release baseline.** The working tree contains many modified/untracked files, duplicate variants, backups, and generated artifacts. Identify the intended release files and evidence; make a clean, reviewed release candidate without deleting or overwriting unrelated work. Reconcile current counts in the roadmap, E2E reports, and audit documents.
   - **Exit:** reviewed source commit, clean release checkout, current test/E2E artifacts tied to that commit.
2. **Prove the actual runtime build.** Run the configured GitHub checks successfully on Python 3.12, including dependency install/check, lint, tests, E2E, dependency audit, secret/misconfiguration scan, image build and vulnerability scan. Review generated SBOM and image identity. Resolve or formally accept every high/critical finding.
   - **Exit:** successful hosted run for the release commit; Python 3.12 lock works; image and scan artifacts are retained. No successful hosted run was evidenced in this audit.
3. **Qualify one target host.** Provision the approved Linux Docker host; inject `FRED_API_KEY` and optional SMTP credentials via protected host configuration; set restrictive ownership; confirm timezone, clock, disk capacity, outbound connectivity, persistent volume, host patching, SSH restriction, and Docker socket access. Install and verify the systemd timer/service.
   - **Exit:** recorded host configuration and access owner; image digest verified; timer and first scheduled cycle work with no inbound app port.
4. **Complete deployment drills.** On that host, run `paper_admin data-smoke`, trigger a controlled alert and confirm receipt, create and restore a backup in an isolated location, run integrity/hash-chain verification and exact replay, and exercise stale-data/provider failure, worker restart, and reconciliation review procedures.
   - **Exit:** retained drill results and named operator acknowledgement; restore/replay reproduces the original state/decision without orders.
5. **Complete paper observation.** Operate for the runbook’s 60 trading sessions and at least three completed rebalances. Review every cycle, alert, rejected/blocked action, stale-data event, restart, simulated fill/cost, and reconciliation difference. Resolve incidents and restart the acceptance period when policy requires.
   - **Exit:** signed paper qualification report with zero unresolved incidents and agreed operational thresholds met.

### P1 — Needed to make the pilot robust and the evidence stronger

1. **Verify dependency installation on the release platform.** Hash-checked companion locks and the update tool now exist. Exact version pins were resolved in Python 3.14.3 and compatibility still needs the configured fresh Python 3.12 CI install, build and image scan.
2. **Harden data-provider operations.** Document provider entitlement/terms and request limits; qualify transient failure behavior, timeouts/retries, recovery, and whether a durable last-good cache is required. Current fetches depend on external Yahoo/FRED availability each run; fail-closed behavior exists, but there is no demonstrated host-side outage drill or alternate source.
3. **Close operator and security ownership.** Name who receives alerts and who covers absence; verify GitHub secret scanning/push protection and repository branch protections as available; document OS update, secret rotation, disk-full, and backup retention responsibilities.
4. **Review paper fill assumptions.** Current paper execution fills at adjusted close using configured commission/slippage assumptions. Validate those assumptions against the strategy’s rebalance timing and disclose their limitations in performance reports; implement richer spread/market-impact simulation only if required by the acceptance design.

### P2 — Research acceptance before interpreting returns as deployment-ready

1. **Point-in-time macro data.** Current FRED values are delayed/lagged operationally, but snapshots preserve the vintage observed at each run; they do not supply historical FRED vintages. Historical backtests need point-in-time releases or a documented conservative vintage reconstruction.
2. **Out-of-sample strategy acceptance.** Define a frozen baseline, leakage/survivorship controls, walk-forward and untouched holdout periods, benchmarks, net-of-cost metrics, uncertainty analysis, and pre-agreed acceptance thresholds. Current software evidence does not prove positive or robust returns.
3. **Diversification and model selection.** Measure asset/factor concentration and compare against simple baselines; test regime, forecast, covariance, risk-budget, volatility-targeting, and allocation components via ablations and stability tests. Add complexity only when it improves robust holdout results.

## Missing-module inventory

There is no clear need to create another large strategy, regime, OMS, broker, persistence, dashboard, or scheduler module for the stated single-host paper milestone. The repository already has those responsibilities. The following are the genuine missing components or artifacts, separated by type:

| Inventory item | Priority | Local implementation | Remaining completion evidence |
|---|---:|---|---|
| Release manifest/evidence index | P0 | Implemented and tested: `paper_release.py`, `paper_qualification.py`; candidate context and fail-closed status report generated. | Review/commit the intended working tree; clean release and successful hosted evidence remain open. |
| Python 3.12 CI/container security | P0 | Workflow installs hash-checked pins, stages source, checks image imports, scans, creates SBOM and exports the scanned image. | GitHub login repair and successful hosted run; local Docker and Python 3.12 are unavailable. |
| Docker host/scheduler/secrets | P0 | Compose, systemd service/timer, protected image selection and deployment guide provided. | Owner confirmed **no host yet**. Provisioning, access, clock, volume and secret qualification are pending. |
| Alert ownership/escalation | P0 | Michael Kazibwe selected; supplied email saved in ignored local operator configuration; `paper_admin alert-test` implemented and tested. | Configure SMTP; verify human receipt; name absence escalation. No email has been sent. |
| Restore/failure/60-session records | P0 | Full runtime backup/restore and exact replay verified in local integration tests; release-bound evidence assessor implemented. | Host drills, off-host backup, 60 sessions/3 rebalances and owner paper sign-off remain pending. |
| Hash-checked dependency manifest/update procedure | P1 | `lock_paper_dependencies.py`, both hashed locks and consistency tests implemented; public PyPI hashes fetched. | Fresh Python 3.12 installation/build/scan must pass; source build dependency review remains necessary. |
| Point-in-time macro adapter/dataset | P2 | `macrovintage.py` implemented; release/revision leakage, duplicate keys and checksum behavior tested. | Acquire and freeze real vintage data; integrate it into the chosen historical evaluation and validate completeness. |
| Strategy acceptance protocol/results | P2 | `STRATEGY_ACCEPTANCE.md` defines chronology, baselines, costs, uncertainty, ablations and owner review. | Owner must freeze numerical criteria before holdout evaluation; actual research and signed results remain pending. |

No separate API server, Kubernetes cluster, Redis/message queue, hosted database, or broker adapter is required for this one-worker paper scope. Live broker integration remains intentionally outside the paper deployment milestone.

## Recommended execution order

### Local implementation evidence (2026-10-29)

- Full suite: **1,032 passed** on Python 3.14.3. Focused new-tool suite: **18 passed**, including restore-to-new-directory, exact replay with zero orders, re-backing-up restored state, release integrity, receipt integrity, observation checks, vintage leakage checks and admin refusal paths. The final explicit release allowlist change was verified again with **5 release tests passed**.
- Current E2E runner: **54 PASS, 0 FAIL, 0 BLOCKED**. Previous output artifacts were preserved under ignored `var/qualification/prior-e2e/` before regeneration.
- Ruff, installed dependency consistency, tracked diff whitespace checks and CI/Compose YAML parsing passed. A misplaced seed constant was moved after imports to clear the existing E402 lint failure without changing its value.
- A reviewable candidate was staged and verified at `var/releases/paper-candidate-20261029/release-manifest.json`. Its release ID is `0ab841907286c8af2aeec951e5b6440b5216ff475bdb7411be087e90fe10321e`; it explicitly records `clean_commit: false`. No files were deleted or committed as part of staging.
- `var/qualification/status.json` reports **BLOCKED**, as expected: no clean release, hosted receipts, host evidence or qualifying state/observation exists. These results have not been converted into fabricated PASS receipts. No external alert was sent.

1. Reconcile release contents and stale/conflicting evidence.
2. Produce a clean release commit and run the full Python 3.12 hosted pipeline; resolve findings.
3. Provision the approved isolated host and deploy the reviewed image/configuration.
4. Pass data, alert, backup/restore, replay, outage/restart, and reconciliation drills.
5. Run the 60-session/three-rebalance paper qualification and sign the report.
6. In parallel, advance point-in-time and out-of-sample strategy research; do not treat operational paper qualification as strategy return approval.

## Audit limitations

### Monthly reporting checkpoint

`monthlyreport.py` and `monthlydelivery.py` implement completed-month summaries, personalized PDF attachments for the shared portfolio, individually addressed TLS SMTP delivery, checksum verification, a persistent delivery ledger and explicit reconciliation of ambiguous sends. Default commands generate only; subscriptions remain inactive until approved. Monthly timer/service templates run on day 1 at 09:00 Europe/Warsaw and are not installed locally. Actual SMTP configuration and recipient receipt are still unqualified. A requested sample to Michael's supplied address is prepared but has not been sent: SMTP is unconfigured and Gmail connection is pending. PDFs for no-data and 14-holding layout cases were rendered and visually checked. The latest full suite passes **1,054 tests**, Ruff passes, dependency consistency passes, and CI YAML parses. Installed ReportLab/Pillow were added to exact/hash-checked locks; clean Python 3.12 build and hosted security scans remain required.

### Interactive dashboard checkpoint

The interactive frontend and local read-only API are implemented in `paper_dashboard.py`, `paper_dashboard_server.py`, and `dashboard/`. The full local suite now passes **1,039 tests** and Ruff passes. A real localhost smoke check retrieved all **14 ETF provider quotes** and **65 SPY three-month history points**; served HTML and its CSP script hash matched. JavaScript syntax was checked with the system JavaScriptCore engine. Browser visual inspection was unavailable because no automated browser was connected and Safari's native automation connection failed. Current portfolio panels correctly remain empty when no saved reports exist. The optional dashboard does not alter simulated execution or publish a host port in the worker's deployment configuration. Regenerate the release context after reviewing this frontend change.

This is a repository and saved-evidence audit, not a security penetration test, investment recommendation, legal review of provider terms, or proof of the current state of a remote GitHub repository or deployment host. Host, hosted-CI, provider, mail, and 60-session evidence must be appended when available.
