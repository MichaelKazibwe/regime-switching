# Dashboard interaction and visual review — 2 November 2026

Updated the existing local investor workspace, preserving the financial payload, allocation contracts, saved client plans and PDF report bytes. Original HTML aliases and manifest were archived in `var/dashboard-review-20261102/original` before the presentation update. The current HTML was regenerated with its CSP script hash and artifact seal; no historical observation ledger was rewritten or approved.

## Changes

- Fixed the core-universe checkbox: switching between 26 core and 28 catalogue instruments now immediately updates the table.
- Added an authenticated, same-origin `/api/observations` endpoint with allowlisted runtime fields. Missing or unreadable ledgers show unavailable evidence. Its scorecard distinguishes no forward returns from measured zero performance.
- Added scheduler heartbeat, eligible session, decision/return counts and matured forecast scores. Runtime status refreshes every minute while the page is visible, with a manual refresh button. Failures retain explicitly dated values. This does not hot-swap the sealed allocations or promote research parameters.
- Added section navigation, a local-time clock, explicit daily-close market date, day/night controls, more legible typography, cards, tables, responsive styles and reduced-motion support.
- Added pointer and keyboard inspection to shared time-series charts: arrows, Home and End report dated values. Chart values, assumptions and financial calculations are unchanged.
- Included the runtime module in the relevant strategy/economic Docker copy lists. No Docker build or host deployment is claimed.

## Verification

Full regression: **1,454 tests passed**. Focused dashboard/macro/dynamic checks: 27 passed. Python static checks and JavaScriptCore syntax compilation passed. Runtime endpoint tests verify unauthenticated denial and same-origin enforcement.

Safari checks on the authenticated loopback service:

| Feature | Result |
| --- | --- |
| All sections: observations, dynamic, growth, engines, news, overview, portfolio, macro, training, performance, scenarios, risk, details | Opened and rendered |
| Universe filter | 26 → 28 instruments immediately, confirmed in the UI |
| Custom macro input | Changed disinflationary-growth input to 40; recalculated a custom scenario with reconciled capital/risk and separate scenario identity |
| Scenario PDF | Browser export generated a 12,443-byte PDF with valid signature in the scenario report store |
| Dynamic chart | Keyboard End showed `2026-10-30 · 2.05×` |
| Dynamic PDF | Triggered authenticated download without a displayed error |
| Live observation panel | Read actual recent scheduler heartbeat, one registered decision, zero forward-return sessions and no matured forecast scores |
| Day/night modes | Visually inspected; corrected hero-button and card contrast |

Desktop Safari was exercised; mobile-device rendering, every operating-system/browser combination and a release-bound independent browser qualification were not completed. Public news freshness depends on external feed availability. This review does not qualify execution, broker connectivity or investment performance.

The updated authenticated service was started on loopback port 8769; the older process on 8768 was not terminated. Reuse the private launch URL shown in this session or the authenticated Safari tab. Static file aliases show the refreshed design but cannot provide authenticated calculations or live runtime monitoring.
