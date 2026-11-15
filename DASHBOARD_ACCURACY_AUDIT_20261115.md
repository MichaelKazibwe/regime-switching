# Deployed dashboard accuracy audit — 15 November 2026

Audited the local Linux dashboard at `http://127.0.0.1:8782/`, immutable image `sha256:d5aaf77590ab3dae8bab65ef03cb19674ba95ff817596051baf289b4bbb42a27`, source candidate `1d60989d4c6366990da29f9290d9478728dcc584f8907f5d089561c19d302b36`. No dashboard figures or user credentials were changed. No discrepancies were found within the checks below.

- **190/190 numerical and source checks passed** against the exact portable snapshot in Linux: all 28 displayed closes/history endpoints agree with the captured prices; portfolio capital and signed-risk totals reconcile; scenario dates match their inputs; Growth & Resilience and its three comparisons agree with independently calculated return, CAGR, volatility, drawdown and expected shortfall metrics; dynamic chart terminal NAV agrees with its reported return; the cycle held-out curve agrees with its reported metrics; all eight simulated fans are finite, ordered and reconcile to their reported medians. Immutable source/snapshot/PDF bindings also verified.
- **1,252 rendered-value comparisons passed**, 626 each in Chromium and WebKit. Every saved profile's asset weights, signed-risk shares and displayed adjusted closes were compared to the authenticated data, alongside all return-engine and dynamic allocation tables. Comparisons respect each table's declared rounding precision.
- **34 downloads verified**, 17 per browser: all four profiles' allocation CSVs, visible-plan JSONs and saved PDFs, the dynamic PDF, and all four macro strategy PDFs. CSV capital totals, currency and amount scaling reconciled; JSON exports retained the correct profile identity and illustration amount; PDF responses were valid PDF files. No browser page errors occurred. The first audit attempt used two-decimal tolerances for a one-decimal return-engine table; that audit-harness tolerance was corrected, and the complete audit passed.
- **Deployed runtime preflight passed all nine checks**, including current eligible session, numerical/PDF bindings, private authentication storage, nonroot Linux operation and an invited user who completed the required password change. Prior desktop/mobile navigation, eight-scenario, viewer-role and logout acceptance remains bound to this same unchanged image.

## Dates and interpretation

The latest captured market session is **2026-11-13**, the eligible Friday close for this Sunday audit. The separately versioned cycle reference is dated **2026-11-12**. Archived investor illustrations retain their older valuation dates; their saved allocations are not current personalized recommendations. Latest market prices shown alongside them are adjusted closing observations, not executable quotes or a revaluation of a live account.

Changing the illustration amount scales the browser scenarios and CSV/JSON illustration; the saved-plan PDF remains the original saved plan. Capital weights and signed variance shares are different quantities, and negative risk shares may represent diversification. Latest refitted cycle weights are separate from its frozen historical test. Forecast/return improvement gates have not established reliable superiority, so no model or portfolio was promoted.

## Evidence and limits

Receipts and exports: `var/dashboard-audit/20261115/`. Reproducible audit code: `dashboard_accuracy_audit.py` and `dashboard_browser_audit.py`. QA used separate disposable accounts and volumes, without accessing the operator's password or changing their account.

These checks establish consistency with the captured inputs, calculation evidence and rendered outputs. They do not independently verify every upstream vendor observation, validate future forecasts, guarantee returns/drawdowns, prove every possible input/browser combination, or replace a full visual/text review of every generated PDF page. The local deployment remains a candidate with frozen data and no configured automatic market refresh.

Firefox is still blocked by the documented QA browser crash before application navigation. External deployment is not approved: the last application scan retains 49 HIGH OS-package findings; the proxy scan retains two HIGH findings; SBOM generation and encrypted off-host recovery remain open. Those limitations are not changed by the successful accuracy audit.
