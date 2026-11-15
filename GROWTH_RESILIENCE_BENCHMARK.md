# Growth & Resilience benchmark and current policy

Implemented 31 October 2026. Current policy: `GROWTH_RESILIENCE_V1`. Private, non-executable reference; no public release approval.

## Objective change

The fixed 50% three-year return objective, 5% maximum account drawdown preference and automatic 2%–4% account drawdown cash lock are removed from current institutional, smart-macro, four-strategy, recommendation and new shadow-cohort paths. Return and drawdown remain measured outcomes. Training no longer rejects candidates solely for the former drawdown ceiling. Volatility, concentration, stress budgets, individual financial loss capacity, market-stress responses and evidence gates remain distinct controls.

Existing locked accounts are not silently unlocked. Old results, original client illustrations and cohorts remain historical. Snapshot: `var/policy-history/20261031T013230141697Z/`. Current stress challenger uses `research/stress_budget_challenger_v3.json`; V1/V2 are historical reproducibility configs. New strategy validation default: `var/strategy-operations-growth-v1`; no existing old-policy ledger is continued as if its policy were unchanged.

## Strategic design

The reference holds 60% equity, 35% economic diversifiers/invested reserves and 5% uninvested USD cash. It is unlevered, fully funded and rebalances every 21 observed sessions at the close, after prior holdings earn that session’s return. Weights were declared, not optimized to maximize the displayed backtest.

| Asset | Capital | Role | Mandate geography |
|---|---:|---|---|
| SPY | 18% | Broad earnings growth | US equity |
| VEA | 10% | International earnings diversification | Developed ex-US, including Japan |
| VWO | 8% | Emerging economies and consumption | Emerging markets |
| EWJ | 2% | Japan industrial and corporate earnings | Japan; overlaps VEA |
| QQQ | 5% | Digital infrastructure and technology; concentrated | US-listed global companies |
| XLI | 4% | Infrastructure and industrial investment | US equity |
| XLV | 4% | Healthcare demand and innovation | US equity |
| XLP | 3% | Essential consumption | US equity |
| XLU | 2% | Utilities and electrification; rate sensitive | US equity |
| XLE | 2% | Energy production; cyclical inflation sensitivity | US equity |
| KIE | 2% | Insurance earnings; underwriting and catastrophe risk | US equity |
| IEF | 7% | Duration diversification in disinflation | US sovereign |
| TLT | 3% | Recession duration hedge; inflation risk | US sovereign |
| TIP | 6% | Inflation-linked principal; real-rate risk | US sovereign |
| IGOV | 3% | Country and currency diversification; unhedged FX | Developed ex-US sovereign |
| GLD | 7% | Monetary and crisis diversification; no yield | Global commodity |
| DBC | 3% | Supply and inflation sensitivity; roll risk | Global commodities |
| DBMF | 4% | Trend diversification; strategy and derivative risk | Global multi-asset |
| SGOV | 2% | Short-duration invested reserve | US sovereign |
| USD_CASH | 5% | Liquidity; zero unverified net interest assumed | USD cash |

The US equity sleeve is 40%, developed ex-US 10%, emerging markets 8% and Japan tilt 2%. These are sleeve allocations, not verified underlying country percentages. Japan overlaps VEA; industry tilts overlap broad equity. Country holdings, FX and factor look-through remain unverified. XLV adds healthcare only to this benchmark; the existing production/research universe is preserved.

Industry exposure includes technology/digital infrastructure, industrial investment, healthcare, essential consumption, utilities/electrification, energy and insurance. These are economic roles, not pure-play or independent factors.

## Common observed comparison

2020-06-02 to 2026-10-30; 1613 daily return sessions. No pre-inception filling. The common sample starts after the initial COVID crash. Modeled cost: 15 bps per one-way turnover, cash interest 0 pending verification; excludes investor-specific taxes and measured execution slippage.

