"""Private pilot runtime checks; infrastructure and investment approval stay separate."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil

from pilot_release import verify_context, verify_snapshot, materialize_snapshot
from pilot_auth import AuthStore
from strategy_dashboard_server import Application
from strategy_training_data import usable_session
from strategy_integrity import strict_json
from strategy_receipts import atomic_json


def run(snapshot, state, *, local_preview=False):
    snapshot, state = Path(snapshot).resolve(), Path(state).resolve()
    daily = os.environ.get("PILOT_DAILY_ROOT")
    if daily and (Path(daily) / "latest.json").is_file():
        from pilot_daily import revision_directory
        _, directory = revision_directory(daily)
        snapshot = directory / "launch.json"
    source = verify_context(Path.cwd())
    inputs = verify_snapshot(snapshot.parent)
    launch = strict_json(snapshot)
    document = materialize_snapshot(snapshot.parent, state)
    app = Application(document, snapshot.parent / launch["capture"],
                      snapshot.parent / launch["training_report"], state / "preflight-pdfs")
    auth = AuthStore(state / "auth.sqlite3")
    users = auth.list_users()
    checks = dict(source_hashes=True, portable_snapshot=True, numerical_and_pdf_bindings=True,
                  current_market_session=inputs["market_session"] == str(usable_session(datetime.now(timezone.utc)).date()),
                  invited_user_completed_password_change=any(u["active"] and not u["must_change"] for u in users),
                  private_auth_database=(state / "auth.sqlite3").stat().st_mode & 0o777 == 0o600,
                  disk_reserve=shutil.disk_usage(state).free >= 1024**3,
                  linux_runtime=platform.system() == "Linux", non_root=os.geteuid() != 0)
    required = {k: v for k, v in checks.items() if not (local_preview and k == "linux_runtime")}
    return dict(status="PASSED_LOCAL_RUNTIME_CHECKS" if all(required.values()) else "BLOCKED_RUNTIME_CHECKS",
                checks=checks, source_release_id=source["release_id"], source_qualification=source["qualification"],
                market_session=app.payload["training"]["market_session"], local_preview=local_preview,
                remaining_external_checks=["Exact Linux image build, vulnerability scan and digest",
                                           "DNS and valid external HTTPS", "Host firewall and resource qualification",
                                           "Encrypted off-host backup and restore", "Owner source/data-access review"],
                production_approval=False, execution_enabled=False)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot", type=Path, default=Path("var/pilot-input/launch.json"))
    p.add_argument("--state", type=Path, default=Path("var/pilot"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--local-preview", action="store_true")
    a = p.parse_args()
    result = run(a.snapshot, a.state, local_preview=a.local_preview)
    atomic_json(a.output, result)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASSED_LOCAL_RUNTIME_CHECKS" else 2)
