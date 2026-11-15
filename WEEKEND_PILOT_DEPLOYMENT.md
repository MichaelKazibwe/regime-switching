# Invited Linux pilot: deployment sequence

Prepared 14 November 2026 for a small invited group with individual logins. The application is a research pilot with shared example portfolios, no brokerage access and no trading. Local tests do not establish financial production qualification. The source tree contains extensive uncommitted work; the staged package is explicitly a candidate until reviewed.

The user subsequently selected a **local Linux VM on the Mac** for the first deployment. Follow `LOCAL_VM_PILOT.md` for that active route. The steps below remain the later remote deployment procedure. Local container tools are now installed and an image has been built; the external security scan gate has not passed.

## 1. Review the candidate and evidence

Read `PILOT_EXECUTION_RESULTS_20261114.md`, `PERFORMANCE_IMPROVEMENTS_EXECUTION.md` and `CYCLE_BENCHMARK_GUIDE.md`. The full private release is under `var/pilot-release/20261114-final-candidate/`: `image/` is the minimal build context, `runtime/` is private data, and `release.json` identifies the candidate. No authentication database, real passwords or market API credentials are shipped. Do not upload the repository or runtime data to a public registry. Review the source diff and data redistribution rights before inviting users; commit the reviewed source and restage without `--allow-dirty` for a reviewed-source release. Preserve the manifests and evidence for the actual version deployed.

## 2. Build and scan the exact Linux image

Run the checked-in `.github/workflows/pilot-ci.yml` on the reviewed revision, or its equivalent on a Linux builder. It installs hash-locked dependencies, runs tests, stages source, builds the image, and requires the vulnerability gate. Build for the VM architecture. Pin the Python base and Caddy image to reviewed immutable digests; retain scan/SBOM output and the resulting application digest. The Mac local tests do not substitute for this step. Docker/image build and remote CI have not been verified here.

For a manual build from the staged directory, use `docker build -f image/Dockerfile.pilot -t YOUR_PRIVATE_REGISTRY/regime-pilot:RELEASE image`, passing the reviewed `PYTHON_BASE_IMAGE` build argument. Push only the source image to a private registry and record its repository digest. Do not use placeholder digests from the examples.

## 3. Prepare the VM and domain

Provision a supported Linux VM with Docker Engine and Compose. The configured concurrent application and worker memory limits total 6 GiB; 8 GiB RAM and four vCPUs are an initial test capacity assumption, requiring measurement on the chosen host. Reserve disk for datasets, PDFs, logs, images and backups. Use SSH keys and restrict SSH to operator addresses. Allow inbound TCP 80/443 for Caddy and HTTPS; do not publish application port 8780. Point the domain's DNS records to the VM and remove incorrect IPv6 records. Keep OS security updates enabled.

## 4. Install the private release

Copy the candidate's `compose.pilot.yaml`, `deploy/`, and private `runtime/` to `/opt/regime-pilot` through an authenticated encrypted transfer. Create `runtime/pilot`, `output`, and `.secrets` there. Set `runtime` and `output` ownership for container UID/GID 10001 and restrict directory permissions to the operator and that runtime user. Keep `.secrets` accessible only to the operator; Compose reads the worker environment on the host. Never copy local `*-state` QA directories or synthetic accounts.

Copy `deploy/pilot/pilot.env.example` to `.env.pilot`. Set `PILOT_IMAGE` to the built application digest, `PILOT_PROXY_IMAGE` to the reviewed Caddy digest, the real HTTPS origin, matching domain, and certificate email. Copy `market.env.example` to `.secrets/market.env`, insert the actual authorized FRED credential, and chmod both environment files 600. Do not paste secrets into command history, reports or Git.

The following commands run from `/opt/regime-pilot`. Prefix every Compose command with:

```sh
docker compose --env-file .env.pilot -f compose.pilot.yaml
```

