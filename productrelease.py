"""Release-bound human attestations for public recommendations, not live trading."""

from datetime import timedelta
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from clientmandate import aware_time
from paper_release import safe_file, sha256


PRODUCT_CHECKS = (
    "legal_scope",
    "client_suitability",
    "instrument_access",
    "data_license_quality",
    "independent_model_validation",
    "security_privacy",
    "operations_recovery",
    "owner_signoff",
)
PRODUCT_SOURCES = (
    "assetuniverse.py",
    "investmentcatalog.py",
    "clientmandate.py",
    "productallocation.py",
    "recommendationrisk.py",
    "productexecutioncost.py",
    "productsimulation.py",
    "productrelease.py",
    "recommendationservice.py",
    "investment_product.py",
    "productreport.py",
    "investor_dashboard.py",
    "investor_analytics.py",
    "investor_macro_feed.py",
    "macro_feature_contract.py",
    "investor_pdf.py",
    "macro_lab_pdf.py",
    "assetroles.py",
    "dashboard/investor.html",
    "dashboard/investor.css",
    "dashboard/investor.js",
    "paper_release.py",
    "tradingcalendar.py",
    "requirements-paper.hashed.lock",
    "productaudit.py",
    "researchdatastore.py",
    "recommendation_api.py",
    "productstate.py",
    "product_build.py",
    "product_smoke.py",
    "Dockerfile.recommendations",
)


def release_manifest():
    from importlib.metadata import version
    import sys

    hashes = {name: sha256(Path(name)) for name in PRODUCT_SOURCES}
    environment = {
        "python": sys.version.split()[0],
        **{p: version(p) for p in ("numpy", "pandas", "scipy", "scikit-learn")},
    }
    digest = hashlib.sha256(
        json.dumps(
            {"sources": hashes, "environment": environment}, sort_keys=True
        ).encode()
    ).hexdigest()
    return {
        "release_id": digest,
        "service_mode": "RECOMMENDATIONS_AND_SIMULATIONS_ONLY",
        "source_hashes": hashes,
        "environment": environment,
        "broker_submission_enabled": False,
        "public_release_checks": list(PRODUCT_CHECKS),
    }


def readiness(manifest, mandate, symbols, *, now, root=None):
    checks = {name: "BLOCKED" for name in PRODUCT_CHECKS}
    covered = set()
    latest = {}
    if root is not None:
        root = Path(root)
        for path in sorted((root / "records").glob("*.json")):
            receipt = json.loads(
                safe_file(root, str(path.relative_to(root))).read_text()
            )
            if (
                receipt.get("release_id") != manifest["release_id"]
                or receipt.get("jurisdiction") != mandate.jurisdiction
            ):
                continue
            check = receipt.get("check")
            stamp = aware_time(receipt["recorded_at"])
            if (
                check not in checks
                or receipt.get("status") not in {"PASS", "FAIL"}
                or not receipt.get("reviewer", "").strip()
                or not receipt.get("artifacts")
                or stamp > aware_time(now)
                or aware_time(now) - stamp > timedelta(days=90)
                or receipt.get("service_mode") != manifest["service_mode"]
            ):
                raise ValueError("Invalid or stale product approval receipt")
            for artifact in receipt["artifacts"]:
                if sha256(safe_file(root, artifact["path"])) != artifact["sha256"]:
                    raise ValueError("Changed product approval evidence")
            if check not in latest or stamp > latest[check][0]:
                latest[check] = (stamp, receipt)
        for check, (_, receipt) in latest.items():
            checks[check] = receipt["status"]
            if check == "instrument_access" and receipt["status"] == "PASS":
                covered = set(receipt.get("instruments", []))
    missing = sorted(set(symbols) - covered)
    if missing:
        checks["instrument_access"] = "BLOCKED"
    client = mandate.assessment()
    mandate_hash = hashlib.sha256(
        json.dumps(asdict(mandate), sort_keys=True).encode()
    ).hexdigest()
    client_receipt = latest.get("client_suitability", (None, {}))[1]
    if (
        client["planning_reasons"]
        or client_receipt.get("mandate_sha256") != mandate_hash
    ):
        checks["client_suitability"] = "BLOCKED"
    approved = bool(
        mandate.jurisdiction.strip() and all(v == "PASS" for v in checks.values())
    )
    return {
        "status": "PUBLIC_RECOMMENDATION_QUALIFIED"
        if approved
        else "OPERATOR_PREVIEW_ONLY",
        "checks": checks,
        "client_reasons": client["planning_reasons"],
        "unapproved_instruments": missing,
        "release_id": manifest["release_id"],
        "mandate_sha256": mandate_hash,
        "evidence_receipts": {
            check: hashlib.sha256(
                json.dumps(item[1], sort_keys=True).encode()
            ).hexdigest()
            for check, item in latest.items()
        },
        "public_recommendations_enabled": approved,
        "broker_submission_enabled": False,
        "attestation_policy": "Named human review with hashed evidence; not proof of legal adequacy or reviewer identity",
    }
