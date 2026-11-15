# Three-year goal feasibility assessment

**Research decision: FAIL_TARGET_FEASIBILITY_SCREEN. No strategy accepted and no production activation.**

Mandate: 50% cumulative net investment return over three calendar years and no more than a 5% account peak-to-trough decline. Required compound annual growth is **14.47%**. USD accounting, no contributions, nominal returns before investor taxes. A finite backtest cannot guarantee either objective.

## Executed evidence

- Frozen **12 variants**, plus 12 fixed no-account-guard diagnostic twins. Previous inspected smart variants: 24; older parent/hybrid work is additional.
- **180 fresh three-calendar-year accounts**, 15 start dates per candidate. Joint observed successes: **0/180**. These overlapping accounts are not independent trials.
- Highest observed fresh-account return: **12.96%** (candidate_09, 2017-01-03–2020-01-03); its drawdown was -4.27%.
- Worst fresh-account drawdown: **-4.79%** (candidate_04, 2015-01-02–2018-01-02).
- Continuous protected-account CAGR range: **-0.22% to 0.20%**. No-account-guard twin CAGR range: **2.44% to 3.72%**.
- Largest executed core risk-budget error: **1.23e-10**, against unchanged 1e-6 tolerance.
- Next-close fills, 15bps traded-notional modeled costs, 30bps fixed-reference sensitivity, zero yield on truly uninvested cash.
- Macro/trend ablations, rolling horizons, raw/filtered tail coverage, exception clustering, six stress episodes, synthetic gap/delay shocks and 3,000 joint three-year bootstrap paths.

## Complete variant results

| Model | Role | CAGR | Maximum drawdown | Rolling approximate-three-year joint success |
|---|---|---:|---:|---:|
| candidate_00 | GOVERNED_RESEARCH_CANDIDATE | -0.21% | -4.02% | 0.00% |
| candidate_00_no_guard | DIAGNOSTIC_ABLATION | 3.04% | -11.72% | 0.00% |
| candidate_01 | GOVERNED_RESEARCH_CANDIDATE | 0.19% | -4.06% | 0.00% |
| candidate_01_no_guard | DIAGNOSTIC_ABLATION | 3.01% | -11.51% | 0.00% |
| candidate_02 | GOVERNED_RESEARCH_CANDIDATE | 0.15% | -4.07% | 0.00% |
| candidate_02_no_guard | DIAGNOSTIC_ABLATION | 3.00% | -11.73% | 0.00% |
| candidate_03 | GOVERNED_RESEARCH_CANDIDATE | -0.22% | -4.07% | 0.00% |
| candidate_03_no_guard | DIAGNOSTIC_ABLATION | 3.36% | -11.82% | 0.00% |
| candidate_04 | GOVERNED_RESEARCH_CANDIDATE | -0.22% | -4.04% | 0.00% |
| candidate_04_no_guard | DIAGNOSTIC_ABLATION | 2.44% | -10.41% | 0.00% |
| candidate_05 | GOVERNED_RESEARCH_CANDIDATE | -0.22% | -4.04% | 0.00% |
| candidate_05_no_guard | DIAGNOSTIC_ABLATION | 2.84% | -10.42% | 0.00% |
| candidate_06 | GOVERNED_RESEARCH_CANDIDATE | -0.21% | -4.02% | 0.00% |
| candidate_06_no_guard | DIAGNOSTIC_ABLATION | 3.15% | -11.72% | 0.00% |
| candidate_07 | GOVERNED_RESEARCH_CANDIDATE | 0.18% | -4.06% | 0.00% |
| candidate_07_no_guard | DIAGNOSTIC_ABLATION | 3.12% | -11.51% | 0.00% |
| candidate_08 | GOVERNED_RESEARCH_CANDIDATE | 0.20% | -4.07% | 0.00% |
| candidate_08_no_guard | DIAGNOSTIC_ABLATION | 3.11% | -11.73% | 0.00% |
| candidate_09 | GOVERNED_RESEARCH_CANDIDATE | -0.22% | -4.07% | 0.00% |
| candidate_09_no_guard | DIAGNOSTIC_ABLATION | 3.72% | -11.90% | 0.00% |
| candidate_10 | GOVERNED_RESEARCH_CANDIDATE | -0.22% | -4.04% | 0.00% |
| candidate_10_no_guard | DIAGNOSTIC_ABLATION | 2.66% | -11.52% | 0.00% |
| candidate_11 | GOVERNED_RESEARCH_CANDIDATE | -0.22% | -4.04% | 0.00% |
| candidate_11_no_guard | DIAGNOSTIC_ABLATION | 3.06% | -10.67% | 0.00% |
| strategic_equity_50 | BENCHMARK_ONLY | 6.36% | -25.03% | 0.00% |
| strategic_equity_70 | BENCHMARK_ONLY | 7.14% | -36.27% | 0.00% |
| prior_v3 | BENCHMARK_ONLY | 2.92% | -10.73% | 0.00% |
| prior_v4 | BENCHMARK_ONLY | 2.46% | -11.28% | 0.00% |
| all_weather_proxy | BENCHMARK_ONLY | 2.19% | -11.33% | 0.00% |

