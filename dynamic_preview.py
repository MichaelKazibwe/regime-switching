"""Verified dynamic portfolio preview and contract-bound PDF; no promotion."""

from pathlib import Path
from html import escape
import argparse
import pandas as pd

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from investor_pdf import styles, table, percent, LineChart
from dynamic_portfolio import refresh
from investor_dashboard import render_payload
from portfolio_contract import validate_contract
from strategy_dashboard_server import read_payload
from strategy_integrity import (
    strict_json,
    file_hash,
    fingerprint,
    seal_dashboard,
    verify_seal,
)
from assetroles import ASSET_ROLES


def validate(snapshot, assessment, reconciliation):
    body = {k: v for k, v in snapshot.items() if k != "snapshot_id"}
    if fingerprint(body) != snapshot.get("snapshot_id"):
        raise ValueError("Dynamic snapshot identity mismatch")
    validate_contract(snapshot["contract"])
    if (
        snapshot["execution_enabled"] is not False
        or snapshot["promotion_enabled"] is not False
    ):
        raise ValueError("Dynamic preview cannot authorize execution")
    for symbol, weight in snapshot["weights"].items():
        if snapshot["contract"]["weights"].get(symbol, 0) != weight:
            raise ValueError("Dynamic contract weights differ")
    if abs(snapshot["contract"]["weights"]["USD_CASH"] - snapshot["cash"]) > 1e-12:
        raise ValueError("Dynamic cash mismatch")
    for document in (snapshot, assessment):
        if any(file_hash(p) != h for p, h in document["source_hashes"].items()):
            raise ValueError("Dynamic source mismatch")
    if (
        assessment["end"] != snapshot["decision_session"]
        or reconciliation.get("release_approved") is not False
    ):
        raise ValueError("Dynamic dates or reconciliation invalid")
    if set(reconciliation["checks"]) != {"0bps", "15bps", "30bps"} or any(
        c["status"] != "RECONCILED_LOCAL_REPLAY"
        for c in reconciliation["checks"].values()
    ):
        raise ValueError("All dynamic cost replays must reconcile")


def render_pdf(block, destination):
    snapshot, assessment = block["snapshot"], block["assessment"]
    s = styles()

    def p(text):
        return Paragraph(escape(str(text)), s["InvestorSmall"])

    story = [
        Paragraph("Dynamic Growth &amp; Resilience", s["InvestorTitle"]),
        p(
            "UNAPPROVED PAPER CANDIDATE - no orders, client mandate or release approval."
        ),
        p(
            "Valuation: "
            + snapshot["decision_session"]
            + " / regime: "
            + snapshot["regime"]
        ),
        p("Contract: " + snapshot["contract"]["contract_id"]),
        p("Snapshot: " + snapshot["snapshot_id"]),
        p(snapshot.get("mix_note", "See dated strategy methodology.")),
        Spacer(1, 12),
    ]
    rows = [["Engine", "Blend"]] + [
        [k.replace("_", " "), percent(v)] for k, v in snapshot["engine_mix"].items()
    ]
    story += [table(rows, [360, 150], s["InvestorSmall"]), Spacer(1, 12)]
    rows = [["Asset / economic role", "Capital", "Variance share"]]
    roles = block.get("roles", ASSET_ROLES)
    for symbol in roles:
        weight = (
            snapshot["cash"]
            if symbol == "USD_CASH"
            else snapshot["weights"].get(symbol, 0)
        )
        risk = 0 if symbol == "USD_CASH" else snapshot["risk_shares"].get(symbol, 0)
        rows.append([symbol + " - " + roles[symbol], percent(weight), percent(risk)])
    asset_table = table(rows, [350, 75, 85], s["InvestorSmall"])
    rows = [["Retrospective cost", "CAGR", "Volatility", "Max drawdown"]]
    for cost, metrics in assessment["metrics"].items():
        rows.append(
            [
                cost,
                percent(metrics["cagr"]),
                percent(metrics["annual_volatility"]),
                percent(metrics["maximum_drawdown"]),
            ]
        )
    story += [
        table(rows, [150, 120, 120, 120], s["InvestorSmall"]),
        Spacer(1, 12),
        p(
            "Historical replay wealth (15 bps) - actual past decisions, not today's weights"
        ),
        LineChart(
            [r["equity"] for r in block.get("history", [])],
            [r["date"] for r in block.get("history", [])],
            width=510,
            height=160,
        ),
        p(assessment["warning"]),
        p(
            "Forecast volatility is a model estimate. Historical costs are modeled; zero verified cash yield. Past allocations differ from today's weights. Forecast simulations for this exact blend are not yet qualified."
        ),
    ]
    story += [
        PageBreak(),
        Paragraph("Current allocation and risk", s["InvestorTitle"]),
        p("Contract: " + snapshot["contract"]["contract_id"]),
        asset_table,
    ]
    SimpleDocTemplate(
        str(destination), pagesize=A4, leftMargin=42, rightMargin=42
    ).build(story)


