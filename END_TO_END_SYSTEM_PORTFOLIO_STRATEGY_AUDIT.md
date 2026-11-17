# End-to-end system, portfolio and strategy audit

> **Universe policy update (2026-11-17):** Current portfolios and strategies resolve a configurable global instrument registry, with no fixed ETF-count limit. Numeric universe counts below describe this document's historical implementation or experiment. See [the current global-universe policy](GLOBAL_ASSET_UNIVERSE.md).

**Audit date: 30 October 2026, Europe/Warsaw.** Scope: the current private recommendation/dashboard product, four-strategy training and simulation path, data provenance, report/notification integration, operational observation and deployment boundary. The separate paper execution stack was covered by the full regression suite and reviewed at its integration boundary; no broker orders, deployment, external messages, production input mutation or additional data download occurred. This is a local engineering and quantitative audit, not independent legal, penetration-test or investment certification.

**Verdict: keep the system in private shadow evaluation. Public release and predictive-model promotion are not supported.** The normal calculation path works, but the audit reproduced acceptance defects and a current CPI calculation defect. Financial results do not demonstrate a profitable strategy or the requested return/loss objective.

**Repair checkpoint:** Repair 1 (A01) was completed first; repairs 2, 3 and 4 were then implemented and validated locally on 31 October 2026. See [MACRO_CALENDAR_REPAIR.md](MACRO_CALENDAR_REPAIR.md) and [REPAIRS_2_3_4_VALIDATION.md](REPAIRS_2_3_4_VALIDATION.md). A02–A04 and the local A17–A18 code failures have regression coverage; A16 now has a prospective accounting implementation but no elapsed investment track record. External host/alert/recovery qualification and economic findings remain open. The findings below preserve the original audit evidence.

**Economic checkpoint — 31 October 2026:** Repair 5 tooling and reassessment are complete; see [ECONOMIC_DESIGN_REASSESSMENT.md](ECONOMIC_DESIGN_REASSESSMENT.md). All four strategies fail the resulting economic screen. This implements the review, not a profitable/approved replacement or closure of A05/A07–A15. Current strategies and the prospective cohort are unchanged.

**P0/P1 execution checkpoint — 31 October 2026:** Isolated implementation and shadow execution are recorded in [ECONOMIC_P0_P1_EXECUTION.md](ECONOMIC_P0_P1_EXECUTION.md). Actual cash/cost/exposure evidence remains unavailable by owner instruction, and no economic/public approval was granted. The original cohort remains unchanged.

## Evidence and validation

- Full suite: **1,284 passed in 43.38 seconds**; Ruff passed. Existing passing tests do not cover the newly reproduced counterexamples.
- Verified completed run: `var/strategy-training-runs/20261030T201931327381Z/training-report.json`; capture has 4,233 market sessions and 28 instruments through 30 October 2026.
- Frozen later-period evaluation: **30 October 2025–30 October 2026**, 252 return sessions. Retrospective universe/strategy development prevents treating this as pristine prospective evidence.
- Isolated probes modified temporary dashboard copies and temporary observation files only. The live dashboard, models, allocation parameters, observation ledger and report PDFs were not altered.
- Numerical and corruption evidence: [end-to-end-evidence-2026-10-30.json](var/system-audit/end-to-end-evidence-2026-10-30.json).
- Four real custom strategy calculations and calculation-specific PDF exports were rerun; see [real-calculation-checks-2026-10-30.json](var/system-audit/real-calculation-checks-2026-10-30.json). These exercise the actual application backend, not a new browser session. HTTP authorization/input rejection are covered by the regression suite.
- The prior receipt of 1/20 operational observations was inspected without incrementing it. Docker/host/alert/recovery qualification remains explicitly false in saved deployment gates.

## P0 — release blockers

### A01. Current macro overlay miscalculates calendar-period CPI changes — confirmed defect

