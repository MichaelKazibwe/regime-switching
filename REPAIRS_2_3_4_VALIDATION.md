# Repairs 2, 3 and 4 — implementation and evidence

Completed locally on **31 October 2026 (Europe/Warsaw)**. Scope: the audit's numbered repair sequence: acceptance integrity, scheduler/watchdog crash recovery, and a genuine prospective portfolio/forecast ledger. Investment parameters and model-promotion gates are unchanged. This is private shadow infrastructure, not a public deployment or an accepted investment strategy.

## Repair 2: numerical and PDF integrity

`strategy_integrity.py`, `strategy_report.py`, `strategy_operations.py`, `refresh_strategy_dashboard.py` and `strategy_dashboard_server.py` now enforce:

- Mandatory hashed CSV artifacts for each reported strategy/reference. Headline metrics and wealth/drawdown histories are recalculated from those CSVs and compared with displayed training evidence. Dashboard training content must match the verified report, not merely its run ID.
- Canonical calculation IDs and independent reruns of **every displayed scenario**, including the real covariance/risk solve and deterministic simulation. This rejects negative cash, forged variance shares/returns/fans, unsupported fields/horizons and blocked simulation status. Legitimate cash-only portfolios with undefined percentage variance shares are handled without an empty `max()` call.
- A generated `artifact-manifest.json` binds dashboard payload/HTML, training run, validation/rendering sources, all four saved strategy PDFs, four investor-profile PDFs and the main investor PDF. Strategy PDFs carry their calculation ID and training run in the document itself. Profile PDFs bind plan IDs and macro context; the complete payload also binds the lab and training evidence.
- The private calculation service validates the seal and all scenarios before serving. Saved profile PDFs are rechecked against the seal. Calculation-specific downloads regenerate from the validated result instead of trusting a cached file that could be replaced.

These are content-integrity and reproducibility checks. The local manifest is not a signature against an attacker who can rewrite the entire code/data/manifest set as the same OS owner. Independent signed release approval and host security remain deployment gates. Doubled-cost results remain separately labeled sensitivity outputs; the verified base performance CSVs are not represented as an independent rerun of every possible sensitivity experiment.

All 20 saved scenarios and nine report PDFs were regenerated. Saved client-plan payloads remain unchanged; prior raw input snapshots and historical training reports remain archived. No higher risk limits or new predictive alpha were introduced.

## Repair 3: durable receipts, recovery and liveness

`strategy_receipts.py` supplies finite/duplicate-key-aware JSON reading, schema/hash validation, restrictive permissions, file and directory fsync, atomic replacement and exclusive immutable receipt creation. A malformed receipt is rejected before it can count; the scheduler never treats mere file existence as success.

`scheduled_strategy_validation.py` now publishes a v2 `RUNNING` receipt **before** computation. Its final success/failure receipt replaces that pointer atomically. Each run snapshots the dashboard/evidence in its own directory, including verification-only runs, and records linked report/manifest digests. A repeat refresh skips only after the current receipt and job chain validate. Concurrent runs are locked; downloads remain bounded to two hours.

`strategy_healthcheck.py` rejects malformed schemas without crashing and reconciles current exchange session, start/finish clocks, run status, job path, completion receipt and input/report/manifest hashes. An active job is pending until its 7,500-second limit, then alerts. Missing completion is pending only until the declared daily deadline: **00:45 UTC following the 22:30 UTC scheduled start**. Invalid or failed records alert immediately. Weekends use the actual last completed NYSE session rather than requiring a fictitious Saturday run.

The Docker recipe includes the new modules. Compose defaults to the new v2 root. Supplied `strategy-watchdog.service` / `.timer` check every five minutes. **No timer or external alert transport has been installed or delivery-tested:** there is still no deployment host. JSON/journald output and nonzero alert exits are locally tested; an external monitoring provider must route and test them on the selected host.

### Explicit interrupted-receipt recovery

Investigate and preserve the error first. A partial/invalid receipt can then be moved to an evidence-preserving quarantine:

```sh
python3 strategy_receipts.py --root var/strategy-operations-v2/observations \
  --quarantine-session YYYY-MM-DD --reason "Recorded operator investigation and cause"
```

Use an actual ISO session date. The command preserves the raw bytes, hash, reason and destination. It refuses to quarantine a valid sealed v2 observation; those require a new reviewed cohort if their source configuration must change. Recovery is not silent overwrite or approval. Retry only after the cause is resolved and inspect the resulting receipt and health status.

## Repair 4: prospective portfolio and forecast accounting

`prospective_strategy_ledger.py` creates a SQLite ledger with transactional commits, unique sessions, immutable update/delete triggers and a linked event hash chain. It tracks four strategies and three simple references independently.

