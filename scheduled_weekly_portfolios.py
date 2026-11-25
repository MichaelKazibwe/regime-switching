"""Bounded weekly research generation and atomic, verified local-VM publication."""

import argparse
import os
from datetime import datetime, timezone
import fcntl
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

from strategy_integrity import strict_json, file_hash, fingerprint
from strategy_receipts import atomic_json
from observation_process import run_bounded, install_cancellation
from weekly_portfolios import weekly_session, SOURCES, verify

from research_publisher import docker_command, installed_image, filesystem_publish

ROOT = Path(__file__).resolve().parent


def publish(directory, image=None):
    """Never expose partial artifacts; require the installed image to verify source hashes."""
    if os.environ.get('PILOT_WEEKLY_PUBLISH_ROOT'):
        return filesystem_publish(directory, os.environ['PILOT_WEEKLY_PUBLISH_ROOT'], kind='weekly')
    DOCKER = docker_command()
    directory = Path(directory).resolve()
    data = verify(directory)
    revision = data["research_id"]
    if image is None:
        image = installed_image()
    with tempfile.TemporaryDirectory(prefix="weekly-publish-") as tmp:
        archive = Path(tmp) / "artifacts.tar"
        with tarfile.open(archive, "w") as tar:
            for name in ("manifest.json", "recommendations.json", "dashboard-report.pdf"):
                tar.add(directory / name, arcname=f"{revision}/{name}", recursive=False)
        # This dedicated volume contains only public-to-invited-users research, never auth state.
        script = f"""
import os, shutil, sys, tarfile, tempfile
from pathlib import Path
from weekly_portfolios import verify
from research_publisher import prior_weekly_session
from strategy_receipts import atomic_json
root = Path('/weekly/published')
root.mkdir(parents=True, exist_ok=True)
temporary = Path(tempfile.mkdtemp(prefix='.staging-', dir=root))
try:
    tarfile.open(fileobj=sys.stdin.buffer, mode='r|').extractall(temporary, filter='data')
    staged, target = temporary / '{revision}', root / '{revision}'
    data = verify(staged)
    previous = root / 'latest.json'
    if previous.is_file():
        if prior_weekly_session(root) > data['market_session']:
            raise ValueError('Weekly session rollback forbidden')
    if target.exists():
        verify(target)
    else:
        os.rename(staged, target)
    atomic_json(root / 'latest.json', dict(research_id='{revision}'))
finally:
    shutil.rmtree(temporary)
"""
        with archive.open("rb") as stream:
            subprocess.run(DOCKER + ["run", "--rm", "-i", "--network", "none", "--read-only",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "10001:10001",
                "--mount", "type=volume,src=regime-pilot-local-weekly,dst=/weekly", "--entrypoint", "python", image,
                "-c", script], stdin=stream, check=True, timeout=90)
    return revision


def tick(root=Path("var/weekly-portfolios"), now=None, publish_vm=False):
    now = now or datetime.now(timezone.utc)
    session = weekly_session(now)
    pointer = strict_json("var/dashboard-live/latest.json")
    if pointer.get("market_session", "") < session:
        return dict(status="WAITING_FOR_VERIFIED_WEEKLY_DATA", market_session=session)
    if file_hash(pointer["bundle"]) != pointer["bundle_sha256"]:
        raise ValueError("Published source bundle mismatch")
    lookthrough_root = os.environ.get("PILOT_LOOKTHROUGH_ROOT")
    holdings_hashes = None
    if lookthrough_root:
        from portfolio_exposures import reviewed_evidence
        holdings_hashes = reviewed_evidence(lookthrough_root, now)["source_hashes"]
    key = fingerprint(dict(session=session, bundle_sha256=pointer["bundle_sha256"], document_sha256=pointer["document_sha256"],
                           sources={s: file_hash(s) for s in SOURCES}, holdings_evidence=holdings_hashes))
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return dict(status="ALREADY_RUNNING", market_session=session)
        latest = strict_json(root / "latest.json") if (root / "latest.json").exists() else {}
        if latest.get("key") == key and latest.get("status") == "COMPLETED_REVIEW_ONLY":
            verify(latest["directory"])
            if publish_vm:
                publish(latest["directory"])
            return dict(status="ALREADY_COMPLETED", market_session=session, directory=latest["directory"])
        if latest.get("key") == key and latest.get("attempt", 0) >= 2:
            return dict(status="RETRY_LIMIT_REACHED", market_session=session)
        attempt = latest.get("attempt", 0) + 1 if latest.get("key") == key else 1
        directory = root / "runs" / f"{session}-{key[:12]}-{attempt}"
        record = dict(key=key, attempt=attempt, market_session=session, directory=str(directory.resolve()), status="RUNNING")
        atomic_json(root / "latest.json", record)
        try:
            record['stage'] = 'GENERATION'
            command = [sys.executable, "weekly_portfolios.py", "--bundle", pointer["bundle"],
                       "--output", str(directory)]
            if lookthrough_root:
                command += ["--lookthrough-root", str(Path(lookthrough_root).resolve())]
            with (root / "worker.log").open("ab") as log:
                code = run_bounded(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
            if code.returncode != 0:
                raise RuntimeError("Weekly research failed; inspect worker.log")
            record['stage'] = 'VERIFY_ARTIFACTS'
            verify(directory)
            if publish_vm:
                record['stage'] = 'PUBLICATION'
                publish(directory)
            record.update(status="COMPLETED_REVIEW_ONLY", stage="COMPLETE")
            return record
        except Exception as error:
            record.update(status="FAILED", error_type=type(error).__name__,
                          failure_class="PUBLICATION" if record['stage'] == 'PUBLICATION' else 'GENERATION_OR_INTEGRITY')
            raise
        finally:
            record['finished_at'] = datetime.now(timezone.utc).isoformat()
            atomic_json(root / 'latest.json', record)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish-vm", action="store_true")
    args = parser.parse_args()
    install_cancellation()
    print(tick(publish_vm=args.publish_vm))
