# Continuous strategy validation and controlled tuning

**2 November implementation update:** use [LIVE_OBSERVATIONS.md](LIVE_OBSERVATIONS.md) for current status. Genuine public-market capture and isolated training are implemented; `live_observation_cycle.py` joins existing daily validation, institutional challengers and dynamic forward tracking. Docker/systemd recipes are supplied but not enabled. Owner has deferred broker/host connectivity. Older proposed module names and the retired 5%/50% objectives below describe historical planning, not current requirements or a claim that a scheduler is running.

**Approved direction:** automatically evaluate current data and tune candidate risk/allocation parameters in the background. **Current execution status:** design and existing building blocks only; no continuous research scheduler has been installed or enabled. The SPY connectivity probe is not a strategy run. No host exists yet, and a complete 28-asset/macro/rate feed has not been qualified.

The accepted investor dashboard remains frozen. Research outputs go into private research storage, not into the accepted dashboard or released recommendation state. Automation may produce proposals; it may not approve its own investment release.

## Run contract

A job is identified by `(exchange_session, strategy_version, source_hash, input_snapshot_hash, cost_model_version, experiment_id)`. Each successful evaluation is append-only and replayable. A retry must not count the same session twice, reset a portfolio high-water mark or publish a partial run. Serialize updates per research account. Use bounded memory/path counts and wall-clock limits.

Only the latest **completed** session is eligible. At the probe time on 30 October, a provider daily row labeled 30 October existed while the exchange was open; the completed-session boundary was 29 October. Use `TradingCalendar`, include a documented provider publication buffer, and discard future/in-progress bars before validation. On NYSE holidays, record a skip with the next eligible session, not a failed model day. On missing/stale/invalid data, quarantine and alert; keep the last successful dashboard snapshot visibly dated. Never call it current by relabeling its timestamp.

Separate successful freshness from investment success. A strategy can have a valid daily evaluation with a loss. Conversely, a favorable simulated return cannot make stale data valid.

## Proposed jobs and cadence

| Job | Proposed schedule | Work | Forbidden side effects |
|---|---|---|---|
| Feed capture / validation | Each NYSE session, target 17:30 America/New_York, with bounded publication-delay retries | Fetch ETF prices and metadata, verify completed session; capture FRED release vintages, rates, FX and cost inputs as applicable; freeze raw and validated versions | No allocation promotion, synthetic gap fill or overwrite of archived observations |
| Frozen-strategy shadow update | After feed snapshot succeeds | Advance champion and fixed challengers one session; old weights earn the return; decisions use only information available by their cutoff and fills obey the declared later time; persist NAV and high-water marks | No changes to frozen strategy source or investor accounts |
| Model/risk diagnostics | After shadow update | Data/weight reconciliation, drawdown, volatility, ES exceedances, exposure concentrations, turnover, costs, forecast calibration; compare matched benchmarks | No erasure of a breach or automatic risk-limit increase |
| Bounded challenger tuning | Weekly, after data and validation jobs | Train on declared historical window; evaluate inner chronological validation, including cost and parameter-neighborhood checks; save all trials | No use of the forward evaluation window to pick parameters; no unbounded return search |
| Promotion review package | Monthly or on a substantive candidate change | Compare unchanged champion with candidate on matured evidence; include failures, trial counts, uncertainty, stability, turnover and costs | No self-issued approval receipts or automatic customer updates |
| Recovery / heartbeat checks | Independent daily deadline and periodic restore drills | Detect no job, stuck job, stale inputs or corrupt output; notify operator; validate replay from snapshot | No silent success on catch-and-ignore exceptions |

The schedule is a proposal, not evidence that a timer is running. The first private host can use a single Docker job plus systemd; add external missed-heartbeat monitoring. A laptop-only development process cannot run while asleep and is not the deployment solution. Do not install the paper-worker timer as a substitute: it runs the separate 14-asset execution path.

## Modules to implement in order

Names below are proposed interfaces; they do **not** exist yet. Reuse existing components instead of cloning financial engines.

