"""Attach reconciled, clearly unapproved challengers without changing client plans."""

from pathlib import Path
import argparse
import json
from investor_dashboard import render_payload
from strategy_dashboard_server import read_payload
from strategy_integrity import file_hash, seal_dashboard, verify_seal


def publish(assessment, robustness, dashboard):
    a = json.loads(Path(assessment).read_text())
    r = json.loads(Path(robustness).read_text())
    if (
        r["assessment_sha256"] != file_hash(assessment)
        or any(file_hash(p) != h for p, h in a["source_hashes"].items())
        or any(file_hash(p) != h for p, h in r["source_artifacts"].items())
    ):
        raise ValueError("Reconciled frozen engine evidence required")
    dashboard = Path(dashboard)
    payload = read_payload(dashboard)
    manifest = json.loads((dashboard.parent / "artifact-manifest.json").read_text())
    if a["market_session"] != payload["training"]["market_session"]:
        raise ValueError("Current market session mismatch")
    payload["return_engines"] = {
        "assessment": a,
        "robustness": r,
        "status": "UNAPPROVED_CHALLENGERS_INCUMBENTS_UNCHANGED",
    }
    render_payload(payload, dashboard)
    seal_dashboard(
        dashboard,
        payload,
        {
            name: {k: v for k, v in info.items() if k != "sha256"}
            for name, info in manifest["pdfs"].items()
        },
        manifest.get("main_investor_pdf"),
    )
    assert verify_seal(dashboard, payload)
    for alias in ["index.html", "v2.html", "strategy-workspace.html"]:
        (dashboard.parent / alias).write_text(dashboard.read_text())
    return {
        "status": "UNAPPROVED_PREVIEW_UPDATED",
        "current_client_plans_changed": False,
        "automatic_promotion": False,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--assessment",
        default="var/institutional-return-engines/v1-validated/assessment.json",
    )
    p.add_argument(
        "--robustness",
        default="var/institutional-return-engines/v1-validated/robustness.json",
    )
    p.add_argument(
        "--dashboard", default="var/investor-dashboard/investor-dashboard.html"
    )
    a = p.parse_args()
    print(json.dumps(publish(a.assessment, a.robustness, a.dashboard)))