Validate configuration with `config --quiet`, then `pull`. Configuration output may contain resolved secrets; do not publish it.

## 5. Start and create invitations

Run the Compose command with `up -d pilot proxy`, then inspect `ps` and private service logs. Caddy must obtain a valid certificate for the configured DNS name. Check external `https://YOUR_DOMAIN/healthz` and confirm unauthenticated `/api/dashboard` returns 401. Check the host firewall from a separate machine.

Create each invite interactively with the Compose command followed by:

```sh
exec pilot python pilot_admin.py add-user person@example.com --role tester
```

Use `viewer` for read-only users. Enter a unique temporary password at the prompt, deliver it privately, and have the user change it on first login. There is no public signup or email sender. Use `revoke-user person@example.com` to disable access and revoke sessions; `reset-password person@example.com` requires another first-login change.

## 6. Run deployment acceptance before inviting the group

Run the Compose command followed by `exec pilot python pilot_preflight.py --output var/pilot/preflight.json`. This checks source/snapshot integrity, numerical/PDF bindings, current data, Linux/nonroot operation, private authentication storage, disk reserve, and an invited user who has completed their password change. Resolve every failed check.

Run `python pilot_verify.py --help` in the image and execute its authenticated acceptance against the real HTTPS origin using an invited test account; enter its password through the prompt. Verify login, first password change, all 14 views, benchmark's eight scenarios, mobile navigation, PDF/JSON downloads, recalculation for a tester, disabled viewer controls, logout and revoked-account denial. Run the frontend acceptance on the exact Linux build in CI as well; local macOS browser limitations are recorded in the execution report. Check browser console/network errors and stale data labels. Test concurrent invited sessions on the chosen host and record response times/memory; local functional tests are not a load qualification.

## 7. Verify data collection before enabling the timer

Run the Compose command followed by `--profile jobs run --rm validation`. The imported current session should return `IMPORTED_SESSION_READ_ONLY`, with zero new observations. Do not delete cohort pointers, rewrite sealed history or count imports as fresh observations. On the next eligible completed market session, require a successful fresh capture/validation/heartbeat. Investigate missing or stale inputs; cash quarantine must remain enforced when required inputs are unavailable.

Install `deploy/pilot/regime-pilot-validation.service` and `.timer` into `/etc/systemd/system/`, run `systemctl daemon-reload`, then `systemctl enable --now regime-pilot-validation.timer`. Inspect `systemctl list-timers` and `journalctl -u regime-pilot-validation.service`. This is an hourly completed-session check; it does not manufacture weekend observations. Confirm recovery after restarting the VM.

## 8. Prove backup, restore and rollback

Use `pilot_admin.py backup` for an online, integrity-checked authentication database backup. Stop the validation timer and worker before making a consistent private runtime backup; include cohort databases/pointers, snapshots, source manifests, config and Caddy certificate volumes. Encrypt backups and transfer them off-host with restricted access. Restore into a separate directory/VM, verify checksums and SQLite integrity, and repeat acceptance. Do not point a restore rehearsal at the live state. Record the recovery time and backup age.

Retain the prior application digest and matching private runtime snapshot. For rollback, stop the timer and application, preserve the failing state for investigation, restore the matched prior snapshot/config and digest, then rerun integrity and acceptance checks before reopening access. Do not roll back only the image across incompatible state changes.

## 9. Open the invited test

Invite the small group only after the exact image, HTTPS, authentication, data freshness, backup restore and operational checks pass. Monitor private errors, disk, memory, timer health and login failures through the weekend. Record issues and feedback without collecting unnecessary personal or financial data. Research outputs and simulated cycle losses are not guarantees; current cash-heavy reference weights are not a personalized investment recommendation.

Remaining operator inputs: reviewed revision/image digest, VM/SSH access, domain/DNS, registry access, market credentials/data rights, invitation usernames, backup destination and a named operator. These are not supplied by local test execution. Public release or live investment execution requires a separately scoped qualification.
