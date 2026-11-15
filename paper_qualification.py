"""Evidence ledger and fail-closed qualification report for a paper release.

Receipts are human attestations with hashed supporting files, not automated
proof that a remote system passed. Assessment checks their release binding,
integrity, reviewer and timestamp, and independently counts paper sessions.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import uuid

import pandas as pd

from paper_release import safe_file, sha256, verify
from paperstore import PaperStoreError, SQLitePaperStore
from researchdatastore import ResearchArtifactError, ResearchDataStore
from tradingcalendar import TradingCalendar


CHECKS = ("ci", "security", "host", "data_smoke", "alert_delivery", "restore_replay",
          "failure_drills", "ownership", "paper_signoff", "strategy_acceptance")


def record(root: Path, release: dict, check: str, artifacts: list[Path],
           reviewer: str, status: str) -> Path:
    if check not in CHECKS or status not in {"PASS", "FAIL"} or not reviewer.strip() or not artifacts:
        raise ValueError("A known check, PASS/FAIL, named reviewer, and supporting artifacts are required")
    receipts = root / "records"
    receipts.mkdir(parents=True, exist_ok=True)
    stored = []
    for source in artifacts:
        if not source.is_file() or source.is_symlink():
            raise ValueError("Evidence must be a regular file")
        digest = sha256(source)
        relative = f"artifacts/{digest}"
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(source, target)
            target.chmod(0o600)
        if sha256(target) != digest:
            raise ValueError("Evidence artifact is corrupt")
        stored.append({"path": relative, "sha256": digest})
    receipt = {"schema_version": 1, "release_id": release["release_id"],
               "source_commit": release["source_commit"], "check": check,
               "status": status, "reviewer": reviewer.strip(), "artifacts": stored,
               "recorded_at": datetime.now(timezone.utc).isoformat()}
    destination = receipts / f"{uuid.uuid4().hex}.json"
    with destination.open("x") as handle:
        json.dump(receipt, handle, indent=2, sort_keys=True)
        handle.write("\n")
    destination.chmod(0o600)
    return destination


def evidence_checks(root: Path, release: dict, *, now: datetime) -> dict:
    latest = {}
    for path in sorted((root / "records").glob("*.json")):
        item = json.loads(safe_file(root, str(path.relative_to(root))).read_text())
        if item.get("release_id") != release["release_id"]:
            continue
        check = item.get("check")
        if check not in CHECKS or item.get("schema_version") != 1:
            raise ValueError("Invalid qualification receipt")
        recorded = datetime.fromisoformat(item["recorded_at"])
        if recorded.tzinfo is None or recorded > now:
            raise ValueError("Invalid receipt timestamp")
        if item.get("source_commit") != release["source_commit"] or not item.get("reviewer", "").strip():
            raise ValueError("Receipt lacks matching source or reviewer")
        if not item.get("artifacts") or item.get("status") not in {"PASS", "FAIL"}:
            raise ValueError("Receipt lacks status or supporting evidence")
        for artifact in item["artifacts"]:
            if sha256(safe_file(root, artifact["path"])) != artifact["sha256"]:
                raise ValueError("Qualification artifact changed")
        if check not in latest or recorded > latest[check][0]:
            latest[check] = (recorded, item)
    return {check: latest[check][1]["status"] if check in latest else "BLOCKED" for check in CHECKS}


def observation(reports: Path, database: Path, *, now: datetime, source_commit: str,
                snapshots: Path, source_tree_sha256: str) -> dict:
    store = SQLitePaperStore(database, read_only=True)
    if not store.integrity_check()["healthy"]:
        raise ValueError("Observation database is unhealthy")
    calendar = TradingCalendar()
    sessions = {}
    incidents = []
    rebalances = 0
    configurations = set()
    research = ResearchDataStore(snapshots)
    for path in sorted(reports.glob("*.json")):
        report = json.loads(safe_file(reports, path.name).read_text())
        if report.get("status") != "APPROVED":
            incidents.append(report.get("cycle_id", path.name))
            continue
        event = store.get_event(report.get("event_id", ""))
        if event is None or event.event_hash != report.get("event_hash"):
            raise ValueError("Observation report is not backed by its database event")
        if event.event_type != "PAPER_DECISION_CYCLE" or event.payload.get("cycle_id") != report.get("cycle_id"):
            raise ValueError("Observation cycle identity is inconsistent")
        if report.get("decision") != event.payload.get("result"):
            raise ValueError("Observation decision differs from stored event")
        envelope = research.load_snapshot(event.payload["research_snapshot"])
        provenance = envelope["provenance"]
        if (provenance.get("code_revision") != source_commit
                or provenance.get("source_tree_sha256") != source_tree_sha256
                or provenance.get("dependency_mismatches") != {}
                or not provenance.get("python_version", "").startswith("3.12.")):
            raise ValueError("Observation runtime does not match the qualified release")
        configurations.add(event.payload.get("configuration_fingerprint"))
        if report.get("data_source") != "YAHOO_FINANCE+FRED" or event.payload.get("data_source") != report["data_source"]:
            raise ValueError("Synthetic or unknown data cannot qualify paper observation")
        stamp = pd.Timestamp(report["data_as_of"])
        updated = pd.Timestamp(report["updated_at"])
        occurred = pd.Timestamp(event.occurred_at)
        if (stamp.tzinfo is None or updated.tzinfo is None or occurred.tzinfo is None
                or updated > pd.Timestamp(now) or updated < occurred):
            raise ValueError("Observation timestamps must be aware and not in the future")
        expected = calendar.latest_completed_session(updated)
        if (expected is None or stamp != expected or calendar.latest_completed_session(occurred) != stamp
                or str(event.payload.get("data_as_of")) != report["data_as_of"]):
            raise ValueError("Observation was not based on the latest completed NYSE close")
        day = stamp.tz_convert("America/New_York").date().isoformat()
        if day in sessions:
            raise ValueError("Multiple cycles claim the same observation session")
        execution = report["decision"].get("paper_execution") or {}
        if execution.get("status") not in {"EXECUTED", "NOT_DUE", "NO_ORDERS"}:
            raise ValueError("Observation lacks a completed paper lifecycle")
        if any(order.get("reconciliation", {}).get("approved") is not True for order in execution.get("orders", [])):
            raise ValueError("Observation has unreconciled orders")
        if execution["status"] == "EXECUTED":
            if not execution.get("orders"):
                raise ValueError("Completed rebalance must contain reconciled orders")
            rebalances += 1
        sessions[day] = stamp
    missing = []
    if sessions:
        start, end = min(sessions), max(sessions)
        for day in pd.date_range(start, end, freq="D"):
            if calendar.is_trading_day(day) and day.date().isoformat() not in sessions:
                missing.append(day.date().isoformat())
    latest = calendar.latest_completed_session(now)
    current = bool(sessions) and latest == max(sessions.values())
    passed = (len(sessions) >= 60 and rebalances >= 3 and not missing and not incidents
              and current and len(configurations) == 1 and None not in configurations)
    return {"status": "PASS" if passed else "BLOCKED", "sessions": len(sessions),
            "completed_rebalances": rebalances, "missing_sessions": missing,
            "incidents": incidents, "current_through_latest_close": current,
            "configuration_count": len(configurations)}


def assess(release_root: Path, evidence: Path, reports: Path, database: Path, *, snapshots=None, now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    release = json.loads((release_root / "release-manifest.json").read_text())
    verify(release_root, release)
    checks = evidence_checks(evidence, release, now=now)
    checks["clean_release"] = "PASS" if release.get("clean_commit") is True else "BLOCKED"
    source_hash = hashlib.sha256()
    for name in sorted(release["files"]):
        if name.endswith(".py") and "/" not in name:
            source_hash.update(name.encode() + b"\0" + (release_root / name).read_bytes() + b"\0")
    try:
        soak = observation(reports, database, now=now, source_commit=release["source_commit"],
                           snapshots=snapshots or database.parent / "research-snapshots",
                           source_tree_sha256=source_hash.hexdigest())
    except (ValueError, OSError, KeyError, TypeError, PaperStoreError, ResearchArtifactError) as exc:
        soak = {"status": "BLOCKED", "error": str(exc)}
    checks["paper_observation"] = soak["status"]
    # Research acceptance is visible but distinct from operational qualification.
    operational = {key: value for key, value in checks.items() if key != "strategy_acceptance"}
    return {"schema_version": 1, "release_id": release["release_id"],
            "source_commit": release["source_commit"], "checks": checks, "observation": soak,
            "paper_operations": "PASS" if all(value == "PASS" for value in operational.values()) else "BLOCKED",
            "strategy_acceptance": checks["strategy_acceptance"],
            "assessed_at": now.isoformat()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, default=Path("var/qualification"))
    commands = parser.add_subparsers(dest="command", required=True)
    receipt = commands.add_parser("record")
    receipt.add_argument("--check", choices=CHECKS, required=True)
    receipt.add_argument("--status", choices=("PASS", "FAIL"), required=True)
    receipt.add_argument("--reviewer", required=True)
    receipt.add_argument("--artifact", type=Path, action="append", required=True)
    check = commands.add_parser("assess")
    check.add_argument("--reports", type=Path, default=Path("var/paper-reports"))
    check.add_argument("--database", type=Path, default=Path("var/paper-state.sqlite3"))
    check.add_argument("--snapshots", type=Path, default=Path("var/research-snapshots"))
    check.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "record":
            release = json.loads((args.release / "release-manifest.json").read_text())
            verify(args.release, release)
            path = record(args.evidence, release, args.check, args.artifact, args.reviewer, args.status)
            result = {"status": "RECORDED_ATTESTATION", "receipt": str(path)}
        else:
            result = assess(args.release, args.evidence, args.reports, args.database, snapshots=args.snapshots)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps(result, sort_keys=True))
        return 0 if args.command == "record" or result["paper_operations"] == "PASS" else 2
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
