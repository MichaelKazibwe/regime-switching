# Four macro-aware portfolio strategies

**Status: four implemented research challengers; no portfolio is certified optimal or accepted for production.**

User mandate remains **50% net cumulative return in three years, at most 5% account peak-to-trough decline**. 60 fresh three-calendar-year accounts were tested; joint successes: **0/60**. No order submission or activation occurred.

## The four strategies

| Strategy | Design | Expansion / recession response |
|---|---|---|
| Economic Balance | Diversified economic risk core with bounded predictive tilts | Moderate equity growth risk; more nominal bonds, inflation-linked bonds and gold in slowdowns |
| Defensive Growth | Larger expansion equity budget plus multi-horizon market trend confirmation | Equity risk expands with growth; slows sharply during contraction or crisis |
| Inflation Resilience | Explicit real-rate/inflation diversification | Reduces nominal duration risk when inflation rises; diversifies across TIP, gold and commodities |
| Tail-Aware Ensemble | Fixed equal blend of the preceding budget maps, market trend and prior realized tail feedback | Conservative forecast ES can reduce sizing; it cannot increase risk to improve returns |

All four use SPY/VEA/VWO, TLT/IEF/IGOV, TIP, GLD and DBC, with SHY/SGOV reserves after historical eligibility. These share overlapping economic risks: equal ETF counts or percentage variance budgets do not establish neutrality to equity, duration, inflation or currency factors. Direct futures, shorting and leverage are not implemented.

## Predeclared regime targets

The following are **requested sleeve variance budgets**, not capital weights or promised returns. Budget construction projects asset targets into a 24% risk envelope, leaving a buffer below the unchanged 25% whole-account contribution cap, then reconstructs explicit feasible sleeve budgets. If invested reserve cross-risk makes the strict solve infeasible, the same core is retried without an invested reserve; failure still rejects to cash and disqualifies the account. Actual reconciled targets are retained. Volatility ceilings are forecast limits, not realized loss bounds.

| Strategy | Economic state | Equity | Nominal bonds | TIP | Gold | Commodities | Annual vol ceiling |
|---|---|---:|---:|---:|---:|---:|---:|
| economic_balance | disinflationary_growth | 45.00% | 25.00% | 5.00% | 15.00% | 10.00% | 6.00% |
| economic_balance | inflationary_growth | 35.00% | 15.00% | 10.00% | 20.00% | 20.00% | 5.50% |
| economic_balance | stagflation | 15.00% | 20.00% | 20.00% | 22.50% | 22.50% | 4.00% |
| economic_balance | deflationary_slowdown | 20.00% | 40.00% | 10.00% | 20.00% | 10.00% | 3.50% |
| defensive_growth | disinflationary_growth | 70.00% | 15.00% | 2.50% | 7.50% | 5.00% | 10.00% |
| defensive_growth | inflationary_growth | 55.00% | 15.00% | 5.00% | 10.00% | 15.00% | 8.00% |
| defensive_growth | stagflation | 15.00% | 25.00% | 15.00% | 22.50% | 22.50% | 4.00% |
| defensive_growth | deflationary_slowdown | 15.00% | 45.00% | 10.00% | 20.00% | 10.00% | 3.00% |
| inflation_resilience | disinflationary_growth | 45.00% | 20.00% | 10.00% | 15.00% | 10.00% | 7.50% |
| inflation_resilience | inflationary_growth | 35.00% | 10.00% | 15.00% | 20.00% | 20.00% | 6.50% |
| inflation_resilience | stagflation | 10.00% | 20.00% | 22.00% | 24.00% | 24.00% | 4.00% |
| inflation_resilience | deflationary_slowdown | 15.00% | 40.00% | 15.00% | 20.00% | 10.00% | 3.50% |
| tail_aware_ensemble | disinflationary_growth | 53.33% | 20.00% | 5.83% | 12.50% | 8.33% | 8.00% |
| tail_aware_ensemble | inflationary_growth | 41.67% | 13.33% | 10.00% | 16.67% | 18.33% | 6.50% |
| tail_aware_ensemble | stagflation | 13.33% | 21.67% | 19.00% | 23.00% | 23.00% | 3.50% |
| tail_aware_ensemble | deflationary_slowdown | 16.67% | 41.67% | 11.67% | 20.00% | 10.00% | 3.00% |

