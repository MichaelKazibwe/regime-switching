# Repair 1: exact-calendar macro data

Completed locally on 30 October 2026. Addresses audit finding A01 and repair step 1. Other audit findings remain open.

## Changes

- Added `macro_feature_contract.py`, shared by `TrainingMacro` and the current FRED overlay. CPI uses the exact current/12-month/3-month/15-month periods; unemployment requires six consecutive observed months; industrial production uses current/six-month endpoints.
- Missing required periods fail closed. Unneeded missing periods do not shift the endpoints or block otherwise valid calculations. Duplicate monthly periods, nonfinite observations and invalid required index values are rejected. Monthly freshness remains 90 days; individual and aligned Treasury inputs must satisfy the existing 14-day limit. Release-aware reader availability remains unchanged.
- Corrected current September 2026 CPI inflation from **4.023310% to 3.717251%**, and inflation momentum from **0.296780 pp to 0.253720 pp**. The corrected comparison months are September/June 2025, not August/May 2025.
- Current/revised historical feature rows that cannot satisfy the contract stay absent. The current quarterly AR(1) outlook fits only actual consecutive observed month pairs and samples only complete three-transition residual blocks. It never compresses a gap or invents an observation. Legacy historical feature inputs retain their full-calendar requirement. Forecasts remain conditional and unvalidated.
- The actual latest 120-calendar-month window has **115 observed feature months, 113 valid adjacent transitions and 109 eligible residual blocks**. Missing feature months are November 2025–March 2026. These are unavailable feature rows, not invented substitute observations or a claim that every underlying series is absent during those months.
- Added contract endpoint/version metadata, source hashing, and dependency inclusion in both relevant Docker recipes and the recommendation release source list.

## Regeneration and provenance

No new provider data were invented or downloaded. The same verified raw FRED snapshot retrieved on 30 October 2026 was reprocessed; original CSVs, retrieval timestamps and old derived features remain archived. The market capture remains through 30 October 2026.

- Corrected features: `var/macro-repairs/20261030T210915901130Z/features.json`.
- Provenance: `var/macro-repairs/20261030T210915901130Z/repair-manifest.json` and `var/macro-repairs/latest.json`.
- Source-bound retrained report: `var/strategy-training-runs/20261030T210916293673Z/training-report.json`.
- Default strategy launch bundle points to the new report and original verified market capture.
- All 20 strategy/forecast scenarios, four individual strategy PDFs, four investor-profile PDFs, the main investor PDF and saved dashboard aliases were regenerated. Quarterly scenarios cover 2026Q4–2027Q3.
- Saved client-plan payloads are unchanged (verified canonical hash). Frozen strategy metrics and classifier results are exactly unchanged. Risk parameters were not tuned; the predictive gate remains OFF. The current macro/quarterly scenario layer is separate from the older saved client plans.

## Validation

- Full suite: **1,293 tests passed**; Ruff passed.
- Nine new regression cases cover the incorrect CPI row-offset behavior, missing required CPI/UNRATE/INDPRO periods, duplicate monthly periods, stale aligned yields, current/vintage contract parity, and gap-aware quarterly fitting without bridged month pairs.
- Corrected actual-snapshot CPI and four quarterly forecasts verified; all 20 scenarios regenerated with source-matched training.
- Current `strategy_operations.audit` passes for the regenerated workspace, but its separate integrity weaknesses in A02–A04 remain open. This pass is not a repaired release approval gate.
- PDF regeneration and visual review use native PDFKit/CoreGraphics because Poppler and Node/the skill metadata helper are unavailable in this environment; no packages were installed.
- Existing prospective receipt 1/20 was not rewritten or incremented. It remains bound to its original run. Scheduler/observation integrity and requalification of receipts belong to later repairs, not this change.

Reload the saved dashboard. If a local calculation server is already running, stop and restart it so it reads the new matching launch bundle and payload. No service was deployed, trading enabled, public approval granted or new email sent.