**Location:** [investor_macro_feed.py:62](investor_macro_feed.py#L62), versus exact-period training logic in `training_macro.py`.

The current/revised overlay drops missing values and uses positional `iloc[-13]` and `iloc[-16]`. A missing month makes a row offset differ from a calendar offset. In the actual current capture, September 2026 CPI is divided by **August 2025** rather than September 2025; the earlier momentum endpoint is May 2025 rather than June 2025.

| Current September 2026 feature | Displayed positional calculation | Calendar-period calculation |
|---|---:|---:|
| CPI year-over-year | 4.0233% | 3.7173% |
| Inflation momentum | 0.2968 pp | 0.2537 pp |

**Impact:** informational macro indicators and the quarterly scenario model fitted on this overlay can be wrong. Those quarterly mixtures also feed allocation-lab scenario weights and exports. This does not prove a wrong historical training feature: `TrainingMacro` separately enforces exact endpoints. The overlay and training paths must be audited separately.

**Required fix:** share an exact-calendar feature contract across current and vintage readers; reject missing required periods, duplicate periods and stale endpoints. Recompute affected current features, quarterly forecasts, scenario allocations and PDFs after correction. Add regression cases with an interior missing CPI month and a missing required endpoint. Do not patch or impute missing official observations.

### A02. Acceptance does not bind displayed training metrics to verified evidence — reproduced

**Location:** [strategy_operations.py:45](strategy_operations.py#L45), [strategy_report.py:15](strategy_report.py#L15).

A temporary dashboard's first training strategy return was changed to **+999%** while retaining its training run ID. `audit()` still returned `LOCAL_ACCEPTANCE_PASSED`. It checks the displayed run ID, not full equality of displayed training fields against the loaded verified report. The report loader itself validates artifacts, dates and candidates but does not independently recompute headline metrics from the hashed CSVs.

**Impact:** stale/corrupted displayed financial results can receive acceptance even when input files remain intact. This is an integrity weakness, not evidence that the present saved results are fraudulent or an unauthenticated remote exploit.

**Required fix:** rebuild presentation metrics/history from verified CSVs, reconcile every display field, and bind the dashboard payload to a canonical report digest. Include a report/signature or independently anchored release manifest appropriate to the threat model. Reject the temporary +999% counterexample.

### A03. Scenario acceptance permits negative cash and unsupported risk/simulation evidence — reproduced

**Location:** [strategy_operations.py:51](strategy_operations.py#L51).

A temporary Economic Balance scenario was changed from 5% cash to **−5% cash**, adding 10 percentage points to SPY so total capital remained 100%. Acceptance still passed. Another temporary scenario replaced its simulation with `{paths: 500, status: BLOCKED_SCENARIO_COVERAGE}`; acceptance also passed.

Acceptance checks the minimum ETF weight but not minimum cash; it checks only the largest provided risk contribution, not their sum or agreement with covariance. It checks `paths == 500`, not successful simulation status, finite metrics, horizon, fan consistency or provenance. It does not recompute the result ID. An all-cash portfolio with all percentage risk shares `None` also has no valid `max()` input under the present code path and needs explicit treatment.

**Required fix:** strict typed scenario schema, cash/weight finiteness and bounds, supported universe, risk-sum/covariance reconciliation, successful coverage status, simulation/fan validation and immutable calculation IDs. Handle legitimate zero-variance cash-only states explicitly. Add failing tests for each counterexample before accepting repaired output.

### A04. PDF acceptance is file-presence validation, not financial reconciliation — code-confirmed gap

**Location:** [strategy_operations.py:76](strategy_operations.py#L76).

The audit checks only that each strategy PDF starts with `%PDF-`. An old or unrelated valid PDF could satisfy that check. The four actual new backend exports succeeded, but the acceptance function cannot establish that saved PDFs match dashboard weights, forecast, horizon, metrics or result ID.

**Required fix:** generate PDFs from a canonical validated result, record source/result IDs and file hashes in a report manifest, and verify that manifest during acceptance. Add structured extraction checks and visual review for report changes. Include all scenarios exported for users, not only the four default files.

### A05. Investment objective and predictive edge remain unproven — measured

All four strategies lost money in the frozen evaluation. The trained classifier also underperformed its frequency baseline:

- Latest gate: model Brier **0.7310**, baseline **0.7264**, gate OFF.
- Frozen later-period score: model **0.9977**, baseline **0.7139**; 58 mature, overlapping outcomes.
- A 50% cumulative return over three years requires approximately **14.47% compounded annually**. Current results provide no evidence for achieving that target with a 5% drawdown preference.

**Required action:** retain predictive gate OFF and do not advertise the strategy as optimal or validated. Predeclare separate operational, predictive and investment acceptance tests. Test economic value net of costs against appropriate simple/risk-matched baselines with dependence-aware uncertainty; do not merely add complexity or tune to the same evaluation interval.

### A06. Deployment and worldwide product controls remain unqualified — verified status

There is no selected host, available local Docker executable, qualified Linux image, installed timer, verified external alert delivery, completed restore drill or public release approval. The original paper `Dockerfile` expects a root `release-manifest.json`, which is absent in this checkout; building that particular image requires the proper release staging process. Separate recommendation and strategy image recipes do not themselves prove that a container runs.

Local loopback token authentication and bounded computation are useful, but are not user identity, tenant authorization, HTTPS ingress, privacy administration or a qualified public service. The strategy service uses `ThreadingHTTPServer`; request/socket timeouts and public resource controls are not a production perimeter. Jurisdiction, instrument access and redistribution rights need release-specific decisions before worldwide use.

**Required action:** qualify the exact deployment image and environment on Linux; complete the explicit host/recovery/monitoring gates. Keep the current local service private. Do not reuse execution-stack qualification as evidence for a separate recommendation workspace.

## Portfolio and strategy performance

Returns are net of modeled 15 bps traded-notional costs, with zero uninvested cash yield, before investor taxes/platform fees. ETF return histories already include their observed adjusted-price behavior; zero cash yield does not mean SGOV/bond returns were set to zero. Reference portfolios do not have the same risk constraints, so the table is descriptive, not a risk-matched proof of superiority.

| Portfolio | Total return | Max drawdown | Annual volatility | Average cash | Annual traded notional | Modeled cost / starting capital |
|---|---:|---:|---:|---:|---:|---:|
| Economic Balance | −2.00% | −2.78% | 3.00% | 60.06% | 4.26× | 0.64% |
| Defensive Growth | −1.97% | −2.66% | 3.73% | 59.55% | 4.37× | 0.65% |
| Inflation Resilience | −0.81% | −2.11% | 2.48% | 55.90% | 3.59× | 0.54% |
| Tail-Aware Ensemble | −1.80% | −2.42% | 2.88% | 56.81% | 5.18× | 0.77% |
| All Weather-style proxy | +4.51% | −4.78% | 7.35% | ~0% | 1.26× | 0.19% |
| Balanced reference | +6.69% | −5.98% | 8.44% | ~0% | 1.15× | 0.17% |
| SPY reference | +12.19% | −8.88% | 12.77% | ~0% | 1.00× | 0.15% |

The All Weather-style reference is a liquid fixed-weight proxy, not actual Bridgewater returns. Benchmarks use the same reported evaluation dates. Cash at the simulation's assumed zero yield also exceeded all four strategy returns in this interval; an actually available cash product requires its own verified yield/fee/access assumptions.

## P1 — material portfolio, modeling and operational weaknesses

### A07. Data outages dominate the evaluation and apparent defensiveness

**130/252 sessions = 51.59%** were quarantined, and each strategy was effectively fully in cash for 130 return sessions. Mean cash was 55.90–60.06%. First failing reasons: missing required UNRATE periods 76, stale UNRATE 27, missing CPI periods 17, stale INDPRO 8, stale CPI 2. These are first-error counts, not exhaustive simultaneous-error attribution.

The fail-closed behavior is appropriate. The weakness is availability and its economic effect: low volatility/drawdowns partly reflect absent exposure, not successful macro timing. Validate official releases, archive completeness and provider failure versus genuine publication absence. Preserve historical vintages. Add availability and quarantine attribution per series and separate data-driven exits from economic exits. Any degraded-data strategy must be separately designed and validated; do not weaken the existing gate opportunistically.

### A08. Four strategies are close variants, not four independent return engines

Pairwise daily return correlations range **0.9586–0.9885**. On the 122 sessions when all four were invested, they remain **0.9588–0.9885**: shared cash periods do not explain away their similarity.

The strategies share macro inputs, classifier, sleeve menu, covariance estimator, risk caps and drawdown guard. Tail-Aware Ensemble averages related risk maps and adds feedback; it is not an independent manager or automatically a tail hedge. Combining these strategies should not be presented as substantial strategy diversification. Evaluate factor overlap, independent signals and marginal portfolio contribution before adding another label.

### A09. Menu breadth is not effective diversification

The four current candidates hold only **9–10 ETFs** from the 26-core menu. The five core sleeves use SPY/VEA/VWO, TLT/IEF/IGOV, TIP, GLD and DBC; SGOV or SHY is a reserve. DBMF is excluded from these fixed strategy maps; ALLW is benchmark-only. Zero weights are intentional, not missing rows, but this is not an optimizer over every menu asset.

Per-ETF Euler variance caps do not cap common interest-rate, real-rate, equity-beta, foreign-currency, commodity or liquidity exposures. For Economic Balance, TLT+IEF+IGOV+TIP+SGOV currently account for approximately **61.48% of capital** across distinct but related rate-sensitive/reserve instruments. This is not 61.48% identical risk. Add factor/duration/FX exposure estimates, stress contribution limits and redundancy checks alongside variance budgeting. Adding more overlapping equity ETFs is not automatically diversification.

### A10. Drawdown controls can suppress recovery and cannot guarantee 5% loss limits

**Location:** [goalportfolio.py:15](goalportfolio.py#L15), `fourstrategysimulation.py`.

Exposure begins reducing at 2% account drawdown and locks permanently into cash at 4% until a separate review resets policy. This can cap participation after an early loss; recovery is not modeled as an automatic feature. It is an intentional persistent safeguard, not a defect to remove casually. Next-close decisions cannot prevent overnight gaps. As an illustrative arithmetic stress, a 10% joint fall on 95% risky exposure loses about 9.5% before fees, regardless of a later cash lock; this is a hypothetical shock, not an estimated event probability.

Specify reviewed re-entry/recovery policy and test it across different inception dates and shocks. Show conditional drawdown distributions rather than labeling the risk preference as a guaranteed cap. Current saved four-quarter simulations already have 95th-percentile maximum account drawdown of about **5.22%** for Defensive Growth and **5.02%** for Tail-Aware Ensemble.

### A11. Turnover and cost feedback materially damage outcomes

Annual traded notional is 3.59–5.18 times starting-account scale. Modeled costs consume approximately 0.54–0.77% of starting capital. Doubling the cost rate yields returns approximately **−2.98%, −3.10%, −1.73%, −2.67%** in strategy order. These are distinct path-dependent runs: fees affect high-water marks and later allocations, so the difference is not just a fee subtraction.

Fixed 15 bps costs and close-price proxies do not model order-size liquidity, spread changes, market impact, stressed fills, taxes or actual user broker terms. Introduce benefit-versus-cost trade decisions, risk-first hysteresis and explicit intervention attribution, while retaining urgent risk reductions. Validate changes prospectively and with observed market-access inputs.

### A12. Cash economics and comparison baselines are incomplete

The research path assumes zero uninvested cash yield despite high average cash. The recommendation product has a separate `CashRate` and cost/tax interface. Results across these engines therefore are not directly interchangeable. Do not invent a positive risk-free return to make results attractive.

Use dated verified net cash-rate histories where applicable, preserving instrument/currency/access differences and both zero-yield and realistic-cash sensitivities. Add simple cash/Treasury and volatility/exposure-matched references. The current comparisons cannot isolate whether macro switching adds economic value beyond defensive sizing.

### A13. Quarterly macro scenarios and the classifier are different models

**Location:** [investor_analytics.py:72](investor_analytics.py#L72), [live_strategy_training.py:137](live_strategy_training.py#L137).

Quarterly variable scenarios use a small monthly AR(1) model on current/revised history with resampled residuals. The classifier uses release-aware historical features to predict a 63-session condition quadrant. The classifier's OFF gate does not validate or invalidate the quarterly AR model; manual/quarterly scenarios remain possible as labeled hypotheticals. There is no independent out-of-sample coverage/calibration demonstration for the quarterly variable bands and their regime frequencies.

Require separate model identities, input lineage, forecast availability, horizon alignment, calibration/coverage and revision sensitivity. [ALFRED distinguishes data known at a historical date from current revisions](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html); enforce that contract in every historical validation. AR(1) persistence clipping and residual sampling are modeling choices, not proof of economic forecasting skill.

### A14. Monte Carlo output is a conditional resampling exercise, not a full adaptive forecast

**Location:** [macro_allocation_lab.py:169](macro_allocation_lab.py#L169).

The lab samples 21-session joint asset blocks from up to 1,260 recent sessions. It independently draws block regimes from a fixed supplied mixture; it has no estimated regime transition/duration process. Targets remain the latest constrained allocation with reduce-only drawdown sizing, not future refitted strategies. Recent block counts are 395/480/65/169 across the four regimes, with overlap, so they are not independent crisis samples.

With 500 paths, a 5% terminal tail has only about 25 paths; loss frequencies and expected shortfall have sampling error and model risk. The model cannot create unobserved structural breaks merely by increasing the number of paths. All four saved current-model scenarios have negative median returns; conditional terminal-loss frequencies are approximately **70.4%, 72.0%, 56.0%, 66.4%**. These are not calibrated real-world loss probabilities.

Add seed/path-count sensitivity, dependence-aware confidence intervals, independent stress regimes, explicit shocks, horizon alignment and transition-aware scenarios. Validate a genuinely adaptive future policy separately if that is the product claim. Do not relabel the present simulations as five-year predictions or loss guarantees.

### A15. Predictive promotion gate is statistically weak even when it eventually turns ON

The gate accepts a mean Brier improvement with at least 12 mature forecast records; overlapping outcomes reduce effective independence. It does not require an uncertainty interval, economic improvement net of costs, calibration by regime, stability across cycles or correction for previous strategy/model experimentation. Fitted latest coefficients are not the same model as the frozen evaluated coefficients.

Keep the current OFF result. Before any future ON gate can support promotion, specify a minimum meaningful advantage and dependence-aware test, distinct validation and untouched prospective window, calibration and a reviewed parameter-change process. Avoid repeated selection on the same frozen interval.

### A16. The observation ledger measures receipts, not a forward investment track record

**Location:** [strategy_operations.py:104](strategy_operations.py#L104).

A daily record contains acceptance evidence and rolling retrospective metrics. It does not mark forward holdings to market, carry the daily proposed portfolio into a prospective NAV ledger, or establish 20 consecutive qualified exchange sessions. The counter counts unique sessions, not uninterrupted coverage. The documents correctly warn about this, but the 20-session counter must not be treated as return validation.

Add separate dated decision/fill/position/cash-flow/NAV records for shadow portfolios, track actual subsequent outcomes of frozen forecasts and record missed sessions/configuration changes. Preserve the distinction between daily operational qualification and an actual prospective portfolio performance record. Only one session has elapsed in the current ledger.

### A17. Partial observation files can silently prevent a fresh run — reproduced

**Location:** [scheduled_strategy_validation.py:27](scheduled_strategy_validation.py#L27).

Creating a corrupt current-session receipt in an isolated temporary directory made `run(..., refresh=True)` return `ALREADY_OBSERVED` without reading or validating it. Because observation JSON is written directly after exclusive creation, a process crash during writing can leave a partial marker. The scheduler exits successfully on existence alone, even though a separate health check can report a problem.

Validate a complete successful receipt, its hash and session before skipping; use atomic durable write/commit semantics and explicit quarantine/recovery for partial records. Do not silently count or overwrite a conflicting observation.

### A18. Watchdog/job receipts are not a durable liveness protocol — reproduced and code-confirmed

**Locations:** [strategy_healthcheck.py:11](strategy_healthcheck.py#L11), `scheduled_strategy_validation.py`.

A valid current observation plus `latest-job.json` containing the valid JSON value `[]` raises `TypeError`, rather than returning the declared alert result. Type/schema checks are missing. `latest-job.json` is updated at job completion, not at start; a killed or stuck job can leave an older success as the latest receipt. The health check verifies statuses/session but not report hash linkage, receipt age, process heartbeat or daily expected-run deadline.

Require structured schemas, run-start/finish receipts, liveness/age checks and a tested external missing-heartbeat alert. Keep nonzero exits, but distinguish a controlled alert from a monitor crash. A local JSON failure receipt alone does not deliver an alert.

## P2 — integration and maintainability weaknesses

### A19. Different financial engines and dated products need an explicit authority boundary

There are separate research strategies, a cost/CVaR recommendation planner, an older investor-plan illustration, the fresh macro strategy lab and a paper execution/reporting ledger. Preserving older client plans is correct, but fresh macro data do not make those plans current. The default viewer contains old plans dated 29 October 2025 alongside 30 October 2026 strategy evidence, with labels explaining the distinction.

`monthlyreport.py` reads paper decision reports/SQLite state; monthly delivery is not automatically a monthly report for the fresh strategy lab. Before users subscribe, choose the authoritative product portfolio/model, version its holdings and performance contract, reconcile dashboard/PDF/monthly reports to it, and verify email delivery. Do not accidentally email paper execution returns as recommendation-model results.

### A20. Release lineage and operating portability need completion

The public recommendation `PRODUCT_SOURCES` list does not bind the entire newer training/calculation/scheduler path. This is acceptable while that path remains private and unapproved, but insufficient if its output is promoted to advice. Separate Docker recipes target Python 3.12 whereas local tests ran Python 3.14; the workstation launch bundle embeds absolute local paths. Data archives/provider revisions and many prior experiments require a reproducible release bundle and inventory.

Define one source/data/environment/model manifest for each intended release, include new numerical components and configs, qualify the actual pinned environment, preserve review receipts, and test restoration/relocation. Keep research snapshots distinct from approved products and private subscriber/SMTP data out of images. Use CI gates to prevent misleading documentation or stale source lists from being treated as deployment evidence.

## Repair order and exit criteria

1. **Correct the current macro feature contract (A01)** and regenerate the affected overlay, quarterly scenarios, lab and PDFs with exact calendar periods; assert the actual September CPI endpoints in regression tests.
2. **Repair acceptance integrity (A02–A04)** using verified numerical reconstruction and report manifests. All reproduced corrupted copies must fail while the valid current workspace passes. Include legitimate cash-only/blocked outputs as explicit states, not uncaught exceptions or false successes.
3. **Repair scheduler and watchdog crash recovery (A17–A18)** with atomic validated receipts, missing-run deadlines and tested alert transport. Test interrupted/partial records and concurrent jobs.
4. **Establish a genuine prospective portfolio/forecast ledger (A16)** and a release-bound observation protocol. Preserve the existing receipt counter as an operational metric, not a performance claim.
5. **Reassess the economic design (A05, A07–A15):** verified cash baseline, risk-matched references, data availability attribution, transaction-cost attribution, factor/stress limits and a transparent goal-feasibility frontier. Keep the 5% preference and explicitly evaluate its participation/recovery cost; changing it requires a deliberate mandate decision.
6. **Unify the user-facing product contract (A19–A20)** before email subscriptions or deployment. Match every portfolio/forecast date, model version and metric between dashboard, PDF and monthly delivery.
7. **Qualify the Linux host/image and recovery/alerts (A06)**, complete actual prospective observations, then seek independent investment validation and explicit release approval. No test count or attractive chart substitutes for these gates.

No fixes or investment-parameter changes were applied as part of this audit. The deliverables are this prioritized findings document and the isolated machine-readable evidence. This audit supersedes interpreting the earlier local acceptance pass as complete end-to-end correctness.
