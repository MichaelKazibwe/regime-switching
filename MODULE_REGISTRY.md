# Regime Switching Portfolio Framework

Version: 1.0.0

---

# Project Architecture

The project follows a layered architecture.

Dependencies are strictly top-down.

```
Execution
    ↑
Portfolio
    ↑
Risk
    ↑
Covariance
    ↑
Forecast
    ↑
Universe
    ↑
Data
    ↑
Core
```

Lower layers must never import higher layers.

---

# CORE

Purpose

Shared infrastructure used by every other package.

Modules

- BaseObject
- BaseCovarianceModel
- Settings
- Validators
- Exceptions

Status

Production

Dependencies

None

---

# DATA

Purpose

Responsible for obtaining market and macroeconomic data.

Modules

- MarketDataLoader

Status

Production

Depends On

- Core

Used By

- Forecast
- Covariance
- Risk

---

# UNIVERSE

Purpose

Defines the investable universe.

Modules

- AssetUniverse

Status

Production

Depends On

- Core

Used By

- Data
- Forecast
- Covariance
- Risk
- Portfolio

---

# FORECAST

Purpose

Expected return forecasting.

Modules

- MomentumForecast
- TrendForecast
- MeanReversionForecast
- ExpectedReturnForecaster
- MacroRegimeModel

Status

Production

Depends On

- Core
- Data
- Universe

Used By

- Portfolio

---

# COVARIANCE

Purpose

Risk estimation.

Modules

- BaseCovarianceModel
- CovarianceEngine
- RegimeCovariance
- FactorCovariance
- EnsembleCovariance

Status

Production

Depends On

- Core
- Data
- Universe

Used By

- Risk

---

# RISK

Purpose

Portfolio risk analytics.

Modules

- RiskModel
- ForwardRiskMetrics
- ForwardRiskAnalyzer
- RiskContributionAnalytics

Status

Production

Depends On

- Covariance

Used By

- Portfolio

---

# PORTFOLIO

Purpose

Portfolio construction.

Modules

- PortfolioConstraints
- BlackLittermanModel
- PortfolioOptimizer

Status

Production

Depends On

- Forecast
- Risk

Used By

- Execution

---

# ANALYTICS

Purpose

Performance measurement.

Modules

- PerformanceAnalytics
- PerformanceAttribution

Status

Production

Depends On

- Portfolio

---

# SIMULATION

Purpose

Scenario analysis and stress testing.

Modules

- RegimeMonteCarlo
- RegimePortfolioSimulator
- RegimeSimulationAnalytics
- DrawdownForecastEngine
- RegimeDrawdownSimulator
- DrawdownProbabilityAnalytics

Status

Production

Depends On

- Risk
- Portfolio

---

# EXECUTION

Purpose

Order generation and live trading.

Planned Modules

- Portfolio
- TradeGenerator
- ExecutionEngine
- TransactionCostModel
- OMS
- BrokerRouter
- PaperBroker
- LiveBroker

Status

Planned

---

# Future Roadmap

Phase 1 ✅

- Core
- Data
- Universe

Phase 2 ✅

- Forecast
- Covariance

Phase 3 ✅

- Risk

Phase 4

- FactorExposureModel
- ScenarioEngine

Phase 5

- Portfolio

Phase 6

- Execution

Phase 7

- Live Trading

---

# Design Principles

1. One responsibility per module.

2. No circular dependencies.

3. Every production module has:

- API_VERSION
- PUBLIC_METHODS
- metadata
- health_check()
- regression tests

4. All mathematical models are deterministic.

5. Every production module must pass

- py_compile
- ruff
- regression tests

before release.

# Module Maturity

| Module | Version | Status |
|---------|---------|--------|
| BaseObject | 1.0.0 | Stable |
| BaseCovarianceModel | 1.0.0 | Stable |
| AssetUniverse | 1.0.0 | Stable |
| CovarianceEngine | 1.0.0 | Stable |
| RegimeCovariance | 1.0.0 | Stable |
| FactorCovariance | 1.0.0 | Stable |
| EnsembleCovariance | 1.0.0 | Stable |
| RiskModel | 1.0.0 | Stable |
| PortfolioOptimizer | 0.x | Under Development |
| BlackLittermanModel | 0.x | Under Development |
| ScenarioEngine | Planned | Not Started |
| FactorExposureModel | Planned | Not Started |
| Portfolio | Planned | Not Started |
| ExecutionEngine | Planned | Not Started |

                    ┌─────────────────────┐
                    │   RebalanceEngine   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │        OMS          │
                    │                     │
                    │  Order Submission   │
                    │  Validation         │
                    │  Order Lifecycle    │
                    │  Cancellation       │
                    │  Rejection          │
                    │  Execution Routing  │
                    └──────┬───────┬──────┘
                           │       │
                ┌──────────┘       └──────────┐
                ▼                             ▼
        ┌──────────────┐              ┌──────────────┐
        │  OrderBook   │              │ Execution    │
        │              │              │ Engine       │
        └──────────────┘              └──────┬───────┘
                                             │
                                             ▼
                                      ┌──────────────┐
                                      │    Trade     │
                                      └──────────────┘