def publish(bundle, evaluation, dashboard):
    dashboard, evaluation = Path(dashboard), Path(evaluation)
    assessment = strict_json(evaluation / "assessment.json")
    reconciliation = strict_json(evaluation / "reconciliation.json")
    if reconciliation["assessment_sha256"] != file_hash(evaluation / "assessment.json"):
        raise ValueError("Dynamic assessment/reconciliation mismatch")
    if reconciliation["replay_code_sha256"] != file_hash(
        "economic_design_assessment.py"
    ):
        raise ValueError("Dynamic reconciliation source changed")
    if any(file_hash(evaluation / p) != h for p, h in assessment["artifacts"].items()):
        raise ValueError("Changed dynamic evaluation artifact")
    snapshot = refresh(bundle, evaluation.parent / "latest.json")
    validate(snapshot, assessment, reconciliation)
    payload = read_payload(dashboard)
    manifest = strict_json(dashboard.parent / "artifact-manifest.json")
    if payload["training"]["market_session"] != snapshot["decision_session"]:
        raise ValueError("Dashboard/dynamic session mismatch")
    frame = pd.read_csv(evaluation / "15bps.csv")
    sample = frame.iloc[
        sorted(set(range(0, len(frame), max(1, len(frame) // 250))) | {len(frame) - 1})
    ]
    block = dict(
        snapshot=snapshot,
        assessment=assessment,
        reconciliation=reconciliation,
        pdf="dynamic-portfolio-report.pdf",
        history=sample[["date", "equity", "drawdown"]].to_dict("records"),
        roles={
            **ASSET_ROLES,
            "DBMF": "Managed futures trend diversifier; derivative and strategy risk.",
        },
    )
    render_pdf(block, dashboard.parent / block["pdf"])
    payload["dynamic_portfolio"] = block
    key = snapshot["contract"]["contract_id"]
    payload["pdf_links"][key] = block["pdf"]
    bindings = {
        name: {k: v for k, v in entry.items() if k != "sha256"}
        for name, entry in manifest["pdfs"].items()
    }
    bindings[block["pdf"]] = dict(
        plan_id=key, context_sha256=fingerprint(payload["context"])
    )
    render_payload(payload, dashboard)
    manifest = seal_dashboard(
        dashboard, payload, bindings, manifest.get("main_investor_pdf")
    )
    manifest["source_hashes"]["dynamic_preview.py"] = file_hash(__file__)
    from strategy_receipts import atomic_json

    atomic_json(dashboard.parent / "artifact-manifest.json", manifest)
    verify_seal(dashboard, payload)
    for alias in ("index.html", "v2.html", "strategy-workspace.html"):
        (dashboard.parent / alias).write_bytes(dashboard.read_bytes())
    return snapshot["contract"]["contract_id"]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--bundle", default="var/investor-dashboard/latest-strategy-run.json"
    )
    p.add_argument("--evaluation", default="var/dynamic-portfolio/evaluation-20261101")
    p.add_argument(
        "--dashboard", default="var/investor-dashboard/investor-dashboard.html"
    )
    args = p.parse_args()
    print(publish(args.bundle, args.evaluation, args.dashboard))
