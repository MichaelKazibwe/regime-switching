# Historical backtests and five-year simulations

The requested 50-year actual-model backtest is **unavailable**. These instruments did not exist throughout 1976–2026; no approved complete pre-inception proxy panel is present. No returns were fabricated. [SGOV issuer history](https://www.ishares.com/us/products/314116/sgov) dates its inception to May 2020. ETF coverage is recorded in `var/research/horizon-analysis/coverage.csv`. The machine-readable 50-year status retains null metrics for each model.

The longest 14-ETF exploratory allocator test spans **2008-07-28–2025-10-29**: CAGR **3.87%**, annualized volatility **6.05%**, maximum drawdown **-20.70%**. It uses actual prices with price-derived regime proxies, not the complete macro-driven production pipeline.

All-three-model comparison: **2022-06-01–2025-10-29**, 857 sessions, 15 bps costs per dollar of ETF trading, zero cash interest. The hybrid is selected chronologically from the existing 12 configurations. These development periods were previously inspected; there is no pristine out-of-sample or deployment-qualification claim.

| Model | CAGR | Annual volatility | Maximum drawdown | Final $1 million |
|---|---:|---:|---:|---:|
| 14 production allocator* | 9.26% | 8.61% | -10.28% | $1,351,434 |
| 26 diversified allocator* | 4.41% | 4.27% | -5.18% | $1,157,983 |
| Chronologically selected hybrid | 5.64% | 5.50% | -6.87% | $1,205,270 |

The forward nominal window is **2026-10-30–2031-10-30**, approximately 1,260 trading sessions. Calibration stops at **2025-10-29** to preserve the existing reserved dates beginning **2025-10-30**. These conditional projections deliberately do not use the latest reserved year and are not current-market predictions.

## Analytical five-year projection

Stationary independent Gaussian log-return extrapolation. The interval excludes drift-estimation uncertainty. Nominal USD, starting from $1 million.

| Model | Median | 5th percentile | 95th percentile | Median with half historical log drift |
|---|---:|---:|---:|---:|
| 14 production allocator* | $1,557,043 | $1,134,839 | $2,136,323 | $1,247,815 |
| 26 diversified allocator* | $1,240,675 | $1,060,314 | $1,451,717 | $1,113,856 |
| Chronologically selected hybrid | $1,315,872 | $1,074,775 | $1,611,052 | $1,147,115 |

For sensitivity, calibrating the 14-ETF projection to its longer 2008–2025 history instead produces a five-year median of **$1,209,125**. This difference demonstrates how strongly projections depend on the lookback and historical drift assumption.

## Five-year Monte Carlo

10,000 paired paths per model; seed 271828; circular 21-session return blocks, preserving within-block dependence and paired model relationships. Each path separately bootstraps an uncertain calibration mean and future centered return blocks. No allocators or trading decisions are rerun on simulated asset prices. Historical trading costs are already embedded; future turnover and cash rates are not separately forecast.

| Model | Median final $1m | 5th percentile | 95th percentile | Terminal-loss frequency | 95th-percentile drawdown magnitude |
|---|---:|---:|---:|---:|---:|
| 14 production allocator* | $1,566,238 | $971,733 | $2,507,071 | 6.25% | 22.38% |
| 26 diversified allocator* | $1,243,829 | $974,303 | $1,577,865 | 7.26% | 12.25% |
| Chronologically selected hybrid | $1,319,859 | $967,839 | $1,783,797 | 6.94% | 15.29% |

These are conditional simulated outcome percentiles and frequencies, not guaranteed forecasts, confidence intervals for expected returns, or actual probabilities of loss. They cannot include crises and structural changes absent from the short calibration sample. The hybrid remains a trade-off: its extended observed drawdown is larger and return smaller than in the earlier short test. No fixed maximum loss has been established.

All paths, 5/63-session block sensitivities, selection trials, historical decisions, source/data hashes and terminal output are retained in `var/research/horizon-analysis/`. No orders were submitted or production limits changed.

```sh
python3 stress_test_models.py --as-of 2026-10-30
# Refresh public history when authorized:
python3 stress_test_models.py --fetch --as-of 2026-10-30
```
