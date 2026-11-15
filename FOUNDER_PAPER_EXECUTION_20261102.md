# Founder paper pilot execution — 2 November 2026

Status: **local engineering advanced; real broker and host qualification pending access details**. The owner reports both a paper Gateway and Linux Docker host are ready. Their protected configuration path, trusted CA path and SSH alias/address have been requested. That report is not recorded as a completed connectivity, host or trading qualification.

| Recommended step | Executed | Remaining |
| --- | --- | --- |
| 1. Essential engineering | Added reduce-only SELL checks at preparation and dispatch, pending sell reservations, signed opening book adoption, transactional position/carrying-cost/fee journals, explicit settlement confirmation and internal-book reconciliation. Default preparation requires a genuine validated production AuthorizedOrderIntent matching instrument, side, dimensions and decision provenance, rechecked at dispatch. | Qualification with actual broker feeds and production decisions; complete tax-lot, transfers, corporate-action processing and trade-bust/correction accounting are separate releases. |
| 2. Read-only broker connection | Attempted verified TLS portfolio discovery at the default local Gateway. Sandbox permission denial was distinguished from connectivity; the permitted read-only check then timed out. No account data or credentials were logged. | Supplied protected configuration/CA and actual paper endpoint/account binding; confirmed raw quotes, contracts, balances, positions and open orders. A timeout is not a successful broker observation. |
| 3. Paper lifecycle qualification | Ran synthetic integrated tests for BUY fills, fees, reduce-only sales, oversell prevention, duplicate and invalid events, settlement timing, unspendable unsettled proceeds and changed/missing production authorization. | Real authorized paper order, partial-fill/cancel/outage/restart evidence against the confirmed Gateway. No actual order or cancellation has been submitted. |
| 4. Reviewed release/image/host | Added minimal content-addressed managed release staging, default-nonexecuting pinned Docker recipe and CI build/test/scan/SBOM/image-retention workflow. Candidate import and integrity tests use staged sources and reject tampering. | Clean reviewed commit, actual Python 3.12 image build/scans, host connection and alert/recovery drills. Docker CLI is unavailable on this development machine; host availability is owner-reported pending SSH details. |
| 5. Genuine operating evidence | Preserved existing ledgers, continued local release acceptance, and recorded diagnostics separately from financial observations. | Actual completed-session broker observations, reconciled performance, completed-month delivery and independent sign-offs. Neither synthetic tests nor repeated same-session runs count. |

## Accounting semantics

- Opening books can be adopted once, while frozen, from a fresh matched snapshot explicitly bound by the signed permit. Existing open broker orders or unsettled opening cash require prior review; neither is silently imported. Unknown historical cost remains unknown.
- SELL is always reduce-only in this release. It cannot exceed the smaller of local-book and broker-reconciled holdings after conservative reservation for other pending sells. This is a controller-side check; real-world concurrent/manual trading and broker close-only semantics require qualification before live use.
- Fills require cumulative quantity, notional, fees and broker-reported trade/settlement dates. Event identity, quantity, journals and settlement records commit atomically. Invalid/future/regressive or unexplained events roll back and freeze the account for review.
- Cash available to buy excludes outstanding purchase payables and does not include unsettled sale proceeds. Settlement requires signed broker-confirmation evidence matching the stored settlement record and a due date, not merely passage of time.
- Signed permits require fee headroom. Buy reservations include the buffer; actual fees above it remain recorded and trigger an account freeze for review.
- Known carrying cost uses average cost rounded to eight decimal places; fees are expensed separately. It is not tax-lot reporting. Unknown-cost disposals are explicitly marked unverified rather than producing invented realized P&L.
- Reconciliation checks the submitted local snapshot against the durable position/cash/open-order book; matching two arbitrary snapshots cannot conceal book differences.

## Production-risk connection

The service defaults to `simulation_only=False` and refuses preparation without its trusted production authorization reader. The reader must supply an actual `AuthorizedOrderIntent`, which validates through existing classes. Dimensions and decision/risk provenance are fingerprinted; ordinary mutable OMS status/fill fields do not invalidate that immutable binding. Server-owned signed account/release/image permissions and current cash/quote/session checks still apply. This does not enable the existing live broker gate.

`simulation_only=True` exists for clearly synthetic module tests. Its intents cannot reach the actual Gateway HTTP writer. Test fixture authorizations, clocks, keys, fills and settlements are not operational approvals or account performance evidence.

## Reproduce locally

```sh
python3 -m pytest -q test_managed_positions.py test_managed_execution.py test_managed_api_evidence.py test_managed_boundary.py test_managed_release.py
python3 managed_release.py stage --destination NEW_UNIQUE_DIRECTORY --allow-dirty
python3 managed_release.py inspect --root NEW_UNIQUE_DIRECTORY
python3 release_acceptance.py
```

Focused verification: **31 tests passed**; repository-wide Ruff passed. Candidate staging is deliberately marked dirty/unqualified. The managed CI workflow is supplied but has not run remotely. No host was provisioned, no external alert/email sent, and no scheduler or broker writer enabled.

Additional final focused verification: **11 tests passed** for position accounting, release integrity and the protected read-only capture CLI. `python3 managed_probe.py --configuration PROTECTED_CONFIG_PATH` retains a private hashed snapshot without submitting orders. The configuration template is `deploy/managed-paper-capture.example.json`; its placeholders are not operational configuration.

Readiness diagnostics: `var/live-upgrade/connectivity-20261102.json`. They contain connection status and local Docker availability only, not account identifiers or credentials. The current managed source must be built from its **staged context**, not the full development directory. Container default execution verifies files and exits without starting a trading worker or public listener.

## Final verification

Full regression: **1,447 passed**, zero failures/errors/skips. Acceptance run `var/release-acceptance/runs/20261102T131525577356Z-0fa6c85f` reports engineering PASS, no failed checks and eight blocked prerequisites: financial evidence, completed-month coverage, actual monthly delivery, prospective observations, host/image/alert/recovery reviews, product/jurisdiction reviews, browser qualification and pinned runtime qualification. Source/input stability passed. Exit code 2 represents these unresolved prerequisites, not failed tests.

Verified source candidate: `var/releases/managed-candidate-20261102-v3`, identity `9bd4e8a986ec9590d1163ccd90773398538ca73f36008b0ab41610a8225ec71d`. It remains a dirty-tree review candidate, not an approved release. Ready operator infrastructure still requires the protected configuration path and SSH alias before read-only access can be verified. Zero actual broker orders have been submitted by this execution.
