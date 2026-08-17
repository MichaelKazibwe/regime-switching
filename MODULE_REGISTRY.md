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