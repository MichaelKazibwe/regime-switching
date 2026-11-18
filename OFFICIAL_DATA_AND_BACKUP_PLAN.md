# Official data qualification and off-host recovery

Owner direction recorded 2026-11-17: prefer governing/statistical bodies in each jurisdiction. This is a source-selection policy, not a claim that new feeds have passed qualification.

| Data | Preferred evidence | Qualification boundary |
|---|---|---|
| US macroeconomic releases | Original BLS/BEA/Federal Reserve releases; FRED/ALFRED for traceable series and vintages | Keep release time, revision vintage, series definition and original agency. Current revised values cannot stand in for historical availability. |
| Euro-area macro and monetary data | ECB and Eurostat; relevant national statistical offices | Preserve geography, seasonal adjustment, units and release calendar. Do not substitute euro-area inflation for US CPI. |
| UK activity, inflation and labour | ONS | Observation period and publication date are separate fields. |
| UK monetary/rate data | Bank of England | Reference rates require an explicit valuation convention; they are not executable quotes. |
| UK fiscal data | HM Treasury, OBR and DMO as applicable | Treasury/Exchequer material supports fiscal analysis, not general stock-price validation. |
| Other jurisdictions | Relevant central bank, national statistical office and finance ministry | Admit each series after definition, release-time, revision and rights checks. |
| Security prices and corporate actions | Official exchange feeds, issuer announcements and licensed exchange-derived records | Require coverage, adjusted-return reconciliation, currency, session, dividends, splits, delistings and access rights. Macro feeds cannot fill this role. |
| Fund look-through | Dated fund-issuer holdings and regulatory filings | Preserve holdings date and actual publication time; quantify stale and unknown exposures. |
| Historical universe membership | Dated exchange/index-provider constituent events and delisting records | Current constituents are insufficient for point-in-time backtests. Missing evidence keeps that qualification closed. |

Every qualified capture needs its original URL/provider, retrieval timestamp, observation period/session, publication/availability timestamp, vintage, units/currency, adjustment basis, content hash and rights review. A recognized institution alone does not prove that a particular dataset is suitable. Daily monitoring may report the latest published monthly/quarterly observation; it must not manufacture daily observations.

Official references:

- https://fred.stlouisfed.org/docs/api/fred/alfred.html
- https://data.ecb.europa.eu/help/api/overview
- https://developer.ons.gov.uk/
- https://www.bankofengland.co.uk/statistics/
- https://www.gov.uk/government/organisations/hm-treasury

## Free pilot and recovery route

Owner instruction on 2026-11-17 supersedes the paid-storage proposal: skip every step requiring payment. No cloud VM, paid domain, paid data subscription or paid storage will be purchased.

- **Hosting:** keep the existing local Linux VM and loopback binding. No public endpoint or domain is required for local testing. Do not open router ports to bypass remote qualification.
- **Off-host archive:** use a Proton Drive Free account for a manual upload of the already-encrypted `.enc` archive. Proton advertises up to 5 GB free; a new account may require welcome tasks to unlock the full allocation. Check actual available space before copying. No payment method or upgrade is needed for this route.
- **Automation alternative:** Backblaze B2 advertises the first 10 GB free and says a billing method is not required to get started. Consider it only in an account with no payment method and after verifying the account's current quotas and access. Free storage is not an unlimited free-service guarantee. Stop uploads before the quota; never enable automatic upgrades.
- **Second independent copy:** an existing removable drive stored separately is useful if already owned. Do not buy hardware under this instruction.
- **Access:** free local testing is supported now. Remote access remains disabled. Tailscale Personal is advertised for personal use with up to six users; a client/commercial pilot must not assume that eligibility. Do not deploy it under a personal plan without checking the applicable terms.

### Recovery procedure

