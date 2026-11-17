"""Portable, verified atomic publication; filesystem transport for Linux workers."""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile

from strategy_integrity import strict_json, fingerprint, file_hash
from strategy_receipts import atomic_json


def docker_command():
    executable = os.environ.get("PILOT_DOCKER_BINARY") or shutil.which("docker")
    if not executable and Path("/opt/homebrew/bin/docker").is_file():
        executable = "/opt/homebrew/bin/docker"
    if not executable:
        raise RuntimeError(
            "Docker unavailable; configure filesystem publication roots on Linux"
        )
    context = os.environ.get("PILOT_DOCKER_CONTEXT")
    if context is None and __import__("sys").platform == "darwin":
        context = "colima-regime-pilot"
    return [executable] + (["--context", context] if context else [])


def installed_image():
    if os.environ.get("PILOT_PUBLICATION_IMAGE"):
        return os.environ["PILOT_PUBLICATION_IMAGE"]
    return subprocess.run(
        docker_command()
        + [
            "inspect",
            os.environ.get("PILOT_CONTAINER", "regime-pilot-local-pilot-1"),
            "--format",
            "{{.Image}}",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


def historical_weekly_session(directory):
    """Read a sealed prior date without requalifying its old model sources."""
    directory = Path(directory)
    manifest = strict_json(directory / "manifest.json")
    if set(manifest["files"]) != {"recommendations.json", "dashboard-report.pdf"}:
        raise ValueError("Complete prior weekly artifact set required")
    if any(
        file_hash(directory / name) != digest
        for name, digest in manifest["files"].items()
    ):
        raise ValueError("Prior weekly artifact checksum mismatch")
    data = strict_json(directory / "recommendations.json")
    if (
        fingerprint({k: v for k, v in data.items() if k != "research_id"})
        != data["research_id"]
        or data.get("execution_enabled") is not False
        or data.get("promotion_enabled") is not False
    ):
        raise ValueError("Prior weekly research identity mismatch")
    return data["market_session"]


def prior_weekly_session(root):
    root = Path(root)
    revision = strict_json(root / "latest.json")["research_id"]
    if (
        not isinstance(revision, str)
        or len(revision) != 64
        or any(c not in "0123456789abcdef" for c in revision)
    ):
        raise ValueError("Invalid prior weekly revision")
    if (root / revision).is_symlink():
        raise ValueError("Prior weekly root symlinks forbidden")
    return historical_weekly_session(root / revision)


def filesystem_publish(directory, destination, *, kind):
    """Validation precedes pointer change; prior good revisions remain immutable."""
    from pilot_release import verify_snapshot
    from weekly_portfolios import verify
    from pilot_daily import candidate

    if kind not in {"daily", "weekly"}:
        raise ValueError("Explicit daily or weekly publication kind required")
    directory, destination = Path(directory), Path(destination)
    if directory.is_symlink() or destination.is_symlink():
        raise ValueError("Publication root symlinks forbidden")
    directory, destination = directory.resolve(), destination.resolve()
    if (
        directory == destination
        or directory.is_relative_to(destination)
        or destination.is_relative_to(directory)
    ):
        raise ValueError("Publication source must be outside the destination tree")
    if any(p.is_symlink() for p in directory.rglob("*")):
        raise ValueError("Publication symlinks forbidden")
    data = verify_snapshot(directory) if kind == "daily" else verify(directory)
    revision = fingerprint(data) if kind == "daily" else data["research_id"]
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix=".staging-", dir=destination) as tmp:
        staged = Path(tmp) / revision
        shutil.copytree(directory, staged)
        target = destination / revision
        if kind == "daily":
            if fingerprint(verify_snapshot(staged)) != revision:
                raise ValueError("Staged daily identity mismatch")
            candidate(staged, Path(tmp) / "verification")
            pointer = destination / "latest.json"
            if pointer.is_file():
                prior = destination / strict_json(pointer)["revision"]
                if verify_snapshot(prior)["market_session"] > data["market_session"]:
                    raise ValueError("Daily session rollback forbidden")
        else:
            verify(staged)
            pointer = destination / "latest.json"
            if pointer.is_file():
                if prior_weekly_session(destination) > data["market_session"]:
                    raise ValueError("Weekly session rollback forbidden")
        if target.exists():
            existing = verify_snapshot(target) if kind == "daily" else verify(target)
            if fingerprint(existing) != fingerprint(data):
                raise ValueError("Existing publication differs")
        else:
            os.rename(staged, target)
        atomic_json(
            destination / "latest.json",
            {"revision" if kind == "daily" else "research_id": revision},
        )
    return revision


def publish_runtime(data):
    """Refresh allowlisted liveness separately from immutable research revisions."""
    import json

    if os.environ.get("PILOT_TELEMETRY_ROOT"):
        atomic_json(Path(os.environ["PILOT_TELEMETRY_ROOT"]) / "current.json", data)
        return
    if os.environ.get("PILOT_DAILY_PUBLISH_ROOT"):
        atomic_json(
            Path(os.environ["PILOT_DAILY_PUBLISH_ROOT"]) / "telemetry.json", data
        )
        return
    script = "from pathlib import Path; import json,sys; from strategy_receipts import atomic_json; atomic_json(Path('/daily/telemetry.json'),json.load(sys.stdin))"
    subprocess.run(
        docker_command()
        + [
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--mount",
            "type=volume,src=regime-pilot-local-daily,dst=/daily",
            "--entrypoint",
            "python",
            installed_image(),
            "-c",
            script,
        ],
        input=json.dumps(data),
        text=True,
        check=True,
        timeout=90,
    )