1. **`strategy_registry.py`** — immutable champion/challenger IDs, economic universe, declared account risk contract, source/config hashes, training windows, decision/fill timing and approved parameter ranges. Register the four macro designs by their existing names. Register the product planner separately; it is not another name for those dynamic strategies.
2. **`currentdata_pipeline.py`** — compose `marketdataloader.py`, `tradingcalendar.py`, `macrovintage.py` and `researchdatastore.py`; separately validate each instrument's eligible history, corporate-action revisions, rates/FX/fund costs and provider rights. ALFRED release dates control macro availability; do not use revised series with artificial lag as historical truth.
3. **`prospective_evaluation.py`** — parameterize the existing strategy/account simulation interfaces for explicit snapshot, start/end and unique output. Remove dependence on hardcoded `2025-10-30` cutoffs in the *new* recurring path; preserve original studies unchanged. Handle DBMF/ALLW eligibility without truncating every other instrument's long history or backfilling inception.
4. **`research_job.py`** — singleton orchestration, durable transactional job ledger, snapshot before evaluation, run timeout/cancellation, resource bounds, last-completed pointer, bounded safe retries and exit codes. Put ledger/result state beside existing private research storage. Never share the investor risk-state directory with experiments.
5. **`challenger_search.py`** — explicitly finite parameter search; separate train/validation/forward roles; purging for overlapping labels and disclosure of all repeated trials; no tuning on sealed forward evidence. Save candidate configurations as new versions.
6. **`modelmonitor.py`** — daily and matured-horizon diagnostics plus independent heartbeat integration. Reuse structured logging/alert transports, with explicit delivery authorization and recipient configuration.
7. **`promotion_review.py`** — collect matched evidence and require named review bound to source, data, cost model, mandate and release. Integrate `productrelease.py` / `paper_qualification.py` according to the destination. It can report readiness, never manufacture PASS evidence.
8. **`deploy/systemd/strategy-research.service` and `.timer`**, plus private Compose service — dedicated unprivileged worker, immutable image, secret mounts, state volume, deadline and operator runbook. Add these only after the one-shot job passes offline, fresh-data and failure tests.

A managed scheduler is an alternative to systemd, not another simultaneous scheduler for the same account. No Kafka, Kubernetes, automatic broker submission or custom authentication/cryptography is needed for this stage.

## Evidence and metrics

Keep daily net returns/NAV, dated allocations and risk contribution reconciliation, original peaks/drawdowns, transaction assumptions/turnover, liquidity, gross and net performance, cost/fee/tax/FX assumptions, rejected decisions, cash yield and cash drag. Record source and available-at timestamps, excluded instruments and reasons. Economic buckets and signed Euler variance shares must not be confused with capital weights.

Use matched-history cash/Treasury, strategic balanced, transparent All Weather-style proxy and actual ALLW-overlap references, as appropriate to each mandate. Actual ALLW is a benchmark only. Log cash-rate mismatch and inception/coverage limitations. Do not advertise one benchmark comparison as a universal optimality certificate.

Report rolling 1/3/5-year outcomes when observed history supports them, maximum drawdown and recovery time, downside deviation, Sharpe/Sortino with explicit rate conventions, CVaR/ES diagnostics and confidence intervals appropriate to dependent returns. Do not annualize a few prospective days into a reliable CAGR or treat absent tail events as proof of safety. Score macro forecasts against contemporaneous frequency baselines using only matured labels, with proper scores and reliability bins; they are not loss probabilities.

Stress: recession/equity selloff, inflation and bond-equity correlation shock, real-rate jumps, credit/liquidity deterioration, USD moves, gaps, doubled costs, rate changes, missing provider sessions and re-entry whipsaw. Treat scenario outcomes as assumptions, not predictions. Keep the original three-year 50% / 5% goal screen separately visible and unsupported unless evidence changes.

## Tuning and promotion policy

- Predeclare ranges for volatility targets, covariance half-lives, strategic tilt limits, turnover penalties, rebalance bands and reduce-only exposure controls. Financial loss capacity, access rules and liquidity reserves are constraints, not optimization knobs.
- Prefer parameter regions with stable net outcomes and low sensitivity to neighboring settings over a single peak backtest. Start with macro alpha disabled for the product planner; enable only after incremental predictive/economic value is demonstrated prospectively against a no-macro ablation.
- Proposed candidate acceptance: zero unexplained constraint/reconciliation failures; net outcome and drawdown trade-off within the preapproved profile; no material degradation under declared cost/stress scenarios; sufficient matured forward observations; validated model-risk/operational review. Numerical thresholds must be signed **before** opening evaluation evidence; they are not invented here as purported financial facts.
- Never optimize a new strategy every day on yesterday's losses. Keep daily evaluation separate from weekly search and infrequent reviewed release.
- Forward evidence after an actual strategy freeze is prospective. The old reserved period is historical holdout evidence only if its information has genuinely remained unseen; do not backdate the freeze or reuse a repeatedly inspected holdout as pristine.
- Require separate approval of any change to the owner's 5% loss preference. No stop, risk target or sample quantile guarantees that decline cannot be exceeded.

## Activation checklist

- [ ] Registry and account contract frozen; numerical acceptance criteria recorded.
- [ ] One-shot snapshot/evaluation replays exactly without orders or dashboard mutation.
- [ ] Current complete feed passes for every required asset and all required macro/rate inputs.
- [ ] Timeout, stale/intraday bar, provider outage, repeated job, partial write and restart tests pass.
- [ ] Host, image, secrets, monitoring recipient and off-host restore are qualified.
- [ ] Install timer; record enabled status, next run, successful real run and external heartbeat receipt.
- [ ] Observe and review; keep failed and skipped runs visible.
- [ ] Monthly review package produced; candidate stays unpromoted until reviewed release.
