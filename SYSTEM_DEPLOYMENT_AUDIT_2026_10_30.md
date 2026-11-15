# System deployment audit — 30 October 2026

**Conclusion: suitable for continued private engineering and shadow evaluation; not qualified for unattended operation or public investor recommendations.** The owner accepted the investor dashboard design. Presentation is now frozen at `dashboard/investor-baseline.json`; backend reliability and validation take priority over further redesign.

This audit supersedes earlier readiness counts, not their historical evidence. It reviews the root module inventory, entry points, research assessments, configuration examples, data paths, API, reports, containers, scheduled units and CI. It includes local regression and lint execution. It is not an external security assessment, legal approval, production-image certification or fresh strategy-performance study.

## Evidence obtained in this review

| Check | Observed result | Interpretation |
|---|---|---|
| `ruff check .` | PASS | Local Python lint, not security certification. |
| `pytest -q` | **1,245 passed in 51.18 seconds** | Python **3.14.3** locally; deployed Python 3.12 and locked image still need separate proof. |
| `python3 e2e_proof_runner.py` | **54 PASS, 0 FAIL, 0 BLOCKED** | Paper/in-memory execution contracts; no live routing. Prior generated evidence preserved in `var/deployment-audit/prior-e2e/`. |
| Recommendation/product tests | 29 passed | Product math, safety and replay coverage remain intact. Included in full regression. |
| New dashboard tests | 10 passed | Private field omission, source identity preservation, data-script injection protection, CSP hash, permissions, horizon validation, no forward/future price filling and report-root containment. Included in full regression. |
| Browser inspection | Safari: dashboard rendered; profile selection, amount scaling, chart window/keyboard inspection, portfolio navigation and ticker search exercised | Not a full cross-browser/mobile accessibility certification. A stale chart readout found during testing was corrected. |
| Dashboard source baseline | `dashboard/investor-baseline.json` | Records presentation source hashes; does not approve portfolio performance or public distribution. |
| Source inventory | 252 root Python files, including 91 `test_*.py` modules; one CI workflow | Raw counts include historical/backup utilities, not 252 production services. |
| Repository status | 116 tracked files; approximately 283 modified/untracked entries at inspection | A clean, complete reviewed source release is still needed. Do not delete backups or overwrite owner changes to obtain a clean status. |
| Docker | No `docker` executable found on this workstation | No image build, image scan, container smoke or host deployment was verified here. |
| Current-data connectivity | Yahoo SPY probe returned 10 daily rows; latest label `2026-10-30` at approximately 18:41 UTC | NYSE session was still open. Calendar identified **2026-10-29** as the latest completed session. The current bar must be excluded. This is connectivity evidence for one symbol only, not a current-data strategy backtest. |

Probe details are private at `var/deployment-audit/current-data-probe.json`. The first attempt failed inside the network sandbox; the explicitly approved retry reached the provider. No strategy was retuned, no investor mandate was relaxed and no live order was submitted.

## What exists and how the system connects

