"""One-shot current-data training, constrained scenario generation and UI/PDF refresh.

Suitable for a separately qualified scheduler. This command does not install
one, promote a model, alter saved investor plans or place orders.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from investor_analytics import macro_context
from investor_dashboard import render_payload
from investor_pdf import render_investor_pdf
from live_strategy_training import train
from macro_allocation_lab import build_lab_payload
from macro_lab_pdf import render_allocation_pdf
from productreport import private_write
from strategy_dashboard_server import read_payload
from strategy_report import load_training_report
from strategy_integrity import seal_dashboard, fingerprint, file_hash, verify_seal
from strategy_receipts import atomic_json


def retire_extensions(payload):
    """A fresh core run cannot carry a prior dynamic contract/report as current."""
    plan_ids = {p["id"] for p in payload["plans"]}
    payload["pdf_links"] = {
        key: value
        for key, value in payload.get("pdf_links", {}).items()
        if key in plan_ids
    }
    for key in ("dynamic_portfolio", "return_engines"):
        payload.pop(key, None)
    payload["extensions_status"] = "REQUIRES_SEPARATE_CURRENT_CONTRACT_REFRESH"


def integrate(
    capture,
    training,
    dashboard,
    *,
    latest_macro_features=None,
    investor_pdf=None,
    benchmark_extension=None,
):
    dashboard = Path(dashboard)
    payload = read_payload(dashboard)
    # Existing client plan payloads are preserved byte-for-byte at the data level.
    original = json.dumps(payload["plans"], sort_keys=True)
    retire_extensions(payload)
    from investmentcatalog import catalogue_payload
    from global_asset_registry import load_registry
    payload["catalogue"] = catalogue_payload()
    payload["core_symbols"] = list(load_registry().symbols())
    payload["universe_contract"] = load_registry().payload()
    if latest_macro_features:
        rows = json.loads(Path(latest_macro_features).read_text())
        if not isinstance(rows, list) or any(
            r.get("source_kind") != "CURRENT_REVISED_FRED_NOT_HISTORICAL_VINTAGES"
            for r in rows
        ):
            raise ValueError("Explicit current/revised FRED features required")
        now = datetime.now(timezone.utc)
        if any(datetime.fromisoformat(r["as_of"]) > now for r in rows):
            raise ValueError("Future macro availability")
        current = macro_context(rows, now.isoformat())
        if not rows:
            current["reason"] = (
                "Current informational FRED features unavailable: required calendar "
                "observations are missing or stale. No values were filled. "
                "Strategy evaluation uses its separate point-in-time inputs."
            )
        if current.get("status") == "HISTORICAL_RESEARCH_CONTEXT":
            current["status"] = "LATEST_AVAILABLE_FRED_CONTEXT"
        if current.get("limitations"):
            current["limitations"][0] = (
                "Latest informational FRED overlay; revised historical training observations are not historical vintages."
            )
        for entry in payload["context"]["plans"].values():
            entry["latest_macro"] = current
    first = payload["context"]["plans"][payload["plans"][0]["id"]]
    macro = first.get("latest_macro") or first.get("macro") or {}
    report = load_training_report(training)
    _, lab = build_lab_payload(capture, training, quarterly=macro.get("quarterly", []))
    lab["pdf_links"] = {}
    pdf_bindings = {}
    from portfolio_contract import make_contract, build_contracts

    for name, results in lab["results"].items():
        filename = f"strategy-{name}.pdf"
        if results["latest_model"].get("weights"):
            render_allocation_pdf(
                results["latest_model"],
                dashboard.parent / filename,
                report,
                contract=make_contract(
                    name,
                    {
                        **results["latest_model"]["weights"],
                        "USD_CASH": results["latest_model"]["cash"],
                    },
                    report["market_session"],
                    report["run_id"],
                    basis="CURRENT_MACRO_SCENARIO_ALLOCATION",
                    performance="FROZEN_MODEL_EVALUATION_NOT_CURRENT_WEIGHTS_BACKTEST",
                ),
            )
            lab["pdf_links"][f"{name}:latest_model"] = filename
            pdf_bindings[filename] = {
                "scenario": f"{name}:latest_model",
                "result_id": results["latest_model"]["result_id"],
                "result_sha256": fingerprint(results["latest_model"]),
            }
    from growth_resilience import build_benchmark
    from portfolio_objectives import POLICY_VERSION

    extension_index = Path("var/growth-resilience-data/latest.json")
    extension = (
        Path(benchmark_extension)
        if benchmark_extension
        else (
            Path(json.loads(extension_index.read_text())["root"])
            if extension_index.is_file()
            else None
        )
    )
    if extension:
        payload["growth_resilience"] = build_benchmark(capture, extension)
        news_path = extension / "news.json"
        extension_meta = json.loads((extension / "capture.json").read_text())
        if file_hash(news_path) != extension_meta["news_sha256"]:
            raise ValueError("News capture checksum mismatch")
        payload["news"] = json.loads(news_path.read_text())
    payload["objective_policy"] = {
        "version": POLICY_VERSION,
        "fixed_return_target": None,
        "maximum_account_drawdown": None,
        "historical_plans_archived": True,
    }
    payload["training"] = report
    payload["allocation_lab"] = lab
    payload["portfolio_contracts"] = build_contracts(payload)
    private_write(
        dashboard.parent / "portfolio-contracts.json",
        json.dumps(payload["portfolio_contracts"], indent=2, allow_nan=False),
    )
    payload["viewer_version"] = 4
    if original != json.dumps(payload["plans"], sort_keys=True):
        raise ValueError("Client plan mutation forbidden")
    private_write(
        dashboard.parent / "allocation-lab.json", json.dumps(lab, allow_nan=False)
    )
    context = {
        **payload["context"],
        "allocation_lab": lab,
        "training": report,
        "growth_resilience": payload.get("growth_resilience"),
        "portfolio_contracts": payload["portfolio_contracts"],
    }
    demo_manifest = Path("var/product-preview/demo-manifest.json")
    if demo_manifest.is_file():
        allowed = {plan["id"] for plan in payload["plans"]}
        for index, item in enumerate(json.loads(demo_manifest.read_text())["reports"]):
            result = json.loads(
                (Path(item["report"]).parent / "recommendation.json").read_text()
            )
            if result["recommendation_id"] in allowed:
                name = f"investor-report-{index}.pdf"
                render_investor_pdf(result, context, dashboard.parent / name)
                payload["pdf_links"][result["recommendation_id"]] = name
                pdf_bindings[name] = {
                    "plan_id": result["recommendation_id"],
                    "context_sha256": fingerprint(payload["context"]),
                }
    main_pdf_binding = None
    if investor_pdf:
        # Render the original balanced illustration, with a clearly separate shadow-strategy appendix.
        result = json.loads(
            Path("var/product-preview/balanced/recommendation.json").read_text()
        )
        context = {
            **payload["context"],
            "allocation_lab": lab,
            "training": report,
            "growth_resilience": payload.get("growth_resilience"),
            "portfolio_contracts": payload["portfolio_contracts"],
        }
        render_investor_pdf(result, context, investor_pdf)
        main_pdf_binding = {
            "path": str(Path(investor_pdf).resolve()),
            "plan_id": result["recommendation_id"],
        }
    private_write(
        dashboard.parent / "latest-strategy-run.json",
        json.dumps(
            {
                "capture": str(Path(capture).resolve()),
                "training_report": str(Path(training).resolve()),
                "market_session": report["market_session"],
                "benchmark_extension": str(extension.resolve()) if extension else None,
                "portfolio_contracts": str(
                    (dashboard.parent / "portfolio-contracts.json").resolve()
                ),
                "contract_map_sha256": file_hash(
                    dashboard.parent / "portfolio-contracts.json"
                ),
            },
            indent=2,
        ),
    )
    render_payload(payload, dashboard)
    seal_dashboard(dashboard, payload, pdf_bindings, main_pdf_binding)
    verify_seal(dashboard, payload)
    for alias in ("index.html", "v2.html", "strategy-workspace.html"):
        path = dashboard.parent / alias
        if path != dashboard:
            private_write(path, dashboard.read_text())
    return {
        "status": "UPDATED_SHADOW_DASHBOARD",
        "dashboard": str(dashboard.resolve()),
        "training_report": str(Path(training).resolve()),
        "market_session": report["market_session"],
        "client_plans_changed": False,
        "execution_enabled": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--capture", type=Path)
    source.add_argument("--download", action="store_true")
    parser.add_argument(
        "--training-report",
        type=Path,
        help="Reuse a verified completed run instead of retraining",
    )
    parser.add_argument(
        "--dashboard",
        type=Path,
        default=Path("var/investor-dashboard/investor-dashboard.html"),
    )
    parser.add_argument("--latest-macro-features", type=Path)
    parser.add_argument("--benchmark-extension", type=Path)
    parser.add_argument(
        "--investor-pdf",
        type=Path,
        default=Path("output/pdf/investor-macro-risk-report.pdf"),
    )
    args = parser.parse_args()
    latest = args.latest_macro_features
    if args.download:
        from strategy_training_data import capture
        from investor_macro_feed import refresh

        captured = capture(
            "var/strategy-training-snapshots",
            "var/research/smart-macro-vintages/manifest.json",
        )
        latest = Path(refresh("var/investor-macro-snapshots")["features"])
        from capture_growth_inputs import capture_growth_inputs

        capture_growth_inputs()
    else:
        captured = args.capture
    trained = args.training_report or train(captured, "var/strategy-training-runs")
    extension = args.benchmark_extension
    if extension is None and Path("var/growth-resilience-data/latest.json").is_file():
        extension = Path(
            json.loads(Path("var/growth-resilience-data/latest.json").read_text())[
                "root"
            ]
        )
    checkpoint = dict(
        capture=str(Path(captured).resolve()),
        training_report=str(Path(trained).resolve()),
        benchmark_extension=str(extension.resolve()) if extension else None,
        latest_macro_features=str(latest.resolve()) if latest else None,
    )
    checkpoint["input_hashes"] = {
        checkpoint[k]: file_hash(checkpoint[k])
        for k in ("capture", "training_report", "latest_macro_features")
        if checkpoint[k]
    }
    atomic_json(args.dashboard.parent / "training-checkpoint.json", checkpoint)
    print(
        json.dumps(
            integrate(
                captured,
                trained,
                args.dashboard,
                latest_macro_features=latest,
                investor_pdf=args.investor_pdf,
                benchmark_extension=extension,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
