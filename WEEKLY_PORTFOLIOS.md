# Weekly portfolio research

The invited-user dashboard has a **Strategies → Weekly portfolios** view (`/#weekly`). It compares short (3 months), medium (1 year) and long (3+ years) research allocations. These are review-required candidates, not orders or approved client allocations.

## Inputs and allocation

Only a fully completed NYSE trading week is eligible, with a 15-minute publication buffer. Holiday weeks use their actual final session. The worker waits for a verified, source-matched daily capture covering that session. It takes the last actual close of each week without filling missing asset prices. An asset needs 156 complete weekly returns. The initial supported universe is the existing verified USD-listed ETF catalogue, excluding the composite benchmark ALLW and the benchmark-only XLV extension. No leverage, shorts or unverified extra instruments are introduced.

The three constrained utility fits use 104-week covariance with 30% diagonal shrinkage, clipped/shrunk mean and momentum estimates, historical weekly tail-loss and drawdown penalties, and concentration penalties. This is a numerical local constrained solution, not proof of a global optimum or future forecasting advantage. Policy constants are disclosed rather than selected using a held-out performance claim.

Each risky asset is capped at 20%. Combined sector satellites are capped at 25%, and XLF/KIE together at 15%. At least half the equity allocation is in SPY/VEA/VWO, and at least one fifth is in VEA/VWO/EWJ. These constraints limit overlapping mandates; they do not replace underlying holding or country look-through. Equity ceilings are 35%/60%/75%, and cash floors are 15%/5%/2% by horizon. Credit, real assets and managed futures have separate caps. Geographic labels describe fund mandates; some US-labelled funds have overseas economic exposures.

The allocation table shows capital weights, illustrative dollars, signed covariance risk shares, exposure labels, observed 26-week returns and volatility, and the reason each holding is included. Changing the holding period changes all candidate-specific tables and metrics. Changing the amount scales illustrative dollars; it does not personalize suitability or change the report's percentage allocations.

## Outlook, replay and stress

The monthly, quarterly, annual and three-year outlooks use 4/13/52/156 weeks. One thousand joint four-week observed blocks preserve within-block asset dependence. Current target weights remain fixed, with weekly self-financing rebalancing and 15 bps cost on risky dollars traded, including entry. Cash earns zero; tax and FX conversion fees are excluded. Reported quantiles and simulated loss frequencies are **uncalibrated conditional scenarios**, not assured market predictions or loss limits. Weekly drawdowns omit intraweek losses, and the short sample can substantially understate tail risks.

Historical replay fits only information available at each decision, then fills at the following weekly close. The first 104 weeks are used for training, and the final 52 for causal replay. The same cost/timing convention is applied to the 60% SPY / 40% IEF reference. There is no untouched policy-selection holdout, so these results do not establish future outperformance. Static worst-quarter diagnostics reuse the fit sample and are labelled accordingly. Declared slowdown, inflation/rate and liquidity shocks are assumptions, not forecasts of a business cycle. Missing validated macro inputs never become invented regime probabilities.

## Automation and publication

`scheduled_weekly_portfolios.py` runs hourly as the Mac login agent `com.regime.weekly-portfolios`. It publishes once per completed week and numerical source identity. It deduplicates repeated hourly checks, permits two generation attempts per identity, holds a process lock and bounds each numerical child to 30 minutes. Daily capture agents, the Mac and the local Colima VM must be running. This is local pilot automation, not an always-on remote service.

Artifacts live under ignored `var/weekly-portfolios/runs/`. A revision includes JSON, a detailed PDF, exact file hashes and numerical source hashes. The publisher transfers a complete revision to the dedicated `regime-pilot-local-weekly` Docker volume, verifies it with the installed image, and only then atomically changes `published/latest.json`. The app mounts this volume read-only at `/app/weekly-research`; account state and the immutable daily research snapshot are separate. A source mismatch blocks publication, while generation failure leaves the previous revision intact. The authenticated API marks a prior week stale instead of presenting it as current.

Commands from the project root:

```sh
.venv/bin/python scheduled_weekly_portfolios.py --publish-vm
launchctl print gui/$(id -u)/com.regime.weekly-portfolios
sh deploy/pilot/local-vm.sh status
```

Inspect ignored `var/weekly-portfolios/latest.json`, `worker.log`, `launchd.stdout.log` and `launchd.stderr.log` for generation/publication status. After a numerical source change, rebuild and test the app image before publishing the new revision. Do not bypass a source mismatch or modify sealed inputs.

## Downloads and review

The dashboard offers the detailed PDF and complete JSON. The PDF includes all three weekly allocations, projections, stress and replay, per-holding explanations, geographic mandate tables, and the bound saved-dashboard plans, growth-reference metrics and model availability. Existing saved-plan PDFs and complete cycle-lab evidence remain separately downloadable with their original identities. News is context, not an optimizer input.

Before adopting a candidate, review product access, jurisdiction, tax, liquidity, currency, overlapping exposures and ability to bear losses. The application deliberately records no automatic client approval and has no new order route.

## Validation

Numerical tests cover concentration and cash constraints, holiday and early-close eligibility, no forward-filling, deterministic projections, exact self-financing entry cost, traversal rejection, complete source manifests and tampered identities. HTTP tests cover authentication and unavailable/tampered evidence. Browser acceptance checks all horizons against saved JSON, amount scaling, desktop/mobile layouts and actual PDF downloads, in addition to the existing dashboard checks. PDF pages are rendered and visually inspected.
