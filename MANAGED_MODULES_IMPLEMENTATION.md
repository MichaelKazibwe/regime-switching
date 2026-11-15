# Managed-account module inventory implementation

## Current P0/P1 result — 3 November 2026

See [P0_P1_STRENGTHENING_EXECUTION.md](P0_P1_STRENGTHENING_EXECUTION.md). The report pipeline was repaired and genuine observations advanced; bounded recovery, an independent local watchdog, weekly candidate research and whole-account pre-trade/dispatch risk checks were added. Local scheduler/watchdog/research services are enabled. Real paper preparation additionally requires measured whole-account risk inputs and signed policy limits; missing evidence remains blocked. Earlier inventory/test counts and statements that no scheduler is enabled are historical checkpoints.

## 2 November follow-through

The current paper path now supports signed-permission **reduce-only SELL** orders, one-time reviewed opening books, atomic position/carrying-cost/fee journals, explicit settlement evidence, and account-book-backed reconciliation. Real paper HTTP submission requires a matching validated production `AuthorizedOrderIntent`; synthetic module sessions are explicitly barred from that writer. See [FOUNDER_PAPER_EXECUTION_20261102.md](FOUNDER_PAPER_EXECUTION_20261102.md) and [MANAGED_PAPER_RUNBOOK.md](MANAGED_PAPER_RUNBOOK.md). Earlier inventory descriptions below are retained as the 1 November checkpoint, not current claims that these additions are absent.

1 November 2026. **Implemented and tested as an isolated PAPER integration. Not a qualified live platform.** Existing production live enablement, authorization, OMS, portfolio accounting and broker routes remain unchanged. No broker session was opened and no real order, cancellation, alert or email was sent.

## Inventory coverage

| Requested module responsibility | Implementation | Boundary / outstanding qualification |
| --- | --- | --- |
| Broker-specific transport through existing interface | `ibkr_paper_orders.py`: IBKR account-bound limit-order payloads, single-order cancel, TLS loopback HTTP writer disabled by default, demo and trading-account discovery; `managed_transport.py`: implements existing `livebroker.BrokerTransport` and only dispatches a matching prepared Order | Initial BUY/LIMIT/DAY stock/fund paper scope only. Actual broker authentication, advisor permissions, sandbox failure drills and eventual live implementation remain unqualified. No warning auto-confirmation, suppression, wildcard cancel, remote endpoint or live account allowed. |
| OMS persistence / recovery | `managed_execution.py` uses `ManagedPaperStore` outbox plus durable broker-ID/event tables, event hashes, idempotency, cumulative-fill checks, crash recovery and UNKNOWN quarantine | A claimed submission is committed before I/O. A timeout or crash cannot auto-resubmit. Broker-confirmed unknown-order binding requires a signed account/release permit and leaves the account frozen pending reconciliation. |
| Broker snapshot and exposure reconciliation | `managed_adapters.py` normalizes paper cash, settled cash, positions and explicit open-order data. Coordinator compares account-bound fresh snapshots and corporate-action state | Missing corporate-action review defaults to None and cannot reconcile. Unknown actions/differences freeze the account; no split/dividend or missing fill is invented. These are reconciliation controls, not complete position/settlement/tax accounting. |
| Executable quotes and instruments | Existing `InstrumentContract` plus `raw_quote`: contract, currency, quote-unit, bid/ask, time, source, lot and tick contracts | Adjusted historical prices denied as execution quotes. Explicit GBX versus GBP handling. Actual vendor entitlements, verified contract master and regional exchange integration still required. |
| Account-bound pre-trade limits and release identity | Signed, expiring PAPER permits bind tenant/account, release ID, image identity, currency, mandate and reviewed evidence; checks quote age, regular session, spread, order/open notional and reconciled settled cash | Pending orders count against cash; permit/quote/reconciliation/cash are rechecked at dispatch. This does not replace the existing production portfolio-risk authorization or constitute a fully implemented live daily/portfolio limit policy. No real approval key or permit was created. |
| Operations controls | `managed_operations.py`: role-bound freeze, cancellation supervision, fresh-reconciliation/signed-permit resume and heartbeat assessment | Cancelling is distinct from cancellation confirmation. CANCEL_PENDING/UNKNOWN prevents resume. External delivery, host monitoring, independent kill-switch and recovery drills remain open. |
| API identity and tenant boundary | `managed_api.py` resolves opaque sessions and exact account grants; quotes, permits, readers and transports are server-owned, not client payloads | No listener/public login is started. Production MFA/OIDC, TLS hosting, durable revocation, privacy/key controls and independent security testing remain required. |
| Source/image/account qualification evidence | `managed_evidence.py` validates signed reviewer receipts against current managed source identity, immutable image digest, account, time window and contained artifact hashes | Missing/altered/expired/wrong-scope or duplicate evidence blocks. Even a complete synthetic test set yields only READY_FOR_INDEPENDENT_PAPER_REVIEW, with execution and release approval false. No genuine external qualification receipts exist. |
| Dynamic evaluation / common contracts / cohort | Existing exact-design replay/reconciliation, `dynamic_preview.py`, `dynamic_forward.py` and bound dashboard/PDF | Preserved unchanged in this pass. One observation/zero forward sessions at registration; model/forecast simulation acceptance and observation period remain open. |

