> Current policy update, 31 October 2026: fixed return targets and the 5% account drawdown constraint are superseded. See [Growth & Resilience](GROWTH_RESILIENCE_BENCHMARK.md). Earlier results below retain their historical assumptions.

# Economic P0/P1 execution

**31 October 2026, Europe/Warsaw.** Inputs are the verified market/vintage capture through 30 October 2026. This implements the five P0/P1 workstreams from `ECONOMIC_DESIGN_REASSESSMENT.md` as an isolated, executable shadow workflow. **Actual investor cash, costs, access and fund exposure gates remain blocked at the owner's explicit instruction: no verified files exist yet.** Nothing here is a public investment release or an approved replacement for the current portfolios.

## Completion and evidence

| Workstream | Executed locally | Remaining external/financial gate |
|---|---|---|
| P0 actual cash/reserve and exposures | Strict source/reviewer/hash/freshness/coverage validators, protected-file templates and explicit unavailable outputs | Actual cash history, broker costs/access, holdings/duration/FX evidence have not been supplied; no values invented |
| P0 availability and churn | All 130 rejected sessions diagnosed by series/calendar endpoint and reconciled with official publication incidents; independent bounded market-only fallback tested | Ongoing provider monitoring and future noncollection remain real risks; no macro observation filled |
| P0 stress-budget challenger | Independent 27-component solve, post-solve constraints, capital/factor-proxy/stress budgets and source-bound new cohorts | Unvalidated priors, assumed shocks/costs and absent actual exposure evidence prevent economic/public approval |
| P1 costs and reviewed recovery | Predeclared cost-hurdle comparisons, protective overrides, versioned review validator and state-preserving tests | Cost hurdle showed no incremental benefit in this run; no recovery approval supplied or consumed |
| P1 existing prospective experiment | Existing qualified job receipt validated/skipped; original SQLite bytes, summary and counts preserved | No new market session has elapsed; original and new experiments have zero forward return sessions |

Full numerical evidence: [V2 execution results](var/economic-shadow/p0-p1-v2-validated-2026-10-31/p0-p1-results.json). Per-session issue explanations are in the adjacent `macro-availability.json`; complete decision/target audit logs and account paths are under `comparisons/`. `var/economic-shadow/latest.json` points to the latest daily operational result, which can intentionally omit repeated historical comparisons.

## P0: evidence is explicit, protected and fail-closed

`economic_evidence.py` requires actual local evidence files, a named review, hashes and universe coverage. It rejects committed examples, missing fields, stale/future metadata, incomplete holdings coverage, invalid access flags, invalid costs and changed evidence files. A validated local attestation is not independent authentication or public approval.

- Cash uses the previously implemented exact-session realized USD net-return contract. No annual quote was substituted for an actual account history.
- Fund evidence covers every proposed component, with supplied effective duration, unhedged FX fraction, look-through coverage, access and source. Portfolio duration/FX review is unavailable until that evidence passes. These supplied measurements do not replace nonlinear derivative analysis.
- Execution evidence requires commission, spread, impact, FX and stressed cost allowances with supporting files. The current experiments retain the explicitly assumed 15 bps model; it is not relabeled as observed broker evidence.

Templates are `config/economics/cash-history.example.json`, `exposures.example.json` and `execution-costs.example.json`. Store actual versions and underlying statements privately outside the repository. The current result is `BLOCKED_NO_VERIFIED_EVIDENCE`; aggregate duration/FX review is `BLOCKED_UNVERIFIED_DURATION_FX_HOLDINGS`. No public release can be inferred from a successful shadow-job exit code. Supplying evidence later is not sufficient by itself to certify or activate the strategy: the measured assumptions, model and operating environment still need independent qualification.

## P0: the missing data are explained, not fabricated

The retrospective diagnosis finds **115 missing-period issues and 78 stale-series issues across 130 rejected sessions**. Multiple issues can occur on one date; 193 is not the number of rejected sessions.

