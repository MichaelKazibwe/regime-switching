# Institutional workbench upgrade execution

Started 24 November 2026 against the recommendations in the feature and UX audit.
This register separates implemented software, measured acceptance and external
qualification. It does not certify an institutional investment service.

## Release boundary

Development is isolated on `institutional-upgrade`. The existing loopback pilot
continues to use its earlier qualified image until the replacement passes its
release gates. Research reviews create no orders, public recommendation approval
or model promotion. Preserve every original observation cohort and report.

## Execution register

| Recommendation | Implemented change / next acceptance |
|---|---|
| Optional ticker failure | Both current dynamic paths use the shared eligibility contract. Regression covers a valid panel with the excluded ticker absent. |
| Portable protocol identity | Canonical logical source names replace absolute identity keys. Relocation and source-mutation tests pass. Source changes require a new prospective cohort; earlier ledgers remain immutable. |
| One portfolio context | `portfolio_workspace.py` supplies proposal type, price/context dates, currency, costs, model identity, revision and exact review revision. Shared Home/Analysis selection. No funded performance is invented. |
| Semantic change log | Compare target weights only across the same portfolio/model/basis. New revisions with unchanged targets say unchanged. Missing/corrupt prior evidence is unavailable. |
| Home and navigation | Compact Home, Portfolios, Analysis, Intelligence and Research library. Archived plans explicitly labelled. Market ribbon appears with market intelligence. Critical update warnings remain visible. Browser acceptance pending. |
| Progressive disclosure | Capital visual, three primary metrics and review needs first; detailed methodology, identifiers and holding rationales expand on demand. Full research tables/PDF retained. |
| Review lifecycle | One exact-revision target contract and actor-scoped immutable review history. Viewer cannot submit decisions; research acceptance never authorizes execution. No organizational roles or approvers are invented. |
| Data/model inventory | Source-bound catalogue exposes model identity, input evidence and explicit unassigned ownership, missing independent validation and unresolved rights/reconciliation. Hashes are not data licenses. |
| Underlying exposures | Optional reviewed holdings manifest validates source hashes, availability/review cutoffs and explicit policy limits. Assessments are sealed into weekly research and PDF. Unknown coverage stays unavailable. Post-optimization review checks do not claim look-through-aware optimality. |
| Optional sparsity failure on genuine data | Retain a feasible dense market optimum when optional support reduction fails; all bounds, diversification, cash and signed risk-share limits are independently rechecked. Nonfinite solutions are rejected. The November 24 replay now completes. |
| Publication performance | Identical causal context/allocation decisions shared within one three-cost historical evaluation. Holdings, fills, fees and NAV stay independent; exact numerical equivalence tested. Full historical validation still runs and has not been bypassed. |
| Financial accounting | Existing account journals/risk envelope remain authoritative. Weekly proposals have no linked account history; no synthetic attribution or live-account return claims. Further connected reporting requires a qualified account/feed. |
| Security, operations and recovery | Retain non-root container, authentication, isolation, writer locks and rollback. Final exact-image scan, current market/source checks, browser acceptance and deployment receipts remain release requirements. Existing operational diagnostics remain in Research evidence. |
| Documentation and ownership | README dated limitations corrected; this register is the current upgrade handoff. Human responsibility remains UNASSIGNED until explicitly designated. Historical phase documents remain history. |
| Expanded assets / live authority | Existing global registry eligibility remains the boundary. New assets, currencies, venues, advisory and live trading require their own data, mandate and operational qualification; this upgrade grants no authority. |

## Verification recorded so far

- Initial integration/regression batch: 45 passed.
- Initial full backend checkpoint: 1,527 passed in 121.59 seconds.
- Integrated backend run: 1,530 passed in 153.58 seconds.
- After the genuine-data optimizer repair: all 1,532 tests passed in 171.27 seconds; JUnit and logs retained privately.
- Shared replay decisions: exact equality with independent 0/15/30 bps runs,
  including trades and fee-dependent NAV; causal fill-day mutation test retained.
- Exposure/context/weekly focused batch: 38 passed.
- Python lint and whitespace checks pass at the intermediate checkpoint.
- Rendered the updated PDF allocation and holdings-evidence pages; inspected legibility and alignment.
- Native security build: official backports applied and actual linked TLS 1.2/1.3 trusted handshakes passed. Final image scan remains pending.
- Genuine capture, training, report, benchmark, weekly research and daily artifacts prepared for the completed November 24 session. Historical forecast/observation approval is not inferred from these builds.
- Chromium/WebKit final acceptance, exact image security, GitHub and rollout: pending.

Tests using synthetic data verify software behavior only. They are never counted
as genuine market outcomes, data-provider qualification or forecasting advantage.

## Holdings evidence input

`weekly_portfolios.py --lookthrough-root PRIVATE_DIRECTORY` optionally consumes
`manifest.json` with `schema_version: 1`, `execution_enabled: false`, `records`
keyed by symbol, explicit `limits` for issuer/country/currency/sector,
`minimum_coverage` and `max_age_days`. Each record supplies `as_of`, aware
`available_at` and `reviewed_at`, an identified `reviewer`, local `source_file`
basename, `source_sha256`, and normalized `constituents` with weight and all four
exposure dimensions. Retain original issuer/provider material beside the manifest.
Do not put private holdings or credentials in Git. No implicit policy approval,
independent authentication or trading authority follows from loading these files.

## External completion criteria

The following cannot be completed by filling a software field: independently
qualified prices and point-in-time membership/corporate-action/FX histories;
licensed issuer holdings and reviewed concentration limits; independent model
validation and genuinely matured prospective outcomes; human owners/approvers;
owner MFA and separated recovery keys; independent-device restoration with agreed
RPO/RTO; representative user task study; remote TLS/firewall/identity and service
qualification if the audience expands. Official macro authorities qualify their
own series, not global securities returns. No paid service is required or created
by this upgrade. These gates stay closed until real evidence is supplied.
