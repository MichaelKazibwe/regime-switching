# Daily alpha research training

Enabled on 15 November 2026, Europe/Warsaw. The Mac LaunchAgent `com.regime.daily-alpha-training` checks hourly and on login/load. It trains once per eligible, completed NYSE session and source-bound input bundle, after the existing daily observation pipeline has validated that session. Weekend/holiday checks reuse the last eligible session and do not invent new observations. Failed jobs have at most two attempts per input/source identity; overlapping jobs are locked out.

The initial final-version fit completed against **2026-11-13**, using **1,065** historical examples. Its last usable training label predates the decision session. Current macro inputs are unavailable, so the fitted research model is retained but no current alpha forecast is fabricated. The historical superiority screen failed; model promotion and trading remain disabled.

Each run performs the fixed-calendar nine-configuration chronological forecast study, selects regularization/shrinkage using prior validation outcomes, refits the latest classifier using only matured labels, and saves inspectable scaler/classifier parameters as JSON. Artifacts and input/source hashes are stored with the result. A daily refit does not mean a new quarterly outcome has matured or that alpha has been demonstrated.

Status:

```sh
cat var/daily-alpha-training/heartbeat.json
cat var/daily-alpha-training/latest.json
```

Runs, model parameters, fixed-calendar scores and private logs: `var/daily-alpha-training/`. Manual idempotent check: `python3 daily_alpha_training.py`. Scheduler source template: `deploy/pilot/com.regime.daily-alpha-training.plist`. The already installed configuration in `~/Library/LaunchAgents/` remains active. For another checkout, render the template with `python3 deploy/render_launch_agent.py deploy/pilot/com.regime.daily-alpha-training.plist --output var/launchagents/com.regime.daily-alpha-training.plist` before reviewing and installing it.

The worker runs on this Mac alongside its existing market-data scheduler, not inside the frozen Linux dashboard container. The Mac must be awake and logged in; the upstream pipeline also needs authorized market-data access. If the eligible session has not validated, training waits rather than using stale or incomplete inputs. Copying research fits into the deployed dashboard or enabling predictions requires a separate reviewed release. No existing forward ledger or registered allocation is rewritten.

Verification: 22 focused training, scheduler and performance tests passed, including coefficient-based probability reconstruction, label maturity, unavailable-input handling, session deduplication and retry bounds. Source lint passed. The first implementation's same-timestamp retry filename collision was corrected before installing the scheduler.