- BLS confirms that October 2025 CPS unemployment survey data were not collected and were not retrospectively collected. [BLS CPS explanation](https://www.bls.gov/cps/methods/2025-federal-government-shutdown-impact-cps.htm).
- BLS documents the October CPI collection interruption and the absence of the ordinary October release. Some nonsurvey components have different treatment; that does not provide a missing aggregate observation for our contract. [BLS CPI explanation](https://www.bls.gov/cpi/additional-resources/2025-federal-government-shutdown-impact-cpi.htm).
- The revised employment/CPI release calendar corroborates the stale periods in the archive. [BLS revised dates](https://www.bls.gov/bls/2025-lapse-revised-release-dates.htm).
- The Federal Reserve records September industrial-production release on 3 December and October/November release on 23 December 2025. These dates reconcile with the archive under its conservative next-New-York-midnight availability rule. [Federal Reserve G.17 announcements](https://www.federalreserve.gov/feeds/G17.html).

`macro_availability_diagnosis.py` matches exact reference periods and date windows. It does not attribute arbitrary future/provider gaps to a shutdown. This incident catalog is a post-hoc diagnostic and **never enters the historical trading rule**; the experiments use the release-aware `macro_valid` state known at each decision.

The existing six-month unemployment, exact CPI/IP endpoint and 90-day/14-day freshness requirements are unchanged. Original strict models still go to cash when required inputs are absent. A second, separately named market-only challenger may hold at most **15% invested capital** and a **1.5% declared shock budget** during missing macro periods. It uses only observed market returns, halves its unvalidated return views and never reconstructs an unavailable economic indicator. It is not enabled in the original strategy or presented as validated alpha.

A deterministic endpoint scan also flags that the missing October 2025 CPI endpoint can matter again for **October 2026** and **January 2027** reference calculations. See [known dependencies](var/economic-shadow/p0-p1-review/known-calendar-dependencies.json). Those are calendar dependencies, not predicted release values or invented future observations.

## P0: independently solved stress-budget challenger

Current active experimental configuration: `research/stress_budget_challenger_v2.json`. The versioned challenger considers all **26 core instruments plus DBMF**, excluding benchmark-only ALLW. No asset is forced into the portfolio.

It uses a deterministic two-start constrained SLSQP solve, existing bucket priors shrunk toward observed clipped means, a fixed uncertainty penalty, variance aversion and modeled turnover cost. It does **not** establish a global optimum or certified expected return. Macro availability changes the allowed operating mode; no fitted classifier alpha is switched on.

Constraints include:

- Existing 5% account drawdown preference, 2% protective start and persistent 4% cash lock.
- Per-ETF capital and positive Euler contribution caps of 25%, with smaller target buffers to reduce avoidable boundary churn.
- A 4% forecast-volatility ceiling and at least 5% uninvested cash.
- Aggregate equity/government/real-asset/credit/alternative capital caps, plus an explicitly labeled foreign-capital proxy cap.
- Four declared simultaneous ETF shocks with a **2.5% portfolio stress-loss ceiling**; degraded mode tightens it to 1.5% and caps total investment at 15%.
- Carried account drawdown plus two full-notional modeled trade-cost allowances must remain within the declared 5% account-loss case.
- An unsuccessful solver or failed post-solve validation gives a blocked/cash outcome. No tolerance relaxation, implicit leverage or fitted winning variant is used.

These shocks and capital proxies are not measured duration/DV01/FX, calibrated event probabilities or a guaranteed maximum loss. All actual exposure and cost qualification gates remain blocked.

The current shadow proposal has approximately **55.44% cash**, **34.50% government/Treasury instruments**, **5.95% equities**, **2.65% DBMF** and **1.46% commodities**. SGOV is 24.5% and SHY approximately 10%; SGOV is an ETF reserve rather than deposit cash. Its modeled annual volatility is about **0.83%**. Worst loss among the four declared shocks is **2.50% before the modeled cost allowance**, or **2.7925%** including that allowance from a fresh NAV-1 account. Actual shocks may be worse. Full weights, Euler shares and checks are in `current-shadow-proposal.json`.

This is a new solve, not the previous illustrative uniform scaling bound. It remains unapproved. Low modeled volatility and high cash do not demonstrate the requested 50% three-year return goal.

## P1: cost and recovery experiments

The four variants were declared before their run. All use identical constraints, cost rate, prior-only 252-session histories and next-close execution. The cost-aware variant adds a discretionary benefit-versus-cost hurdle to the common cost-penalized optimizer; plain does not mean frictionless. Urgent risk, lock, unavailable-data and solver-failure exits override discretionary waiting and cost hurdles.

Retrospective evaluation: **30 October 2025–30 October 2026**, zero uninvested cash yield, 15 bps modeled traded notional, before investor taxes/platform fees.

| Predeclared variant | Net return | Maximum drawdown | Annual volatility | Modeled costs / starting capital | Fully cash sessions |
|---|---:|---:|---:|---:|---:|
| Strict / plain | +0.46% | −0.51% | 0.67% | 0.248% | 130 |
| Strict / cost-aware | +0.46% | −0.51% | 0.67% | 0.248% | 130 |
| Market-only degraded / plain | +1.31% | −0.69% | 1.02% | 0.239% | 0 |
| Market-only degraded / cost-aware | +1.31% | −0.69% | 1.02% | 0.239% | 0 |

No solver rejection occurred in these four paths. Event counters include evaluations that result in no trade; they must not be read as executed-trade counts. Per-decision logs preserve the decision session, intended later execution session, mode, weights, checks, costs/benefit rationale and final calculation ID. Protective scaling recomputes all disclosed risk metrics and IDs; it does not leave an unscaled risk summary attached to scaled weights.

**There is no demonstrated incremental benefit from the discretionary cost hurdle in this sample.** The degraded variant's higher return comes with different exposure/data behavior, not proven predictive skill. This interval has already informed the project, so it is not an untouched holdout. These very defensive results are not risk-matched proof of superiority over the four original models, do not exceed the separately measured 3.60% standalone SGOV reference, and do not validate the three-year target. That single-fund reference also differs from the project's concentration mandate.

Recovery is deliberately controlled. `reviewed_unlock` requires a cohort/session/config/state-bound receipt, named reviewer, evidence digest, valid review window and ten confirmed market sessions. It refuses to reset NAV or the high-water mark, refuses a still-unrecovered account outside the original 2% protective-start threshold, and records consumed review identity. Any approved research re-entry is limited to 10% exposure. No approval was supplied, no receipt was consumed, and no original or challenger account was unlocked. This local validator is not a public authorization endpoint; automatic unlock remains disabled. Original lock behavior is unchanged.

## P1: prospective cohorts and daily handoff

The existing `var/strategy-operations-v2` ledger's bytes, summary, source evidence and observation count were preserved. Its qualified current receipt was validated and idempotently skipped. It remains **1 operational observation and 0 forward return sessions**.

Four separate active challenger cohorts are stored below:

`var/economic-shadow-cohorts/STRESS_BUDGET_SHADOW_V2/<variant>/ledger.sqlite3`

They have distinct variant identity, source/config hashes, transactional immutable event chains, actual registration timestamps, carried peaks/locks and next-close pending instructions. Each currently has **NAV 1, zero forward return sessions**, and first permitted simulated fill at the **2 November 2026 NYSE close**. There are no broker orders. Repeating the same handoff does not increment the count or rewrite a decision. Changed source/configuration or conflicting same-session input requires a separate explicit cohort.

Initial V1 prototype registrations remain archived with zero forward returns. V2 versions the final post-scaling metric/ID reconciliation; economic risk parameters were not optimized between V1 and V2. Only V2 is the current configured worker target. Old records were not deleted or silently upgraded.

`run_economic_shadow_cycle.py` requires a healthy completed training/validation job and its exact receipt-bound snapshot bundle. It avoids the older global dashboard bundle when an isolated newer candidate exists. It refuses pending/failed validation or a mismatched bundle. The offline daily consumer does not retrain or invent a missing market session.

```sh
# Full isolated retrospective comparisons and current shadow registration:
python3 run_economic_p0_p1.py --register-shadow \
  --bundle <matching-current-verified-bundle.json>

# Preferred daily continuation from the completed validation job:
python3 run_economic_shadow_cycle.py
```

The first command's bundle must be current and match the completed source evidence; the preferred daily command resolves that handoff. Existing output directories are not overwritten. Evidence can optionally be supplied privately with `--evidence-root`; absent files retain the blocked gates. A successful job exit means shadow processing completed, not investor eligibility or release approval.

`Dockerfile.economic-shadow`, `compose.economic-shadow.yaml`, and `deploy/systemd/economic-shadow.*` supply a non-root, read-only, capability-dropped batch consumer with **no network**. The timer is **00:50 UTC Tuesday–Saturday**, after the primary weekday validation window. These files are **not installed or host-qualified**. A host administrator must build/scan/test the immutable image, stage protected inputs and routing, verify UID/permissions/recovery/monitoring, and only then enable the timer. No host exists in this session, and no unattended service or external alert delivery was claimed.

## Verification and remaining gates

Full local regression suite: **1,332 passed**; Ruff passed. New tests cover constrained allocations, strict and degraded modes, aggregate stress versus ETF caps, covariance/input rejection, protective cost-hurdle overrides, discretionary rejection, missing/invalid evidence, review bindings and peak preservation, exact official incident windows, immutable prospective registration, changed-source rejection, current-bundle handoff and scaled risk/ID reconciliation. Future market sessions in tests are synthetic fixtures only.

The actual full run verified all source hashes, wrote the four comparison paths and decision logs, registered independent V2 cohorts, and preserved the original prospective SQLite hash. A real repeated daily handoff was exercised to confirm idempotence. The investor dashboard, PDFs, standing original decisions and public approvals were not changed.

**Still blocked:** actual user cash/fees/access/exposure evidence, independent economic validation, elapsed prospective returns, measured stress execution assumptions, qualified Docker host, external alert delivery and public release. The owner's instruction to keep missing evidence gates blocked remains in force. Implementation and shadow execution are complete; profitable performance, a 5% guaranteed loss cap and institutional approval have not been established.
