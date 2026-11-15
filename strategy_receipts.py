"""Durable, validated v2 operational receipts; never upgrades legacy evidence."""

from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile

from strategy_integrity import canonical, fingerprint, strict_json


def atomic_json(path, value, *, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_observation(path, now=None):
    value = strict_json(path)
    return validate_observation(value, Path(path).stem, now)


def validate_observation(value, session, now=None):
    if not isinstance(value, dict) or value.get("schema_version") != 2:
        raise ValueError(
            "Validated v2 observation required; legacy evidence is not upgraded"
        )
    expected = value.get("receipt_sha256")
    body = {k: v for k, v in value.items() if k != "receipt_sha256"}
    evidence = value.get("evidence")
    if (
        fingerprint(body) != expected
        or value.get("release_approved") is not False
        or not isinstance(evidence, dict)
        or evidence.get("schema_version") != 2
        or evidence.get("status") != "LOCAL_ACCEPTANCE_PASSED"
        or not isinstance(evidence.get("checks"), dict)
        or not evidence["checks"]
        or not all(v is True for v in evidence["checks"].values())
    ):
        raise ValueError("Observation integrity failure")
    for name in ["report_sha256", "artifact_manifest_sha256"]:
        digest = evidence.get(name)
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("Observation digest missing")
    if session != evidence["market_session"]:
        raise ValueError("Observation session mismatch")
    stamp = datetime.fromisoformat(value["observed_at"])
    if stamp.tzinfo is None or stamp > (now or datetime.now(timezone.utc)):
        raise ValueError("Invalid receipt clock")
    return value


def quarantine_receipt(path, reason):
    """Explicit operator action: preserve a malformed record; never rewrite a valid seal."""
    import hashlib
    from datetime import date
    import uuid

    path = Path(path)
    date.fromisoformat(path.stem)
    if not reason or not reason.strip() or path.is_symlink() or not path.is_file():
        raise ValueError("Regular receipt and explicit reconciliation reason required")
    try:
        read_observation(path)
    except (ValueError, KeyError, TypeError):
        pass
    else:
        raise ValueError(
            "Valid sealed observations require a new cohort, not quarantine"
        )
    destination = (
        path.parent / "quarantine" / (path.stem + "-" + uuid.uuid4().hex + ".json")
    )
    destination.parent.mkdir(mode=0o700, exist_ok=True)
    atomic_json(
        destination.with_suffix(".receipt.json"),
        {
            "source": str(path),
            "destination": str(destination),
            "reason": reason,
            "raw_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "release_approved": False,
        },
    )
    os.replace(path, destination)
    return str(destination)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--quarantine-session", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    from datetime import date

    date.fromisoformat(args.quarantine_session)
    print(
        quarantine_receipt(args.root / (args.quarantine_session + ".json"), args.reason)
    )
