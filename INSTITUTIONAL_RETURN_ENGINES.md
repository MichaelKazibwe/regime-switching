# Institutional-method return engines

Implemented and evaluated 31 October 2026. Four separately versioned, unapproved long-only challengers. Historical profitability improved; a superior or reliably profitable investment product has not been established. Existing paper strategies, client plans and cohorts remain unchanged.

## Public institutional research translated into engineering

| Public source | Implemented adaptation | Boundary |
|---|---|---|
| [Bridgewater/State Street All Weather](https://www.ssga.com/us/en/institutional/insights/the-all-weather-portfolio-built-for-any-forecast) | Growth/inflation diversification across global equities, nominal and inflation-linked bonds, gold and commodities; modest bounded macro tilts | Transparent anchors are our design, not Bridgewater weights. Realized macro data are not unexpected-growth/inflation forecasts. No proprietary All Weather replication is claimed. |
| [AQR time-series momentum](https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing) | 63/126/252-session excess trends against an actually observed reserve ETF; blended rather than one fast trading signal | Long-only reduction toward reserves/cash; no direct futures shorting or borrowing. Does not replicate a long/short CTA. |
| [Man AHL trend-speed and execution research](https://www.man.com/insights/need-for-speed-trend-following) | Multiple horizons, volatility scaling, prior-stress correlation estimates, and explicit transaction-cost sensitivity | ETF implementation and observed DBMF are distinct from AHL proprietary models and execution technology. Fund-level derivatives remain exposure metadata to verify. |
| [AQR strategic rebalancing](https://www.aqr.com/-/media/AQR/Documents/Insights/White-Papers/Portfolio-Rebalancing-Part-1-Strategic-Asset-Allocation.pdf) | Monthly scheduled decisions, a 4% gross-weight drift band, half rebalancing when feasible, full risk repairs when required | Our declared settings, not parameters copied from an institutional book or chosen by a profit grid search. |
| [Dimensional asset-allocation principles](https://www.dimensional.com/us-en/insights/dimensionals-approach-to-asset-allocation) | Regional diversification, explicit equity/bond trade-offs and cost discipline | Value, profitability and quality premiums were not fabricated from sector labels. Verified point-in-time fundamental data would be required to implement them. |

## Four distinct designs

| Engine | Main return mechanism | Normal forecast volatility ceiling |
|---|---|---:|
| Economic Balance | Diversified strategic market exposures, restrained trend tilts and economic balancing | 8% |
| Defensive Growth | Higher global equity participation, modest regional/industry momentum and defensive diversification | 12% |
| Inflation Resilience | Inflation-linked bonds, gold/commodities, energy exposure and limited nominal duration | 10% |
| Tail-Aware Ensemble | Conservative blend of the other anchors, additional managed futures/gold and prior-stress covariance control | 10% |

Forecast limits are sizing controls, not realized-volatility or drawdown guarantees. Target portfolios use 25% per-ETF and positive Euler contribution ceilings, group/satellite caps, no portfolio borrowing or shorting and at least 5% uninvested cash. Observed holdings can drift or gap past targets. Prior-close risk review triggers next-close repair above 26% single-ETF weight, 30% single-asset variance contribution, 110% of the forecast-volatility ceiling, or the exposure limit plus 1 percentage point. Group limits are enforced on proposed portfolios; these are not continuous-time guarantees. The ensemble is a declared anchor blend, not a fitted winner-selection model or purchased tail insurance. No fixed return target or 5% account drawdown lock exists.

The original 28-instrument menu is evaluated for observed eligibility; ALLW remains benchmark-only. Each tradable instrument needs 252 complete observed returns. Younger instruments receive zero weight until eligible. SGOV is used as an invested reserve only after sufficient actual history; otherwise eligible SHY is used. Reserve weights remain capped at 25%. Their observed ETF returns are not credited as deposit interest. Unverified uninvested cash interest remains zero.

Missing macro observations enter this separately declared market-only degraded design, capped at 65% invested capital and 7% forecast volatility. No missing macro value or vintage is manufactured, no old strict fail-closed policy is changed, and no revised retrospective data are treated as newly observed forecasts.

## Net historical results

2011-01-04 through 2026-10-30: 3,980 observed sessions. 15 bps on actual risky-asset dollars traded, solved on self-financing transactions; zero unverified cash interest. Inputs are the source-verified adjusted-price and release-aware feature captures. Existing positions earn each return before a target based strictly on the previous close fills. Risk-exit decisions and partial rebalances also use prior-close weights, avoiding same-close lookahead.

| Challenger | CAGR | Annual volatility | Max drawdown | Latest 252-session reset | Incumbent same period |
|---|---:|---:|---:|---:|---:|
| economic_balance | 4.48% | 6.18% | -12.86% | 5.31% | -1.43% |
| defensive_growth | 5.05% | 7.64% | -16.40% | 5.37% | -1.68% |
| inflation_resilience | 4.85% | 6.35% | -13.93% | 8.99% | -0.82% |
| tail_aware_ensemble | 4.75% | 5.73% | -11.89% | 7.90% | -1.68% |

The latest-year resets start new hypothetical accounts on 30 October 2025 with prior data available for the first next-close target, matching the incumbent evaluation period. They are reused historical comparisons, not untouched validation. No sequence of historical positives guarantees future profitability.

## Benchmark challenge

| Challenger | Risk-matched 60/40 CAGR | Positive lower bound of paired excess-return intervals? |
|---|---:|---|
| economic_balance | 5.54% | False |
| defensive_growth | 5.69% | False |
| inflation_resilience | 5.38% | False |
| tail_aware_ensemble | 4.74% | False |

None establishes robust incremental advantage over the matched reference. The reference uses the same trade dates and target forecast-risk budgets, covariance ending at the preceding decision close, the same costs and no borrowing. This is a descriptive diagnostic control, not an independent deployable reference. Intervals use both 21- and 63-session paired blocks and are not adjusted for the project’s broader selection history.

Unscaled 60/40 returned approximately 9.34% CAGR with 21.14% maximum drawdown; SPY approximately 13.92% / 33.72%; the transparent All Weather-style proxy approximately 6.45% / 23.56%. These have different risk exposures. Neither the proxy nor the ETF candidates represent institutional fund returns. The challengers trade lower participation and return for lower observed drawdowns.

## Costs, periods and regime checks

| Engine | Latest-year return at 0 bps | At 15 bps | At 30 bps |
|---|---:|---:|---:|
| economic_balance | 5.64% | 5.31% | 4.98% |
| defensive_growth | 5.72% | 5.37% | 5.01% |
| inflation_resilience | 9.41% | 8.99% | 8.58% |
| tail_aware_ensemble | 8.29% | 7.90% | 7.51% |

Costs are adaptive reruns using the fixed declared policy, not a calibration to a cheaper assumed account. Actual spreads, taxes, platform charges, capacity and investor cash economics are unverified. Fee-sensitive partial rebalance decisions are recalculated within each rerun.

Five chronological reporting windows cover 2011–2015, 2016–2019, 2020–2022, 2023–2024 and 2025–2026. Separate episode diagnostics cover the 2011 debt shock, 2018 tightening, the COVID crash/recovery and 2022 inflation. All were examined after data existed; rolling prior-data execution does not turn a design made in 2026 into a pre-registered historical strategy. Non-contiguous macro-regime means are descriptive observations, not tradable regime CAGRs.

## Project integration and forward evidence

- Core: `institutional_return_engines.py`; evaluation: `evaluate_institutional_engines.py`; independent reconciliation and risk matching: `assess_return_engine_robustness.py`.
- Frozen protocol, CSVs, trades, costs and period metrics: `var/institutional-return-engines/v1-validated/`. The aborted timing diagnostic is explicitly archived and unpublished.
- Dashboard: **Return engines**, a separate unapproved section with four selectors, period results, cost sensitivities, risk-matched comparisons, stress episodes and full menu allocation/risk shares.
- Forward cohort: `var/return-engine-shadow-v1/prospective.sqlite3`. Four versioned `institutional_v1_*` identities; one actual registration, zero forward-return sessions, first hypothetical fill due 2 November 2026. Existing cohorts were preserved.
- Cycle: `run_return_engine_cycle.py`. Locks concurrent runs, requires a fresh source-matched bundle, reuses same-input evaluation, rejects changed frozen code, publishes unapproved evidence and registers only future fills. No scheduler was installed and no host was provisioned.

```sh
# After the normal market/macro refresh has produced a fresh verified bundle:
python3 run_return_engine_cycle.py
# To perform a separately named immutable historical evaluation:
python3 evaluate_institutional_engines.py --output var/institutional-return-engines/NEW_RUN_DIRECTORY
```

Missing account cash, execution costs, access eligibility, duration/FX holdings, public jurisdiction review, independent economics review and host qualification remain blocked. No orders, emails, live deployment, automatic model promotion or institution affiliation was created.

## Validation

New tests cover incomplete pre-inception histories, explicit degraded operation, concentration and risk controls, future macro rejection, invariance to future prices, delayed risk exits after a price gap and immutable forward-only challenger registration. Independent replay reconciled all four complete net-return paths. **1,351 tests passed** in the full regression. Ruff passed; dashboard JavaScript parsed in native JavaScriptCore. The artifact seal and four challenger evidence records were checked, and both Docker manifests have no missing local Python imports. Docker images were not built. Native Safari preview was unavailable (`cgWindowNotFound`), so the new tab has static/script checks but no completed visual browser review. Results are recorded in `var/institutional-return-engines/regression.xml`.

The next decision is prospective evaluation against both the incumbents and simple references, not another search for the best historical winner.
