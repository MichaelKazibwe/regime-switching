"""Stage only recommendation runtime sources, assets and locked dependencies."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from paper_release import runtime_sources, safe_file, sha256, verify
from productrelease import PRODUCT_SOURCES


def stage(root, destination, *, allow_dirty=False):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError("Use a new release context; existing artifacts are preserved")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    if dirty and not allow_dirty:
        raise ValueError(
            "Clean reviewed commit required; --allow-dirty creates a candidate only"
        )
    paths = (
        runtime_sources(
            root,
            entries=(
                "investment_product",
                "recommendation_api",
                "productrelease",
                "product_build",
                "product_smoke",
            ),
        )
        | set(PRODUCT_SOURCES)
        | {".dockerignore"}
    )
    files = {name: sha256(safe_file(root, name)) for name in sorted(paths)}
    identity = dict(
        schema_version=1, source_commit=revision, files=files, clean_commit=not dirty
    )
    manifest = {
        **identity,
        "release_id": hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "qualification": "CANDIDATE" if dirty else "RELEASE_SOURCE",
        "broker_submission_enabled": False,
    }
    destination.mkdir(parents=True, mode=0o700)
    for name in files:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(safe_file(root, name), target)
    (destination / "release-manifest.json").write_text(json.dumps(manifest, indent=2))
    verify(destination, manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()
    result = stage(args.root, args.destination, allow_dirty=args.allow_dirty)
    print(
        json.dumps(
            dict(
                release_id=result["release_id"],
                qualification=result["qualification"],
                files=len(result["files"]),
            )
        )
    )
