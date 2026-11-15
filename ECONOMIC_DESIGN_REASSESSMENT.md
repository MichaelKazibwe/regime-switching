> Acceptance execution: [local engineering passed, release prerequisites blocked](RELEASE_ACCEPTANCE_EXECUTION.md). Latest full regression: 1,375 passed. Existing ledgers and published portfolio artifacts were unchanged.

> Unified acceptance checkpoint: run `python3 release_acceptance.py`. See [the acceptance guide](RELEASE_ACCEPTANCE_GUIDE.md) and `var/release-acceptance/latest.json` for the source-bound report, fresh checks and unresolved release prerequisites. Acceptance does not add observations or approve release.

> Return-engine refinement: see [Institutional-method challengers](INSTITUTIONAL_RETURN_ENGINES.md) for public-source research, positive historical results, benchmark limitations and the separate forward cohort. Incumbents are unchanged.

> Integrated deployment checkpoint: see [Six-workstream execution](SIX_RECOMMENDATIONS_EXECUTION.md) for the contract-bound dashboard/report/ledger, current comparison and unresolved external gates. Active observation root: `var/strategy-operations-integrated-v1`.

> Current policy update, 31 October 2026: fixed return targets and the 5% account drawdown constraint are superseded. See [Growth & Resilience](GROWTH_RESILIENCE_BENCHMARK.md). Earlier results below retain their historical assumptions.

# Repair 5 — economic design reassessment

**Completed locally: 31 October 2026 (Europe/Warsaw). Market cutoff: 30 October 2026.** The assessment tooling and review are complete; the investment strategies do **not** pass the resulting economic screen. No portfolio is promoted, risk preference relaxed, current strategy source changed or standing prospective decision replaced.

## What was implemented and executed

`economic_design_assessment.py` verifies the training report, source hashes and market capture, independently reconstructs all four archived trade paths, and reconciles returns, capital, turnover and costs. It then computes cash/cost sensitivities, risk-budget-matched references, paired block-bootstrap comparisons, availability/cost attribution, all-28-asset descriptive diagnostics, full-account stress screens and a declared three-year reference frontier. `economic_design_report.py` verifies the resulting artifacts and produces a standalone frontier chart and illustrative exposure review.

Authoritative numerical results:

- [Completed assessment](var/economic-assessments/repair-5-2026-10-31-validated/economic-assessment.json)
- [Reference frontier](var/economic-assessments/repair-5-2026-10-31-validated/reference-frontier.csv)
- [Individual observed cohorts](var/economic-assessments/repair-5-2026-10-31-validated/three-year-cohorts.csv)
- [Illustrative stress exposure review](output/economic-design/stress-exposure-review.json)
- [Derived-output provenance](output/economic-design/report-output-manifest.json)

Earlier exploratory folders without the `-validated` suffix remain archived. Use the verified result above or `var/economic-assessments/latest.json`; exploratory results are not a release or decision source.

## Main conclusion

The binding issues are data availability, cash economics, weak incremental performance and aggregate shock exposure. Adding models or ETF tickers does not resolve them. The present 50% three-year return / 5% account drawdown objective remains **unsupported by this evidence**; the analysis does not claim it is mathematically impossible.

The current four strategies' evaluation remains 252 sessions, **30 October 2025–30 October 2026**, using the same frozen evaluation model and original 15 bps cost convention. Predictive alpha stays OFF. The new study does not rewrite those results to credit an assumed cash yield.

## 1. Cash and reserve economics

No actual investor cash-account return history is configured. The example cash-rate configuration is unverified and was not used as evidence. The assessment now accepts a separately reviewed, hash-bound realized USD net-cash-return history with exact valuation-session coverage; missing dates are rejected. See [the private configuration contract](config/economics/README.md). This gate remains `BLOCKED_NO_VERIFIED_USER_CASH_HISTORY` until actual evidence is supplied and reviewed.

