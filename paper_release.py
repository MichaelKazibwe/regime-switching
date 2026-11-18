"""Create and verify a minimal, content-addressed paper release context."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ENTRIES = (
    "paper_service", "paper_admin", "paper_release", "paper_backup",
    "paper_qualification", "macrovintage", "lock_paper_dependencies", "paper_dashboard_server",
    "monthlyreport", "monthlydelivery",
)
RUNTIME_RESOURCES = (
    "deploy/runtime/build_sqlite.py", "deploy/runtime/collect_runtime.py",
    "deploy/runtime/README.md",
)
RESOURCES = RUNTIME_RESOURCES + (
    "research/global_asset_registry.json",
    "Dockerfile", "compose.paper.yaml", ".dockerignore", ".env.paper.example",
    "OPERATIONAL_RUNBOOK.md", "PAPER_DEPLOYMENT_GUIDE.md", "STRATEGY_ACCEPTANCE.md",
    "deploy/systemd/README.md", "deploy/systemd/paper-worker.service",
    "deploy/systemd/paper-worker.timer", "deploy/operator.example.json",
    "requirements-paper.in", "requirements-dev.in", "requirements-paper.lock",
    "requirements-dev.lock", "requirements-paper.hashed.lock", "requirements-dev.hashed.lock",
    "dashboard/index.html", "dashboard/dashboard.css", "dashboard/dashboard.js",
    "deploy/systemd/monthly-report.service", "deploy/systemd/monthly-report.timer",
    "deploy/monthly-recipients.example.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_file(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(part in {"..", "."} for part in path.parts):
        raise ValueError(f"Unsafe artifact path: {relative}")
    candidate = root / path
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Artifact escapes root: {relative}")
    for parent in (candidate, *candidate.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError(f"Symlinks are not release artifacts: {relative}")
    if not candidate.is_file():
        raise ValueError(f"Missing artifact: {relative}")
    return candidate


def runtime_sources(root: Path, entries=None) -> set[str]:
    pending = list(ENTRIES if entries is None else entries)
    sources: set[str] = set()
    while pending:
        module = pending.pop()
        filename = module + ".py"
        if filename in sources:
            continue
        path = safe_file(root, filename)
        sources.add(filename)
        for node in ast.walk(ast.parse(path.read_text(), filename=filename)):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                if (root / (name + ".py")).is_file():
                    pending.append(name)
    return sources


def manifest(root: Path, *, allow_dirty: bool = False) -> dict:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    dirty = bool(subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=root,
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout.strip())
    if dirty and not allow_dirty:
        raise ValueError("Release requires a clean reviewed commit; use --allow-dirty only for a candidate.")
    paths = runtime_sources(root) | set(RESOURCES)
    files = {name: sha256(safe_file(root, name)) for name in sorted(paths)}
    identity = {"schema_version": 1, "source_commit": revision, "files": files, "clean_commit": not dirty}
    release_id = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {**identity, "release_id": release_id,
            "qualification": "CANDIDATE" if dirty else "RELEASE_SOURCE"}


def verify(root: Path, document: dict) -> None:
    if document.get("schema_version") != 1 or not re.fullmatch(r"[0-9a-f]{40,64}", document.get("source_commit", "")):
        raise ValueError("Invalid release manifest schema or source commit")
    files = document.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("Release manifest has no files")
    if not isinstance(document.get("clean_commit"), bool):
        raise ValueError("Release manifest must declare its clean-commit status")
    identity = {key: document[key] for key in ("schema_version", "source_commit", "files", "clean_commit")}
    expected = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if expected != document.get("release_id"):
        raise ValueError("Release manifest identity mismatch")
    for name, expected_hash in files.items():
        if sha256(safe_file(root, name)) != expected_hash:
            raise ValueError(f"Release artifact changed: {name}")
    # Reject extra executable/config files rather than quietly copying them into the image.
    entries = list(root.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise ValueError("Symlinks are not permitted in the release directory")
    actual = {str(path.relative_to(root)) for path in entries if path.is_file()}
    if actual != set(files) | {"release-manifest.json"}:
        raise ValueError("Release directory contains unlisted or missing files")


def stage(root: Path, destination: Path, *, allow_dirty: bool = False) -> dict:
    if destination.exists():
        raise ValueError("Destination must not exist; retain old release contexts for review")
    document = manifest(root, allow_dirty=allow_dirty)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
        temporary = Path(directory) / "release"
        temporary.mkdir()
        for name in document["files"]:
            target = temporary / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(safe_file(root, name), target)
        (temporary / "release-manifest.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
        verify(temporary, document)
        temporary.rename(destination)
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("stage")
    build.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    build.add_argument("--destination", type=Path, required=True)
    build.add_argument("--allow-dirty", action="store_true")
    check = commands.add_parser("verify")
    check.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    try:
        if args.command == "stage":
            document = stage(args.root.resolve(), args.destination.resolve(), allow_dirty=args.allow_dirty)
        else:
            document = json.loads((args.root / "release-manifest.json").read_text())
            verify(args.root.resolve(), document)
        print(json.dumps({"status": "PASS", "release_id": document["release_id"],
                          "clean_commit": document["clean_commit"]}))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
