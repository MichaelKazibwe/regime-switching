"""Daily handoff from a qualified validation receipt to isolated shadow cohorts."""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from run_economic_p0_p1 import execute
from strategy_healthcheck import health
from strategy_integrity import strict_json, file_hash
from strategy_receipts import read_observation


def current_bundle(root):
    root = Path(root)
    state = health(root)
    if state["status"] != "HEALTHY_SHADOW_JOB":
        raise ValueError("Fresh completed validation required before economic handoff")
    job = strict_json(root / "latest-job.json")
    bundle = Path(job["job"]) / "dashboard" / "latest-strategy-run.json"
    receipt = read_observation(
        root / "observations" / (job["market_session"] + ".json")
    )
    if file_hash(bundle) != receipt["evidence"]["bundle_sha256"]:
        raise ValueError("Candidate bundle/receipt mismatch")
    return bundle


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validation-root", type=Path, default=Path("var/strategy-operations-integrated-v1")
    )
    parser.add_argument("--evidence-root", type=Path)
    args = parser.parse_args()
    bundle = current_bundle(args.validation_root)
    output = Path("var/economic-shadow") / datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    execute(
        bundle,
        output,
        evidence_root=args.evidence_root,
        run_experiments=False,
        register=True,
    )
