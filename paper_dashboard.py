"""Render the interactive, self-contained paper portfolio dashboard."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
import math
import re
from pathlib import Path
from typing import Any

from assetuniverse import PRODUCTION_ASSETS

ASSET_NAMES = {
    "SPY": ("S&P 500", "US equity"), "QQQ": ("Nasdaq 100", "US equity"),
    "IWM": ("Russell 2000", "US equity"), "VEA": ("Developed markets", "Global equity"),
    "VWO": ("Emerging markets", "Global equity"), "TLT": ("20+ year Treasury", "Fixed income"),
    "IEF": ("7–10 year Treasury", "Fixed income"), "SHY": ("1–3 year Treasury", "Fixed income"),
    "LQD": ("Investment grade bonds", "Credit"), "HYG": ("High yield bonds", "Credit"),
    "GLD": ("Gold", "Real assets"), "SLV": ("Silver", "Real assets"),
    "DBC": ("Broad commodities", "Real assets"), "VNQ": ("US real estate", "Real assets"),
}
ASSETS_DIRECTORY = Path(__file__).resolve().parent / "dashboard"


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def dashboard_state(reports: list[dict[str, Any]]) -> dict:
    valid = []
    metric_fields = (
        "portfolio_value", "cash", "cumulative_return_since_start", "active_return_since_start",
        "maximum_drawdown_since_start", "cumulative_turnover", "cumulative_transaction_costs",
        "benchmark", "benchmark_return_since_first_observation", "valuation_observations", "data_as_of",
    )
    for item in reports:
        if not isinstance(item, dict):
            continue
        decision = item.get("decision") or {}
        execution = decision.get("paper_execution") or {}
        metrics = execution.get("operator_metrics") or {}
        view = {key: item.get(key) for key in ("cycle_id", "status", "data_as_of", "updated_at")}
        public_metrics = {key: metrics.get(key) for key in metric_fields}
        public_metrics["positions_by_market_value"] = {
            symbol: {key: position.get(key) for key in ("shares", "market_value", "weight")}
            for symbol, position in (metrics.get("positions_by_market_value") or {}).items()
            if isinstance(position, dict)
        }
        view["decision"] = {"regime": decision.get("regime"), "paper_execution": {
            "status": execution.get("status"), "operator_metrics": public_metrics,
        }}
        valid.append(view)
    ordered = sorted(valid, key=lambda item: str(item.get("data_as_of") or item.get("updated_at") or item.get("cycle_id", "")), reverse=True)
    return _json_safe({"reports": ordered, "generated_at": datetime.now(timezone.utc).isoformat(),
                       "assets": [{"symbol": symbol, "name": ASSET_NAMES[symbol][0], "group": ASSET_NAMES[symbol][1]}
                                  for symbol in PRODUCTION_ASSETS]})


def script_source() -> str:
    return (ASSETS_DIRECTORY / "dashboard.js").read_text(encoding="utf-8")


def _number(value: Any, percent: bool = False) -> str:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(parsed):
        return "—"
    if percent:
        return f"{parsed:.2%}"
    return f"{parsed:,.2f}"


def load_reports(directory: Path, limit: int) -> list[dict[str, Any]]:
    reports = []
    for path in sorted(directory.glob("*.json"), reverse=True)[:limit]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            continue
        if (isinstance(payload, dict) and isinstance(payload.get("decision", {}), dict)
                and isinstance(payload.get("decision", {}).get("paper_execution") or {}, dict)
                and isinstance((payload.get("decision", {}).get("paper_execution") or {}).get("operator_metrics") or {}, dict)):
            reports.append(payload)
    return reports


def render_dashboard(reports: list[dict[str, Any]]) -> str:
    """Render report evidence plus interactive charts; never fabricate portfolio data."""
    rows = []
    for report in reports:
        decision = report.get("decision", {})
        execution = decision.get("paper_execution") or {}
        metrics = execution.get("operator_metrics") or {}
        row_values = (
            report.get("cycle_id"),
            report.get("status"),
            report.get("data_as_of"),
            decision.get("regime"),
            _number(metrics.get("portfolio_value")),
            _number(metrics.get("cash")),
            _number(metrics.get("cumulative_return_since_start"), percent=True),
            _number(metrics.get("active_return_since_start"), percent=True),
            _number(metrics.get("maximum_drawdown_since_start"), percent=True),
            _number(metrics.get("cumulative_turnover")),
            _number(metrics.get("cumulative_transaction_costs")),
        )
        rows.append(
            "<tr>" + "".join(f"<td>{html.escape(str(value or '—'))}</td>" for value in row_values) + "</tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="11">No valid paper cycle reports found.</td></tr>')
    data = json.dumps(dashboard_state(reports), allow_nan=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = (ASSETS_DIRECTORY / "index.html").read_text(encoding="utf-8")
    replacements = {
        "__DASHBOARD_STYLE__": (ASSETS_DIRECTORY / "dashboard.css").read_text(encoding="utf-8"),
        "__DASHBOARD_SCRIPT__": script_source(), "__FALLBACK_ROWS__": "".join(rows),
        "__DASHBOARD_DATA__": data,
    }
    return re.sub("|".join(replacements), lambda match: replacements[match.group()], template)


def write_dashboard(reports_directory: str | Path, output_path: str | Path) -> Path:
    """Atomically refresh a static dashboard from persisted cycle reports."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    rendered = render_dashboard(load_reports(Path(reports_directory), 365))
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(output)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", default="var/paper-reports")
    parser.add_argument("--output", default="var/paper-dashboard.html")
    parser.add_argument("--limit", type=int, default=365)
    args = parser.parse_args(argv)
    if args.limit <= 0:
        parser.error("--limit must be positive")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_dashboard(load_reports(Path(args.reports), args.limit)), encoding="utf-8")
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