CORE              ████████████████████  Stable
DATA              ████████████████████  Stable
UNIVERSE          ████████████████████  Stable
FORECAST          ████████████████████  Stable
COVARIANCE        ████████████████████  Stable
RISK              ████████████████████  Stable
PORTFOLIO         ███████████░░░░░░░░░  Development
ANALYTICS         █████████████████░░░  Integration
SIMULATION        ███████████████░░░░░  Development
EXECUTION         ████████████████░░░░  Integration
LIVE TRADING      ███░░░░░░░░░░░░░░░░░  Planned

MARKET DATA
     ↓
UNIVERSE
     ↓
FORECAST
     ↓
COVARIANCE
     ↓
RISK
     ↓
PORTFOLIO
     ↓
REBALANCE
     ↓
OMS
     ↓
ORDER BOOK
     ↓
EXECUTION ENGINE
     ↓
TRADE
     ↓
PORTFOLIO ACCOUNT

                    RebalanceEngine
                           │
                           ▼
                    ┌─────────────┐
                    │     OMS     │
                    └──────┬──────┘
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
        Validation     Risk Gates    Duplicate Check
             │             │             │
             └─────────────┼─────────────┘
                           ▼
                    ┌─────────────┐
                    │  OrderBook  │
                    └──────┬──────┘
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
         Submit        Cancel        Reject
             │             │             │
             └─────────────┼─────────────┘
                           ▼
                  ExecutionEngine
                           │
                           ▼
                         Trade
                           │
                           ▼
                   PortfolioAccount
                           │
                           ▼
                    Reconciliation


test_oms()
│
├── lifecycle_oms
│   ├── submit
│   ├── execute
│   ├── cancel
│   └── reject
│
├── risk_oms
│   ├── risk approval
│   └── risk rejection
│
└── serialization / health

Portfolio / Rebalance
        │
        ▼
       OMS
        │
        ▼
PreTradeRiskGate
        │
   ┌────┴────┐
   │         │
REJECT     APPROVE
   │         │
   │         ▼
   │     OrderBook
   │         │
   │         ▼
   │  ExecutionEngine
   │         │
   │         ▼
   │       Trade
   │         │
   └─────────┴──────► PortfolioAccount

Portfolio Target
      │
      ▼
RebalanceEngine
      │
      ▼
TradeGenerator        ← WHAT should we trade?
      │
      ▼
PreTradeRiskGate      ← Is the proposed trade allowed?
      │
      ▼
OMS                   ← Manage the order lifecycle
      │
      ▼
BrokerRouter          ← WHERE/HOW should the order be routed?
      │
      ▼
ExecutionEngine / Broker
      │
      ▼
Trade

TradeGenerator
├── target/current position reconciliation
├── delta calculation
├── BUY/SELL determination
├── quantity generation
├── minimum trade threshold
├── deterministic order IDs
├── Order creation
├── batch generation
├── metadata
├── health_check()
├── to_dict()
├── from_dict()
└── regression tests

Current Portfolio
       │
       ▼
Target Portfolio
       │
       ▼
TradeGenerator
       │
       ├── BUY orders
       ├── SELL orders
       └── no-op / threshold filtering
              │
              ▼
            Order
              │
              ▼
        PreTradeRiskGate
              │
              ▼
             OMS

BrokerRouter
     │
     ▼
PaperBroker
     │
     ├── accepts routed orders
     ├── maintains broker-side order state
     ├── supports cancellation
     ├── simulates fills deterministically
     ├── records execution receipts
     ├── NEVER modifies PortfolioAccount
     └── NEVER bypasses OMS


                  EXECUTION STACK

TradeGenerator
      │
      ▼
PreTradeRiskGate
      │
      ▼
OMS
      │
      ▼
BrokerRouter
      │
      ▼
PaperBroker
      │
      │  broker-side execution receipt
      ▼
Execution / Accounting Layer
      │
      ▼
PortfolioAccount


TradeGenerator
      │
      ▼
PreTradeRiskGate
      │
      ▼
OMS
      │
      ▼
BrokerRouter
      │
      ▼
PaperBroker
      │
      ├── Broker acknowledgement
      ├── Broker Order ID
      ├── Partial fill
      ├── Full fill
      ├── Cancellation
      ├── Rejection
      └── Execution receipt
             │
             ▼
       Execution / Accounting


RebalanceEngine
       │
       ▼
TradeGenerator
       │
       ▼
