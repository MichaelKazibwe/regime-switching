"""Coherent local-VM recovery export under all registered research writer locks."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tarfile
import time

from forward_cohort import database, observations
from pilot_recovery import backup, restore
from pilot_release import verify_context
from pilot_snapshot_locks import quiesce, WRITER_LOCKS
from research_publisher import docker_command
from strategy_receipts import atomic_json


VOLUMES = {
    "inputs": "regime-pilot-local-inputs",
    "state": "regime-pilot-local-state",
    "daily": "regime-pilot-local-daily",
    "weekly": "regime-pilot-local-weekly",
}


def snapshot(output, source_context, key, *, root=Path.cwd()):
    root, output, source_context = map(lambda p: Path(p).resolve(), (root, output, source_context))
    if output.exists() or not output.is_relative_to(root / "var"):
        raise ValueError("New private recovery directory beneath project var required")
    release = verify_context(source_context)
    output.mkdir(parents=True, mode=0o700)
    components = output / "components"
    components.mkdir(mode=0o700)
    docker = docker_command()

    def run(args, timeout=120):
        return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout).stdout.strip()

    container = "regime-pilot-local-pilot-1"
    image = run(docker + ["inspect", container, "--format", "{{.Image}}"])
    installed = run(docker + ["exec", container, "python", "-c",
        "from pathlib import Path; print(Path('/app/pilot-release.json').read_text())"])
    if json.loads(installed)["release_id"] != release["release_id"]:
        raise ValueError("Backup source context must match the installed image")
    began = datetime.now(timezone.utc).isoformat()
    paths = {}
    with quiesce(root) as held:
        stop_requested = False
        stop_at = time.monotonic()
        try:
            stop_requested = True
            run(["sh", str(root / "deploy/pilot/local-vm.sh"), "stop"])
            for label, volume in VOLUMES.items():
                archive = output / (label + ".tar")
                exporter = "import sys,tarfile; t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|'); t.add('/data',arcname='.'); t.close()"
                with archive.open("xb") as stream:
                    archive.chmod(0o600)
                    subprocess.run(docker + ["run", "--rm", "--network", "none", "--read-only",
                        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                        "--mount", f"type=volume,src={volume},dst=/data,readonly",
                        "--entrypoint", "python", image, "-c", exporter],
                        stdout=stream, stderr=subprocess.PIPE, check=True, timeout=120)
                target = components / label
                target.mkdir(mode=0o700)
                with tarfile.open(archive) as exported:
                    exported.extractall(target, filter="data")
                paths[label] = target
            for name in ("strategy-operations-integrated-v1", "return-engine-shadow-v1", "dynamic-forward-v1"):
                source = root / "var" / name
                target = components / ("host-" + name)
                target.mkdir(mode=0o700)
                dbpath = database(source)
                with sqlite3.connect(f"file:{dbpath}?mode=ro", uri=True) as src, sqlite3.connect(target / dbpath.name) as dst:
                    src.backup(dst)
                    if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise ValueError("Host cohort snapshot failed integrity check")
                shutil.copyfile(source / "active-cohort.json", target / "active-cohort.json")
                if observations(source).is_dir():
                    shutil.copytree(observations(source), target / "observations")
                paths["host-" + name] = target
            for name in ("macro-alpha", "forecast-coverage"):
                source = root / "var" / name
                target = components / name
                shutil.copytree(source, target)
                paths[name.replace("-", "_")] = target
            shutil.copytree(source_context, components / "reviewed_source")
            paths["reviewed_source"] = components / "reviewed_source"
            atomic_json(output / "quiescence.json", dict(status="REGISTERED_WRITERS_QUIESCED",
                started_at=began, captured_at=datetime.now(timezone.utc).isoformat(),
                lock_protocols=list(WRITER_LOCKS), lock_count=len(held), app_stopped=True,
                installed_image=image, source_release_id=release["release_id"],
                scope="Registered host research/scheduler entry points and local app; arbitrary external filesystem edits excluded"))
        finally:
            if stop_requested:
                run(["sh", str(root / "deploy/pilot/local-vm.sh"), "start"])
                atomic_json(output / "restart.json", dict(app_restart_requested=True,
                    app_stop_seconds=time.monotonic()-stop_at, execution_enabled=False))
    for p in output.rglob("*"):
        p.chmod(0o600 if p.is_file() else 0o700)
    receipt = backup(paths, output / "pilot-recovery.enc", key,
                     quiescence_receipt=str(output / "quiescence.json"))
    atomic_json(output / "backup-receipt.json", receipt)
    checked = restore(output / "pilot-recovery.enc", output / "restored", key)
    atomic_json(output / "restore-receipt.json", checked)
    return dict(status="COORDINATED_LOCAL_SNAPSHOT_VERIFIED", image=image,
                source_release_id=release["release_id"], manifest_id=checked["manifest_id"],
                off_host_recovery_proven=False, execution_enabled=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-context", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    args = parser.parse_args()
    print(snapshot(args.output, args.source_context, args.key))
