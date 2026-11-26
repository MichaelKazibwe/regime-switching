# Regime switching research and private pilot

Python portfolio research, chronological regime forecasting, risk controls, paper execution and an invitation-only dashboard. The active deployment is a **local Linux research pilot**, not an approved live investment service. Order execution and automatic model promotion remain disabled in the pilot.

## Start here

- [Institutional feature and UX audit](INSTITUTIONAL_FEATURE_AND_UX_AUDIT_20261119.md) and [upgrade execution register](INSTITUTIONAL_UPGRADE_EXECUTION.md)
- [Current project review](PROJECT_REVIEW_20261117.md) and [execution evidence](PROJECT_REVIEW_EXECUTION.md)
- [Free pilot, official data and recovery plan](OFFICIAL_DATA_AND_BACKUP_PLAN.md) — no paid resources are authorized.

- [Global migration verification](GLOBAL_UNIVERSE_MIGRATION_RESULTS.md)
- [Open global asset universe](GLOBAL_ASSET_UNIVERSE.md) — current policy for every portfolio, benchmark and strategy; historical fixed-count descriptions are archived experiment context.

- [Local VM dashboard and login setup](LOCAL_VM_PILOT.md)
- [Dashboard accuracy audit](DASHBOARD_ACCURACY_AUDIT_20261115.md)
- [Interactive terminal and navigation guide](DASHBOARD_TERMINAL_UPGRADE.md)
- [Macro alpha testing monitor](MACRO_ALPHA_MONITORING.md)
- [Daily alpha research training](DAILY_ALPHA_TRAINING.md)
- [Completed performance experiments](PERFORMANCE_IMPROVEMENTS_EXECUTION.md)
- [Business-cycle benchmark](CYCLE_BENCHMARK_GUIDE.md)
- [Remote deployment requirements](WEEKEND_PILOT_DEPLOYMENT.md)
- [Source cleanup and commit verification](CLEANUP_COMMIT_PREPARATION.md)

The local preview is `http://127.0.0.1:8782/`. Existing operators can inspect it with `sh deploy/pilot/local-vm.sh status`; it requires the separately built image, Colima VM and private volumes described in the guide. A clone contains no passwords, private snapshots, authentication databases or trained research artifacts. Example environment files contain placeholders only.

## Development checks

Use Python 3.12 for the release environment. Install `requirements-dev.hashed.lock` with pip's `--require-hashes` option in an isolated environment, then run:

```sh
python -m pytest -q
python -m ruff check .
git diff --check
```

Pytest excludes generated runtime/build contexts, archives and output. Canonical tests are retained; obsolete copied test implementations were removed. `archive/` intentionally preserves older reconstruction sources outside the production boundary. Standalone research tools and deployment commands are retained even when they are not imported modules.

Mac LaunchAgent files in `deploy/` are templates. The installers resolve current interpreter/project paths; installed jobs are separate. `deploy/render_launch_agent.py` can render a configuration for review without installing or starting it.

## Data and evidence

Keep `var/`, `output/`, local environment files, secrets, databases, captures, reports and model artifacts private and outside Git. Research reports describe the specific dated experiments they evaluated. The dashboard distinguishes archived illustrations, dated market closes, historical reference performance and simulated scenarios. Passing software tests does not establish predictive alpha or future returns.

Historical phase documents and proof reports are project history; their older counts and deployment conclusions are not current release approvals. The November 26 local workbench upgrade passed Chromium/WebKit desktop/mobile acceptance, all local runtime checks and its exact-image HIGH/CRITICAL gate against the fresh November 26 vulnerability database. Its coordinated encrypted snapshot passed an isolated local restore. See [the execution register](INSTITUTIONAL_UPGRADE_EXECUTION.md) for exact image/source identities and clean-build status. A prior encrypted off-host round trip exists, while a current-release independent-device restore, separated recovery keys and owner MFA remain open. Firefox is not part of the qualified browser set. A CycloneDX component inventory for the installed image is retained privately with native-source provenance receipts. Consult the execution register for new upgrade checks and the deployment guides before exposing the service beyond this Mac.
## Weekly portfolio research

See [Weekly portfolio research](WEEKLY_PORTFOLIOS.md) for the automated weekly candidates, projections, reports and local pilot operations.

See [Automatic daily dashboard updates](DAILY_DASHBOARD_REFRESH.md) for daily data publication and open-page refresh.

See [Daily macro monitoring](MACRO_MONITORING.md) for daily observations, quarterly aggregates and missing-data interpretation in Macro outlook.