Current quadrant weights and a bounded **20% forecast mixture** blend the state maps. During crisis, the stagflation/slowdown budget blend caps requested equity risk at 15%, limits invested capital to 40%, and applies at most 5% forecast annual volatility. A persistent account guard reduces allocation between 2% and 4% drawdown, latches to cash at 4%, and never resets the high-water mark. Gaps can exceed 5% before next-close execution.

## Macroeconomic prediction and risk calibration

Archived point-in-time industrial production, unemployment, CPI and Treasury yields are combined with market trend, breadth, volatility and a credit-relative proxy. A standardized, regularized multinomial logistic model forecasts the **derived economic quadrant 63 sessions ahead**. Each training label is strictly observable before the decision close; monthly refits use at most 1,260 training examples after a 504-example minimum. Economic states are rules derived from released conditions, not independently verified recession labels.

Model probabilities are shrunk 50% toward historical class frequencies. The model is used only after at least 12 matured prior forecasts outperform their contemporaneous frequency baselines on mean Brier score; otherwise allocation uses the frequency baseline. This is a point-in-time screening rule, not a calibration guarantee. Monthly 63-session outcomes overlap. NBER recession labels are retrospective reporting-only and never trading inputs.

Completed matured forecasts: **177**. Mean Brier scores: model **0.7452**, baseline **0.7459**, actually used **0.7585**; lower is better. Model enabled on **55.37%** of evaluated predictions. Reliability bins are retained; these probabilities must not be presented as calibrated recession or financial-loss probabilities.

Risk uses volatility-scale-preserving shrunk correlations, EWMA/long-window volatility and past-stress correlations. Prior-only filtered historical VaR/ES is scored against the next observed return before a new closing fill. Ensemble ES feedback is reduce-only, capped at 2x forecast scale. Exact conditional core risk attribution includes invested Treasury cross-risk; the 1e-6 gate, 25% capital/risk caps and paper-only boundary remain unchanged.

## Same-history net performance

Observed comparison: **2008-07-25–2025-10-29**. Modeled costs are 15bps of traded ETF notional; doubled-cost runs use 30bps. Cash earns zero; USD nominal returns are before investor taxes. Daily adjusted-close fills are a research proxy.

| Model | Role | Total return | CAGR | Annual volatility | Max drawdown | Rejected proposals |
|---|---|---:|---:|---:|---:|---:|
| economic_balance | MANDATE_CANDIDATE | -0.00% | -0.00% | 1.42% | -4.12% | 0 |
| economic_balance_no_guard | DIAGNOSTIC | 56.35% | 2.63% | 4.32% | -13.18% | 0 |
| economic_balance_double_cost | COST_SENSITIVITY | -3.76% | -0.22% | 0.40% | -4.02% | 0 |
| defensive_growth | MANDATE_CANDIDATE | 3.69% | 0.21% | 1.66% | -4.06% | 0 |
| defensive_growth_no_guard | DIAGNOSTIC | 64.01% | 2.91% | 4.76% | -12.93% | 0 |
| defensive_growth_double_cost | COST_SENSITIVITY | -3.93% | -0.23% | 0.56% | -4.01% | 0 |
| inflation_resilience | MANDATE_CANDIDATE | 1.45% | 0.08% | 1.51% | -4.09% | 0 |
| inflation_resilience_no_guard | DIAGNOSTIC | 59.57% | 2.75% | 4.43% | -13.99% | 0 |
| inflation_resilience_double_cost | COST_SENSITIVITY | -3.79% | -0.22% | 0.41% | -4.03% | 0 |
| tail_aware_ensemble | MANDATE_CANDIDATE | -1.93% | -0.11% | 1.45% | -4.08% | 0 |
| tail_aware_ensemble_no_guard | DIAGNOSTIC | 48.60% | 2.32% | 4.26% | -12.56% | 0 |
| tail_aware_ensemble_double_cost | COST_SENSITIVITY | -3.94% | -0.23% | 0.55% | -4.00% | 0 |
| v3 | BENCHMARK_ONLY | 64.09% | 2.92% | 4.31% | -10.73% | n/a |
| v4 | BENCHMARK_ONLY | 52.13% | 2.46% | 3.81% | -11.28% | n/a |
| all_weather_proxy | BENCHMARK_ONLY | 45.18% | 2.19% | 3.33% | -11.33% | n/a |
| strategic_50 | BENCHMARK_ONLY | 189.43% | 6.36% | 10.54% | -25.03% | n/a |
| strategic_70 | BENCHMARK_ONLY | 228.22% | 7.14% | 14.84% | -36.27% | n/a |