| Reference | CAGR | Annual volatility | Max drawdown |
|---|---:|---:|---:|
| Growth & Resilience | 10.60% | 9.77% | -15.85% |
| US equity | 16.64% | 16.78% | -24.50% |
| 60/40 US | 9.19% | 10.65% | -21.32% |
| All Weather-style proxy | 4.25% | 9.45% | -23.70% |

All Weather-style is the transparent 30% SPY / 40% TLT / 15% IEF / 7.5% GLD / 7.5% DBC illustration, not actual Bridgewater fund returns. Selection bias, short history and parameter uncertainty prevent a durable outperformance claim.

Three-year joint 21-session block bootstrap: 1000 paths; median total return 36.46%; 5th–95th percentile 6.55% to 70.18%; ending-loss frequency 2.70%; 95th-percentile drawdown magnitude 17.44%. Conditional historical resampling, not a forecast guarantee. No drawdown clipping or forced return target.

The four macro strategies were retrained on the verified 30 October capture under current policy. Their most recent 252-session evaluation remains negative (approximately -0.82% to -1.68%). The new strategic reference is not silently substituted for their strategy evaluation.

## Dashboard and news

The dashboard opens on Growth & Resilience, with interactive comparison/drawdown charts, legend toggles, asset search, complete capital and signed variance shares, geography and industry roles, scenario metrics and limitations. Saved client illustrations are preserved and marked historical. The main investor PDF adds the reference allocation and comparison appendix.

The Market news section supports search, topic filtering, publication dates, source health and refresh. The authenticated `/api/news` endpoint caches public RSS for five minutes; the open dashboard polls it every five minutes. Public feeds can fail; prior headlines retain their original retrieval timestamp and an explicit failure status. News never changes weights or triggers orders. Files opened directly show a dated capture, not a running feed.

Captured news at 2026-10-31T01:34:31.560790+00:00: 35 headlines. Fed and ECB fetched successfully; Yahoo Finance unavailable in this capture. This is a public macro/policy feed with an attempted general-market source, not a comprehensive licensed market-news service.

Run locally: `python3 strategy_dashboard_server.py` and open the private fragment-token URL printed by the process. Use `--port 8769` if 8768 is occupied. Fresh-price dashboard jobs also capture current XLV history and a fresh headline snapshot, avoiding a stale healthcare extension on future sessions. Scheduled fresh-price training is separate from news polling; the feed does not turn daily market closes into live exchange quotes.

## Validation and remaining gates

Full regression: 1,339 tests passed. Ruff checks passed. Browser review confirmed the default benchmark, complete allocation table, live source refresh and headline search. A new-policy shadow job passed, is healthy, has one observation and zero forward-return sessions; its first hypothetical fill is due 2 November 2026. Historical ledgers were preserved. New tests cover removal of default drawdown locking, funded backtest timing and costs, unclipped losing simulations, unsafe/future RSS entries, stale-cache provenance and authenticated same-origin news access. JavaScript parses in native JavaScriptCore. The updated benchmark PDF page was rendered and visually checked with native PDFKit. Docker manifests were updated, but no image was built or deployed.

Missing verified cash, fees/spreads, duration/FX holdings, access eligibility, jurisdiction/public approval and elapsed prospective performance remain blocked. This benchmark is available for comparison, not authorized execution.

## Primary source references

- [Vanguard VEA fund mandate](https://advisors.vanguard.com/investments/products/vea/vanguard-ftse-developed-markets-et)
- [State Street XLV fund mandate](https://www.ssga.com/us/en/individual/etfs/state-street-health-care-select-sector-spdr-etf-xlv)
- [Federal Reserve RSS feeds](https://www.federalreserve.gov/feeds/feeds.htm)
- [ECB RSS feeds](https://www.ecb.europa.eu/home/html/rss.fr.html)

The temporary browser-review service on port 8769 was stopped after verification; the saved dashboard remains open. Start the command above to use live news again. Existing services on other ports were left running.