## Integrated paper path

Verified application identity -> explicit account grant -> server-owned instrument/quote/permit -> fresh matched account snapshot -> signed limit/cash checks -> transactional PAPER_PENDING -> committed DISPATCHING -> account-confirmed IBKR paper adapter -> broker-ID mapping -> deduplicated execution events -> fresh reconciliation before further activity.

The legacy BrokerTransport bridge rejects unprepared orders and changes to ticker/contract mapping, side, quantity, limit price or time in force. It reports local event state explicitly as local; it does not mislabel cached state as a fresh broker query. Nothing automatically registers this adapter with a production broker router or enables `LiveBroker`.

An unknown send is quarantined, not retried. A reviewed broker-ID binding is not evidence that a trade filled; actual broker events and account reconciliation are still necessary. Cancellation acknowledgement leaves CANCEL_PENDING. Late complete fills after a cancel are recorded; regressive, excess, duplicate-conflicting, wrong-account and unknown-order events are rejected.

## Tests and reproduction

```sh
python3 -m pytest -q test_managed_execution.py test_managed_api_evidence.py test_managed_adapters.py test_managed_boundary.py test_managed_accounts.py test_ibkr_paper_probe.py
python3 -m ruff check .
python3 release_acceptance.py
```

Focused result: **42 passed**. Tests cover API-to-paper-adapter-to-event lifecycle, cross-account denial, signed limits and reviews, server-owned inputs, settled/pending cash, stale quotes, GBP/GBX units, ambiguous send/restart quarantine, warning replies, partial/cancel/late-fill sequencing, conflicting events, corporate-action review, reviewed resume, changed artifacts and default-denied HTTP submission. Synthetic data, keys, reviews and fake writers exist only in tests; they are not broker or investment performance evidence.

Final release audit: **1,436 tests passed, zero failures/errors/skips; Ruff and JavaScript syntax passed**. Fourteen acceptance checks passed and eight prerequisites remained blocked. Sources, financial inputs, dashboard/PDFs and original ledgers stayed unchanged during the audit. Retained report: `var/release-acceptance/runs/20261101T183938035220Z-bcbae38b/acceptance.md`. Machine-readable module/source evidence: `var/live-upgrade/managed-modules.json`. Neither report grants live execution authority.

The HTTP writer is implemented but **not configured or exercised against a real Gateway**. If a qualified operator later supplies it, it accepts only TLS `https://localhost:5000`, a confirmed DU demo account and the two supported paper order endpoints. Authentication remains manual/externally qualified. The `submission_enabled` flag is an operator configuration, not sufficient authority: the supported service path still requires all account/session/permit/reconciliation checks. Do not expose the writer directly to clients.

## Remaining to go live

Actual advisor/licence/client-country approvals; broker sandbox access and recorded gateway tests; SELL/reduce-only and broader products; complete positions, fees, FX, settlement/corporate-action and tax accounting; production risk authorization integration; production MFA/security and managed-platform packaging; clean image/host, alerts/recovery; real observation/reporting history; independent model/security/operations approval. Existing eight release prerequisites remain applicable. No account or geographic permissions are inferred from source code or test results.

IBKR API references: [submission](https://ibkrcampus.com/docs/web-api/api-reference/trading/trading-orders/submit-new-order), [cancel](https://ibkrcampus.com/docs/web-api/v1/endpoints/orders/cancel-order), [warning confirmations](https://ibkrcampus.com/docs/web-api/v1/endpoints/orders/place-order-reply-confirmation). The implementation does not auto-confirm those warnings.
# Genuine market observation update — 2 November 2026

See [LIVE_OBSERVATIONS.md](LIVE_OBSERVATIONS.md): actual public data capture, isolated classifier training and an integrated daily shadow validation command are available. Market observations do not qualify broker fills or client execution. Gateway/host checks are deferred at the owner's request; no scheduler or order execution is enabled.
