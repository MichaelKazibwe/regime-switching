"""Execute P0/P1 in isolated shadow artifacts, with missing evidence blocked."""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from economic_evidence import verify, portfolio_review
from institutionalportfolio import calibrated_covariance
from macro_availability_diagnosis import diagnose
from shadow_challenger_experiment import experiment, VARIANTS
from stress_budget_challenger import allocate
from stress_challenger_ledger import advance
from strategy_integrity import strict_json, file_hash
from strategy_receipts import atomic_json
from strategy_report import load_training_report
from prospective_strategy_ledger import summary
from strategy_healthcheck import health

CONFIG = Path("research/stress_budget_challenger_v3.json")
POLICY_SOURCES = [
    "stress_budget_challenger.py",
    "run_economic_p0_p1.py",
    "shadow_challenger_experiment.py",
    "macro_availability_diagnosis.py",
    "stress_challenger_ledger.py",
    "economic_evidence.py",
    "institutionalportfolio.py",
    "goalportfolio.py",
    "compare_portfolio_models.py",
    "productallocation.py",
    str(CONFIG),
]


def execute(
    bundle, output, *, evidence_root=None, run_experiments=True, register=False
):
    source_hashes = {n: file_hash(n) for n in POLICY_SOURCES}
    b = strict_json(bundle)
    report = load_training_report(b["training_report"])
    if not report["current_numerical_source_match"]:
        raise ValueError("Current source-matched report required")
    capture = strict_json(b["capture"])
    base = Path(b["capture"]).parent
    if file_hash(b["capture"]) != report["capture_sha256"]:
        raise ValueError("Capture/report mismatch")
    for name, h in capture["files"].items():
        if Path(name).name != name or file_hash(base / name) != h:
            raise ValueError("Capture artifact mismatch")
    prices = pd.read_csv(base / "prices.csv", index_col=0, parse_dates=True)
    features = strict_json(Path(b["training_report"]).parent / "features.json")
    indexed = {r["date"]: r for r in features}
    cfg = strict_json(CONFIG)
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    symbols = [s for s in prices if s != "ALLW"]
    history = prices[symbols].pct_change(fill_method=None).tail(252)
    dates = pd.DatetimeIndex(
        pd.read_csv(
            Path(b["training_report"]).parent / "economic_balance.csv",
            index_col=0,
            parse_dates=True,
        ).index
    )
    evidence = verify(evidence_root, symbols, dates)
    diagnosis = diagnose(
        capture["macro_manifest"],
        features,
        report["evaluation"]["start"],
        report["evaluation"]["end"],
    )
    atomic_json(out / "evidence-gates.json", evidence)
    atomic_json(out / "macro-availability.json", diagnosis)
    cov = calibrated_covariance(history)[0]
    proposal = allocate(history, cov, cfg, macro_valid=report["latest_macro_available"])
    atomic_json(out / "current-shadow-proposal.json", proposal)
    exposures = portfolio_review(proposal["weights"], cfg, evidence, evidence_root)
    results = (
        experiment(
            prices,
            indexed,
            report["evaluation"]["start"],
            report["evaluation"]["end"],
            cfg,
            out / "comparisons",
        )
        if run_experiments
        else []
    )
    before = summary("var/strategy-operations-v2/prospective.sqlite3")
    legacy_hash = file_hash("var/strategy-operations-v2/prospective.sqlite3")
    registrations = []
    if register:
        from scheduled_strategy_validation import run

        # Existing observation is idempotently validated/skipped, not rewritten.
        continuation = run("var/strategy-operations-integrated-v1", refresh=True)
        source = {
            "capture_sha256": file_hash(b["capture"]),
            "report_sha256": file_hash(b["training_report"]),
            "policy_sources": source_hashes,
        }
        for variant in VARIANTS:
            registrations.append(
                advance(
                    Path("var/economic-shadow-cohorts")
                    / cfg["version"]
                    / variant[0]
                    / "ledger.sqlite3",
                    prices,
                    indexed.get(report["market_session"]),
                    history,
                    cov,
                    cfg,
                    variant,
                    source,
                )
            )
    else:
        continuation = {"status": "NOT_REQUESTED"}
    after = summary("var/strategy-operations-v2/prospective.sqlite3")
    if (
        before != after
        or file_hash("var/strategy-operations-v2/prospective.sqlite3") != legacy_hash
    ):
        raise ValueError("Existing prospective evidence changed")
    if any(file_hash(n) != h for n, h in source_hashes.items()):
        raise ValueError("Challenger policy changed during execution")
    result = {
        "schema_version": 1,
        "status": "P0_P1_LOCAL_IMPLEMENTATION_WITH_EVIDENCE_GATES_BLOCKED",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market_session": report["market_session"],
        "evidence_gates": evidence,
        "aggregate_exposure_review": exposures,
        "diagnosed_rejections": diagnosis["rejected_sessions"],
        "issue_classifications": diagnosis["issue_classifications"],
        "shadow_candidate": proposal,
        "predeclared_comparisons": results,
        "candidate_cohorts": registrations,
        "existing_cohort_continuation": continuation,
        "existing_prospective_summary": after,
        "existing_prospective_health": health("var/strategy-operations-v2"),
        "source_hashes": source_hashes,
        "config_sha256": file_hash(CONFIG),
        "training_report_sha256": file_hash(b["training_report"]),
        "recovery_status": "REVIEW_REQUIRED_NO_APPROVAL_OR_AUTOMATIC_UNLOCK",
        "economic_approval": False,
        "execution_enabled": False,
        "public_release_approved": False,
        "limitations": [
            "No actual cash, broker or fund exposure evidence was supplied; user explicitly retained those blockers.",
            "Hypothetical ETF shocks and capital proxies do not establish actual duration/DV01/FX or guaranteed drawdown caps.",
            "Current proposal is independently solved, not the earlier illustrative scaled portfolio. Statistical budgets/return priors remain unvalidated.",
            "Backtests reuse a retrospectively designed evaluation window; they are exploratory comparisons, not untouched validation.",
            "Market-only fallback is isolated and predeclared, not a missing macro value, vintage substitution or change to the original strict policy.",
            "No future observation or approved recovery was manufactured. Host scheduling and external alert delivery remain unqualified.",
        ],
    }
    result["artifacts"] = {
        str(p.relative_to(out)): file_hash(p) for p in out.rglob("*") if p.is_file()
    }
    atomic_json(out / "p0-p1-results.json", result)
    atomic_json(
        "var/economic-shadow/latest.json",
        {
            "report": str(out / "p0-p1-results.json"),
            "sha256": file_hash(out / "p0-p1-results.json"),
            "approval": False,
        },
    )
    print("P0/P1 results:", out / "p0-p1-results.json", flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle",
        type=Path,
        default=Path("var/investor-dashboard/latest-strategy-run.json"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--skip-experiments", action="store_true")
    parser.add_argument("--register-shadow", action="store_true")
    args = parser.parse_args()
    execute(
        args.bundle,
        args.output
        or Path("var/economic-shadow")
        / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"),
        evidence_root=args.evidence_root,
        run_experiments=not args.skip_experiments,
        register=args.register_shadow,
    )
