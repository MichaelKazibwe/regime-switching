# Portfolio risk contributions and capital weights

**Assessment:** the solver meets its configured group risk budgets, but the covariance model materially inflates SGOV variance relative to this historical sample. Resolve that estimator sensitivity before using the resulting weights for paper qualification. No allocation, signal or production configuration was changed by this analysis.

Analysis of the **26-ETF research portfolio**, not actual account holdings. Saved adjusted prices end at **29 October 2026**; covariance uses **756** returns from **2023-10-25** through **2026-10-29**, annualized by 252. Four conditional regimes share one covariance snapshot. No current regime classification, expected return, drawdown forecast or return backtest is supplied.

## Method and verification

Capital weight is the fraction of total portfolio capital invested. Percentage risk contribution is `w_i * (Sigma @ w)_i / (w.T @ Sigma @ w)`. Contributions sum to 100% of modelled variance; the same percentages also decompose modelled standard deviation using Euler contributions. A component annual volatility is that share multiplied by portfolio annual volatility, not the ETF standalone volatility. Cash has zero price variance in this model and therefore zero contribution, while still carrying purchasing-power and currency risks.

Independently refitted Ledoit-Wolf covariance reproduces the saved matrix. Configuration and price hashes match the allocation snapshot; risk contributions reconcile to reported values and group budgets. All eight normal/stress profiles satisfy capital accounting, the 25% position cap, volatility ceilings and the 0.000001 risk-budget tolerance. This verifies arithmetic and constraints; it does not validate the estimator or investment performance.

## Capital and risk by economic group

| Regime | Equity capital / risk | Nominal-government capital / risk | Inflation-sensitive capital / risk | Cash | Model volatility / ceiling |
|---|---:|---:|---:|---:|---:|
| Growth up / inflation down | 29.75% / 50.00% | 47.26% / 30.00% | 17.99% / 20.00% | 5.00% | 6.26% / 12.00% |
| Growth up / inflation up | 18.37% / 40.00% | 45.45% / 15.00% | 24.17% / 45.00% | 12.01% | 4.42% / 10.00% |
| Stagflation | 6.22% / 20.00% | 38.46% / 25.00% | 14.85% / 55.00% | 40.47% | 2.36% / 7.00% |
| Deflationary slowdown | 10.77% / 15.00% | 46.07% / 55.00% | 18.16% / 30.00% | 25.00% | 5.08% / 6.00% |

The inflation-sensitive group contains gold, commodity futures exposure and TIP. Nominal government bonds include SGOV, which remains invested exposure rather than uninvested cash. All normal-regime volatility estimates are below their ceilings: cash floors bind in disinflationary growth and deflationary slowdown; the SGOV 25% position cap binds in inflationary growth and stagflation. The strategy does not borrow to fill the gap to a volatility ceiling.

## Main risk concentrations

| Regime | Three largest model risk contributors | Combined risk share | Active ETFs |
|---|---|---:|---:|
| Growth up / inflation down | SPY 18.07%, GLD 15.82%, TLT 11.75% | 45.64% | 22 |
| Growth up / inflation up | GLD 23.92%, DBC 17.35%, SPY 14.53% | 55.79% | 22 |
| Stagflation | GLD 35.94%, DBC 13.95%, SGOV 10.59% | 60.49% | 21 |
| Deflationary slowdown | TLT 27.41%, GLD 23.62%, IEF 13.95% | 64.98% | 21 |

Gold is a significant driver despite modest capital weights: in stagflation, 5.20% capital contributes 35.94% of modelled risk. Deflationary slowdown concentrates risk in TLT, GLD and IEF (64.98% combined). Long-duration, intermediate-duration and inflation-linked bonds can share rate exposure; allocating TIP to a different sleeve does not eliminate that correlation.

In disinflationary growth, SPY holds 10.41% capital but contributes 18.07% risk; IEF holds 16.54% capital but contributes 10.48% risk. These differences illustrate why capital allocations should not be read as risk budgets.

LQD, HYG, SLV and VNQ are zero in every regime, and TLT or DBC is additionally zero in some regimes. Consequently, 26 eligible instruments produce 21–22 active positions. Many sector allocations are below 1% of capital in defensive regimes; their incremental diversification should justify transaction costs and turnover.

## Priority finding: SGOV and covariance shrinkage

