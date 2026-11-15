# Deployment roadmap — accepted dashboard, continuous validation, controlled release

**Updated: 30 October 2026. This section is the current delivery plan.** Earlier paper-only plans below are historical implementation detail, not evidence of current public-release readiness. The first product is **recommendations, simulations and charts**, not client account management. The accepted investor dashboard is now frozen. The 14-asset paper worker remains a separate qualification path.

**Current position:** 1,245 local tests pass; Ruff passes. No host exists yet; no background research timer has been enabled; no public recommendation release is qualified. Saved investor examples use 29 October 2025 prices. Do not call those examples live or claim the research strategies are already active behind them.

Read the evidence and module audit in [SYSTEM_DEPLOYMENT_AUDIT_2026_10_30.md](SYSTEM_DEPLOYMENT_AUDIT_2026_10_30.md). The automation architecture, cadence and tuning policy are in [CONTINUOUS_STRATEGY_VALIDATION_PLAN.md](CONTINUOUS_STRATEGY_VALIDATION_PLAN.md).

## Dashboard V2 implementation checkpoint

A subsequent owner request extends the V1 freeze: [INVESTOR_DASHBOARD_V2.md](INVESTOR_DASHBOARD_V2.md) records the complete 26-asset map, latest/plan-time macro overlays, quarterly conditional outlook, strategy context, risk/performance charts and PDF integration. Current FRED data was captured on 30 October 2026. This is a private reporting enhancement, not completion of the recurring evaluator, current-data portfolio requalification or public investment-release gates. The saved portfolio remains dated 29 October 2025.

## Fresh-data strategy / allocation implementation checkpoint

The current-data capture, purged classifier fitting, frozen 252-session evaluation, macro-driven candidate allocation lab, all-asset roles, conditional portfolio scenarios, PDF appendix and authenticated loopback recalculation service are implemented and locally exercised. See [LIVE_STRATEGY_AND_MACRO_ALLOCATION_GUIDE.md](LIVE_STRATEGY_AND_MACRO_ALLOCATION_GUIDE.md). The completed run retains its original risk constraints, 130 data-quarantined evaluation sessions and a failed predictive-alpha gate; it is not approved for promotion. Recurring host scheduling, independent monitoring/recovery, investor service qualification and public release remain open gates.

## Deployment milestones and acceptance

| Order | Milestone | Deliverable | Exit gate |
|---|---|---|---|
| 0 · P0 | Freeze and reconcile | Accepted UI baseline; complete source/dependency manifest; named owners and scope | Dashboard source hashes recorded; reviewed runtime files versioned; original risk mandate retained; clean reproducible candidate |
| 1 · P0 | Reliable current-data boundary | Immutable 28-instrument snapshots and release-aware macro inputs; explicit eligible instruments, fees/rates/FX | Latest completed session only; no fabricated data; provenance/availability checks and outage tests pass; provider use approved for intended audience |
| 2 · P0 | Continuous shadow evaluation | Registry, one-shot runner, durable job ledger, matched benchmarks and dated risk diagnostics | All registered fixed strategies replay; errors and missing jobs alert; no mutation of investor state; one complete current-data run verified |
| 3 · P0/P1 | Controlled candidate tuning | Bounded chronological search, trial accounting, frozen forward track and review package | Predeclared criteria and parameter ranges; credible net risk/return evidence; no automatic promotion or loss-capacity relaxation |
| 4 · P0 | Private hosted operation | Linux Docker host, pinned image, single scheduler, backups/secrets/alerts and operational runbook | Exact image CI/scan/SBOM/import tests, restore/replay, failure drills and delivered heartbeat; only then enable unattended research |
| 5 · P0 before clients | Product service hardening | Transactional state/publication, private client artifacts, identity/tenant authorization and bounded authenticated service | Crash/concurrency/idempotency/isolation tests; no forgotten peak; no cross-user data access; secure transport and retention verified |
| 6 · P0 before clients | Scoped investment and data approval | First jurisdiction, audience, service classification, suitability and instrument/data rights review | Release-bound evidence for actual scope; verified assumptions; owner and independent approval; unsupported targets disclosed |
| 7 · P1 | Controlled invited pilot | Accepted UI served through the private service, scoped user access, reports and monitoring | Operator qualification; restore/alert drills; documented observation and review; no unexplained incidents or risk breaks |
| 8 · P2 | Wider release | Capacity, support, regional mappings and audited release process | Pilot gates passed; approval for each new jurisdiction/use; measured service targets; rollback and support ownership operational |

Do not wait for investment backtests to finish before engineering the data/operational boundaries. Conversely, passing tests or a host smoke test does not establish investment suitability. Milestones 3 and 4 can progress independently after their inputs are defined; client release needs both operational and financial/legal gates.

## Prioritized implementation to-do list

The owner remains accountable for scope and investment acceptance; engineering owns runtime/data integrity; an independent model reviewer owns validation; appropriate legal/data-rights reviewers own jurisdiction and provider approval. These are roles still to assign where not already named, not approvals asserted by this document.

