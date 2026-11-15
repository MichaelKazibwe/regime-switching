"""Named local review requests bound to diagnostics; never execution approval."""

from datetime import datetime, timezone
from pathlib import Path
import getpass
import uuid
import json
import hashlib
from strategy_receipts import atomic_json


def record(root, decision, reason, *, strategy=None, candidate_version=None):
    root = Path(root)
    if (
        decision not in {"HOLD", "REQUEST_FREEZE", "REQUEST_REFIT", "REJECT_CANDIDATE"}
        or not reason
        or not reason.strip()
    ):
        raise ValueError("Explicit review request and reason required")
    if decision == "REQUEST_REFIT" and not candidate_version:
        raise ValueError("Refit requires a separately versioned candidate")
    if decision == "REQUEST_FREEZE" and not strategy:
        raise ValueError("Freeze review requires an explicit strategy scope")
    current = root / "latest.json"
    body = current.read_bytes()
    report = json.loads(body)
    value = dict(
        decision=decision,
        reason=reason,
        actor=getpass.getuser(),
        recorded_at=datetime.now(timezone.utc).isoformat(),
        report_sha256=hashlib.sha256(body).hexdigest(),
        cohort_heads={
            k: v["chain_head"] for k, v in report.get("degradation", {}).items()
        },
        strategy=strategy,
        candidate_version=candidate_version,
        execution_enabled=False,
        release_approved=False,
        applied_to_trading=False,
    )
    target = root / "model-reviews" / (uuid.uuid4().hex + ".json")
    atomic_json(target, value, exclusive=True)
    return value
