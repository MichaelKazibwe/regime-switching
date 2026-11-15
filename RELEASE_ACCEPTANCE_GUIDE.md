# Unified release acceptance

Run from the project checkout:

```sh
python3 release_acceptance.py
```

This is the canonical local acceptance command for the current recommendation/simulation workflow. It checks existing completed-session artifacts and performs isolated report and recovery exercises. It does not refresh prices, retrain/promote a model, start a service, deploy an image, enroll recipients, send email, place orders or append observations. Run the existing daily refresh/candidate jobs first when a newer market session is available.

Each execution creates a private directory under `var/release-acceptance/runs/`. It contains `acceptance.json`, `acceptance.md`, stage evidence, command logs, fresh regression XML, a monthly PDF and local `.eml` preview, and backup/restore exercise copies. `var/release-acceptance/latest.json` points to the latest completed report and binds its hash. Earlier runs are retained.

## What is checked

- Completed-session market capture, observed healthcare extension, training source hashes and input checksums.
- Dashboard portfolio identities, twenty independently recalculated macro scenarios, source-bound PDFs and payload/manifest integrity.
- The actual HTTP handler's unauthenticated denial, authenticated portfolio payload and cross-origin denial, exercised in-process without a listening server.
- Independent strategic benchmark and bootstrap recalculation; all four challenger trade replays, risk-matched controls and displayed evidence.
- Both immutable prospective ledgers, current decision dates, report/assessment binding, registered contract identity and next-close timing. Acceptance runs never increase observation counts.
- Daily-job monitoring receipts and deadlines.
- Completed-month PDF generation and exact MIME attachment binding, using an inactive `example.invalid` preview identity. NO_DATA/PARTIAL is retained rather than fabricated into a monthly return.
- Actual ledger/input backup and isolated restore with chain reconciliation. This is local recovery evidence, not a remote-host drill.
- Existing financial evidence, release/host/alert/recovery attestations and product-review gates when supplied.
- Actual completed-period monthly delivery evidence when available. This requires protected enrollment, a configured sender, unambiguous SENT records and matching recipient/attachment/summary evidence. The command never calls SMTP; acceptance by SMTP does not prove inbox reading.
- Pinned Python/dependency alignment, Ruff, JavaScript syntax and a freshly executed full pytest suite. A prior unrelated XML report cannot qualify this run. Tests skipped by `--skip-tests` remain BLOCKED.
- Source/input stability throughout the run. Concurrent or unexpected changes invalidate the run. Acceptance obtains shared nonblocking locks on existing daily/candidate job locks and its own exclusive lock.

Relative and absolute references to the same replay artifacts are normalized before comparison. Return/risk numbers and their underlying file hashes remain exact; no numerical tolerance is used to waive a replay disagreement.

## Status and exit codes

| Exit | Status | Meaning |
|---:|---|---|
| 0 | READY_FOR_OPERATOR_REVIEW | Every required check passed; this still does not approve release or enable recommendations/orders. |
| 1 | FAILED_CHECKS / INITIALIZATION_FAILED | A check failed, evidence is inconsistent/corrupt, or startup could not complete. |
| 2 | BLOCKED_PREREQUISITES | No failed checks, but required data, elapsed observation, runtime or review evidence is missing. |
| 3 | BUSY | Acceptance or a coordinated daily job is active; no existing report or observation is replaced. |

The report gives separate local-engineering status plus an individual priority, reason and next action for every blocker. Missing external evidence cannot be converted into PASS by a successful local test suite.

For a diagnostic run that skips the full test suite:

```sh
python3 release_acceptance.py --skip-tests
```

The regression gate stays blocked. The command still checks the saved workflow and exercises local reports/recovery.

## Supplying existing evidence

Optional arguments select protected evidence without embedding credentials in source:

```sh
python3 release_acceptance.py \
  --financial-evidence /protected/economics \
  --qualification-release /protected/current-immutable-release \
  --qualification-evidence /protected/qualification \
  --product-mandate /protected/pilot-mandate.json \
  --product-evidence /protected/product-review \
  --browser-evidence /protected/browser-review.json
```

These arguments reuse `economic_evidence.verify`, `paper_release.verify`, `paper_qualification.evidence_checks` and `productrelease.readiness`. A qualified release must contain the required current source versions and be clean. Attestations remain named human reviews with hashed supporting artifacts; the command does not manufacture them or treat them as independent proof of financial truth. A client mandate is used only by the existing product-review adapter when supplied; no fictitious client is created for a non-personalized preview.

`--recipients` selects the protected monthly enrollment file; `--monthly-delivery-root` selects the existing report/delivery evidence directory. Defaults preserve existing configuration. No paper-default subscriber is reassigned to the benchmark or new challengers.

The browser receipt schema is illustrated by `deploy/release-acceptance-browser.example.json`. Its placeholders are intentionally unapproved. A real receipt must identify the exact source snapshot, input bundle and dashboard, have a named reviewer and a valid review window of at most 31 days, cover the required interactions/viewports/failure states, and reference regular hashed artifacts confined to its evidence directory. A syntax parser cannot substitute for browser review.

## Deployment boundary

The command is a development/operator audit run against this checkout and its private verified artifacts. It is not added to runtime images that deliberately exclude test/development dependencies. CI can run its regression tests without private snapshots; full release acceptance requires the actual private bundle and ledgers. No packages, host or scheduler are installed by this command.

Fresh financial-period coverage and prospective observation are independent gates. The current minimum is 20 actual decision observations and 20 forward-return sessions in both cohorts. Passing that operational minimum does not establish alpha, suitability or durable profitability. Independent economic and product reviews remain required.

The legacy execution-worker qualification is separate: its existing 60-session/three-rebalance paper gate is unchanged. This recommendation/simulation audit cannot authorize a broker worker or waive that gate.