**Forecast validation finding:** the probabilities actually used score worse than the historical-frequency baseline. The point-in-time gate did not establish a reliable forecasting advantage. These forecasts are not validated alpha and cannot justify promotion.

### Fresh three-calendar-year accounts

| Strategy | Accounts | Median total return | Best total return | Worst drawdown | Joint goal successes |
|---|---:|---:|---:|---:|---:|
| economic_balance | 15 | 0.64% | 11.42% | -4.14% | 0 |
| defensive_growth | 15 | 1.99% | 11.31% | -4.13% | 0 |
| inflation_resilience | 15 | 1.43% | 10.08% | -4.10% | 0 |
| tail_aware_ensemble | 15 | 1.17% | 9.54% | -4.12% | 0 |

The four fixed designs were not retuned after observing performance. A feasibility correction projected concentrated asset budgets into the already declared caps and added the no-reserve retry; it did not change the return target, loss objective, risk tolerance or strategy maps. Pre-correction rejected-proposal evidence is preserved under `before-budget-feasibility-fix/`.

The `_no_guard` rows are fixed diagnostic twins without the account drawdown guard. They remain subject to crisis, position, volatility and exact risk-accounting controls, but are **not authorized alternatives** to the user mandate. Cash-heavy protected accounts must not be praised as successful crisis prediction merely because they stop participating.

## All Weather benchmarking

