"""Local integrity-checked backup/restore of shadow ledger and its input bundle."""

from pathlib import Path
from datetime import datetime, timezone
import json
import shutil
import sqlite3
from strategy_integrity import file_hash, fingerprint
from strategy_receipts import atomic_json
from strategy_monthly_report import read_events


def verify_backup(root):
    root = Path(root)
    m = json.loads((root / "backup-manifest.json").read_text())
    identity = {k: v for k, v in m.items() if k != "manifest_id"}
    if fingerprint(identity) != m["manifest_id"]:
        raise ValueError("Backup manifest changed")
    for item in m["files"]:
        p = root / item["stored"]
        if (
            p.is_symlink()
            or p.resolve().parent != root.resolve()
            or file_hash(p) != item["sha256"]
        ):
            raise ValueError("Backup file integrity failure")
    mapped = {item["source"]: root / item["stored"] for item in m["files"]}
    if m.get("bundle_source"):
        b = json.loads(mapped[m["bundle_source"]].read_text())

        def stored(path):
            key = str(Path(path).resolve())
            if key not in mapped:
                raise ValueError("Incomplete backup input mapping")
            return mapped[key]

        capture = json.loads(stored(b["capture"]).read_text())
        report = json.loads(stored(b["training_report"]).read_text())
        if (
            file_hash(stored(b["capture"])) != report["capture_sha256"]
            or file_hash(stored(b["portfolio_contracts"])) != b["contract_map_sha256"]
        ):
            raise ValueError("Backup provenance mismatch")
        for metadata, parent in [
            (capture, Path(b["capture"]).parent),
            (report, Path(b["training_report"]).parent),
        ]:
            for name, digest in metadata.get(
                "files", metadata.get("artifacts", {})
            ).items():
                if (
                    Path(name).name != name
                    or file_hash(stored(parent / name)) != digest
                ):
                    raise ValueError("Backup input hash mismatch")
        ext = Path(b["benchmark_extension"])
        em = json.loads(stored(ext / "capture.json").read_text())
        if file_hash(stored(ext / "XLV-adjusted.csv")) != em["prices_sha256"]:
            raise ValueError("Backup healthcare mismatch")
    events = read_events(root / "ledger.sqlite3")
    return {
        "status": "LOCAL_BACKUP_VERIFIED",
        "events": len(events),
        "chain_head": events[-1][1] if events else None,
        "manifest_id": m["manifest_id"],
    }


def create_backup(database, bundle, destination):
    database = Path(database)
    bundle = Path(bundle)
    root = Path(destination)
    if root.exists():
        raise ValueError("New backup directory required")
    events = read_events(database)
    b = json.loads(bundle.read_text())
    sources = {bundle, Path(b["portfolio_contracts"])}
    capture = Path(b["capture"])
    cm = json.loads(capture.read_text())
    sources.add(capture)
    sources.update(capture.parent / name for name in cm["files"])
    report = Path(b["training_report"])
    sources.add(report)
    sources.update(
        report.parent / name for name in json.loads(report.read_text())["artifacts"]
    )
    ext = Path(b["benchmark_extension"])
    sources.update(
        ext / name for name in ["capture.json", "XLV-adjusted.csv", "news.json"]
    )
    root.mkdir(parents=True, mode=0o700)
    files = []
    with (
        sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as db,
        sqlite3.connect(root / "ledger.sqlite3") as target,
    ):
        db.backup(target)
    files.append(
        {
            "source": str(database.resolve()),
            "stored": "ledger.sqlite3",
            "sha256": file_hash(root / "ledger.sqlite3"),
        }
    )
    for i, source in enumerate(sorted(sources, key=str)):
        if source.is_symlink() or not source.is_file():
            raise ValueError("Regular backup source required")
        name = f"input-{i:03d}-{source.name}"
        shutil.copyfile(source, root / name)
        files.append(
            {
                "source": str(source.resolve()),
                "stored": name,
                "sha256": file_hash(root / name),
            }
        )
    m = {
        "schema_version": 1,
        "bundle_source": str(bundle.resolve()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
        "chain_head": events[-1][1] if events else None,
        "restoration": "Verified source-to-stored mapping. Rebind input paths explicitly before a host/job restart; no prior decisions are regenerated.",
    }
    m["manifest_id"] = fingerprint(m)
    atomic_json(root / "backup-manifest.json", m)
    for p in root.iterdir():
        p.chmod(0o600)
    return verify_backup(root)


def restore_backup(source, destination):
    original = verify_backup(source)
    dest = Path(destination)
    if dest.exists():
        raise ValueError("Restore destination must be new")
    shutil.copytree(source, dest)
    if verify_backup(dest) != original:
        raise ValueError("Restore does not reconcile")
    return {**original, "status": "LOCAL_RESTORE_VERIFIED"}
