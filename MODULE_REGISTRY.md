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