# Source cleanup and commit preparation — 15 November 2026

Removed **62 reviewed root targets (66 files, about 261 MiB)**: obsolete source snapshots and patches, timestamped backup directories, redundant test copies, stale generated inventories/logs, a project ZIP and an unrelated VS Code installer. Private recovery copies of removed source/evidence are retained in `var/cleanup/20261115/removed-files-recovery.tar.gz`, with a SHA-256 removal manifest. The downloadable installer was discarded without a recovery copy. Runtime ledgers, market captures, models, authentication data, current deployment volumes, active recovery tools, standalone research commands and the intentional `archive/` boundary were preserved.

Canonical alert and risk-governor tests replace byte/AST-identical copies. The old trade-analytics source-copy test was replaced by a small wrapper calling the canonical production regression. The collection comparison confirms that only those four superseded test modules left discovery. The lower test count reflects deduplication, not disabled failure checks.

Additional cleanup:

- `pytest.ini` prevents discovery inside generated runtime/Docker build contexts, which previously produced six duplicate-import collection errors.
- `.gitignore` excludes all generated output, Python tool caches, downloads and obsolete source recovery files, alongside existing private runtime/environment/database exclusions.
- The final regression inventory explicitly classifies all **399** root Python modules other than the regression harness, including retained research/pilot libraries and tests. New unclassified root files still fail the inventory gate.
- Six LaunchAgent source configurations are portable templates. Their rendered configurations were compared with all six installed agents and matched exactly; running schedules were not changed. Both existing installers render paths before comparing/installing configurations.
- `README.md` provides the current entry points and separates historical phase reports from current deployment evidence.
- `.gitattributes` standardizes source text line endings. Staged CSV/Markdown/test whitespace was normalized, and proof CSV writers now emit LF so regenerated evidence remains clean.

## Verification

- **1,412 tests passed** in 90.57 seconds in a fresh, isolated, hash-locked Python 3.14 environment. The release target remains Python 3.12; earlier exact Linux pilot testing is recorded separately.
- **54/54 end-to-end paper-execution proofs passed**; zero failed, blocked or skipped. Proof reports were regenerated.
- Full repository Ruff checks, `pip check`, Git whitespace checks, explicit source inventory and Python-artifact hygiene passed.
- All retained import-graph dependencies for the pilot, daily training, observation scheduler, research benchmark, paper runtime and managed/recommendation APIs exist.
- Trivy secret scanning of the materialized commit candidate found **zero secrets**. Private runtime, local credentials, databases, generated PDFs, image exports and recovery archives are excluded from the candidate.

The first global-Python regression attempt correctly rejected old installed dependency versions after the security lock updates. The final run used the isolated `.venv` with the locked packages; the global Python environment and installed training job were not modified.

Local evidence, the removal manifest, before/after collection lists, regression XML, scan results and proposed commit message are in `var/cleanup/20261115/`. Source changes are prepared for a reviewed commit; no commit or push is performed by this cleanup. Existing substantive feature changes were preserved rather than reverted. Staging this candidate does not grant production or financial approval: the documented external security findings, Firefox issue, SBOM and off-host recovery gates remain open.