| ID | Priority | Change / addition | Existing modules to use or amend | Done when |
|---|---|---|---|---|
| D01 | P0 | Freeze investor interface | `dashboard/investor.*`, `investor_dashboard.py`, `productreport.py` | **DONE locally:** `dashboard/investor-baseline.json`; only bug, accessibility or data-correctness fixes until next design review |
| D02 | P0 | Reconcile source and release scope | `paper_release.py`, `productrelease.py`, Git inventory, dependency locks | Runtime source including new UI assets is reviewed/versioned; clean candidate and reproducible hashes, with prior archives preserved |
| D03 | P0 | Register champion and challengers | Add `strategy_registry.py`; existing four macro strategies + separate product planner | Versioned source/config/universe/risk contract, account state, timing and benchmark mapping for each; none falsely marked approved |
| D04 | P0 | Fresh immutable data pipeline | Add `currentdata_pipeline.py`; reuse loader/calendar/vintage/store | Complete-session gate, in-progress-bar exclusion, per-asset eligibility, adjustment/revision checks and snapshot manifests tested |
| D05 | P0 | Generalize evaluation inputs | Add `prospective_evaluation.py`; adapt reusable research functions | Explicit snapshot/start/end/output; no hidden fixed cutoff/input path; point-in-time decisions and later fills; original studies retained |
| D06 | P0 | Durable one-shot research job | Add `research_job.py`; reuse stores/logging | Singleton/idempotent account updates, committed run pointer, crash recovery, timeout and resource controls; outputs research-only |
| D07 | P0 | Predeclare investment tests | `STRATEGY_ACCEPTANCE.md`, registry and mandate documents | Profile-specific net-return/downside/cost/calibration thresholds frozen before evaluation; unsupported 50%/5% goal not rebranded |
| D08 | P1 | Weekly bounded candidate search | Add `challenger_search.py` and immutable experiment ledger | Train/validation/forward separation, overlapping-label purge, all trial counts saved, neighboring-parameter/cost stability evidence |
| D09 | P1 | Drift and risk diagnostics | Add `modelmonitor.py`; reuse attribution/stress/logging | Drawdown/ES/exposure/turnover/calibration monitors, stale/missing-job alarm and actual operator receipt tested |
| D10 | P0 for automation | Choose/provision private host | Existing Docker/Compose/systemd patterns | Owner chooses host; SSH/access, time sync, patched OS, encrypted volumes, secrets and off-host backup qualified |
| D11 | P1 | CI recommendation image path | `.github/workflows/paper-ci.yml`, `Dockerfile.recommendations` | Python 3.12 locked tests; product image build/import/CLI/viewer smoke; image scan/SBOM/digest retained; no secrets bundled |
| D12 | P0 for automation | Install dedicated research scheduler | Add research Compose service + systemd units | Only after D03–D06 and host checks; timer enabled, next run and successful completed-session run evidenced; external missed-job monitor |
| D13 | P0 for service | Transactional product state/artifacts | `recommendation_api.py`, `investment_product.py`, `productaudit.py`, `recommendationrisk.py` | Failure injection proves state and publication commit together or recover safely; multi-process ownership/idempotency covered |
| D14 | P0 before multi-user | Client identity and access isolation | Product API + established identity provider/gateway + private artifact endpoint | Per-user ownership, revocation/expiry, HTTPS, request limits, bounded jobs and tenant isolation tests; never expose local JSON directories |
| D15 | P0 before public | Define jurisdiction and product scope | `clientmandate.py`, `productrelease.py`, reviewed disclosures | Appropriate service/data/suitability review and release-bound evidence; no assumptions that recommendations are automatically unregulated |
| D16 | P0 before investor release | Verify economic inputs and data rights | `productexecutioncost.py`, `productallocation.py`, data manifests | Fund expenses, cash yield, cost/impact model, applicable tax/FX inputs and redistribution rights independently supported |
| D17 | P1 | Validate scenario distributions | `productsimulation.py`, dynamic strategy simulator, model validation suite | Conditional versus predictive claims correct; pathwise switching separate from static plans; calibration/sensitivity and coverage reports |
| D18 | P1 | Human promotion/rollback procedure | Add `promotion_review.py`; reuse release/qualification receipts | Only signed version-bound approvals move candidate to champion; rollback restores compatible code, config and state, not a reset peak |
| D19 | P1 | Qualify investor reports and subscriptions | `monthlyreport.py`, `monthlydelivery.py`, product report service | Shared-paper versus per-user product metrics defined; period/account isolation, consent, PDF correctness, unsubscribe/bounce/retry policy tested |
| D20 | P1 | Preserve UI, certify behavior | Existing investor UI; browser CI tooling | Mobile/browser/keyboard/contrast, empty/blocked plans, amount bounds, chart inspection and exports tested without redesign |
| D21 | P1 | Operational acceptance | `paper_backup.py`, stores, alerts, runbooks | Host outage, provider outage, corruption, partial write and off-host restore drills; operational owners and absence escalation assigned |
| D22 | P1 | Invited observation and sign-off | Product pilot runbook; paper qualification only for separate paper worker | Review every incident; proposed product pilot has at least 60 complete sessions and 3 scheduled allocation review/rebalance opportunities, plus owner sign-off; this minimum does not prove multi-year returns |
| D23 | P2 | Regional expansion and capacity | Product catalogue/access mapping/service capacity | Verified local instruments/currency disclosures and approved service scope per region; load and support targets measured before expansion |

No dependency installation, host purchase, public publication, email delivery or customer deployment was performed by writing this plan. Costs and vendor selection are deliberately not invented.

## Immediate execution queue

- [x] Accept and hash the investor dashboard baseline.
- [x] Run full local regression and Ruff; record current evidence.
- [x] Check a current-data provider connection and identify the incomplete-day hazard.
- [x] Audit runtime paths and create this priority/dependency plan.
- [ ] **Next engineering unit: D03–D06, in that order** — strategy registry, immutable current-data snapshot, general evaluation boundary and one-shot job. Include tests for the current intraday-bar finding.
- [ ] In parallel with engineering decisions: owner selects first host and first client jurisdiction; independently review provider/data rights and economic assumptions.
- [ ] Then D08–D12: bounded tuning, monitors, exact product image CI and an enabled dedicated scheduler.
- [ ] Close D13–D21 before invited investor service; observe D22 before wider release.

## Operating rules for background improvement

Evaluate daily; search a bounded candidate space weekly; review releases monthly or on a justified material change. Freeze the investor-facing champion between approved releases. A candidate may improve return at unacceptable risk, or reduce losses by remaining in cash; both trade-offs must be visible. No optimization target takes precedence over the actual client's loss capacity, liquidity or instrument restrictions.

Use all 28 assets as a reviewed **menu**, not a forced 28-holding allocation. ALLW remains benchmark-only and actual history is limited by inception. Track factor concentration, duration, credit, currencies, liquidity, sector overlap and total risk; use signed risk shares alongside capital weights. Keep matched strategic and All Weather-style references, actual ALLW overlap and cash returns. A proxy is not official Bridgewater fund performance.

Do not silently lower the evidence standard after losses or report only successful experiments. If a monitored approved strategy breaches its operational/data contract, stop new recommendation publication, preserve evidence and alert. Portfolio loss alone is not an infrastructure failure; follow the explicitly approved investment-risk policy rather than inventing a liquidation.

## Definition of a completed release

**Private automated research:** qualified host/image/feed, running singleton timer, append-only state, real successful run, delivered alerts and tested restore; no client recommendation or order authority.

**Invited investor recommendation pilot:** the above plus transactional private product service, identity/isolation, scoped review and verified economic/data assumptions; accepted dashboard displays only the authorized user's current approved snapshot and its actual status.

**Public investor release:** invited pilot acceptance plus appropriate jurisdiction-specific approvals, tested capacity/support/privacy/security processes, reproducible promoted model, monitored performance claims and reviewable rollback. The original 50%/three-year/5% aspiration is not a release guarantee.

<!-- HISTORICAL ROADMAP BELOW -->

## Historical paper deployment roadmap and implementation notes

The material below is retained for traceability. Dates, test counts and statuses reflect the point at which each note was written; use the current plan above for prioritization.

# Roadmap to Deployment

**Current client-facing product scope:** recommendations with simulations and charts, as selected by the owner. [RECOMMENDATION_PRODUCT_GUIDE.md](RECOMMENDATION_PRODUCT_GUIDE.md) documents the implemented 28-instrument menu, client mandates, constrained allocation, costs/taxes/currency inputs, private interactive reports, input replay and authenticated local operator API. The existing 14-asset paper execution system remains a separate internal qualification tool. Public recommendation release is closed until an initial jurisdiction, verified providers/instruments, client suitability, independent model validation, privacy/security and operational approvals are established. Local code completion does not confer worldwide authorization or validate the earlier return target.