The estimated shrinkage coefficient is **2.9415%**. [Scikit-learn documents Ledoit-Wolf](https://scikit-learn.org/stable/modules/generated/sklearn.covariance.LedoitWolf.html) as a blend of empirical covariance and a scaled identity matrix. The identity target pulls every asset variance toward the same cross-asset average. Applying this directly to assets with very different volatility scales materially raises the variance assigned to the Treasury-bill ETF.

SGOV's annualized sample volatility is **0.22%**, versus **3.06%** in the model. This is approximately 14.0 times the sample volatility. Its [issuer mandate](https://www.ishares.com/us/products/314116/sgov) is 0–3 month Treasury bills; its published three-year standard deviation was 0.22% as of 30 September 2026, a useful corroboration on a different window. It is still an ETF with execution and price risk, not zero-risk cash.

| Regime | SGOV capital | SGOV model risk share | SGOV unshrunk-sample risk share at same weights |
|---|---:|---:|---:|
| Growth up / inflation down | 7.09% | 0.12% | 0.00% |
| Growth up / inflation up | 25.00% | 3.01% | 0.03% |
| Stagflation | 25.00% | 10.59% | 0.09% |
| Deflationary slowdown | 4.61% | 0.08% | 0.01% |

In stagflation, the nominal-government group meets its 25% model risk target but contributes only 15.42% under unshrunk historical covariance at the same weights. Equity and inflation-sensitive shares then become 22.85% and 61.73%. This is an estimator-sensitivity diagnostic, not proof that sample covariance is the correct forward risk model. Changing the estimator would require solving the budgets again; do not adopt these diagnostic risk shares as approved targets.

Recommended first research comparison: shrink correlations after standardizing each return series, then restore separately estimated volatilities; compare with a diagonal variance target that preserves volatility scales and suitable block/factor covariance models. Keep Treasury-bill variance nonzero and retain the cash and position constraints. Compare stability and out-of-sample calibration before choosing an estimator. No estimator replacement has been made.

## Diversification and overlap

| Pair | Shrunk-model return correlation |
|---|---:|
| SPY / QQQ | 0.916 |
| SPY / XLI | 0.781 |
| SPY / XLY | 0.821 |
| SPY / KIE | 0.406 |
| SPY / ITB | 0.453 |
| VEA / EWJ | 0.838 |
| TIP / IEF | 0.656 |
| IEF / TLT | 0.802 |

Sector and country funds add targeted tilts, but their overlap with broad funds means ticker count overstates independent diversification. KIE and ITB have lower correlation with SPY in this window than QQQ, yet that does not establish superior crisis diversification. IGOV, EWJ, VEA and VWO also introduce foreign economic/currency exposures; USD listing alone is not a hedge. No current constituent-level look-through, duration decomposition or currency-factor attribution was calculated.

## Cash and stress overlay

| Regime | Normal cash | Normal SGOV | Cash + SGOV capital (not a cash-equivalence claim) | Stress cash | Stress model volatility |
|---|---:|---:|---:|---:|---:|
| Growth up / inflation down | 5.00% | 7.09% | 12.09% | 60.00% | 2.63% |
| Growth up / inflation up | 12.01% | 25.00% | 37.01% | 60.00% | 2.01% |
| Stagflation | 40.47% | 25.00% | 65.47% | 60.00% | 1.58% |
| Deflationary slowdown | 25.00% | 4.61% | 29.61% | 60.00% | 2.71% |

All stress allocations retain at least 60% uninvested cash. The overlay proportionally scales the same regime portfolio, so percentage risk contributions do not change; dollar risk and estimated volatility decrease. This is cash de-risking, not a separately optimized crash hedge. Covariance shocks, gaps, liquidity shortages and macro-input errors can still cause losses. Large defensive reserves can materially reduce returns in a recovery; cash income must be modelled in acceptance backtests.

## Prioritized assessment

1. **Before paper qualification:** address the low-volatility-asset covariance sensitivity and repeat risk budgeting with validated estimators. Preserve strict fail-closed budget checks, cash floors and concentration caps.
2. **Before claiming diversification improvements:** measure incremental contribution of the overlapping sector/Japan satellites, stock/sector look-through, rate duration, FX factors and crisis correlation stress. Test whether the gold and duration concentrations are acceptable.
3. **Before changing risk targets:** compare the current 756-session estimate against short/long windows, exponentially weighted and regime-conditioned covariance, using predeclared out-of-sample tests. Do not select solely on this snapshot.
4. **Before paper activation:** run point-in-time macro switching and next-session execution with costs, turnover limits, cash interest and realistic minimum trade thresholds. Validate net returns, drawdown and expected shortfall as well as volatility. No conclusion about expected returns or deployment readiness follows from risk-budget compliance alone.

## Detailed evidence

- [All 26 asset weights, contributions and covariance-sensitivity diagnostics, normal and stress](var/research/diversified-regime-expanded/risk-analysis/asset-weights-and-risk.csv)
- [Economic-group capital and risk shares](var/research/diversified-regime-expanded/risk-analysis/group-weights-and-risk.csv)
- [Regime concentration and volatility summary](var/research/diversified-regime-expanded/risk-analysis/regime-summary.csv)
- [Machine-readable analysis and snapshot hashes](var/research/diversified-regime-expanded/risk-analysis/analysis.json)

![Weights and modelled risk contributions](var/research/diversified-regime-expanded/risk-analysis/weights-versus-risk.png)
