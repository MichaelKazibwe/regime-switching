# Global-universe migration verification

The investment universe is now a versioned, open global instrument registry rather than a fixed ETF roster. The current configuration contains 35 registered product instruments, with 32 enabled for research. These counts are configuration results, not limits. Research admission and paper-execution qualification remain separate.

The registry ID is `c7eadd60f8ca6c7863b9bec4b80ea709d3f7b5aabf4bd6db6b2a72664b68b58a`. The expanded private capture contains 4,244 completed valuation sessions and 33 priced instruments through November 16, 2026; one priced instrument is a comparison-only reference. The source-matched model report uses the 32 enabled research instruments.

## Verified behavior

- All 1,455 backend tests passed. Changed Python files pass Ruff and changed JavaScript files pass syntax checks.
- A synthetic registry exceeding 100 instruments is accepted. A separate subprocess test admits a fifteenth qualified paper member, exercising both the asset factory and execution ticker validation.
- Global quote handling checks actual local closes, information availability, exchange holidays, timestamped FX and pence conversion. Missing expected bars, missing/stale FX and unsupported return accounting fail closed.
- Strategy sleeves and reference anchors expand by metadata while preserving risk ceilings and declared class/cash budgets. Current portfolio rosters and table dimensions follow the registry. Named fixed-composition market references remain explicitly identified comparisons.
- Native Tokyo and London listings are registered but not research-enabled in the default USD capture. Their FX, data access and execution admission are not implied by registration.
- Existing client illustrations and historical source-bound ledgers were preserved. Changed source/universe contracts select separate prospective databases and receipt streams. The final global cohort starts with one observation and zero earned return sessions; previous observations do not count toward its qualification period.
- Cycle stress scenarios and weekly portfolio candidates were recomputed against the expanded universe. Their hypothetical outputs do not establish a global optimum, forecasting advantage or guaranteed drawdown limit.

Chromium and WebKit passed the complete dashboard acceptance suite against the Linux release: desktop/mobile navigation, cycle states and calculations, weekly candidate tables, scenario calculations, daily refresh, daily macro monitoring, CSV exports and PDF downloads. The regenerated 12-page weekly PDF was rendered and visually inspected. After its pagination adjustment, the 31 focused weekly/daily/pilot tests also passed.

The four incumbent frozen test-window returns remain negative (approximately -2.45%, -2.08%, -1.69% and -2.59%). Institutional challenger comparisons do not establish a positive lower confidence bound on excess performance over their matched references. Missing current macro inputs retain the cash-quarantine behavior. No model promotion or order submission was enabled.

Market data, model outputs, account databases, reports/PDFs and deployment receipts remain in ignored private directories. Public source documentation intentionally retains historical experiment counts with an explicit migration note rather than rewriting prior evidence.

## Deployment boundary

This is an invited-user local Linux VM research pilot. External HTTPS/domain, host qualification, vulnerability remediation, off-host backup/restore and owner source/data-access review remain separate deployment requirements. Passing local tests does not grant production approval or public recommendation authority.
