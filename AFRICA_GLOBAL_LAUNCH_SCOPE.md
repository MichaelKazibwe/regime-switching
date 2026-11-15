# Africa-based global managed-account platform

Decision research: 1 November 2026. **Planning recommendation, not an incorporation, tax ruling, licence, brokerage approval or permission to trade.**

## Recommended base and broker

Use **Mauritius as the provisional operating-jurisdiction target** and **Interactive Brokers Professional Advisor as the primary global brokerage integration target**. This is an engineering and due-diligence recommendation. Company formation, local substance, licensing, bank account and broker acceptance remain uncompleted.

Select a jurisdiction for workable supervision, banking, investor confidence, operating cost and lawful tax efficiency. Weak enforcement is not a useful design objective for a client-money business. Africa is a region, not one licensing jurisdiction. The operating company's location does not determine every client's tax residence or eliminate permissions required where clients are served.

Mauritius has an explicit Investment Adviser (Unrestricted) category covering management of securities portfolios under mandate. The automated nature of this product also requires examination of the separate Robotic and Artificial Intelligence Enabled Advisory Services framework. Have Mauritian counsel/FSC scope the precise combination before applying; do not assume one securities licence covers every forex, commodity, derivative, dealing or custody activity. Sources: [FSC investment adviser criteria](https://www.fscmauritius.org/media/78011/lc_sec-24-investment-adviser-unrestricted.pdf), [FSC robotic-adviser criteria](https://www.fscmauritius.org/media/0e2jf2jd/lc_fs_1_18.pdf), [FSC securities categories](https://www.fscmauritius.org/licensing-supervision/securities).

Mauritius Revenue Authority lists a general corporate tax rate of 15% and conditional partial exemptions for specified income, including certain FSC-licensed activities. Local income-generating activity, qualified personnel and expenditure conditions apply. This is not an all-in tax estimate: confirm eligible income, current levies, VAT, withholding/treaty treatment, ownership/control and the founders' and clients' tax residence before modelling costs. Incorporating there does not relocate the actual management of a business by itself. [MRA corporate taxation](https://mra.mu/index.php/business/corporate-tax).

South Africa is the operational alternative for a South Africa-first business: its discretionary investment-manager category provides another explicit regulatory route, but requires a separate local licensing/tax/access assessment. It is not automatically a cheaper jurisdiction. [FSCA investment-manager description](https://www.fsca.co.za/Regulatory%20Frameworks/Regulatory%20Frameworks%20Documents/4.4.1%20%20Sector%20Risk%20Assessment%20-%20Short%20Version%2031%20May%202019.pdf).

IBKR is the preferred integration target because its advisor offering supports managed-client structures, allocation tools and API-based account allocation. Use the professional structure appropriate to a licensed business; do not use friends-and-family/non-professional exemptions for a public client-management service. Mauritius appears on its available-country list, but that is not confirmation it will accept this particular firm, clients or instruments. Obtain written entity/account/product eligibility. Sources: [Professional Advisor](https://www.interactivebrokers.com/en/accounts/advisor/overview.php), [API allocation documentation](https://www.interactivebrokers.com/docs/tws-api/doc/financial-advisors/groups-and-profiles), [available countries](https://investors.interactivebrokers.com/en/index.php?f=7021), [non-professional account restrictions](https://www.interactivebrokers.com/en/accounts/non-professional-advisor.php).

## Account model

- Manage the founder's and clients' accounts separately, with distinct account identifiers, mandates, positions, cash, limits, fees, tax records and immutable execution histories.
- Target individually titled broker-custodied managed accounts; the platform receives approved trading authority, not pooled deposits or withdrawal credentials. Actual custody/control classification needs legal review.
- Every order must bind tenant, broker legal entity, account, instrument contract, strategy/mandate, release version and authorization. A master-account login must never imply unrestricted access in the application.
- Predeclare fair allocation rules before shared orders; reconcile fills and rounding per account. Never allocate favorable fills to the founder after seeing results.
- Client onboarding, identity/beneficial-owner checks, screening, suitability/appropriateness, consent, fees, privacy, statements and complaints are launch-critical for client service. Requirements must be mapped to each approved client-residence country.
- Keep new-client countries denied until reviewed. No worldwide self-service signup merely because the broker accepts residents there.

## Market expansion plan

These are requested or proposed coverage targets, not approved tradable instruments. The current 28-instrument USD research catalogue remains unchanged until adapters, metadata, histories and mandates are validated.

| Market | Planned route | Qualification needed |
| --- | --- | --- |
| NYSE and other US equity venues | Primary IBKR target | Account permissions, exchange data, contract IDs, execution and settlement tests |
| S&P 500 exposure | Eligible fund or other separately approved product | The S&P 500 is an index, not an exchange or directly tradable stock; select account-eligible instruments |
| London Stock Exchange | Primary IBKR target | GBP/GBX quotation conversion, fund domicile/access, taxes/charges, settlement and market calendar |
| Hong Kong Stock Exchange | Primary IBKR target | HKD, board lots, tick rules, sessions/holidays, trading permissions and applicable charges |
| Johannesburg Stock Exchange, South Africa | Verify IBKR eligibility; regional JSE-member broker if needed | Do not assume direct access; custody, ZAR cash, liquidity, exchange data and account permissions |
| Stock Exchange of Mauritius | Regional licensed broker/custodian target | Local onboarding, instrument directory, data rights and confirmed API/workflow |
| Nairobi, Kenya; Uganda; Dar es Salaam, Tanzania | Regional partner integrations, proposed East Africa expansion | Separate country reviews, custody/CDS arrangements, currencies, data, settlement and operational access |
| Nigeria; Egypt; Ghana; BRVM; Casablanca | Later regional expansion candidates | Country-specific permissions, liquidity/capital controls, repatriation, broker and data qualification |
| Further global venues | Add individually after qualification | No wildcard authorization or automatic instrument activation |

IBKR publishes NYSE, LSE and Hong Kong equity coverage. This is venue-level product information, not account-level permission. Its country-residence list is not a list of African exchanges it connects to. [IBKR stock venues](https://www.interactivebrokers.co.uk/en/trading/cache_STK_.php). The JSE describes access through member firms and member-provided direct market access. [JSE membership/access](https://www.jse.co.za/trade/become-member/equity-market-membership).

## Stocks, commodities and forex are different engines

1. Start the live pilot with fully funded stocks/funds and operational currency conversion, following all existing release gates. Commodity funds can provide an initially simpler commodity allocation where account-eligible.
2. Add dedicated FX strategies only after venue/entity permissions, currency exposures, pip/lot sizing, financing, rollover, leverage/margin and close-out risk are modelled and tested. Currency conversion for settlement is not evidence that speculative leveraged forex is enabled.
3. Add commodity futures only after contract multipliers, expiry/rolls, first-notice/delivery avoidance, margin, daily cash variation and limit/negative-price handling are qualified. Commodity funds, futures and CFDs are not interchangeable. No physical delivery by default.
4. Validate each strategy against the new market's actual sessions, executable liquidity, currencies and net costs. The existing ETF allocator is not automatically a stock selector, FX trader or futures system.

## Mandatory engineering changes

Promote tenant/account isolation and client operations from P1 to **P0 for any client-account launch**. Add or extend:

- Global security master: broker contract IDs, venue/MIC, ISIN when available, instrument type, listing/settlement currency, quote units, tick/lot/minimum, multiplier/expiry and corporate-action identity. Ticker alone is insufficient.
- Multi-exchange calendar and scheduler: venue time zones/DST, holidays, auctions, lunch breaks, halts and asynchronous closes. Preserve point-in-time macro availability without applying US close timestamps to all markets.
- Multi-currency double-entry accounting: cash by currency, base-currency NAV, dated FX marks, conversions, settlement, local taxes/fees and corporate actions. Separate research-adjusted and executable prices.
- Account eligibility engine: client residence, mandate, instrument permission, product restrictions, funding/buying power and jurisdiction approval; defaults deny.
- Broker adapters: IBKR first, then independently verified African regional transports; durable outbox, order-ID recovery, rate limits and per-account reconciliation remain mandatory.
- Multi-tenant API/security: MFA/RBAC, tenant-scoped data access, encryption/key ownership, per-account freezes and access audit before exposing client accounts.
- Fair pre-trade allocation, per-account costs/performance reporting and founder/client conflict review.
- Data-provider entitlements and source lineage per venue, including stale quotes and illiquid/no-trade sessions; no fabricated backfills.
- Separate FX/futures risk/execution/accounting modules and scenario tests before enabling those products.

## Next execution order

1. Obtain a written Mauritius licensing/tax scope and identify the first client-residence countries. Resolve where the founder will actually manage the company.
2. Confirm IBKR professional-advisor acceptance, broker legal entity, client-country eligibility and product/market/API permissions. No account is opened by this document.
3. Implement tenant/account identity, global instrument contracts and multi-currency accounting in paper mode; keep credentials and authority separate from the dashboard.
4. Qualify US/London/Hong Kong paper connectivity, then one African venue through a confirmed member broker.
5. Finish existing host/security/recovery/observation gates and approve a limited own-account live pilot.
6. Admit client accounts only after the client-service licence/mandates, isolation and operational controls are approved. Add further countries and leveraged/derivative products as separate releases.
