# Deployment and live-trading upgrade roadmap

**5 November dashboard update:** authenticated viewer now follows complete verified daily publications, including current price panels, macro/training/scenarios, benchmark, institutional and dynamic evidence/PDFs; browser checks each minute. All thirteen sections were opened in Safari and authenticated API/PDF/custom-scenario checks passed. Full regression: 1,484 passed. See [DASHBOARD_LIVE_UPDATES.md](DASHBOARD_LIVE_UPDATES.md) for section data sources, archived-profile boundaries and the macOS block on automatic viewer startup. Collection remains hourly; market prices are daily closes, not streaming quotes.

Execution progress: [LIVE_UPGRADE_EXECUTION.md](LIVE_UPGRADE_EXECUTION.md). Run `python3 live_upgrade_status.py` for the ordered status inventory. Partial implementation does not close qualification criteria.

**3 November P1 update:** checklist items **25 and 26** now have implemented local observability, escalation outbox, recovery drills, writer fencing and degradation monitoring. See [LIVE_ROADMAP_P1_EXECUTION.md](LIVE_ROADMAP_P1_EXECUTION.md) for actual operating evidence and remaining qualification requirements. This is distinct from the earlier economic P0/P1 strengthening study. Historical assessment/test counts below retain their original dates; external delivery, off-host recovery and genuine broker/longer-horizon evidence are not qualified.

Assessment date: 1 November 2026. **Not approved for unattended paper deployment or live trading.** The current product is a private recommendation/simulation preview. An instruction to improve deployment readiness does not provide broker credentials, account authority, jurisdiction approval or completed operating evidence.

**Updated owner scope:** The target now includes the founder's and other users' managed accounts, global equities, African exchanges, commodities and forex. [AFRICA_GLOBAL_LAUNCH_SCOPE.md](AFRICA_GLOBAL_LAUNCH_SCOPE.md) recommends Mauritius provisionally and IBKR Professional Advisor as the primary integration target, subject to legal/tax review and broker acceptance. Account isolation and client operations are P0 for client launch. All execution and jurisdiction-approval gates remain disabled/unapproved.

## What exists and what is missing

The project already contains market/macro capture, four adaptive strategy engines, a new dynamic blend, portfolio/risk authorization, OMS, a broker router, paper accounting/reconciliation, immutable prospective ledgers, recovery, monthly PDF/email tooling, dashboard, CI and Docker/systemd packaging. Reuse these boundaries. `livebroker.py` provides an abstract transport and live adapter boundary; this is not evidence of a qualified connection to an actual broker. The recommendation dashboard is not an execution console.

The fresh pre-repair acceptance on 1 November had 14 passing checks, zero failed checks and eight blocked prerequisites. A second run validates the repairs described below; use `var/release-acceptance/latest.json` for its report. Old counts and locked phase labels are historical evidence, not live-release approval. Docker is not available on this development machine. There is no confirmed deployment host. Mauritius and IBKR are provisional targets; no jurisdiction approval, client-country permissions or broker acceptance has been established.

## Repairs completed in this pass

- Dynamic blend calculation/risk validation now runs in temporary storage before challenger ledger updates or dashboard publication. A blocked blend leaves those downstream steps uncalled. Successful cycles publish the dynamic snapshot after those steps. This does not make all filesystem/database operations one atomic transaction; crash recovery across publication boundaries still needs qualification.
- Macro percentage inputs reject blanks, negatives, nonfinite values, values above 100 and zero totals. A pending older response is invalidated immediately when inputs change, and PDF download is disabled until a valid result is displayed.
- Rebuilt the current dashboard and its aliases, preserving the financial payload and existing PDF bindings, then verified its integrity seal. No allocation, prospective history or PDF financial results were regenerated.
- Added a regression test proving dynamic calculation failure precedes ledger/dashboard mutation. Local JavaScriptCore checked seven numeric-input cases; the focused Python suite passed 21 tests. Final full acceptance is recorded separately.

Items 01–26 below remain open unless their completion criterion is evidenced. These repairs close defects within items 05 and the dynamic-cycle implementation; they do not mark browser, model, host or live-broker qualification complete.

### Final validation

Post-repair acceptance: **engineering PASS; 14 passing checks, zero failed checks, eight blocked prerequisites**. Full regression: **1,384 tests, zero failures/errors/skips**. Repository-wide Ruff and dashboard JavaScript syntax passed. The audit verified that its bound sources, inputs, dashboard/PDFs and original ledgers remained unchanged during validation. [Retained acceptance report](var/release-acceptance/runs/20261101T144119212406Z-4711790f/acceptance.md).

