# Open global asset universe

The project no longer treats a fixed ETF list or instrument count as the investment universe. `research/global_asset_registry.json` is the versioned source of instrument identity and eligibility. Portfolios, risk models, strategies, current benchmarks, recommendation services and dashboard rosters resolve their constituents from that registry. `maximum_universe_size` is `null`; adding an instrument does not require changing a matrix dimension in source code.

`DIVERSIFIED_ASSETS` and `PRODUCTION_ASSETS` remain compatibility API names. They resolve registry records at process start. The former is the enabled research vector; the latter is the explicitly qualified paper-execution vector. Neither is a universal portfolio limit. Restart and qualify a new source-bound cohort after changing the registry; do not alter membership midway through an existing run.

## Current admission and limits

The initial expanded research configuration includes individual equities and ADRs alongside the existing equity, bond, real-asset and alternative funds. Microsoft, Toyota, ASML and Sony histories were captured through the completed November 16, 2026 session with no missing values in that capture. The healthcare fund and managed-futures fund are registered research constituents rather than special fixed-universe exceptions. Instrument counts shown by the UI are calculated from the configured registry and available data, not used as ceilings.

Native Tokyo and London listings are registered separately with JPY and GBP/GBX units. Their presence is not a claim that FX, data access, execution or client suitability has been qualified. Research-enable them only with qualified timestamped quotes and FX. The standard USD download refuses native-currency research members without that adapter, preventing pence or yen from silently being treated as dollars.

Registry metadata supports equities, ADRs, ETFs, funds, direct bonds, REITs, commodities, crypto, FX, cash, futures and options. Data/return-accounting support is a separate gate. Direct bonds require coupon/accrual-aware total returns; derivative/FX contract accounting cannot be replaced by a spot-price assumption. Unsupported return adapters fail closed. Registry inclusion never creates public recommendation approval, broker access, trading authority or a claim of liquidity.

The paper-qualified seed remains the previously qualified execution set. A new equity or fund entering research does not inherit paper qualification. Changing a production profile still requires the existing source, account, venue and execution checks. There are no new order routes or automatic promotions.

## Strategy and benchmark behavior

Economic sleeves expand by registered risk bucket and instrument metadata. Their class budgets, position/risk ceilings, stress controls, cash rules and data-quarantine behavior remain enforced. A new constituent gets a modest normalized within-sleeve prior, not a guaranteed holding. Strategies may legitimately exclude an asset class they do not support; exclusion is not a global ETF-count restriction.

Growth/reference anchors preserve declared class and cash budgets while resolving their constituent sets dynamically. Weekly allocation uses metadata for financial-sector, satellite, broad-fund and international constraints. Broad-fund/international floors apply only when those categories are available. The optional SPY/IEF comparison is unavailable when its components are absent; it does not prevent another global universe from being analyzed. Named market references may keep a fixed declared composition without restricting investable assets elsewhere.

Historical reports, saved client illustrations and old ledgers retain the assets and source versions used when they were created. Numeric counts in historical reports describe those experiments. They must not be rewritten to imply that a newly added instrument was held or evaluated earlier. A changed registry/source protocol starts a separate prospective cohort and observation window; old observations do not count toward the new protocol's qualification period.

## Global valuation and currency

`global_market_panel.base_currency_panel` accepts actual local-session quotes and availability timestamps, venue calendars and timestamped FX rates expressed as base-currency units per native currency. It applies quote-unit multipliers once, selects only information available by the portfolio valuation time, rejects missing expected local closes and stale/missing FX, and records the underlying observation timestamps. An actual mark may remain unchanged while its exchange is closed; it is never presented as a newly observed local-market price.

To supply a qualified provider capture, use:

```sh
.venv/bin/python strategy_training_data.py \
  --output var/global-market-captures \
  --global-panel-manifest /private/provider/valuation-manifest.json
```

The manifest specifies schema version 1, USD base currency, the exact registry ID, a hashed valuation CSV (`timestamp`), hashed quote CSVs by instrument (`session,available_at,close`), and hashed FX CSVs by listing currency (`session,available_at,rate`). It must cover every enabled research member. Source files and valuation provenance are copied into the private immutable capture. The current daily research pipeline uses completed NYSE valuation dates as its common USD reporting grid, while each constituent's own exchange determines which actual local close is eligible.

The recommendation service also accepts explicit per-currency FX histories and quote-unit multipliers. Native-calendar portfolios use common completed exchange sessions and a matching annual valuation-session count in covariance, cash compounding and simulations. No FX history is inferred or filled. For execution or public use, provider rights, timestamps, spreads, liquidity, corporate actions, FX costs and underlying issuer/country overlap still need independent review.

## Onboarding an instrument

1. Add a unique identity, provider symbol, asset/risk classification, region, currency, quote unit, venue/calendar, return-accounting model and sources to the registry.
2. Keep it out of enabled research and execution until its data adapter, actual history, FX, availability and risk classification are verified.
3. Capture immutable inputs, including FX and local-close provenance where needed. Do not invent pre-inception observations or replace missing open-session prices.
4. Refit/replay the affected strategies and references, compare costs and risk, and register a new prospective source/universe cohort.
5. Build and test the backend/image/dashboard before publishing the new daily and weekly artifacts. Obtain client review before adopting any candidate.

## Verification

Tests cover a registry with more than 100 instruments, metadata/accounting conflicts, strategy sleeve expansion, frozen-contract preservation, class-budget preservation, multi-currency and pence conversion, unavailable/future FX, local holidays and missing expected closes. Existing risk, capital, cost, chronology and execution tests remain in place. The global migration does not establish forecasting advantage or globally optimal allocations.

Source configuration and tests may be committed to GitHub. Credentials, market captures, model outputs, PDFs, account stores and local deployment state stay under ignored private directories.
