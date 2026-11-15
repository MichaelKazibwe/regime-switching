"""Protected-config, read-only IBKR paper capture; never a trading/observation job."""

from datetime import datetime, timezone
from pathlib import Path
import argparse
import re
import stat
import uuid

from ibkr_paper_probe import GatewayReader, snapshot
from strategy_integrity import strict_json, file_hash
from strategy_receipts import atomic_json


def capture(configuration, output, *, reader_factory=GatewayReader):
    path = Path(configuration)
    if (
        path.is_symlink()
        or not path.is_file()
        or stat.S_IMODE(path.stat().st_mode) & 0o077
    ):
        raise PermissionError("Regular protected owner-only configuration required")
    config = strict_json(path)
    if (
        set(config) != {"tenant", "paper_account", "gateway_ca_file"}
        or not isinstance(config["tenant"], str)
        or not config["tenant"].strip()
        or not isinstance(config["paper_account"], str)
        or not re.fullmatch(r"DU[0-9]+", config["paper_account"])
    ):
        raise ValueError("Exact paper capture configuration required")
    stamp = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    root = Path(output) / stamp
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    report = dict(
        status="BLOCKED",
        captured_at=datetime.now(timezone.utc).isoformat(),
        execution_enabled=False,
        release_approved=False,
        counts_as_performance_observation=False,
        configuration_sha256=file_hash(path),
        code_sha256=file_hash(__file__),
    )
    try:
        reader = reader_factory(cafile=config["gateway_ca_file"] or None)
        account = snapshot(reader, config["paper_account"])
        account["tenant"] = config["tenant"]
        atomic_json(root / "account.json", account, exclusive=True)
        report.update(
            status="READ_ONLY_PAPER_CAPTURE_UNQUALIFIED",
            account_sha256=file_hash(root / "account.json"),
        )
    except Exception as exc:
        # Never log authentication messages, account IDs, URLs or private data.
        report["reason"] = type(exc).__name__
    atomic_json(root / "receipt.json", report, exclusive=True)
    return report, root


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--configuration", required=True)
    p.add_argument("--output", default="var/managed-paper/read-only-captures")
    a = p.parse_args()
    report, _ = capture(a.configuration, a.output)
    print(report["status"])
    raise SystemExit(
        0 if report["status"] == "READ_ONLY_PAPER_CAPTURE_UNQUALIFIED" else 2
    )