Bridgewater balances exposures to growth and inflation surprises. Our liquid unlevered proxy approximates this principle with five economic sleeves and is not an official Bridgewater allocation or private-fund return. [Bridgewater methodology](https://www.bridgewater.com/resources/all-weather-story.pdf).

Actual ALLW ETF overlap is short and uses a different derivative/exposure structure. These are descriptive results, not risk-matched proof of superiority. [Official ALLW information](https://www.ssga.com/us/en/intermediary/etfs/state-street-bridgewater-all-weather-etf-allw).

| Model | Overlap period return | Annual volatility | Max drawdown |
|---|---:|---:|---:|
| actual_ALLW | 14.64% | 13.17% | -8.78% |
| economic_balance_no_guard | 7.38% | 3.65% | -1.64% |
| defensive_growth_no_guard | 8.98% | 4.48% | -1.61% |
| inflation_resilience_no_guard | 7.59% | 3.66% | -1.56% |
| tail_aware_ensemble_no_guard | 7.67% | 3.82% | -1.59% |
| all_weather_proxy | 5.74% | 3.11% | -1.79% |

Actual ALLW overlap: **2025-03-07–2025-10-29**. Initial ALLW entry cost is modeled; the research accounts enter that comparison with existing holdings. The overlap does not establish superiority over Bridgewater at matched risk.

## Conditional three-year estimates

5,000 joint 21-session block-bootstrap paths include historical drift uncertainty and preserve shared sampled dates. The return streams are net diagnostic-twin returns, not simulated underlying markets; the account guard and allocations are not rerun on those paths. These are conditional development scenarios, not validated forward predictions or calibrated success probabilities.

| Stream | Median total return | 5th–95th percentile return | 95th-percentile drawdown magnitude | Joint 50%/5% frequency |
|---|---:|---:|---:|---:|
| economic_balance_no_guard | 8.23% | -5.37% to 23.50% | 12.17% | 0.00% |
| defensive_growth_no_guard | 9.21% | -5.53% to 25.70% | 12.78% | 0.04% |
| inflation_resilience_no_guard | 8.67% | -5.30% to 24.29% | 12.32% | 0.00% |
| tail_aware_ensemble_no_guard | 7.32% | -6.07% to 22.21% | 12.35% | 0.00% |
| all_weather_proxy | 6.82% | -4.10% to 18.42% | 9.81% | 0.00% |

One-year scenarios for each starting macro quadrant and market crisis are retained in `starting-regime-one-year-scenarios.csv`. They resample complete historical 21-session blocks, conditioned on the block-start state, including within-block transitions and drift uncertainty. Repeated sampling assumes similar starting-condition distributions over the horizon; it is not a structural macro transition forecast. Insufficient block counts are flagged. A sampled drawdown quantile is not a maximum possible loss.

## Historical reference weights and diversification

Reference proposals are fresh-account illustrations at the last historical decision close, before the owner account guard. They are **not current positions or buy instructions**. Actual continuous accounts may be cash-locked. Capital and whole-account risk weights are retained in `last-historical-reference-targets.csv`; exact reconciled budget fields remain in proposal JSON files.

| Strategy | Invested ETFs | Uninvested cash | Effective positive-risk positions | Forecast annual volatility |
|---|---:|---:|---:|---:|
| economic_balance | 10 | 5.00% | 7.85 | 5.08% |
| defensive_growth | 9 | 5.00% | 8.01 | 6.63% |
| inflation_resilience | 10 | 5.00% | 7.49 | 4.62% |
| tail_aware_ensemble | 10 | 5.00% | 8.13 | 5.83% |

**Strategy overlap:** historical diagnostic net-return correlations range from **0.975 to 0.994**. These designs share much of the same risk engine and asset universe. Dividing capital between them does not create four independent sources of returns. This is a material limitation to the proposed diversification; it prevents claiming institutional or All Weather superiority from strategy count alone.

Illustrative reference-target date: **2025-10-28T20:00:00+00:00**, with zero assumed prior account drawdown. All other catalogue assets receive zero weight. These are archived proposal illustrations, not current allocations.

| Asset | economic_balance | defensive_growth | inflation_resilience | tail_aware_ensemble |
|---|---:|---:|---:|---:|
| DBC | 10.21% | 10.16% | 9.30% | 10.00% |
| GLD | 7.00% | 7.07% | 6.45% | 7.64% |
| IEF | 14.59% | 20.00% | 11.15% | 16.13% |
| IGOV | 6.00% | 7.92% | 4.66% | 6.60% |
| SGOV | 17.62% | 0.00% | 22.05% | 6.58% |
| SPY | 4.94% | 8.25% | 4.31% | 6.25% |
| TIP | 20.26% | 18.52% | 24.99% | 24.21% |
| TLT | 4.85% | 6.47% | 3.71% | 5.33% |
| USD_CASH | 5.00% | 5.00% | 5.00% | 5.00% |
| VEA | 4.64% | 8.12% | 4.06% | 5.96% |
| VWO | 4.91% | 8.48% | 4.32% | 6.29% |

## Decision and remaining qualification

No design is declared an optimum. The mandate remains a joint return/preservation test; a higher return earned by violating the drawdown objective cannot qualify. Previous research included 36 inspected smart variants plus additional ablations/parent work; these four fixed designs add four more. There is no pristine out-of-sample claim. The universe and architecture were chosen retrospectively. The reserved boundary remains 2025-10-30.

Before promotion: independently validate economic labels, probability calibration and tails; review factor/duration/currency/liquidity exposures; replay actual executable prices; qualify the new risk contract and eligible instruments through production authorization; collect genuinely fresh observations; and obtain strategy/paper acceptance. Actual managed-futures benchmarking from earlier work remains a separate short-history illustration. Long-only trend is not a replication of diversified futures trend. [Trend research and limitations](https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing).

## Reproduction and evidence

```sh
python3 evaluate_four_macro_strategies.py
python3 report_four_macro_strategies.py
python3 -m pytest -q test_four_macro_strategies.py
python3 -m pytest -q
```

Frozen design: `research/four_macro_strategies.json`. Evidence: `var/research/four-macro-strategies-v6/` (ignored local artifacts requiring packaging for independent review). Includes full/doubled-cost accounts, 60 fresh accounts, allocation audits, forecast timestamps/training endpoints, Brier/reliability scores, regime/cycle attribution, stress episodes, reference weights, risk diagnostics, diversification, actual ALLW overlap, conditional scenarios and source checksums.

## Validation

Focused tests: **28 passed**. Full suite: **1,206 passed**. Ruff and diff checks pass. These are engineering checks, not investment qualification.