The eight blocked prerequisites are financial evidence, complete-month coverage, actual monthly delivery evidence, prospective observations, host/image/alert/recovery reviews, product/jurisdiction review, browser qualification and pinned-runtime qualification. Nothing in this pass approves a live order, sends an email, installs a scheduler, provisions a host or proves future investment returns.

## Ordered implementation and qualification checklist

| ID | Priority | Work: change/add/qualify | Completion criterion | Dependency / owner |
| --- | --- | --- | --- | --- |
| 01 | P0 | Define first broker, jurisdiction and own-account versus client-account scope | Written scoped pilot mandate; account authority and instrument permissions verified | Owner, qualified local counsel where applicable |
| 02 | P0 | Reconcile repository; isolate release sources from backups/generated artifacts | Reviewed clean commit, import/release manifest, reproducible source identity; no unrelated files deleted | Engineering + owner review |
| 03 | P0 | Qualify pinned Python 3.12 release image and dependency locks | Full CI, execution tests, dependency/image/security scans, retained SBOM and immutable image digest | CI access and Linux/Docker runner |
| 04 | P0 | Provision one Linux Docker host using existing Compose/systemd templates | Restricted SSH, clock/disk monitoring, persistent protected volume, secrets, exact reviewed image and schedule verified | Host provision/access still required |
| 05 | P0 | Finish browser qualification and numeric input handling | Blank/negative/nonfinite macro input rejected; mobile layout, PDF identity and chart/profile interactions verified against release hashes | Engineering + browser reviewer |
| 06 | P0 | Validate the exact new dynamic portfolio | Chronological replay, all regimes, turnover/cost sensitivity, ablations, uncertainty and aggregate risk checks; no borrowed component performance | Quant/model validation |
| 07 | P0 | Integrate validated dynamic contract into dashboard, PDF and simulations | Every surface references the same dated contract; separate fixed reference and archived portfolios; stale/error states visible | Item 06 |
| 08 | P0 | Register a separately versioned dynamic observation cohort | No rewriting existing ledgers or backdating; hypothetical next-close fills and forward returns reconcile | Item 06; prospective time |
| 09 | P0 | Verify cash yield, fees/spreads, holdings/FX/duration and instrument access | Protected reviewed evidence bound to the release and account; current unknowns stay blocked | Actual provider/broker documents |
| 10 | P0 | Run paper host drills and observation period | Confirm alert receipt, isolated off-host restore, replay, outage/restart/disk-full handling; satisfy each applicable cohort/paper gate | Host and actual future sessions |
| 11 | P0 | Qualify monthly financial reporting and delivery | Complete post-registration month, reconciled PDF, consent/enrollment, configured sender, authorized receipt and ambiguous-send recovery | Actual month + sender configuration |
| 12 | P0-live | Implement concrete `BrokerTransport` for the chosen broker's sandbox | Documented authentication, account ID/environment checks, instrument mapping, submit/cancel/status normalization and reconnect | Item 01, official broker API |
| 13 | P0-live | Add durable broker submission outbox and ambiguity recovery | Persist client order IDs before send; timeout/crash queries broker before any retry; duplicate/reordered callbacks idempotent | OMS + broker sandbox |
| 14 | P0-live | Qualify broker-sourced account reconciliation | Startup/continuous cash, positions, open orders, fills and fees match broker; unknown/manual orders freeze affected account for review | Sandbox account feed |
| 15 | P0-live | Add executable quote and instrument contracts | Raw tradable prices, bid/ask age, exchange calendar, halts, split/dividend handling, tick/lot/minimum/fractional rules; adjusted closes never used as live order prices | Licensed data + broker instrument feed |
| 16 | P0-live | Extend pre-trade controls against actual account state | Buying power, settled cash, pending orders, per-order/daily notional, price collars, exposure/concentration, rate limits and stale/reconciliation vetoes | Existing risk authorization + items 13–15 |
| 17 | P0-live | Qualify real execution lifecycle | Partial fill, reject, cancel/replace race, late fill, disconnection, expiry, market closure and broker restart tests against sandbox | Broker sandbox evidence |
| 18 | P0-live | Add operational live controls | Independently tested persistent kill switch, cancel-open-orders workflow, account freeze, restricted resume and incident audit; liquidation requires explicit policy | Operations + broker |
| 19 | P0-live | Build production identity/security boundary | TLS, MFA/admin RBAC, service identities, secret rotation, access audit, rate limits, penetration review; loopback bearer token remains private-preview only | Security + host |
| 20 | P0-live | Qualify broker-to-account accounting | Actual fees, FX, dividends, splits, settlement, cash interest and tax-lot/reporting obligations for target scope; deterministic reconciliation | Broker + accounting review |
| 21 | P0-live | Add live release gate bound to exact evidence | Source/image/config/account/strategy IDs, expiring independent sign-offs, separate sandbox/live credentials; no dashboard toggle bypass | All P0-live items |
| 22 | P0-live | Run limited own-account canary only after approval | Owner-approved small cash-only limits, manual review, measured actual spread/slippage, rollback/freeze drills; no leverage/shorts/options initially | Independent release review |
| 23 | P0-client | Add tenant/account isolation before serving multiple users | Account-scoped authorization, separate ledgers/keys/limits, privacy/deletion/retention, tested cross-account access denial | Required before any client-account launch |
| 24 | P0-client | Add client operations appropriate to approved scope | Onboarding, mandates, suitability/access review, complaints, disclosure/reporting and any required regulated-provider integrations | Required before any client-account launch; jurisdiction-specific review |
| 25 | P1 | Add scalable observability and recovery | External alerts/escalation, freshness and execution SLOs, retained metrics/logs, tested backup objectives, single-writer fencing | Proven single-host pilot first |
| 26 | P1 | Measure strategy and execution degradation | Forecast calibration/drift, realized versus modeled risk, implementation shortfall and turnover; freeze/refit decisions reviewed, never auto-promote profitable-looking experiments | Genuine operating history |