| Layer | Main files | Deployment assessment |
|---|---|---|
| Asset definitions | `assetuniverse.py`, `investmentcatalog.py`, `core_constants.py` | Three scopes: 14 production/paper assets, 26 diversified research assets, 28 product-menu instruments. Catalogue inclusion is not authorization. ALLW is benchmark-only; DBMF access is conditional. Preserve these distinctions. |
| Market ingestion | `marketdataloader.py`, `validators.py`, `tradingcalendar.py`, `paperdata.py` | Adjusted ETF history, no fabricated price-gap filling, session/freshness checks. Product API loads supplied price files; it is not an automatically refreshing 28-asset feed. |
| Macro ingestion | `paperdata.py`, `fetch_strategy_macro.py`, `macrovintage.py` | FRED adapter for operation; separate ALFRED/release-aware research archive. Paper adapter uses lagged revised series, which cannot establish an unbiased historical backtest. |
| Regime and forecasts | `macroregime.py`, `regimeforecastengine.py`, `smartregimeportfolio.py`, `fourregimestrategies.py`, `forecastmodels.py`, `expectedreturnforecaster.py` | Multiple policies/research versions exist. Forecast-enabled four-strategy evidence does not establish alpha; the actually used forecasts scored worse than the frequency baseline. There is no validated route promoting these into the recommendation product. |
| Allocation and risk | `portfoliooptimizer.py`, `riskbudgetengine.py`, `riskcontributionanalyzer.py`, `covarianceengine.py`, `volatilitytargeting.py`, `riskgovernor.py`, stress/tail modules | Legacy paper authorization enforces its own strict risk contract. Product allocation has a different capital/CVaR contract; passing one must never authorize the other. |
| Research candidates | `diversifiedregimepolicy.py`, `hybridportfoliopolicy.py`, `institutionalportfolio.py`, `goalportfolio.py`, `fourregimestrategies.py`; evaluation/optimization scripts | Useful reproducible studies, but many have fixed historical cutoffs and `var/research/...` input dependencies. They are not a ready recurring fresh-data evaluation service. |
| Recommendation product | `clientmandate.py`, `productallocation.py`, `productexecutioncost.py`, `recommendationrisk.py`, `recommendationservice.py`, `productsimulation.py` | Non-executable planning with suitability/release blocks. Macro alpha disabled by default. Fixed-allocation conditional scenarios are not a simulation of the complete future dynamic regime strategy. |
| Product entry points | `investment_product.py`, `recommendation_api.py` | Private CLI and authenticated single-operator loopback API. No public tenant identity, customer session or authorization layer. API price inputs are loaded at process creation. |
| Investor presentation | `investor_dashboard.py`, `productreport.py`, `dashboard/investor.*` | Accepted local dashboard with four saved examples, 28-asset exploration, capital/variance information, scenario comparisons and readiness. Saved session is **2025-10-29**. Viewer never refreshes advice, trades or reapproves plans. |
| Operator presentation | `paper_dashboard.py`, `paper_dashboard_server.py`, `dashboard/index.html`, `dashboard/dashboard.*` | Separate paper-worker view and cached provider quote path. Do not expose it as a public customer API or merge its prices into old plan dates. |
| Simulated execution | `paper_runtime.py`, `paperexecution.py`, production authorization/handoff modules, `oms.py`, `brokerrouter.py`, `paperbroker.py`, accounting/reconciliation | Substantial fail-closed paper lifecycle exists. It does not authorize product recommendations for real trading. `livebroker.py` is not a reason to enable client account management. |
| Persistence and replay | `paperstore.py`, `researchdatastore.py`, `researchreplay.py`, `productaudit.py`, `restartrecovery.py`, `paper_backup.py` | Strong local snapshot/recovery foundations. Product multi-file state/report updates still need transaction/crash semantics for a service deployment. |
| Reports and notification | `monthlyreport.py`, `monthlydelivery.py`, `emailtransport.py`, `paperalerts.py`, structured logging | Shared paper-portfolio completed-month reports and PDF email tooling exist. Not a verified user-specific recommendation delivery service. Sender/recipient consent, host receipt, bounces and operations remain to qualify. |
| Release and operations | `paper_release.py`, `paper_qualification.py`, `productrelease.py`, Dockerfiles, Compose, `deploy/systemd`, `.github/workflows/paper-ci.yml` | Paper release tools and scheduler templates exist; no host was supplied. Product container recipe exists but CI currently builds/scans the paper image, not the recommendation image. |
| Options utilities | Greeks, Black–Scholes, options-tail/stress modules | Supporting code is not evidence of an approved ETF-product options strategy. Keep outside initial recommendation scope. |

## Findings ordered by risk and dependency

