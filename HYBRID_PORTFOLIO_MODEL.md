# Regime-adaptive hybrid portfolio

> **Universe policy update (2026-11-17):** Current portfolios and strategies resolve a configurable global instrument registry, with no fixed ETF-count limit. Numeric universe counts below describe this document's historical implementation or experiment. See [the current global-universe policy](GLOBAL_ASSET_UNIVERSE.md).

**Status: implemented research candidate, not activated in the paper worker.** The hybrid combines the 14-ETF production allocator and 26-ETF diversified research allocator. It seeks the highest net training return subject to a drawdown objective, rather than claiming a universally optimal portfolio.

## Result on common dates

Chronological parameter-selection evaluation: **2023-11-03 to 2025-10-29**, after 15 bps commission/slippage per dollar traded and with zero cash interest. These dates differ from the earlier three-year comparison; compare models within this table. The final 20% of dates, **2025-10-30 to 2026-10-29**, were excluded from return scoring.

| Model | CAGR | Annual volatility | Maximum drawdown | Sharpe over SGOV | Final value per $1 million |
|---|---:|---:|---:|---:|---:|
| 14 production allocator* | 17.76% | 8.26% | -7.85% | 1.442 | $1,381,419 |
| 26 diversified allocator* | 10.23% | 4.68% | -2.59% | 1.084 | $1,212,291 |
| Chronologically selected hybrid | 12.54% | 6.21% | -3.40% | 1.162 | $1,262,915 |

The hybrid earns **2.31 percentage points more annual return** than the diversified parent, with **0.82 points more drawdown**. Relative to the production allocator, it gives up **5.23 points of annual return** while reducing the observed maximum drawdown by **4.45 points** (56.7% relative reduction). It does not dominate both parents. The production allocator also has a higher Sharpe ratio in this period; the case for the hybrid is its chosen return/drawdown trade-off, not superiority on every metric.

## Concrete portfolio rules

1. **Combine validated parent proposals.** Only 14-ETF proposals passing the original exact 0.000001 budget tolerance and portfolio limits are eligible. Otherwise its blend fraction becomes zero and the diversified parent supplies the allocation. Parent proposals refresh every 21 sessions. Sources older than 35 calendar days reject allocation.
2. **Choose the blend chronologically.** Latest fold parameters: growth uses 100% of the valid 14-ETF proposal; defensive conditions use 100% of the 26-ETF proposal. Earlier selected folds used a 75%/25% growth blend. These are proportions of parent capital allocations, including their implicit cash reserves, not promises of full investment.
3. **Define growth conservatively.** The completed SPY close must be above its 200-session moving average and the last available price-proxy regime must indicate rising growth. Otherwise use the defensive fraction. The proxy regimes remain the comparison harness's 63-session SPY trend and DBC-minus-IEF relative performance, not actual macro releases.
4. **Reassess market risk daily.** Use a 252-return covariance estimate built by shrinking standardized-return correlations and restoring each asset's historical variance. The latest selected growth volatility ceiling is 12%; defensive and stress ceilings are 7% and 5%. Scaling only reduces exposure, never adds leverage.
5. **Maintain reserves and concentration limits.** Maximum 25% capital per ETF; at least 2% ordinary cash. Defensive invested exposure is capped at 60%; stress exposure at 40%, preserving at least 60% cash. SGOV remains invested ETF exposure, not cash.
6. **Use hysteresis and next-session execution.** Stress entry uses SPY's 252-session drawdown <=-10% or 20-session annualized volatility >=25%; exit requires drawdown >-7% and volatility <20%. Decisions use completed closes; old holdings accrue the next session return before a simulated next-close fill.
7. **Control unnecessary trading.** Skip proposed changes below 3% aggregate traded notional unless existing holdings breach the selected risk, exposure or position limits. This is a trade band, not a liquidity or fill guarantee.

## Selection protocol and scope of optimality

The candidate set was declared before running the experiment: growth parent-14 fractions {75%, 100%}, defensive fractions {0%, 25%}, and growth volatility ceilings {10%, 12%, 15%}, giving **12** candidates. Choose every 126 sessions using only the prior 252 sessions, with doubled 30 bps trading costs and zero cash interest.