Using the captured adjusted market prices over the same 252 sessions, a standalone SGOV ETF reference returned approximately **+3.60% after modeled initial trading cost**, while the explicit zero-yield uninvested-cash assumption returned 0%. SGOV is a reserve ETF, not deposit cash, an insured account, a known future yield or a universally available product. Its issuer describes the fund and its risks in the [SGOV prospectus](https://www.ishares.com/us/literature/summary-prospectus/sp-ishares-0-3-month-treasury-bond-etf-2-28.pdf).

| Strategy | Original net return | Fixed decisions, cash linked to observed SGOV returns | Interpretation |
|---|---:|---:|---|
| Economic Balance | −2.00% | +0.21% | Sensitivity only |
| Defensive Growth | −1.97% | +0.22% | Sensitivity only |
| Inflation Resilience | −0.81% | +1.26% | Sensitivity only |
| Tail-Aware Ensemble | −1.80% | +0.29% | Sensitivity only |

The linked-cash sensitivity retains original ETF decisions and credits residual cash with observed SGOV returns. It does **not** model actual SGOV funding trades, reserve concentration caps, taxes, account availability or a new guard/calibration path. It is not an executable allocation or a full adaptive strategy rerun. Historical adjusted ETF returns already reflect observed fund/distribution behavior; no invented current annual yield or double fund-expense deduction was added.

**Decision:** obtain actual account cash economics before public comparisons. Reserve implementation must preserve per-instrument limits and access/fee constraints; replacing every cash balance with one ETF can violate them. Do not claim that crediting an assumed deposit yield fixes the investment strategy.

## 2. Data availability and trading costs

All four original paths independently reconcile with their verified CSVs. Each has **130 unavailable-macro return sessions out of 252 (51.59%)**. P&L is segmented by available versus unavailable signal sessions; this is not a prediction of what would have happened if the missing inputs existed.

| Strategy | Total modeled costs / starting capital | Quarantine exit + recovery entry costs | Share of modeled costs |
|---|---:|---:|---:|
| Economic Balance | 0.635% | 0.285% | 44.8% |
| Defensive Growth | 0.651% | 0.285% | 43.7% |
| Inflation Resilience | 0.536% | 0.277% | 51.6% |
| Tail-Aware Ensemble | 0.772% | 0.285% | 36.9% |

Trade tags identify the first evidence-supported category: data quarantine, recovery re-entry, drawdown sizing, or joint schedule/risk/regime behavior. Several triggers can coincide. These are associated realized modeled costs, not an identified causal experiment or a guaranteed saving achievable by removing a trigger.

The assessment also replays the **same decisions** at zero and 30 bps. These fixed-decision sensitivities are distinct from the archived doubled-cost strategy reruns, in which costs affect later risk decisions. Both concepts must remain separately labeled.

**Decision:** reconcile publication gaps versus ingestion gaps, measure availability by series, and resolve the data contract first. Retain fail-closed behavior. Research turnover controls only for discretionary trades, with predeclared benefit-versus-cost thresholds and hysteresis; urgent risk reductions must remain available. No such parameter was fitted to this evaluation period or deployed here.

## 3. Risk-budget-matched references

New comparisons use the archived strategy's planned volatility budget on the same execution dates. Reference volatility is estimated from **252 actual returns ending before the execution close**. References use the same fee rate, no leverage and their own 2% de-risking / permanent 4% cash lock. This is an ex-ante risk-budget match, not a promise that realized volatilities are identical.

| Strategy | Original | Matched All Weather-style reference | Matched balanced reference | Matched SPY reference |
|---|---:|---:|---:|---:|
| Economic Balance | −2.00% | −2.02% | +0.13% | +0.83% |
| Defensive Growth | −1.97% | −2.47% | −0.33% | +0.44% |
| Inflation Resilience | −0.81% | −0.54% | +0.56% | +0.87% |
| Tail-Aware Ensemble | −1.80% | −2.32% | +0.02% | +0.54% |

These references piggyback the original strategy's known risk decisions/fill schedule and have their own guard outcomes. They are diagnostic controls, not standalone strategies or mandate-approved replacements. In particular, concentrated references may violate the project's per-ETF caps. All Weather-style means the declared liquid 30/40/15/7.5/7.5 proxy, not actual Bridgewater fund performance.

Paired moving-block bootstrap intervals use **2,000 paths with both 21- and 63-session blocks**. None of the four strategies has a positive lower bound against every declared reference/block sensitivity. Several intervals cross zero, so this is **not** a claim of statistically established underperformance in every comparison. It shows no robust incremental advantage sufficient for promotion. The intervals are descriptive, dependent on the observed period and unadjusted for the project's wider model-selection history.

## 4. Entire 28-asset menu and aggregate risk

The assessment includes all **28 catalogue instruments**, each with its economic role, current strategy weights, actual trailing-252-session return/volatility/correlation, and descriptive ridge loadings on SPY/IEF/TIP/GLD/DBC proxies. All 28 have complete current observed history in this capture. The proxy regressions are not causal economic factors, measured duration, DV01, currency decomposition or future-return estimates.

The four candidates still hold 9–10 ETFs. DBMF remains outside these fixed strategy maps; ALLW stays benchmark-only. No zero-weight asset is automatically added. Overlapping equity satellites, multiple duration instruments and highly related strategies do not automatically produce independent diversification.

Using the existing calibrated covariance and current active asset set, all four candidates pass their current per-ETF capital and Euler variance caps. **They nevertheless fail the new aggregate five-percent stress screen.** Four explicitly assumed ETF-return shocks cover growth collapse, inflation/rate shock, stagflation and liquidity dislocation. They are scenarios, not calibrated event probabilities or a claim about the maximum possible loss.

| Strategy | Worst loss in declared hypothetical shocks, before fees |
|---|---:|
| Economic Balance | 11.94% |
| Defensive Growth | 14.47% |
| Inflation Resilience | 10.28% |
| Tail-Aware Ensemble | 13.22% |

Full shock vectors are in the assessment. Duration/DV01/FX limits remain **unverified** because reliable exposure metadata have not been supplied; statistical ETF betas do not substitute for them.

The derived exposure review preserves the archived evaluation account's high-water mark and reserves 0.30% for up to two full-notional trades at the existing modeled 15 bps. Under those particular assumptions, satisfying a five-percent account drawdown case would imply cash fractions approximately **77.9%, 83.8%, 65.5% and 78.6%** respectively. This is a conservative **illustrative bound**, not a proposed optimum, executed allocation, suitability decision or guarantee. Other shocks, stressed trading costs and gaps can exceed it. It also illustrates the participation/return cost of the strict loss preference; no candidate weights were changed to these values.

**Decision:** use aggregate shock-loss and verified exposure limits alongside per-ETF variance caps when designing the next shadow challenger. An allocation that fails the loss budget must not be described as low-loss merely because its variance budget reconciles. Preserve existing gates while obtaining actual duration/FX/holdings data and testing an independently specified candidate.

## 5. Three-year return–drawdown frontier and recovery cost

![Observed reference frontier](output/economic-design/economic-frontier.png)

The grid was declared in code before evaluation: three reference families, annual volatility budgets **2%, 4%, 6%, 8%, 10%**, and protection on/off. Each of the **30 configurations** has **29 overlapping 756-session cohorts**, monthly-spaced by 21 sessions: **870 runs**, not 870 independent experiments. Earliest cohort start is **1 June 2021** and latest complete grid-cohort end **6 October 2026**. The separate strategy evaluation reaches 30 October 2026. Prior actual histories estimate volatility; the common frontier start requires 252 observed SGOV returns and therefore excludes older crises.

The frontier uses zero uninvested cash yield and 15 bps costs. Some reference positions exceed project per-ETF/factor limits; these are reference diagnostics, not demonstrated deployable solutions. No leverage, fitted winner, altered loss preference or unobserved synthetic history was used.

**No run achieved both 50% three-year return and maximum drawdown no worse than 5%.** A 50% three-year target requires approximately **14.47% compounded annually**. This is evidence about the declared references/windows, not a proof that every conceivable strategy must fail.

Examples of the participation/recovery trade-off:

| Reference / annual vol budget | Guarded median 3-year return | Unguarded median 3-year return | Guarded worst drawdown | Unguarded worst drawdown |
|---|---:|---:|---:|---:|
| All Weather-style / 4% | −0.95% | +6.22% | −4.00% | −11.05% |
| Balanced / 4% | +6.77% | +14.27% | −3.99% | −8.97% |
| SPY / 6% | +3.99% | +22.00% | −4.15% | −9.45% |
| SPY / 10% | +1.65% | +38.30% | −5.64% | −15.55% |

Medians and worst drawdowns summarize different overlapping cohorts; the table is not one single path. Protection can reduce losses and also prevent recovery after an early cash lock. Even the protected runs can breach 5% through next-close timing/gaps. Unguarded runs are diagnostics only and were not activated. Actual positive cash returns could alter this zero-yield frontier; no unsupported deposit history was invented to quantify that change.

**Decision:** keep the 5% preference and report the unsupported return aspiration honestly. Any change to the return objective, loss tolerance or re-entry policy needs an explicit mandate decision and a newly versioned prospective challenger, not retrospective selection of a favorable window. Risk and return decisions must reflect the investor's ability and willingness to lose money; see the [SEC investor risk guidance](https://www.investor.gov/introduction-investing/investing-basics/save-and-invest/gauge-your-risk-tolerance).

## Economic screen and prioritized next work

The new screen is blocked for all four strategies: actual user cash history is absent, original returns are below zero-yield cash, aggregate declared stresses exceed 5%, and robust reference advantage is not demonstrated. Passing a descriptive screen would still require independent review; this tool never enables promotion.

1. **P0 — establish actual cash/reserve economics and exposure metadata.** Configure protected cash history, account fees/access, verified fund duration/FX/holdings and stress-cost inputs. Keep missing inputs explicitly unavailable.
2. **P0 — resolve data-availability causes and associated churn.** Preserve exact-calendar/vintage and fail-closed contracts. Test any predeclared degraded-data fallback separately before considering it for use.
3. **P0 — design a stress-budgeted shadow challenger.** Require aggregate loss-budget checks and factor concentration review, rather than adding more labels or correlated ETFs. Do not adopt the illustrative scaling bounds as validated weights.
4. **P1 — research cost-aware discretionary rebalancing and reviewed recovery.** Keep protective exits; compare unchanged baselines using fixed experiment protocols, measured execution assumptions and separate prospective cohorts.
5. **P1 — continue the existing prospective experiment without rewriting it.** Accumulate actual later outcomes; use the strict engineering acceptance plus independent economic validation. The current bootstrap is not a three-year track record.
6. **Then repair 6:** unify the user-facing portfolio/model/date/performance contract before exposing any of this new analysis through recommendations, dashboard or monthly email reports.

## Reproduce and verify

```sh
python3 economic_design_assessment.py \
  --bundle var/investor-dashboard/latest-strategy-run.json
```

For a newer isolated scheduled candidate, pass that candidate's matching `latest-strategy-run.json`. Each run writes a new private directory and verifies its sources/artifacts. An existing output folder is not overwritten. To add an actual reviewed cash history, supply `--cash-manifest /protected/path/cash-history.json`; the committed example intentionally fails validation.

```sh
MPLCONFIGDIR=/private/tmp/regime-economic-mpl python3 economic_design_report.py \
  --assessment var/economic-assessments/repair-5-2026-10-31-validated/economic-assessment.json \
  --training-report var/strategy-training-runs/20261030T210916293673Z/training-report.json
```

**Validation:** 1,319 tests passed in the full suite; Ruff passed. New tests check self-financing profit attribution, next-close guard timing, permanent cash locks, missing-price rejection, prior-only risk matching, reproducible paired intervals, rejected/unverified/missing cash history, aggregate stress versus ETF caps, blocked promotion, and carried-peak/cost-aware stress bounds. Existing dashboard integrity and prospective ledger were rechecked without changing their contents or counts.

The dashboard/PDF design remains locked. No packages were installed, no emails sent, no orders submitted, no return target promised and no public deployment or economic approval granted. The assessment implementation is complete; A05 and the other economic audit findings remain unresolved until new economic evidence and a qualified design satisfy them.

## P0/P1 execution checkpoint — 31 October 2026

See [ECONOMIC_P0_P1_EXECUTION.md](ECONOMIC_P0_P1_EXECUTION.md) for source/reviewer evidence gates, official release-incident reconciliation, the separately solved stress-budget challenger, predeclared cost/fallback comparisons, reviewed recovery validation and independent prospective cohorts. The owner confirmed no verified files are available, so cash/cost/access/exposure gates remain blocked. Active challenger configuration is `research/stress_budget_challenger_v2.json`; original strategies and their cohort are unchanged. V2 shadow results and daily-handoff templates do not imply financial approval or a qualified host.
