# Project review execution register — updated 18 November 2026

## Latest installed adaptive allocation release — 18 November 2026

This update supersedes the installed-state entries below. Their image and recovery receipts remain dated historical evidence.

The invitation-only local pilot at http://127.0.0.1:8782/#weekly now runs image `sha256:a867251d5f2e3de3209e13da4f1e777b7873519d231c9944c052631cda962a46`, source release `9deaacbc9fa99406e05a1ead77f41d7afd62c86145b621ffa182f63d7777260c`, from source commit `ecba72dbfdf5e18ca9c23a9ca9f36fd07ffb28a8`. All 200 shipped files match the tested source. The existing account, old input trees and rollback pointers were preserved.

Weekly horizon candidates now fit uncertainty-shrunk current-market return/covariance inputs, allow variable holding counts and independently enforce a 35% maximum positive signed variance contribution. The new adaptive aggregate fits its horizon proportions plus additional cash from those market inputs. The daily dynamic strategy also fits its engine proportions; its revised prospective cohort is separate from the old design. See [the allocation method and safeguards](ADAPTIVE_PORTFOLIOS.md).

- Final backend regression: **1,519 passed**. Chromium and WebKit acceptance passed on genuine data against the exact installed image, including all four weekly candidates, matching allocations/projections, comparison tables, refresh failure/recovery, roles, review controls and PDFs. The live Safari weekly page was separately observed after installation.
- The completed market session is **November 18**; weekly decision prices correctly remain at the completed week of **November 13**. The complete collection, benchmark, daily alpha, daily publication and weekly publication pipeline completed with no waiting stages. All **10 runtime checks** and **four feature-readiness checks** pass.
- Exact installed image security: **zero HIGH/CRITICAL findings** using the fresh November 18 database. Lower-severity findings remain separately tracked; no waivers or SBOM were introduced.
- All hosted release-code workflows pass: [pilot](https://github.com/MichaelKazibwe/regime-switching/actions/runs/44405899664), [paper](https://github.com/MichaelKazibwe/regime-switching/actions/runs/44405899522), [managed paper](https://github.com/MichaelKazibwe/regime-switching/actions/runs/44405899575), [recommendations](https://github.com/MichaelKazibwe/regime-switching/actions/runs/44405900782).
- Sampled local four-reader API load budget passes, p95 approximately **1.70 seconds**. This excludes WAN, sustained mixed optimizer/export load and broad scalability claims. Local browser acceptance reused a previously qualified toolchain after verifying identical dependency-lock hashes and copying the final sources/tests; the redundant download build was stopped. The canonical hosted build and browser checks also pass.
- The updated **14-page PDF** includes the aggregate proportions, holdings, risk shares, stress results, projections and dated dashboard context. Recommendations remain subject to client research review; the optimizer does not establish future outperformance or loss limits.

Detailed private evidence: `var/project-review/adaptive-allocations/`. The prior encrypted off-host recovery point remains a dated earlier release, not a new backup of this upgrade. Owner MFA, independent-device recovery, source/data-access rights, independent market evidence and sufficiently matured outcomes retain their separate requirements in [PILOT_GATE_REQUIREMENTS.md](PILOT_GATE_REQUIREMENTS.md). Trading, automatic promotion and production approval remain disabled.

## Earlier review and release evidence


The 32-item source review is [PROJECT_REVIEW_20261117.md](PROJECT_REVIEW_20261117.md). All findings now have an implementation or an explicit evidence/scope disposition below. **This does not mean all original institutional/public-release acceptance criteria are closed.** The current authorized scope is a free, local, invitation-only research pilot. Execution and automatic promotion remain disabled.

No paid server, domain, data subscription or storage account was created. Remote commercial access and externally qualified recovery are not represented as completed.


## Earlier execution status — 18 November 2026

This dated update supersedes the installed-image, security and operator-step status in the historical sections below. The free local invitation-only pilot remains at http://127.0.0.1:8782/; execution and automatic promotion remain disabled. Institutional/public release is not approved.

- Installed image: `sha256:5d42a323ea425a77fb2805c59340b5c0dee810a0f72e0d5ec3d3fd489434cc4c`; source release `86a7c68ef2899a0bef9846bc4feb3d6d11ed36727d185e62a9b2f19d219f3340`. All 200 shipped source files match the reviewed main revision; later CI/documentation changes do not alter that runtime.
- All 10 final local runtime checks and four feature-readiness checks pass. The complete daily/weekly/alpha/monitoring pipeline completed without waiting stages. Completed market session: November 17; weekly portfolio price cutoff: November 13, with daily macro context dated separately.
- Full host backend regression: 1,511 passed, followed by passing targeted release, native-runtime and recovery regressions. Genuine-data Chromium/WebKit acceptance passes, covering desktop/mobile views, state-dependent calculations, roles, scenarios, PDF/downloads and refresh. Four-reader sampled API p95 was approximately 1.05 seconds; this is a local sampled workload, not a WAN/service-scale qualification.
- The final exact-image scan passes the declared HIGH/CRITICAL threshold with zero findings at those severities, using the November 18 vulnerability database. Lower-severity findings remain tracked. No findings were waived, no threshold was lowered, and no SBOM was requested/generated. The runtime uses digest-pinned distroless Debian 13 and verified SQLite 3.54.1; release identities bind the native security inputs.
- Hosted checks pass on `a87e8dcd957bf27a5b16b9bbb255826a7474ca1e`: [pilot](https://github.com/MichaelKazibwe/regime-switching/actions/runs/44340419567), [paper](https://github.com/MichaelKazibwe/regime-switching/actions/runs/44340419433), [managed paper](https://github.com/MichaelKazibwe/regime-switching/actions/runs/44340419287), [recommendations](https://github.com/MichaelKazibwe/regime-switching/actions/runs/44340419240). These replace earlier failed-run status below.
- Coordinated recovery acquires all 10 registered host writer locks, stops application writers for export and restarts the pilot in a finally block. The final archive includes four VM volumes, host monitoring/cohort streams, the matching image source context and the allowlisted operator restore code with locked dependencies. Local decryption, database integrity, archived-operator-source restoration and isolated exact-image Linux restoration pass. The final encrypted archive was uploaded to Proton and downloaded with a matching SHA-256; its downloaded-copy exact-image Linux restore also passed. Account metadata and all three monitoring cohorts survived; copied sessions were revoked only in the isolated restored copy. Independent physical-device recovery remains untested.
- VM build-disk exhaustion was resolved by removing unused build cache and identified disposable build remnants; deployed data volumes and rollback images were preserved. The browser runner then built and passed acceptance.

### Remaining evidence and owner requirements

All 32 review findings have a recorded implementation or evidence/scope disposition. The following acceptance criteria remain open; engineering checks cannot substitute for them:

1. Owner must directly enroll Proton MFA and store recovery codes privately. Requiring a security-key PIN alone does not enroll a key or enable MFA. Browser policy requires owner entry and submission of new authentication credentials.
2. Keep a separately protected recovery-key copy away from both this Mac and the cloud backup account. Complete a fresh-host/independent-physical-device disaster restore; same-Mac isolated Linux recovery is narrower evidence.
3. Complete actual owner/independent source and client-data-access rights review. Free software and official macro data do not grant securities-data redistribution rights.
4. Supply actual independent aligned total-return prices, corporate actions/currencies, historical membership/delistings and dated issuer look-through holdings for admitted assets. Macro authorities cannot qualify securities prices or fund holdings.
5. Allow genuinely future observations and monthly/quarterly/annual outcomes to mature. The current small prospective sample does not establish alpha, optimal allocations or calibrated forecasts. Missing required macro observations remain unavailable rather than imputed.
6. External identity, valid HTTPS, firewall and remote-host qualification apply before expanding beyond the authorized local pilot. No paid domain, VM or data subscription is required for the present local test.

See [PILOT_GATE_REQUIREMENTS.md](PILOT_GATE_REQUIREMENTS.md) for concrete inputs and free operator procedures. Detailed local evidence lives under `var/project-review/`; it is not committed or published.

## Historical execution receipts — November 17

The sections below retain their original image, test and gate status as dated history; use the November 18 update above for current status.

## Engineering and research evidence

- Full backend suite: **1,504 passed** (`var/project-review/pytest-clean-final-all.xml`).
- Standalone complete regression: **1,108/1,108 checks passed** (`var/project-review/final-regression-end-to-end.log`); canonical harness: **26/26** (`canonical-regression.log`). The historical reference monolith `rewrite.py` remains inventoried/compiled, outside the active import/runtime contract; optional plotting/web/database packages were not installed just to import historical code.
- Legacy historical-data integration and walk-forward backtest passed with network access to their existing free sources. Those runs do not qualify revised macro data as historical-vintage investment evidence.
- Chromium and WebKit passed all 11 views, desktop/mobile, roles, research review, daily refresh, macro monitoring, benchmark scenario metrics, amount scaling and PDF/CSV/JSON exports against the exact app image and genuine captured inputs (`var/project-review/clean-ci-browser/acceptance.json`). Synthetic sealed-fixture acceptance also passed separately. An earlier export download timed out; its diagnostic rerun and subsequent genuine-data runs passed. This is retained as a transient observation, not erased.
- Four local readers, 20 requests: **p95 1.325 seconds**, no errors, maximum response **2,212,800 bytes**. Budgets: p95 under 10 seconds and response under 8 MiB. This excludes WAN and simultaneous optimization/export load.
- Synthetic optimizer capacity: 100 assets **0.085 seconds**; 500 assets **9.011 seconds**, allocation constraints passed. Not financial-performance evidence or a broad scalability certification.
- Two targeted mutation faults were killed: future FX sessions and silently missing reference holdings (`var/project-review/mutations-final/receipt.json`). This is not a whole-project mutation score.
- Selected critical-contract coverage was approximately **79%** over five named modules. Coverage is scoped and does not imply exhaustive correctness.
- Genuine model training and three-policy portfolio research were rerun through **2026-11-16**. All 11 declared macro masks failed the comparison screen. The uncertainty-shrink alternative reduced retrospective drawdowns and returns; it was not automatically adopted.
- A fresh isolated Linux container, with network disabled and no production volumes, completed imported-session collection, bootstrap, benchmark and daily/weekly publication. The pipeline correctly reported **WAITING** for the alpha trainer's new validated host session; it did not manufacture observations or training status. Receipt: `var/project-review/linux-pipeline-issued-evidence/receipt.json`.
- Encrypted archive: **131,194,931 bytes**. Authenticated decrypt/restore and isolated Linux validation passed; one invited account's metadata was preserved and sessions were revoked only in the restored copy. Host publication writers were not globally stopped, so full cross-component quiescence is not certified. **No off-host upload/download has occurred.**
- Exact final candidate image: `sha256:67899da3f4203454dd9eb3b0f861ed2c27fe52933fefa95f0d0853ea6a5c61dd`; source release `44428bb15c4d96fa0be4c940b4ce3875c574e9f78f5b78e1ca3ea22c301156b5`, qualification **CANDIDATE**. The fixable zlib finding was removed. The exact-image scan retains **47 HIGH findings, 11 distinct CVEs, none with a listed fix**, so its public security gate remains BLOCKED. No waivers or SBOM were generated.

## Disposition of every review item

“Verified” below describes the named engineering evidence; it does not grant investment, security, regulatory or production approval.

| ID | Implemented / evaluated | Remaining original acceptance requirement |
|---|---|---|
| A1 | Portable Docker discovery, verified filesystem publication, Linux orchestration/Compose/timer wiring, relocated bootstrap paths, imported monitoring streams; isolated Linux publication passed | Observe a genuinely new completed session and week on a clean host. Imported daily alpha training remains explicitly waiting. |
| A2 | Exact-image scan verifier, pinned available zlib security fix, public security gate retained | 47 unresolved HIGH findings; external proxy/TLS/firewall and owner review. Paid infrastructure deferred; declined SBOM remains opt-in. |
| A3 | Private-key authenticated encryption CLI, SQLite snapshot/integrity checks, safe extraction, local and Linux restore rehearsals | Free storage account, actual upload/download, separately protected recovery key, full writer-quiescence and fresh-host recovery objectives. |
| A4 | Typed final job states, retry limits, lock contention handling and failure receipts | Keep monitoring actual future scheduled failures; no unattended-service guarantee. |
| A5 | Separate telemetry and read-time heartbeat ageing; frozen-heartbeat regression | Actual alert delivery/operator response remains unqualified. |
| A6 | Independent snapshot, benchmark, macro-alpha and weekly readiness | Green capability readiness never replaces external release approval. |
| A7 | Explicit seal and subprocess-entry dependencies; synthetic and genuine portable artifacts loaded by exact Linux image | Hosted CI run/branch-protection evidence after publishing this source revision. |
| A8 | Bounded structured 503 overload, authenticated concurrency/isolation tests and local load budget | Larger simultaneous optimizer/export load and WAN measurements. |
| B1 | Reject future/stale FX observation sessions independently of publication times; adversarial tests and mutation check | Native listings still need separately qualified FX/venue data. |
| B2 | Missing positive reference holdings rejected; named unavailable references stay unavailable; weight validation and mutation check | New references require admitted input series. |
| B3 | XNAS/XTKS calendars and explicit capture/valuation/research/paper capability matrix | Metadata support alone does not admit new execution instruments. |
| B4 | Full 252-session independent comparison, missingness discrepancies and corporate-action arithmetic tests | Official exchange/issuer evidence, economic reconciliation, symbol/delisting histories and rights review. |
| B5 | Effective/available-time membership adapter with permanent identities and evidence fields | Actual point-in-time membership data and full replay integration; current-universe bias remains disclosed. |
| B6 | Versioned dynamic eligibility contract replaces hidden XLV removal; genuine replays regenerated | Independent review of the declared strategy design. |
| C1 | Genuine source-bound model evaluation and new prospective cohort; old ledgers preserved | Sufficient untouched prospective outcomes and demonstrated net predictive/portfolio advantage. Existing gate remains off. |
| C2 | Eleven predeclared masks, purged nonoverlapping origins, calibration/baseline scores and multiple-comparison bounds | All masks failed; sufficient future evidence is still required. No automatic selection. |
| C3 | Archived-protocol scoring, compatible-target checks, isolated qualification windows, immutable issued-forecast reconciliation across platforms | Wait for genuine targets to mature. No forecast rewriting or backfill. |
| C4 | Official BLS noncollection evidence recorded as post-hoc context, separate from model inputs | No October 2025 CPI value was invented; an alternative feature would require its own protocol. |
| C5 | Analytic optimizer gradient, uncertainty-shrink/turnover hypothesis, chronological validation/test report and adverse outcomes | New policy selection needs untouched evidence and stronger matched-risk comparisons. Current comparison is retrospective, not a new holdout. |
| C6 | Reviewed look-through aggregation for issuer/country/economic currency/sector; unknown coverage and breaches remain visible | Actual dated holdings, factor/liquidity evidence and independently reviewed measured limits. |
| C7 | Nonnegative loss ES convention plus signed tail return, cost/cash/tax sensitivity comparisons and stress results | Qualified asset/venue spreads, FX costs, cash yields, client taxes and liquidity assumptions. Sensitivities are not observed costs. |
| C8 | Genuine issuance records and realized horizon coverage, following-week execution and complete-week maturity checks | Monthly/quarterly/annual outcomes must actually mature; simulated intervals remain uncalibrated. |
| D1 | Push/PR synthetic full-image browser CI, exact app separated from browser runner, hash locks, coverage/artifacts; SBOM explicitly opt-in | Hosted workflow result and owner-controlled branch protection. |
| D2 | Adversarial financial/state/recovery tests, scoped branch coverage and two targeted mutations | Broader coverage/mutation work remains possible; current tests do not establish institutional certification. |
| D3 | Browser receipts bind exact image/release and all frontend assets | Retain hosted immutable receipt links for a reviewed commit. |
| D4 | Duplicate invitation becomes explicit non-destructive error; role/session/revocation tests retained; recovery revokes copied sessions | Reviewed MFA, invitation-expiry and recovery workflow before remote expansion. Current local scope remains password/session controlled. |
| D5 | Shared evidence/date identity, progressive disclosure, task-oriented research review; keyboard/chart, night/day and mobile browser checks | Independent user studies, full assistive-technology and contrast audit. |
| D6 | Local API cold/warm samples, four-reader p95/payload budget, browser navigation timings, 100/500-asset solve measurements | WAN, sustained larger mixed workloads and independently set service budgets. |
| D7 | Canonical regression façade with correct failure exit, ATR/position-sizing coverage, explicit historical-tool classification and current AST catalogue | Named human ownership and broader package migration are future maintenance work; no arbitrary source deletion. |
| D8 | Failed missing-regime validation raises a typed error; regression passes | No outstanding known implementation action in this review. |
| D9 | Immutable exact-revision reviewer/mandate/source binding; stored-record integrity checks; authenticated tester workflow and viewer denial | Actual client/independent review is not fabricated and cannot authorize execution. |
| D10 | Explicit global admission/capability reasons; native venue/calendar fixes and separate adapters | Each additional asset/market requires real data, accounting, costs, rights and risk qualification. Derivatives/live routing are not newly enabled. |

## Installed local pilot

The exact candidate image above is installed on the existing local Linux VM at `http://127.0.0.1:8782/`. All **10** runtime checks and all **four** required feature checks passed. The original account is preserved, old input trees are retained, and both scheduled publishers succeeded against the installed image. Final image deployment receipt: `var/project-review/clean-ci-image-rollout/deployment.json`; preflight: `clean-ci-image-rollout/preflight.json`. The data/cohort migration receipt is retained in `local-rollout-2/deployment.json`. No public access or execution authority was enabled.

## Free remaining operator steps

1. Create Proton Drive Free directly, complete verification and enable MFA. Browser control was unavailable in this session; no account was created. Use a fresh password entered on the provider's page.
2. Upload only `var/project-review/recovery-final/pilot-recovery-20261117-final.enc`. Keep `.secrets/pilot-recovery/20261117-final.key` separate; never upload it beside the archive or commit it. Download the archive to a new location and complete the documented restore/hash check. This recovery point passed both local integrity checks and restoration in image `sha256:67899da3f4203454dd9eb3b0f861ed2c27fe52933fefa95f0d0853ea6a5c61dd`; off-host recovery remains unproven.
3. Keep the pilot on `http://127.0.0.1:8782/`. No paid domain or cloud VM is required. Do not expose it publicly while the security and remote identity gates are open.
4. Supply/review actual official exchange and issuer evidence where macro agencies do not cover prices or holdings. See [the official-source policy and free recovery procedure](OFFICIAL_DATA_AND_BACKUP_PLAN.md).
5. Continue real future-session and horizon monitoring. Failed research gates remain failed until qualifying evidence changes them.

All 32 findings are accounted for. The local engineering execution and institutional/public qualification are deliberately separate statuses; unachieved external or future-observation criteria above remain open.

## Hosted-CI follow-up

The first GitHub run exposed clean-checkout issues masked by the original Mac's ignored runtime files. They were corrected and verified in an isolated checkout: the historical three-year policy is now a byte-identical versioned research JSON, and two wrapper tests construct their own synthetic dashboard template. The paper image now includes its admitted backup module and global registry JSON; the recommendation Dockerfile copies every declared resource, including `.dockerignore` and research JSON. Both actual images pass manifest/import checks; recommendation synthetic plan/viewer/replay smoke passes. The clean paper execution proof matrix passes **54/54**.

All scanner actions pin Trivy **0.76.2**; source scanning retains JSON evidence at the original HIGH/CRITICAL threshold. The current source secret/configuration scan reports **zero HIGH/CRITICAL findings**. The older scanner had returned failure with only LOW informational missing-healthcheck notes for batch images. No false health checks, security waivers or disabled vulnerability gates were added. SBOM is explicitly opt-in across pilot, paper, managed-paper and recommendation workflows. Hosted workflow outcomes remain separate from these local clean-checkout results.

The next hosted run exposed a genuine startup edge case: a zero monotonic timestamp could defer the first news refresh until machine uptime reached five minutes. An explicit uninitialized timestamp now forces the first refresh regardless of uptime; the regression fixes the clock at ten seconds. Hosted paper and recommendation builds completed, but their vulnerability scans failed. These failures remain release blockers and are not waived.

Hosted pilot run [44128747391](https://github.com/MichaelKazibwe/regime-switching/actions/runs/44128747391) passed backend regressions, frontend lint, immutable image imports, Chromium/WebKit acceptance and branch coverage; the image vulnerability gate failed. The x86 browser runner now installs `libatomic1` before invoking Playwright. A subsequent paper audit identified fixable `idna` and `pydantic-settings` advisories; their locks advance to 3.15 and 2.14.2 using official PyPI artifact hashes. Paper/recommendation/managed/research image bases now use the same digest-pinned Python 3.12 Trixie base as the pilot: the older Bookworm base could not install the locked NumPy wheel and attempted a compiler-less source build. Release/startup regression checks after these repairs passed **38/38**. Final hosted dependency/image checks remain required; no security findings are waived.
