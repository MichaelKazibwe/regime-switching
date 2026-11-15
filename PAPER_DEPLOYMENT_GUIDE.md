# Paper release and host qualification

## Interactive operator dashboard

Start the local read-only dashboard with `python3 -m paper_dashboard_server --port 8766`, then open **http://127.0.0.1:8766**. It serves only the dashboard and its API, not project files or credentials. It uses existing locked dependencies; no frontend package installation or external JavaScript CDN is needed.

The interface includes a searchable 14-ETF watchlist, selectable asset/price-history ranges, chart inspection by pointer or keyboard, saved portfolio/benchmark performance, allocation, holdings, cycle filters, CSV export and light/dark themes. Yahoo Finance five-minute provider bars refresh every 60 seconds; chart history is cached for five minutes. These are indicative provider prices, may be delayed, and are not an exchange streaming feed. Each quote carries a bar timestamp; stale, partial and unavailable responses are distinguished. Price updates never revalue or change the saved paper account.

Portfolio charts/holdings read actual saved JSON cycle reports from `var/paper-reports` (override using `--reports`). Empty histories remain empty rather than receiving sample investment performance. `python3 -m paper_dashboard` still creates a standalone interactive HTML snapshot at `var/paper-dashboard.html`; provider APIs require the local server. The new assets and server are included in release staging, so regenerate the release context and qualification evidence when reviewing this change. Existing release candidates remain snapshots of their original source.

The server binds only to loopback, rejects foreign host/origin requests, and has no trading or mutation endpoints. Keep it as a local operator view; any remotely hosted frontend needs a separately reviewed access/authentication design. The scheduled Docker worker and its network exposure are unchanged.

The local tooling is implemented. A fully qualified deployment still requires a real Linux host, successful hosted checks, delivered alerts, restore/failure drills, and the observation period. No host was available at implementation time. GitHub authentication also requires repair by the account owner.

## Prepare the release

### Monthly PDF reports and email subscriptions

`monthlyreport.py` builds month-end summaries and personalized PDFs from saved cycles. `monthlydelivery.py` sends one separately addressed email per active subscriber with a PDF attachment. All subscribers receive the existing shared `paper-default` portfolio; they do not receive separate account returns. Reports include saved NAV, monthly and benchmark returns, observed drawdown, costs, turnover, holdings, regime observations, cycle statuses, simulated order counts and coverage notes.

Copy `deploy/monthly-recipients.example.json` to protected `.env.monthly-recipients.json`, then add approved recipients with unique `user_id`, name, one email, `start_month` and `active: true`. Disable subscriptions using `active: false`. The sample is inactive by default. Keep the real recipient list out of Git and the image. On the Linux host, the bind-mounted file must be readable by container UID 10001; assign owner `10001:10001` and mode `0600`. SMTP settings reuse the existing protected `PAPER_SMTP_*` settings, sender and alert-recipient configuration. TLS is required for monthly attachments. A connected Gmail app can help send a manual sample; it does not configure SMTP for the scheduled worker.

Generate PDFs without sending:

```sh
python -m monthlydelivery run --month 2026-09
```

Explicitly send after reviewing the PDFs and confirming SMTP/recipient configuration:

```sh
python -m monthlydelivery run --month 2026-09 --send
```

Omit `--month` to use the preceding completed New York month. Current/future months are rejected. Eligibility begins at the subscriber's configured `start_month`. `--send` is required for all delivery; generation alone never opens an SMTP connection. Outputs, checksummed artifacts, source summaries, the delivery ledger and `last-run.json` are under `var/monthly-reports` and belong in protected backups. A no-data report explicitly states that saved records are unavailable; it does not assert zero activity. Reports with financial source records require database/event verification before sending. Missing opening/closing session boundaries make monthly return, benchmark return and counter deltas unavailable. Missing intermediate sessions produce partial coverage and may understate observed drawdown. NAV-ratio returns assume the existing paper account has no external contributions/withdrawals; adding cash flows requires a separate return-calculation design.

The sender checks PDF integrity and subscriber/portfolio/month ownership before attaching it. The SQLite ledger identifies each `(portfolio, month, user)` delivery. SMTP-accepted messages become `SENT` and are skipped on reruns; this is not human receipt confirmation. Failures before message submission become `FAILED` and require `--retry-failed`. A lost connection during submission, or a process interrupted in `SENDING`/`PREPARED`, requires operator review; the job never automatically retries these uncertain outcomes. After checking provider logs, resolve explicitly:

```sh
python -m monthlydelivery resolve --month 2026-09 --user-id example-user --outcome SENT --reviewer 'Michael Kazibwe' --reason 'Provider logs confirm acceptance'
```

Use `--outcome FAILED` only when provider evidence confirms it was not accepted, then rerun with `--send --retry-failed`. Resolution is retained in the ledger. SMTP cannot guarantee exactly-once delivery across ambiguous failures. Monthly jobs acquire the same lock as the worker/backup, preserving consistent report sources and the delivery database; review lock conflicts and rerun after the active operation ends.

After a successful delivery/receipt drill on the host, install the supplied `monthly-report.service` and `.timer` alongside the worker units. The service mounts the protected recipient list read-only and executes `python -m monthlydelivery run --send` in the reviewed image. The timer runs **on the first day of each month at 09:00 Europe/Warsaw** for the previous month. Enable it with `sudo systemctl enable --now monthly-report.timer`, inspect its next run and journal, and review `last-run.json` after each job. No host timer was installed locally. `Persistent=true` catches a missed trigger; an extended outage requires explicit `--month` backfills for older missed months. Keep the subscriber configuration and SMTP secrets backed up separately with protected access.

1. Review the current modified/untracked files and retain unrelated work. Commit the intended source, tests, locks, deployment files and documentation to a reviewed branch. Run `python3 -m pytest -q`, `ruff check .`, `python3 -m pip check`, and `python3 e2e_proof_runner.py`; retain results tied to the release commit. This workspace contains historical backups and duplicate files; source staging follows the local Python import graph, so these are excluded without deletion.
2. The generated `requirements-paper.hashed.lock` and `requirements-dev.hashed.lock` contain published PyPI artifact hashes for the exact version pins. Refresh with `python3.12 lock_paper_dependencies.py`; install in a fresh Python 3.12 environment using `python -m pip install --require-hashes -r requirements-dev.hashed.lock`. Candidate hashes may be generated with `--allow-other-python`, but Python 3.12 CI must verify compatibility. Changes to pins require regeneration, resolution/install checks, full tests, vulnerability scans and review. Source build dependencies are controlled by the package build backend and must also be reviewed in the built image/SBOM.
3. Stage a new release directory from the clean commit:

   ```sh
   python -m paper_release stage --destination var/release-context
   python -m paper_release verify --root var/release-context
   ```

   Existing destinations are never overwritten. `--allow-dirty` creates a clearly marked candidate for local review; qualification rejects it as a clean release. Review `release-manifest.json`, especially its source commit, file inventory and hashes.
4. Pass the configured GitHub CI checks on the same commit. The container job builds the staged context, verifies its contents/revision, checks imports, scans the image and saves the scanned image as an archive with checksum and image ID. Retain the matching checks, source scan, image scan, SBOM, archive and manifest artifacts. A successful workflow must be observed; configuration alone is not a PASS.

## Install the reviewed image on a host

1. Select and provision one isolated Linux VM in the approved account/region. Install Docker Engine/Compose and OS security updates. Restrict SSH to the operator network, synchronize the clock, reserve sufficient disk for the worker/history/backups, and expose no application port. Identify host patching, secret rotation and absence coverage owners before enabling scheduling.
2. Create `/opt/regime-switching` and copy the staged deployment files there. Download the reviewed CI image archive and matching checksum from that run. Verify `sha256sum --check paper-image.tar.gz.sha256`, load it with `docker load --input paper-image.tar.gz`, and confirm `docker image inspect` matches the retained image ID. Keep the previous reviewed image for rollback. If building on the host, rerun the same scans on that exact image and record its different image identity; a rebuild is not the CI image.
3. Create protected files owned by the host operator/root with mode `0600`:
   - `.env.image`: `PAPER_IMAGE=sha256:<reviewed-image-id>` (or an immutable registry digest).
   - `.env.paper`: copy `.env.paper.example`, inject the FRED key and SMTP credentials from protected configuration, set the approved recipient, keep `TRADING_MODE=PAPER`, `LIVE_TRADING_ENABLED=false`, `BROKER_SUBMISSION_ENABLED=false`.
   - Copy `deploy/operator.example.json` to the protected runtime evidence directory and fill ownership, absence escalation, backup location and approval details. Michael Kazibwe is the requested pilot operator; his supplied email is stored only in local ignored qualification configuration.