**Four-strategy research checkpoint:** [FOUR_MACRO_STRATEGIES_ASSESSMENT.md](FOUR_MACRO_STRATEGIES_ASSESSMENT.md) compares four fixed macro-aware designs with earlier V3/V4 candidates, strategic growth benchmarks, the constrained All Weather-inspired proxy and actual ALLW overlap. It includes prior-only macro-condition forecasts, risk-budget feasibility, conditional drawdown/return estimates and preserved 50%/three-year, 5%-decline gates. Implementation and tests do not confer an optimum designation, strategy acceptance, or paper-runtime eligibility.

**2026-10-30 strategy mandate checkpoint:** The owner specified **50% cumulative return over three years with at most 5% account peak-to-trough decline**. [THREE_YEAR_GOAL_ROADMAP.md](THREE_YEAR_GOAL_ROADMAP.md) records the bounded implementation and evaluation; [THREE_YEAR_GOAL_ASSESSMENT.md](THREE_YEAR_GOAL_ASSESSMENT.md) records the failed feasibility screen. None of 180 fresh research accounts met both objectives. This strategy remains research-only; paper promotion is closed. Existing production authorization and risk-budget tolerances are unchanged. Historical phase completion below does not override this strategy acceptance gate.

**Goal:** reach a production-like **paper deployment in the short term**, then treat live trading as a separate future program requiring broker qualification and explicit authorization. The paper system may consume real market data and generate simulated orders, but must not submit live orders.

**Status at roadmap creation:** development/integration. The project has substantial portfolio, risk, OMS, execution-safety, recovery, audit, and operational code. It is not yet deployment-ready.

## How to use this roadmap

- Work through the gates in order. A gate is complete only when its exit criteria have evidence in the repository.
- Keep a decision log for scope changes, unresolved risks, and accepted limitations.
- No live orders or live credentials are used during development, qualification, or paper deployment.
- Do not mark a phase complete based only on code presence, a prior report, or a passing isolated unit test.
- Re-run relevant evidence on the current commit and record command, environment, result, and artifact.

## Current evidence snapshot

The detailed current-state gap assessment is in [PAPER_DEPLOYMENT_GAP_AUDIT.md](PAPER_DEPLOYMENT_GAP_AUDIT.md). Treat historical validation counts and module-registry readiness claims as unverified until reconciled with current artifacts and the release commit.

| Area | Progress found | Remaining gap |
|---|---|---|
| Portfolio decision and risk | Latest local regression suite passes **1,054 tests**, including the dashboard and monthly reporting; strict risk-budget validation is in the production authorization path. | Strategy quality and out-of-sample return acceptance remain research gates; Python 3.12 lock install is not yet verified. |
| Market and macro data | Pinned paper runtime manifest and Yahoo Finance/FRED adapters are present; data freshness and lag checks are implemented. | Controlled live-source smoke test, provider suitability/terms, and point-in-time macro-vintage policy still require qualification. |
| Execution boundary | Paper lifecycle is wired through authorization, OMS, router, paper broker, accounting, and reconciliation; current E2E is **54 PASS, 0 FAIL, 0 BLOCKED**. | Production-like paper observation and failure drills remain; live broker submission is disabled and out of scope. |
| Operational safety | Kill switch, circuit breaker, restart recovery, health, audit, alerting, runbook, trading calendar, and clock-related tests/reports exist. A stored clock certification reports 223 focused executions passed. | This is not full deployment evidence. Persistence, monitoring, alert delivery, recovery under realistic failures, and production environment behavior still need qualification. |
| Repository/release | Current branch is `main`, HEAD `7d214f7`, reported 14 commits ahead of `origin/main`. | The working tree has many modified and untracked files. Preserve and reconcile them before release; do not assume all are disposable or canonical. CI/release and secret scanning need evidence. |
| Deployment readiness | One-shot worker, SQLite persistence, Docker/Compose packaging, CI, environment example, and runbook exist. | Docker build, scheduled host rehearsal, monitored paper observation, and owner sign-off are not complete. |

The saved E2E result is in `e2e_proof_results.md`; its matrix definition is in `E2E_PROOF_MATRIX.md`. The prior inventory/readiness claims in `MODULE_REGISTRY.md` and `SYSTEM_INVENTORY_AND_DEPLOYMENT_READINESS.md` should be reconciled against current files before relying on them.

**Missing-inventory implementation update:** Release staging/manifest verification, release-bound evidence receipts/assessment, complete runtime backup/restore/replay, historical FRED vintage selection, PyPI artifact-hashed companion locks, controlled alert testing, and a strategy acceptance protocol are implemented. See `PAPER_DEPLOYMENT_GUIDE.md`. Michael Kazibwe is the selected pilot operator; his supplied recipient is kept in ignored local configuration. No host exists yet, local GitHub authentication is invalid, and hosted CI/target-host drills/60-session observation remain open. This is local implementation progress, not deployment sign-off.

## Short-term target: paper deployment

The next concrete milestone is an automated paper portfolio service that can, on a defined schedule, ingest and validate data, produce an auditable portfolio decision, run risk checks, create simulated orders, account for simulated fills and costs, reconcile state, and alert an operator when anything is wrong.

For the first paper release, keep the scope narrow: the existing 14 ETFs, one documented rebalance schedule, one benchmark hierarchy, one paper broker, and conservative risk limits. Prefer robust daily or scheduled operation over intraday execution. Keep the live broker disabled and unreachable from the paper deployment configuration.

### Paper deployment code changes and module ownership

The items below are change areas to inspect and implement as required; listing a module does not assume it needs a rewrite.

**Implementation checkpoint (2026-10-29):** Implemented the one-shot paper worker (`paper_service.py`), Yahoo Finance/FRED data adapter (`paperdata.py`), authorized OMS → router → paper broker → accounting → reconciliation flow (`paperexecution.py`), versioned SQLite checkpoints for OMS/account/broker/reconciliation state, cycle-scoped order IDs, single-process locking, rebalance interval enforcement, JSON reports, and a persistent failure alert log. The worker cannot instantiate a live broker and leaves blocked/rejected decisions unexecuted. IV-B.4 risk validation now computes the regime risk-budget result and enforces the existing `1e-6` tolerance plus configured leverage/concentration limits before authorization. To satisfy the strict budget, `ProductionComposition` defaults its expected-return tilt to zero; nonzero tilt remains configurable but fails closed when it breaches the budget. Added exact package pins and Python 3.12 CI/container-build jobs, Docker/Compose worker packaging, paper environment example, runbook instructions, and restart/lifecycle tests. Latest local Python 3.14 validation after P1 updates: **1011 pytest tests passed**, `ruff check .`, `git diff --check`, and `pip check` passed. The 54-proof E2E runner reports **54 PASS, 0 FAIL, 0 BLOCKED**. A controlled read-only Yahoo Finance/FRED smoke check passes for 14 ETFs, 3,771 price rows, and all required macro inputs, stamped with the latest completed NYSE close. This computer has no Python 3.12 or Docker executable; the exact lock install and image build need the CI runner.

