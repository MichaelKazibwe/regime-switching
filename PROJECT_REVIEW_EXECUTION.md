# Project review execution register — 17 November 2026

The 32-item source review is [PROJECT_REVIEW_20261117.md](PROJECT_REVIEW_20261117.md). All findings now have an implementation or an explicit evidence/scope disposition below. **This does not mean all original institutional/public-release acceptance criteria are closed.** The current authorized scope is a free, local, invitation-only research pilot. Execution and automatic promotion remain disabled.

No paid server, domain, data subscription or storage account was created. Remote commercial access and externally qualified recovery are not represented as completed.

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
2. Upload only `var/project-review/recovery-after-review/pilot-recovery-20261117-post-review.enc`. Keep `.secrets/pilot-recovery/20261117-post-review.key` separate; never upload it beside the archive or commit it. Download the archive to a new location and complete the documented restore/hash check.
3. Keep the pilot on `http://127.0.0.1:8782/`. No paid domain or cloud VM is required. Do not expose it publicly while the security and remote identity gates are open.
4. Supply/review actual official exchange and issuer evidence where macro agencies do not cover prices or holdings. See [the official-source policy and free recovery procedure](OFFICIAL_DATA_AND_BACKUP_PLAN.md).
5. Continue real future-session and horizon monitoring. Failed research gates remain failed until qualifying evidence changes them.

All 32 findings are accounted for. The local engineering execution and institutional/public qualification are deliberately separate statuses; unachieved external or future-observation criteria above remain open.

## Hosted-CI follow-up

The first GitHub run exposed clean-checkout issues masked by the original Mac's ignored runtime files. They were corrected and verified in an isolated checkout: the historical three-year policy is now a byte-identical versioned research JSON, and two wrapper tests construct their own synthetic dashboard template. The paper image now includes its admitted backup module and global registry JSON; the recommendation Dockerfile copies every declared resource, including `.dockerignore` and research JSON. Both actual images pass manifest/import checks; recommendation synthetic plan/viewer/replay smoke passes. The clean paper execution proof matrix passes **54/54**.

All scanner actions pin Trivy **0.76.2**; source scanning retains JSON evidence at the original HIGH/CRITICAL threshold. The current source secret/configuration scan reports **zero HIGH/CRITICAL findings**. The older scanner had returned failure with only LOW informational missing-healthcheck notes for batch images. No false health checks, security waivers or disabled vulnerability gates were added. SBOM is explicitly opt-in across pilot, paper, managed-paper and recommendation workflows. Hosted workflow outcomes remain separate from these local clean-checkout results.
