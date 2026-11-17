"""Immutable client review decisions; approval never creates an execution capability."""

from datetime import datetime, timezone
from pathlib import Path
import fcntl

from strategy_integrity import strict_json, fingerprint
from strategy_receipts import atomic_json


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
