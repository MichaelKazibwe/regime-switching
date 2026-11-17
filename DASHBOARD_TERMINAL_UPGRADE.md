# Interactive research terminal — 15 November 2026

Deployed locally at `http://127.0.0.1:8782/#benchmark`, with the existing operator account and private state preserved. Final source candidate: `ee916d9bd52f889bde443489246a5e441cb427995f0f4d27f591a45549c49bd1`; image ID: `sha256:c0f036f49726ab37a2ae74ab332ebb7031b0e9bca9cfeeced9a7f060d3859649`.

## Cycle calculations

Previously the selector changed the graph and explanatory text while the prominent cards showed fixed reference/historical statistics. The new six-card scenario summary uses the selected cycle's median return, median ending wealth, 5th-percentile return and wealth, 95th-percentile return, path drawdown percentile and simulated frequency of an ending loss greater than 10%.

The illustration amount scales wealth, holding values, shock dollar impacts and chart units. A second-cycle selector overlays its median and compares return/drawdown outcomes. Wealth/return modes, pointer and keyboard inspection, searchable holdings, expandable allocation and a numerical comparison CSV are available. Cached data prevents repeat benchmark fetches during navigation. A late response cannot overwrite another view's identity.

Reference weights, covariance risk shares, cash percentage, instantaneous shock assumptions and the held-out evaluation are explicitly separated. They remain fixed because the saved scenarios stress one reference allocation; no unverified cycle-specific optimized weights are invented. The existing benchmark remains dated November 12, with market closes through November 13. Charts and simulations are not streaming quotes or calibrated promises.

## Navigation and appearance

Fourteen separate destinations were consolidated into ten views across five groups:

| Group | Views and consolidated content |
|---|---|
| Workspace | Overview with saved-plan scenario comparisons; holdings |
| Strategies | Dynamic strategy; Growth & Resilience; return engines with model training/evaluation |
| Explore | Cycle lab; macro outlook; historical analysis |
| Intelligence | Market news |
| Risk & evidence | Risk, forward observation monitor and saved plan assumptions/identifiers |

Additional changes include a global search palette (Cmd/Ctrl+K), clickable market summaries with observed-price sparklines, a working brand/home link, grouped tabs, stronger typography, a new violet/ink palette, light/dark themes, responsive controls and motion that respects reduced-motion preferences. Mobile prices stay on one line, chart text is drawn at readable device-aware sizes, and long holdings tables scroll within their cards. Related material remains accessible in expandable sections.

The design references included [eToro's consolidated terminal](https://www.etoro.com/news-and-analysis/etoro-updates/finally-the-trading-terminal-that-shows-everything-on-one-screen/) and [Trading 212's portfolio charts](https://helpcentre.trading212.com/hc/en-us/articles/22435640547613-Portfolio-Charts). The intended distinction is traceable cycle research and comparison, rather than simulated live trading. No independent head-to-head usability study, broker latency benchmark or investment-performance superiority is claimed.

## Verification and rollout

- Chromium and WebKit passed desktop and 390-pixel mobile checks in the exact final Linux QA source: all ten views, eight cycle metric cases per browser, preserved reference weights, amount scaling, comparison CSV, interactive chart units/inspection, grouped navigation, search, brand navigation, light/dark display, saved/custom PDFs, logout and viewer controls; zero page errors.
- The redesigned calculation/data path passed **190 numerical/source checks**, and **1,252 rendered-value comparisons plus 34 exports** passed in Chromium/WebKit. The subsequent final-navigation-only source delta was confined to `pilot/workspace.js`; final Linux browser acceptance covered that delta.
- Ten authentication/backend tests passed; JavaScript syntax, repository Ruff and Git whitespace checks passed. Numerical forecasting, optimization, portfolio contracts and ledger sources were not changed.
- Navigation was measured locally, not against competitors. Native-browser median switches were approximately 26 ms Chromium / 84 ms WebKit; the final Linux run measured 109 ms / 38 ms, with a 963 ms maximum Chromium transition. These are limited local functional-run timings, not a controlled capacity or latency qualification.
- The operator's account metadata was checked before/after rollout. A private SQLite backup and prior image configuration were retained. Final deployed preflight passes all nine runtime checks. Safari was refreshed under the existing operator session, and changing the cycle visibly changed the figures.

Evidence, screenshots, exports, source identity and rollback configuration are under `var/pilot-qa/20261115-terminal-final/`. Research inputs and model activation gates are unchanged. Firefox remains subject to its existing QA browser failure; the external security, SBOM, domain/HTTPS and off-host recovery requirements remain open. This local UI upgrade does not approve an external financial service.
