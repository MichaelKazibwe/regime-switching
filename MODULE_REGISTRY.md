# MODULE REGISTRY — REGIME SWITCHING PORTFOLIO FRAMEWORK

> **Universe policy update (2026-11-17):** Current portfolios and strategies resolve a configurable global instrument registry, with no fixed ETF-count limit. Numeric universe counts below describe this document's historical implementation or experiment. See [the current global-universe policy](GLOBAL_ASSET_UNIVERSE.md).

> **15 November 2026 source cleanup:** Start with [README.md](README.md) and the current local-pilot guides. Superseded source copies and duplicate tests were removed from the source tree; recoverable local copies remain in ignored cleanup storage. Runtime data, trained artifacts and generated output are excluded from the commit. The historical phase counts below are preserved as history.

> **1 November 2026 deployment checkpoint:** Live trading remains disabled. The current upgrade checklist is [LIVE_TRADING_UPGRADE_ROADMAP.md](LIVE_TRADING_UPGRADE_ROADMAP.md), covering 26 ordered engineering and qualification tasks. Historical LOCKED labels below certify their recorded phase only; they do not approve a broker connection, unattended host, client service or live orders. Read `var/release-acceptance/latest.json` for the latest source-bound audit result.

> **Historical registry and phase notes.** The 70-file source-bundle counts and earlier failures below are historical. Current paper additions include `paper_release.py`, `paper_qualification.py`, `paper_backup.py`, `macrovintage.py`, and `lock_paper_dependencies.py`, alongside the existing worker/data/execution/store/dashboard/alert/replay modules. Current implementation, validation and remaining host/research gates are recorded in [PAPER_DEPLOYMENT_GAP_AUDIT.md](PAPER_DEPLOYMENT_GAP_AUDIT.md) and [PAPER_DEPLOYMENT_GUIDE.md](PAPER_DEPLOYMENT_GUIDE.md).

**Registry state:** System inventory baseline established 2026-08-26
**Source basis:** supplied complete project source bundle (70 file entries) and current project architecture/progress document.
**Deployment status:** NOT READY FOR LIVE DEPLOYMENT — systematic inspection and hardening remain.

## 1. Inventory facts

- **70 bundled file entries**: 65 root entries + 5 archive entries.
- **64 production modules** are represented by the root modules excluding `final_regression.py`; `final_regression.py` is the comprehensive regression gate.
- The architecture document previously described a 64-file production inventory; the distinction above reconciles that count with the 65 root entries currently bundled.
- The 14-asset production universe is: SPY, QQQ, IWM, VEA, VWO, TLT, IEF, SHY, LQD, HYG, GLD, SLV, DBC, VNQ.
- The separate 26-ETF research profile is available through `AssetUniverse.diversified()` and `DIVERSIFIED_ASSETS`. It appends TIP, IGOV, SGOV, XLF, XLP, XLE, XLU, XLI, KIE, ITB, EWJ and XLY. `diversifiedregimepolicy.py` consumes this profile; its research allocations and qualification gaps are documented in [DIVERSIFIED_REGIME_PORTFOLIO.md](DIVERSIFIED_REGIME_PORTFOLIO.md). Paper runtime eligibility remains the production profile.
- `hybridportfoliopolicy.py` combines validated 14-ETF and 26-ETF parent proposals in research. `optimize_hybrid_portfolio.py` selects among a predeclared grid chronologically and tests daily risk controls with next-session execution. Results and limitations are in [HYBRID_PORTFOLIO_MODEL.md](HYBRID_PORTFOLIO_MODEL.md); no production activation or inherited account-level budget approval is implied.
- `smartregimeportfolio.py` implements actual-vintage macro/market features, restartable daily regime state and explicit per-asset risk budgets. `fetch_strategy_macro.py` freezes archived economic releases; `optimize_smart_portfolio.py` runs historical eligibility, chronological optimization, cycle reporting, macro ablation and paired loss simulation. The candidate is **not accepted for replacement**; see [SMART_REGIME_PORTFOLIO_ASSESSMENT.md](SMART_REGIME_PORTFOLIO_ASSESSMENT.md).

## 2. Module registry

Recommendation product modules: `investmentcatalog.py` (28-item menu), `clientmandate.py` (goals/capacity/cash source), `productallocation.py` (mean/CVaR, strategic bands, costs and stress), `recommendationrisk.py` (persistent drawdown/review/re-entry), `productexecutioncost.py` (quotes/capacity/tax proxies), `productsimulation.py` (paired conditional asset scenarios), `productrelease.py` (release/jurisdiction/mandate-bound evidence), `recommendationservice.py` (non-executable workflow), `productaudit.py` (exact private inputs/replay), `productreport.py` (interactive local chart report), `investment_product.py` (CLI) and `recommendation_api.py` (authenticated loopback operator API). `AssetUniverse.product_menu()` exposes catalogue metadata without extending the legacy execution universe. Tests: `test_investment_product.py`, `test_product_api_replay.py`. Packaging: `Dockerfile.recommendations`. Scope, assumptions and public-release gaps: [RECOMMENDATION_PRODUCT_GUIDE.md](RECOMMENDATION_PRODUCT_GUIDE.md).