| ID | Priority | Finding / evidence | Required action | Release affected |
|---|---|---|---|---|
| A01 | P0 | No host, no exact hosted image evidence, dirty/incomplete versioned source | Select private Linux Docker host; reconcile source manifest; build/scan exact pinned candidate and retain provenance. | All unattended deployment |
| A02 | P0 | No continuous 28-asset current-data research job; research scripts use frozen paths/cutoffs | Add session-aware immutable ingest, unified evaluation entry point, scheduler, job ledger and monitoring. Do not schedule the existing fixed-date scripts unchanged. | Automatic background testing |
| A03 | P0 | Current daily provider bar can be incomplete | Filter against exchange close and publication buffer, reject stale required instruments; record observed vs usable timestamps. Add an intraday-bar regression case to the recurring feed boundary. | Fresh-data research/product |
| A04 | P0 | Four macro strategies are research-only; original target failed its historical joint-goal screen (0/60 accounts) | Freeze champion/challengers and retain the target failure. Validate prospects against simple references before promotion. Do not select the highest observed return and call it optimal. | Investment claims/promotion |
| A05 | P0 | Product API writes result JSON before risk state; a lock serializes requests but does not atomically commit multiple files | Reproduce crash windows and add transactional state + artifact publication/commit pointer. Confirm state survives write, archive and response failures without forgetting a high-water mark. | Unattended recommendation API |
| A06 | P0 | Launch jurisdiction/service audience remains undefined; current receipts correctly block release | Define one first jurisdiction and recommendation scope, commission appropriate review, verify per-instrument access and claims. No worldwide automatic approval. | Public/private client recommendations |
| A07 | P0 before public | API is one operator; static viewer contains the visible plan | Add real identity, tenant ownership checks, private artifact delivery, expiry/revocation, HTTPS, rate/resource limits and adversarial isolation tests. A bearer token shared by all users is insufficient. | Multi-user pilot/public |
| A08 | P0 before public | Research provider access does not establish display/redistribution rights | License intended use; qualify provider adjustment policies, revisions, fund metadata, rates, fees and FX. Separate EOD analytical prices from executable quotes. | Public data/recommendations |
| A09 | P1 | Product scenarios use unvalidated planning priors and sampled blocks; not calibrated outcome probabilities | Coverage/forecast evaluation, sensitivity and changing-regime/pathwise tests; keep conditional labels and disclose assumptions. | Investor projections |
| A10 | P1 | Separate risk contracts/universes and potential repeated-study selection | Add versioned strategy registry, experiment ledger, explicit profile constraints and human promotion gate. Never silently alter 5% loss capacity. | Strategy tuning |
| A11 | P1 | No observed daily research automation heartbeat, alert or recovery proof | Singleton scheduler, bounded retries, no partial-success marker, independent missed-job alarm, kill switch, quarantine and replay drill. | Unattended research |
| A12 | P1 | Product build absent from current CI image job | Add Python 3.12 locked tests, recommendation-image build/scan/SBOM, CLI/viewer smoke and release hash checks. Test asset files are included in image. | Product release |
| A13 | P1 | Shared paper monthly reports differ from client product reports | Define report/account attribution and immutable period snapshots; add consent, delivery lifecycle and client isolation before widening recipients. | User email product |
| A14 | P1 | Existing HTML error/empty states tested locally; not full browser certification | Preserve accepted design; add mobile/keyboard/contrast, infeasible plan, large amount, chart bounds and download checks to browser CI. | Investor dashboard release |
| A15 | P1 | Exact retention, recovery ownership and off-host restore not evidenced | Encrypt backups/secrets; define retention and erasure; prove restore, correct owner access and off-host recovery within target. | All hosted services |
| A16 | P2 | Source root includes backups, large bundles and historical documentation with old counts | Reconcile reviewed files into release manifests and mark old docs historical. Archive only through an approved reversible cleanup; no broad rewrite/deletion. | Maintenance/reproducibility |

Priority is gate-specific: identity is not required for one local operator, but is mandatory before a multi-user investor launch. No Kubernetes, real broker, leverage, option execution or additional strategy family is required for the first milestone.

## Financial acceptance implications

The 50% cumulative three-year target is about **14.47% annual compounded growth**, before considering how fees/taxes affect the requested net target. The simultaneous 5% drawdown preference is not supported by existing results. More optimization trials cannot establish a guarantee. Maintain the original goal as an explicitly unsupported aspiration until evidence and suitability support a lawful product description.

Measure economically distinct exposures, not just ticker count: equity beta/geography, duration/real rates, credit, inflation/commodities, alternative-model risk, USD translation, liquidity and cash reinvestment. Evaluate proposed and reference portfolios over the same feasible history and cost conventions. Actual ALLW has limited observed history; do not manufacture a 50-year ETF track record or substitute proxy results for official fund performance.

Point-in-time macro availability must follow archived releases. FRED documents real-time periods and vintage retrieval: [real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html), [vintage dates](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html). Fixed release lags alone do not undo later revisions.

Jurisdiction review must assess whether the service and performance presentation trigger local requirements. For US scope, the SEC distinguishes interactive-analysis tools and other hypothetical performance, and describes applicable conditions and disclosures; this audit does not determine classification: [SEC investment adviser marketing guide](https://www.sec.gov/resources-small-businesses/small-business-compliance-guides/investment-adviser-marketing).

The executable delivery sequence and acceptance checklist are in `ROADMAP_TO_DEPLOYMENT.md`; the background-research design is in `CONTINUOUS_STRATEGY_VALIDATION_PLAN.md`.
