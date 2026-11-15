# Systemd paper worker schedule

Monthly user reporting is a separate optional timer. After verifying the
protected recipient configuration, TLS SMTP delivery, and recipient receipt,
install `monthly-report.service` and `monthly-report.timer` in the same way as
the worker units. Enable with `sudo systemctl enable --now monthly-report.timer`.
It runs on day 1 at 09:00 Europe/Warsaw and reports the previous New York month.
The mounted recipient file must be mode `0600`, owned by container UID 10001,
and stored at `/opt/regime-switching/.env.monthly-recipients.json`.
See `PAPER_DEPLOYMENT_GUIDE.md` for generation, delivery, retries and resolution
of ambiguous SMTP outcomes. These units are supplied, not installed locally.

The unit runs the one-shot Docker Compose worker once per weekday at 17:15
America/New_York, after the regular close and early-close sessions. The worker
itself checks data freshness, enforces a local lock, and uses the local date as
its idempotency key. It submits simulated paper orders only.

## Install on the paper host

1. Install the reviewed release under `/opt/regime-switching`, load its scanned image, and
   create `/opt/regime-switching/.env.paper` with secret values supplied by the
   host's protected secret mechanism. Keep the file mode at `0600` and owner
   restricted. Never commit it.
   Create `.env.image` with `PAPER_IMAGE=sha256:<reviewed-image-id>`, also mode
   `0600`. The service reads this file for Compose image interpolation.
   Follow `PAPER_DEPLOYMENT_GUIDE.md` for release staging, image verification,
   host/integration drills, and evidence recording before enabling the timer.
2. Install the service and timer files:

   ```sh
   sudo install -m 0644 deploy/systemd/paper-worker.service /etc/systemd/system/
   sudo install -m 0644 deploy/systemd/paper-worker.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now paper-worker.timer
   ```

3. Verify the schedule and the first run:

   ```sh
   systemctl list-timers paper-worker.timer
   sudo systemctl start paper-worker.service
   sudo journalctl -u paper-worker.service --since today
   ```

`Persistent=true` catches a missed timer after host downtime. Before resuming
after an outage, check logs and the dashboard, verify the paper database and
event chain, and confirm the provider has fresh completed-session data. Do not
manually start a second cycle while the service is active. A failed cycle is
not automatically retried; diagnose and rerun only after reviewing its event
and idempotency key.

Docker daemon access is root-equivalent. Restrict SSH, host accounts, and access
to the Docker socket; do not expose a network port for this worker.