1. Create the storage account yourself, enable MFA and retain account recovery material separately. Do not send passwords or keys through chat.
2. Generate a private local key with `python pilot_recovery.py init-key --key <private-key-path>`. Keep a second protected key copy away from both the VM and storage account.
3. Stop scheduled writers and the app for a coherent full-service snapshot. Record the quiescence evidence. Export the VM volumes and include current source/release, account database, cohorts and receipts, macro-alpha records, daily/weekly publications and pointers. Never include the encryption key in the archive.
4. Supply a JSON mapping of component labels to exported paths, then run `python pilot_recovery.py backup --components <components.json> --output <new-archive.enc> --key <private-key-path> --quiescence-receipt <receipt-reference>`. The bounded tool rejects archives above 512 MiB; larger services need a separately reviewed streaming implementation.
5. Upload only the encrypted archive. Download it into a new location, verify its ciphertext hash against the local receipt, and run `python pilot_recovery.py restore --archive <download.enc> --output <new-isolated-directory> --key <private-key-path>`.
6. Check restored service bindings and database integrity in an isolated environment. Revoke restored sessions before any real service activation. Measure recovery time and recovered-data age. Restart the original service and confirm it retains its previous good revisions.
7. Keep enough free quota for the next complete generation. Rotate only after a verified newer recovery point exists. Manual free storage does not provide automated immutable retention; record this reduced protection explicitly.

Off-host recovery remains unqualified until an actual upload, download and isolated restore succeed. Encryption tests alone cannot close that gate. No account is connected yet, so the external upload cannot be performed by the project.

Official references checked 2026-11-17:

- https://proton.me/drive/pricing?mode=sps&plan=free
- https://proton.me/support/more-storage-proton-drive
- https://proton.me/support/set-up-proton-drive
- https://www.backblaze.com/cloud-storage/pricing
- https://help.backblaze.com/hc/en-us
- https://tailscale.com/docs/account/manage-plans/free-plans-discounts

## Prepared local recovery point

The post-review encrypted archive is `var/project-review/recovery-after-review/pilot-recovery-20261117-post-review.enc` (131,194,931 bytes). Its SHA-256 is `4003657c859a33a18ae8d68ccaa8ae838e38b667e2cd2686effc4658087bf6c4`. The private key is `.secrets/pilot-recovery/20261117-post-review.key`; keep it separate. Both paths are ignored by Git. The original pre-upgrade recovery point is retained. Do not upload plaintext export or restored directories.

Install the pinned operator dependencies in an isolated environment before using the CLI: `python -m pip install --require-hashes -r requirements-paper.hashed.lock -r requirements-ops.hashed.lock`. No paid tooling is required.

## November 18 execution update

The November 17 encrypted recovery point was uploaded to Proton, downloaded, matched by SHA-256 and restored in the exact Linux image. The key was not uploaded. Evidence is private at `var/project-review/proton-offhost-20261118/off-host-recovery-receipt.json`. Proton auto-renewal was cancelled with owner authorization; the account transitions to Free on December 18. MFA enrollment remains an owner action.

A subsequent local snapshot now holds all ten registered research writer locks during export and stops the app. Use `python pilot_snapshot.py --output var/recovery/<new-id> --source-context <installed-source-context> --key <private-key-path>`. The source context must match the installed image. The initial coordinated rehearsal passed authenticated local restore and exact-image Linux restore; the measured app stop was approximately 38 seconds. This improves registered-writer consistency but does not certify arbitrary external file edits, a second independent recovery host or a second protected key copy. A newer coordinated archive must receive its own off-host test before replacing the earlier verified off-host recovery point.

See [the remaining qualification requirements](PILOT_GATE_REQUIREMENTS.md). Earlier prepared-archive and signup instructions above are historical records, not the current completion status.

The coordinated snapshot also includes an allowlisted `operator_source` component with the restore/export code, hash-locked numerical and encryption dependencies, and deployment instructions. It does not rely on the original checkout being present on a replacement host. Independent-device restore and out-of-band key protection still require their own evidence.
