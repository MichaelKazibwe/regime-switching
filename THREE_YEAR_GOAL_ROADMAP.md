# Three-year return and capital preservation roadmap

Owner objective: **50% cumulative investment return over three years**, with **at most 5% temporary peak-to-trough account decline**. This requires approximately **14.47% annual compound growth**, net of modeled trading costs. Additional contributions do not count as investment returns. Research accounting is in USD, matching the existing project; taxes, inflation and another spending currency require separate assessment.

These are acceptance objectives, not promised outcomes. A stop, cash switch or estimated risk constraint cannot guarantee a 5% maximum loss through gaps and delayed execution. Higher potential returns generally involve greater risk. [SEC asset allocation guidance](https://www.investor.gov/introduction-investing/getting-started/asset-allocation).

The existing production universe, strict **1e-6** risk-budget tolerance, 25% asset capital/risk contribution caps and paper-only authorization remain unchanged. No broker orders, deployments, emails or acceptance receipts are authorized by this research roadmap.

| Step | Deliverable and exit evidence | Initial state |
|---|---|---|
| 1. Freeze mandate | `research/three_year_goal_plan.json`: target, account high-water mark definition, cost assumptions, data hashes, reserved boundary and bounded search | Complete |
| 2. Establish honest benchmarks | Simple global growth allocations plus V3, V4 and All Weather-inspired references; distinguish benchmark-only weights from eligible production proposals | Complete; actual 10% DBMF benchmark also tested |
| 3. Build growth candidates | Two explicit equity risk anchors, two volatility ceilings, three fixed overlays: plain, market trend, macro plus market trend; 12 variants | Complete |
| 4. Protect and attribute capital | Conditional core/reserve risk accounting, daily forecast checks, fixed account drawdown reductions, protective cash lock and explicit gap-breach reporting | Complete in research; no runtime authorization |
| 5. Separate calibration from sizing | Prior-only filtered historical forecast residuals, next-return coverage and exception-clustering diagnostics; do not increase risk to improve a p-value | Implemented and evaluated; not a calibration certification |
| 6. Test horizons and costs | Continuous accounts, complete rolling 756-session windows, fresh annually started three-year accounts, fixed no-drawdown-control ablations, doubled costs, six stress episodes and gap/delay scenarios | Complete; 180 fresh three-calendar-year accounts |
| 7. Compare uncertainty | Paired block resampling and joint three-year bootstrap; conditional model evidence, not guaranteed success probabilities | Complete; 2,000 paired resamples and 3,000 joint paths |
| 8. Validate engineering | Timing, future-data, costs, risk attribution, no high-water reset, protective lock, selection and malformed-input tests; full regression suite | Complete: 25 focused and 1,178 full-suite tests pass; Ruff and diff checks pass |
| 9. Make the feasibility decision | Publish all variants, joint goal frequencies, failures, source hashes, limitations and a machine-readable research screen; no forced winner | Complete: FAIL; 0/180 fresh accounts meet both objectives |
| 10. Independently qualify | Actual tradable execution replay, factor/liquidity model review, managed-futures implementation if justified, fresh future observations and owner acceptance | Closed: research screen failed; future/independent evidence unavailable |
| 11. Qualify paper runtime | New risk-contract integration, deployment environment, reconciliation/restart drills, supervised observation and operator acceptance | Closed: no accepted strategy; no deployment host selected |

The fixed drawdown policy reduces new risky allocations after a 2% account drawdown, more strongly after 3%, and latches to uninvested cash at 4%. The latch requires operator review and is not silently reset after a calendar period. Next-close execution means losses can exceed either threshold before fills. This deliberately exposes the opportunity cost of prioritizing the 5% objective.

The 12 variants are research-only extensions of the existing conditional core/reserve allocator. Growth anchors describe **risk shares**, not capital weights. The market overlay uses only prior observed multi-horizon price trends. The macro overlay is capped at 10%; macro scenario scores are not probabilities. The fixed no-account-drawdown-control twins are diagnostic ablations and remain subject to allocation, stress and position controls; they are not approved alternatives.

No actual managed-futures sleeve will be fabricated from long-only ETF trend signals. AQR's research concerns diversified trend implementations, including derivatives and short exposure, with different risks and execution requirements. [AQR research](https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing).

All three-year frequencies are development evidence. The ETF universe and earlier models were selected retrospectively; overlapping windows are dependent. The reserved boundary remains **2025-10-30**. Even dates excluded here cannot be called pristine if inspected in earlier work. Search count starts after 24 inspected smart variants, excluding older hybrid/parent searches.

Results: [THREE_YEAR_GOAL_ASSESSMENT.md](THREE_YEAR_GOAL_ASSESSMENT.md). The best fresh-account three-year return was **12.96%**; the worst decline across those accounts was **4.79%**. No candidate met both objectives. The implementation and feasible local research stages are complete; the return target is not achieved. Steps requiring future observations, independent approval or a deployment host cannot honestly be completed by a local backtest.

The original executed simulation source and account outputs are retained in a hash-verified cache. A subsequent numerical boundary correction uses **1e-12 roundoff tolerance** for return/drawdown comparisons; simulation functions, market inputs and account paths are unchanged. `python3 evaluate_three_year_goal.py --reuse-simulations` verifies those invariants before recalculating metrics. A changed simulation function or cached input/output fails closed and requires a full rerun. This is verification, not an additional parameter search.
