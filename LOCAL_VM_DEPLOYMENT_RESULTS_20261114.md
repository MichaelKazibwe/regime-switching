# Local VM deployment execution — 14 November 2026

Selected destination: the local Linux VM on this Mac. No cloud purchase, public Git push, registry upload, public tunnel or domain registration was made. The GitHub repository is public, so private runtime artifacts remain local.

## Installed and deployed

- Homebrew tools installed: Colima 0.10.3, Docker CLI 29.9.3, Compose 5.7.1, Buildx 0.39.0, Trivy 0.76.2 (and Lima dependency).
- Dedicated `regime-pilot` VM: native ARM64 Linux, two CPUs, 4 GiB RAM, 35 GiB data disk; no home-directory mount or SSH-agent forwarding. The existing active Docker context is preserved.
- Portable source candidate: `var/pilot-release/20261114-local-v3/`, release ID `1d60989d4c6366990da29f9290d9478728dcc584f8907f5d089561c19d302b36`.
- Deployed immutable local image ID: `sha256:d5aaf77590ab3dae8bab65ef03cb19674ba95ff817596051baf289b4bbb42a27`. The Linux image source verification and service/module import checks passed without network access.
- Application runs as UID 10001 with a read-only root, dropped capabilities, bounded resources, separate input/state volumes and loopback-only binding. Mac URL: **http://127.0.0.1:8782/**. Health endpoint passed; Safari displayed the invitation-only sign-in screen.
- Verified research inputs were copied into the VM, excluding prior QA accounts and derived Mac views. Frozen market session: November 13. There is no default operator user or scheduled refresh with market credentials.

## Build defects fixed

The first clean Linux build exposed a missing `soupsieve` transitive pin. A clean Python 3.12 Linux resolver identified the complete dependency closure; the pin and official artifact hashes were added. The image integrity check then exposed omitted Docker metadata files and `shadow_bundle_backup.py` excluded by an overly broad ignore rule. Both were corrected. Local Compose's health check was adjusted for port 8782, and precreated private volumes were marked external to Compose.

## Security scan outcome

The initial application image had 146 HIGH/CRITICAL findings, including eight CRITICAL. Fixed official certifi 2026.10.18, Pillow 13.0.0 and urllib3 2.8.0 releases were pinned with hashes. Numerical library pins were retained. The base moved to immutable Python 3.12 / Debian Trixie digest `sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b`.

Final image scan: **zero CRITICAL, 49 HIGH OS-package findings; zero HIGH/CRITICAL Python-package findings**. The external release scan gate still fails. No findings were suppressed or silently waived. Reports are under `var/deployment/20261114/application-vulnerabilities-{initial,final}.json`.

The downloaded Caddy image has two HIGH findings (`CVE-2026-116587`, `CVE-2026-78661`) and is not used for local access. Its exact scan report is `var/deployment/20261114/caddy-vulnerabilities.json`. Public HTTPS release requires a remediated proxy and application image or a separately reviewed disposition of remaining findings.

The requested SBOM generation command was rejected by the user. No SBOM is claimed. That requirement remains open.

## Evidence and next action

Linux Python 3.12 acceptance: **30 passed**, zero failures/errors/skips (`var/deployment/20261114/linux-regression.xml`). The authenticated real-HTTP smoke passed every check with current November 13 data, including all dashboard modules, PDF exports, scenario accounting, unauthorized denial, no order routes, and session revocation (`linux-smoke/acceptance.json`).

Chromium and WebKit passed all 14 desktop/mobile sections, eight cycle scenarios, PDF/JSON downloads, tester calculations, viewer restrictions and logout, with zero page errors. Receipts/screenshots: `linux-browser-initial/` and `linux-webkit/` under the evidence directory. Firefox remains **blocked**: the default QA namespace restriction and missing OS user/profile were diagnosed and corrected in QA only, but the browser then crashed on creating a blank page before any application navigation. Its failure is saved in `firefox-profile-failure.log`; no Firefox acceptance is claimed. Production container sandbox settings were not changed.

The machine-readable consolidated receipt is `var/deployment/20261114/deployment-status.json`. A separate five-test release/hash utility check also passed on the Mac.

A consistent local backup was made while the preview was briefly stopped, then copied into the separate `regime-pilot-local-restore` volume. The preview was restarted. The restored image verified source/snapshot hashes, all four investor plans and PDF bindings, and SQLite integrity for all four databases, with zero users. Receipt: `var/deployment/20261114/local-restore-acceptance.json`; private backup directory: `var/deployment/20261114/local-backup/` (0700 directories / 0600 files). This proves a local restore of the current snapshot, not encrypted off-host recovery or recovery of future user data.

Tool identities, image identity, Linux resolution, build logs, image exports and scan reports reside under `var/deployment/20261114/`. The source remains a dirty-tree candidate; no clean reviewed-commit qualification is implied.

Create your individual local login through the terminal helper in `LOCAL_VM_PILOT.md`, complete the mandatory password change yourself, then run preflight. That operator credential step cannot be marked complete before you perform it. A later remote test with other people requires the remote VM/domain/HTTPS, data rights, credentials, external acceptance and off-host recovery steps in `WEEKEND_PILOT_DEPLOYMENT.md`.