Four fixed macro strategy additions: `fourregimestrategies.py` implements Economic Balance, Defensive Growth, Inflation Resilience and Tail-Aware Ensemble; a purged monthly 63-session macro-quadrant forecast; bounded forecast influence; and feasible capped risk-budget proposals using the unchanged strict institutional solve. `fourstrategysimulation.py` handles next-close account simulations with lifetime drawdown controls. `evaluate_four_macro_strategies.py` performs benchmark, cohort, cycle, cost and bootstrap comparisons; `report_four_macro_strategies.py` generates the assessment and complete-block starting-regime scenarios. Frozen design: `research/four_macro_strategies.json`; tests: `test_four_macro_strategies.py`. These are research-only and have no broker authorization role. See [FOUR_MACRO_STRATEGIES_ASSESSMENT.md](FOUR_MACRO_STRATEGIES_ASSESSMENT.md).

Three-year mandate research additions: `goalportfolio.py` implements a persistent account drawdown guard, prior-only filtered historical risk diagnostics and bounded growth-overlay proposals through the unchanged strict institutional allocator. `evaluate_three_year_goal.py` executes the 12-variant study and verified metric reanalysis; `report_three_year_goal.py` generates diagnostics, uncertainty, charts and assessment; `benchmark_managed_futures.py` evaluates a fixed actual DBMF benchmark only. Tests: `test_goal_portfolio.py`, `test_goal_benchmarks.py`. Mandate and current failed screen: [THREE_YEAR_GOAL_ROADMAP.md](THREE_YEAR_GOAL_ROADMAP.md). None is wired to broker execution or production authorization.

Research refinement additions: `institutionalportfolio.py` implements a conditional core risk solve including invested reserve cross-risk, shrunk/stressed correlation estimates and forecast diagnostics. `refine_institutional_portfolio.py` performs the frozen eight-variant chronological experiment; `benchmark_all_weather.py` provides a descriptive actual ALLW overlap. Configuration is `research/institutional_refinement_plan.json`; tests are `test_institutional_portfolio.py`. These modules have no broker integration and do not replace production risk authorization. Results and qualification gaps: [INSTITUTIONAL_PORTFOLIO_REFINEMENT.md](INSTITUTIONAL_PORTFOLIO_REFINEMENT.md).

### Core

| Module | Current role | Status |
|---|---|---|
| `basecomponent.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `basecovariancemodel.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `core_constants.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `exceptions.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `validators.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `testsupport.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |

### Data / Universe

| Module | Current role | Status |
|---|---|---|
| `marketdataloader.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `assetuniverse.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |

### Forecast / Regime

| Module | Current role | Status |
|---|---|---|
| `forecastmodels.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `macroregime.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `regimeforecastengine.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `expectedreturnforecaster.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `regimesimulation.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `regimeallocationpolicy.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |

### Covariance / Risk

| Module | Current role | Status |
|---|---|---|
| `covarianceengine.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `regimecovariance.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `factorcovariance.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `ensemblecovariance.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `factorexposuremodel.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `riskmodel.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `riskcontributionanalyzer.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `riskbudgetengine.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `volatilitytargeting.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `forwardriskmetrics.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `forwardriskanalyzer.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `drawdownforecast.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `scenarioengine.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `constraints.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |

### Portfolio

| Module | Current role | Status |
|---|---|---|
| `blacklitterman.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `portfoliooptimizer.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `portfolio.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `portfoliodecisionengine.py` | Portfolio decision orchestration; currently has a failing regression fixture. | Implemented / inspect |
| `productioncomposition.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |

### Execution / OMS

| Module | Current role | Status |
|---|---|---|
| `order.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `orderstatus.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `orderbook.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `trade.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `tradegenerator.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `transactioncostmodel.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `executionengine.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `rebalanceengine.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `pretraderiskgate.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `oms.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `brokerrouter.py` | Authorized order routing boundary. | Implemented / inspect |
| `paperbroker.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `livebroker.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `brokerexecutionengine.py` | Broker execution receipt normalization and execution bridge. | Implemented / inspect |
| `portfolioaccount.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `reconciliationengine.py` | OMS/broker/account reconciliation. | Implemented / inspect |
| `posttradeexecutionmonitor.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `executionanalytics.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `tradeanalytics.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |

### Production orchestration

| Module | Current role | Status |
|---|---|---|
| `productionintegration.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `productiondecisionexecution.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `productionriskvalidation.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `productionexecutiongate.py` | Sole execution-authorization boundary. | Implemented / inspect |
| `productionpipelineintegration.py` | Production pipeline orchestration and authorization integration. | Implemented / inspect |

### Analytics / Regression

| Module | Current role | Status |
|---|---|---|
| `analytics.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `performanceattribution.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `regression_suite.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `final_regression.py` | Comprehensive system regression gate. | Implemented / inspect |
| `step7_production_test.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `step8_historical_data_test.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |
| `step9_historical_backtest.py` | Implemented in supplied source; detailed interface inspection pending. | Implemented / inspect |

### Legacy / Monolithic

| Module | Current role | Status |
|---|---|---|
| `rewrite.py` | Legacy/monolithic implementation; containment and retirement candidate. | Implemented / inspect |

## 3. Archive inventory

| Module | Status |
|---|---|
| `archive/section3.py` | Archived / non-production until reviewed |
| `archive/section2.py` | Archived / non-production until reviewed |
| `archive/rewrite_clean.py` | Archived / non-production until reviewed |
| `archive/section1.py` | Archived / non-production until reviewed |
| `archive/section4.py` | Archived / non-production until reviewed |