## Modules to add or extend

The responsibilities below now have tested PAPER implementations mapped in [MANAGED_MODULES_IMPLEMENTATION.md](MANAGED_MODULES_IMPLEMENTATION.md). This is implementation coverage, not live qualification. Broker/host/client permissions and production integration remain gated; the managed path does not replace existing authorization boundaries.

- Extend `livebroker.py`/`brokerrouter.py` through a broker-specific transport; do not duplicate portfolio or risk logic in it.
- Extend OMS persistence with a broker outbox, execution-event deduplication, broker-ID mapping and unresolved-submission quarantine.
- Extend `reconciliationengine.py` with a broker account snapshot reader, pending-order exposure and corporate-action-aware reconciliation.
- Add executable quote/instrument adapters, separate from adjusted historical research data.
- Extend pre-trade authorization with account-bound live limits and expiring release identity.
- Add a live operations service for account freezes, cancel supervision, external monitoring and reviewed resume.
- Add a production API identity/tenant boundary before exposing dashboard or execution functions externally.
- Add source/image/account-bound live qualification evidence using the existing release/receipt patterns.
- Extend dynamic portfolio evaluation, common dashboard/PDF contract handling and independent prospective cohort registration.

## Release sequence and boundaries

1. Finish local repairs and exact-design validation.
2. Qualify clean image, host, evidence and unattended paper operation.
3. Complete broker sandbox transport, account reconciliation and failure testing.
4. Review legal/product/security scope for the actual intended service.
5. Obtain explicit approval for a tightly limited live own-account canary.
6. Expand limits only after reviewed real results; client money is a separate release.

Twenty observation/return sessions in the recommendation acceptance tool and the older 60-session/three-rebalance paper runbook are different gates. Satisfy the gates applicable to the selected release; neither can be manufactured by rerunning tests. Do not interpret zero software test failures as proof of investment profitability or maximum-loss protection.

## External review references

Jurisdiction is unresolved. The following are control-design references, not a conclusion that every rule applies to this project. [FINRA Notice 15-09](https://www.finra.org/sites/default/files/notice_doc_file_ref/Notice_Regulatory_15-09.pdf) describes development, validation and supervision practices for algorithmic trading. [SEC robo-adviser guidance](https://www.sec.gov/news/press-release/2017-52) addresses disclosure, client information and compliance concerns in automated advice. [ESMA's algorithmic-trading supervisory briefing](https://www.esma.europa.eu/press-news/esma-news/esma-issues-supervisory-briefing-algorithmic-trading) highlights pre-trade controls, governance, testing and outsourcing. Obtain a scoped review before public/client-account operation.
