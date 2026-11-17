# Daily macro monitoring

Explore → Macro outlook (`/#macro`) starts with verified daily observations and their calendar-quarter aggregates. The earlier macro dashboard was tied to an archived 2025 plan; it is now inside **Archived plan-date macro context & conditional quarterly scenarios**, rather than presented as current monitoring.

## What updates

The monitor follows the verified daily snapshot installed by the daily publisher. Its source is the same capture and training bundle as the current dashboard. The server checks their hashes and numerical-source match, caches results for that daily revision, and recomputes when a new revision is applied. An open Macro outlook checks every minute and when returning to the tab. The current selected quarter can also be refreshed manually.

Eight calendar quarters of daily context are available. Selecting a quarter updates its daily rows, latest included indicator cards, coverage and compounded SPY reference return. Clicking a quarter in the aggregate table selects that quarter. CSV downloads the selected daily rows; JSON exports the complete monitor, release dates, coverage and source hashes.

## Availability and missing data

Each session uses ALFRED vintages that were available at that decision timestamp under the existing conservative policy: a date-only release becomes usable at the following New York midnight. A later release or revision cannot appear in an earlier session. Historical rows are reconstructed from the captured vintage archive, not a live-issued forecast ledger.

Unemployment, CPI and industrial production are monthly series. Their last available observation repeats between releases, with its actual observation date and availability timestamp retained. **Carried forward** means unchanged daily context, not a new monthly measurement or an imputed missing calendar period. New or revised inputs are identified separately. Monthly context older than 90 days and Treasury observations older than 14 days are unavailable under the existing freshness policy.

The combined macro state remains unavailable when required feature history is missing, even if individual headline readings are available. In the initial November 13 capture, raw CPI is available but a required historical CPI calendar period is missing, so the combined signal is explicitly blocked. No neutral regime or quarterly forecasting probability is substituted. The selected-session quality banner and daily state column disclose this distinction.

## Quarterly meaning

Quarterly indicator means are equal-weight averages of available daily as-known contexts. They are monitoring statistics, not sums, independent release averages, official quarterly publications or conditional forecasts. Missing values are excluded; per-series observation counts and distinct observation/vintage counts are in the JSON. Repeated monthly readings count as daily context, not additional independent releases.

Combined macro coverage uses valid macro sessions divided by expected NYSE trading sessions through the snapshot date. Missing sessions are disclosed. Current-quarter rows are marked **Quarter to date**; earlier quarters are historical. The SPY reference compounds adjusted-close daily returns, with no fees or tax, only if all expected sessions and returns are present. It is not a client portfolio result. Treasury spread uses aligned 10-year and 3-month observation dates and is expressed in percentage points.

Archived quarterly scenario forecasts remain separate. Daily monitoring does not activate forecasts, alter saved portfolio mandates, promote a model or enable orders.

## Validation

Focused tests cover causal release/revision availability, stale raw series, missing values and sessions, quarter boundaries, compounded returns, coverage, authentication and daily refresh. Independent reconciliation checks compare every quarterly mean, coverage count and market-return product against its daily rows. Browser acceptance checks all eight quarters, row dates and values, selected-quarter CSV export, archived-section labelling and desktop/mobile layouts in Chromium and WebKit.
