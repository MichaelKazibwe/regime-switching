# Diversified regime portfolio

> **Universe policy update (2026-11-17):** Current portfolios and strategies resolve a configurable global instrument registry, with no fixed ETF-count limit. Numeric universe counts below describe this document's historical implementation or experiment. See [the current global-universe policy](GLOBAL_ASSET_UNIVERSE.md).

Status: implemented research candidate; not activated in the paper worker. USD capital, long-only ETFs, no capital borrowing. The four economic regimes below are a separate research taxonomy from the production bull/neutral/crisis states.

A combined return/drawdown research candidate now uses this allocator alongside the 14-ETF production allocator. Its daily risk controls, chronological parameter selection and common-date comparison are documented in [HYBRID_PORTFOLIO_MODEL.md](HYBRID_PORTFOLIO_MODEL.md). The hybrid is a separate research strategy requiring its own account risk-budget acceptance.

## Investment approach

Bridgewater's contribution is diversification across assets with different growth and inflation sensitivities, assessed through covariance and contributions to portfolio variance. Its [All Weather explanation](https://www.bridgewater.com/resources/all-weather-story.pdf) concerns economic surprises relative to expectations; this first implementation uses caller-supplied standardized growth/inflation direction signals and must not be described as a complete economic-surprise model.

Berkshire's contribution is ownership of productive businesses, capital discipline and deliberate liquidity, as discussed in its [2025 annual report](https://www.berkshirehathaway.com/2025ar/2025ar.pdf). Broad equity ETFs provide diversified business exposure here. They do not reproduce Berkshire's company selection, valuation discipline, operating businesses or insurance economics. These weights are our research assumptions, not either firm's recommendations or holdings.

## Integrated company asset-diversity list

The machine-readable catalogue is [`research/company_asset_diversity.json`](research/company_asset_diversity.json), reviewed **30 October 2026**. It is loaded and validated by `DiversifiedRegimePolicy`; every allocation now includes an `asset_diversity_coverage` list. Generated allocation reports embed the source catalogue and its SHA-256 hash. The catalogue describes selected public exposures, not complete or real-time holdings. Bridgewater's private funds cannot be reconstructed from the public All Weather product or US equity filings alone.