## 4. Current validation result

| Gate | Result | Interpretation |
|---|---|---|
| File inventory | PASS | 70 bundled entries detected |
| Python compile | PASS | All 70 extracted files compile |
| AST audit | PASS | Structural parsing succeeded |
| Ruff | BLOCKED | `ruff` executable unavailable in audit environment |
| Imports | FAIL / PARTIAL | `yfinance` and `fredapi` unavailable; historical modules cannot import |
| Production decision smoke test | PASS | End-to-end production decision completed successfully in final regression run |
| Individual module regression | FAIL | `portfoliodecisionengine.py` primary regression currently fails |
| Git/GitHub state | UNKNOWN | No Git repository was supplied in the source bundle; must inspect actual repository before push |
| Live deployment readiness | NOT READY | Dependency, regression, infrastructure, operational and live-safety gates remain |

## 5. Immediate blockers before deployment certification

1. Fix the `PortfolioDecisionEngine` regression fixture/API contract mismatch: the current test supplies `growth` and `inflation`, while the decision path requires `unemployment`.
2. Install and lock required runtime/development dependencies, including the missing `yfinance`, `fredapi`, and `ruff` tooling, then rerun the complete regression gate.
3. Inspect the real Git repository, branch, working tree, ignored files, secrets, history and CI configuration before any GitHub upload.
4. Reconcile the source bundle with the actual filesystem repository; the bundle is an audit artifact, not proof of repository parity.
5. Complete the full system inspection module-by-module before changing production behavior.

## 6. Deployment roadmap

### Gate A — Inventory & baseline
- Complete module inventory and responsibility map.
- Establish canonical source tree.
- Establish Git baseline.

### Gate B — Functional certification
- Compile all modules.
- Ruff/static analysis.
- Import audit.
- Unit/module regression.
- Quantitative regression.
- Production decision regression.
- Historical data/backtest regression.

### Gate C — Architecture certification
- Dependency graph.
- Circular import audit.
- Interface/API audit.
- State/lifecycle audit.
- Serialization audit.
- Configuration audit.

### Gate D — Execution hardening
- Identity integrity.
- Lifecycle integrity.
- Authorization integrity.
- Routing integrity.
- Broker integrity.
- Receipt integrity.
- Reconciliation integrity.
- Accounting integrity.

### Gate E — Paper trading
- Deterministic paper execution.
- Multi-day simulation.
- Reconciliation.
- Failure/recovery testing.
- Monitoring and alerts.

### Gate F — External broker integration
- Credentials/secrets management.
- Broker transport implementation.
- Connectivity/health.
- Order status synchronization.
- Cancellation/recovery.
- Broker reconciliation.

### Gate G — Live-safety certification
- Kill switch.
- Circuit breakers.
- Position/risk limits.
- Stale-data protection.
- Clock/calendar controls.
- Duplicate/replay protection.
- Restart recovery.
- Operational runbooks.

### Gate H — Deployment
- CI/CD green.
- Production environment reproducible.
- Database/persistence verified.
- Monitoring/dashboard verified.
- Shadow/paper phase completed.
- Controlled canary deployment.
- Final human approval.

## 7. Future architecture backlog

The architecture document identifies future infrastructure not yet present in the 70-file bundle, including data gateways/realtime feeds, persistence/repositories, recovery, monitoring, governance, orchestration, API, dashboard, deployment and expanded test layers. These are **planned**, not to be counted as implemented modules until actual source files exist.

## 8. Next controlled action

**Do not harden blindly yet.** The next step is the full system inspection using this registry as the baseline. Each module will be classified as `PASS`, `PASS WITH RISK`, `FAIL`, `INCOMPLETE`, `LEGACY`, or `PLANNED`, with dependencies, callers, APIs, tests, persistence, production usage and deployment relevance recorded.


## 9. Current architecture

RebalanceEngine
      │
      │ planning only
      ▼
canonical Order
      │
      ▼
ExecutionAuthorization
      │
      ▼
AuthorizedOrderIntent
      │
      ▼
AuthorizedExecutionHandoff
      │
      ├──────────────► OMS authorized execution
      │
      ▼
AuthorizedRoutingHandoff
      │
      ▼
BrokerRouter.route_authorized_order()
      │
      ▼
Broker
      │
      ▼
broker execution receipt
      │
      ▼
BrokerExecutionEngine.execute_authorized_receipt()
      │
      ▼
ExecutionEngine
      │
      ▼
PortfolioAccount
      │
      ▼
OMS lifecycle + audit provenance


                         MARKET DATA
                             │
                ┌────────────┴────────────┐
                │                         │
             PRICES                    RETURNS
                │                         │
                │                         ├── Covariance
                │                         ├── Risk
                │                         └── Regime models
                │
                └── ExpectedReturnForecaster
                              │
                              ▼
                       expected_returns
                              │
                              ▼
                    Black-Litterman
                              │
                              ▼
                    PortfolioOptimizer
                              │
                              ▼
                        target weights
                              │
                              ▼
                     Risk / constraints
                              │
                              ▼
                      Production Gate


# Certification standard

