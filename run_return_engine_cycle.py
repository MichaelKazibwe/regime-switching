"""Locked, idempotent private challenger cycle using a fresh verified bundle.

Refresh market/macro inputs first. No host scheduler is installed by this CLI.
"""

from datetime import datetime, timezone
from pathlib import Path
import argparse
import fcntl
import json
from tempfile import TemporaryDirectory
from evaluate_institutional_engines import run as evaluate
from assess_return_engine_robustness import assess
from return_engine_shadow import advance
from publish_return_engine_preview import publish
from strategy_receipts import atomic_json
from strategy_integrity import file_hash
from dynamic_portfolio import refresh as refresh_dynamic


def cycle(
    bundle,
    *,
    root="var/institutional-return-engines",
    database="var/return-engine-shadow-v1/prospective.sqlite3",
    dashboard="var/investor-dashboard/investor-dashboard.html",
    dynamic_output=None,
    publish_preview=True,
):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    dynamic_output = (
        Path(dynamic_output) if dynamic_output else root / "dynamic-latest.json"
    )
    latest = root / "latest.json"
    with (root / "cycle.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Validate the new blend before any ledger or dashboard mutation.
        # The temporary candidate is never advertised as the latest snapshot.
        with TemporaryDirectory(prefix="dynamic-cycle-") as temporary:
            dynamic = refresh_dynamic(bundle, Path(temporary) / "candidate.json")
        if latest.exists():
            saved = json.loads(latest.read_text())
            if saved["bundle_sha256"] == file_hash(bundle):
                result = advance(
                    bundle, saved["assessment"], saved["robustness"], database
                )
                if publish_preview:
                    publish(saved["assessment"], saved["robustness"], dashboard)
                atomic_json(dynamic_output, dynamic)
                return {
                    **result,
                    "evaluation_reused": True,
                    "dynamic_snapshot_id": dynamic["snapshot_id"],
                    "dynamic_output": str(dynamic_output),
                }
        output = root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        evaluate(bundle, output)
        assessment = output / "assessment.json"
        robustness = output / "robustness.json"
        assess(assessment, bundle, robustness)
        registration = advance(bundle, assessment, robustness, database)
        if publish_preview:
            publish(assessment, robustness, dashboard)
        saved = {
            "bundle_sha256": file_hash(bundle),
            "assessment": str(assessment.resolve()),
            "robustness": str(robustness.resolve()),
            "database": str(Path(database).resolve()),
            "registration": registration,
            "promotion_enabled": False,
        }
        atomic_json(latest, saved)
        atomic_json(dynamic_output, dynamic)
        return {
            **registration,
            "evaluation_reused": False,
            "dynamic_snapshot_id": dynamic["snapshot_id"],
            "dynamic_output": str(dynamic_output),
        }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--bundle", default="var/investor-dashboard/latest-strategy-run.json"
    )
    p.add_argument("--root", default="var/institutional-return-engines")
    p.add_argument("--dynamic-output", default=None)
    p.add_argument(
        "--database", default="var/return-engine-shadow-v1/prospective.sqlite3"
    )
    p.add_argument(
        "--dashboard", default="var/investor-dashboard/investor-dashboard.html"
    )
    a = p.parse_args()
    print(
        json.dumps(
            cycle(
                a.bundle,
                root=a.root,
                database=a.database,
                dashboard=a.dashboard,
                dynamic_output=a.dynamic_output,
            ),
            indent=2,
        )
    )
