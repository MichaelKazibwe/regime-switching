# Ordered checklist execution — 1 November 2026

Latest checklist P1 execution (3 November): [LIVE_ROADMAP_P1_EXECUTION.md](LIVE_ROADMAP_P1_EXECUTION.md) maps item 25 (observability/recovery) and item 26 (degradation measurement) to concrete modules, real local recovery/monitoring results and unqualified external dependencies. Neither item is marked fully qualified by synthetic tests or local restore timing.

Latest module pass: [MANAGED_MODULES_IMPLEMENTATION.md](MANAGED_MODULES_IMPLEMENTATION.md) maps all nine requested responsibilities to the new paper transport, durable coordinator, adapters, API, operations and evidence modules, with tests and remaining live requirements. Earlier checkpoints below are retained history, not claims that later modules are absent.

## Follow-through on remaining items 1–6

The following is actual execution progress, not approval to deploy or manage client money.

| Remaining item | Work executed | Qualification still open |
| --- | --- | --- |
| 1: dynamic portfolio | Published a separate Dynamic portfolio dashboard section with contract identity, engine mix, full menu/cash weights and signed risk shares, searchable roles, growth/drawdown chart and cost scenarios. Generated and visually checked a two-page contract-bound PDF. Added/tested separate forward ledger and registered one real operational observation with zero return sessions; first hypothetical fill scheduled for 2 November. | Independent model acceptance, exact-design forecast simulations, longer prospective history and broader browser qualification. Historical replay is not a forward simulation or observation history. |
| 2: account integration | Added/tested internal opaque expiring/revocable paper sessions resolving to explicit account grants; default-deny client-country checks, instrument/quote/currency/age validation, exact direct-rate cash valuation and pre-trade largest-remainder lot allocation with no founder preference. | Production MFA/identity integration, settled buying-power reservations, position/settlement/corporate-action accounting, real mandates, account routing, encrypted key management and security review. The helpers do not authorize or submit orders. |
| 3: broker sandbox | Added a TLS-verified localhost IBKR paper portfolio probe: demo identity confirmation, read-only endpoint allowlist, bounded complete position pagination and account-bound cash/settled-cash validation. Tests cover wrong account, denied order endpoints and connection failure. | No authenticated Gateway or confirmed advisor permissions are available. No broker session was opened. Write transport and real partial-fill/cancel-race/reconnect tests remain unimplemented/unqualified. The probe is not an order adapter. |
| 4: release/host | Staged and verified a new content-addressed paper worker candidate at `var/releases/paper-candidate-20261101-steps1-6`. It records clean_commit=false. | This is the existing paper worker release context, not a packaged multi-client platform. A clean reviewed commit, managed-platform packaging, Linux image build/scans, host and host-side drills remain required. No host exists in the supplied evidence. |
| 5: evidence gates | Ran local identity, eligibility, fair-allocation, cash valuation, broker-probe, prospective-registration and preview integrity tests. Rendered/reviewed PDF and exercised dynamic dashboard in Safari. Re-ran full release acceptance. | Observation time cannot be manufactured; complete-month delivery, mobile/browser qualification, legal/product and independent model/security reviews remain blocked. No email was sent. |
| 6: pilot | Added/tested separate founder/client readiness diagnostics; client scope adds licence, mandate, identity-isolation and client-country requirements. Both outputs always retain execution_enabled=false and release_approved=false. | Neither pilot is started or qualified. This diagnostic inventories reviews; it is not an executable release authorization. Use existing evidence validators and independently approved live-account controls before any pilot. |

New code: `dynamic_preview.py`, `dynamic_forward.py`, `managed_boundary.py`, `ibkr_paper_probe.py` and their tests. Existing investor plans, benchmark contracts, original ledgers and numerical strategy policy were preserved. A new optional dynamic PDF link was added; it does not replace investor-plan reports.

### Reproduce the local follow-through

```sh
python3 dynamic_preview.py
python3 -m pytest -q test_dynamic_preview.py test_dynamic_forward.py test_managed_boundary.py test_ibkr_paper_probe.py
python3 paper_release.py verify --root var/releases/paper-candidate-20261101-steps1-6
python3 release_acceptance.py
```

