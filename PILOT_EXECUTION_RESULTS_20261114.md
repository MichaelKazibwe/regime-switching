# Completed execution evidence — 14 November 2026

The research improvements, balanced cycle benchmark, local backend/frontend acceptance and portable candidate staging completed. The system is prepared for an invited Linux research pilot, subject to the deployment checks below. It has not been deployed remotely or qualified for live investment execution.

## Tests and release

- Full regression: **1,525 passed, zero failures/errors/skips**, 141.285 seconds. Receipt: `var/pilot-qa/20261114-full-regression.xml`.
- Final authentication/backend unit run after the last service changes: **10 passed**, 40.39 seconds. Receipt: `var/pilot-qa/20261114-final-pilot.xml`.
- Final real-HTTP authenticated backend smoke passed every check, including current data, all modules, PDFs, scenario accounting, access denial and session revocation: `var/pilot-qa/20261114-final-backend/acceptance.json`. Its local software/data readiness flag does not replace the external deployment gates below.
- Final Chromium and WebKit acceptance passed at desktop 1440×1000 and mobile 390×844: all 14 sections, eight benchmark scenarios, JSON/PDF downloads, custom scenario calculation, viewer restrictions and logout, with no page errors. Receipts/screenshots: `var/pilot-qa/20261114-final-v2/`. Two real mobile overflow defects and PDF control contrast were corrected during these runs. Workspace loading assertions allow the actual verified-data load time.
- Firefox acceptance is **blocked**, not passed: the installed macOS headless binary exits at launch with `Could not find profile folder`, even with canonical temporary paths. Require Firefox acceptance on the exact Linux deployment build before claiming three-browser coverage.
- Pilot source lint and `git diff --check` passed. No Docker executable is available locally, so Linux image build, scan, SBOM and remote CI remain unexecuted requirements.
- Portable candidate: `var/pilot-release/20261114-final-candidate/`, source release ID `00fe6ebaf4765be792f2eae8140d5017767ce54c96bbb78c8f85865f1ec79b85`. Source context and private snapshot hashes verified; relocated numerical/PDF bindings loaded all four investor plans. Current snapshot session: **2026-11-13**. The extensive dirty repository makes this a **CANDIDATE**, not a reviewed-source release.
- Warm-start import acceptance: `var/pilot-qa/20261114-import-acceptance.json` returned `IMPORTED_SESSION_READ_ONLY`, zero new observations and the existing chain head. An initial local check supplied the staging directory instead of a container-equivalent root and failed; the corrected root layout passed. No imported session is counted as a new forward observation.

## Research outcome

All performance workstreams finished in `var/performance-improvements/complete-20261114/`. The fixed-calendar forecast has 20 scheduled origins, 17 scored: Brier 0.7576 versus frequency 0.7430, and its uncertainty gate fails. Selected portfolio paths did not pass their declared improvement screens. Therefore no predictive or allocation candidate was automatically promoted, and no return advantage is claimed.

The new cycle benchmark searched 27 balanced risk/volatility/drawdown configurations with separated validation/test windows and independent accounting. Selected reference: `inflation_diversified-0.08-none`. Frozen held-out return 3.22%, annual volatility 2.52%, maximum drawdown −1.69% at 15 bps costs. Latest separately refitted allocation holds 51.11% uninvested cash; its historical test is not the performance of those latest weights. Eight business-cycle/regime paths are simulations, not forecasts or guarantees. See `CYCLE_BENCHMARK_GUIDE.md` for allocations, signed risk contributions and shock results.

## Remaining deployment gates

Follow `WEEKEND_PILOT_DEPLOYMENT.md` in order: review/commit source and restage; build/scan the exact Linux image; configure VM/domain/TLS and immutable image digests; install private snapshot and credentials; create individual invitations; pass external authenticated acceptance and Firefox checks; verify collection and enable the timer; prove encrypted off-host backup/restore and rollback; then open the invited test.

No cloud host/domain credentials were supplied. No cloud resources, external invitations, public publishing, live orders, or financial promotions were executed. The existing market observation scheduler remains separate from the disposable QA servers.