1. Import integrity
2. Public API
3. Constructor behavior
4. Input validation
5. Output contract
6. State behavior
7. Serialization
8. Metadata
9. Health checking
10. Error semantics
11. Dependency direction
12. Determinism
13. Test coverage
14. Production consumers
15. Legacy/duplicate behavior


PHASE 0 — Inventory Baseline
        ✅ COMPLETE

PHASE 1 — Repository Reconciliation
        ✅ COMPLETE
        Commit: e15801f

PHASE 2 — Functional Certification
        ▶ NEXT

PHASE 3 — Architecture Certification
        ⏳

PHASE 4 — Execution Hardening
        ⏳

PHASE 5 — Operational Hardening
        ⏳

PHASE 6 — Paper Trading Certification
        ⏳

PHASE 7 — External Broker Integration
        ⏳

PHASE 8 — Live-Safety Certification
        ⏳

PHASE 9 — GitHub / Release Certification
        ⏳

PHASE 10 — Deployment
        ⏳


# B
marketdataloader.py
assetuniverse.py
# C
forecastmodels.py
expectedreturnforecaster.py
macroregime.py
regimeforecastengine.py
regimeallocationpolicy.py
regimesimulation.py
# D
covarianceengine.py
regimecovariance.py
ensemblecovariance.py
factorcovariance.py
factorexposuremodel.py
riskmodel.py
forwardriskanalyzer.py
forwardriskmetrics.py
drawdownforecast.py
volatilitytargeting.py
riskbudgetengine.py
riskcontributionanalyzer.py
# E
blacklitterman.py
constraints.py
portfoliooptimizer.py
portfolio.py
portfolioaccount.py
portfoliodecisionengine.py
scenarioengine.py
# F
productioncomposition.py
productionintegration.py
productionpipelineintegration.py
productionriskvalidation.py
productionexecutiongate.py
productiondecisionexecution.py
# G
tradegenerator.py
trade.py
order.py
orderbook.py
orderstatus.py
rebalanceengine.py
pretraderiskgate.py
executionengine.py
executionanalytics.py
oms.py
reconciliationengine.py
posttradeexecutionmonitor.py
transactioncostmodel.py
# H
authorizedexecutionhandoff.py
authorizedorderintent.py
authorizedorder.py
authorizedroutinghandoff.py
# I
brokerrouter.py
brokerexecutionengine.py
paperbroker.py
livebroker.py
# J
analytics.py
performanceattribution.py
tradeanalytics.py
final_regression.py
quantitative_regression.py
regression_suite.py
step7_production_test.py
step8_historical_data_test.py
step9_historical_backtest.py

# improved architecture

                    MARKET DATA
                         │
                         ▼
                ┌─────────────────┐
                │ Feature Engine   │
                └────────┬────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
      Macro Regime   Return Forecast  Risk Model
          │              │              │
          │              ▼              ▼
          │        Forecast Ensemble  Covariance
          │              │              │
          │              ▼              ▼
          │       Forecast Shrinkage  Cov Ensemble
          │              │              │
          └──────────────┼──────────────┘
                         ▼
                  BLACK-LITTERMAN
                         │
                         ▼
                  RISK BUDGET ENGINE
                         │
                         ▼
                 PORTFOLIO OPTIMIZER
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
           Regime      Vol Target  Turnover
          Constraints             Penalty
              │          │          │
              └──────────┼──────────┘
                         ▼
                  FINAL WEIGHTS
                         │
                         ▼
                 RISK VALIDATION
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
           Exposure     VaR       Scenarios
           Checks      / CVaR      / Stress
              │          │          │
              └──────────┼──────────┘
                         ▼
                  APPROVAL GATE
                         │
                         ▼
                    OMS / EXECUTION

# priority fixes

| ID | Issue                                | Type            | Priority |
| -- | ------------------------------------ | --------------- | -------- |
| E1 | Repository inventory mismatch        | Engineering     | P1       |
| E2 | Stale 65-module documentation        | Engineering     | P2       |
| E3 | 13 Ruff failures                     | Engineering     | P1       |
| E4 | Duplicate tests                      | Engineering     | P1       |
| E5 | Broker duplicate check ordering      | Execution       | **P0**   |
| E6 | OMS validation boundary              | Architecture    | P1       |
| E7 | FAILED + success=True                | State integrity | **P0**   |
| A1 | Regime/production ticker mismatch    | Architecture    | **P0**   |
| A2 | EFA/EEM vs VEA/VWO                   | Architecture    | **P0**   |
| A3 | Missing assets silently renormalized | Portfolio       | **P0**   |
| A4 | Incomplete regime policies           | Portfolio       | P1       |
| F1 | Signals treated as expected returns  | Quant           | **P0**   |
| F2 | Incompatible signal scales           | Quant           | **P0**   |
| F3 | Undefined forecast horizon           | Quant           | **P0**   |
| F4 | Fixed signal weights                 | Quant           | P1       |
| B1 | BL receives uncalibrated views       | Quant           | **P0**   |
| B2 | Equal-weight BL prior                | Quant           | P1       |
| B3 | BL vs regime allocation interaction  | Quant           | P1       |
| R1 | Regime covariance stability          | Risk            | P1       |
| R2 | Risk-budget economic value           | Risk            | P1       |
| R3 | Volatility targeting impact          | Risk            | P1       |
| R4 | Turnover/transaction costs           | Portfolio       | P1       |
| M1 | Monte Carlo return model             | Simulation      | P2       |
| P1 | No component-level attribution       | Research        | **P0**   |
| P2 | No benchmark hierarchy               | Research        | **P0**   |
| P3 | No rigorous OOS comparison           | Research        | **P0**   |

