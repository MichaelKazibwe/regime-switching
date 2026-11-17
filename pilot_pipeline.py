"""Bounded Linux/Mac research pipeline with independently reported publication stages."""

from datetime import datetime, timezone
from pathlib import Path
import fcntl
import os

from pilot_collect import collect
from pilot_daily import tick as daily
from scheduled_weekly_portfolios import tick as weekly
from daily_alpha_training import tick as train
from dashboard_runtime import runtime
from strategy_receipts import atomic_json
from strategy_integrity import strict_json, file_hash, fingerprint


def bootstrap_snapshot(root):
    """Relocate a reviewed imported snapshot without creating observation evidence."""
    pointer = root / "var/dashboard-live/latest.json"
    if pointer.is_file():
        return
    from pilot_release import materialize_snapshot

    source = root / "var/pilot-input"
    document = materialize_snapshot(source, root / "var/pilot-pipeline/bootstrap")
    original = strict_json(source / "evidence/original-bundle.json")
    bundle = {
        **original,
        "capture": str(source / "market/capture.json"),
        "training_report": str(source / "training/training-report.json"),
        "benchmark_extension": str(source / "extension"),
        "portfolio_contracts": str(document.parent / "portfolio-contracts.json"),
        "portable_derivation": dict(
            original_bundle_sha256=file_hash(source / "evidence/original-bundle.json"),
            creates_new_observations=False,
        ),
    }
    if original.get("latest_macro_features"):
        raise ValueError(
            "Portable bootstrap requires an explicitly bundled latest-macro feature adapter"
        )
    target = root / "var/pilot-pipeline/portable-bundle.json"
    atomic_json(target, bundle)
    atomic_json(
        pointer,
        dict(
            document=str(document),
            bundle=str(target),
            document_sha256=file_hash(document),
            bundle_sha256=file_hash(target),
            market_session=strict_json(source / "snapshot-manifest.json")[
                "market_session"
            ],
            execution_enabled=False,
        ),
    )


def benchmark(root):
    from cycle_benchmark import run as evaluate

    pointer = strict_json(root / "var/dashboard-live/latest.json")
    key = fingerprint(
        dict(
            bundle=pointer["bundle_sha256"],
            source=file_hash(root / "cycle_benchmark.py"),
        )
    )
    target = root / "var/cycle-benchmark" / ("pipeline-" + key[:20])
    if (target / "benchmark.json").is_file():
        value = strict_json(target / "benchmark.json")
        if any(file_hash(p) != h for p, h in value["source_hashes"].items()):
            raise ValueError("Existing benchmark sources differ")
        atomic_json(
            target.parent / "latest.json",
            dict(
                benchmark=str(target / "benchmark.json"),
                sha256=file_hash(target / "benchmark.json"),
            ),
        )
        return dict(status="ALREADY_COMPLETED")
    value = evaluate(pointer["bundle"], target)
    return dict(status=value["status"], market_session=value["market_session"])


def run(root=Path.cwd()):
    root = Path(root).resolve()
    state = root / "var/pilot-pipeline"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / "pipeline.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return dict(status="ALREADY_RUNNING")
        result = dict(
            status="RUNNING",
            started_at=datetime.now(timezone.utc).isoformat(),
            stages={},
            execution_enabled=False,
        )
        try:
            for name, action in [
                ("collection", lambda: collect(root)),
                (
                    "bootstrap",
                    lambda: bootstrap_snapshot(root) or {"status": "AVAILABLE"},
                ),
                ("benchmark", lambda: benchmark(root)),
                ("alpha_training", lambda: train(root)),
                ("daily", lambda: daily(root / "var/pilot-daily", publish_vm=True)),
                (
                    "weekly",
                    lambda: weekly(root / "var/weekly-portfolios", publish_vm=True),
                ),
            ]:
                result["stage"] = name
                result["stages"][name] = action()
                if result["stages"][name].get("status") in {
                    "FAILED",
                    "RETRY_LIMIT_REACHED",
                    "RETRY_BUDGET_EXHAUSTED",
                }:
                    raise RuntimeError(
                        "Research stage failed or exhausted retries: " + name
                    )
            waiting = [
                name
                for name, value in result["stages"].items()
                if value.get("status", "").startswith(("WAITING", "ALREADY_RUNNING"))
            ]
            result["status"] = "WAITING" if waiting else "COMPLETED"
            result["waiting_stages"] = waiting
        except Exception as error:
            result.update(status="FAILED", error_type=type(error).__name__)
            raise
        finally:
            result["finished_at"] = datetime.now(timezone.utc).isoformat()
            atomic_json(state / "heartbeat.json", result)
            target = Path(
                os.environ.get("PILOT_TELEMETRY_ROOT", root / "var/pilot-telemetry")
            )
            atomic_json(target / "current.json", runtime(root / "var"))
        return result


if __name__ == "__main__":
    import json

    print(json.dumps(run(), indent=2))
