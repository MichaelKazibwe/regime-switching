"""Immutable client review decisions; approval never creates an execution capability."""

from datetime import datetime, timezone
from pathlib import Path
import fcntl

from strategy_integrity import strict_json, fingerprint
from strategy_receipts import atomic_json


def history(root, *, reviewer, limit=100, now=None):
    """Read only the authenticated reviewer's sealed research feedback."""
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("Bounded review history required")
    root = Path(root)
    if root.is_symlink():
        raise ValueError("Review directory symlinks forbidden")
    if not root.exists():
        return []
    now = now or datetime.now(timezone.utc)
    rows = []
    for path in sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:256]:
        if path.is_symlink():
            raise ValueError("Review symlinks forbidden")
        row = strict_json(path)
        identity = fingerprint(dict(
            recommendation=row["recommendation_revision"], reviewer=row["reviewer"],
            decision=row["decision"], rationale=row["rationale"],
        ))
        stamp = datetime.fromisoformat(row["recorded_at"])
        if (row["reviewer"] != reviewer or identity != row["review_id"] or path.stem != identity
                or row["execution_enabled"] is not False
                or row["public_recommendation_approval"] is not False
                or row["decision"] not in {"ACCEPTED_FOR_RESEARCH", "REJECTED", "CHANGES_REQUESTED"}
                or stamp.tzinfo is None or stamp > now):
            raise ValueError("Research review history integrity mismatch")
        rows.append(row)
    return sorted(rows, key=lambda r: r["recorded_at"], reverse=True)[:limit]


def record_decision(
    root, recommendation, *, reviewer, decision, rationale, expected_revision
):
    if decision not in {"ACCEPTED_FOR_RESEARCH", "REJECTED", "CHANGES_REQUESTED"}:
        raise ValueError("Explicit research review decision required")
    if (
        not isinstance(reviewer, str)
        or not reviewer.strip()
        or not isinstance(rationale, str)
        or not 10 <= len(rationale.strip()) <= 2000
    ):
        raise ValueError("Identified reviewer and meaningful rationale required")
    required = {"recommendation_id", "mandate", "as_of", "release", "allocation"}
    if (
        not required <= set(recommendation)
        or fingerprint(recommendation) != expected_revision
    ):
        raise ValueError("Review must bind the exact immutable recommendation revision")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    identity = fingerprint(
        dict(
            recommendation=expected_revision,
            reviewer=reviewer,
            decision=decision,
            rationale=rationale,
        )
    )
    with (root / "review.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        path = root / (identity + ".json")
        if path.exists():
            existing = strict_json(path)
            expected = dict(
                review_id=identity,
                recommendation_id=recommendation["recommendation_id"],
                recommendation_revision=expected_revision,
                mandate_sha256=fingerprint(recommendation["mandate"]),
                release_id=recommendation["release"]["release_id"],
                reviewer=reviewer,
                decision=decision,
                rationale=rationale,
                execution_enabled=False,
                public_recommendation_approval=False,
            )
            if set(existing) != set(expected) | {"recorded_at"} or any(
                type(existing[k]) is not type(v) or existing[k] != v
                for k, v in expected.items()
            ):
                raise ValueError("Stored research review integrity mismatch")
            recorded = datetime.fromisoformat(existing["recorded_at"])
            if recorded.tzinfo is None or recorded > datetime.now(timezone.utc):
                raise ValueError("Invalid stored research review clock")
            return existing
        result = dict(
            review_id=identity,
            recommendation_id=recommendation["recommendation_id"],
            recommendation_revision=expected_revision,
            mandate_sha256=fingerprint(recommendation["mandate"]),
            release_id=recommendation["release"]["release_id"],
            reviewer=reviewer,
            decision=decision,
            rationale=rationale,
            recorded_at=datetime.now(timezone.utc).isoformat(),
            execution_enabled=False,
            public_recommendation_approval=False,
        )
        atomic_json(path, result, exclusive=True)
        return result