# ivestigating returns required

| Version                | What it tells us                      |
| ---------------------- | ------------------------------------- |
| SPY                    | Basic benchmark                       |
| Equal-weight 14 assets | Whether diversification helps         |
| Regime allocation only | Value of regime switching             |
| Risk-budget portfolio  | Value of risk allocation              |
| + forecasts            | Whether forecasting helps             |
| + BL                   | Whether BL helps or hurts             |
| + constraints          | Cost of portfolio constraints         |
| + volatility targeting | Whether vol targeting destroys upside |
| Full production        | Actual strategy                       |


# SYSTEM BELIEVABILITY REQUIREMENTS

                         PRODUCTION PORTFOLIO
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │     RISK GOVERNANCE     │
                    │                         │
                    │ Risk Limits             │
                    │ Drawdown Limits         │
                    │ Concentration Limits    │
                    │ Volatility Limits       │
                    │ Tail Risk                │
                    │ Risk of Ruin             │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │      POSITION RISK      │
                    │                         │
                    │ ATR                     │
                    │ Stop Distance           │
                    │ Risk / Trade            │
                    │ Kelly / Fractional Kelly│
                    │ Position Size            │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │     PORTFOLIO RISK      │
                    │                         │
                    │ Volatility              │
                    │ VaR / CVaR              │
                    │ Risk Contribution       │
                    │ Factor Exposure         │
                    │ Correlation             │
                    │ Stress                  │
                    │ Scenario Loss           │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │    PERFORMANCE QUALITY  │
                    │                         │
                    │ CAGR                    │
                    │ Sortino                 │
                    │ Drawdown                │
                    │ Recovery                │
                    │ Alpha                   │
                    │ Information Ratio       │
                    │ Profit Factor           │
                    │ Expectancy              │
                    │ Win Rate                │
                    │ Reward/Risk              │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │       RETURNS           │
                    │                         │
                    │ Annual Return           │
                    │ Cumulative Return       │
                    └─────────────────────────┘

PerformanceAnalytics
│
├── annual_return()
├── CAGR()
├── annualized_volatility()
├── downside_deviation()
├── sharpe_ratio()
├── sortino_ratio()
├── calmar_ratio()
│
├── equity_curve()
├── drawdown_series()
├── maximum_drawdown()
├── drawdown_duration()
├── recovery_period()
├── recovery_factor()
│
├── alpha()
├── beta()
├── tracking_error()
├── information_ratio()
│
├── annual_return_estimate()
├── rolling_return()
├── rolling_volatility()
├── rolling_sharpe()
├── rolling_sortino()
│
└── performance_report()

Current Drawdown
Maximum Drawdown
Peak Equity
Trough Equity
Peak Date
Trough Date
Drawdown Duration
Recovery Date
Recovery Duration
Time Under Water
Number of Drawdowns
Average Drawdown
Median Drawdown
95th Percentile Drawdown

TradeAnalytics
│
├── trade_count()
├── winning_trades()
├── losing_trades()
│
├── win_rate()
├── loss_rate()
│
├── average_win()
├── average_loss()
├── median_win()
├── median_loss()
│
├── reward_to_risk()
├── expectancy()
├── profit_factor()
├── break_even_win_rate()
│
├── consecutive_wins()
├── consecutive_losses()
├── average_holding_period()
│
├── payoff_ratio()
├── expectancy_per_trade()
│
└── trade_statistics()

Estimated Kelly
       ↓
Fractional Kelly
       ↓
Risk budget
       ↓
Portfolio constraints
       ↓
Volatility target
       ↓
ATR / position sizing
       ↓
Final position

Win probability
Loss probability
Reward / Risk
Risk per trade
Initial capital
Ruin threshold
Number of trades
Correlation assumptions
Analytical Risk of Ruin
Monte Carlo Risk of Ruin
Probability of 20% drawdown
Probability of 30% drawdown
Probability of 50% drawdown
Probability of capital impairment

                PORTFOLIO
                   │
          ┌────────┴────────┐
          │                 │
     Cash/ETF/Stock      Options
          │                 │
     Portfolio Risk     Options Risk
                            │
                  ┌─────────┼─────────┐
                  │         │         │
                Delta     Gamma     Vega
                  │         │         │
                  └─────────┼─────────┘
                            │
                       Aggregation
                            │
                            ▼
                     Portfolio Risk
Net Delta
Gross Delta
Gamma Exposure
Vega Exposure
Theta
Rho
Delta-adjusted exposure
Gamma P&L sensitivity
Volatility shock sensitivity
Zomma

Theoretical parity value
Observed parity value
Parity deviation
Relative deviation
Transaction-cost-adjusted deviation
Arbitrage flag
Observed deviation
        ↓
bid/ask spread
        ↓
fees
        ↓
financing
        ↓
dividends
        ↓
execution costs
        ↓
ONLY THEN determine whether deviation is economically meaningful

=========================================================
              PORTFOLIO RISK REPORT
=========================================================

