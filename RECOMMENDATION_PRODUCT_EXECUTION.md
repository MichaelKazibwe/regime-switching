# Recommendation guide execution — 5 November 2026

The local engineering work below has been executed. External qualification, elapsed operating history and independent sign-offs remain open; this is not public-release approval. The recommendation product remains separate from managed-account execution.

## Changes executed

- `productstate.py` commits the API recommendation and account high-water state in one SQLite transaction with full synchronous durability. Private JSON files are recoverable exports. A failed export cannot discard committed risk state. Duplicate recommendation identities return the stored result. Existing account JSON is read for migration; account/currency checks remain enforced.
- `investment_product.py` now locks the account state across reading, planning, checkpointing and report generation. A competing CLI process fails rather than overwriting the account peak. The existing state-before-report checkpoint remains conservative if rendering fails; multi-file reports are not represented as one atomic filesystem transaction.
- `product_build.py` stages a 72-file import closure, dashboard assets and hashed dependencies, checks every hash and excludes private snapshots, credentials, tests and backups. Dirty workspaces produce explicitly labeled candidates; no clean commit was invented. `Dockerfile.recommendations` now consumes that staged context.
- `.github/workflows/recommendation-ci.yml` adds Python 3.12 product tests, minimal-context image build, import/source verification, CLI and synthetic plan/viewer/replay smoke checks, vulnerability scan, SBOM and image/source identity retention. This workflow was prepared locally; it was not pushed or executed remotely.
- Four new historical 1,000-path examples and PDFs were generated at `var/product-guide-execution/final-previews`. Each exact snapshot replay matched the current product source/dependency release. Existing accepted examples, account ledgers and dashboard allocations were preserved. Synthetic packaging checks are explicitly not market-performance evidence.

## Reconciled rollout queue

The old proposed filenames in `ROADMAP_TO_DEPLOYMENT.md` are interface suggestions, not requirements to duplicate later implementations.

| ID | Local implementation / evidence | Remaining qualification |
| --- | --- | --- |
| D01 | Accepted UI baseline and later authorized functional updates retained | Release-bound independent UI acceptance |
| D02 | Minimal hashed product source context generated and verified | Review/version all intended changes into a clean commit |
| D03 | Source/config/contract identities in training reports and three separate immutable cohorts | Reviewed champion designation and signed profile acceptance criteria |
| D04 | `strategy_training_data`, `macro_feature_contract`, `market_quality`; verified completed-session capture | Independent provider comparison, financial inputs and data rights |
| D05 | Parameterized chronological training/replay and next-close prospective ledgers | Independent investment validation |
| D06 | `scheduled_strategy_validation`, `observation_recovery`, `observation_process`; locking, retries and durable receipts | Qualified host resource/outage operation |
| D07 | Engineering acceptance and preserved strategy protocols exist | Owner/reviewer-signed numerical investment thresholds; cannot be invented after inspecting returns |
| D08 | `run_p1_refinement`, `scheduled_p1_research`; finite trials, purged calibration and retained candidates | Genuine future comparison and independent candidate review |
| D09 | `strategy_degradation`, `forecast_calibration`, `live_p1_service`, separate watchdog | External alert delivery, sufficient matured predictions and actual operator receipt |
| D10 | Host recipes and runbooks retained | Host access/provisioning explicitly deferred; encrypted volume/secrets/off-host operation unqualified |
| D11 | Recommendation-specific image CI, minimal context and local smoke added | Docker/CI execution, exact image scan/SBOM/digest; Docker unavailable locally |
| D12 | Hourly Mac collection and bounded weekly research already enabled; latest viewer publication integrated | Mac awake/login/network dependency; qualified continuous host and external monitor |
| D13 | Atomic API result/state commit, recoverable exports, single-owner API lock and CLI account lock; failure-injection tests | Host-level crash/power-loss/backup qualification; no claim that all HTML/PDF files commit atomically |
| D14 | Authenticated loopback single-operator APIs with bounded requests and private account paths | Chosen identity provider/gateway, per-user authorization/revocation, HTTPS, encrypted storage and actual multi-user isolation qualification |
| D15 | Fail-closed jurisdiction/service/mandate-bound evidence intake | Reviewed first jurisdiction, legal service scope and actual signed evidence; provisional targets are not approvals |
| D16 | Cash/cost/expenses/tax/FX/access gates implemented and remain blocked | Actual independently reviewed files/contracts; owner previously confirmed these are absent |
| D17 | Paired conditional scenarios, drift/cost assumptions and numerical replay; exact preview replays rerun | Independently signed distribution/calibration validation and genuine forward observations |
| D18 | Source- and mandate-bound `productrelease` receipts prohibit self-issued approval | Human promotion/rollback sign-off and qualified compatible-state recovery; no promotion performed |
| D19 | Portfolio-period PDF/email machinery, consent/enrollment checks and retry boundaries exist | Complete post-registration month, subscriber enrollment, sender configuration and authorized actual receipt |
| D20 | All thirteen dashboard sections opened in Safari; authenticated data/calculation/PDF checks retained separately | Mobile/cross-browser and independent release-bound accessibility/visual qualification |
| D21 | Local backup/replay, corruption/provider-failure/restart tests and recovery drills exist | Real host outage/off-host restore, external escalation and named operational acceptance |
| D22 | Three decision registrations and three return sessions through 4 November across cohorts | Actual pilot history: 60 complete sessions, three scheduled review opportunities and owner sign-off; cannot backfill decisions |
| D23 | Current catalogue and conservative FX/access restrictions retained | Reviewed regional instruments/service permissions and measured hosting/support capacity before expansion |

## Six recommendations: unresolved inputs

1. Instrument roles are implemented; domicile, local availability, disclosures and licensed data need reviewed provider evidence.
2. Economic components are implemented; independent factor/currency/duration/alternative suitability review is pending.
3. Risk state and recovery controls are implemented; contract acceptance and fresh-observation re-entry/forecast evidence need independent review. Retired return/drawdown targets remain historical.
4. Allocation and cost constraints are implemented; priors, severity, impact coefficients, fund expenses and measured look-through need financial validation.
5. Currency/tax/access inputs are implemented; jurisdiction and local product mappings need qualified approval.
6. Local product, reports, state and image-CI preparation are implemented; production identity, privacy/retention, licensing, infrastructure and independently observed investment quality remain unqualified.

## Evidence locations

Final unified acceptance: **engineering PASS; 14 passing checks, zero failed checks and eight blocked release prerequisites**. Full regression: **1,490 passed, zero failures/errors/skips**. Repository Ruff, JavaScript syntax and bound source/input/ledger stability passed. The first failed helper-fixture run is retained; the linked latest run uses the corrected source. The four final-source 1,000-path previews and PDFs replay exactly; the final 72-file staged source also passed synthetic plan/viewer/replay smoke in isolation. No actual image build or scan is claimed.

- Candidate source identity: `var/product-guide-execution/release-context-final/release-manifest.json`.
- Four exact replays: `var/product-guide-execution/replay-verification.json`.
- Synthetic smoke: `var/product-guide-execution/synthetic-smoke/smoke.json`.
- Fresh unified acceptance and full-regression XML: `var/product-guide-execution/acceptance/latest.json` and its linked run.
- Browser/API verification from the dashboard integration: `var/dashboard-verification/latest.json`.

No emails, trades, external publication, manufactured observations, self-issued PASS attestations or production identity/host deployment were performed. The separate viewer login service remains disabled after macOS denied Documents-folder access; direct viewer operation and the already-enabled collector are distinct from automatic viewer startup.
