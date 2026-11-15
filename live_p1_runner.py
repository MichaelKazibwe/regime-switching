"""Bound the P1 monitor process; retain timeout/failure status independently."""

from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import subprocess
import sys
from observation_process import run_bounded, install_cancellation
from strategy_receipts import atomic_json


def run(root="var/live-upgrade-p1", configuration=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    now = datetime.now(timezone.utc)
    status = dict(status="RUNNING", started_at=now.isoformat(), execution_enabled=False)
    atomic_json(root / "runner-status.json", status)
    command = [sys.executable, "live_p1_service.py", "--root", str(root)]
    if configuration:
        command += ["--configuration", configuration]
    log = root / "worker-logs" / (now.strftime("%Y%m%dT%H%M%S%fZ") + ".log")
    log.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with log.open("w") as stream:
            completed = run_bounded(
                command,
                cwd=Path(__file__).resolve().parent,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=900,
            )
        status.update(
            status="COMPLETED" if completed.returncode == 0 else "FAILED",
            exit_code=completed.returncode,
        )
        return completed.returncode
    except Exception as exc:
        status.update(status="FAILED", error_type=type(exc).__name__)
        return 2
    finally:
        status["finished_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(root / "runner-status.json", status)


if __name__ == "__main__":
    install_cancellation()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default="var/live-upgrade-p1")
    p.add_argument("--configuration")
    a = p.parse_args()
    code = run(a.root, a.configuration)
    print(json.dumps(dict(exit_code=code, execution_enabled=False)))
    raise SystemExit(code)
