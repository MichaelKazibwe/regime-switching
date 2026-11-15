"""Strict canonical evidence reconciliation for private shadow artifacts."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Regular artifact required")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strict_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    return json.loads(
        Path(path).read_text(),
        object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")),
    )


def reconcile_history(report, root):
    from live_strategy_training import _metrics, _history

    for row in [*report["strategies"], *report["benchmarks"]]:
        name = row["name"] + ".csv"
        if name not in report["artifacts"]:
            raise ValueError("Missing required performance artifact")
        frame = pd.read_csv(Path(root) / name, index_col=0, parse_dates=True)
        metrics = _metrics(frame)
        if set(metrics) != set(row["metrics"]) or any(
            isinstance(row["metrics"][k], bool)
            or not np.isfinite(row["metrics"][k])
            or not np.isclose(v, row["metrics"][k], rtol=1e-9, atol=1e-10)
            for k, v in metrics.items()
        ):
            raise ValueError("Headline metrics disagree with verified CSV")
        history = _history(frame)
        if [r[0] for r in history] != [r[0] for r in row["history"]] or not np.allclose(
            np.array([r[1:] for r in history]),
            np.array([r[1:] for r in row["history"]]),
            rtol=1e-9,
            atol=1e-10,
        ):
            raise ValueError("Displayed history disagrees with verified CSV")


def validate_scenario(result, lab):
    from macro_allocation_lab import recalculate

    result = deepcopy(result)
    supplied_id = result.pop("result_id", None)
    actual_id = hashlib.sha256(
        json.dumps(result, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    if supplied_id != actual_id:
        raise ValueError("Scenario calculation ID mismatch")
    weights, cash = result["weights"], result["cash"]
    if isinstance(cash, bool) or not np.isfinite(cash) or not 0 <= cash <= 1:
        raise ValueError("Invalid cash weight")
    if any(
        isinstance(w, bool) or not np.isfinite(w) or not 0 <= w <= 0.250001
        for w in weights.values()
    ):
        raise ValueError("Invalid instrument weight")
    if abs(sum(weights.values()) + cash - 1) > 1e-6:
        raise ValueError("Capital does not reconcile")
    sim = result["simulation"]
    if sim["status"] != "CONDITIONAL_RESEARCH_SCENARIOS" or sim["paths"] != 500:
        raise ValueError("Successful covered simulation required")
    expected = recalculate(
        lab,
        result["strategy"],
        result["forecast_weights"],
        quarters=sim["quarters"],
        paths=500,
        mode=result["mode"],
    )
    for item in [result, expected]:
        for key in ["result_id", "calculated_at", "forecast_supplied_at"]:
            item.pop(key, None)
    if canonical(result) != canonical(expected):
        raise ValueError("Scenario disagrees with independent recalculation")
    # Recalculation reconciles covariance, Euler shares, cash-only None shares,
    # forecasts, fan quantiles, finite metrics, resource bounds and account peaks.
    return True


def seal_dashboard(document, payload, pdf_bindings, main_pdf=None):
    from productreport import private_write

    root = Path(document).parent
    manifest = {
        "schema_version": 2,
        "payload_sha256": fingerprint(payload),
        "html_sha256": file_hash(document),
        "run_id": payload["training"]["run_id"],
        "pdfs": {},
        "release_approved": False,
        "source_hashes": {
            name: file_hash(name)
            for name in [
                "strategy_integrity.py",
                "growth_resilience.py",
                "capture_growth_inputs.py",
                "market_news.py",
                "portfolio_objectives.py",
                "portfolio_contract.py",
                "strategy_monthly_report.py",
                "shadow_bundle_backup.py",
                "integrated_strategy_comparison.py",
                "strategy_operations.py",
                "strategy_receipts.py",
                "strategy_report.py",
                "refresh_strategy_dashboard.py",
                "strategy_dashboard_server.py",
                "macro_allocation_lab.py",
                "macro_lab_pdf.py",
                "investor_pdf.py",
                "scheduled_strategy_validation.py",
                "strategy_healthcheck.py",
                "prospective_strategy_ledger.py",
            ]
        },
    }
    for name, binding in pdf_bindings.items():
        if Path(name).name != name or not name.endswith(".pdf"):
            raise ValueError("Contained PDF name required")
        manifest["pdfs"][name] = {"sha256": file_hash(root / name), **binding}
    if main_pdf:
        manifest["main_investor_pdf"] = {
            **main_pdf,
            "sha256": file_hash(main_pdf["path"]),
            "context_sha256": fingerprint(payload["context"]),
        }
    private_write(root / "artifact-manifest.json", canonical(manifest))
    return manifest


def verify_seal(document, payload):
    root = Path(document).parent
    manifest = strict_json(root / "artifact-manifest.json")
    if (
        manifest.get("schema_version") != 2
        or manifest.get("release_approved") is not False
        or manifest["payload_sha256"] != fingerprint(payload)
        or manifest["html_sha256"] != file_hash(document)
        or manifest["run_id"] != payload["training"]["run_id"]
    ):
        raise ValueError("Dashboard manifest mismatch")
    if not manifest.get("source_hashes") or any(
        file_hash(name) != h for name, h in manifest["source_hashes"].items()
    ):
        raise ValueError("Artifact validation source mismatch")
    required = set(payload["pdf_links"].values()) | set(
        payload["allocation_lab"]["pdf_links"].values()
    )
    if set(manifest["pdfs"]) != required:
        raise ValueError("PDF manifest coverage mismatch")
    for name, entry in manifest["pdfs"].items():
        if Path(name).name != name or entry["sha256"] != file_hash(root / name):
            raise ValueError("PDF hash mismatch")
        if not (root / name).read_bytes().startswith(b"%PDF-"):
            raise ValueError("Invalid PDF")
        if "result_id" in entry:
            strategy, preset = entry["scenario"].split(":")
            result = payload["allocation_lab"]["results"][strategy][preset]
            if entry["result_id"] != result["result_id"] or entry[
                "result_sha256"
            ] != fingerprint(result):
                raise ValueError("PDF calculation binding mismatch")
        elif (
            entry.get("plan_id") not in payload["pdf_links"]
            or payload["pdf_links"][entry["plan_id"]] != name
            or entry.get("context_sha256") != fingerprint(payload["context"])
        ):
            raise ValueError("PDF plan/context binding mismatch")
    if manifest.get("main_investor_pdf"):
        main = manifest["main_investor_pdf"]
        if (
            main["sha256"] != file_hash(main["path"])
            or main["context_sha256"] != fingerprint(payload["context"])
            or main["plan_id"] not in payload["pdf_links"]
        ):
            raise ValueError("Main investor PDF binding mismatch")
    return manifest
