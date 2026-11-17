"""Publish verified daily data to the local VM without rebuilding or restarting it."""

import argparse
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

from pilot_release import snapshot, verify_snapshot, materialize_snapshot
from strategy_dashboard_server import Application
from strategy_integrity import strict_json, fingerprint, file_hash
from strategy_receipts import atomic_json
from strategy_training_data import usable_session

DOCKER = ["/opt/homebrew/bin/docker", "--context", "colima-regime-pilot"]
FIELDS = ("dashboard_root", "document", "payload", "lab", "results", "news")


def revision_directory(root):
    root = Path(root)
    revision = strict_json(root / "latest.json")["revision"]
    if not isinstance(revision, str) or len(revision) != 64 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("Invalid daily revision")
    directory = root / revision
    if directory.is_symlink() or fingerprint(verify_snapshot(directory)) != revision:
        raise ValueError("Daily snapshot revision mismatch")
    return revision, directory


def candidate(directory, state):
    directory, state = Path(directory), Path(state)
    document = materialize_snapshot(directory, state)
    launch = strict_json(directory / "launch.json")
    paths = [directory / launch[k] for k in ("capture", "training_report")]
    if any(p.is_absolute() and not p.resolve().is_relative_to(directory.resolve()) for p in paths):
        raise ValueError("Daily launch paths must be contained")
    app = Application(document, *paths, state / "shared-saved-pdfs")
    if not app.lab["report"]["current_numerical_source_match"]:
        raise ValueError("Daily data requires the installed numerical sources")
    if app.payload["training"]["market_session"] != verify_snapshot(directory)["market_session"]:
        raise ValueError("Daily session mismatch")
    return app


def refresh(application, root, state, active_revision):
    """Caller holds the application lock. Replace every data/PDF binding together."""
    revision, directory = revision_directory(root)
    if revision == active_revision:
        application.refresh_error = None
        return revision
    updated = candidate(directory, state)
    if updated.payload["training"]["market_session"] < application.payload["training"]["market_session"]:
        raise ValueError("Daily market-session rollback rejected")
    replacement = {field: getattr(updated, field) for field in FIELDS}
    for field, value in replacement.items():
        setattr(application, field, value)
    application.refresh_error = None
    return revision


def publish(directory, image=None):
    directory = Path(directory).resolve()
    revision = fingerprint(verify_snapshot(directory))
    if image is None:
        image = subprocess.run(DOCKER + ["inspect", "regime-pilot-local-pilot-1", "--format", "{{.Image}}"],
                               check=True, capture_output=True, text=True, timeout=30).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="pilot-daily-") as tmp:
        archive = Path(tmp) / "snapshot.tar"
        with tarfile.open(archive, "w") as tar:
            tar.add(directory, arcname=revision)
        script = f"""
import os, shutil, sys, tarfile, tempfile
from pathlib import Path
from pilot_daily import candidate
from pilot_release import verify_snapshot
from strategy_integrity import fingerprint
from strategy_receipts import atomic_json
root = Path('/daily')
temporary = Path(tempfile.mkdtemp(prefix='.staging-', dir=root))
try:
    tarfile.open(fileobj=sys.stdin.buffer, mode='r|').extractall(temporary, filter='data')
    staged, target = temporary / '{revision}', root / '{revision}'
    if fingerprint(verify_snapshot(staged)) != '{revision}':
        raise ValueError('Daily identity mismatch')
    candidate(staged, temporary / 'verification')
    if target.exists():
        if fingerprint(verify_snapshot(target)) != '{revision}':
            raise ValueError('Existing daily identity mismatch')
    else:
        os.rename(staged, target)
    previous = root / 'latest.json'
    if previous.exists():
        from pilot_daily import revision_directory
        _, prior = revision_directory(root)
        if verify_snapshot(target)['market_session'] < verify_snapshot(prior)['market_session']:
            raise ValueError('Daily publication rollback rejected')
    atomic_json(previous, dict(revision='{revision}'))
finally:
    shutil.rmtree(temporary)
"""
        with archive.open("rb") as stream:
            subprocess.run(DOCKER + ["run", "--rm", "-i", "--network", "none", "--read-only",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "10001:10001",
                "--memory", "2g", "--cpus", "2", "--tmpfs", "/tmp:size=256m,mode=1777",
                "--mount", "type=volume,src=regime-pilot-local-daily,dst=/daily", "--entrypoint", "python", image,
                "-c", script], stdin=stream, check=True, timeout=180)
    return revision


def tick(root=Path("var/pilot-daily"), now=None, publish_vm=False):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / "publish.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return dict(status="ALREADY_RUNNING")
        expected = str(usable_session(now or datetime.now(timezone.utc)).date())
        pointer = strict_json("var/dashboard-live/latest.json")
        if pointer["market_session"] != expected:
            result = dict(status="WAITING_FOR_VERIFIED_DAILY_CAPTURE", expected_session=expected,
                          retained_session=pointer["market_session"])
            atomic_json(root / "heartbeat.json", result)
            return result
        from macro_alpha import build as macro_build, record as macro_record
        bundle = strict_json(pointer['bundle'])
        alpha = macro_build(bundle['capture'], bundle['training_report'])
        macro_record(alpha, strict_json(Path(bundle['training_report']).parent / 'features.json'),
                     'var/macro-alpha', now=now)
        benchmark_pointer = Path("var/cycle-benchmark/latest.json")
        benchmark = None
        if benchmark_pointer.is_file():
            bound = strict_json(benchmark_pointer)
            benchmark = Path(bound["benchmark"])
            if file_hash(benchmark) != bound["sha256"]:
                raise ValueError("Cycle benchmark pointer hash mismatch")
            evidence = strict_json(benchmark)
            if any(file_hash(p) != h for p, h in evidence["source_hashes"].items()):
                raise ValueError("Cycle benchmark sources are stale")
        key = fingerprint(dict(document=pointer["document_sha256"], bundle=pointer["bundle_sha256"],
                               benchmark=file_hash(benchmark) if benchmark else None,
                               macro_alpha_source=file_hash("macro_alpha.py"),
                               macro_alpha_forecast=alpha["forecast_id"]))
        directory = root / "snapshots" / key
        if not directory.exists():
            directory.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="prepare-", dir=directory.parent) as tmp:
                staged = Path(tmp) / "snapshot"
                snapshot(Path.cwd(), staged, "var/dashboard-live/latest.json", benchmark=benchmark)
                staged.rename(directory)
        manifest = verify_snapshot(directory)
        if manifest["market_session"] != expected:
            raise ValueError("Published pointer and daily snapshot session differ")
        revision = fingerprint(manifest)
        previous = strict_json(root / "heartbeat.json") if (root / "heartbeat.json").exists() else {}
        if publish_vm and (previous.get("revision") != revision or previous.get("status") != "PUBLISHED"):
            publish(directory)
        result = dict(status="PUBLISHED" if publish_vm else "PREPARED", market_session=expected,
                      revision=revision, directory=str(directory.resolve()),
                      checked_at=datetime.now(timezone.utc).isoformat(), execution_enabled=False)
        atomic_json(root / "heartbeat.json", result)
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish-vm", action="store_true")
    args = parser.parse_args()
    print(json.dumps(tick(publish_vm=args.publish_vm)))
