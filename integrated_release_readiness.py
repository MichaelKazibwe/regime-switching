"""Report real local evidence and unresolved external gates; never authorize release."""

from pathlib import Path
import argparse
import json
import shutil
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from economic_evidence import verify
from portfolio_contract import extended_prices
from strategy_healthcheck import health
from strategy_integrity import file_hash
from strategy_receipts import atomic_json


def assess(bundle, operations, output, *, evidence_root=None, junit=None):
    b = json.loads(Path(bundle).read_text())
    prices = extended_prices(b["capture"], b["benchmark_extension"])
    import pandas as pd

    report = json.loads(Path(b["training_report"]).read_text())
    dates = pd.read_csv(
        Path(b["training_report"]).parent / "economic_balance.csv",
        index_col=0,
        parse_dates=True,
    ).index
    financial = verify(evidence_root, [s for s in prices if s != "ALLW"], dates)
    checks = {
        "daily_shadow_job": health(operations)["status"],
        "financial_evidence": financial["status"],
        "docker_available_locally": bool(shutil.which("docker")),
        "host_qualified": "BLOCKED_NO_HOST",
        "immutable_image_qualified": "BLOCKED_NO_IMAGE_BUILD",
        "external_alert_delivery": "BLOCKED_NO_DELIVERY_EVIDENCE",
        "public_jurisdiction_review": "BLOCKED_NO_REVIEW",
        "elapsed_observation": "BLOCKED_INCOMPLETE_FORWARD_PERIOD",
        "independent_economic_validation": "BLOCKED_NOT_SUPPLIED",
    }
    localtests = None
    if junit:
        root = ET.parse(junit).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        totals = {
            k: sum(int(s.get(k, 0)) for s in suites)
            for k in ["tests", "failures", "errors", "skipped"]
        }
        localtests = {
            **totals,
            "sha256": file_hash(junit),
            "passed": totals["tests"] > 0
            and totals["failures"] == 0
            and totals["errors"] == 0,
        }
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "LOCAL_IMPLEMENTATION_EXTERNAL_GATES_BLOCKED",
        "checks": checks,
        "financial_evidence": financial,
        "local_regression": localtests,
        "market_session": report["market_session"],
        "bundle_sha256": file_hash(bundle),
        "release_approved": False,
        "execution_enabled": False,
        "scope": "Private non-personalized recommendation preview; local testing is not host qualification, economic approval or evidence of real account suitability.",
    }
    atomic_json(output, result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--bundle", default="var/investor-dashboard/latest-strategy-run.json"
    )
    p.add_argument("--operations", default="var/strategy-operations-integrated-v1")
    p.add_argument("--output", default="var/integrated-deployment/readiness.json")
    p.add_argument("--evidence-root")
    p.add_argument("--junit")
    a = p.parse_args()
    print(
        json.dumps(
            assess(
                a.bundle,
                a.operations,
                a.output,
                evidence_root=a.evidence_root,
                junit=a.junit,
            ),
            indent=2,
        )
    )