PreTradeRiskGate
       │
       ▼
OMS
       │
       ▼
BrokerRouter
       │
       ├───────────────┐
       ▼               ▼
 PaperBroker        LiveBroker
       │
       ▼
Execution Receipt
       │
       ▼
ExecutionEngine
       │
       ▼
PortfolioAccount


Portfolio
    ↓
RebalanceEngine
    ↓
TradeGenerator
    ↓
PreTradeRiskGate
    ↓
OMS
    ↓
BrokerRouter
    ↓
PaperBroker
    ↓
BrokerExecutionEngine
    ↓
ExecutionEngine
    ↓
Trade
    ↓
PortfolioAccount
    ↓
Reconciliation

RebalanceEngine
      ↓
TradeGenerator
      ↓
PreTradeRiskGate
      ↓
OMS
      ↓
BrokerRouter
      ↓
PaperBroker
      ↓
BrokerExecutionEngine
      ↓
ExecutionEngine
      ↓
PortfolioAccount
      ↓
Reconciliation

                 OMS
                  │
                  ▼
            BrokerRouter
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
   PaperBroker          LiveBroker
        │                   │
        └─────────┬─────────┘
                  ▼
       BrokerExecutionEngine
                  │
                  ▼
        Execution Receipt
                  │
                  ▼
       ┌───────────────────┐
       │ Reconciliation    │
       │ Engine            │
       └─────────┬─────────┘
                 │
        ┌────────┼────────┐
        ▼        ▼        ▼
      OMS      Broker   Account
     State      State    State

ReconciliationEngine
        │
        ├── observes OMS
        ├── observes broker
        ├── observes account
        │
        └── produces decision
                 │
                 ├── MATCHED
                 └── DISCREPANCY

Order
  ↓
OrderStatus
  ↓
OrderBook
  ↓
TransactionCostModel
  ↓
ExecutionEngine
  ↓
RebalanceEngine
  ↓
TradeGenerator
  ↓
PreTradeRiskGate
  ↓
OMS
  ↓
BrokerRouter
  ↓
PaperBroker
  ↓
BrokerExecutionEngine
  ↓
LiveBroker
  ↓
ReconciliationEngine
  ↓
PostTradeExecutionMonitor
  ↓
ExecutionAnalytics



                    MARKET DATA
                        │
                        ▼
              ┌──────────────────┐
              │ Macro / Regime   │
              │ Detection        │
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │ Forecast / Alpha │
              │ Engine           │
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │ Expected Return  │
              │ Model            │
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │ Risk / Covariance│
              │ Architecture     │
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │ Black-Litterman  │
              │ / Portfolio      │
              │ Optimizer        │
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │ Constraints /    │
              │ Risk Budgeting   │
              └────────┬─────────┘
                       │
                       ▼
                TARGET PORTFOLIO
                       │
                       ▼
                REBALANCE ENGINE
                       │
                       ▼
                TRADE GENERATOR
                       │
                       ▼
              ─── EXECUTION STACK ───
                       │
                       ▼
                  ANALYTICS

                    MARKET / PORTFOLIO STATE
                              │
                              ▼
                    ┌─────────────────────┐
                    │ PortfolioDecision   │
                    │ Engine               │
                    └──────────┬──────────┘
                               │
             ┌─────────────────┼─────────────────┐
             │                 │                 │
             ▼                 ▼                 ▼
        MacroRegime       Expected Return     Covariance
             │                 │                 │
             └─────────────────┼─────────────────┘
                               ▼
                       Black-Litterman
                               │
                               ▼
                     Portfolio Optimizer
                               │
                               ▼
                       Constraints
                               │
                               ▼
                         Risk Model
                               │
                               ▼
                   Risk Contributions
                               │
                               ▼
                     Scenario Analysis
                               │
                               ▼
                    ┌───────────────────┐
                    │ PortfolioDecision │
                    └─────────┬─────────┘
                              │
                              ▼
                      RebalanceEngine
                              │
                              ▼
                       TradeGenerator
                              │
                              ▼
                       Execution Stack

#==============================
#portfolio decision engine
#==============================

INPUT
  ↓
TICKERS
  ↓
REGIME
  ↓
EXPECTED RETURNS
  ↓
COVARIANCE
  ↓
BLACK-LITTERMAN
  ↓
OPTIMIZATION
  ↓
CONSTRAINTS
  ↓
WEIGHT VALIDATION
  ↓
RISK METRICS
  ↓
PORTFOLIO METRICS
  ↓
SCENARIOS
  ↓
APPROVED / REJECTED
  ↓
PortfolioDecision
  ↓
