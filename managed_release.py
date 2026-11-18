"""Stage/verify a managed PAPER source candidate, never an executing service."""

import argparse
import ast
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from paper_release import safe_file, verify, sha256, RUNTIME_RESOURCES
from strategy_integrity import fingerprint

ROOTS = (
    "managed_api",
    "managed_evidence",
    "managed_transport",
    "ibkr_paper_orders",
    "managed_positions",
    "managed_release",
)


def sources(root, initial=ROOTS):
    pending = list(initial)
    result = set()
    while pending:
        name = pending.pop() + ".py"
        if name in result:
            continue
        path = safe_file(root, name)
        result.add(name)
        for node in ast.walk(ast.parse(path.read_text())):
            imported = (
                [a.name.split(".")[0] for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module.split(".")[0]]
                if isinstance(node, ast.ImportFrom) and node.module
                else []
            )
            pending.extend(n for n in imported if (root / (n + ".py")).is_file())
    return result


def stage(root, destination, *, allow_dirty=False):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError("New release destination required")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    if dirty and not allow_dirty:
        raise ValueError(
            "Clean reviewed commit required; --allow-dirty is candidate-only"
        )
    from managed_evidence import SOURCES

    paths = (
        sources(root, (*ROOTS, *(p[:-3] for p in SOURCES if p.endswith('.py'))))
        | set(SOURCES) | set(RUNTIME_RESOURCES)
        | {
            "Dockerfile.managed-paper",
            "MANAGED_PAPER_RUNBOOK.md",
            "requirements-paper.hashed.lock",
            "deploy/live-p1-monitor.example.json",
        }
    )
    paths |= {
        str(p.relative_to(root))
        for p in (root / "research").glob("*.json")
        if p.is_file()
    }
    identity = dict(
        schema_version=1,
        source_commit=commit,
        files={p: sha256(safe_file(root, p)) for p in sorted(paths)},
        clean_commit=not dirty,
    )
    manifest = {
        **identity,
        "release_id": fingerprint(identity),
        "qualification": "CANDIDATE" if dirty else "RELEASE_SOURCE",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
        target = Path(temp) / "release"
        target.mkdir()
        for relative in manifest["files"]:
            output = target / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(safe_file(root, relative), output)
        (target / "release-manifest.json").write_text(
            json.dumps(manifest, sort_keys=True)
        )
        verify(target, manifest)
        target.rename(destination)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["stage", "inspect"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--destination")
    parser.add_argument("--allow-dirty", action="store_true")
    a = parser.parse_args()
    if a.action == "stage":
        if not a.destination:
            parser.error("--destination required")
        doc = stage(a.root, a.destination, allow_dirty=a.allow_dirty)
    else:
        root = Path(a.root)
        doc = json.loads((root / "release-manifest.json").read_text())
        verify(root, doc)
    print(
        json.dumps(
            dict(
                status="SOURCE_VERIFIED_NOT_DEPLOYMENT_QUALIFIED",
                release_id=doc["release_id"],
                clean_commit=doc["clean_commit"],
                execution_enabled=False,
                release_approved=False,
            )
        )
    )
