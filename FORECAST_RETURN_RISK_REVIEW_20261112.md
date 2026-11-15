# Forecast, return and risk review — 12 November 2026

Current captured session: 11 November 2026. Research remains non-executable; historical comparisons are retrospective, not prospective account returns.

## Pipeline repair

A missing exact-calendar CPI endpoint made the current/revised informational FRED overlay fail. The capture now retains its checksummed raw files and writes an explicitly empty feature list plus UNAVAILABLE status/reason. Checksums, malformed inputs and provider failures still raise. No missing value is filled and no old overlay is relabeled current.

Point-in-time strategy inputs also lack a required macro period. The original strategy design explicitly returns DATA_QUARANTINE_CASH_ONLY. Acceptance now verifies the feature/report availability agreement, disabled invalid-input forecast, exactly 100% cash and zero risky weights. It validates all available scenarios against the declared quarterly context: four strategies × latest model when the informational overlay is unavailable; the full twenty when four quarters are available. Missing scenarios cannot pass under an available overlay. All artifact, numerical, PDF and source checks remain required.

A separate ledger comparison omitted explicit cash when normalizing a zero-risk candidate. It now reconciles candidate cash as well as risky weights. This changes source-bound protocol identity, so active-cohort.json selects a new prospective-cash-quarantine-v2.sqlite3 for each of the original, institutional and dynamic cohorts. Old prospective.sqlite3 files remain preserved; the original summary is archived-v1-summary.json. No old return is transferred or backfilled into the new cohorts. Operational observation counts and new cohort return counts are distinct.

## Forecast evidence

The predeclared validation selected C=1.0 and 25% learned / 75% frequency-baseline shrinkage. On 18 nonoverlapping historical quarterly outcomes, Brier was 0.7208 versus baseline 0.6882. The improvement lower bound was -0.0968; activation failed. Keep baseline predictions. No prospective quarterly outcomes have matured.

Next research: compare with regime persistence as well as frequency; use chronological purged selection, log loss, Brier and regime-specific reliability; retain the test results and demand new prospective evidence. Brier measures both calibration and discrimination, so calibration alone does not establish predictive skill ([scikit-learn documentation](https://scikit-learn.org/stable/modules/calibration.html)).

## Return and risk experiments

The table compares 252-session retrospective tests at 15 bps traded notional and zero cash yield. The incumbent here is the institutional engine, not the original fixed macro strategy. Variants are not live recommendations.

| Strategy | Variant | Test return | Maximum drawdown | Average cash |
|---|---|---:|---:|---:|
| economic_balance | incumbent | 4.87% | -4.24% | 24.3% |
| economic_balance | market_only_efficient | 4.30% | -4.14% | 58.8% |
| economic_balance | market_only_cautious | 4.28% | -3.85% | 50.0% |
| economic_balance | observed_macro_ablation | 2.99% | -4.14% | 55.9% |
| defensive_growth | incumbent | 5.82% | -4.62% | 25.2% |
| defensive_growth | market_only_efficient | 0.31% | -4.64% | 55.0% |
| defensive_growth | market_only_cautious | 4.92% | -2.56% | 48.7% |
| defensive_growth | observed_macro_ablation | 0.34% | -4.76% | 54.9% |
| inflation_resilience | incumbent | 7.55% | -4.11% | 24.2% |
| inflation_resilience | market_only_efficient | 8.19% | -3.18% | 62.3% |
| inflation_resilience | market_only_cautious | 7.21% | -3.08% | 67.7% |
| inflation_resilience | observed_macro_ablation | 8.19% | -3.18% | 62.3% |
| tail_aware_ensemble | incumbent | 7.04% | -4.08% | 24.1% |
| tail_aware_ensemble | market_only_efficient | 6.43% | -4.15% | 51.1% |
| tail_aware_ensemble | market_only_cautious | 5.18% | -3.34% | 50.2% |
| tail_aware_ensemble | observed_macro_ablation | 6.45% | -4.15% | 51.1% |

The validation rule retained three incumbents; the defensive-growth selected variant did worse on the historical test than its incumbent. Do not deploy the retrospectively best variant. The inflation efficient variant and defensive cautious variant are follow-up candidates only.

Priorities: isolate quarantine cash drag versus intentional risk reduction; compare an observed reserve ETF and actual verified account cash yield at equal risk; evaluate turnover bands at both 15 and 30 bps; retain asset, bucket and positive Euler risk caps and independently check covariance, correlation stress and expected shortfall. More equity exposure or looser caps alone do not establish better risk-adjusted results.

Next experiment specification: research/forecast_return_risk_review_20261112.json. Detailed source-bound study: var/p1-refinement/20261112-session-11-review/assessment.json. No weights, predictive gates, or order authority were promoted.

## Current operational allocation and verification

The 11 November dynamic snapshot uses its existing MARKET_ONLY_DEGRADED rule: 35% cash and 5.16% estimated annualized volatility. This is a conditional model risk estimate, not realized volatility or return. Original strategies remain 100% cash in data quarantine. No risk parameters were loosened.

Final repository regression: 1,496 passed. Changed Python files pass Ruff; git diff --check passes. Cash-only ledger reconciliation has a direct integration regression, including rejection of inconsistent cash. All three archived ledger file hashes match their recorded pre-change hashes.

Recovery completed at 20:39 UTC (21:39 Europe/Warsaw): published dashboard bundle is dated 11 November; dynamic 0/15/30 bps replays independently reconcile; watchdog reports HEALTHY_LOCAL_OBSERVATIONS / HEALTHY_SHADOW_JOB. Repeat scheduler tick returns CURRENT_SESSION_ALREADY_VALIDATED without duplicate observations. All three archived database hashes remain unchanged. The authenticated HTTP viewer was not running (connection refused); publication validated the complete Application and exports locally, but an HTTP/browser check was not completed.