AUDIT + SUMMARY + SERIALIZATION


                    MARKET DATA
                         │
                         ▼
                 ┌───────────────┐
                 │ AssetUniverse │
                 └───────┬───────┘
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
       MacroRegimeModel       ExpectedReturnForecaster
             │                       │
             │                       │
             └───────────┬───────────┘
                         ▼
                 Regime Selection
                         │
                         ▼
              ┌────────────────────┐
              │ RegimeCovariance   │
              │        +           │
              │ EnsembleCovariance │
              │        +           │
              │ FactorCovariance   │
              └──────────┬─────────┘
                         │
                         ▼
                 Covariance Matrix
                         │
                         ▼
              ┌────────────────────┐
              │ Black-Litterman    │
              └──────────┬─────────┘
                         │
                         ▼
              Posterior Expected Return
                         │
                         ▼
              ┌────────────────────┐
              │ PortfolioOptimizer │
              └──────────┬─────────┘
                         │
                         ▼
              PortfolioConstraints
                         │
                         ▼
                  RiskModel
                         │
                         ▼
             RiskContributionAnalyzer
                         │
                         ▼
                  ScenarioEngine
                         │
                         ▼
             PortfolioDecisionEngine
                         │
                         ▼
                Portfolio Target
                         │
                         ▼
                  RebalanceEngine
                         │
                         ▼
                 TradeGenerator
                         │
                         ▼
                 PreTradeRiskGate
                         │
                         ▼
                       OMS
                         │
                         ▼
                  BrokerRouter
                         │
                         ▼
                   PaperBroker
                         │
                         ▼
             BrokerExecutionEngine
                         │
                         ▼
                 ExecutionEngine
                         │
                         ▼
                PortfolioAccount

#===============================
# Risk budget engine
#===============================

                    PRODUCTION COMPOSITION
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
          ▼                  ▼                  ▼
   RiskBudgetEngine   ExpectedReturn       Black-Litterman
          │             Forecaster             Model
          │                  │                  │
          └──────────────────┼──────────────────┘
                             ▼
                    PortfolioOptimizer
                             │
                    ┌────────┴────────┐
                    │                 │
                    ▼                 ▼
               Constraints       Risk Budgets
                    │
                    ▼
             PortfolioDecisionEngine

IV-B.5 Execution Gate
        │
        ▼
IV-B.3 Decision Execution       ✅
        │
        ▼
IV-B.2 Integration              ✅
        │
        ▼
Portfolio Decision Engine       ✅
        │
        ├── Asset Universe       ✅
        ├── Regime Model         ✅
        ├── Expected Returns     ✅
        ├── Covariance           ✅
        ├── Regime Covariance    ✅
        ├── Ensemble Covariance  ✅
        ├── Black-Litterman      ✅
        ├── Optimizer            ✅
        ├── Constraints          ✅
        ├── Risk Model           ✅
        ├── Risk Contribution    ✅
        └── Scenario Engine      ✅


                    ┌──────────────────────┐
                    │   Market / Portfolio │
                    │        State         │
                    └──────────┬───────────┘
                               │
                               ▼
                  ┌─────────────────────────┐
                  │ PortfolioDecisionEngine │
                  │        PHASE IV-A       │
                  └───────────┬─────────────┘
                              │
             ┌────────────────┼────────────────┐
             │                │                │
             ▼                ▼                ▼
       Regime Model      Expected Return    Covariance
                                              │
                         ┌────────────────────┼──────────────┐
                         │                    │              │
                         ▼                    ▼              ▼
                  CovarianceEngine    RegimeCovariance   Factor...
                         │                    │
                         └─────────┬──────────┘
                                   ▼
                         EnsembleCovariance
                            60% base
                            40% regime
                                   │
                                   ▼
                         Black-Litterman
                                   │
                                   ▼
                           PortfolioOptimizer
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
             RiskBudgetEngine             Constraints
                    │
                    ▼
             Risk Contribution
                    │
                    ▼
             Scenario Analysis
                    │
                    ▼
              Portfolio Decision
                    │
                    ▼
             ┌─────────────────┐
             │  IV-B PIPELINE  │
             └────────┬────────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
       Decision     Risk       Execution
       Execution  Validation     Gate
          │           │           │
          └───────────┴───────────┘
                      │
                      ▼
             Production Pipeline

market/returns
      ↓
regime
      ↓
expected returns
      ↓
base covariance
      +
regime covariance
      ↓
60/40 ensemble
      ↓
Black-Litterman
      ↓
optimizer
      ↓
RiskBudgetEngine
      ↓
PortfolioDecision
      ↓
ProductionRiskValidation
      ↓
ExecutionGate