P0 implementation is complete for the local paper worker. Deployment qualification remains: install and test the exact lock on Python 3.12, build the Docker image, run a controlled Yahoo/FRED smoke test with deployment secrets, and rehearse the scheduled host deployment. The system remains paper-only and fail-closed. Current E2E artifacts replace stale results; earlier reports are preserved under `/tmp/regime_switching_prior_e2e_20261029/` and `/tmp/regime_switching_e2e_before_strict_risk/`.

**P1 implementation checkpoint (2026-10-29):** Paper execution costs are configurable and reported per fill; durable daily valuation marks now include cash, NAV, marked positions/weights, cumulative return, benchmark-relative return, drawdown, turnover, and cumulative costs. A self-contained HTML operator dashboard refreshes after each cycle. Rejected, blocked, and not-due cycles still carry operator marks. Added optional SMTP alerts for rejected/blocked decisions and failed cycles while retaining the local JSONL alert record; added `paper_admin.py` commands for SQLite online backup and integrity/hash-chain verification, and documented review, stop, recovery, and backup procedures in the runbook. The data adapter now requires prices through the latest completed NYSE session, including early closes/holidays. Pilot defaults are 14 ETFs, simulated $1,000,000, 21 calendar-day rebalance interval, 1% cash buffer, strict `1e-6` risk tolerance, 5 bps commission, 10 bps slippage, and 60 trading sessions with at least three completed rebalances. Latest full local suite: **1011 passed**. The worker still fills fully at adjusted close; daily bars cannot support measured spread, queue, depth, delayed-fill, or market-impact simulation. Email delivery, restore drills, notification ownership, and operation on the target host must be verified there.

**P2 implementation checkpoint (2026-10-29):** Added a content-addressed, hash-verified snapshot store for market/macro inputs, effective non-secret configuration, source/dependency/Python provenance, decision-time NumPy RNG state, and read-only replay. Preserved mapping order because asset order is material to portfolio math; excluded only generated per-run decision IDs from replay comparison while retaining them in the audit event. Snapshot artifacts are under `var/research-snapshots` and are included in the persistent `/app/var` Docker volume. The P2 test suite passes locally (**3 passed**) and exact decision replay now reproduces the saved weights, expected returns, covariance, scenario output, and stable risk fields. P2 implementation is complete locally. The snapshot records the data vintage observed at decision time; it does not create historical FRED vintages or cure point-in-time bias in backtests.

**Paper toolchain implementation checkpoint (2026-10-29):** Expanded `.github/workflows/paper-ci.yml` with full-SHA-pinned actions, Python 3.12 tests and E2E proof execution, PyPA `pip-audit`, Trivy source/config secret scanning, exact built-image vulnerability scanning, CycloneDX SBOM generation, and retained evidence artifacts. Added `.github/dependabot.yml` for Python, Docker base-image, and Actions updates. Added a weekday `systemd` service/timer and installation notes under `deploy/systemd`. The local full suite now reports **1014 passed**; targeted Ruff and `git diff --check` pass. The local environment has no Docker, systemd validator, or hosted GitHub runner, so image build/scan, hosted Python 3.12 lock install, Dependabot, and remote security workflows have not been executed here. The repository owner still needs to verify/enable native GitHub secret scanning and push protection if available.

| Priority | Change area | Existing modules to review/extend | Paper-release result |
|---|---|---|---|
| P0 | Decision identity and traceability | `portfoliodecisionengine.py`, `productiondecisionexecution.py`, `productionintegration.py`, `productionpipelineintegration.py`, `productionexecutiongate.py` | Every decision has one stable `decision_id`; source data timestamp/version, regime, forecasts, risk checks, target weights, and rejection reasons are retained. |
| P0 | Data contract and freshness | `marketdataloader.py`, `tradingcalendar.py`, `assetuniverse.py`, `validators.py`, `core_constants.py` | Explicit expected assets/calendar/timezone; reject stale, incomplete, misaligned, nonpositive, duplicate, or malformed prices; record source and as-of timestamp. |
| P0 | Repeatable configuration | `core_constants.py` plus a new typed configuration module and checked-in example config | Strategy, universe, risk limits, rebalance schedule, costs, data sources, and paper/live mode are validated at startup. Secrets are injected outside source control. |
| P0 | Reproducible environment | New `pyproject.toml` or equivalent dependency manifest and lock; CI workflow | Supported Python version and pinned runtime/dev dependencies; clean setup and CI steps. Include market/data and notification dependencies only when used. |
| P0 | Persistent paper state | `oms.py`, `portfolioaccount.py`, `orderbook.py`, `restartrecovery.py` and a new persistence/repository adapter | Persist decisions, orders, fills, positions, cash, and checkpoints transactionally; support idempotent restart/replay and schema versions. In-memory state alone is insufficient for an unattended service. |
| P0 | Paper-only runtime boundary | `paperbroker.py`, `brokerrouter.py`, `livebroker.py`, `productionexecutiongate.py`, `productionpipelineintegration.py` | Paper config cannot instantiate or route to the live broker; startup asserts paper mode; live route requires a separate explicit deployment configuration and remains off. |
| P0 | Scheduled orchestration | `productioncomposition.py`, `productionpipelineintegration.py`, `rebalanceengine.py`, `tradingcalendar.py` plus a new CLI/worker entry point | Single scheduled cycle: data check → decision → risk gate → rebalance plan → paper execution → accounting/reconciliation → persisted report. Safe on duplicate invocation. |
| P0 | Logs, audit, and alerts | `structuredlogging.py`, `audittrail.py`, `operationalevent.py`, `operationalhealth.py`, `alertengine.py`, `emailtransport.py` | Structured logs with correlation IDs; append-only decision/execution audit; actionable alerts for failed cycles, stale data, breached limits, recovery, and reconciliation breaks. |
| P0 | End-to-end contract | `e2e_proof_runner.py`, `E2E_PROOF_MATRIX.md`, `test_phase_iv_f_execution_safety.py`, phase III/IV/I tests | Fix E2E decision identity failure, then prove the full paper lifecycle and fail-closed bypass protections on the candidate release. |
| P1 | Paper fill and cost realism | `paperbroker.py`, `transactioncostmodel.py`, `tradegenerator.py`, `brokerexecutionengine.py`, `paperexecution.py` | Configurable commission/slippage assumptions are charged and exposed per fill. Partial/cancel/reject lifecycle exists in broker components. Runtime still fills at adjusted close; credible quote/volume-based spread, delayed-fill, market-impact and market-session simulation remains a qualification gap. |
| P1 | Operator visibility | `paperexecution.py`, `paper_service.py`, `paperalerts.py`, `analytics.py`, `executionanalytics.py`, `riskreport.py` | Per-cycle marked positions/weights, cash, NAV, cumulative return, benchmark-relative return, drawdown, turnover, costs, data time, decision/risk and reconciliation status; persistent JSON reports/alerts and optional SMTP delivery. No interactive dashboard is packaged. |
| P1 | Recovery and operations | `paperstore.py`, `paper_admin.py`, `restartrecovery.py`, `reconciliationengine.py`, `killswitch.py`, `circuitbreaker.py`, `OPERATIONAL_RUNBOOK.md` | Online SQLite backup and integrity/hash-chain verification commands; fail-closed active-order recovery and documented manual procedures. Target-host restore/restart/kill-switch drills and operator ownership remain to be completed. |
| P2 | Research-data store | `researchdatastore.py`, `researchreplay.py`, `paper_runtime.py`, `paperstore.py`, `paper_admin.py` | Implemented locally: content-addressed input/config/runtime capture, mapping-order preservation, decision-time RNG context, read-only replay, and exact decision comparison. P2 tests pass; host-volume backup/restore and historical macro-vintage qualification remain deployment/research gates. |

