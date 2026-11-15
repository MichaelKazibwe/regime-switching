# All Weather-informed macro portfolio refinement

**Subsequent owner-mandate study:** [THREE_YEAR_GOAL_ROADMAP.md](THREE_YEAR_GOAL_ROADMAP.md) and [THREE_YEAR_GOAL_ASSESSMENT.md](THREE_YEAR_GOAL_ASSESSMENT.md) execute the specified 50%-over-three-years / 5%-drawdown research screen. Twelve growth candidates and 180 fresh accounts fail the combined objective; production promotion remains closed. The V4 results below are preserved.

**Decision: implementation complete as a research challenger; do not replace V3 or activate it for paper trading.** The bounded refinement improves volatility and several stress episodes, but does not jointly improve long-history return, maximum drawdown and estimated loss frequency. It therefore does not meet the requested performance objective or establish institutional qualification. No production settings or execution modules were changed.

## Framework and benchmark

Bridgewater’s All Weather framework balances exposures to economic surprises in growth and inflation. Our implementation applies that diversification principle using liquid ETFs; equal asset-sleeve risk is an approximation, not a replication of Bridgewater’s economic sensitivity model. Industrial production, unemployment, CPI and the yield curve describe released conditions; they do not directly measure surprises relative to market expectations. [Bridgewater, The All Weather Story](https://www.bridgewater.com/resources/all-weather-story.pdf).

Two benchmarks are retained:

1. A long-history **All Weather-inspired proxy**, targeting 20% core risk each in global equities, nominal government bonds, inflation-linked bonds, gold and commodities. It shares the candidate’s unlevered limits, risk estimation, Treasury reserve and crisis/drawdown controls, with no tactical macro or equity trend tilt. Its controls make it a deliberately constrained comparator, not a passive All Weather fund or an official allocation.
2. **Actual ALLW ETF adjusted-close returns** over its available pre-reserved overlap, March–October 2025. Its derivative exposures and risk level differ materially from this long-only ETF candidate; the comparison is descriptive and not risk matched. It does not provide decades of actual All Weather fund returns. [State Street ALLW fund information and risks](https://www.ssga.com/us/en/intermediary/etfs/state-street-bridgewater-all-weather-etf-allw).

Volatility management and trend are researched techniques, not a universal recipe for superior results. Evidence on volatility-managed portfolios includes disappointing implementable out-of-sample comparisons. We test these controls rather than assuming that institutional usage proves alpha. [Cederburg, O’Doherty, Wang and Yan, 2020](https://www.lehigh.edu/~xuy219/research/COWY.pdf).

## Implemented changes

| Component | Implementation and purpose |
|---|---|
| Economic core | SPY/VEA/VWO equities; TLT/IEF/IGOV nominal bonds; TIP; GLD; DBC. Instruments need 252 complete actual returns before eligibility. |
| Bounded views | Compare balanced and growth-balanced risk anchors, 0% or 25% macro-view blending, and a modest equity trend reduction. Bound single-instrument sleeve budgets before the risk solve. |
| Risk estimate | Ledoit–Wolf shrinkage on standardized correlations, restored instrument volatility scales, maximum of long-window and EWMA volatility, and a 25% past-stress correlation mixture when enough past stressed observations exist. |
| Forecast feedback | Prior-close portfolio risk forecasts are paired with subsequent gross returns before new closing fills. A 63-session EWMA correction is reduce-only and capped at 2; this is a prudential overlay, not proof of statistical calibration. |
| Treasury reserve | SGOV after 252 actual returns, otherwise SHY; up to 25% capital. These are invested assets with price, duration and cross-covariance risk. Truly uninvested cash earns zero in this experiment. |
| Risk accounting | Solve core Euler contributions including reserve cross-risk. Reconcile relative core contributions to declared budgets within **1e-6**; separately report whole-account contributions and reserve capital. Never normalize away reserve risk. |
| Position and risk limits | At most 25% capital and 25% estimated positive whole-account variance contribution per asset; at least 5% cash. Stress exposure is at most 40%, hence at least 60% cash. Volatility, empirical ES95 and rolling drawdown controls can reduce exposure. |
| Trading | Monthly routine review, a 4% total-weight trade band, and daily forecast-risk breach checks. Decisions fill at the following close; the old holdings earn the intervening return. Model costs are 15 basis points of traded notional; selection uses 30 basis points. |
| Model selection | Freeze eight variants. Use the preceding 756 sessions, select every 252 sessions, maximize doubled-cost training CAGR subject to observed training drawdown ≤8% and annual volatility ≤5%. If none qualifies, use the frozen proxy parameters. These are research screening limits, not signed deployment acceptance thresholds. |
| Evidence | Whole-account attribution, forecast coverage and clustering diagnostics, macro/reserve ablations, six stress episodes, NBER cycle reporting, paired block-bootstrap uncertainty, and joint one-year simulation. |

Risk budgeting allocates estimated variance, not expected return or loss probability. Negative Euler contributions can reflect hedging; they are retained explicitly. The new **conditional core plus reserve contract** differs from V3’s full-account asset budget contract. It cannot inherit production authorization. Risk limits constrain forecasts and proposed trades; market gaps, covariance errors and next-close execution can breach realized limits.

## Historical results

Actual ETF history, **2008-07-28 to 2025-10-29**, net of modeled costs. No pre-inception ETF prices are manufactured. The first GFC segment is partial.

| Model | CAGR | Annual volatility | Maximum drawdown |
|---|---:|---:|---:|
| Prior macro V3 | 2.92% | 4.31% | −10.73% |
| Refined V4 | 2.46% | 3.81% | −11.28% |
| All Weather-inspired proxy | 2.19% | 3.33% | −11.33% |
| V4, doubled costs | 2.13% | 3.81% | −12.32% |
| V4, macro tilt disabled | 2.43% | 3.79% | −11.28% |
| V4, reserve disabled | 2.31% | 3.80% | −10.87% |

V4 gives up approximately 0.46 percentage points of CAGR for 0.50 points less annual volatility relative to V3. Its worst drawdown is 0.55 points deeper. It exceeds the constrained proxy’s CAGR, but has higher volatility and almost the same drawdown. Macro tilts contribute little; the last chronological selection chose **zero macro-view weight**, a growth-balanced anchor and a 6% forecast volatility ceiling. This does not establish useful macro forecasting alpha.

The Treasury reserve improves modeled returns but worsens drawdown relative to the no-reserve ablation. SHY before SGOV eligibility is not a risk-free cash substitute. Annual traded notional remains about **2.36 times account value**, despite monthly routine review: daily limit breaches still create turnover. Doubling costs cuts CAGR by approximately 0.33 points and changes the realized path of drawdown controls.

From **2022-06-01 to 2025-10-29**, V4 achieves 4.58% CAGR, 3.78% volatility and −5.49% drawdown, versus V3’s 4.32%, 4.73% and −4.99%. The improvement in recent return and volatility comes with a deeper drawdown. After the first training window, CAGR is 2.28% for V4 versus 2.56% for V3; chronological selection does not remove retrospective design bias.

Selected episode results are **period returns / drawdown within that episode**, not annualized returns:

| Episode | V4 | V3 | Inspired proxy |
|---|---:|---:|---:|
| Partial GFC, Jul 2008–Jun 2009 | −2.74% / −5.68% | −2.05% / −5.51% | −2.82% / −5.83% |
| Euro debt, 2011 | +4.97% / −1.84% | +6.11% / −1.53% | +5.35% / −1.81% |
| China/commodity slowdown, 2015–Feb 2016 | −4.66% / −8.51% | −4.81% / −8.76% | −3.99% / −7.44% |
| 2018 selloff | −2.18% / −5.03% | −5.05% / −8.09% | −2.14% / −4.83% |
| COVID shock, Feb 19–Mar 23, 2020 | −4.76% / −6.26% | −5.40% / −7.09% | −4.31% / −5.75% |
| Inflation/rate shock, 2022 | −6.27% / −8.28% | −8.12% / −10.34% | −4.97% / −6.85% |

Actual ALLW overlap, **2025-03-07 to 2025-10-29**:

| Model | Period return | Annualized volatility | Maximum drawdown |
|---|---:|---:|---:|
| Actual ALLW, including modeled entry cost | +14.64% | 13.17% | −8.78% |
| V4 | +7.05% | 3.63% | −1.70% |
| V3 | +8.32% | 4.43% | −1.52% |
| Inspired proxy | +5.74% | 3.11% | −1.79% |

The overlap is short and was **not used to select the candidate**. Existing candidates enter the overlap with established holdings; ALLW includes a modeled initial entry charge. Fund expenses are embedded in its adjusted prices. This comparison does not show that V4 outperforms All Weather at matched risk.

The last historical target, decided **2025-10-23** and simulated at the **2025-10-24** close, illustrates the difference between capital and risk weights. It is not a current allocation or a deployment instruction.

| Asset | Capital weight | Estimated whole-account variance share |
|---|---:|---:|
| SPY | 11.28% | 24.01% |
| VEA | 4.94% | 10.00% |
| VWO | 3.23% | 6.00% |
| TLT | 5.89% | 6.00% |
| IEF | 18.24% | 8.00% |
| IGOV | 7.18% | 6.00% |
| TIP | 12.00% | 5.00% |
| GLD | 8.84% | 20.00% |
| DBC | 10.61% | 15.00% |
| SGOV reserve | 12.79% | −0.02% |
| Uninvested USD cash | 5.00% | 0.00% under this model |

Rounded percentages may differ from totals. SGOV's small negative contribution reflects estimated diversification cross-risk, not a guarantee of safety. Other catalogue instruments receive zero weight. Expanding the candidate list does not require allocating to every ETF.

## Calibration and uncertainty gates

Across 4,342 nonzero forecast outcomes, raw normal-model daily VaR95 exceptions occur on **4.38%** of days; the EWMA-adjusted model has **3.75%**, against nominal 5%. The adjusted unconditional coverage p-value is approximately **0.000084**, rejecting nominal coverage through excessive conservatism. Realized-to-forecast volatility is about **0.90** after adjustment. Conservative sizing is a deliberate safety preference, but the result must not be described as accurately calibrated VaR. Conditional coverage and exception transitions are retained in the machine-readable audit; normal tails and independent exceptions cannot be assumed.

Exception clustering is also material: the Christoffersen independence p-values are approximately **0.00000060 raw** and **0.000000026 adjusted**. Conditional coverage is rejected for both forecasts. This is an unresolved model-validation finding, even though the overall exception rate looks conservative. The largest core-budget reconciliation error is **1.21e-9**, comfortably within the unchanged **1e-6** engineering tolerance; exact risk accounting does not cure forecast model misspecification.

The 2,000 paired 21-session block-bootstrap resamples put the development CAGR difference **V4 minus V3** between approximately **−1.19 and +0.33 percentage points** at 95%. This interval is conditional on the historical return streams and is not adjusted for strategy selection or multiple research iterations.

In 5,000 joint conditional one-year bootstrap paths with drift uncertainty, terminal loss frequencies are **25.84% V4**, **25.60% V3**, and **25.78% inspired proxy**. V4’s simulated 95th-percentile drawdown magnitude improves to **7.24%**, versus **8.15% V3**, while terminal loss frequency does not improve. These are model-dependent simulations, not calibrated future probabilities. The portfolios are not reoptimized on simulated asset histories.

## Qualification still required

The eight new variants follow **16 previously inspected smart variants**, plus earlier hybrid and parent research. The universe, model architecture and screening design were selected retrospectively. Dates from **2025-10-30 onward are excluded from scoring, calibration and selection**, but prior inspection elsewhere prevents describing them as pristine holdout data. No repeated search should be hidden by restarting experiment counts.

To progress toward institutional qualification:

1. **Keep promotion closed.** Obtain owner-approved numerical objectives and benchmark-relative acceptance thresholds before new evaluation. Current results fail the combined return/drawdown objective.
2. **Independent model validation.** Review macro assumptions, release timestamps, solver and account reconciliation. Validate factor exposures: duration/DV01, real-rate and breakeven inflation, equity beta, currency, credit and commodity shocks. Current sleeve risk balance does not establish factor neutrality. Estimate tail dependence, liquidity stress and expected-shortfall model error.
3. **Revisit the calibration hypothesis in a new frozen experiment.** Separate conservative exposure limits from statistical volatility/VaR calibration. Evaluate exception clustering and regime-specific coverage; do not tune to the same coverage p-values. Test whether simple market controls outperform macro complexity and whether the reserve’s carry compensates for duration and turnover costs.
4. **Execution-grade replay.** Repeat using actual tradable next-session prices, distributions/corporate actions, bid/ask spreads, volume/capacity and realistic fees. Adjusted-close fills here are a research convention. Include missing data, stale quotes, gap moves and delayed execution.
5. **Fresh evaluation.** Freeze the next model, source/data hashes and risk contract, then use genuinely uninspected future observations or a separately governed new evaluation set. Use multiple-testing controls and independent replication before claiming alpha.
6. **Runtime and paper qualification.** Integrate the new hierarchical risk contract and eligible instruments through the production authorization boundary with fail-closed validation. Independently test persistence, restart, broker/account reconciliation and limits, then collect supervised paper observations and operator acceptance. The current 14-ETF production gate remains unchanged.

## Files and reproduction

- `institutionalportfolio.py`: risk estimator, conditional core solver, forecast feedback and diagnostics.
- `research/institutional_refinement_plan.json`: frozen eight-variant research design and limits.
- `refine_institutional_portfolio.py`: verified historical inputs, chronological selection, simulation, ablations, stress and cycle reports.
- `benchmark_all_weather.py`: descriptive actual ALLW overlap, separate from selection.
- `test_institutional_portfolio.py`: allocation accounting, timing, calibration, eligibility and future-data protections.

```sh
python3 refine_institutional_portfolio.py
python3 benchmark_all_weather.py --fetch
python3 -m pytest -q test_institutional_portfolio.py
python3 -m pytest -q
```

The ALLW command requires network access; subsequent offline comparisons use `python3 benchmark_all_weather.py`. Historical ETF prices, archived macro files and V3 artifacts must already exist. Research input caches and generated evidence are ignored local artifacts under `var/research/institutional-refinement-v4/`; source hashes, all training trials, selections, trade audits, daily net returns, stress episodes, forecast coverage and bootstrap results are retained there. They must be packaged with a formal review because a source-only checkout does not include these local datasets.

Validation: **21 focused tests and 1,153 full-suite tests passed**, with Ruff checks passing for all four new Python files. Passing these tests establishes engineering evidence within the tested scope; it does not qualify investment performance or authorize deployment.
