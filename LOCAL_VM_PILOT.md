# Local Linux VM deployment

The selected target is the `regime-pilot` Linux VM on this Mac. This is a local research preview. It does not provide invited users on other computers with access, and it needs no domain or cloud subscription. The VM has two CPUs, 4 GiB RAM and a 35 GiB data disk; the Mac home directory is not mounted in it.

The application uses a pinned native Linux ARM64 image, runs as UID 10001 with a read-only root filesystem, and listens only on the VM's loopback address. Colima forwards the preview to **http://127.0.0.1:8782/** on the Mac. Inputs and account state reside in dedicated Docker volumes; prior QA accounts are excluded. No public ports or market API credentials are configured.

## Operate the deployed preview

From the project directory:

```sh
sh deploy/pilot/local-vm.sh status
sh deploy/pilot/local-vm.sh logs
sh deploy/pilot/local-vm.sh stop
sh deploy/pilot/local-vm.sh start
```

After restarting the Mac, start the VM first with `colima start regime-pilot --activate=false`, then start the application. The image identity is stored in `var/deployment/20261114/local.env`; the helper uses a separate Docker CLI configuration without changing the active Docker context. Do not run `down -v` or delete the named volumes: they contain private state.

## Create your individual login

The deployed preview has no built-in default user. In your terminal, run:

```sh
sh deploy/pilot/local-vm.sh invite YOUR_USERNAME --role tester
```

Enter and confirm a unique temporary password at the hidden prompts. Open the preview URL, sign in and complete the required password change yourself. Passwords must be 12–256 characters. Do not send passwords in chat. For read-only access, use `--role viewer`. List users with the `users` helper and disable an account with `revoke YOUR_USERNAME`.

Then run:

```sh
sh deploy/pilot/local-vm.sh preflight
```

The invitation/password-change check remains incomplete until you finish that step. Readiness also requires the currently eligible completed market session; this deployment is a frozen snapshot and has no automatic market refresh until credentials and collection are deliberately configured. Historical results do not become new forward observations by copying them to the VM.

## Local and external qualification

Build, image identity, vulnerability scan and Linux test evidence are stored under `var/deployment/20261114/`. A failed security scan is not an approval for external deployment. The initially scanned Caddy image has two HIGH advisories and is not used by this local preview. The initial application scan prompted fixed certifi, Pillow and urllib3 versions and a newer pinned Debian base; retain the final scan findings when assessing external release readiness.

The application source remains a dirty-tree candidate. No public Git push, registry upload, cloud purchase or invitation message was performed. For a remote invited group later, follow `WEEKEND_PILOT_DEPLOYMENT.md`: choose a remote VM and domain, resolve external security gates, configure HTTPS, supply authorized data credentials, prove off-host backup/restore, and repeat acceptance on that exact host and architecture. A localhost URL cannot be used by testers on other computers.
