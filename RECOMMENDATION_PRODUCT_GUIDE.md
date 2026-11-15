> **5 November execution update:** [Pending-task execution and current blockers](RECOMMENDATION_PRODUCT_EXECUTION.md) reconciles every D01–D23 rollout item with the later implementation. This pass added atomic recommendation/risk-state persistence, CLI account locking, a minimal source build context and recommendation-image CI; generated four separate 1,000-path previews/PDFs; and verified exact replay. Current acceptance is retained in `var/product-guide-execution/acceptance/latest.json`. Older counts and dates below are historical.

> **Current operation:** [Dashboard live updates](DASHBOARD_LIVE_UPDATES.md) documents the active hourly collector, weekly bounded research, authenticated minute-level viewer updates and current data through 4 November. Earlier statements below that no background timer is enabled are superseded. Archived client examples remain historical. The direct viewer runs locally; its new login service is disabled after macOS denied Documents-folder access. No public, managed-account or investment release is approved.

> Earlier acceptance execution: [local engineering passed, release prerequisites blocked](RELEASE_ACCEPTANCE_EXECUTION.md). The previous full regression was 1,375 passed. Existing ledgers and published portfolio artifacts were unchanged in that pass.

> Unified acceptance checkpoint: run `python3 release_acceptance.py`. See [the acceptance guide](RELEASE_ACCEPTANCE_GUIDE.md) and `var/release-acceptance/latest.json` for the source-bound report, fresh checks and unresolved release prerequisites. Acceptance does not add observations or approve release.

> Return-engine refinement: see [Institutional-method challengers](INSTITUTIONAL_RETURN_ENGINES.md) for public-source research, positive historical results, benchmark limitations and the separate forward cohort. Incumbents are unchanged.

> Integrated deployment checkpoint: see [Six-workstream execution](SIX_RECOMMENDATIONS_EXECUTION.md) for the contract-bound dashboard/report/ledger, current comparison and unresolved external gates. Active observation root: `var/strategy-operations-integrated-v1`.

> Current policy update, 31 October 2026: fixed return targets and the 5% account drawdown constraint are superseded. See [Growth & Resilience](GROWTH_RESILIENCE_BENCHMARK.md). Earlier results below retain their historical assumptions.

# Recommendations, simulations and charts product

The implemented product prepares **non-executable portfolio recommendations and conditional scenarios**. The owner selected recommendations with simulations/charts, rather than account management. It has no order-submission route or custody function. The launch jurisdiction remains unspecified, so public recommendations remain disabled until scoped approval evidence exists.

## Implementation of the six recommendations

| Recommendation | Implemented product capability | Qualification still required |
|---|---|---|
| Give all 28 instruments a role | `investmentcatalog.py`, `AssetUniverse.product_menu()`; economic buckets, satellites, alternative permissions, composite benchmark exclusion and separate legacy eligibility | Verified domicile, regional availability, disclosures, approved local instruments and licensed data |
| Build different economic components | Preservation, balanced and growth mandates; global equities, government bonds, credit, inflation/real assets, permitted DBMF alternative; explicit strategic references and overlap limits | Independent factor, currency, duration and alternative-product suitability review |
| Replace restrictive assumptions | Supplied net base-currency cash yield, client-specific loss preferences, persistent high-water marks, gradual reductions and measured re-entry; unsupported 50%/three-year/5% goal remains flagged | Approve the new recommendation risk contract; validate re-entry and forecast error on fresh observations |
| Robust financial allocation | Convex mean/CVaR planning with shrunk gross return priors, uncertainty discount, strategic bands, sector/credit caps, transaction costs, sale-tax proxies and hypothetical stress constraints | Priors, cost coefficients, scenario severity, fund expenses and economic exposures need independent validation |
| Global suitability and implementation | Currency conversion, tax account and annual drag inputs, liquidity reserve, alternative permissions; release- and jurisdiction-bound evidence, client-mandate-specific suitability approval | Choose a lawful initial jurisdiction, regulated service scope and local product mappings; no automatic worldwide authorization |
| Deliver an actual product | CLI, authenticated loopback operator API, private JSON/CSV reports, interactive browser charts, exact input snapshots/replay, risk-state persistence, separate container recipe and release checks | Identity/tenant infrastructure, encryption/retention, legal approval, data-provider contracts, independently observed model quality and hosted operation |