The objective is the highest net training CAGR among candidates with absolute training maximum drawdown <=6%. If none meets 6%, use the predeclared fallback objective `CAGR - 2 * absolute maximum drawdown`. This is a soft research selection rule, not a guaranteed loss limit. All trials, not just winners, are retained.

| Training end | Following evaluation begins | Growth fraction from 14 ETFs | Defensive fraction from 14 ETFs | Growth vol ceiling | Training drawdown | Met 6% objective? |
|---|---|---:|---:|---:|---:|---|
| 2023-11-02 | 2023-11-03 | 75.00% | 0.00% | 10.00% | -6.34% | No; fallback used |
| 2024-05-06 | 2024-05-07 | 75.00% | 0.00% | 10.00% | -6.34% | No; fallback used |
| 2024-11-04 | 2024-11-05 | 100.00% | 0.00% | 12.00% | -3.75% | Yes |
| 2025-05-08 | 2025-05-09 | 100.00% | 0.00% | 12.00% | -3.75% | Yes |

The latest fold selection used data only through **2025-05-08**. It is a historical research setting, not a current live recommendation. The first two selections had no candidate satisfying the training drawdown objective and used the disclosed fallback. Before the first selection, a fixed, predeclared seed candidate supplies the warmup portfolio. Evaluation returns remain continuous through parameter changes, including their transaction costs; folds are not stitched together by resetting accounts.

Only a small, defined candidate family was searched. No claim of global optimality, statistical significance or future outperformance is made. These development dates were already inspected during earlier comparisons, so chronological selection does not turn them into a pristine out-of-sample test. Parameter and ETF selection biases remain. A future evaluation must freeze the complete methodology and obtain new acceptance evidence.

## Costs and risk-model qualifications

Annual traded notional for the hybrid is **240.20%** of capital (buy plus sell). At doubled 30 bps costs with zero cash interest, CAGR is **12.13%** and maximum drawdown is **-3.60%**. Using SGOV total returns as a cash-interest sensitivity raises base-cost CAGR to **13.09%**. That proxy is not an actual broker cash rate.

The hybrid risk-control covariance preserves observed variance scales, addressing the SGOV distortion in that layer. The parent allocations still use their existing covariance estimators. Their residual sensitivity is not repaired by an overlay and must be addressed before acceptance.

**Blending does not preserve the parents' account-level risk budgets.** This model defines a new composite account with position, cash and volatility constraints. It does not bypass or replace the existing production gate. A new approved account risk-budget contract, authorization integration, point-in-time macro signals, realistic price/execution data, tail-risk and correlation stress, and paper observation are still required. Daily checks do not guarantee a maximum drawdown; losses can occur before the next execution.

## Files and execution

- `hybridportfoliopolicy.py`: research-only blend policy and scale-preserving covariance estimator.
- `research/hybrid_portfolio.json`: frozen candidate grid, objective and risk controls.
- `optimize_hybrid_portfolio.py`: chronological selection, realistic self-financing costs, daily risk controls and common-date comparisons.
- `test_hybrid_portfolio.py`: risk limits, parent rejection, future/stale information, variance scaling, chronological selection and next-session execution.
- `var/research/hybrid-optimization/research-model.json`: selected research settings, experiment boundaries, source/data hashes and limitations.

```sh
python3 optimize_hybrid_portfolio.py
python3 -m pytest -q test_hybrid_portfolio.py test_compare_portfolio_models.py
```

The runner prints terminal results and writes all parameter trials, chronological selections, parent proposals, hybrid decisions, metrics and daily equity curves. No broker orders are submitted and no production settings are changed.

Research rationale: [Moreira and Muir](https://www.nber.org/papers/w22208) study volatility-managed portfolios; this motivates testing risk scaling but does not validate this implementation. [Bailey and coauthors](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) explain why choosing among backtests can overfit; the limited search, full trial log and separation of selection dates are precautions, not proof against selection bias.

![Hybrid and parent portfolio performance](var/research/hybrid-optimization/hybrid-performance.png)
