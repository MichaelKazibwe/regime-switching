# Automatic daily dashboard updates

The local Linux pilot now receives new verified daily data without rebuilding its image or restarting the service. Open signed-in dashboards already check the data version every minute and on returning to the tab. They reload automatically when the training run changes, preserving the selected view in the URL.

The existing hourly observation agent captures and validates the latest completed NYSE session. The new `com.regime.pilot-daily-refresh` Mac login agent checks every 15 minutes for that verified publication. It waits for the completed-session publication buffer and successful upstream validation; it does not substitute intraday prices or create weekend observations. Capture/training time and the upstream hourly schedule determine when a new daily result becomes available.

`pilot_daily.py` creates an immutable portable snapshot containing market inputs, training evidence, saved allocations and PDF bindings. A dedicated non-root helper validates the whole snapshot with the installed Linux numerical code before atomically publishing its revision pointer. The dashboard mounts the `regime-pilot-local-daily` volume read-only at `/app/daily-research`, independently of accounts, weekly research and the original input snapshot. The server swaps financial data, calculation inputs, result cache, news cache and PDF bindings together under its application lock. Bad snapshots or older market sessions are rejected; the previous verified snapshot stays visible, with update failure/staleness indicated.

Repeated publication checks reuse the same snapshot. New market data does not grant model promotion, client approval or order execution. The separately dated weekly and cycle research retain their own schedules and evidence labels.

## Operations

Keep the Mac awake, the user logged in and the Colima VM running. Normal session expiry still requires signing in again. This is local pilot automation, not an always-on cloud deployment.

From the project root:

```sh
launchctl print gui/$(id -u)/com.regime.pilot-daily-refresh
.venv/bin/python pilot_daily.py --publish-vm
sh deploy/pilot/local-vm.sh status
sh deploy/pilot/local-vm.sh preflight
```

Generation/publication receipts and logs are private under `var/pilot-daily/`. The original daily capture receipt is `var/local-observation-scheduler/heartbeat.json`. A `WAITING_FOR_VERIFIED_DAILY_CAPTURE` result means upstream daily capture/training has not yet published the expected completed session. Retain the last good snapshot and inspect upstream logs; do not change dates or bypass validation.

If numerical source code changes, build and validate the new app image before publishing data that requires it. Previously published daily revisions and original input snapshots remain immutable. Data uses an additional approximately 11 MB per publication with the current sample; monitor VM free space during a longer pilot.

## Verification

Tests cover revision identity, path traversal, whole-state replacement, invalid-update retention, rollback rejection, repeated refresh deduplication, waiting for current daily capture and authenticated version reporting. Browser acceptance simulates a new daily version and verifies automatic reload, retained sign-in and the selected weekly view, then checks the existing dashboard views and exports in Chromium and WebKit. Real Linux publication validates the current sealed daily snapshot and all its calculation/PDF bindings.