These are functioning local capabilities, not a declaration that the public/global release requirements are complete. A local product service still needs model development and independent validation. Institutionally appropriate allocation incorporates time horizon, liquidity, taxes and regulation. [CFA Institute](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/asset-allocation-with-real-world-constraints). Automated personalized recommendations can fall within suitability requirements; applicability must be assessed for the actual jurisdiction and service. [ESMA guidance](https://www.esma.europa.eu/sites/default/files/2023-04/ESMA35-43-3172_Guidelines_on_certain_aspects_of_the_MiFID_II_suitability_requirements.pdf).

## Investment design decisions

- The **28-instrument menu** is the existing 26 names plus DBMF and ALLW. ALLW remains a composite benchmark, excluded from the component optimizer to avoid opaque overlap. DBMF requires explicit alternative permission and adequate actual price history. Instruments need at least 253 complete prices. No pre-inception returns are manufactured.
- The catalogue is not 28 independent sources of return. Equity satellites share equity risk; HYG is credit risk, foreign bonds add currency exposure, and gold/silver/commodities have different sensitivities. Bucket and satellite limits supplement per-asset capital caps; they are not a substitute for independently measured factor exposures.
- **Macro alpha defaults off** because the four-strategy study failed its forecast baseline. The service does not promise that recession predictions can reliably time asset markets.
- Profiles are **illustrative policy defaults**, not validated recommendations for all clients. Preservation starts with a 70% cash floor; balanced/growth start with 5%, increased for liquidity or risk reductions. Equity and other bucket ranges apply to available investment capital. The optimizer may use more cash. Growth requires sufficient horizon and capacity to bear loss; incompatible mandates are blocked, not made to fit by relaxing limits.
- The original objective, **50% cumulative return in three years with at most 5% decline**, remains unsupported by existing evidence. The `original_goal` example retains that objective and low loss capacity. The other demo profiles are different hypothetical clients, not changes to the owner's mandate.
- Long-term return priors are **unvalidated gross planning assumptions**. A 10% observed-return component is bounded by winsorization; there is no historical-mean maximization or search for an apparent optimum. Supplied annual fund expenses reduce only the 90% gross-prior component because observed fund returns already embed expenses. Investor tax drag and the platform fee are separate inputs. Missing expense inputs block public release.
- Base-currency cash yield must be supplied with a source, aware timestamp and freshness. The demo explicitly assumes zero and marks it unverified. Cash yield is net of the supplied bank/tax/custody assumptions, before a separately specified platform fee. The system does not invent a current interest rate or treat a Treasury ETF as risk-free cash.
- Explicit historical FX must convert all USD-listed prices for a non-USD base currency. This is **currency translation, not currency hedging** or a verified UCITS substitution. A change in an existing account's base currency requires review.

## Optimization, costs and loss controls

`productallocation.py` uses a linear mean/CVaR objective with a 21-session decision benefit, uncertainty discount, strategic-reference tracking, turnover and optional conservative sale-tax costs. It enforces nonnegative fully reconciled capital, 25% asset capital caps, cash needs, bucket/satellite/credit limits and supplied loss preferences across named hypothetical shocks. Both the proposal and strategic comparison are feasible under these planning constraints.

The output contract is **`PRODUCT_CAPITAL_BANDS_V1_NOT_LEGACY_RISK_BUDGET_AUTHORIZATION`**. This intentionally replaces fixed variance-budget targets for the recommendation product. It does **not** claim to enforce the legacy 25% per-asset variance contribution limit or exact legacy budget shares. Euler contributions are reported and numerical constraint reconciliation is checked at 1e-6. The original 14-asset paper/trading authorization path, its exact risk budget validation and live-trading restrictions remain unchanged. Product plans cannot be routed through that path as authorized orders.

Fees are reconciled against dollars actually exchanged after fees; base cash transfers are not charged as ETF trades. Cash liquidity and hypothetical stress losses are checked **after initial costs**, with conservative re-solving when necessary. A small-change hold is possible only if current holdings remain inside the mandate constraints. Infeasible inputs produce a blocked result and no weights, rather than an automatic liquidation recommendation.

`productexecutioncost.py` accepts observed bid/ask, average daily traded value, volatility, commission and FX costs. It rejects stale/future quotes and excessive participation. Its square-root impact coefficient still requires empirical validation. Annual tax drag and a conservative sale-tax proxy are supported; there is no treaty engine, wash-sale benefit assumption or certified jurisdiction-specific tax-lot optimizer. Taxable public recommendations are blocked when relevant tax inputs are missing.

Risk state preserves the high-water mark, prior breach history and distinct-session confirmations across restarts. Gradual reductions maintain a small minimum planning exposure rather than permanently cash-locking every account. Five confirmed sessions allow a bounded re-entry increase. A breach or operational incident requires review. A named evidence-backed review may clear the review flag only once the account is back within its loss preference; it does not erase the peak or breach history. None of these rules guarantees a maximum loss.

## Scenarios and charts

The proposed portfolio and its feasible strategic reference share sampled asset-date blocks. Scenarios preserve within-block dependence, include uncertainty in drift, use explicit growth priors and an empirical exponential-moment adjustment, and rebalance every 21 sessions **after old holdings earn that session's return**. Initial known costs are included. Cash yield is assumed constant, not forecast. Future withdrawals, contributions, realized tax-lot changes and dynamic macro allocation are not simulated.

Reports show the horizon, conditional return/drawdown summaries, capital weights, blocked suitability/release reasons and an interactive fan chart. Changing the initial amount scales the same scenarios; it does not create a new forecast. The intervals and frequencies are **model scenarios, not calibrated future probabilities or loss bounds**. The short common history of the investable instruments cannot cover every historical crisis.

## Run the local product

Using the already cached historical bundle:

```sh
python3 investment_product.py --demo --paths 1000
```

Open `var/product-preview/balanced/index.html`, `preservation/index.html`, `growth/index.html` or `original_goal/index.html`. All examples are historical operator previews with no public approval. Demo profile horizons differ and are displayed explicitly.

For supplied current inputs:

```sh
python3 investment_product.py --mandate config/product/mandate.example.json \
  --prices /path/to/verified-prices.csv --cash-rate /path/to/verified-cash-rate.json \
  --as-of CURRENT_AWARE_UTC_TIMESTAMP --costs /path/to/observed-costs.json \
  --fund-expenses /path/to/expense-fractions.json --output var/private-client-plan
```

Replace the example mandate and timestamp; do not use fictitious suitability information. `--historical-preview` is required for past decisions. Current requests require the latest completed NYSE session, a current decision clock and complete market sessions. For another base currency, supply `--fx-to-base` with aligned base-currency units per USD. Optional `--current-weights`, `--sale-tax-rates`, `--annual-tax-drag` and `--risk-state` inputs are documented by `--help`. Expense and tax-drag dictionaries cover every eligible model instrument plus zero for base cash. Current weights must include every model component and cash and sum exactly to one; unmodelled holdings cause review instead of being silently discarded.

The CLI persists account-keyed risk state and blocks a base-currency mismatch. Risk review requires `--risk-reviewer` and `--risk-review-evidence` on a recovered saved account. Evidence is retained privately. JSON/CSV/HTML artifacts are written atomically with 0600 permissions. These local permissions are not encryption or a complete privacy/retention program.

## Operator API

`recommendation_api.py` binds **only 127.0.0.1** and requires `PRODUCT_API_TOKEN` (32–256 ASCII characters) configured privately. It does not print the token. Requests require the correct loopback Host, same-origin browser context and Bearer authentication. JSON payloads are bounded, arbitrary file paths/approval directories are not accepted, and raw errors are not returned. A single-owner state-directory lock and per-application request lock protect account high-water updates.

Routes: authenticated `GET /health`, `GET /v1/catalogue`, and `POST /v1/plan`. The POST body contains `mandate` and optional `current_weights`, `annual_tax_drag`, `sale_tax_rates`, `equity_fraction`, `trend_confirmed`, and `paths` (100–2000). The server supplies the price/rate/FX/expense snapshot. It never loads public approval receipts and is always an operator preview. There are no order routes.

```sh
python3 recommendation_api.py --prices /path/to/prices.csv \
  --cash-rate /path/to/cash-rate.json --state-root var/product-api --port 8767
```

This is a **single-operator local integration API**, not a public multi-tenant service. Public delivery still requires identity/tenant isolation, TLS, appropriate encrypted storage and retention, rate limiting at the edge, independently reviewed infrastructure and jurisdiction approval. Do not expose this listener through a public proxy as a shortcut. Update verified snapshots when prices/rates expire; this implementation does not invent a continuous licensed data feed.

## Exact input snapshots and replay

Each CLI/API plan retains content-addressed, hash-verified input snapshots using the existing exact IEEE-754 snapshot store. Source files, dependency versions, prices, cash-rate assumptions, costs, taxes, currency data, prior risk state and simulation controls are bound to the run. Private financial data must be retained under an approved retention/access policy.

```sh
python3 investment_product.py --replay var/product-preview/balanced/recommendation.json \
  --snapshot-root var/product-preview/balanced/snapshots
```

Replay requires the same source/dependency release and verifies allocation, scenario and risk-state outputs. It cannot restore public approval or turn a past decision into current advice. Changed artifacts or source versions fail closed.

## Public-release evidence

`productrelease.py` binds approvals to the exact product source/dependency release, jurisdiction and recommendation/simulation service scope. Required checks are legal scope, client suitability, instrument access, licensed/data quality, independent model validation, security/privacy, operations/recovery and owner sign-off. Client suitability additionally binds to the exact mandate hash; instrument approval must cover each proposed instrument. Receipts need a named reviewer, recent aware timestamp and hash-verified evidence. Missing, stale, failed, altered or mismatched evidence blocks release. The ledger records human attestations; it does not establish reviewer identity, professional credentials or legal adequacy by itself.

No PASS receipts are created by the demos or tests. Missing country, verified rates, verified fund expenses, non-illustrative cost inputs, relevant taxes or risk review also prevents public release. The full-system tests establish engineering evidence, not suitability or investment performance.

## Packaging and remaining rollout gates

`Dockerfile.recommendations` packages the CLI with the existing hashed dependencies, runs as a non-root user and starts no web listener or order worker by default. It is separate from the existing paper-worker image. Build/scan the exact image in an appropriate runner before use; local code tests are not an image-build or vulnerability-scan receipt. Mounted private data/output directories need suitable UID/permissions.

The next product release requires a **specified initial jurisdiction**, verified provider/instrument data, independent financial validation, privacy/security review, production infrastructure and supervised operation. The prior 50%/three-year/5% objective has not become supported by these software changes. No account trades, emails, public publication, registrations or legal approvals were performed.

## Local verification

Final full regression: **1,235 passed**. The 29 new product tests cover mandate conflicts, catalogue/legacy separation, FX and cash-rate inputs, capital/stress/liquidity reconciliation after costs, no-trade handling, state persistence/re-entry/review, quote capacity, paired scenarios, release evidence tampering, API authentication/origin/body limits, exact snapshot replay and checkpoint-before-publication. Repository-wide Ruff and `git diff --check` pass. The generated historical preservation snapshot replays with an exact numerical match. Four 1,000-path examples match the current source/dependency release and remain public-release blocked. Safari rendering and amount-based chart scaling were checked. Evidence is stored privately in `var/product-preview/verification.json`.

Docker is unavailable in this local environment; the separate image recipe has **not** been built or vulnerability-scanned. The operator API uses POSIX file locking and is intended for a supported macOS/Linux operator host. Public identity/tenant isolation, infrastructure security, provider licensing, jurisdiction decisions and independent investment validation remain release requirements rather than inferred passes from these tests.


## Accepted investor dashboard baseline — 30 October 2026

The owner accepted the local investor dashboard. Design changes are paused; correctness, accessibility and service integration remain in scope. `dashboard/investor-baseline.json` records source hashes for **INVESTOR_DASHBOARD_V1**. This is a presentation freeze, not investment or public-release approval.

Open `var/investor-dashboard/index.html` for the integrated four-example viewer. It includes profile selection, illustrative amount scaling, scenario windows and keyboard/pointer inspection, benchmark comparison, allocation groups, capital and signed variance shares, searchable instrument detail, historical price charts, risk/readiness information and local JSON/CSV downloads. The examples retain their original 2025-10-29 price date and release IDs; they are not live recommendations.

Build a viewer from existing saved plans without reoptimizing or changing their evidence:

```sh
python3 investor_dashboard.py --reports var/product-preview --output var/investor-dashboard/index.html
```

Optionally pass `--prices /private/path/adjusted-prices.csv` to include actual dated price context. The renderer takes no observations later than each plan's session, does not forward-fill prices and requires an exact session observation for a displayed closing price. Without that input it explicitly displays unavailable price context. `investment_product.py --demo` now creates an integrated root `index.html` as well as individual reports and includes its existing cached historical prices.

For temporary local HTTP use, add `--serve --port 8768`. Only `/` and `/index.html` are served on loopback, with no directory listing, client JSON or raw snapshot endpoint. Stop the foreground process when finished. This server is a private single-plan viewer, not a public authenticated customer service. Browser file opening requires no server.

Changing the displayed amount scales the saved paths; it does not recalculate fees, suitability, allocation, taxes or account constraints. A shorter chart window crops the existing distribution; KPI cards remain full-horizon estimates. Pointwise fan bounds are not drawdown limits. The strategic reference is not official All Weather performance. Cash and invested Treasury ETFs remain distinct.

Visible exports omit client identity and raw approval evidence, but still contain private financial planning data; keep them private. The viewer never grants approvals or submits orders. New renderer sources are part of product release hashes. Older exact numerical replay requires its original source/dependency release; opening an archive does not migrate or reapprove it.

Verification for the accepted baseline: 1,245 tests and Ruff pass locally; 54/54 paper execution proofs pass. New dashboard boundaries have 10 regression cases. Further mobile/cross-browser and authenticated service checks are deployment tasks. See `ROADMAP_TO_DEPLOYMENT.md` for the current delivery queue and `CONTINUOUS_STRATEGY_VALIDATION_PLAN.md` for background evaluation, which is not enabled yet.


## Investor dashboard V2 and current macro overlay

The subsequent owner request supersedes the V1 design freeze. The new full-universe map, latest/decision-time macro switch, four-quarter conditional outlook, strategy review guidance, risk/performance charts and PDF exports are documented in [INVESTOR_DASHBOARD_V2.md](INVESTOR_DASHBOARD_V2.md). V1 hashes remain in `dashboard/investor-baseline-v1.json`; V2 is implemented for review, not automatically accepted or publicly qualified. Latest FRED capture is dated 30 October 2026, separately from the saved 29 October 2025 portfolio. No weights or mandates were changed. Continuous background evaluation remains a separate deployment task.


## Fresh strategy training and macro allocation lab

See [LIVE_STRATEGY_AND_MACRO_ALLOCATION_GUIDE.md](LIVE_STRATEGY_AND_MACRO_ALLOCATION_GUIDE.md) for the completed current-data run, all four strategies, macro-driven capital/risk allocations, shared economic asset roles, conditional simulations, PDF exports and the authenticated local recalculation service. Latest captured market session: 30 October 2026. The predictive alpha gate remains off; no client-plan replacement, background timer, order or public release is enabled.

## Acceptance, observation and scheduled candidate validation

See [STRATEGY_DEPLOYMENT_ACCEPTANCE.md](STRATEGY_DEPLOYMENT_ACCEPTANCE.md) for the six-workstream checklist, exact quarantine findings, immutable 20-session observation ledger, isolated daily refresh, Docker/systemd setup and remaining host gates. Run `python3 strategy_operations.py --observe` for current-snapshot acceptance, or `python3 scheduled_strategy_validation.py --refresh` for a new private candidate. Scheduled output does not replace the investor dashboard or promote predictive models.

## Exact-calendar macro repair — 30 October 2026

Current and vintage macro readers now share `macro_feature_contract.py`. Missing periods no longer shift CPI endpoints; quarterly current/revised scenarios fit only consecutive observed transitions. The dashboard, 20 lab scenarios and PDFs were regenerated with source-matched training. See [MACRO_CALENDAR_REPAIR.md](MACRO_CALENDAR_REPAIR.md) for provenance, unchanged risk parameters and open audit findings.

## Repairs 2–4 checkpoint — 31 October 2026

See [REPAIRS_2_3_4_VALIDATION.md](REPAIRS_2_3_4_VALIDATION.md) for strict CSV/scenario/PDF reconciliation, durable v2 job/observation receipts, watchdog and explicit quarantine recovery, and prospective NAV/forecast accounting. Use `var/strategy-operations-v2` for new observations; the prior v1 root remains archived and untrusted for migration. Current v2 state is 1 operational observation and **0 forward return sessions**, not a completed observation period. No timers, external alerts or public deployment were enabled.

## Repair 5 — economic design, 31 October 2026

Implemented and executed `economic_design_assessment.py` and `economic_design_report.py`: independent path/profit reconciliation, observed SGOV versus unverified user cash, cost/availability attribution, prior-close risk-budget references, paired block-bootstrap intervals, 28-asset diagnostics, aggregate stress review and a declared three-year reference frontier. See [ECONOMIC_DESIGN_REASSESSMENT.md](ECONOMIC_DESIGN_REASSESSMENT.md). The 30 configurations × 29 overlapping cohorts produced no joint 50%-return/5%-drawdown success. This is not proof of impossibility. All four economic screens remain blocked; no current weights, predictive gate, investor dashboard or prospective cohort changed. The next numbered repair is 6, the unified product contract; independent economic validation and actual cash/exposure inputs remain prerequisites.

## P0/P1 execution checkpoint — 31 October 2026

See [ECONOMIC_P0_P1_EXECUTION.md](ECONOMIC_P0_P1_EXECUTION.md) for source/reviewer evidence gates, official release-incident reconciliation, the separately solved stress-budget challenger, predeclared cost/fallback comparisons, reviewed recovery validation and independent prospective cohorts. The owner confirmed no verified files are available, so cash/cost/access/exposure gates remain blocked. Active challenger configuration is `research/stress_budget_challenger_v2.json`; original strategies and their cohort are unchanged. V2 shadow results and daily-handoff templates do not imply financial approval or a qualified host.


## Pipeline recovery and model review — 12 November 2026

See [FORECAST_RETURN_RISK_REVIEW_20261112.md](FORECAST_RETURN_RISK_REVIEW_20261112.md) for the 11 November capture, informational CPI gap disclosure, strict cash-only quarantine acceptance, explicit cash reconciliation, preserved prior ledgers and separately identified new shadow cohorts. Current observations use each root's `active-cohort.json`; the old `prospective.sqlite3` files remain archived evidence. New cohorts start with zero forward-return sessions. The historical calibration study still fails its predictive activation gate; no model or weight variant was promoted. The finite next-study specification is `research/forecast_return_risk_review_20261112.json`.
