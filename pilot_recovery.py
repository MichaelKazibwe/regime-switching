"""Bounded authenticated full-pilot backups; off-host qualification remains separate."""

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import sqlite3
import stat
import tarfile
import tempfile

from strategy_integrity import file_hash, fingerprint

MAGIC = b"REGIME-PILOT-AESGCM-V1\x00"
MAX_BYTES = 512 * 1024 * 1024


def init_key(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(secrets.token_bytes(32))


def read_key(path):
    path = Path(path)
    if (
        path.is_symlink()
        or not stat.S_ISREG(path.stat().st_mode)
        or path.stat().st_mode & 0o077
    ):
        raise ValueError("Encryption key must be a private regular 0600 file")
    key = path.read_bytes()
    if len(key) != 32:
        raise ValueError("256-bit backup key required")
    return key


def backup(paths, destination, key_path, *, quiescence_receipt):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not quiescence_receipt or not isinstance(quiescence_receipt, str):
        raise ValueError("Recorded writer-quiescence evidence required")
    destination = Path(destination)
    if destination.exists():
        raise ValueError("Use a new encrypted backup destination")
    files = {}
    with tempfile.TemporaryDirectory(prefix="regime-recovery-") as tmp:
        root = Path(tmp)
        for label, source in paths.items():
            if not re.fullmatch("[A-Za-z0-9_-]+", label):
                raise ValueError("Safe backup component labels required")
            source = Path(source)
            if not source.exists() or source.is_symlink():
                raise ValueError("Regular existing backup sources required")
            for p in sorted(source.rglob("*")) if source.is_dir() else [source]:
                if p.is_symlink():
                    raise ValueError("Backup symlinks forbidden")
                if not p.is_file() or p.name.endswith(("-wal", "-shm")):
                    continue
                if p.resolve() == Path(key_path).resolve():
                    raise ValueError("Never include the encryption key in its backup")
                relative = Path(label) / (
                    p.relative_to(source) if source.is_dir() else p.name
                )
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                if p.suffix in {".sqlite3", ".sqlite", ".db"}:
                    with (
                        sqlite3.connect(f"file:{p.resolve()}?mode=ro", uri=True) as src,
                        sqlite3.connect(target) as dst,
                    ):
                        src.backup(dst)
                        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                            raise ValueError("Backup database integrity failure")
                else:
                    shutil.copyfile(p, target)
                target.chmod(0o600)
                files[str(relative)] = file_hash(target)
                if (
                    sum(x.stat().st_size for x in root.rglob("*") if x.is_file())
                    > MAX_BYTES
                ):
                    raise ValueError(
                        "Backup exceeds bounded pilot archive size; use a reviewed streaming backup service"
                    )
        if not files:
            raise ValueError("Nonempty complete-service component set required")
        manifest = dict(
            schema_version=1,
            created_at=datetime.now(timezone.utc).isoformat(),
            components=sorted(paths),
            files=files,
            quiescence_receipt=quiescence_receipt,
            off_host_recovery_proven=False,
        )
        manifest["manifest_id"] = fingerprint(manifest)
        (root / "recovery-manifest.json").write_text(
            json.dumps(manifest, sort_keys=True)
        )
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as tar:
            for p in sorted(root.rglob("*")):
                if p.is_file():
                    tar.add(p, arcname=str(p.relative_to(root)), recursive=False)
        plaintext = stream.getvalue()
        if len(plaintext) > MAX_BYTES:
            raise ValueError("Archive exceeds backup size limit")
        nonce = secrets.token_bytes(12)
        ciphertext = (
            MAGIC + nonce + AESGCM(read_key(key_path)).encrypt(nonce, plaintext, MAGIC)
        )
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(ciphertext)
        return dict(
            status="LOCAL_ENCRYPTED_BACKUP_CREATED",
            manifest_id=manifest["manifest_id"],
            ciphertext_sha256=hashlib.sha256(ciphertext).hexdigest(),
            components=manifest["components"],
            off_host_recovery_proven=False,
        )


def restore(source, destination, key_path):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    source, destination = Path(source), Path(destination)
    if destination.exists() or source.stat().st_size > MAX_BYTES + 128:
        raise ValueError(
            "New isolated restore destination and bounded archive required"
        )
    blob = source.read_bytes()
    if not blob.startswith(MAGIC):
        raise ValueError("Unknown encrypted archive format")
    offset = len(MAGIC)
    plain = AESGCM(read_key(key_path)).decrypt(
        blob[offset : offset + 12], blob[offset + 12 :], MAGIC
    )
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(
        prefix="verify-restore-", dir=destination.parent
    ) as tmp:
        root = Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(plain), mode="r:") as tar:
            members = tar.getmembers()
            if (
                len({m.name for m in members}) != len(members)
                or sum(m.size for m in members) > MAX_BYTES
            ):
                raise ValueError("Duplicate or oversized restore archive")
            for member in members:
                p = Path(member.name)
                if not member.isfile() or p.is_absolute() or ".." in p.parts:
                    raise ValueError("Unsafe restore archive member")
            tar.extractall(root, filter="data")
        manifest = json.loads((root / "recovery-manifest.json").read_text())
        if (
            fingerprint({k: v for k, v in manifest.items() if k != "manifest_id"})
            != manifest["manifest_id"]
        ):
            raise ValueError("Restore manifest mismatch")
        expected = set(manifest["files"]) | {"recovery-manifest.json"}
        actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
        if actual != expected:
            raise ValueError("Restore contains missing or unlisted artifacts")
        for name, digest in manifest["files"].items():
            p = root / name
            if file_hash(p) != digest:
                raise ValueError("Restored artifact hash mismatch")
            p.chmod(0o600)
            if p.suffix in {".sqlite3", ".sqlite", ".db"}:
                with sqlite3.connect(p) as db:
                    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise ValueError("Restored database integrity failure")
        os.rename(root, destination)
    return dict(
        status="ISOLATED_LOCAL_RESTORE_VERIFIED",
        manifest_id=manifest["manifest_id"],
        components=manifest["components"],
        off_host_recovery_proven=False,
        execution_enabled=False,
    )


def main():
    """Local-only operations: never creates cloud accounts or incurs charges."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    key = commands.add_parser("init-key")
    key.add_argument("--key", type=Path, required=True)
    create = commands.add_parser("backup")
    create.add_argument(
        "--components",
        type=Path,
        required=True,
        help="JSON object mapping component labels to paths",
    )
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--key", type=Path, required=True)
    create.add_argument("--quiescence-receipt", required=True)
    recover = commands.add_parser("restore")
    recover.add_argument("--archive", type=Path, required=True)
    recover.add_argument("--output", type=Path, required=True)
    recover.add_argument("--key", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "init-key":
        init_key(args.key)
        result = dict(status="PRIVATE_KEY_CREATED", secret_printed=False)
    elif args.command == "backup":
        result = backup(
            json.loads(args.components.read_text()),
            args.output,
            args.key,
            quiescence_receipt=args.quiescence_receipt,
        )
    else:
        result = restore(args.archive, args.output, args.key)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
