"""Single-host shadow backup objectives and isolated recorded-NAV restore drills."""

from pathlib import Path
from datetime import datetime, timezone
from time import monotonic
import json
import numpy as np
from shadow_bundle_backup import create_backup, restore_backup, verify_backup
from strategy_monthly_report import read_events
from strategy_integrity import file_hash
from strategy_receipts import atomic_json


def nav_replay(database):
    events = read_events(database)
    previous = None
    marks_checked = 0
    for event, _ in events:
        if previous:
            for name, state in event["states"].items():
                nav = previous["states"][name]["nav"]
                peak = previous["states"][name]["peak"]
                for mark in event["marks"].get(name, []):
                    nav *= 1 + mark["net_return"]
                    peak = max(peak, nav)
                    if not np.isclose(
                        nav, mark["nav"], rtol=1e-10, atol=1e-12
                    ) or not np.isclose(nav / peak - 1, mark["drawdown"], atol=1e-10):
                        raise ValueError("Restored NAV/peak replay mismatch")
                    marks_checked += 1
                if not np.isclose(nav, state["nav"], atol=1e-10) or not np.isclose(
                    peak, state["peak"], atol=1e-10
                ):
                    raise ValueError("Restored state mismatch")
        previous = event
    return dict(
        chain_head=events[-1][1] if events else None,
        events=len(events),
        marks_checked=marks_checked,
        replay="Recorded-return NAV and peak replay; not independent alpha/market-price reconstruction",
    )


def snapshot(databases, bundle, destination, *, now=None):
    now = now or datetime.now(timezone.utc)
    root = Path(destination)
    if root.exists():
        raise ValueError("New backup destination required")
    root.mkdir(parents=True, mode=0o700)
    components = {}
    for name, database in databases.items():
        if Path(name).name != name:
            raise ValueError("Safe component name required")
        before = nav_replay(database)
        proof = create_backup(database, bundle, root / name)
        after = nav_replay(database)
        if before != after or proof["chain_head"] != before["chain_head"]:
            raise ValueError(
                "Writer changed during backup; retry without overwriting this attempt"
            )
        components[name] = dict(
            source=str(Path(database).resolve()),
            chain_head=before["chain_head"],
            events=before["events"],
            manifest_sha256=file_hash(root / name / "backup-manifest.json"),
        )
    document = dict(
        created_at=now.isoformat(),
        components=components,
        bundle_sha256=file_hash(bundle),
        off_host_verified=False,
        execution_enabled=False,
    )
    atomic_json(root / "recovery-manifest.json", document, exclusive=True)
    return document


def drill(source, destination, *, rto_seconds=900):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise ValueError("Isolated new restore directory required")
    started = monotonic()
    manifest = json.loads((source / "recovery-manifest.json").read_text())
    destination.mkdir(parents=True, mode=0o700)
    results = {}
    for name, item in manifest["components"].items():
        if (
            Path(name).name != name
            or file_hash(source / name / "backup-manifest.json")
            != item["manifest_sha256"]
        ):
            raise ValueError("Recovery inventory mismatch")
        verify_backup(source / name)
        restore_backup(source / name, destination / name)
        result = nav_replay(destination / name / "ledger.sqlite3")
        if (
            result["chain_head"] != item["chain_head"]
            or result["events"] != item["events"]
        ):
            raise ValueError("Recovery loses committed state")
        results[name] = result
    elapsed = monotonic() - started
    proof = dict(
        status="LOCAL_RESTORE_OBJECTIVE_PASS"
        if elapsed <= rto_seconds
        else "RTO_BREACH",
        elapsed_seconds=elapsed,
        rto_target_seconds=rto_seconds,
        components=results,
        off_host_verified=False,
        restart_paths_rebound=False,
        execution_enabled=False,
    )
    atomic_json(destination / "drill.json", proof, exclusive=True)
    return proof