CAPITAL
---------------------------------------------------------
NAV                         €100,000
Gross Exposure                100.0%
Net Exposure                  100.0%
Cash                            0.0%

RETURN
---------------------------------------------------------
Annual Return                  X.XX%
CAGR                           X.XX%
Annual Return Estimate         X.XX%

RISK
---------------------------------------------------------
Annual Volatility              X.XX%
VaR 95%                        X.XX%
CVaR 95%                       X.XX%
VaR 99%                        X.XX%
CVaR 99%                       X.XX%

DRAWDOWN
---------------------------------------------------------
Current Drawdown               X.XX%
Maximum Drawdown               X.XX%
Drawdown Duration              XXX days
Recovery Time                  XXX days
Time Under Water                XXX days

RISK-ADJUSTED RETURN
---------------------------------------------------------
Sharpe                         X.XX
Sortino                        X.XX
Calmar                         X.XX
Information Ratio              X.XX
Alpha                          X.XX
Beta                           X.XX

TRADE QUALITY
---------------------------------------------------------
Trades                         XXX
Win Rate                       XX.X%
Average Winner                 X.XXR
Average Loser                  X.XXR
Reward/Risk                    X.XX
Expectancy                     X.XXR
Profit Factor                  X.XX
Break-even Win Rate            XX.X%

POSITION RISK
---------------------------------------------------------
Kelly Fraction                 X.XX%
Fractional Kelly               X.XX%
ATR Risk / Position            X.XX%
Largest Risk Contributor       XXXX
Largest Factor Exposure        XXXX

TAIL RISK
---------------------------------------------------------
Risk of Ruin                   X.XX%
P(DD > 10%)                    X.XX%
P(DD > 20%)                    X.XX%
P(DD > 30%)                    X.XX%
P(DD > 50%)                    X.XX%

OPTIONS RISK
---------------------------------------------------------
Net Delta                      X.XX
Gamma                          X.XX
Vega                           X.XX
Put/Call Parity Deviation      X.XX
Zomma                          X.XX
=========================================================
                  RISK STATUS: GREEN/AMBER/RED
=========================================================

# target

                         ┌──────────────────┐
                         │  MARKET DATA     │
                         └────────┬─────────┘
                                  │
                 ┌────────────────▼────────────────┐
                 │         FORECAST ENGINE         │
                 │ Momentum / Trend / Macro / ML  │
                 └────────────────┬────────────────┘
                                  │
                                  ▼
                         EXPECTED RETURNS
                                  │
                                  ▼
                         COVARIANCE ENGINE
                                  │
                                  ▼
                    ┌──────────────────────────┐
                    │    PORTFOLIO OPTIMIZER   │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                         INITIAL ALLOCATION
                                 │
                 ┌───────────────▼────────────────┐
                 │        RISK ENGINE              │
                 │                                 │
                 │ Volatility                      │
                 │ VaR / CVaR                      │
                 │ Risk Contribution               │
                 │ Factor Risk                     │
                 │ Stress                          │
                 │ Drawdown                        │
                 │ Recovery                        │
                 └───────────────┬─────────────────┘
                                 │
                                 ▼
                       POSITION RISK ENGINE
                                 │
                 ┌───────────────┼────────────────┐
                 │               │                │
                ATR            Kelly           Limits
                 │               │                │
                 └───────────────┼────────────────┘
                                 │
                                 ▼
                         RISK GOVERNOR
                                 │
                         ┌───────▼───────┐
                         │ FINAL WEIGHTS │
                         └───────┬───────┘
                                 │
                                 ▼
                       PRODUCTION DECISION
                                 │
                                 ▼
                        EXECUTION SAFETY
                                 │
                                 ▼
                             EXECUTION
                                 │
                                 ▼
                       REALIZED TRADES
                                 │
                 ┌───────────────┴────────────────┐
                 │                                │
          TRADE ANALYTICS                  PERFORMANCE
                 │                                │
        Expectancy                         CAGR
        Win Rate                           Sortino
        Profit Factor                      Alpha
        Reward/Risk                        IR
        Kelly                              Drawdown
        Risk of Ruin                       Recovery
                 │                                │
                 └───────────────┬────────────────┘
                                 ▼
                         RISK FEEDBACK LOOP
                                 │
                                 └──────────► OPTIMIZER

Historical Stress Scenario
────────────────────────────────────
Scenario date
Asset returns on that date
Portfolio return
Portfolio loss
Stressed NAV
Worst contributing asset
Asset-level contributions

# portfolio asset definition

| Asset | Economic exposure           |
| ----- | --------------------------- |
| SPY   | US large-cap equities       |
| QQQ   | US growth/technology        |
| IWM   | US small caps               |
| VEA   | Developed ex-US equities    |
| VWO   | Emerging-market equities    |
| TLT   | Long-duration US Treasuries |
| IEF   | Intermediate Treasuries     |
| SHY   | Short Treasuries            |
| LQD   | Investment-grade credit     |
| HYG   | High-yield credit           |
| GLD   | Gold                        |
| SLV   | Silver                      |
| DBC   | Commodities                 |
| VNQ   | Real estate                 |