`dynamic_forward.advance(bundle, database)` refreshes and registers at most one observation per completed session into a **separate** cohort; it rejects changing a sealed session. The registered database is `var/dynamic-forward-v1/prospective.sqlite3`. It must not be repeatedly invoked to imply additional observation days. It is not installed as an unattended job.

The PDF is `output/pdf/dynamic-portfolio-report.pdf`, identical to its manifest-bound dashboard copy. Its dated contract is `2c9010a2ffd1e3a71786c9ceace6107cfc086a7d5f5d48c4a8ca1763d96f190e`. PDF pages were rendered with native PDFKit and visually inspected. The shell Node executable is unavailable; the supplied PDF marker script was validated using the available Node runtime. No packages were installed.

IBKR implementation references: [account discovery](https://ibkrcampus.com/docs/web-api/trading/portfolio-and-positions/querying-your-accounts), [paged positions](https://ibkrcampus.com/docs/web-api/v1/endpoints/portfolio/positions), [currency ledger](https://ibkrcampus.com/docs/web-api/v1/endpoints/portfolio/portfolio-ledger). The read-only probe deliberately rejects non-demo/unconfirmed account identities and does not implement API order endpoints or automate authentication. Professional advisor/tiered-account access must be confirmed separately.

Final follow-through validation: **1,415 tests passed, zero failures/errors/skips; Ruff and JavaScript syntax passed**. Release acceptance remains engineering PASS with 14 passing checks and eight blocked prerequisites. Retained report: `var/release-acceptance/runs/20261101T154438414726Z-74d71645/acceptance.md`. The new dynamic PDF was resolved by its contract through the verified application boundary and matched the manifest-bound file byte-for-byte. Native Safari verified the new view, contract identity, DBMF role/search (6.40% capital, 8.03% variance share) and historical drawdown selection. Full phone-width and release-wide browser qualification is still open. No browser PASS receipt was issued.

**Status: in progress; not qualified for live deployment.** No real account, licence, broker transport, host or client deployment was created. Existing research universes, mandates, broker enablement, ledgers and dashboard financial results are unchanged.

| Checklist item | Implementation in this pass | Still needed |
| --- | --- | --- |
| 01 | Owner/client account scope and provisional Mauritius/IBKR targets recorded | Licensing/tax/client-country approval and broker acceptance |
| 06 | Exact dynamic blend replay with prior-close decisions, later close fills, explicit degraded macro states and 0/15/30 bps cost reruns | Independent replay reconciliation, regime/benchmark/ablation/uncertainty assessment and acceptance; retrospective results are not untouched or prospective evidence |
| 13 | Durable account-bound non-executable PAPER intents, stable client IDs, duplicate/conflict rejection and frozen-account veto | Broker dispatch/ack/event state machine and ambiguity recovery |
| 15 | Broker/entity/contract/venue identity, quote units, lot/tick checks; NYSE/LSE/HKEX/JSE calendars, lunch-break checks, completed sessions and strictly later closes | Verified security master, executable quotes, auctions/halts and market permissions; unsupported African calendars fail closed |
| 20 | Exact journals balanced per currency, immutable journal rows, duplicate/conflicting events and restart persistence | Positions, corporate actions, settlement, fees, FX NAV and broker reconciliation |
| 23 | Explicit account/action grants, same-account-ID cross-tenant denial, isolated reads/journals and freezes | Authentication-derived principals, API integration, encryption/key management, mandates and client security review |
| All 26 | Source-bound ordered machine-readable progress inventory | Actual completion evidence for every qualification criterion |

Implementations: `managed_accounts.py`, `global_market_calendar.py`, `live_upgrade_status.py` and their tests. These are paper foundations, isolated from live routing and the public dashboard. Internal `Principal` objects are not authentication tokens; a future API must derive them from verified identity. Provisioning/filesystem access are trusted operator operations. Paper intent references do not verify a mandate or risk authorization and cannot authorize a broker submission.

## Validation and reproduction

```sh
python3 -m pytest -q test_managed_accounts.py test_global_market_calendar.py test_live_upgrade_status.py
python3 -m ruff check .
python3 live_upgrade_status.py
python3 evaluate_dynamic_portfolio.py --output var/dynamic-portfolio/NEW_UNIQUE_RUN
python3 release_acceptance.py
```

Focused result: **18 tests passed**; repository-wide Ruff passed before final formatting. Tests cover account isolation, journals, precision independent of caller Decimal context, duplicate requests, freezes, persistence, lot/tick/GBX checks, Hong Kong lunch break, differing venue closes, US daylight-saving transition and denied unknown calendars. All database fixtures use temporary paths and synthetic values; they are not prospective performance evidence. No packages were installed.

Two additional dynamic-replay tests passed: modeled costs reduce wealth, and changing fill-day prices cannot change the first prior-close target. The exact replay is a newly declared design with a 21-session schedule, 4% discretionary trade band, immediate next-close risk-triggered proposals and full fills at modeled adjusted closes. It does not represent executable live fills or the old benchmark's history.

## Completed historical replay

The exact blend replay completed **3,980 sessions, 4 January 2011–30 October 2026**. Observed regime counts: 1,643 inflationary-growth, 1,260 disinflationary-growth, 486 stagflation, 461 slowdown and 130 explicit market-only degraded sessions. Missing macro was not fabricated. All observations are retrospective, with design/universe choices made after historical data existed.

| Modeled cost per traded risky-asset dollar | CAGR | Annual volatility | Maximum drawdown |
| --- | ---: | ---: | ---: |
| 0 bps | 5.18% | 6.21% | -12.60% |
| 15 bps | 4.64% | 6.21% | -12.71% |
| 30 bps | 4.10% | 6.21% | -12.82% |

Annual turnover is approximately **345%** under this replay's strict risk-triggered rebalancing. Trading cost sensitivity is therefore material. These returns exclude verified client-specific fees, taxes and live execution effects and do not establish suitability or future profitability. Promotion remains disabled. Files: `var/dynamic-portfolio/evaluation-20261101/assessment.json`, per-cost CSVs and decision/fill trade logs.

All three cost runs were also reconciled through the separate existing accounting replay against every session's wealth, return, turnover and cash, with 780 fills per run and decisions strictly before fills. `reconciliation.json` records local numerical reconciliation and explicitly does not claim independent human review or release approval.

Final full acceptance passed **1,404 tests with zero failures/errors/skips**, repository-wide Ruff and JavaScript syntax checks. Fourteen workflow checks passed and eight prerequisites remained blocked. Retained report: `var/release-acceptance/runs/20261101T150326684317Z-e5b62d86/acceptance.md`. The audit confirmed that its bound source/input/dashboard/PDF and original ledger hashes stayed unchanged during validation. This does not certify the new managed-account foundation as integrated or live-ready.

Repository reconciliation recorded branch `main`, commit `7d214f7c96f35011fcd7a5b53f4e3d7c2786ca5c`, 43 modified/staged entries and 333 untracked entries at capture time. Counts are Git entries, not exact file counts. `var/live-upgrade/repository.json` explicitly records `clean_release: false`. No unrelated work was deleted, staged or committed.

`var/live-upgrade/status.json` leaves all 26 qualification items OPEN and execution disabled. It is a progress inventory, not a release gate. Full acceptance is retained under `var/release-acceptance`; check its latest report for post-change results.

## Remaining work and dependencies

1. Complete exact-design dynamic portfolio validation, dashboard/PDF integration and a separate prospective cohort.
2. Integrate authenticated account identity, account eligibility, instruments/quotes, position/FX/settlement accounting and fair allocation at production boundaries.
3. Implement sandbox broker transport against confirmed account/entity/API permissions, then test real outage, partial-fill, cancel-race and restart behavior.
4. Produce a clean reviewed source release and qualified Linux image/host, security/recovery/alert evidence.
5. Complete observation, reporting, browser, product and independent model/security review gates.
6. Qualify a limited founder-account pilot, followed by a separately approved client-account launch. FX/futures and additional African venues require separate releases.

External requirements remain: licensing/tax/client-country review, broker onboarding/sandbox entitlement, host access, verified financial inputs/data entitlements, actual later sessions and independent sign-offs. Developer access cannot supply these facts. No automatic promotion, broker calls, order submission, SMTP delivery or remote deployment occurs in this pass.
