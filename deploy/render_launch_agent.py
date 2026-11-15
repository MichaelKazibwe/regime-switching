"""Render a portable LaunchAgent template; does not install or enable a service."""

import argparse
from pathlib import Path
import plistlib
import sys


def render(source, root):
    def expand(value):
        if isinstance(value, str):
            return value.replace("__PROJECT_ROOT__", str(Path(root).resolve())).replace("__PYTHON__", sys.executable)
        if isinstance(value, list):
            return [expand(item) for item in value]
        if isinstance(value, dict):
            return {key: expand(item) for key, item in value.items()}
        return value
    return plistlib.dumps(expand(plistlib.loads(Path(source).read_bytes())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(render(args.template, Path(__file__).resolve().parent.parent))
    args.output.chmod(0o600)
