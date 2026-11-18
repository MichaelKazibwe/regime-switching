"""Publish a complete verified viewer separately from immutable cohort evidence."""

from strategy_eligibility import eligible_prices

from pathlib import Path
import fcntl
import shutil
import uuid

import numpy as np
import pandas as pd

from strategy_integrity import strict_json, file_hash, verify_seal, fingerprint
from strategy_receipts import atomic_json


def publish(
    operations="var/strategy-operations-integrated-v1", root="var/dashboard-live"
):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / "publication.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _publish(operations, root)


def _publish(operations, root):
    from dynamic_preview import publish as publish_dynamic
    from evaluate_dynamic_portfolio import evaluate
    from economic_design_assessment import replay
    from portfolio_contract import extended_prices
    from publish_return_engine_preview import publish as publish_engines
    from strategy_dashboard_server import Application, read_payload
    from investor_dashboard import market_payload, render_payload
    from strategy_integrity import seal_dashboard

    root = Path(root).resolve()
    job = strict_json(Path(operations) / "latest-job.json")
    cycle = strict_json("var/live-observation-cycle/latest.json")
    if job["status"] != "PASSED_SHADOW_ONLY" or cycle["status"] != "PASSED_SHADOW_ONLY":
        raise ValueError("Complete successful observation cycle required")
    source = Path(job["job"]) / "dashboard"
    bundle = source / "latest-strategy-run.json"
    if file_hash(bundle) != cycle["bundle_sha256"]:
        raise ValueError("Observation bundle mismatch")
    previous = root / "latest.json"
    viewer_identity = fingerprint(
        {
            p: file_hash(p)
            for p in (
                "dashboard/investor.js",
                "dashboard/investor.html",
                "dashboard/investor.css",
                "dashboard_publication.py", "strategy_eligibility.py", "research/dynamic_eligibility.json",
                "strategy_dashboard_server.py",
                "dynamic_portfolio.py", "evaluate_dynamic_portfolio.py", "dynamic_preview.py",
            )
        }
    )
    if previous.exists():
        saved = strict_json(previous)
        if (
            saved["bundle_sha256"] == file_hash(bundle)
            and saved.get("viewer_identity") == viewer_identity
        ):
            doc = Path(saved["document"])
            if file_hash(doc) == saved["document_sha256"]:
                verify_seal(doc, read_payload(doc))
                return saved
    destination = root / "runs" / uuid.uuid4().hex
    viewer = destination / "dashboard"
    shutil.copytree(source, viewer)
    document = viewer / "investor-dashboard.html"
    b = strict_json(bundle)
    engine = strict_json("var/institutional-return-engines/latest.json")
    if engine["bundle_sha256"] != file_hash(bundle):
        raise ValueError("Current engine evidence required")
    publish_engines(engine["assessment"], engine["robustness"], document)
    evaluation = destination / "dynamic-evaluation"
    # Reuse only fully written, source-matched replays; interrupted runs stay isolated.
    for existing in sorted(
        (root / "runs").glob("*/dynamic-evaluation/assessment.json")
    ):
        assessment = strict_json(existing)
        if (
            assessment["source_hashes"].get(str(bundle)) == file_hash(bundle)
            and all(file_hash(p) == h for p, h in assessment["source_hashes"].items())
            and all(
                file_hash(existing.parent / p) == h
                for p, h in assessment["artifacts"].items()
            )
        ):
            evaluation = existing.parent
            break
    else:
        evaluate(bundle, evaluation)
    prices = eligible_prices(extended_prices(b["capture"], b["benchmark_extension"]))
    checks = {}
    for key, rate in (("0bps", 0.0), ("15bps", 0.0015), ("30bps", 0.003)):
        frame = pd.read_csv(evaluation / (key + ".csv"), index_col=0, parse_dates=True)
        trades = strict_json(evaluation / (key + "-trades.json"))
        targets = {pd.Timestamp(t["fill_session"]): t["weights"] for t in trades}
        independent = replay(
            prices.pct_change(fill_method=None).loc[frame.index],
            targets,
            cost_rate=rate,
        )
        for column in ("equity", "return", "turnover", "cash"):
            if not np.allclose(
                frame[column], independent[column], rtol=1e-9, atol=1e-10
            ):
                raise ValueError("Dynamic independent replay mismatch: " + column)
        checks[key] = dict(
            status="RECONCILED_LOCAL_REPLAY", sessions=len(frame), fills=len(trades)
        )
    atomic_json(
        evaluation / "reconciliation.json",
        dict(
            assessment_sha256=file_hash(evaluation / "assessment.json"),
            replay_code_sha256=file_hash("economic_design_assessment.py"),
            checks=checks,
            release_approved=False,
            independent_human_review=False,
        ),
    )
    publish_dynamic(bundle, evaluation, document)
    payload = read_payload(document)
    payload["latest_market"] = market_payload(prices, [job["market_session"]])[
        job["market_session"]
    ]
    manifest = strict_json(viewer / "artifact-manifest.json")
    render_payload(payload, document)
    seal_dashboard(
        document,
        payload,
        {
            n: {k: v for k, v in entry.items() if k != "sha256"}
            for n, entry in manifest["pdfs"].items()
        },
        manifest.get("main_investor_pdf"),
    )
    # Full application validation includes scenario identities and PDF seals.
    Application(
        document, b["capture"], b["training_report"], destination / "scenario-pdfs"
    )
    receipt = dict(
        document=str(document),
        bundle=str(bundle.resolve()),
        document_sha256=file_hash(document),
        bundle_sha256=file_hash(bundle),
        market_session=job["market_session"],
        execution_enabled=False,
        viewer_identity=viewer_identity,
    )
    atomic_json(previous, receipt)
    return receipt


if __name__ == "__main__":
    print(publish())
