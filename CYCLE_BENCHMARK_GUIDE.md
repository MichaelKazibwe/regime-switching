# Cycle-balanced research benchmark — 14 November 2026

A separate benchmark for research comparisons. The owner selected balanced return, diversification and drawdown control. It does not replace client plans or existing reference portfolios.

## Selection and evaluation

The search compares three group risk budgets × three volatility ceilings (6%, 8%, 10%) × three drawdown-control designs, 27 declared combinations. Allocation estimation ends before a 252-session validation window; validation selects the design; the final 252-session test is evaluated separately. All history was already available when the design was proposed, so this is retrospective evidence rather than an untouched prospective test.

Objective: validation CAGR minus half annual variance, plus half the signed maximum drawdown, minus daily 95% expected shortfall. Asset capital is capped at 25%, gross invested exposure at 95%, satellites at 30%, with equity/government/real-asset/credit/alternative capital caps of 60/55/35/10/15%. Asset Euler shares and volatility are checked under normal, stress and observed covariance. No leverage or shorting.

The selected design is inflation_diversified-0.08-none. The 8% volatility figure is a ceiling, not a forecast target. The drawdown-overlay candidates reduce exposure based on prior-close drawdown, with a 25% exposure floor and monthly re-entry; they do not clip losses or guarantee a maximum decline. The selected design uses no overlay.

Frozen held-out result: return 3.22%, annual volatility 2.52%, maximum drawdown -1.69%; 15 bps modeled traded-notional costs and zero unverified account cash yield. Doubled-cost return: 3.11%.

## Latest separately refitted allocation

Market session 2026-11-12. Forecast volatility 1.87%; cash 51.11%. These current weights differ from the historical frozen test allocation; its performance must not be attributed to them. The high cash allocation makes this a conservative reference, not a fully invested growth benchmark.

| Asset | Capital | Signed risk share |
|---|---:|---:|
| USD_CASH | 51.11% | 0.00% |
| SGOV | 12.63% | 0.13% |
| SHY | 4.96% | 2.11% |
| DBC | 3.70% | 12.88% |
| TIP | 2.96% | 3.69% |
| TLT | 2.83% | 7.49% |
| DBMF | 2.77% | 4.99% |
| IEF | 2.74% | 4.41% |
| IGOV | 2.69% | 6.76% |
| HYG | 1.98% | 2.63% |
| GLD | 1.69% | 17.21% |
| LQD | 1.42% | 2.59% |
| XLU | 1.28% | 5.14% |
| XLP | 1.24% | 3.88% |
| VNQ | 1.16% | 5.14% |
| KIE | 1.02% | 2.65% |
| XLF | 0.89% | 2.98% |
| SPY | 0.88% | 3.66% |
| VWO | 0.52% | 2.63% |
| XLY | 0.45% | 2.25% |
| VEA | 0.40% | 2.42% |
| ITB | 0.23% | 1.89% |
| XLI | 0.20% | 1.01% |
| IWM | 0.18% | 1.03% |
| EWJ | 0.04% | 0.26% |
| QQQ | 0.03% | 0.17% |
| XLE | 0.00% | 0.00% |
| SLV | 0.00% | 0.00% |

## Business-cycle and regime stress

Eight 500-path one-year scenarios use joint, observed 21-session return blocks from training-only history: each of the four macro regimes, inflation into stagflation, recession into recovery, full-cycle switches and smoothed historical Markov switches. Transitions are fitted at a fixed 63-session horizon and never bridge unavailable periods. Missing conditional pools block the affected scenario. These are conditional assumptions, not calibrated market predictions.

| Scenario | Median return | Fifth-percentile return | 95th-percentile drawdown |
|---|---:|---:|---:|
| deflationary_slowdown | 2.73% | -0.72% | 2.74% |
| disinflationary_growth | 2.73% | -0.32% | 2.57% |
| full_cycle_switches | 2.67% | -0.67% | 3.06% |
| historical_markov_switches | 2.54% | -1.92% | 3.86% |
| inflation_shock_then_stagflation | 3.09% | 0.29% | 3.06% |
| inflationary_growth | 0.71% | -3.50% | 5.02% |
| recession_then_recovery | 3.11% | 0.13% | 2.48% |
| stagflation | 4.22% | 2.99% | 0.95% |

Three additional instantaneous group shocks cover growth recession, inflation/rates and liquidity/correlation stress. Results are before fees/tax and do not establish execution capacity. No predictive alpha was enabled.

Evidence: var/cycle-benchmark/20261114-balanced-v2/benchmark.json. CSV export: var/cycle-benchmark/20261114-balanced-v2/allocation-and-risk-weights.csv. The private pilot includes the Cycle benchmark section with all scenarios, group risk, shock results and JSON export. Independent accounting replay reconciles the historical curves. Country/FX look-through, cash yields, actual execution costs and independent investment validation remain unevidenced.