Bridgewater's public All Weather model covers global equities, nominal and inflation-linked government bonds and commodities; its historical framework also discusses gold. The table maps these classes to this project's instruments. These mappings are our implementation choices. Sources: [public model](https://www.ssga.com/us/en/intermediary/etfs/state-street-bridgewater-all-weather-etf-allw), [All Weather framework](https://www.bridgewater.com/resources/all-weather-story.pdf).

| Bridgewater exposure | Expanded research proxy | Coverage |
|---|---|---|
| US equities | SPY, QQQ, IWM | Asset-class proxy |
| Developed international equities | VEA | Asset-class proxy |
| Emerging-market equities | VWO | Asset-class proxy |
| US nominal government bonds | TLT, IEF, SHY, SGOV | Asset-class proxy; SGOV is Treasury-bill exposure |
| Non-US nominal government bonds | IGOV | Developed-market sovereign and unhedged currency exposure |
| Inflation-linked government bonds | TIP | US inflation-linked bond proxy; real-yield duration remains |
| Gold | GLD | Asset-class proxy |
| Broad commodities | DBC | Asset-class proxy |

Berkshire's diversity includes listed investments, liquidity and owned businesses. Listed-stock examples below were disclosed in the **2025 annual report**, not verified as current positions. Subsidiary examples come from its official directory. Sources: [2025 annual report](https://www.berkshirehathaway.com/2025ar/2025ar.pdf), [subsidiary directory](https://www.berkshirehathaway.com/subs/sublinks.html).

| Berkshire exposure | Disclosed examples | Expanded research mapping |
|---|---|---|
| Liquidity and Treasury bills | Cash, US Treasury bills | USD cash and SGOV; cash and Treasury-bill ETF remain distinct |
| Fixed-maturity investments | Fixed-income securities | IEF/LQD are partial proxies; LQD currently unallocated |
| Technology | Apple (AAPL) | SPY/QQQ, broad equity only |
| Financial services | American Express (AXP), Bank of America (BAC), Moody's (MCO) | XLF, financial sector equity |
| Consumer brands | Coca-Cola (KO) | XLP, consumer staples equity |
| Energy producers | Chevron (CVX), Occidental (OXY) | XLE, energy equity; DBC remains separate commodity exposure |
| Insurance and reinsurance | GEICO, General Re, National Indemnity | KIE, listed insurance equity; no access to Berkshire float |
| Rail transport | BNSF | XLI, industrial equity; not a dedicated railroad basket |
| Utilities and energy infrastructure | Berkshire Hathaway Energy | XLU, utility sector equity |
| Industrial manufacturing | Precision Castparts, Marmon, Lubrizol | XLI, industrial sector equity |
| Housing and building products | Clayton Homes, Shaw, Benjamin Moore | ITB, home construction equity; VNQ remains distinct |
| Retail, distribution and services | McLane, NetJets, Dairy Queen | XLY, consumer discretionary equity; partial services proxy |
| Japanese trading houses | Mitsubishi, ITOCHU, Mitsui, Marubeni, Sumitomo | EWJ, broad Japan equity; not the five trading houses |

These mappings provide asset-class, sector or broad regional exposure; they do not reproduce Berkshire's private businesses, company valuations or insurance float. Sector funds overlap SPY and each other, and EWJ overlaps VEA. Covariance is estimated jointly across all instruments; sector mappings must never be added up as independent capital or used to infer constituent holdings.

The expanded profile adds **TIP, IGOV, SGOV, XLF, XLP, XLE, XLU, XLI, KIE, ITB, EWJ and XLY**. Mandates were checked against [TIP](https://www.ishares.com/us/products/239467/ishares-tips-bond-etf), [IGOV](https://www.ishares.com/us/products/239830/ishares-international-treasury-bond-etf), [SGOV](https://www.ishares.com/us/products/314116/sgov), the [sector ETF lineup](https://www.ssga.com/us/en/intermediary/capabilities/equities/sector-investing/select-sector-etfs), [KIE](https://www.ssga.com/us/en/intermediary/etfs/state-street-spdr-sp-insurance-etf-kie), [ITB](https://www.ishares.com/us/products/239512/ishares-us-home-construction-etf) and the [Japan index/linked EWJ listing](https://www.msci.com/indexes/index/939200/msci-japan-index). TIP is now enabled in research, replacing its former watchlist status. USD listing does not hedge IGOV or EWJ's underlying currency exposure.

`canonical_proxies` and `mapping` describe the existing production profile. Optional `research_proxies` and `research_mapping` describe the expanded profile. The catalogue retains production gaps explicitly. Coverage statuses distinguish `allocated_proxy`, `available_unallocated` and `missing`; the allocation's `universe_profile` identifies which mappings apply. All 12 additions have research eligibility only, not execution approval.

## Assets and risk allocation

`AssetUniverse.production()` retains the established 14-ETF paper universe. `AssetUniverse.diversified()` provides the 26-ETF research universe, using the same 14 in canonical order followed by the 12 additions. `DIVERSIFIED_ASSETS` is the authoritative ordered research vector; `AssetUniverse.tickers` remains sorted for the existing generic API. The regime policy selects `universe_profile: diversified_research` and uses the authoritative vector for prices, covariance and weights. Paper configuration continues to reject an expanded universe until production qualification.

The equity basket's internal capital split is SPY 35%, QQQ 3%, IWM 2%, VEA 12%, VWO 8%, EWJ 5%, XLF 5%, KIE 4%, XLP 6%, XLE 4%, XLU 4%, XLI 6%, ITB 2% and XLY 4%. These are research assumptions within the equity sleeve, not total portfolio weights or optimized allocations. LQD, HYG, SLV and VNQ remain available but unallocated initially.

| Economic regime | Equity risk | Government-bond risk | Inflation-sensitive risk | Minimum cash | Estimated annual volatility ceiling |
|---|---:|---:|---:|---:|---:|
| Growth rising, inflation falling | 50% | 30% | 20% | 5% | 12% |
| Growth rising, inflation rising | 40% | 15% | 45% | 10% | 10% |
| Growth falling, inflation rising | 20% | 25% | 55% | 25% | 7% |
| Growth falling, inflation falling | 15% | 55% | 30% | 25% | 6% |

Risk percentages are shares of estimated portfolio variance, not invested dollars. The solver calculates capital weights for the three baskets, then scales the complete portfolio down to satisfy the cash floor, 25% maximum per ETF and volatility ceiling. It never scales up through borrowing. Scaling preserves relative risk contributions; any error above 0.000001 rejects the allocation. Estimated volatility ceilings cannot guarantee future realized volatility or limit losses during gaps.

The government-bond basket includes TLT/IEF/SHY/IGOV/SGOV. Their capital splits are 20/35/15/15/15, 5/15/15/10/55, 0/10/15/10/65 and 30/30/10/20/10 percent in the table's regime order. The inflation-sensitive basket contains GLD/DBC/TIP at 45/15/40, 30/40/30, 35/30/35 and 50/0/50 percent. TIP belongs to the inflation-sensitive risk group, not the nominal-government group; it remains exposed to changes in real yields. SGOV is invested ETF exposure and counts toward the position and stress exposure limits; it does not count toward uninvested cash.

## Example capital allocations from observed prices

Yahoo Finance adjusted daily prices through the completed NYSE session on **29 October 2026**, using the most recent 756 daily returns and annualized Ledoit-Wolf covariance. These are four conditional allocations using the same covariance snapshot, not a declaration of the current economic regime. Values below are percentages of total capital, rounded to two decimals; rounding can change column totals slightly.

| Asset | Growth ↑ inflation ↓ | Growth ↑ inflation ↑ | Growth ↓ inflation ↑ | Growth ↓ inflation ↓ |
|---|---:|---:|---:|---:|
| SPY | 10.41 | 6.43 | 2.18 | 3.77 |
| QQQ | 0.89 | 0.55 | 0.19 | 0.32 |
| IWM | 0.60 | 0.37 | 0.12 | 0.22 |
| VEA | 3.57 | 2.20 | 0.75 | 1.29 |
| VWO | 2.38 | 1.47 | 0.50 | 0.86 |
| TLT | 9.45 | 2.27 | 0.00 | 13.82 |
| IEF | 16.54 | 6.82 | 3.85 | 13.82 |
| SHY | 7.09 | 6.82 | 5.77 | 4.61 |
| LQD | 0.00 | 0.00 | 0.00 | 0.00 |
| HYG | 0.00 | 0.00 | 0.00 | 0.00 |
| GLD | 8.10 | 7.25 | 5.20 | 9.08 |
| SLV | 0.00 | 0.00 | 0.00 | 0.00 |
| DBC | 2.70 | 9.67 | 4.45 | 0.00 |
| VNQ | 0.00 | 0.00 | 0.00 | 0.00 |
| TIP | 7.20 | 7.25 | 5.20 | 9.08 |
| IGOV | 7.09 | 4.55 | 3.85 | 9.21 |
| SGOV | 7.09 | 25.00 | 25.00 | 4.61 |
| XLF | 1.49 | 0.92 | 0.31 | 0.54 |
| XLP | 1.79 | 1.10 | 0.37 | 0.65 |
| XLE | 1.19 | 0.73 | 0.25 | 0.43 |
| XLU | 1.19 | 0.73 | 0.25 | 0.43 |
| XLI | 1.79 | 1.10 | 0.37 | 0.65 |
| KIE | 1.19 | 0.73 | 0.25 | 0.43 |
| ITB | 0.60 | 0.37 | 0.12 | 0.22 |
| EWJ | 1.49 | 0.92 | 0.31 | 0.54 |
| XLY | 1.19 | 0.73 | 0.25 | 0.43 |
| Uninvested USD cash | 5.00 | 12.01 | 40.47 | 25.00 |
| Estimated annual volatility | 6.26 | 4.42 | 2.36 | 5.08 |

Cash and SGOV are separate: ETF exposure retains market and execution risk. Cash is assigned zero market-price variance in this model, not zero inflation or currency risk. Treasury-bill ETF concentration can bind and increase uninvested cash; cash is never relabelled as SGOV to bypass a reserve. Cash interest, ETF fees, spreads, slippage and turnover must be treated appropriately in return analysis. No return improvement is claimed from these estimates.

Expanded evidence is generated under `var/research/diversified-regime-expanded/`: `observed-prices.csv`, `annual-covariance.csv`, `weights.csv` and `allocations.json`. The report includes the exact ordered universe, profile, timestamps, price/configuration/catalogue hashes and all eight normal/stress allocations. Earlier 14-ETF snapshots under `var/research/diversified-regime/` and `var/research/diversified-regime-catalog/` are historical research outputs; their weights do not describe the expanded configuration. Public adjusted histories may be revised and are not historical point-in-time archives. Retain dated copies when comparing experiments.

## Switching and stress rules

`classify()` accepts standardized growth/inflation signals and the timestamp at which those observations became available. Future observations are rejected. A ±0.1 deadband retains each axis of the prior regime; ambiguous initial signals reject classification. Feed construction, maximum signal age and scale calibration remain acceptance work, not implemented automatic macro ingestion in this module.

`stress_state()` enters stress when the supplied drawdown is at least 10% or annualized volatility is at least 25%. It exits only when drawdown improves beyond -7% and volatility falls below 20%. For the first backtest, predeclare SPY's trailing 252-session peak drawdown and trailing 20-session annualized daily volatility as these inputs, calculated from completed sessions. The function itself accepts observations; it does not fetch or persist them.

Stress is an overlay on every economic regime: at most 40% invested ETF exposure, at least 60% cash, and a 5% estimated volatility ceiling. It scales down the selected economic allocation and preserves its risk budgets. It is a liquidity defence, not a guarantee against drawdowns. Decisions should be calculated after a completed session and executed in a later eligible session; the session close used for a signal is not an executable same-close fill.

## Implementation and reproducibility

- `research/diversified_regime_portfolio.json`: explicit four-regime basket weights, risk budgets and limits.
- `research/company_asset_diversity.json`: sourced production/research proxy mappings, remaining replication gaps and research instrument eligibility.
- `assetuniverse.py`: canonical production metadata and expanded research factory; `core_constants.py` imports both ordered lists rather than maintaining another production ticker list.
- `constraints.py`: preserves an existing cash reserve when invested weights total less than 100%; it no longer normalizes that reserve away. Position caps still apply. Portfolio domain integration uses dictionary weights and covariance reordered to `universe.tickers` so the sorted generic API cannot silently permute the canonical research vector.
- `diversifiedregimepolicy.py`: validated policy, signal classifier, stress hysteresis, covariance estimator and positive group risk-budget solver. No order authorization or routing.
- `test_diversifiedregimepolicy.py`: constraints across regimes/stress states, adverse correlations, timing, missing sessions, invalid configuration and stress boundaries.

```sh
python3 -m diversifiedregimepolicy --fetch
python3 -m diversifiedregimepolicy --prices-csv path/to/adjusted-prices.csv --output var/research/my-run
python3 -m pytest -q test_diversifiedregimepolicy.py
```

Input CSV columns must match `DIVERSIFIED_ASSETS` exactly: `SPY,QQQ,IWM,VEA,VWO,TLT,IEF,SHY,LQD,HYG,GLD,SLV,DBC,VNQ,TIP,IGOV,SGOV,XLF,XLP,XLE,XLU,XLI,KIE,ITB,EWJ,XLY`. Earlier 14-column CSVs are rejected for this profile. Daily session dates must be unique, complete and ordered; prices must be finite and positive and end at the latest completed NYSE session. At least 252 daily return observations are required. The estimator uses at most 756 returns. There is no forward-filling of missing observations.

## Required before paper activation

1. Specify and implement point-in-time growth/inflation feeds using release availability and historical vintages; predeclare signal construction, scale, staleness limits and the stress benchmark/lookbacks. Persist prior regime/stress state and test restart behaviour. Reject unavailable/stale inputs through the existing fail-closed path.
2. Backtest with rolling past-only covariance, release-time macro data, next-session execution, cash returns, spreads, slippage, turnover and rebalance thresholds. Compare against the current strategy, a simple 60/40 benchmark and a fixed diversified baseline over identical dates. The full profile cannot be replayed through 2008 with actual ETF prices: SGOV began in 2020. Test recent periods after sufficient training history; use explicitly separate, predeclared benchmark/proxy studies for earlier crises, never fabricated ETF returns.
3. Freeze parameters before evaluating an untouched holdout. Measure net returns, maximum drawdown, expected shortfall, Sharpe/Sortino, turnover, regime transitions and concentration. Check sensitivity to budgets, windows, transaction costs and correlation shocks. Thresholds above are research choices, not accepted optima.
4. Design the explicit relationship between these four economic states and production bull/neutral/crisis controls. Carry a single approved set of risk budgets through optimizer, authorization and execution; never bypass the existing exact-budget or crisis gates. Validate integration with all safety and reconciliation checks.
5. Obtain strategy acceptance, then add persisted signals and candidate telemetry to the dashboard, reports and paper observation process. Complete the existing deployment qualification and operator checks before enabling orders. This research implementation does not itself qualify the service for deployment.