- Each decision stores its actual registration timestamp, originating session, training run and first eligible **NYSE close strictly after registration**. Nothing can fill on its decision close or earn a return before the recorded investment takes effect.
- Held synthetic total-return notionals are marked using verified adjusted-price ratios. Costs, traded notional, cash, NAV, high-water marks, drawdowns, persistent locks and pending targets are carried forward. There are no contributions or withdrawals in this initial USD shadow cohort.
- Already-registered future-close instructions can fill during a catch-up valuation. Missing observation dates are explicitly flagged; new historical allocation decisions or forecasts are never invented. Catch-up valuations do not increase the count of observed decision receipts.
- Strategy source/configuration or ledger implementation changes stop continuation of the existing cohort and require a separately reviewed new cohort. Daily refits of the unchanged model design are identified by their immutable training run/report digest; they do not overwrite previously registered forecasts.
- The original four-way model/baseline/used distributions are stored with each decision. Outcomes mature after exactly **63 NYSE sessions**, using the point-in-time macro feature at that target session. Missing/unavailable outcomes are flagged rather than shifted to another date. Mature scores compare the original frozen forecast with the realized quadrant; no future refit is credited with an earlier prediction.
- Summaries separate observed decisions, actual forward return sessions, missed decisions, model outcomes and benchmark performance. CAGR is withheld before 252 return sessions; volatility requires at least two. A bootstrap's zero return is not performance evidence.

These are simulated adjusted-total-return accounts, not actual brokerage holdings, market fills or exchange-grade execution. The assumptions remain 15 bps traded notional, zero uninvested cash yield, no investor taxes/platform fees and no guaranteed drawdown cap. The references do not share the strategies' risk limits. The registered forecast outcomes overlap and are not statistically independent.

### Current state and commands

The v1 folder `var/strategy-operations/` is retained unchanged as legacy evidence and is not upgraded into the new cohort.

A real v2 run under `var/strategy-operations-v2/` passed acceptance and initialized the prospective ledger on 31 October 2026, using the latest completed **30 October 2026** market session. State: **1 operational observation, 0 forward return sessions, 1 registered forecast, 0 matured forecasts**. All seven shadow portfolios begin at NAV 1 in cash; their first permitted simulated fill is the **2 November 2026 NYSE close**. No future return or fill has been recorded as fact.

```sh
# Fresh isolated candidate, acceptance and prospective update after a usable close:
python3 scheduled_strategy_validation.py --refresh

# Verify job/receipt health (pending is distinct from healthy):
python3 strategy_healthcheck.py

# Read the prospective NAV/forecast summary without changing it:
python3 prospective_strategy_ledger.py
```

The summary is also written to `var/strategy-operations-v2/prospective-summary.json`. Run details, acceptance, immutable observations and `end-to-end-checks.json` are in the same private root. The existing operational receipt counter still requires manual continuity/missed-session review and never grants release approval; the prospective ledger now makes missing decision sessions and actual return history explicit.

If a local dashboard calculation service was already running before these repairs, restart it to load the new sealed bundle. No server was left running by the validation work. The scheduled workflow stays isolated from the investor workspace; it does not automatically publish a candidate, replace a client plan, promote a model or submit orders.

## Verification and remaining gates

- **1,309 tests passed** in the full suite; Ruff passed.
- Reproduced failure tests cover forged CSV headline returns, resigned corrupted scenario IDs/content, negative cash, blocked simulations, false risk shares, corrupted fans, unrelated PDFs, malformed/partial receipts, exclusive writes, pre-commit rejection and watchdog overruns.
- Prospective integration tests cover actual calendar-delayed fills, fees, carried peaks/locks, duplicate-session idempotence, source-change rejection, exact-maturity scoring of stored forecasts, missed-decision flags and immutable SQL triggers. Future dates in those tests are synthetic fixtures, not observed live performance.
- A real local run independently recalculated all twenty current scenarios and passed v2 acceptance. The health check returned `HEALTHY_SHADOW_JOB`; a repeated refresh returned `ALREADY_OBSERVED` only after validation.
- A real calculation-service startup, custom allocation/PDF export and deliberately replaced PDF-cache recovery passed. Main PDF remains seven pages; its calculation/run lineage and allocation page were visually reviewed using native rendering. Node/Poppler are unavailable, so no package installation or metadata-helper success is claimed.

Still pending: elapsed prospective investment evidence, independent economic/model validation, qualified Linux Docker build/host, external alert-delivery test, recovery drill and any public multi-user release controls. The predictive gate remains OFF. Audit findings concerning investment efficacy, missing data, strategy similarity, scenario calibration and cost/risk assumptions remain open; these engineering repairs do not imply profitable performance.
