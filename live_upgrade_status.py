"""Inventory progress without granting qualification or execution authority."""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from strategy_integrity import file_hash, fingerprint
from strategy_receipts import atomic_json

LOCAL_PROGRESS = {
    "01": "Scope recorded; Mauritius/IBKR provisional, professional approvals absent.",
    "05": "Numeric repair tested; browser qualification incomplete.",
    "06": "Exact dynamic replay and cost-sensitivity tooling added; independent validation and acceptance remain open.",
    "13": "Account outbox, dispatch/ambiguity recovery and writer fencing tested locally; genuine broker sandbox qualification absent.",
    "15": "Lot/tick/quote contracts and four venue calendars tested; verified security master/quote feeds absent.",
    "20": "Position, carrying-cost, fee and settlement journals implemented; corporate actions, FX/tax lots and verified broker accounting remain open.",
    "23": "Opaque sessions and account grants/internal API tested; production identity, security and privacy qualification remain open.",
    "25": "Local SLO/metrics/escalation monitor, monotonic account writer leases and backup/restore drills implemented. External delivery and off-host/single-host-pilot qualification remain open. See LIVE_ROADMAP_P1_EXECUTION.md.",
    "26": "Forward calibration/drift, prospective risk registry, turnover and broker-evidence shortfall/latency diagnostics implemented. Genuine broker records and matured risk/forecast windows remain unavailable; no automatic refit/promotion.",
}


def inventory(roadmap="LIVE_TRADING_UPGRADE_ROADMAP.md"):
    tasks = []
    for line in Path(roadmap).read_text().splitlines():
        cells = [s.strip() for s in line.strip("|").split("|")]
        if len(cells) != 5 or not cells[0].isdigit():
            continue
        key, priority, work, criterion, dependency = cells
        tasks.append(
            dict(
                id=key,
                priority=priority,
                work=work,
                completion_criterion=criterion,
                dependency=dependency,
                qualification="OPEN",
                implementation_status="IMPLEMENTED_LOCAL_QUALIFICATION_PARTIAL"
                if key in {"25", "26"}
                else "SEE_PROGRESS_AND_QUALIFICATION",
                progress=LOCAL_PROGRESS.get(
                    key, "Completion evidence not established by this inventory."
                ),
            )
        )
    if [t["id"] for t in tasks] != [f"{i:02}" for i in range(1, 27)]:
        raise ValueError("Exact ordered 26-item checklist required")
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "BLOCKED_UNQUALIFIED",
        "execution_enabled": False,
        "release_approved": False,
        "roadmap_sha256": file_hash(roadmap),
        "implementation_sources": {
            p: file_hash(p)
            for p in (
                "managed_accounts.py",
                "writer_fencing.py",
                "operational_metrics.py",
                "operational_escalation.py",
                "operational_recovery.py",
                "managed_disaster_recovery.py",
                "live_p1_service.py",
                "strategy_degradation.py",
                "execution_degradation.py",
                "risk_forecast_registry.py",
                "operational_model_review.py",
                "test_managed_accounts.py",
                "global_market_calendar.py",
                "test_global_market_calendar.py",
                "test_live_upgrade_status.py",
                "evaluate_dynamic_portfolio.py",
                "test_dynamic_replay.py",
                __file__,
            )
        },
        "tasks": tasks,
        "external_dependencies": [
            "Licensing/tax scope and client-country approval",
            "Broker acceptance, account permissions and sandbox access",
            "Linux Docker host and immutable release CI evidence",
            "Verified financial inputs and data entitlements",
            "Actual observation sessions, completed month and report delivery",
            "Independent model/security/operations/browser qualification",
        ],
    }
    result["inventory_id"] = fingerprint(result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="var/live-upgrade/status.json")
    args = parser.parse_args()
    report = inventory()
    atomic_json(Path(args.output), report)
    print(f"{report['status']}: 26 open qualification items; {args.output}")