# current situation

                  ECONOMIC ENVIRONMENT
                         │
                         ▼
                    REGIME MODEL
                         │
             ┌───────────┼───────────┐
             ▼           ▼           ▼
           BULL       NEUTRAL      CRISIS
             │           │           │
             ▼           ▼           ▼
          15% risk     10% risk      5% risk
             │           │           │
             ▼           ▼           ▼
         Higher        Moderate     Capital
         risk          risk         preservation
             │           │           │
             └───────────┼───────────┘
                         ▼
                    OPTIMIZATION
                         │
                         ▼
                RISK CONSTRAINTS
                         │
             ┌───────────┼────────────┐
             ▼           ▼            ▼
          Position     Leverage     Volatility
           limits       limits       limits
             │           │            │
             └───────────┼────────────┘
                         ▼
                       CASH
                         │
                         ▼
                   FINAL PORTFOLIO


                    OPTIONS POSITIONS
                           │
                           ▼
                  OPTION VALUATION
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
            Greeks       IV data       Pricing
              │
      ┌───────┼────────┬──────────┐
      ▼       ▼        ▼          ▼
    Delta   Gamma     Vega      Zomma
      │       │        │          │
      └───────┴────────┴──────────┘
                       │
                       ▼
              OPTIONS RISK ENGINE
                       │
             ┌─────────┼─────────┐
             ▼         ▼         ▼
         Portfolio   Stress    Parity
          Greeks     Greeks    checks
             │         │         │
             └─────────┼─────────┘
                       ▼
                TAIL / RISK ENGINE
                       │
                       ▼
                 RISK GOVERNOR
                       │
                       ▼
                FINAL DECISION

# next step

R5 — Production Integration / Risk-Feedback Loop

MARKET DATA
    ↓
FORECAST ENGINE
    ↓
EXPECTED RETURNS
    ↓
COVARIANCE ENGINE
    ↓
PORTFOLIO OPTIMIZER
    ↓
INITIAL ALLOCATION
    ↓
RISK ENGINE
    ↓
POSITION RISK ENGINE
    ↓
RISK GOVERNOR
    ↓
FINAL WEIGHTS
    ↓
PRODUCTION DECISION
    ↓
EXECUTION SAFETY
    ↓
EXECUTION
    ↓
REALIZED TRADES
    ↓
TRADE ANALYTICS / PERFORMANCE
    ↓
RISK FEEDBACK LOOP
    ↓
OPTIMIZER

R4 OPTIONS RISK
        │
        ▼
R4.12 REGRESSION CERTIFICATION
        │
        │  ✅ LOCKED
        ▼
================================================
NEXT CONTROLLED GATE
REPOSITORY + SYSTEM RECONCILIATION
================================================
        │
        ├── Actual filesystem
        ├── Git repository
        ├── Branch / commit
        ├── Working tree
        ├── tracked / untracked / ignored
        ├── dependencies
        ├── configuration
        ├── source parity
        ├── module inventory
        └── test/regression state
        │
        ▼
ARCHITECTURE CERTIFICATION
        │
        ▼
EXECUTION HARDENING CERTIFICATION
        │
        ▼
OPERATIONAL HARDENING
        │
        ▼
PAPER TRADING


## Investor dashboard and current delivery plan — 30 October 2026

- `investor_dashboard.py`: private saved-plan aggregation, sanitized presentation payload, exact-date historical market context and optional loopback-only viewer. No order or model-promotion authority.
- `dashboard/investor.html`, `dashboard/investor.css`, `dashboard/investor.js`: accepted investor interface, separate from the existing paper-operator dashboard.
- `dashboard/investor-baseline.json`: owner-accepted UI source hashes; presentation freeze only.
- `productreport.py`: shared private writer and single-plan entry point into the investor interface.
- `test_investor_dashboard.py`: source-identity/privacy/CSP/injection, horizon/market-boundary and manifest containment cases.
- `SYSTEM_DEPLOYMENT_AUDIT_2026_10_30.md`: current code-path audit and deployment gaps.
- `ROADMAP_TO_DEPLOYMENT.md`: current ordered milestones, priority/ownership/acceptance and to-do queue; prior notes retained as historical.
- `CONTINUOUS_STRATEGY_VALIDATION_PLAN.md`: proposed recurring evaluator/search/monitor/promotion architecture. Proposed modules named there are **not implemented** and no research timer is active.


## Investor macro/risk dashboard V2

- `investor_analytics.py`: point-in-time plan context, isolated latest-macro overlay, unvalidated quarterly conditional scenarios and explicitly retrospective fixed-weight risk/macro diagnostics.
- `investor_macro_feed.py`: one-shot private current/revised FRED capture with source hashes; revised features carry retrieval-time availability and cannot replace historical vintage inputs.
- `investor_pdf.py`: full core-universe investor PDF and reusable macro section for monthly paper PDFs.
- `test_investor_analytics.py`: future-data exclusion, stale/missing history, scenario bounds, fixed-weight reconciliation, historical/current separation and PDF/core-universe coverage.
- `INVESTOR_DASHBOARD_V2.md`: source dates, operations, model assumptions and validation limits. No background scheduler is enabled.


## Fresh strategy training and macro allocation lab

See [LIVE_STRATEGY_AND_MACRO_ALLOCATION_GUIDE.md](LIVE_STRATEGY_AND_MACRO_ALLOCATION_GUIDE.md) for the completed current-data run, all four strategies, macro-driven capital/risk allocations, shared economic asset roles, conditional simulations, PDF exports and the authenticated local recalculation service. Latest captured market session: 30 October 2026. The predictive alpha gate remains off; no client-plan replacement, background timer, order or public release is enabled.

