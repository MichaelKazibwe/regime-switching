"""Minimal source context and a separate private, portable research snapshot."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile

from paper_release import runtime_sources, safe_file
from strategy_integrity import strict_json, file_hash, fingerprint
from strategy_receipts import atomic_json
from forward_cohort import database as cohort_database


def contained(root, name):
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Contained release artifact required")
    target = root / path
    if any(parent.is_symlink() for parent in [target, *target.parents] if parent != root.parent):
        raise ValueError("Symlink release artifacts are not accepted")
    return target


def verify_snapshot(root):
    root = Path(root).resolve()
    manifest = strict_json(root / "snapshot-manifest.json")
    if manifest.get("schema_version") != 1 or manifest.get("execution_enabled") is not False:
        raise ValueError("Private pilot snapshot manifest required")
    for name, digest in manifest["files"].items():
        if file_hash(contained(root, name)) != digest:
            raise ValueError("Pilot snapshot artifact mismatch")
    return manifest


def materialize_snapshot(root, state):
    """Relocate only the main PDF binding; preserve all numerical/artifact bytes."""
    root, state = Path(root).resolve(), Path(state).resolve()
    manifest = verify_snapshot(root)
    identity = fingerprint(manifest)
    views = state / "views"
    views.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = views / identity
    if destination.exists():
        receipt = strict_json(destination / "derivation.json")
        if (receipt["snapshot_manifest_sha256"] != file_hash(root / "snapshot-manifest.json")
                or receipt["derived_seal_sha256"] != file_hash(destination / "artifact-manifest.json")):
            raise ValueError("Derived pilot snapshot identity mismatch")
        return destination / "investor-dashboard.html"
    original = strict_json(root / "dashboard/artifact-manifest.json")
    main = original.get("main_investor_pdf")
    if main and file_hash(root / "dashboard/main-investor-report.pdf") != main["sha256"]:
        raise ValueError("Main PDF relocation content mismatch")
    temporary = Path(tempfile.mkdtemp(prefix="view-", dir=views))
    temporary.chmod(0o700)
    for path in (root / "dashboard").iterdir():
        if path.is_file():
            private_copy(path, temporary / path.name)
    if main:
        original["main_investor_pdf"]["path"] = str(destination / "main-investor-report.pdf")
    atomic_json(temporary / "artifact-manifest.json", original)
    atomic_json(temporary / "derivation.json", dict(
        snapshot_manifest_sha256=file_hash(root / "snapshot-manifest.json"),
        original_seal_sha256=file_hash(root / "dashboard/artifact-manifest.json"),
        derived_seal_sha256=file_hash(temporary / "artifact-manifest.json"),
        transformation="Main investor PDF path only; content, allocation, context and release IDs unchanged",
        release_approved=False))
    os.rename(temporary, destination)
    return destination / "investor-dashboard.html"


def verify_context(root):
    root = Path(root).resolve()
    manifest = strict_json(root / "pilot-release.json")
    identity = {k: manifest[k] for k in ["schema_version", "source_commit", "clean_commit", "files"]}
    if (manifest.get("release_id") != fingerprint(identity)
            or manifest.get("broker_submission_enabled") is not False):
        raise ValueError("Pilot source manifest mismatch")
    for name, digest in manifest["files"].items():
        if file_hash(contained(root, name)) != digest:
            raise ValueError("Pilot source artifact mismatch")
    return manifest


def private_copy(source, destination):
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or not source.is_file():
        raise ValueError("Regular private source artifact required")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copyfile(source, destination)
    destination.chmod(0o600)


def snapshot(source_root, destination, pointer, benchmark=None):
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    published = strict_json(pointer)
    if (file_hash(published["document"]) != published["document_sha256"]
            or file_hash(published["bundle"]) != published["bundle_sha256"]):
        raise ValueError("Published input identity mismatch")
    b = strict_json(published["bundle"])
    report = strict_json(b["training_report"])
    capture = strict_json(b["capture"])
    document = Path(published["document"])
    seal = strict_json(document.parent / "artifact-manifest.json")
    for name in [document.name, "artifact-manifest.json", *seal["pdfs"], "portfolio-contracts.json"]:
        private_copy(document.parent / name, destination / "dashboard" / name)
    if seal.get("main_investor_pdf"):
        private_copy(seal["main_investor_pdf"]["path"], destination / "dashboard/main-investor-report.pdf")
    # The live viewer expects its conventional filename even if the source differs.
    if document.name != "investor-dashboard.html":
        raise ValueError("Standard sealed investor document required")
    private_copy(b["capture"], destination / "market/capture.json")
    for name, digest in capture["files"].items():
        source = contained(Path(b["capture"]).parent, name)
        if file_hash(source) != digest:
            raise ValueError("Market capture changed")
        private_copy(source, destination / "market" / name)
    private_copy(b["training_report"], destination / "training/training-report.json")
    for name, digest in report["artifacts"].items():
        source = contained(Path(b["training_report"]).parent, name)
        if file_hash(source) != digest:
            raise ValueError("Training artifact changed")
        private_copy(source, destination / "training" / name)
    private_copy(published["bundle"], destination / "evidence/original-bundle.json")
    for name in ["capture.json", "XLV-adjusted.csv", "news.json"]:
        private_copy(Path(b["benchmark_extension"]) / name, destination / "extension" / name)
    atomic_json(destination / "launch.json", dict(document="dashboard/investor-dashboard.html",
                capture="market/capture.json", training_report="training/training-report.json"))
    if benchmark:
        private_copy(benchmark, destination / "benchmark.json")
    from dashboard_runtime import runtime
    atomic_json(destination / "monitoring-runtime.json", runtime(source_root / "var"))
    files = {str(p.relative_to(destination)): file_hash(p) for p in destination.rglob("*") if p.is_file()}
    manifest = dict(schema_version=1, market_session=report["market_session"],
                    source_bundle_sha256=file_hash(published["bundle"]), files=files,
                    execution_enabled=False, private_shared_research_dataset=True)
    atomic_json(destination / "snapshot-manifest.json", manifest)
    verify_snapshot(destination)
    return manifest


def seed_runtime(source_root, runtime, input_root):
    capture = strict_json(input_root / "market/capture.json")
    macro = strict_json(input_root / "market" / Path(capture["macro_manifest"]).name)
    seed = runtime / "research/smart-macro-vintages"
    seed.mkdir(parents=True, exist_ok=True, mode=0o700)
    for key, record in macro["series"].items():
        src = input_root / "market" / Path(record["path"]).name
        if not src.is_file():
            src = input_root / "market" / f"{key}.csv"
        if file_hash(src) != record["sha256"]:
            raise ValueError("Point-in-time macro seed checksum mismatch")
        private_copy(src, seed / f"{key}.csv")
        record["path"] = f"var/research/smart-macro-vintages/{key}.csv"
    atomic_json(seed / "manifest.json", macro)
    imports = {}
    for name in ["strategy-operations-integrated-v1", "return-engine-shadow-v1", "dynamic-forward-v1"]:
        old = source_root / "var" / name
        selected = cohort_database(old)
        if not selected.is_file():
            continue
        new = runtime / name
        new.mkdir(parents=True, exist_ok=True, mode=0o700)
        with sqlite3.connect(selected) as src, sqlite3.connect(new / selected.name) as dst:
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Cohort backup failed integrity check")
        (new / selected.name).chmod(0o600)
        if (old / "active-cohort.json").is_file():
            private_copy(old / "active-cohort.json", new / "active-cohort.json")
        from strategy_monthly_report import read_events
        events = read_events(new / selected.name)
        if events:
            imports[name] = dict(session=events[-1][0]["session"], chain_head=events[-1][1],
                                 database_sha256=file_hash(new / selected.name))
    atomic_json(input_root / "cohort-import.json", dict(schema_version=1, cohorts=imports,
                intent="Preserve previously sealed sessions; never count imports as new observations"))
    manifest = strict_json(input_root / "snapshot-manifest.json")
    manifest["files"]["cohort-import.json"] = file_hash(input_root / "cohort-import.json")
    atomic_json(input_root / "snapshot-manifest.json", manifest)
    (runtime / "pilot").mkdir(parents=True, exist_ok=True, mode=0o700)
    return capture["price_session"]


def stage(root, destination, *, allow_dirty=False, pointer=None, benchmark=None, source_only=False):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError("Use a new release destination")
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                              capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root,
                               check=True, capture_output=True, text=True).stdout.strip())
    if dirty and not allow_dirty:
        raise ValueError("Clean reviewed source required; --allow-dirty stages a candidate only")
    pointer = Path(pointer or root / "var/dashboard-live/latest.json")
    report, seal = {}, {}
    if not source_only:
        p = strict_json(pointer)
        b = strict_json(p["bundle"])
        report = strict_json(b["training_report"])
        seal = strict_json(Path(p["document"]).parent / "artifact-manifest.json")
    paths = runtime_sources(root, entries=("pilot_server", "pilot_admin", "pilot_release", "pilot_verify", "pilot_preflight",
                    "local_observation_scheduler", "pilot_collect", "observation_watchdog", "investment_product",
                    "recommendation_api", "managed_api", "cycle_benchmark", "execute_performance_improvements",
                    "shadow_bundle_backup", "integrated_strategy_comparison", "strategy_monthly_report", "weekly_portfolios"))
    paths |= set(report.get("source_hashes", {})) | set(seal.get("source_hashes", {}))
    paths |= {str(x.relative_to(root)) for folder in ["dashboard", "pilot", "research"]
              for x in (root / folder).glob("*") if x.is_file() and x.suffix in {".json", ".html", ".css", ".js"}}
    paths |= {"requirements-paper.hashed.lock", "Dockerfile.pilot", ".dockerignore"}
    image = destination / "image"
    image.mkdir(parents=True, mode=0o700)
    for name in sorted(paths):
        source = safe_file(root, name)
        target = image / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o644)
    identity = dict(schema_version=1, source_commit=revision, clean_commit=not dirty,
                    files={name: file_hash(image / name) for name in sorted(paths)})
    manifest = dict(**identity, release_id=fingerprint(identity),
                    qualification="CANDIDATE" if dirty else "REVIEWED_SOURCE",
                    broker_submission_enabled=False)
    (image / "pilot-release.json").write_text(json.dumps(manifest, indent=2))
    verify_context(image)
    runtime = destination / "runtime"
    if not source_only:
        snapshot(root, runtime / "pilot-input", pointer, benchmark)
        seed_runtime(root, runtime, runtime / "pilot-input")
    for name in ["compose.pilot.yaml", "deploy/pilot/Caddyfile", "deploy/pilot/pilot.env.example",
                 "deploy/pilot/market.env.example", "deploy/pilot/regime-pilot-validation.service",
                 "deploy/pilot/regime-pilot-validation.timer"]:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    atomic_json(destination / "release.json", dict(source_release_id=manifest["release_id"],
                qualification=manifest["qualification"], market_session=report.get("market_session"),
                secrets_included=False, production_qualification=False))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    result = stage(args.root, args.destination, allow_dirty=args.allow_dirty,
                   benchmark=args.benchmark, source_only=args.source_only)
    print(json.dumps({k: result[k] for k in ["release_id", "qualification"]}))