REAL HISTORICAL DATA
        │
        ├── Prices
        │     ├── SPY
        │     ├── EFA
        │     └── EEM
        │
        ├── Macro
        │     ├── Unemployment
        │     ├── Yield Spread
        │     └── Inflation
        │
        └── Historical Regimes
                │
                ▼
       INPUT VALIDATION
                │
                ▼
     PortfolioDecisionEngine
                │
        ┌───────┴────────┐
        ▼                ▼
 Expected Returns    Regime Covariance
        │                │
        └───────┬────────┘
                ▼
       Covariance Ensemble
                │
                ▼
        Black-Litterman
                │
                ▼
       Risk-Budget Optimizer
                │
                ▼
       Portfolio Constraints
                │
                ▼
          Risk Analysis
                │
                ▼
       APPROVED / REJECTED


                    REGRESSION SUITE
                           │
          ┌────────────────┼─────────────────┐
          │                │                 │
          ▼                ▼                 ▼
   Infrastructure    Portfolio Layer    Execution Layer
          │                │                 │
          │                │                 ├── Orders
          │                │                 ├── OMS
          │                │                 ├── Broker
          │                │                 ├── Execution
          │                │                 └── Reconciliation
          │                │
          │                ├── Risk budgets
          │                ├── Constraints
          │                ├── Position caps
          │                ├── Vol targeting
          │                ├── Leverage
          │                ├── Cash
          │                └── Risk report
          │
          ├── Compilation
          ├── Ruff
          ├── Imports
          └── Required modules

Regime
   │
   ▼
Risk Budget
   │
   ▼
Risk-Budget Optimizer
   │
   ▼
Portfolio Constraints
   │
   ▼
Volatility Targeting
   │
   ▼
Leverage Safety Backstop
   │
   ▼
Cash Sleeve
   │
   ▼
Final Invariants
   │
   ▼
Risk Report
   │
   ▼
Production Portfolio


REGIME REGRESSION
│
├── bull
│   ├── optimize
│   ├── validate
│   ├── volatility
│   ├── leverage
│   ├── cash
│   └── regime_results["bull"] = ...
│
├── neutral
│   ├── optimize
│   ├── validate
│   ├── volatility
│   ├── leverage
│   ├── cash
│   └── regime_results["neutral"] = ...
│
└── crisis
    ├── optimize
    ├── validate
    ├── volatility
    ├── leverage
    ├── cash
    └── regime_results["crisis"] = ...

FEASIBLE VOLATILITY TARGET
│
├── reads regime_results["bull"]
├── creates low-exposure portfolio
├── proves target is feasible
├── calls optimizer.vol_target_engine
├── independently calculates final volatility
└── requires target achievement

CROSS-REGIME DIFFERENTIATION
│
├── bull vs neutral
├── neutral vs crisis
└── bull vs crisis

# current progress
Market/Price Data
      ↓
Expected Return Forecaster
      ↓
Momentum
Trend
Mean Reversion
      ↓
Combined Forecast
      ↓
Black-Litterman
      ↓
Regime-Aware Portfolio Optimizer
      ↓
Risk Budgeting
      ↓
Volatility Targeting
      ↓
Portfolio / Cash
      ↓
Execution Stack

# test regression structure

PHASE 0 — PROJECT ROOT
        ↓
PHASE 1 — PYTHON RUNTIME
        ↓
PHASE 2 — REQUIRED MODULE FILES
        ↓
PHASE 3 — PYTHON COMPILATION
        ↓
PHASE 4 — RUFF STATIC ANALYSIS
        ↓
PHASE 5 — IMPORT SMOKE TEST
        ↓
PHASE 6A — PRODUCTION PORTFOLIO REGRESSION
        ↓
PHASE 12B — REGIME-CONDITIONED FORECAST REGRESSION
        ↓
PHASE 7 — REGRESSION MODULE INVENTORY
        ↓
PHASE 8 — EXECUTION CHAIN INTEGRITY
        ↓
PHASE 9 — MODULE REGRESSION TESTS
        ↓
PHASE 10 — REPOSITORY STATUS
        ↓
FULL SYSTEM REGRESSION SUMMARY