### 30 October 2026: operational strategy acceptance

Added `strategy_operations.py` (capture/report/scenario acceptance and immutable prospective session ledger), `scheduled_strategy_validation.py` (locked isolated refresh with failure receipts), `Dockerfile.strategy-validation`, `compose.strategy.yaml` and `deploy/systemd/strategy-validation.*`. See [STRATEGY_DEPLOYMENT_ACCEPTANCE.md](STRATEGY_DEPLOYMENT_ACCEPTANCE.md). Current evidence does not certify a Docker image, external monitoring, public deployment or a completed 20-session observation period.

## Exact-calendar macro repair — 30 October 2026

Current and vintage macro readers now share `macro_feature_contract.py`. Missing periods no longer shift CPI endpoints; quarterly current/revised scenarios fit only consecutive observed transitions. The dashboard, 20 lab scenarios and PDFs were regenerated with source-matched training. See [MACRO_CALENDAR_REPAIR.md](MACRO_CALENDAR_REPAIR.md) for provenance, unchanged risk parameters and open audit findings.

## Repairs 2–4 checkpoint — 31 October 2026

See [REPAIRS_2_3_4_VALIDATION.md](REPAIRS_2_3_4_VALIDATION.md) for strict CSV/scenario/PDF reconciliation, durable v2 job/observation receipts, watchdog and explicit quarantine recovery, and prospective NAV/forecast accounting. Use `var/strategy-operations-v2` for new observations; the prior v1 root remains archived and untrusted for migration. Current v2 state is 1 operational observation and **0 forward return sessions**, not a completed observation period. No timers, external alerts or public deployment were enabled.

## Repair 5 — economic design, 31 October 2026

Implemented and executed `economic_design_assessment.py` and `economic_design_report.py`: independent path/profit reconciliation, observed SGOV versus unverified user cash, cost/availability attribution, prior-close risk-budget references, paired block-bootstrap intervals, 28-asset diagnostics, aggregate stress review and a declared three-year reference frontier. See [ECONOMIC_DESIGN_REASSESSMENT.md](ECONOMIC_DESIGN_REASSESSMENT.md). The 30 configurations × 29 overlapping cohorts produced no joint 50%-return/5%-drawdown success. This is not proof of impossibility. All four economic screens remain blocked; no current weights, predictive gate, investor dashboard or prospective cohort changed. The next numbered repair is 6, the unified product contract; independent economic validation and actual cash/exposure inputs remain prerequisites.

## P0/P1 execution checkpoint — 31 October 2026

See [ECONOMIC_P0_P1_EXECUTION.md](ECONOMIC_P0_P1_EXECUTION.md) for source/reviewer evidence gates, official release-incident reconciliation, the separately solved stress-budget challenger, predeclared cost/fallback comparisons, reviewed recovery validation and independent prospective cohorts. The owner confirmed no verified files are available, so cash/cost/access/exposure gates remain blocked. Active challenger configuration is `research/stress_budget_challenger_v2.json`; original strategies and their cohort are unchanged. V2 shadow results and daily-handoff templates do not imply financial approval or a qualified host.

## Growth & Resilience policy update — 31 October 2026

- `portfolio_objectives.py`: current no-fixed-return/no-fixed-account-drawdown policy; explicit legacy guards remain reproducible.
- `growth_resilience.py`: fully funded strategic reference, common-history net-cost comparisons, variance attribution and joint block-bootstrap scenarios.
- `market_news.py`: bounded allowlisted public RSS ingestion and five-minute cached authenticated dashboard feed.
- `capture_growth_inputs.py`: source-hashed healthcare extension and public headline snapshots for current and future dashboard refreshes.
- `GROWTH_RESILIENCE_BENCHMARK.md`: design, allocation, limitations, sources, validation and local news instructions.

## Institutional-method return challengers — 31 October 2026

- `institutional_return_engines.py`: four frozen long-only designs, observed eligibility, multi-horizon signals, covariance and portfolio constraints.
- `evaluate_institutional_engines.py` / `assess_return_engine_robustness.py`: prior-close execution, cost/period studies, independent replay and risk-matched references.
- `return_engine_shadow.py` / `run_return_engine_cycle.py`: separate immutable prospective cohort and locked idempotent cycle; no promotion or orders.
- `publish_return_engine_preview.py`: explicitly unapproved dashboard evidence.
- `INSTITUTIONAL_RETURN_ENGINES.md`: research mapping, results and limits.

## Unified release acceptance — 31 October 2026

- `release_acceptance.py`: one source-bound, locked, read-only workflow audit; isolated PDF/MIME and backup/restore exercises, fresh regression, and explicit external blockers. No deployment, sending, model promotion or appended observations.
- `test_release_acceptance.py`: status semantics, missing prerequisites, regression binding, runtime version matching, ledger/contract integrity, locks, browser evidence, immutable inputs and no-SMTP preview tests.
- `RELEASE_ACCEPTANCE_GUIDE.md`: command, evidence interfaces, exit codes and operating boundary.
- `deploy/release-acceptance-browser.example.json`: intentionally unapproved browser-review schema.
