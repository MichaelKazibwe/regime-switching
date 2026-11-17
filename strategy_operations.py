"""Private acceptance evidence and prospective shadow-observation ledger.

No orders, model promotion, email delivery or public serving capabilities.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from productreport import private_write
from strategy_dashboard_server import read_payload
from strategy_report import load_training_report
from strategy_training_data import usable_session
from strategy_integrity import canonical, validate_scenario, verify_seal, fingerprint
from macro_allocation_lab import prepare_lab


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def macro_availability_handled(report, features):
    available = features[-1].get("macro_valid", True)
    if report["latest_macro_available"] is not available:
        return False
    if available:
        return True
    forecast = report["classifier"]["latest_forecast"]
    return (
        forecast.get("input_valid") is False
        and forecast.get("enabled") is False
        and all(
            row["candidate"].get("status") == "DATA_QUARANTINE_CASH_ONLY"
            and row["candidate"].get("cash") == 1.0
            and all(w == 0.0 for w in row["candidate"]["weights"].values())
            for row in report["strategies"]
        )
    )


def scenario_modes_valid(payload):
    first = payload["context"]["plans"][payload["plans"][0]["id"]]
    macro = first.get("latest_macro") or first.get("macro") or {}
    quarters = macro.get("quarterly", [])
    if macro.get("status") == "UNAVAILABLE":
        if quarters:
            return False
    elif len(quarters) != 4:
        return False
    expected = {"latest_model", *(q["quarter"] for q in quarters)}
    results = payload["allocation_lab"]["results"]
    return len(results) == 4 and len(expected) == 1 + len(quarters) and all(
        set(rows) == expected for rows in results.values()
    )


def audit(bundle, dashboard):
    bundle_path = bundle
    bundle = json.loads(Path(bundle).read_text())
    report_path = Path(bundle["training_report"])
    report = load_training_report(report_path)
    capture_path = Path(bundle["capture"])
    capture = json.loads(capture_path.read_text())
    for name, expected in capture["files"].items():
        path = (capture_path.parent / name).resolve()
        if path.parent != capture_path.parent.resolve() or digest(path) != expected:
            raise ValueError("Capture artifact mismatch")
    features = json.loads((report_path.parent / "features.json").read_text())
    evaluation = [
        r
        for r in features
        # Returns begin after the initial decision; quarantine counts cover the
        # decision inputs, including that initial date and excluding the last close.
        if report["evaluation"]["new_account_start"]
        <= r["date"]
        < report["evaluation"]["end"]
    ]
    quarantined = [r for r in evaluation if not r.get("macro_valid", True)]
    payload = read_payload(dashboard)
    checks = {
        "capture_matches_report": digest(capture_path) == report["capture_sha256"],
        "same_training_run": payload["training"]["run_id"] == report["run_id"],
        "current_numerical_sources": report["current_numerical_source_match"],
        "macro_availability_handled": macro_availability_handled(report, features),
        "current_completed_session": report["market_session"]
        == str(usable_session(datetime.now(timezone.utc)).date()),
        "quarantine_count_reconciles": len(quarantined)
        == report["evaluation_quarantined_sessions"],
        "non_executable": report["execution_enabled"] is False
        and report["promotion"] == "NONE",
    }
    checks["training_display_reconciles"] = canonical(payload["training"]) == canonical(
        report
    )
    verify_seal(dashboard, payload)
    from portfolio_contract import verify_contracts

    checks["portfolio_contracts_verified"] = verify_contracts(payload)
    checks["contract_export_matches_viewer"] = (
        bundle.get("contract_map_sha256") == digest(bundle["portfolio_contracts"])
        and json.loads(Path(bundle["portfolio_contracts"]).read_text())
        == payload["portfolio_contracts"]
    )
    checks["artifact_manifest_verified"] = True
    lab = prepare_lab(capture_path, report_path)
    results = payload["allocation_lab"]["results"]
    scenarios = []
    for strategy, rows in results.items():
        for mode, result in rows.items():
            valid = validate_scenario(result, lab)
            scenarios.append({"strategy": strategy, "mode": mode, "passed": valid})
    checks["all_available_scenarios_valid"] = scenario_modes_valid(payload) and all(
        s["passed"] for s in scenarios
    )
    checks["all_strategy_pdfs_present"] = all(
        (Path(dashboard).parent / f"strategy-{s}.pdf").read_bytes().startswith(b"%PDF-")
        for s in results
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "LOCAL_ACCEPTANCE_PASSED" if all(checks.values()) else "BLOCKED",
        "checks": checks,
        "market_session": report["market_session"],
        "run_id": report["run_id"],
        "report_sha256": digest(report_path),
        "schema_version": 2,
        "artifact_manifest_sha256": digest(
            Path(dashboard).parent / "artifact-manifest.json"
        ),
        "bundle_sha256": digest(bundle_path),
        "artifact_manifest_path": str(
            (Path(dashboard).parent / "artifact-manifest.json").resolve()
        ),
        "training_report_path": str(report_path.resolve()),
        "bundle": str(Path(bundle_path).resolve()),
        "dashboard": str(Path(dashboard).resolve()),
        "evaluation_quarantine_reasons": dict(
            Counter(
                r.get("macro_unavailable_reason", "UNSPECIFIED") for r in quarantined
            )
        ),
        "quarantined_dates": [r["date"] for r in quarantined],
        "scenarios": scenarios,
        "predictive_gate": report["classifier"]["latest_gate"],
        "latest_macro_available": report["latest_macro_available"],
        "observation_protocol": fingerprint({"sources": report["source_hashes"],
                                               "universe": report["core_universe"]}),
        "informational_macro_status": (
            payload["context"]["plans"][payload["plans"][0]["id"]]
            .get("latest_macro", {}).get("status", "UNAVAILABLE")
        ),
        "strategy_metrics": {r["name"]: r["metrics"] for r in report["strategies"]},
        "release_approved": False,
        "limitations": [
            "Local acceptance is not host qualification or investment approval.",
            "Quarantined data remain unavailable; no imputation or freshness relaxation.",
        ],
    }


def observe(evidence, root, *, now=None):
    """One immutable observation per real market session; backfill is forbidden."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Aware observation timestamp required")
    if evidence["status"] != "LOCAL_ACCEPTANCE_PASSED":
        raise ValueError("Failed acceptance cannot count as an observation")
    if evidence["market_session"] != str(usable_session(now).date()):
        raise ValueError("Only the current completed session may be observed")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / (evidence["market_session"] + ".json")
    from strategy_receipts import atomic_json, read_observation, validate_observation
    from strategy_integrity import fingerprint

    record = {
        "schema_version": 2,
        "observed_at": now.isoformat(),
        "evidence": evidence,
        "release_approved": False,
    }
    record["receipt_sha256"] = fingerprint(record)
    if path.exists():
        previous = read_observation(path, now)
        if (
            previous["evidence"]["report_sha256"] != evidence["report_sha256"]
            or previous["evidence"]["artifact_manifest_sha256"]
            != evidence["artifact_manifest_sha256"]
        ):
            raise ValueError("Session already sealed with a different training run")
    else:
        # Validate schema before committing an exclusively linked complete file.
        if (
            evidence.get("schema_version") != 2
            or not evidence.get("checks")
            or not all(v is True for v in evidence["checks"].values())
        ):
            raise ValueError("Validated v2 acceptance required")
        validate_observation(record, evidence["market_session"], now)
        atomic_json(path, record, exclusive=True)
        read_observation(path, now)
    rows = [read_observation(p, now) for p in sorted(root.glob("????-??-??.json"))]
    sessions = {r["evidence"]["market_session"] for r in rows
                if r["evidence"].get("observation_protocol") == evidence.get("observation_protocol")}
    return {
        "observed_sessions": len(sessions),
        "required_sessions": 20,
        "observation_window_complete": len(sessions) >= 20,
        "status": "REVIEW_REQUIRED" if len(sessions) >= 20 else "OBSERVING",
        "release_approved": False,
        "automatic_promotion": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle",
        type=Path,
        default=Path("var/investor-dashboard/latest-strategy-run.json"),
    )
    parser.add_argument(
        "--dashboard",
        type=Path,
        default=Path("var/investor-dashboard/investor-dashboard.html"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("var/strategy-operations/acceptance.json")
    )
    parser.add_argument("--observe", action="store_true")
    args = parser.parse_args()
    evidence = audit(args.bundle, args.dashboard)
    private_write(args.output, json.dumps(evidence, indent=2, allow_nan=False))
    if args.observe:
        state = observe(evidence, args.output.parent / "observations")
        private_write(
            args.output.parent / "observation-status.json", json.dumps(state, indent=2)
        )
        print(json.dumps(state, indent=2))
    print(
        json.dumps(
            {"status": evidence["status"], "checks": evidence["checks"]}, indent=2
        )
    )
    if evidence["status"] != "LOCAL_ACCEPTANCE_PASSED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
