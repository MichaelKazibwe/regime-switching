# Dashboard data and automatic refresh — 5 November 2026

> **Universe policy update (2026-11-17):** Current portfolios and strategies resolve a configurable global instrument registry, with no fixed ETF-count limit. Numeric universe counts below describe this document's historical implementation or experiment. See [the current global-universe policy](GLOBAL_ASSET_UNIVERSE.md).

The authenticated viewer runs on loopback port 8770. Its private launch URL is in `var/dashboard-service/manual.log`; do not share that token. Static HTML exports do not have authenticated live functionality.

| Sections | Data and refresh |
| --- | --- |
| Market snapshot, asset price charts | Latest verified adjusted daily closes for 28 instruments, through 4 November. Not intraday/executable quotes. |
| Macro outlook and trained strategies | Captured macro series, point-in-time training inputs, current FRED informational overlay and current validated scenario bundle. Rebuilt after a new eligible completed session. |
| Growth & Resilience | Current common-history benchmark, risk statistics and conditional simulations from observed prices. Fixed reference weights remain fixed. |
| Return engines | Current reconciled institutional assessment and robustness evidence. Unapproved research candidates. |
| Dynamic portfolio | Current contract, three-cost historical replay, independently reconciled numerical replay and contract-bound PDF. |
| Live observations | Original, institutional and dynamic ledgers plus scheduler freshness; polled every minute. |
| News | Public feeds, refreshed every five minutes; unavailable/cached feeds disclosed. |
| Saved profile overview, allocation, scenarios, performance, risk and details | Archived client illustrations retain their original valuation and PDF identity. Current market and macro overlays are separate; saved recommendations are not silently regenerated. |

The existing hourly `com.regime.live-observations` job now invokes `dashboard_publication.publish` after successful collection, including retries of publication when the completed session is already observed. Publication copies the core reports into a separate run, attaches current engine and dynamic evidence, verifies PDF/scenario bindings, then atomically replaces `var/dashboard-live/latest.json`. It never rewrites sealed cohort artifacts. A single-writer lock prevents overlapping publication. Repeated current-bundle publications reuse complete source-matched dynamic evaluations.

The server validates and swaps the entire financial application under its lock. Browser polling checks for a new training run every minute and on tab visibility; a new run reloads the verified workspace. Freshness, connection failure and rejected updates are labeled. News polling is independent. The Mac must remain awake, logged in and online for collection. No broker account feed, streaming quote subscription, trading or automatic parameter promotion was enabled.

Verification: full repository regression 1,484 passed; changed Python lint and JavaScriptCore syntax passed. All thirteen sections were opened in Safari. `verify_live_dashboard.py` checks authentication, common session dates, all cohort data, live-news status, all five portfolio PDFs and scenario exports. Receipt: `var/dashboard-verification/latest.json`.

The proposed `com.regime.investor-dashboard` login service was blocked by macOS Documents-folder policy before Python started. It was stopped and disabled; its prepared plist and installer are retained for review. The viewer currently runs directly, so automatic viewer restart after login is not qualified. Existing hourly collection remains enabled. Resolve macOS access through the user's normal settings before enabling the new login service; no security settings were bypassed.
