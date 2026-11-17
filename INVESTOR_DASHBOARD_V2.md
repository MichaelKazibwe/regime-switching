# Investor dashboard V2: allocation, macro outlook and risk

> **Universe policy update (2026-11-17):** Current portfolios and strategies resolve a configurable global instrument registry, with no fixed ETF-count limit. Numeric universe counts below describe this document's historical implementation or experiment. See [the current global-universe policy](GLOBAL_ASSET_UNIVERSE.md).

Implemented at the owner's request after the V1 design freeze. This is a new reviewable interface, not a public investment-release approval. V1 source hashes are retained separately.

## What changed

- **Complete 26-ETF core map:** every core instrument appears, including zero weights. The preservation example really holds only SHY and SGOV plus cash; a full universe is not the same as 26 nonzero positions. The separate 28-instrument menu includes conditional DBMF and benchmark-only ALLW. No holdings or risk limits were changed to make a larger count appear.
- **Allocation source control:** compare selected investor-plan weights with the actual archived diversified research target (27 October 2025). The research column/map is explicitly not the selected investor recommendation. Both disclose cash separately.
- **Macro intelligence:** industrial-production growth, CPI inflation, inflation momentum, unemployment momentum and the 10Y-minus-3M Treasury curve; units, source observation periods, available-at time and historical sparklines are visible.
- **Two economic clocks:** choose the macro state at the original decision date or the latest supplied FRED snapshot. Latest information does not relabel the saved 29 October 2025 portfolio or recalculate its projections/eligibility.
- **Four-quarter outlook:** select any indicator to see conditional medians and pointwise 5th-95th ranges. Regime scenario frequencies and qualitative strategy review lenses are presented for each quarter. The first target is the upcoming quarter end, so its remaining horizon may be shorter than three months.
- **Risk and performance:** historical fixed-weight wealth, drawdown, 63-session annualized volatility, daily historical VaR/ES, signed saved variance shares, quarter outcomes by starting economic regime, macro/return correlations and regime-weighted historical quarter scenarios.
- **Investor PDF:** per-plan four-page reports include all 26 core assets, extended instruments/cash, the separate research allocation, latest macro indicators/quarterly ranges, strategy guidance, risk charts and macro/portfolio scenarios.
- **Monthly PDF integration:** shared paper reports can attach point-in-time reporting-month context and a separate latest-macro appendix. Report identity includes the summary contents; the new report schema is version 2. Sending still requires the existing explicit `--send` workflow and delivery checks.

## Current source snapshot

The current FRED retrieval was captured on **30 October 2026**. UNRATE, CPIAUCSL and INDPRO observations extend to September 2026; Treasury observations extend to 28 October. These are publication-lagged economic observations, not streaming market quotes. The latest overlay projects conditional released-feature scenarios for **2026 Q4 through 2027 Q3**.

Raw files, manifest and derived features are private under `var/investor-current-macro/`. No API key is embedded in HTML, PDFs, CSVs or console output. New repeated captures use immutable timestamp directories:

```sh
python3 investor_macro_feed.py --output var/investor-macro-snapshots
```

This command accesses FRED using the protected existing configuration and prints the new `features.json` location. It is a one-shot capture; no recurring timer is enabled by this work. Provider failures do not create a completed feature snapshot.

Current FRED historical observations contain revisions available at retrieval time. Every derived feature row therefore carries that retrieval timestamp, even when its observation period is old. This data cannot serve as a point-in-time historical backtest. Original archived ALFRED features remain separate. See [FRED real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) and [observation/vintage controls](https://fred.stlouisfed.org/docs/api/fred/series_observations.html).

## Build from saved recommendations

Use a price CSV covering the held instruments (the preview combined the existing cache with the existing DBMF/ALLW series; no forward fill). Rebuilding the viewer does not optimize or alter recommendation JSON or risk state:

```sh
python3 investor_dashboard.py \
  --reports var/product-preview \
  --prices /private/path/adjusted-prices.csv \
  --macro-features var/research/smart-portfolio-v3/features.json \
  --macro-forecasts var/research/four-macro-strategies-v6/macro-forecasts.json \
  --research-allocation var/research/smart-portfolio-v3/decision-audit.json \
  --latest-macro-features var/investor-current-macro/features.json \
  --pdf \
  --output var/investor-dashboard/index.html
```

All inputs are optional except saved plans. Missing inputs produce explicit unavailable states. `investment_product.py` accepts the same report-context flags and `--pdf` for new single-plan or demo outputs. Context enriches reports after the existing risk-state checkpoint; it does not change allocation calculations or approval receipts.

Temporary `--serve` binds loopback only and serves the chosen dashboard and named `investor-report-N.pdf` siblings. Raw JSON, arbitrary files, traversal paths and external Host headers remain blocked. This is not a multi-user customer server. No remote publication occurred.

For monthly shared-paper reports, provide context before the `run` subcommand:

```sh
python3 -m monthlydelivery \
  --macro-features /private/path/point-in-time-features.json \
  --latest-macro-features var/investor-current-macro/features.json \
  run
```

Period context excludes releases after the reporting month. Latest context is separately dated after the month and cannot change monthly performance. This example generates files only; it sends no email.

## Interpretation and validation limits

Quarterly indicator outlooks use up to 120 monthly snapshots, shrunk diagonal AR(1) persistence and 2,000 simulations with joint three-month residual blocks. This is an **unvalidated conditional research model**, not an official forecast, calibrated recession probability or return guarantee. It omits parameter uncertainty and many structural breaks. Latest descriptive regime scores use macro variables only and are not the existing market/macro policy's production state. The archived 63-session classifier and its validation gate are shown separately in plan-time mode.

Portfolio diagnostics apply the saved weights retrospectively with daily rebalancing. They include selection hindsight, assume zero uninvested cash yield and omit trading costs, investor taxes and platform fees. ETF adjusted history may embed fund expenses. They are not actual account performance, prospective strategy validation or a re-run of dynamic regime switching. Metrics use all available complete held-instrument sessions; charts display the latest 1,260 sessions.

Historical quarter attribution uses macro features available before the quarter and complete NYSE-session price histories. Correlation is descriptive, not causal. Forecast-regime portfolio scenarios weight historical quarter means; regimes with fewer than four observed quarters are excluded. Less than 80% supported regime weight yields unavailable rather than a fabricated estimate. Those screens do not establish statistical reliability.

Profile selection still represents separate hypothetical clients. Macro strategy guidance does not override financial loss capacity, liquidity, instrument access, the original 50%/three-year/5% unsupported objective or release gates. No trades, broker connections, active user emails or automatic promotions were enabled.

PDFs were generated with ReportLab and rendered/inspected using macOS PDFKit. The skill's Node instrumentation helper and Poppler were unavailable; no packages were installed. Layout and extracted text were checked, including source/portfolio date separation and all 26 rows. Browser inspection confirmed the new macro navigation, indicators, forecast chart labels and full core map; complete cross-browser/mobile certification remains a deployment task.

Final local validation: **1,257 pytest cases passed** and `ruff check .` passed. All four profile PDFs rendered as four pages each; macro/date labels and complete core tables were checked. No hosted CI, recurring scheduler, public recommendation approval or automatic allocation promotion is implied.
