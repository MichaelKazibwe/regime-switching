"""Integrity-checked presentation of private shadow strategy training evidence."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from fourregimestrategies import FourMacroStrategies
from strategy_training_data import usable_session


def load_training_report(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Training report must be a regular file")
    report = json.loads(
        path.read_text(),
        parse_constant=lambda _: (_ for _ in ()).throw(
            ValueError("Nonfinite training JSON")
        ),
    )
    if (
        report.get("schema_version") != 1
        or report.get("status") != "COMPLETED_SHADOW_EVALUATION"
    ):
        raise ValueError("Completed shadow evaluation required")
    if (
        report.get("execution_enabled") is not False
        or report.get("public_recommendations_enabled") is not False
        or report.get("promotion") != "NONE"
    ):
        raise ValueError("Training cannot grant release or execution authority")
    stamp = pd.Timestamp(report["generated_at"])
    now = pd.Timestamp(datetime.now(timezone.utc))
    if stamp.tzinfo is None or stamp > now + pd.Timedelta(minutes=5):
        raise ValueError("Invalid training timestamp")
    if pd.Timestamp(report["market_session"]) > usable_session(now.to_pydatetime()):
        raise ValueError("Training uses an uncompleted market session")
    root = path.parent.resolve()
    for name, digest in report["artifacts"].items():
        candidate = root / name
        if (
            Path(name).name != name
            or candidate.is_symlink()
            or not candidate.is_file()
            or hashlib.sha256(candidate.read_bytes()).hexdigest() != digest
        ):
            raise ValueError("Training artifact integrity failure")
    if set(r["name"] for r in report["strategies"]) != set(
        FourMacroStrategies().config["strategies"]
    ):
        raise ValueError("Exactly four known strategies required")
    symbols = report["core_universe"]
    if (not symbols or len(symbols) != len(set(symbols))
            or not set(symbols) <= set(__import__("global_asset_registry").load_registry().instruments)):
        raise ValueError("Training requires an explicit registered universe")
    for row in [*report["strategies"], *report["benchmarks"]]:
        h = row["history"]
        if len(h) != report["evaluation"]["sessions"] or [p[0] for p in h] != sorted(
            set(p[0] for p in h)
        ):
            raise ValueError("Evaluation dates do not reconcile")
        if (
            h[0][0] != report["evaluation"]["start"]
            or h[-1][0] != report["evaluation"]["end"]
        ):
            raise ValueError("Evaluation endpoints mismatch")
        if not np.isfinite(np.array([p[1:] for p in h], dtype=float)).all() or any(
            p[1] <= 0 or not -1 < p[2] <= 1e-8 for p in h
        ):
            raise ValueError("Invalid training wealth/drawdown data")
        candidate = row.get("candidate", {})
        weights = candidate.get("weights")
        if weights is not None and (
            set(weights) != set(symbols)
            or min([*weights.values(), candidate["cash"]]) < -1e-8
            or max(weights.values()) > 0.250001
            or not np.isclose(sum(weights.values()) + candidate["cash"], 1, atol=1e-6)
        ):
            raise ValueError("Candidate capital constraints failed")
    from strategy_integrity import reconcile_history

    reconcile_history(report, root)
    report["artifact_integrity_verified"] = True
    report["current_numerical_source_match"] = all(
        Path(p).is_file() and hashlib.sha256(Path(p).read_bytes()).hexdigest() == h
        for p, h in report["source_hashes"].items()
    )
    report["view_only"] = True
    return report
