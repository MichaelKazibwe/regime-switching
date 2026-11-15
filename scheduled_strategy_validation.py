"""Locked daily shadow refresh into an isolated candidate workspace."""

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from productreport import private_write
from strategy_receipts import atomic_json, read_observation
from strategy_operations import audit, observe
from strategy_training_data import usable_session
from observation_process import run_bounded
from forward_cohort import database as cohort_database


def run(root, *, refresh=False):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / "job.lock").open("a") as lock:
        os.fchmod(lock.fileno(), 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("A validation job is already active") from None
        if refresh:
            session = str(usable_session(datetime.now(timezone.utc)).date())
            receipt = root / "observations" / (session + ".json")
            if receipt.exists():
                read_observation(receipt)
                from strategy_healthcheck import health

                if health(root)["status"] != "HEALTHY_SHADOW_JOB":
                    raise ValueError(
                        "Receipt exists but job chain needs operator reconciliation"
                    )
                return {
                    "status": "ALREADY_OBSERVED",
                    "market_session": session,
                    "promotion": "NONE",
                }
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        job = root / "runs" / stamp
        job.mkdir(parents=True, mode=0o700)
        status = {
            "schema_version": 2,
            "run_id": stamp,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "RUNNING",
            "promotion": "NONE",
        }
        atomic_json(job / "status.json", status)
        atomic_json(root / "latest-job.json", {"job": str(job), **status})
        try:
            resume = None
            # latest-job was replaced above; inspect the prior immutable failure records.
            if refresh:
                from observation_recovery import reusable_bundle

                for old in sorted((root / "runs").iterdir(), reverse=True):
                    if old == job or not (old / "status.json").is_file():
                        continue
                    saved = json.loads((old / "status.json").read_text())
                    if saved.get("status") != "FAILED":
                        continue
                    try:
                        resume = reusable_bundle(old, session)
                    except (OSError, ValueError, KeyError, TypeError):
                        resume = None
                    if resume:
                        status["reused_training_from"] = str(old)
                        break
            if refresh:
                candidate = job / "dashboard"
                template = (
                    Path(status["reused_training_from"]) / "dashboard"
                    if resume
                    else Path("var/investor-dashboard")
                )
                shutil.copytree(template, candidate)
                # Reuse only the prior dashboard as a template; fresh inputs are downloaded.
                command = [
                    sys.executable,
                    "refresh_strategy_dashboard.py",
                    "--dashboard",
                    str(candidate / "investor-dashboard.html"),
                    "--investor-pdf",
                    str(job / "investor-report.pdf"),
                ]
                command += (
                    [
                        "--capture",
                        resume["capture"],
                        "--training-report",
                        resume["training_report"],
                        "--benchmark-extension",
                        resume["benchmark_extension"],
                    ]
                    if resume
                    else ["--download"]
                )
                if resume and resume.get("latest_macro_features"):
                    command += [
                        "--latest-macro-features",
                        resume["latest_macro_features"],
                    ]
                status["stage"] = "REPORT_REBUILD" if resume else "CAPTURE_TRAIN_REPORT"
                log_path = job / "refresh.log"
                private_write(log_path, "")
                with log_path.open("w") as log:
                    completed = run_bounded(
                        command,
                        cwd=Path(__file__).resolve().parent,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        timeout=7200,
                    )
                    if completed.returncode:
                        raise subprocess.CalledProcessError(
                            completed.returncode, command
                        )
            else:
                candidate = job / "dashboard"
                shutil.copytree("var/investor-dashboard", candidate)
            status["stage"] = "ARTIFACT_AUDIT"
            evidence = audit(
                candidate / "latest-strategy-run.json",
                candidate / "investor-dashboard.html",
            )
            private_write(job / "acceptance.json", json.dumps(evidence, indent=2))
            from prospective_strategy_ledger import advance_from_bundle, summary

            status["stage"] = "FORWARD_LEDGER"
            ledger = advance_from_bundle(
                candidate / "latest-strategy-run.json",
                cohort_database(root),
                evidence,
            )
            atomic_json(
                root / "prospective-summary.json", summary(cohort_database(root))
            )
            status["stage"] = "OBSERVATION_RECEIPT"
            observation = observe(evidence, root / "observations")
            private_write(
                root / "observation-status.json", json.dumps(observation, indent=2)
            )
            status.update(
                status="PASSED_SHADOW_ONLY",
                market_session=evidence["market_session"],
                observation=observation,
                prospective=ledger,
                report_sha256=evidence["report_sha256"],
                artifact_manifest_sha256=evidence["artifact_manifest_sha256"],
                stage="COMPLETE",
            )
        except Exception as exc:
            status.update(
                status="FAILED",
                error_type=type(exc).__name__,
                failure_class="INTEGRITY_OR_DATA"
                if isinstance(exc, ValueError)
                else "RUNTIME_OR_PROVIDER",
            )
            raise
        finally:
            status["finished_at"] = datetime.now(timezone.utc).isoformat()
            atomic_json(job / "status.json", status)
            atomic_json(root / "latest-job.json", {"job": str(job), **status})
        return status


def main():
    from observation_process import install_cancellation

    install_cancellation()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="var/strategy-operations-integrated-v1")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Download and evaluate a new isolated candidate",
    )
    args = parser.parse_args()
    print(json.dumps(run(args.root, refresh=args.refresh), indent=2))


if __name__ == "__main__":
    main()
