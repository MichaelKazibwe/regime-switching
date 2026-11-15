# Integrated recommendation deployment execution

31 October 2026. Local implementation and validation completed; external deployment and investment approval remain blocked.

| Workstream | Implemented and checked | Remaining requirement |
|---|---|---|
| 1. Portfolio contract / Repair 6 | Five versioned current allocation contracts bind weights, model, valuation date, cost model and performance basis. Dashboard, scenario/PDF exports and ledger use explicit identities; archived illustrations stay separate. | Independent release review |
| 2. Prospective benchmark | Growth & Resilience is registered alongside four macro strategies and three legacy references. Next-close fills, monthly benchmark rebalancing, immutable events and contract checks implemented. | Real later sessions: one observation, zero forward-return sessions; first hypothetical fill 2 November 2026 |
| 3. Strategy value | Same-date, same-cost strategy replay reconciled; risk-matched benchmark uses prior-only volatility and decision-time budgets; 0/15/30 bps sensitivities and paired 21/63-session intervals computed. | Robust incremental advantage is not established; no promotion |
| 4. Financial evidence | Existing protected intake and fail-closed checks cover cash, execution costs, duration/FX/holdings and instrument access including the healthcare extension. Missing evidence is reported explicitly. | Actual reviewed evidence is absent; no assumptions marked verified |
| 5. Operations | Daily integrated shadow job passed and is healthy. Local backup and restore of real ledger plus input bundle verified. Tests cover tampering, immutable events, delayed fills, missing monthly boundaries, feed failures and authenticated API access. Docker import closure checked. | Docker unavailable locally; no qualified Linux host, image, external alert delivery or host recovery drill |
| 6. Reporting and rollout | Contract-bound completed-month summaries integrate with existing PDF/email tooling; partial periods block email delivery. A NO_DATA September preview was generated without sending. Qualification/checklist templates remain unapproved. | Complete post-registration month, explicit portfolio subscriber enrollment, protected sender configuration, jurisdiction review, independent economics review and release signoff |

## Latest economic comparison

Evaluation: 30 October 2025–30 October 2026. All figures below use modeled 15 bps costs on actual risky-asset dollars traded, zero unverified cash yield, the same dates and reference risk budgets derived from contemporaneous strategy decisions. Reference schedules share strategy quarantine and trade dates; these are diagnostic controls, not deployable independent strategies.

| Strategy | Strategy net return | Matched Growth & Resilience | Robust positive lower interval bound |
|---|---:|---:|---|
| economic_balance | -1.43% | 0.18% | False |
| defensive_growth | -1.68% | 0.26% | False |
| inflation_resilience | -0.82% | 0.14% | False |
| tail_aware_ensemble | -1.68% | 0.19% | False |

Changing costs uses fixed decisions, not a retrained adaptive path. Paired intervals remain descriptive and are not independent or multiple-testing-adjusted proof of alpha. Strategy promotion stays disabled.

## Reproduce local checks

```sh
python3 integrated_strategy_comparison.py
python3 scheduled_strategy_validation.py --root var/strategy-operations-integrated-v1
python3 strategy_healthcheck.py --root var/strategy-operations-integrated-v1
python3 integrated_release_readiness.py --junit var/integrated-deployment/regression.xml
```

The daily scheduled mode adds `--refresh` to capture completed market data, macro data, XLV and public headlines before training. Scheduler/host activation has not occurred. Do not repeat observations to inflate session counts. Same-session decisions are immutable. Historical roots and earlier validation attempts are retained.

Monthly generation uses `monthlydelivery.py --strategy-ledger <ledger> --portfolio-id Growth_Resilience_reference ... run --month YYYY-MM`. Use `deploy/integrated-monthly-recipients.example.json` as an inactive enrollment example. The existing paper-default recipient configuration was not reassigned. Generate-only remains the default; no email was sent. USD balances in these shadow reports scale an explicit 100,000 notional and are not broker balances.

Backup tools: `shadow_bundle_backup.create_backup`, `verify_backup`, `restore_backup`. Local actual artifacts are `var/integrated-deployment/backup` and `restored`; source-to-stored mappings and hashes are preserved. Host restart requires explicit path/configuration rebinding and qualification; local restore does not attest a remote recovery drill.

## Validation and artifacts

- Full regression: **1,345 passed**; subsequent PDF presentation checks: **43 passed**. Ruff passed; JavaScript parsed in native JavaScriptCore.
- Source-bound current contracts: `var/investor-dashboard/portfolio-contracts.json`.
- Current daily job and prospective state: `var/strategy-operations-integrated-v1/`.
- Comparison: `var/integrated-deployment/strategy-comparison.json`.
- Explicit external blockers: `var/integrated-deployment/readiness.json`.
- Monthly preview status: `var/integrated-deployment/monthly-preview-status.json`.
- Main PDF was rendered with native PDFKit; identity text wrapping was corrected after visual review. The optional Node PDF marker helper is unavailable; no package installation was performed.

## Next action

Keep the financial design frozen during prospective observation. Collect reviewed cash/cost/access/exposure evidence and provision a Linux Docker host, then qualify the immutable image, alerts and recovery. Twenty daily engineering observations are a minimum operational gate, not proof of strategy profitability. Public recommendations and execution remain disabled.
