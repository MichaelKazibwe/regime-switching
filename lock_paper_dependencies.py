"""Add PyPI artifact hashes to exact pins without installing packages.

Run under Python 3.12 on the release platform. CI still verifies resolution
and installation; hashes alone do not prove compatibility or safety.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.request import urlopen


def hash_lock(source: Path, *, fetch=None) -> str:
    fetch = fetch or fetch_metadata
    lines = ["# PyPI artifact hashes for exact pins; regenerate with lock_paper_dependencies.py."]
    for raw in source.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "-r requirements-paper.lock":
            lines.append("-r requirements-paper.hashed.lock")
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)", line)
        if not match:
            raise ValueError(f"Only exact pins are supported: {line}")
        name, version = match.groups()
        metadata = fetch(name, version)
        if str(metadata["info"]["version"]) != version:
            raise ValueError(f"Version mismatch for {name}")
        hashes = sorted({
            item["digests"]["sha256"] for item in metadata["urls"]
            if not item.get("yanked", False)
        })
        if not hashes or any(not re.fullmatch(r"[0-9a-f]{64}", item) for item in hashes):
            raise ValueError(f"No valid unyanked artifacts for {name}=={version}")
        lines.append(line + " \\")
        lines.extend("    --hash=sha256:" + digest + (" \\" if index < len(hashes) - 1 else "")
                     for index, digest in enumerate(hashes))
    return "\n".join(lines) + "\n"


def fetch_metadata(name: str, version: str) -> dict:
    with urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--allow-other-python", action="store_true",
                        help="Create candidate hashes only; Python 3.12 CI remains required")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12) and not args.allow_other_python:
        parser.error("Use Python 3.12 for release locks (or explicitly create candidate hashes).")
    # Fetch everything before publishing either lock, so failures leave old files intact.
    outputs = {}
    for name in ("paper", "dev"):
        source = args.root / f"requirements-{name}.lock"
        outputs[args.root / f"requirements-{name}.hashed.lock"] = hash_lock(source)
    for path, content in outputs.items():
        temporary = path.with_suffix(".tmp")
        temporary.write_text(content)
        temporary.replace(path)
        print(json.dumps({"file": path.name, "sha256": hashlib.sha256(content.encode()).hexdigest()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
