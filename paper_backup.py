"""Create and verify a complete paper-runtime backup while holding its worker lock."""

from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile

from audittrail import OperationalAuditTrail
from paperconfig import PaperRuntimeConfig
from paper_release import safe_file, sha256
from paperstore import SQLitePaperStore
from researchdatastore import ResearchDataStore


def verify_bundle(root: Path, *, replay: bool = False) -> dict:
    root = root.resolve()
    document = json.loads(safe_file(root, "backup-manifest.json").read_text())
    if document.get("schema_version") != 1 or not document.get("files"):
        raise ValueError("Invalid backup manifest")
    files = document["files"]
    entries = list(root.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise ValueError("Backup contains a symlink")
    actual = {str(path.relative_to(root)) for path in entries if path.is_file()}
    if actual != set(files) | {"backup-manifest.json"}:
        raise ValueError("Backup file inventory differs from manifest")
    for name, expected in files.items():
        if sha256(safe_file(root, name)) != expected:
            raise ValueError(f"Backup checksum mismatch: {name}")
    database = safe_file(root, document["database"])
    store = SQLitePaperStore(database, read_only=True)
    if not store.integrity_check()["healthy"]:
        raise ValueError("Backup database/event chain is unhealthy")
    audit_path = safe_file(root, document["audit_log"])
    audit = OperationalAuditTrail(audit_path)
    if not audit.verify()["healthy"]:
        raise ValueError("Backup audit chain is unhealthy")
    audit_ids = {record.event["event_id"] for record in audit.read()}
    snapshots = root / document["snapshots"]
    if not snapshots.resolve().is_relative_to(root):
        raise ValueError("Snapshot directory escapes backup")
    snapshot_store = ResearchDataStore(snapshots)
    cycles = 0
    replay_results = []
    for event in store.read_events():
        if not event.event_id.startswith("paper-cycle:"):
            continue
        if event.event_id not in audit_ids:
            raise ValueError(f"Cycle missing from audit trail: {event.event_id}")
        snapshot_store.load_snapshot(event.payload["research_snapshot"])
        cycles += 1
        if replay:
            from researchreplay import replay_decision

            result = replay_decision(store, snapshot_store, event.event_id)
            if not result["exact_match"]:
                raise ValueError(f"Replay mismatch: {event.event_id}")
            replay_results.append(result)
    return {"status": "PASS", "cycles_verified": cycles, "replays": replay_results,
            "files_verified": len(files)}


def create_bundle(config: PaperRuntimeConfig, root: Path, destination: Path) -> dict:
    root = root.resolve()
    destination = destination.resolve()
    if destination.exists() or destination.is_relative_to(root):
        raise ValueError("Backup destination must be new and outside the runtime root")
    relative = {}
    for name, path in (("database", config.state_database), ("audit_log", config.audit_log),
                       ("snapshots", config.research_snapshot_directory)):
        absolute = path.resolve()
        if not absolute.is_relative_to(root):
            raise ValueError(f"Configured {name} must be inside runtime root")
        relative[name] = str(absolute.relative_to(root))
    database = safe_file(root, relative["database"])
    safe_file(root, relative["audit_log"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock_path = database.with_suffix(database.suffix + ".lock")
    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Worker is active; backup requires its exclusive lock") from exc
        with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
            temporary = Path(directory) / "bundle"
            temporary.mkdir(mode=0o700)
            skipped = {database, database.with_name(database.name + "-wal"),
                       database.with_name(database.name + "-shm"), lock_path,
                       root / "backup-manifest.json"}
            for path in sorted(root.rglob("*")):
                if path.is_symlink():
                    raise ValueError("Symlinks are forbidden in runtime backups")
                if not path.is_file() or path in skipped:
                    continue
                name = str(path.relative_to(root))
                source = safe_file(root, name)
                target = temporary / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                target.chmod(0o600)
            target_database = temporary / relative["database"]
            target_database.parent.mkdir(parents=True, exist_ok=True)
            SQLitePaperStore(database, read_only=True).backup_to(target_database)
            with sqlite3.connect(target_database) as connection:
                connection.execute("PRAGMA journal_mode = DELETE")
            target_database.chmod(0o600)
            files = {str(path.relative_to(temporary)): sha256(path)
                     for path in sorted(temporary.rglob("*")) if path.is_file()}
            document = {"schema_version": 1, **relative, "files": files}
            (temporary / "backup-manifest.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
            result = verify_bundle(temporary)
            temporary.rename(destination)
    return {**result, "backup": str(destination)}


def restore_bundle(source: Path, destination: Path, *, replay: bool = False) -> dict:
    if destination.exists():
        raise ValueError("Restore destination must not exist; never overwrite active state")
    verify_bundle(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
        temporary = Path(directory) / "restore"
        shutil.copytree(source, temporary)
        temporary.chmod(0o700)
        result = verify_bundle(temporary, replay=replay)
        temporary.rename(destination)
    return {**result, "restore": str(destination)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("create")
    backup.add_argument("--runtime-root", type=Path, default=Path("var"))
    backup.add_argument("--destination", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("source", type=Path)
    verify.add_argument("--replay", action="store_true")
    restore = commands.add_parser("restore")
    restore.add_argument("source", type=Path)
    restore.add_argument("destination", type=Path)
    restore.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    if args.command == "create":
        result = create_bundle(PaperRuntimeConfig.from_env(), args.runtime_root, args.destination)
    elif args.command == "verify":
        result = verify_bundle(args.source, replay=args.replay)
    else:
        result = restore_bundle(args.source, args.destination, replay=args.replay)
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
