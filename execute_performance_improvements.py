"""Canonical all-workstream execution, including fixed-calendar forecast scoring."""

import argparse
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
import platform

from run_performance_improvements import run as portfolios
from performance_forecast_calendar import run as forecasts
from performance_cost_stress import run as cost_stress
from performance_evidence import run as exports
from strategy_integrity import strict_json, file_hash
from strategy_receipts import atomic_json


def run(bundle, output, *, reuse_portfolio_study=None, cash_returns=None, cash_evidence=None):
    bundle, root = Path(bundle).resolve(), Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    files = [__file__, "performance_forecast_calendar.py", "performance_cost_stress.py",
             "performance_evidence.py"]
    sources = {str(Path(p).resolve()): file_hash(p) for p in files}
    atomic_json(root / "execution-protocol.json", dict(
        source_hashes=sources, bundle_sha256=file_hash(bundle),
        forecast_authority="Fixed calendar, no future-availability origin shifts",
        portfolio_study="Finite eight-design protocol; earlier validation selects variants",
        supplemental_costs="All 32 strategy/design combinations at 0/15/30 bps",
        execution_enabled=False, promotion_enabled=False))
    if reuse_portfolio_study:
        study_path = Path(reuse_portfolio_study).resolve()
        study = strict_json(study_path)
        if cash_returns or cash_evidence:
            raise ValueError("A reused study cannot acquire different cash inputs")
        if (study["status"] != "COMPLETED_RESEARCH_ONLY"
                or study["bundle_sha256"] != file_hash(bundle)
                or any(file_hash(p) != h for p, h in study["source_hashes"].items())):
            raise ValueError("Same-bundle completed source-matched study required")
    else:
        study_path = root / "portfolio-study/assessment.json"
        study = portfolios(bundle, study_path.parent, cash_returns=cash_returns,
                           cash_evidence=cash_evidence)
    fixed_path = root / "forecast-fixed-calendar.json"
    forecast = forecasts(bundle, fixed_path)
    costs = cost_stress(study_path, root / "all-trial-costs", bundle_path=bundle)
    evidence = exports(study_path, root / "exports", forecast_path=fixed_path)
    if any(file_hash(p) != h for p, h in sources.items()):
        raise ValueError("Execution source changed")
    outcome = dict(status="COMPLETED_ALL_AVAILABLE_IMPROVEMENT_EXPERIMENTS",
                   completed_at=datetime.now(timezone.utc).isoformat(),
                   market_session=study["market_session"], bundle_sha256=file_hash(bundle),
                   source_hashes=sources, portfolio_study=str(study_path),
                   portfolio_study_sha256=file_hash(study_path),
                   forecast=dict(path=str(fixed_path), sha256=file_hash(fixed_path),
                                 gate_passed=forecast["candidate_gate_passed"]),
                   portfolio_screens={k: r["historical_screen_passed"]
                                      for k, r in study["portfolios"].items()},
                   cost_stress_status=costs["status"], diagnostic_export_status=evidence["status"],
                   actual_account_cash=study["account_cash"],
                   versions={p: version(p) for p in ["numpy", "pandas", "scipy", "scikit-learn"]},
                   python_version=platform.python_version(),
                   prospective_confirmation_required=True,
                   execution_enabled=False, promotion_enabled=False)
    test = forecast["historical_test"]
    calendar = test["fixed_calendar"]
    lines = ["# Executed performance improvements", "",
             f"Market session: {study['market_session']}. All available experiments completed.", "",
             "## Forecasting", "",
             f"Fixed calendar: {len(calendar)} scheduled origins, {test['outcomes']} scored outcomes. "
             "Unavailable observations never shift forecast origins. This evidence supersedes "
             "the portfolio engine's preliminary availability-adaptive forecast diagnostic.", "",
             f"Validation choice: {forecast['selected_on_validation']}. "
             f"Historical forecasting screen passed: {forecast['candidate_gate_passed']}.", "",
             "| Predictor | Brier | Log loss |", "|---|---:|---:|"]
    for name, row in [("Selected challenger", test["candidate"]), *test["benchmarks"].items()]:
        lines.append(f"| {name} | {row['brier']:.4f} | {row['log_loss']:.4f} |")
    lines += ["", "## Returns and risk", "",
              "Three successive yearly test windows; each choice uses the preceding yearly "
              "validation window. The continuous replay includes changes between selected designs.", "",
              "| Strategy | 15 bps selected / incumbent | 30 bps selected / incumbent | "
              "Historical screen |", "|---|---:|---:|---|"]
    for name, row in study["portfolios"].items():
        a, b = row["costs"]["0.0015"], row["costs"]["0.003"]
        lines.append(f"| {name} | {a['selected']['total_return']:.2%} / "
                     f"{a['incumbent']['total_return']:.2%} | {b['selected']['total_return']:.2%} / "
                     f"{b['incumbent']['total_return']:.2%} | {row['historical_screen_passed']} |")
    lines += ["", "Eight designs × four strategies were also stressed under frozen decisions "
              "at 0, 15 and 30 bps. The original-cost path reconciles and higher costs cannot "
              "artificially improve fixed-decision NAV. Separate capital and risk weight exports "
              "include normal, stress and observed covariance diagnostics.", "",
              "## Evidence boundaries", "",
              f"Actual account cash comparison: {study['account_cash']['status']}.", "",
              "No account cash rate was invented. SGOV is a traded ETF under the same capital "
              "caps and no higher baseline estimated variance. Active strategies and all existing "
              "cohorts are unchanged. Historical screens do not establish prospective superiority; "
              "model and weight promotion remain disabled. Candidate registration timestamps and "
              "current-session checks are retained in the portfolio study. All history was already "
              "available before these designs were proposed.", "",
              "Files: forecast-fixed-calendar.json; all-trial-costs/assessment.json; "
              "exports/regime-reliability.json; exports/capital-and-risk-weights.csv; "
              "exports/group-risk-weights.csv. The complete portfolio study is linked in assessment.json."]
    (root / "report.md").write_text("\n".join(lines) + "\n")
    outcome["artifacts"] = {str(p.relative_to(root)): file_hash(p)
                             for p in root.rglob("*") if p.is_file()}
    atomic_json(root / "assessment.json", outcome)
    atomic_json(root.parent / "execution-latest.json", dict(
        assessment=str(root / "assessment.json"), assessment_sha256=file_hash(root / "assessment.json"),
        status=outcome["status"], execution_enabled=False, promotion_enabled=False))
    print("Complete execution evidence:", root / "report.md", flush=True)
    return outcome


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reuse-portfolio-study", type=Path)
    parser.add_argument("--cash-returns", type=Path)
    parser.add_argument("--cash-evidence", type=Path)
    args = parser.parse_args()
    bundle = args.bundle or Path(strict_json("var/dashboard-live/latest.json")["bundle"])
    run(bundle, args.output, reuse_portfolio_study=args.reuse_portfolio_study,
        cash_returns=args.cash_returns, cash_evidence=args.cash_evidence)