| Component                     | Responsibility                      |
| ----------------------------- | ----------------------------------- |
| `macroregime.py`              | Determine economic regime           |
| `regimeforecastengine.py`     | Condition forecasts on regime       |
| `expectedreturnforecaster.py` | Produce raw forecast components     |
| `blacklitterman.py`           | Blend equilibrium returns and views |
| `riskbudgetengine.py`         | Determine regime risk budgets       |
| `volatilitytargeting.py`      | Scale portfolio risk                |
| `portfoliooptimizer.py`       | Construct final portfolio           |
| `productioncomposition.py`    | Wire production components together |
| `regression_suite.py`         | Prove the system works              |


                    FINAL REGRESSION
                           │
             ┌─────────────┴─────────────┐
             │                           │
        64-FILE INVENTORY          REPOSITORY HYGIENE
             │                           │
             ▼                           ▼
       PYTHON COMPILE              stale references
             │                     backup artifacts
             ▼                     duplicate modules
        AST AUDIT                  git state
             │
             ▼
       IMPORT AUDIT
             │
             ▼
       DEPENDENCY GRAPH
             │
             ▼
       CYCLE DETECTION
             │
             ▼
      INDIVIDUAL FILE TESTS
             │
             ▼
       CORE ENGINES
             │
       ┌─────┼─────────┐
       ▼     ▼         ▼
    Risk   Forecast   Covariance
       │     │         │
       └─────┼─────────┘
             ▼
      PORTFOLIO OPTIMIZER
             │
             ▼
    PORTFOLIO DECISION ENGINE
             │
             ▼
    PRODUCTION INTEGRATION
             │
             ▼
      RISK VALIDATION
             │
             ▼
      EXECUTION GATE
             │
             ▼
      EXECUTION CHAIN
             │
             ▼
       HISTORICAL TESTS
             │
             ▼
       FINAL CERTIFICATION


# ULTIMATE GOAL (fully operational live-trading system)

SYSTEM
────────────────────
System Health
Data Health
Broker Health
Database Health
Clock Health

PORTFOLIO
────────────────────
NAV
Daily P&L
Cumulative P&L
Drawdown
Volatility
Sharpe
Exposure

REGIME
────────────────────
Current Regime
Probability
Confidence
Forecast

RISK
────────────────────
VaR
CVaR
Stress Loss
Risk Budget
Factor Exposure

EXECUTION
────────────────────
Orders
Open Orders
Fills
Rejects
Slippage
Turnover

RECONCILIATION
────────────────────
Broker vs Internal


                ┌─────────────────────┐
                │ Control Plane       │
                │ Dashboard/API       │
                └──────────┬──────────┘
                           │
        ┌──────────────────▼─────────────────┐
        │ Trading Orchestrator               │
        └───────┬───────────┬───────────────┘
                │           │
       ┌────────▼───┐ ┌─────▼────────┐
       │ Strategy   │ │ Risk Engine  │
       └────────┬───┘ └─────┬────────┘
                │           │
                └─────┬─────┘
                      ▼
               Execution Gateway
                      │
             ┌────────┴────────┐
             │                 │
        Paper Broker       Live Broker
                              │
                           Exchange

# current modules

assetuniverse.py
macroregime.py
regimeforecastengine.py
regimecovariance.py
expectedreturnforecaster.py
forecastmodels.py
covarianceengine.py
ensemblecovariance.py
factorcovariance.py
factorexposuremodel.py
blacklitterman.py
portfoliooptimizer.py
constraints.py
riskbudgetengine.py
riskmodel.py
riskcontributionanalyzer.py
volatilitytargeting.py
scenarioengine.py
regimesimulation.py
forwardriskmetrics.py
forwardriskanalyzer.py

# NEEDED
# data infrastructure
marketdata/
    marketdatagateway.py
    realtimefeed.py
    historicaldata.py
    datacache.py
    dataquality.py
    datafreshness.py
    corporateactions.py
    tradingcalendar.py
# portfolio infrastructure
portfolio/
    portfolioledger.py
    positionservice.py
    cashservice.py
    navengine.py
    portfolioaccounting.py
# risk infrastructure
risk/
    pretrade_risk.py
    intraday_risk.py
    liquidityrisk.py
    marketimpact.py
    varengine.py
    cvarengine.py
    stressengine.py
    factorrisk.py
    drawdowncontroller.py
    circuitbreaker.py
    killswitch.py
#  execution infrastructure
execution/
    executionrouter.py
    executionoptimizer.py
    executionalgorithms.py
    vwap.py
    twap.py
    pov.py
    adaptiveexecution.py
    orderstate.py
    idempotency.py
    executionrecovery.py
# broker infrastructure
brokers/
    brokerinterface.py
    brokerfactory.py
    brokerhealth.py
    brokerfailover.py
    alpaca_transport.py
    ibkr_transport.py
# persistence
persistence/
    database.py
    models.py
    repositories.py
    orderrepository.py
    executionrepository.py
    positionrepository.py
    auditrepository.py
    decisionrepository.py
# recovery
recovery/
    staterecovery.py
    restartrecovery.py
    reconciliationrecovery.py
    brokerrecovery.py
# monitoring
monitoring/
    metrics.py
    health.py
    alerts.py
    alertmanager.py
    systemmonitor.py
    datamonitor.py
    broker_monitor.py
    riskmonitor.py
# governance/
    modelregistry.py
    strategyregistry.py
    configregistry.py
    deploymentregistry.py
    auditlog.py
    changelog.py
# deployment
deployment/
    Dockerfile
    docker-compose.yml
    healthcheck.py
    startup.py
    shutdown.py
    .github/
    workflows/
        tests.yml
        regression.yml
        deployment.yml
