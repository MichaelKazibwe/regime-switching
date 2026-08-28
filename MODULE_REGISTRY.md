# MODULE REGISTRY — REGIME SWITCHING PORTFOLIO FRAMEWORK

**Registry state:** System inventory baseline established 2026-08-26
**Source basis:** supplied complete project source bundle (70 file entries) and current project architecture/progress document.
**Deployment status:** NOT READY FOR LIVE DEPLOYMENT — systematic inspection and hardening remain.

## 1. Inventory facts

- **70 bundled file entries**: 65 root entries + 5 archive entries.
- **64 production modules** are represented by the root modules excluding `final_regression.py`; `final_regression.py` is the comprehensive regression gate.
- The architecture document previously described a 64-file production inventory; the distinction above reconciles that count with the 65 root entries currently bundled.
- The 14-asset production universe is: SPY, QQQ, IWM, VEA, VWO, TLT, IEF, SHY, LQD, HYG, GLD, SLV, DBC, VNQ.

## 2. Module registry
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