### Tools to include for the paper milestone

The target is a small, auditable daily paper service. Use one tool per responsibility, keep the runtime image lean, and do not add a second database, metrics platform, queue, or orchestration layer without measured need.

| Responsibility | Paper-milestone tool | Project coverage and completion requirement |
|---|---|---|
| Source control and release evidence | Git + GitHub pull requests, protected `main`, reviewed release tag | Repository is already on GitHub Actions. Gate 0 still has to reconcile the dirty working tree before a release can be cut. Require passing CI and a reviewed change before merge; retain the release commit, configuration fingerprint, container digest, and qualification evidence together. |
| CI and supported runtime | GitHub Actions; Python 3.12; Docker build job | `.github/workflows` already runs Python 3.12 lint/tests and builds the Docker image. Keep CI read-only, grant minimum `GITHUB_TOKEN` permissions, and pin third-party actions to reviewed full commit SHAs before treating the workflow as release-grade. The Python 3.12 lock install and container build still need a successful CI run. |
| Python dependencies | Exact pins plus `requirements-paper.hashed.lock`, `requirements-dev.hashed.lock`, and `lock_paper_dependencies.py`; pip | Candidate PyPI artifact hashes are generated; CI/Docker now install with `--require-hashes`. Verify installation on clean Python 3.12 and fail qualification on unresolved drift. |
| Code quality | Ruff (`ruff check .`) | Ruff lint is wired into CI. The formatter check currently reports 174 files requiring formatting; keep formatting out of this deployment change and schedule a reviewed style-only change before adopting it as a required gate. |
| Automated tests | pytest; existing unit/integration/paper-lifecycle tests and E2E proof runner | CI runs `pytest -q`. Local exact decision replay and complete backup/restore replay now pass. Require all unit/math, contract, integration, recovery, paper lifecycle and E2E gates again on the clean Python 3.12 release. |
| Python dependency vulnerabilities | Pinned PyPA `pip-audit` GitHub Action against both locked requirement files | Added to CI; hosted execution and any finding remediation remain release gates. Never auto-ignore advisories. The action audits requirements files ([project documentation](https://github.com/pypa/gh-action-pip-audit)). |
| Container vulnerabilities and SBOM | Pinned Trivy scan of the built image; CycloneDX SBOM retained with the build | Added to CI; hosted execution and review of all critical/high findings remain release gates. The exact image scan is required, not a separately rebuilt image ([action documentation](https://github.com/aquasecurity/trivy-action)). |
| Secret protection | Trivy source secret scan in CI; enable GitHub secret scanning and push protection when the account plan supports them | Current-tree secret/config scan is wired into CI. Historical secret exposure review and native GitHub settings still require owner verification. Never use real provider or SMTP credentials in CI. GitHub feature availability depends on repository type and plan ([availability](https://docs.github.com/en/code-security/concepts/secret-security/about-alerts)). |
| Dependency change monitoring | Dependabot for Python requirements, Docker base image, and GitHub Actions | `.github/dependabot.yml` added. Review updates through CI; do not auto-merge paper-runtime dependency updates. Rebuild, audit, regression-test, and retain the new SBOM first. |
| Market and macro data | Existing `paperdata.py` adapters: yfinance for ETF history, `fredapi` for FRED observations; `pandas-market-calendars` for NYSE session timing | Adapters and validation exist. Before unattended use, confirm source terms, data rights, availability, adjusted-price behavior, rate limits, and outages. Record provider, retrieval time, observation/as-of time, and stale/missing-data outcome. Treat FRED revisions as a separate point-in-time research gap; a saved current vintage is not a historical vintage. |
| Input research archive | `researchdatastore.py` content-addressed snapshot artifacts under `var/research-snapshots` | Snapshot hashing, order-sensitive input/config fingerprints, RNG context, and exact decision replay are implemented and covered by local tests. Keep the database and artifacts together; verify backup/restore and replay on the target host before qualification. |
| Paper decision and execution | `paper_service.py`, production decision/risk gate, `paperexecution.py`, paper broker, OMS, account, reconciliation | Existing one-shot flow is paper-only and produces persisted reports. Live trading and broker submission stay disabled. Use no live broker SDK or live credential in this deployment. |
| State and audit | SQLite via `paperstore.py`; hash-chained events, JSONL audit, OMS/account/broker/reconciliation snapshots | Existing local persistence is sufficient for one serialized daily worker. Preserve the SQLite database, audit log, reports, alerts, and research snapshots in the same persistent volume; verify integrity and event hashes after backups. Do not run multiple writers or place the database on an unqualified network filesystem. |
| Scheduler and host | Docker Compose one-shot worker triggered by the supplied host `systemd` timer after the completed NYSE close | Timer/service and install notes are added under `deploy/systemd`. The actual host/timer is not provisioned. Use a single-instance lock, missed-run review, no automatic execution retry, and no inbound application port. |
| Monitoring and operator view | Structured application logs, durable cycle reports, local JSONL alerts, static HTML dashboard; optional SMTP transport | Existing logging/report/dashboard/alert paths cover the single-worker pilot. Verify alert receipt and owner/on-call escalation on the host. Keep a daily review of freshness, cycle status, risk result, fills/costs, NAV, reconciliation, and recovery status. Prometheus/Grafana and a hosted log stack are not required for one daily worker. |
| Backup and maintenance | `python -m paper_admin backup`, `verify`, and `replay` | Backup, integrity/hash-chain checks, and local exact replay tests exist. Back up SQLite plus audit/reports/alerts/snapshot files, restore into an isolated directory, verify, and rehearse on the host. |
| External-data smoke and soak | `python -m paper_admin data-smoke`; controlled host-side 60-session paper observation | Smoke command exists and uses real provider access; do not put secrets in CI. Run it in the deployment environment before scheduling. Complete the 60-session/three-rebalance observation and document exceptions, notifications, recovery, and reconciliation. |

#### Required CI and release sequence

1. On each pull request: install the exact dev lock on Python 3.12; run Ruff lint, the complete pytest suite, and the E2E proof gate; run secret and dependency scans; build the paper image; scan the built image; and retain test, audit, SBOM, and image-identity artifacts. Formatter checks remain deferred until the project-wide formatting change is reviewed.
2. On the release candidate: repeat those checks from a clean checkout, verify no secrets or unexpected files enter the image, confirm paper-only environment flags, and record the source commit, lock hashes, image digest, scan results, and configuration fingerprint.
3. In the target host: inject secrets through the host’s protected configuration mechanism; verify the image digest, persistent volume, scheduler, clock/timezone, data smoke, backup, alert delivery, and operator access; then begin the observation period.
4. During the observation period: review every cycle, alert, blocked/rejected action, stale-data event, restart, and reconciliation difference. Any unresolved incident resets the acceptance period according to the operator’s documented policy.
5. Close the tools gate only when hosted CI/image scans pass with no unaccepted findings, native repository security settings are reviewed, exact replay passes on the deployed image, restore and alert drills pass, and the host soak has the required evidence and owner sign-off.

Do not add broker-vendor SDKs, Kubernetes, Redis/message queues, a hosted database, a data warehouse, or heavyweight metrics infrastructure for this pilot. Revisit those choices only when the deployment changes to multiple workers, higher frequency, stronger availability, or live-broker qualification. Strategy-research candidates are listed separately below and are not paper-runtime requirements.

### Strategy returns and diversification research plan

Return improvement is a research question, not a guarantee. First establish whether the existing strategy has robust net-of-costs value; change one component at a time and keep an untouched baseline. The first priority is to improve measurement and diversify sources of risk, not simply add more tickers or complexity.

#### 1. Make performance evidence credible

- Build a point-in-time, walk-forward dataset with prices adjusted consistently for distributions/splits, exchange calendars, realistic rebalance timing, and transaction costs.
- Prevent look-ahead and survivorship bias; use vintage macro observations or conservatively lag series by their actual publication schedule.
- Use chronological train/validation/test periods and rolling or expanding walk-forward tests. Reserve a final untouched period for one-time evaluation.
- Report CAGR, volatility, Sharpe and Sortino, maximum drawdown, Calmar, tail loss/expected shortfall, turnover, exposure, capacity sensitivity, and net returns after spreads/slippage/fees. Include confidence intervals or block-bootstrap uncertainty where appropriate.
- Compare against SPY, cash/T-bills, equal weight, static risk parity, and simple strategic ETF allocations. Use ablations to isolate regime, forecasts, Black-Litterman, risk budgeting, constraints, and volatility targeting.
- Test parameter sensitivity and regime subperiods; report when performance depends on a narrow parameter choice or a small number of observations.

#### 2. Diversify exposures deliberately

- **Asset class and economic driver:** the current ETF universe already spans US/international equities, nominal government bonds, credit, precious metals, broad commodities, and REITs. Measure actual factor and crisis behavior; ticker count is not diversification.
- **Equity geography and style:** review US mega-cap/growth concentration in SPY/QQQ, small caps via IWM, and international developed/emerging exposure via VEA/VWO. Add value, quality, minimum-volatility, or equal-weight exposures only if data availability, overlap, costs, and test evidence justify them.
- **Rates and credit:** distinguish duration exposure (TLT/IEF/SHY), credit spread risk (LQD/HYG), and inflation sensitivity. Avoid treating bonds as a stable equity hedge across all inflation/rate regimes.
- **Real assets:** measure gold, silver, broad commodities, and REIT sensitivities separately; they are not interchangeable inflation hedges.
- **Strategy sources:** test trend/time-series momentum, cross-sectional momentum, defensive/quality signals, carry where the instrument set supports it, and volatility-managed exposure as separate sleeves. Do not combine until each sleeve has a clean independent benchmark and cost model.
- Use correlation-under-stress, factor exposure, marginal risk contribution, and drawdown overlap. Regime-conditional or shrinkage correlation estimates may help, but require stability checks and conservative fallbacks.

#### 3. Quant techniques to evaluate in sequence

1. **Robust baselines and shrinkage:** compare simple moving-average/trend rules and strategic allocations; use Ledoit-Wolf or other covariance shrinkage and robust covariance alternatives against the current estimator. Check conditioning and out-of-sample risk calibration.
2. **Volatility and risk budgeting:** compare inverse-volatility/risk-parity weights, capped risk contribution, volatility targeting, and drawdown-aware exposure controls. Add turnover penalties and position/sector caps; test net benefit after costs.
3. **Forecast calibration:** express signals on comparable standardized scales and a defined forecast horizon; calibrate expected returns conservatively, shrink toward zero or a prior, and track forecast error and calibration by asset/regime. Avoid feeding uncalibrated signals into Black-Litterman as if they were expected returns.
4. **Regime robustness:** test simple observable rules against probabilistic regime models (e.g. hidden Markov/state-space) only if the added estimation risk is justified. Measure transition stability, classification delay, and performance when regime labels are wrong. Use hysteresis or probability thresholds to reduce churn where evidence supports it.
5. **Portfolio optimization:** compare constrained mean-variance, risk budgeting, Black-Litterman with calibrated view uncertainty, and robust optimization. Penalize turnover; enforce long-only/leverage/asset limits as intended; test weight stability under small input changes. Prefer the simplest model that survives out-of-sample tests.
6. **Tail and stress risk:** add historical and hypothetical stress scenarios, expected shortfall, drawdown limits, and correlation breakdown tests. Use these first as risk controls and diagnostics, not as precise return forecasts.
7. **Validation discipline:** use nested walk-forward model selection and a trial log to reduce backtest overfitting; consider deflated Sharpe/probabilistic Sharpe and multiple-testing corrections when many variants are tried.

Candidate libraries after environment review: `scikit-learn` for standardization, model evaluation and some regime/statistical methods; `statsmodels` for time-series diagnostics; a tested covariance/optimization stack (for example, `PyPortfolioOpt` or direct `cvxpy` models) only if it replaces rather than duplicates project logic; `arch` for volatility-model research if needed. Pin and validate any adopted library, check numerical behavior and licenses, and keep the production runtime lean. These are research candidates, not prerequisites for paper deployment.

#### Research acceptance rule

Promote a strategy change only when it improves a predeclared net-of-costs objective or materially reduces risk without unacceptable return loss across multiple walk-forward periods, survives parameter/cost stress, and is reproducible from saved data and configuration. Keep the baseline available for direct comparison and rollback.

## Ordered deployment gates

### Gate 0 — Protect and establish the current baseline

**Priority: immediate.** The working tree contains user/project work in progress, so preserve it before any cleanup, refactor, or release operation.

Actions:

1. Inventory the current branch, commit ancestry, modified/untracked/ignored files, and generated artifacts; map each to an owner/purpose.
2. Identify the canonical production modules and distinguish them from backups, archives, generated reports, and legacy implementations.
3. Reconcile `MODULE_REGISTRY.md`, the readiness report, E2E matrix/results, regression logs, and source inventory. Label each item current, historical, stale, or unverified.
4. Decide how to preserve the current work safely (for example, a reviewed checkpoint/branch) before any cleanup or integration.
5. Record the current interpreter and environment without installing or changing dependencies.

**Exit criteria:** a reviewed source-of-truth inventory; no unexplained file in the working tree; a named baseline commit/environment; an evidence index with timestamps and commit IDs. No project files are deleted as part of reconciliation.

### Gate 1 — Define the deployment product and operating limits

Actions:

1. Confirm the first deployment target as paper-only service; record whether it is fully automated or operator-triggered and what decisions the operator reviews.
2. Define assets, rebalance schedule, capital assumptions, order types, session behavior, benchmark, risk limits, and permitted operating hours.
3. Define who may configure, start, stop, recover, approve, and monitor the service.
4. Define failure policy for stale/missing prices, missing macro observations, market holidays, partial data, rejected decisions, broker outages, and reconciliation breaks.
5. Define measurable acceptance thresholds for performance, drawdown, turnover, tracking error, availability, alert latency, and recovery time. Values must be chosen by the project owner; do not infer them from code defaults.

**Exit criteria:** signed-off operating specification, risk limits, ownership/on-call responsibilities, and explicit paper-versus-live boundary.

### Gate 2 — Repository and build reproducibility

Actions:

1. Reconcile the 14-asset universe and all ticker aliases across data, regime, optimizer, backtest, and execution components.
2. Establish supported Python version(s), dependency manifest and lock, deterministic setup instructions, and configuration schema.
3. Keep secrets out of source and artifacts; document secret injection, rotation, and access controls. Review ignored/untracked files and the bundled ZIP/DMG/source dumps for accidental sensitive or irrelevant material.
4. Add or confirm CI for formatting/lint, type or static checks where applicable, imports, unit/regression tests, and artifact generation.
5. Establish a clean, reviewable release branch and tag policy. Do not commit or publish until the owner has reviewed the current changes and scope.

**Exit criteria:** a clean reproducible checkout can install from the declared lock and pass baseline CI; release contents and secret scan are reviewed.

### Gate 3 — Functional and architecture certification

Actions:

1. Preserve the locally passing decision identity behavior from E2E-01: ensure identity is created once, immutable, and preserved from portfolio decision through accounting/audit; certify it on the release image.
2. Reconcile the reported `PortfolioDecisionEngine` macro input contract (`unemployment` versus older fixtures using other fields) and make production/test contracts explicit.
3. Inspect all production modules for public contracts, validation, failure handling, state transitions, serialization compatibility, dependency direction, and unused/duplicate legacy paths.
4. Verify asset universe consistency and reject missing assets or invalid inputs explicitly; check regime-policy coverage for every supported regime.
5. Confirm the system fails closed on invalid, stale, partial, or out-of-order inputs and on exceptions at every orchestration boundary.

**Exit criteria:** documented module/API map; no unresolved P0/P1 defect; current-tree unit and integration suite green; deterministic repeated decisions for identical inputs; serialization and restart compatibility evidence.

### Gate 4 — Quantitative research and backtest validation

Actions:

1. Verify price adjustments, calendars, missing-data handling, survivorship assumptions, and transaction-cost/slippage assumptions.
2. Establish point-in-time macro availability. FRED historical revisions must not leak future revisions into past decisions; document the vintage/source policy.
3. Run the 14-asset walk-forward backtest with strictly lagged information and no future observations. Preserve data versions, parameters, and decision-level audit output.
4. Compare benchmarks and ablations: SPY, equal weight, regime-only, risk-budget-only, forecast contribution, Black-Litterman contribution, constraints, volatility targeting, and full strategy.
5. Use out-of-sample and sensitivity analyses across periods/regimes, costs, rebalance frequency, and data perturbations; report uncertainty and drawdown/tail risk, not only Sharpe/annualized return.
6. Independently review whether forecast signal units/horizons and Black-Litterman views are calibrated and economically interpretable.

**Exit criteria:** reproducible research report, no look-ahead leakage found, approved performance/risk thresholds met out of sample, and all strategy components have attributable contribution or a documented decision to remove/disable them.

### Gate 5 — Execution lifecycle and end-to-end proof

Actions:

1. Rerun the locally passing E2E-01 and full proof runner against the clean release source baseline.
2. Clear all mandatory E2E failures and blockers in dependency order: decision/risk authorization, canonical OMS order, authorized handoffs, routing, paper broker receipt, accounting, order lifecycle, provenance, and reconciliation.
3. Add or verify negative proofs for bypass attempts, malformed authorization, duplicate/replayed receipts, partial fills, cancels/replaces, stale authorization, and mismatched identities.
4. Verify cash, positions, fees, realized/unrealized P&L, and OMS/broker/account reconciliation under complete, partial, duplicate, late, rejected, and corrected executions.
5. Preserve E2E evidence with commit, environment, timestamps, and immutable results.

**Exit criteria:** every mandatory E2E proof passes on the release candidate; zero unexplained blocked/failed proofs; all money, quantity, identity, authorization, regime, and provenance invariants reconcile.

### Gate 6 — Operational and security readiness

Actions:

1. Choose and validate durable persistence for orders, fills, positions, decisions, audit events, and recovery checkpoints; test corruption, disk-full, and schema/version migration cases.
2. Verify monitoring and alerts for data freshness, decision failures, risk limits, rejected orders, broker health, reconciliation breaks, kill switch, circuit breakers, and restart recovery.
3. Exercise startup, graceful stop, crash restart, recovery failure, clock/session boundaries, dependency outage, rate limiting, and alert transport failure.
4. Complete threat/security review: credential handling, dependency vulnerabilities, least privilege, network access, audit integrity, access logs, and incident response.
5. Complete capacity and resilience checks, backup/restore procedures, retention policy, and disaster recovery objectives.

**Exit criteria:** documented and rehearsed runbooks; reliable durable recovery; alert delivery proven; security findings resolved or formally accepted; operational owner and escalation path assigned.

### Gate 7 — Paper deployment qualification

Actions:

1. Deploy into an isolated production-like environment with live trading and live broker submission disabled by configuration and enforced in code.
2. Run shadow decisions against live market inputs without submitting orders, then compare proposed decisions, risk checks, and expected fills with independent calculations.
3. Run paper orders through the actual OMS/router/paper broker and reconciliation lifecycle over the agreed observation period and representative market conditions.
4. Review every exception, alert, data gap, rejected action, restart, and reconciliation difference.
5. Meet the pre-agreed availability, risk, behavior, and monitoring thresholds for the full observation period.

**Exit criteria:** written paper qualification report and owner sign-off; all unresolved incidents closed; no bypass path; successful recovery and reconciliation evidence.

### Gate 8 — Broker integration qualification (only if live execution is in scope)

Actions:

1. Select the broker and verify its API, order semantics, rate limits, market sessions, asset support, and legal/account requirements.
2. Implement broker adapter and credentials in a sandbox environment; verify health, submit/acknowledge, modify/cancel, partial fill, reject, timeout, retry, and disconnect behavior.
3. Prove idempotency, duplicate prevention, reconciliation, and safe recovery after ambiguous network outcomes.
4. Conduct broker sandbox and operational acceptance with no production capital.

**Exit criteria:** broker-specific conformance evidence and approval. If the first deployment remains paper-only, this gate stays explicitly deferred and the live path remains disabled.

### Gate 9 — Controlled canary and deployment decision

Actions:

1. Review the release candidate, all gate evidence, known risks, rollback plan, runbooks, and monitoring dashboard.
2. Confirm production configuration, data entitlements, secrets, limits, timezone/calendar, persistence, and access controls.
3. Obtain explicit human approval from the accountable owner. For live mode, separately approve broker access, capital limits, and live trading enablement.
4. Start with a tightly limited canary consistent with the approved risk envelope; monitor continuously and halt on any threshold breach.
5. Reconcile positions, orders, and cash independently; document the decision to continue, roll back, or stop.

**Exit criteria:** deployment is accepted only for the approved mode and limits, with a tested rollback and ongoing operational ownership. Live trading requires its own explicit sign-off; passing engineering gates alone does not enable it.

## Recommended immediate sequence

1. **Gate 0:** preserve and reconcile the working tree and current evidence; this remains open because many pre-existing modified/untracked files have not been individually attributed.
2. **Gate 1:** approve operating limits, schedule, observation duration, and operator ownership.
3. **Gate 2:** verify the exact dependency lock on Python 3.12 and build the container in the target environment; review release contents and secret scanning.
4. **Gate 3:** close remaining architecture/data-contract review items and document strategy acceptance thresholds.
5. **Gate 4:** validate point-in-time macro data and strategy performance out of sample before calling returns deployment-ready.
6. **Gate 5:** maintain the passing 54-proof E2E baseline and add/execute deployment-specific failure drills.
7. **Gate 6:** qualify data/alert integrations, security, backups, monitoring, and recovery in the target environment.
8. **Gate 7:** rehearse scheduled operation, then complete the agreed paper observation period and owner sign-off.
9. **Gate 8:** qualify a broker only if live execution is a requirement.
10. **Gate 9:** make a separate, explicit deployment decision and proceed through a controlled canary.

## Definition of deployment

For this project, **paper deployment** means an operated, monitored, production-like service that consumes real data but cannot submit live orders. **Live deployment** means routing real orders and requires all prior gates plus broker qualification, approved capital/risk limits, independent operational readiness, and explicit human authorization. The project should not claim live readiness merely because the software compiles or its unit tests pass.

## Evidence update log

| Date | Change | Evidence basis |
|---|---|---|
| 2026-10-29 | Initial roadmap created from repository inventory, current Git status/history, module registry, operational runbook, saved regression outputs, clock certification, and E2E results. | Read-only inspection; no tests or project scripts run for this roadmap. |
| 2026-10-29 | Expanded short-term paper deployment scope with module-level code changes, runtime/engineering tools, and a staged quantitative returns and diversification research plan. | Existing source inventory and saved validation artifacts; recommendations are proposed work, not completed implementation. |

### 30 October 2026: operational strategy acceptance

Added `strategy_operations.py` (capture/report/scenario acceptance and immutable prospective session ledger), `scheduled_strategy_validation.py` (locked isolated refresh with failure receipts), `Dockerfile.strategy-validation`, `compose.strategy.yaml` and `deploy/systemd/strategy-validation.*`. See [STRATEGY_DEPLOYMENT_ACCEPTANCE.md](STRATEGY_DEPLOYMENT_ACCEPTANCE.md). Current evidence does not certify a Docker image, external monitoring, public deployment or a completed 20-session observation period.

## Repairs 2–4 checkpoint — 31 October 2026

See [REPAIRS_2_3_4_VALIDATION.md](REPAIRS_2_3_4_VALIDATION.md) for strict CSV/scenario/PDF reconciliation, durable v2 job/observation receipts, watchdog and explicit quarantine recovery, and prospective NAV/forecast accounting. Use `var/strategy-operations-v2` for new observations; the prior v1 root remains archived and untrusted for migration. Current v2 state is 1 operational observation and **0 forward return sessions**, not a completed observation period. No timers, external alerts or public deployment were enabled.

## Repair 5 — economic design, 31 October 2026

Implemented and executed `economic_design_assessment.py` and `economic_design_report.py`: independent path/profit reconciliation, observed SGOV versus unverified user cash, cost/availability attribution, prior-close risk-budget references, paired block-bootstrap intervals, 28-asset diagnostics, aggregate stress review and a declared three-year reference frontier. See [ECONOMIC_DESIGN_REASSESSMENT.md](ECONOMIC_DESIGN_REASSESSMENT.md). The 30 configurations × 29 overlapping cohorts produced no joint 50%-return/5%-drawdown success. This is not proof of impossibility. All four economic screens remain blocked; no current weights, predictive gate, investor dashboard or prospective cohort changed. The next numbered repair is 6, the unified product contract; independent economic validation and actual cash/exposure inputs remain prerequisites.

## P0/P1 execution checkpoint — 31 October 2026

See [ECONOMIC_P0_P1_EXECUTION.md](ECONOMIC_P0_P1_EXECUTION.md) for source/reviewer evidence gates, official release-incident reconciliation, the separately solved stress-budget challenger, predeclared cost/fallback comparisons, reviewed recovery validation and independent prospective cohorts. The owner confirmed no verified files are available, so cash/cost/access/exposure gates remain blocked. Active challenger configuration is `research/stress_budget_challenger_v2.json`; original strategies and their cohort are unchanged. V2 shadow results and daily-handoff templates do not imply financial approval or a qualified host.