# production API
api/
    app.py
    auth.py
    portfolio_routes.py
    risk_routes.py
    execution_routes.py
    health_routes.py
    admin_routes.py
# operational dashboard
dashboard/
    app.py
    pages/
        overview.py
        portfolio.py
        risk.py
        regime.py
        execution.py
        reconciliation.py
        system.py
        audit.py
# test architecture
tests/
    unit/
    integration/
    regression/
    property/
    risk/
    execution/
    broker/
    recovery/
    chaos/
    data/
    live_safety/
# final
                 LIVE-SAFETY
                    ▲
                    │
               CHAOS TESTS
                    │
             BROKER INTEGRATION
                    │
              PAPER TRADING
                    │
             HISTORICAL TESTS
                    │
            SYSTEM INTEGRATION
                    │
                UNIT TESTS

# "over-the-edge" system
multi-strategy
multi-portfolio
multi-broker
multi-currency
cross-asset
intraday regime updates
adaptive execution
dynamic risk budgets
real-time factor risk
portfolio-level hedging
tail-risk overlays
stress-triggered de-risking
automatic recovery
automatic broker failover
model ensemble governance


Macro regime
     ↓
Regime-conditioned expected returns
     +
Regime-conditioned covariance
     +
Black-Litterman views
     +
Risk model
     +
Constraints
     ↓
Portfolio optimizer
     ↓
Target weights
     ↓
Position sizing
     ↓
Turnover / transaction-cost control
     ↓
Portfolio

# portfoliooptimizer

Expected Return
+
Black-Litterman
+
Covariance
+
Regime Risk Budget
+
Portfolio Constraints
+
Volatility Target
+
Leverage Limit


What regime?
     ↓
What risk budget?
     ↓
What baseline allocation?
     ↓
What did BL do?
     ↓
What did constraints do?
     ↓
What did volatility targeting do?
     ↓
What was the final leverage?
     ↓
How much cash?

# system goal: 1

14 assets
   ↓
Market data
   ↓
Macro data
   ↓
Regime classification
   ↓
Regime-conditioned covariance
   ↓
Expected returns
   ↓
Black-Litterman
   ↓
Risk budgets
   ↓
Portfolio constraints
   ↓
Volatility targeting
   ↓
PortfolioOptimizer
   ↓
PortfolioDecisionEngine
   ↓
14-asset production portfolio
   ↓
Historical walk-forward backtest
   ↓
Transaction costs
   ↓
Execution stack
   ↓
Final regression

┌─────────────────────────────────────────────────────────────┐
│                     OPERATIONS / UI                         │
│ API + Dashboard + Alerts + Admin                            │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                    GOVERNANCE LAYER                          │
│ Model Registry | Strategy Registry | Config | Audit         │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                    DECISION ENGINE                           │
│ Regime → Forecast → BL → Optimizer → Risk Budget            │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                     RISK ENGINE                              │
│ Pre-trade | Intraday | VaR | CVaR | Stress | Liquidity      │
│ Factor Risk | Drawdown | Circuit Breaker | Kill Switch      │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                  PORTFOLIO / OMS LAYER                       │
│ Portfolio Ledger | Positions | Cash | NAV | Orders           │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                  EXECUTION ENGINE                            │
│ Router | Optimizer | VWAP | TWAP | POV | Adaptive            │
│ Order State | Idempotency | Recovery                         │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                    BROKER LAYER                              │
│ Broker Interface | Factory | Health | Failover              │
│ IBKR | Alpaca | Future Brokers                              │
└──────────────────────────────┬──────────────────────────────┘
                               │
                         EXTERNAL MARKET


                         ┌─────────────────────────────────────────────────────────────┐
│                 DATA INFRASTRUCTURE                          │
│ Gateway | Realtime | Historical | Cache | Quality            │
│ Freshness | Corporate Actions | Trading Calendar             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                 PERSISTENCE                                  │
│ DB | Orders | Executions | Positions | Decisions | Audit     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                 RECOVERY                                     │
│ State | Restart | Reconciliation | Broker Recovery            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                 MONITORING                                   │
│ Metrics | Health | Alerts | Data | Broker | Risk | System    │
└─────────────────────────────────────────────────────────────┘

# orchestration

orchestration/

    tradingengine.py

    decisionengine.py

    rebalanceengine.py

    ordergeneration.py

    riskgate.py

    executionengine.py

    reconciliationengine.py

    lifecyclemanager.py

# TradingEngine

TradingEngine
      │
      ├── MarketDataGateway
      │
      ├── RegimeEngine
      │
      ├── ForecastEngine
      │
      ├── PortfolioOptimizer
      │
      ├── RiskEngine
      │
      ├── PortfolioService
      │
      ├── OrderGenerator
      │
      ├── ExecutionEngine
      │
      ├── Broker
      │
      ├── ReconciliationEngine
      │
      └── Monitoring


