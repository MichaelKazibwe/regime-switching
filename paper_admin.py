"""Administrative maintenance commands for paper deployment state."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from paperstore import SQLitePaperStore
from paperconfig import PaperRuntimeConfig
from paperdata import PaperDataProvider
from paperdata import PaperDataError
from secretredaction import redact_sensitive_message
from researchdatastore import ResearchDataStore
from researchreplay import ResearchReplayError, replay_decision
from paperalerts import notify_operator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="var/paper-state.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup", help="Create a consistent SQLite backup")
    backup.add_argument("destination")
    commands.add_parser("verify", help="Check SQLite integrity and event-chain hashes")
    commands.add_parser("alert-test", help="Send one controlled paper alert; requires configured SMTP")
    commands.add_parser(
        "data-smoke",
        help="Fetch and validate market/macro inputs without running decisions or orders",
    )
    replay = commands.add_parser(
        "replay",
        help="Recompute a stored decision without submitting orders",
    )
    replay.add_argument("--event-id", required=True)
    replay.add_argument("--snapshots", default="var/research-snapshots")
    args = parser.parse_args(argv)

    if args.command == "alert-test":
        config = PaperRuntimeConfig.from_env()
        result = notify_operator(
            config, cycle_id="operator-delivery-test", status="FAILED",
            message="Controlled paper deployment alert test. Please confirm receipt to the operator.",
        )
        safe = redact_sensitive_message(
            json.dumps(result), (os.environ.get("PAPER_SMTP_PASSWORD", ""),)
        )
        print(json.dumps({"status": "SENT" if result and result.get("delivered") else "BLOCKED",
                          "notification": json.loads(safe), "human_receipt_confirmed": False}))
        return 0 if result and result.get("delivered") else 2

    if args.command == "data-smoke":
        config = PaperRuntimeConfig.from_env()
        provider = PaperDataProvider(config)
        try:
            provider._fred()  # validate secret availability before network access
            observations = provider()
        except Exception as exc:
            status = "BLOCKED" if isinstance(exc, PaperDataError) and "required" in str(exc) else "FAILED"
            error = redact_sensitive_message(
                f"{type(exc).__name__}: {exc}",
                tuple(os.environ.get(key, "") for key in ("FRED_API_KEY", "PAPER_SMTP_PASSWORD")),
            )
            print(json.dumps({"status": status, "error": error}, sort_keys=True))
            return 2 if status == "BLOCKED" else 1
        print(json.dumps({
            "status": "PASS",
            "data_as_of": observations["data_as_of"].isoformat(),
            "data_source": observations["data_source"],
            "price_rows": int(len(observations["prices"])),
            "asset_count": int(len(observations["prices"].columns)),
            "regime_count": int(len(observations["regimes"])),
            "macro_fields": sorted(observations["macro_data"]),
            "benchmark": config.benchmark,
        }, sort_keys=True))
        return 0
    store = SQLitePaperStore(
        Path(args.database),
        read_only=args.command in {"replay", "verify", "backup"},
    )
    if args.command == "replay":
        try:
            result = replay_decision(
                store,
                ResearchDataStore(args.snapshots),
                args.event_id,
            )
        except ResearchReplayError as exc:
            print(json.dumps({"status": "FAILED", "error": str(exc)}, sort_keys=True))
            return 1
        print(json.dumps(result, sort_keys=True, default=str))
        return 0 if result["exact_match"] else 1
    if args.command == "backup":
        destination = store.backup_to(args.destination)
        verification = SQLitePaperStore(destination).integrity_check()
        print(json.dumps({"backup": str(destination), **verification}, sort_keys=True))
        return 0 if verification["healthy"] else 1

    verification = store.integrity_check()
    print(json.dumps(verification, sort_keys=True))
    return 0 if verification["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