Risk anchors are variance budgets, not capital allocations. The plain/market/macro-market variants are all retained; none is silently selected after evaluation. Allocation rejection causes a logged cash proposal and makes the research screen fail. The cash high-water mark is never reset. The 2%–4% exposure reduction is a frozen research design choice, not proof that all possible protective policies fail.

## Interpretation and limitations

The mandate prioritizes preservation so strongly that the tested account guard sharply restricts compounding. Cash-heavy or inactive periods must not be mistaken for successful crisis forecasting. The no-guard twins reveal the returns and drawdowns forgone; they are diagnostic and are not authorized alternatives. A cash latch requires operator review and does not assume a discretionary profitable restart.

Both normal and filtered historical forecast diagnostics are retained, including diagnostic no-guard accounts with longer histories. Filtered thresholds use only prior realized standardized residuals and do not raise allocations. Coverage or clustering can still fail; low observation counts are explicitly reported rather than certified.

Joint bootstrap frequencies resample the fixed no-guard portfolio streams, with shared dates and drift uncertainty. They do not rerun asset-level allocation or the protective account guard on simulated markets. They are conditional diagnostics, not calibrated probabilities of meeting the mandate. Paired overlay intervals are development-only and not corrected for repeated strategy searches.

Synthetic one-session and repeated three-session shocks demonstrate possible execution-delay losses; they are scenarios, not estimated probabilities. The strategy is long-only and unlevered at the account level; foreign bonds retain currency exposure. Fund prices embed expenses, and modeled costs omit measured spreads, capacity and investor-specific taxes.

History ends 2025-10-29; the reserved boundary remains 2025-10-30. Source/input hashes are retained. Earlier inspection and retrospective universe/model design mean there is no pristine out-of-sample claim. The first GFC segment is partial. Daily bars cannot establish an intraday 5% drawdown bound.

## Remaining roadmap gates

Local research steps 1–9 have executable evidence; an unsuccessful feasibility result is not strategy acceptance. Independent qualification and paper promotion remain closed unless a candidate clears owner-approved research criteria. The current outcome does not justify weakening the 5% objective, risk budgets or authorization gate.

A real managed-futures ETF comparison, when available, is a fixed separate benchmark and is not a direct futures implementation or a change to the 12-variant search. No pre-inception fund returns are manufactured. Independent factor/duration/currency/liquidity validation, actual execution-price replay, future observations, host qualification and supervised paper acceptance remain necessary external work.

If no candidate meets the mandate, the owner must choose whether to extend the horizon, permit a deeper temporary decline, or accept a lower return target. This study does not prove that 50%/5% is mathematically impossible; it supplies no evidence sufficient to deploy it.

## Reproduction

```sh
python3 evaluate_three_year_goal.py
python3 benchmark_managed_futures.py --fetch
python3 report_three_year_goal.py
python3 -m pytest -q test_goal_portfolio.py
python3 -m pytest -q
```

Generated evidence: `var/research/three-year-goal-v5/` (ignored local data, must be packaged for independent review). Core files include `comparison.csv`, `fresh-three-year-accounts.csv`, `feasibility-screen.csv`, `decision-audit.json`, `research-screen.json`, `extended-risk-diagnostics.json`, `gap-delay-stress.csv`, `stress-episodes.csv`, `paired-overlay-uncertainty.csv`, `three-year-conditional-bootstrap.csv`, and `goal-feasibility.png`.

## Actual managed-futures ETF illustration

Fixed 10% DBMF sleeve replaces 10% equity capital in a benchmark-only comparison. Actual adjusted fund prices, a 252-return eligibility lag and matched history are used. This is a short-history, retrospective illustration, not a selected or authorized strategy. [Issuer fund description](https://www.imgp.com/us/fund/US53700T8273/).

| Benchmark | Start | End | CAGR | Maximum drawdown | Rolling joint success |
|---|---|---|---:|---:|---:|
| growth_reference | 2020-05-08 | 2025-10-29 | 11.29% | -23.37% | 0.00% |
| 10pct_actual_DBMF | 2020-05-08 | 2025-10-29 | 10.68% | -18.53% | 0.00% |

## Calibration finding

In the fixed candidate_00 no-account-guard diagnostic account, raw normal VaR95 exceptions occur on **3.93%** of evaluated days; filtered historical exceptions occur on **4.65%**. The filtered unconditional coverage p-value is **0.289**, but conditional coverage still fails (**p=0.000426**). Overall frequency improved; clustering remains unresolved. This diagnostic does not certify the protected account or future loss bounds.

Synthetic stress on historical target allocations reaches **9.75%** loss for a one-session scenario and **25.99%** for repeated three-session shocks. These are deliberately hypothetical gap/delay scenarios, not historical portfolio losses or probability estimates. They demonstrate why a next-close cash switch cannot guarantee 5% protection.

## Engineering validation

Full regression suite: **1,178 passed**. Focused goal/benchmark tests: **25 passed**. Ruff checks for all six new Python files and `git diff --check` pass. Simulation source/input hashes were verified; no production activation or orders occurred. These checks are engineering evidence, not investment acceptance.