# configuration
configuration/

    settings.py
    environments.py
    tradingconfig.py
    riskconfig.py
    brokerconfig.py
    modelconfig.py

# Trading system

trading_system/
│
├── core/
│   ├── types.py
│   ├── enums.py
│   ├── exceptions.py
│   ├── events.py
│   └── interfaces.py
│
├── configuration/
│   ├── settings.py
│   ├── environments.py
│   ├── tradingconfig.py
│   ├── riskconfig.py
│   ├── brokerconfig.py
│   └── modelconfig.py
│
├── data/
│   └── marketdata/
│
├── research/
│   ├── assetuniverse.py
│   ├── macroregime.py
│   ├── regimeforecastengine.py
│   ├── expectedreturnforecaster.py
│   ├── forecastmodels.py
│   └── ...
│
├── portfolio/
│
├── risk/
│
├── execution/
│
├── brokers/
│
├── persistence/
│
├── reconciliation/
│
├── recovery/
│
├── monitoring/
│
├── governance/
│
├── orchestration/
│
├── api/
│
├── dashboard/
│
├── deployment/
│
└── tests/


DATA
│
├── marketdataloader.py
├── validators.py
└── assetuniverse.py

REGIME / FORECAST
│
├── macroregime.py
├── regimeforecastengine.py
├── expectedreturnforecaster.py
├── forecastmodels.py
└── regimesimulation.py

RISK / COVARIANCE
│
├── covarianceengine.py
├── basecovariancemodel.py
├── regimecovariance.py
├── ensemblecovariance.py
├── factorcovariance.py
├── riskmodel.py
├── riskcontributionanalyzer.py
├── riskbudgetengine.py
├── volatilitytargeting.py
├── drawdownforecast.py
├── forwardriskmetrics.py
├── forwardriskanalyzer.py
└── scenarioengine.py

PORTFOLIO CONSTRUCTION
│
├── blacklitterman.py
├── constraints.py
├── portfoliooptimizer.py
├── portfoliodecisionengine.py
├── productioncomposition.py
└── regimeallocationpolicy.py

EXECUTION
│
├── order.py
├── orderstatus.py
├── orderbook.py
├── trade.py
├── tradegenerator.py
├── transactioncostmodel.py
├── executionengine.py
├── rebalanceengine.py
├── pretraderiskgate.py
├── oms.py
├── brokerrouter.py
├── paperbroker.py
├── brokerexecutionengine.py
├── livebroker.py
├── reconciliationengine.py
├── posttradeexecutionmonitor.py
└── executionanalytics.py

PRODUCTION ORCHESTRATION
│
├── productionintegration.py
├── productiondecisionexecution.py
├── productionexecutiongate.py
├── productionpipelineintegration.py
└── productionriskvalidation.py

ANALYTICS / REGRESSION
│
├── analytics.py
├── performanceattribution.py
├── tradeanalytics.py
├── quantitative_regression.py
├── regression_suite.py
├── step7_production_test.py
├── step8_historical_data_test.py
├── step9_historical_backtest.py
├── testsupport.py
└── test_phase_iv_d_production_gate.py

LEGACY / MONOLITHIC IMPLEMENTATION
│
└── rewrite.py

# RiskContributionAnalytics

σ²p = w'Σw

σp = √(w'Σw)

MRC = Σw / σp

RCi = wi × MRCi

RC_pct_i = RCi / σp

# RiskBudgetEngine

RiskBudgetEngine
├── __init__
├── _validate_configuration
├── _normalize_regime
├── get_target_budgets
├── optimize
├── calculate_risk_contributions
├── calculate_risk_contribution_pct
├── calculate_budget_errors
├── analyze
├── budget_vector
├── get_risk_budget
├── risk_budget
├── health_check
├── metadata
├── to_dict
└── reset

build_risk_budget_engine()

test_risk_budget_engine()

REGIME-SWITCHING SYSTEM
│
├── CORE PRODUCTION
│   ├── market data
│   ├── covariance
│   ├── forecasting
│   ├── regime detection
│   ├── risk budgets
│   ├── portfolio optimization
│   ├── decision engine
│   └── portfolio/account layer
│
├── PRODUCTION EXECUTION
│   ├── orders
│   ├── OMS
│   ├── execution
│   ├── brokers
│   ├── reconciliation
│   └── monitoring
│
├── REGRESSION / VALIDATION
│   ├── final_regression.py
│   ├── quantitative_regression.py
│   ├── regression_suite.py
│   ├── step7...
│   ├── step8...
│   ├── step9...
│   └── hardening tests
│
└── ARCHIVE
    ├── rewrite.py
    ├── archive/*
    └── historical snapshots