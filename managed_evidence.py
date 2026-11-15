"""Source/image/account-bound review receipts; readiness is not order authority."""

from datetime import datetime, timezone, timedelta
import hashlib
import hmac
from pathlib import Path

from strategy_integrity import file_hash, fingerprint, canonical
from paper_release import safe_file

SOURCES = (
    "live_p1_service.py",
    "live_p1_runner.py",
    "operational_metrics.py",
    "operational_escalation.py",
    "operational_recovery.py",
    "operational_model_review.py",
    "strategy_degradation.py",
    "execution_degradation.py",
    "risk_forecast_registry.py",
    "executionanalytics.py",
    "emailtransport.py",
    "shadow_bundle_backup.py",
    "writer_fencing.py",
    "managed_disaster_recovery.py",
    "managed_portfolio_risk.py",
    "portfolio_risk_envelope.py",
    "economic_evidence.py",
    "managed_probe.py",
    "authorizedorderintent.py",
    "productionexecutiongate.py",
    "order.py",
    "managed_release.py",
    "Dockerfile.managed-paper",
    "managed_positions.py",
    "managed_adapters.py",
    "managed_accounts.py",
    "managed_boundary.py",
    "managed_execution.py",
    "managed_transport.py",
    "managed_operations.py",
    "managed_api.py",
    "managed_evidence.py",
    "ibkr_paper_orders.py",
    "ibkr_paper_probe.py",
    "global_market_calendar.py",
)
REVIEWS = {
    "model",
    "operations",
    "security",
    "broker_paper",
    "account_access",
    "host_image",
    "observation",
}


def source_identity():
    return fingerprint({p: file_hash(p) for p in SOURCES})


def readiness(
    receipts, keys, scope, image_digest, root, *, client_account=False, now=None
):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Aware review clock required")
    required = REVIEWS | (
        {"licence_scope", "client_mandate", "identity_isolation", "client_country"}
        if client_account
        else set()
    )
    passed = set()
    invalid = []
    current = source_identity()
    for receipt in receipts:
        body = {k: v for k, v in receipt.items() if k != "signature"}
        try:
            key = keys[body["reviewer"]]
            if len(key) < 32:
                raise ValueError("Weak review key")
            sig = hmac.new(key, canonical(body).encode(), hashlib.sha256).hexdigest()
            if not isinstance(receipt.get("signature"), str) or not hmac.compare_digest(
                sig, receipt["signature"]
            ):
                raise ValueError("Review signature mismatch")
            start, end = (
                datetime.fromisoformat(body[k]) for k in ("reviewed_at", "expires_at")
            )
            if (
                start.tzinfo is None
                or end.tzinfo is None
                or not start <= now < end
                or end - start > timedelta(days=31)
            ):
                raise ValueError("Review window invalid")
            if (
                body["source_id"],
                body["image_digest"],
                body["tenant"],
                body["account"],
                body["mode"],
            ) != (current, image_digest, scope.tenant, scope.account, "PAPER"):
                raise ValueError("Review binding mismatch")
            if not image_digest.startswith("sha256:") or len(image_digest) != 71:
                raise ValueError("Immutable image digest required")
            if not body.get("artifacts"):
                raise ValueError("Review artifacts required")
            if any(
                file_hash(safe_file(Path(root), a["path"])) != a["sha256"]
                for a in body["artifacts"]
            ):
                raise ValueError("Review artifact changed")
            if body["status"] != "PASS" or body["check"] not in required:
                raise ValueError("Review not accepted")
            if body["check"] in passed:
                raise ValueError("Ambiguous duplicate review")
            passed.add(body["check"])
        except (KeyError, TypeError, ValueError, OSError) as exc:
            invalid.append(str(exc))
    return dict(
        status="READY_FOR_INDEPENDENT_PAPER_REVIEW"
        if passed == required and not invalid
        else "BLOCKED",
        source_id=current,
        passed=sorted(passed),
        missing=sorted(required - passed),
        invalid=invalid,
        execution_enabled=False,
        release_approved=False,
    )
