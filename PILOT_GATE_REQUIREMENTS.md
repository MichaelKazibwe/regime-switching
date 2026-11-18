# Pilot qualification requirements

The approved deployment scope is a local Linux VM on the owner's Mac, bound to loopback, with individual tester/viewer accounts and no execution or model promotion. Remote access and public recommendations require separate qualification. A local runtime pass does not approve those capabilities.

## Evidence that automation can supply

- An exact immutable app image with source identity, complete native dependency provenance, a recent HIGH/CRITICAL vulnerability scan and no ignored findings.
- Backend and Chromium/WebKit acceptance against that image, including roles, refresh, calculations and PDF/data exports.
- A recovery snapshot captured under every registered research writer lock while the app is stopped. The supported coordinator is `pilot_snapshot.py`; it releases partial locks on contention, restarts the app on export failure and authenticates/restores the resulting encrypted archive. App restart must also be followed by preflight. Arbitrary external edits are outside its registered-writer contract.
- A genuine off-host upload/download, matching ciphertext hash and isolated exact-image restore. A second independent device/host and a separately protected recovery-key copy are additional disaster-recovery requirements; a container on the original Mac does not prove them.

## Owner and external requirements

| Gate | Required evidence | Current handling |
|---|---|---|
| Backup account MFA | Authenticator-app or physical-security-key enrollment, privately saved recovery codes and a visible enabled state | Owner completes credential enrollment directly. “Require PIN for security key” alone does not enroll a key or create MFA. Never put a PIN, password, seed or recovery code in this repository. |
| Owner source/use review | Identified human reviewer, exact source release, approved audience/purpose, reviewed limitations and incident owner | Do not derive formal approval from a request to execute code. Review remains pending until explicitly recorded. |
| Data rights | Provider-specific permission for the actual private/client audience and exports, with dated terms and reviewer | Open. The yfinance project explicitly directs users to Yahoo's terms and describes personal-use limitations. An open-source client library does not license its downloaded data. |
| Independent price economics | All admitted symbols, at least 252 aligned sessions, compatible total-return basis, corporate actions/currencies and discrepancy review | Open. NAV, market close and adjusted total return are distinct quantities. Official macro data cannot validate securities returns. |
| Point-in-time universe | Dated admission/removal and delisting evidence, permanent identities, actual availability times and replay reconciliation | Open. Current registry membership does not prove historical investability. |
| Fund look-through | Dated issuer/regulatory holdings, availability times, measured issuer/country/FX/sector coverage and reviewed unknown exposures | Open. Free issuer files can supply current observations but cannot establish missing historical vintages. |
| Prospective forecasting/portfolio advantage | Genuine untouched outcomes, predeclared comparisons and sufficiently mature monthly/quarterly/annual targets | Collecting. Two sessions and one return observation do not establish alpha, optimality or calibrated forecasts. Do not backfill observations or change failed gates to passing. |
| Remote identity/HTTPS | Owner-approved endpoint/audience, identity/recovery design, valid trusted HTTPS, firewall/resource tests and qualified exact image | Not authorized/qualified for activation. Loopback testing does not require a paid domain or remote server. Keep the existing local binding. |

Missing October 2025 CPI remains missing under the current strict macro protocol. An alternative feature set requires a versioned protocol and fresh validation, not an imputed value presented as official data.

## Review sources

- [yfinance usage and data-rights notice](https://ranaroussi.github.io/yfinance/)
- [Example issuer source: iShares TLT](https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf) — its NAV, closing-price and holdings observations retain separate dates and valuation conventions.
- [Official macro and free backup policy](OFFICIAL_DATA_AND_BACKUP_PLAN.md)
- [Module-by-module execution register](PROJECT_REVIEW_EXECUTION.md)

All open external/human/future requirements remain explicit. No paid provider, waiver, false attestation or fabricated outcome is required or permitted to make a local test run.