4. Compose uses the reviewed image directly and never builds implicitly. When running manually, pass `--env-file .env.image` for image interpolation; the systemd unit reads `.env.image` itself. Inspect Compose configuration without printing secrets to retained/shared logs. Run the container as the supplied UID 10001 with its persistent `paper-state` volume; retain the supplied read-only filesystem, capability and privilege restrictions.

## Qualify integrations and recovery

Run the following through Compose with the reviewed image/environment, preserving JSON outputs as evidence:

```sh
docker compose --env-file .env.image -f compose.paper.yaml run --rm --no-deps paper-worker python -m paper_admin data-smoke
docker compose --env-file .env.image -f compose.paper.yaml run --rm --no-deps paper-worker python -m paper_admin verify
docker compose --env-file .env.image -f compose.paper.yaml run --rm --no-deps paper-worker python -m paper_admin alert-test
```

Before the first cycle, `verify` is not a qualification of useful state; run it again after a real cycle. Execute a controlled alert through the existing notification transport, and have the recipient confirm receipt/time. Local JSONL records and an SMTP send result do not establish human receipt. Retain confirmation with the alert result. No alert was sent during local implementation because SMTP credentials were not configured.

The complete backup tool acquires the same nonblocking lock as the worker, backs up SQLite, copies audit/reports/alerts/research artifacts, hashes the inventory, verifies event/audit chains and snapshot references, and publishes a new bundle. Stop scheduling for the drill. Mount a protected backup directory outside the runtime volume as `/backups`, writable by UID 10001, then run inside the reviewed image:

```sh
python -m paper_backup create --runtime-root /app/var --destination /backups/paper-cycle-001
python -m paper_backup verify /backups/paper-cycle-001
python -m paper_backup restore /backups/paper-cycle-001 /backups/restore-drill-001 --replay
```

Restore targets must be new; the tool never replaces active state. Replay needs the original source/runtime and no broker access. Keep verified backups outside the host as well as outside its runtime volume, with restrictive access and the approved retention. Rehearse recovery from provider unavailability/stale data, process interruption, full disk/permission failure in an isolated copy, and a reconciliation mismatch. Confirm safe refusal, preserved state and operator escalation. Do not run destructive drills against the active volume. Keep scan/evidence retention at least as long as the paper observation; CI artifacts have finite retention and must be archived.

## Schedule and observe

After host/data/alert/restore/failure checks pass, install `deploy/systemd/paper-worker.service` and `.timer` following their README. The weekday timer runs at 17:15 New York; the CLI skips NYSE holidays. The worker does not automatically retry failed cycles. Review the dashboard, database, event/audit chains, logs, report freshness and reconciliation after every scheduled session. A timer or Docker-daemon failure can prevent in-process alerts entirely, so the named operator must also review timer/journal status and escalate a missing daily report.

Run for 60 completed NYSE sessions and at least three completed, reconciled rebalances with a frozen release/configuration. If an incident interrupts the period, resolve it and document a new observation window. Preserve the full state archive; pass only the selected window's reports to assessment. Never delete earlier incident evidence.

## Record evidence and assess

The ledger stores human attestations and hashed supporting artifacts; it does not pretend to log into or verify a remote host. Record only observed results, including FAIL results. Checks are `ci`, `security`, `host`, `data_smoke`, `alert_delivery`, `restore_replay`, `failure_drills`, `ownership`, `paper_signoff`, and the separate research gate `strategy_acceptance`. Record `paper_signoff` only after the owner reviews the completed observation report and supporting operational evidence.

```sh
python -m paper_qualification --release var/release-context record --check host --status PASS --reviewer 'Michael Kazibwe' --artifact /protected-evidence/host-review.json
python -m paper_qualification --release var/release-context assess --reports var/paper-reports --database var/paper-state.sqlite3 --snapshots var/research-snapshots --output var/qualification/status.json
```

Missing/failed/changed evidence, a dirty candidate, mismatched release provenance, synthetic source data, inconsistent configurations, missing sessions, unresolved incident reports, fewer than 60 sessions or three rebalances all prevent operational PASS. The assessor checks reports against the database and saved snapshot/runtime provenance. Reviewed receipts are bound to one release ID and source commit; old receipts cannot qualify a new release. The latest receipt for a check controls its status. Retain owner sign-off and numerical strategy acceptance criteria/results under `STRATEGY_ACCEPTANCE.md` before interpreting returns as accepted strategy evidence.

To roll back, stop the timer, preserve current state/evidence, choose the prior reviewed image and restore a verified compatible backup into a new volume. Rehearse verify/replay/reconciliation and obtain the owner's operational approval before resuming. Do not point an older image at unverified newer state.
