"""Capability readiness independent of HTTP liveness and production approval."""

from datetime import datetime, timezone
from pathlib import Path
import math

from strategy_integrity import strict_json, file_hash, fingerprint
from strategy_training_data import usable_session


def inspect_features(snapshot, *, weekly_root=None, benchmark=None, now=None):
    from pilot_release import verify_snapshot
    from weekly_portfolios import published, weekly_session

    now = now or datetime.now(timezone.utc)
    expected = str(usable_session(now).date())
    root = Path(snapshot) if snapshot else None
    checks = {}

    def check(name, action):
        try:
            if not action():
                raise ValueError("Capability missing, stale or unqualified")
            checks[name] = dict(ready=True, status="READY")
        except (OSError, ValueError, KeyError, TypeError) as error:
            checks[name] = dict(
                ready=False,
                status="UNAVAILABLE_OR_STALE",
                error_type=type(error).__name__,
            )

    check(
        "research_snapshot",
        lambda: bool(root and verify_snapshot(root)["market_session"] == expected),
    )

    def benchmark_ready():
        path = (
            root / "benchmark.json"
            if root and (root / "benchmark.json").is_file()
            else benchmark
        )
        if not path:
            return False
        data = strict_json(path)
        return (
            data["status"] == "RESEARCH_BENCHMARK"
            and data["market_session"] == expected
            and data["execution_enabled"] is False
            and all(file_hash(p) == h for p, h in data["source_hashes"].items())
        )

    def alpha_ready():
        if not root:
            return False
        data = strict_json(root / "macro-alpha.json")["forecast"]
        probabilities = data["prediction"]["probabilities"]
        return (
            fingerprint({k: v for k, v in data.items() if k != "forecast_id"})
            == data["forecast_id"]
            and all(file_hash(p) == h for p, h in data["source_hashes"].items())
            and data["market_session"] == expected
            and data["monitoring_enabled"] is True
            and data["execution_enabled"] is False
            and data["portfolio_activation_enabled"] is False
            and probabilities is not None
            and len(probabilities) == 4
            and all(
                isinstance(p, (int, float))
                and not isinstance(p, bool)
                and math.isfinite(p)
                and 0 <= p <= 1
                for p in probabilities
            )
            and abs(sum(probabilities) - 1) < 1e-9
        )

    check("cycle_benchmark", benchmark_ready)
    check("macro_alpha", alpha_ready)
    check(
        "weekly_portfolios",
        lambda: bool(
            weekly_root
            and published(weekly_root)[1]["market_session"] == weekly_session(now)
        ),
    )
    return dict(
        ready=all(c["ready"] for c in checks.values()),
        capabilities=checks,
        expected_market_session=expected,
        production_approval=False,
        execution_enabled=False,
    )
