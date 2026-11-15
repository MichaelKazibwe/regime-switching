"""Private integrated investor dashboard, rendered from saved plans.

This viewer never recalculates allocations, grants approval or submits orders.
"""

from __future__ import annotations

import argparse
import base64
from datetime import date
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

from investmentcatalog import catalogue_payload

ASSETS = Path(__file__).resolve().parent / "dashboard"


def display_plan(result):
    """Expose only dashboard fields, omitting client identity and raw evidence."""
    m = result["mandate"]
    date.fromisoformat(result["price_session"])
    simulation = result.get("simulations")
    if simulation:
        for name in ("proposed", "strategic_reference"):
            fan = simulation["fan"][name]
            if (
                len(fan) != 3
                or len({len(line) for line in fan}) != 1
                or len(fan[0]) != simulation["years"] * 252
            ):
                raise ValueError("Scenario fan does not match its declared horizon")
            for line in fan:
                if any(
                    not isinstance(v, (int, float))
                    or isinstance(v, bool)
                    or not 0 <= v < 1e100
                    for v in line
                ):
                    raise ValueError("Invalid scenario wealth values")
    title = (
        "Original goal"
        if m.get("target_total_return") is not None
        else m["profile"].title()
    )
    return {
        "id": result["recommendation_id"],
        "title": title,
        "profile": m["profile"],
        "mandate": {
            k: m.get(k)
            for k in (
                "base_currency",
                "account_value",
                "horizon_years",
                "drawdown_preference",
                "financial_loss_capacity",
                "target_total_return",
                "near_term_liquidity",
            )
        },
        "price_session": result["price_session"],
        "as_of": result["as_of"],
        "historical_preview": result["historical_preview"],
        "release_id": result["release"]["release_id"],
        "allocation": result["allocation"],
        "qualification": {
            k: result["qualification"].get(k)
            for k in (
                "status",
                "checks",
                "client_reasons",
                "public_recommendations_enabled",
            )
        },
        "hard_blocks": result.get("hard_blocks", []),
        "excluded_instruments": result.get("excluded_instruments", {}),
        "risk": {
            k: result["risk_state"].get(k)
            for k in ("peak", "exposure_multiplier", "review_required", "prior_breach")
        },
        "simulations": simulation,
        "limitations": result.get("limitations", []),
    }


def market_payload(prices, sessions):
    """Actual adjusted prices up to each plan date, with no forward filling."""
    import numpy as np
    import pandas as pd

    if (
        not isinstance(prices.index, pd.DatetimeIndex)
        or prices.index.tz is not None
        or not prices.index.is_unique
        or not prices.index.is_monotonic_increasing
    ):
        raise ValueError("Ordered unique market session dates required")
    data = {}
    for session in sessions:
        stamp = pd.Timestamp(session)
        history = prices.loc[prices.index <= stamp].tail(252)
        instruments = {}
        for item in catalogue_payload():
            symbol = item["symbol"]
            points = []
            if symbol in history:
                for d, value in history[symbol].items():
                    if np.isfinite(value) and value > 0:
                        points.append([str(d.date()), float(value)])
            close = points[-1][1] if points and points[-1][0] == session else None
            instruments[symbol] = {"close": close, "history": points}
        data[session] = {
            "session": session,
            "kind": "HISTORICAL_ADJUSTED_CLOSE_NOT_EXECUTABLE_QUOTES",
            "instruments": instruments,
        }
    return data


def render_dashboard(
    results, destination, *, market=None, context=None, pdf_links=None
):
    if not results:
        raise ValueError("At least one saved recommendation is required")
    plans = [display_plan(result) for result in results]
    payload = {
        "plans": plans,
        "catalogue": catalogue_payload(),
        "market": market or {},
        "viewer_version": 2,
        "context": context or {},
        "core_symbols": __import__("assetuniverse").DIVERSIFIED_ASSETS,
        "pdf_links": pdf_links or {},
    }
    render_payload(payload, destination)


def render_payload(payload, destination):
    """Render only local data with hashed scripts; no financial recomputation."""
    from productreport import private_write

    encoded = (
        json.dumps(payload, allow_nan=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    script = (ASSETS / "investor.js").read_text()
    style = (ASSETS / "investor.css").read_text()
    template = (ASSETS / "investor.html").read_text()
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    document = (
        template.replace("__SCRIPT_HASH__", digest)
        .replace("__STYLE__", style)
        .replace("__SCRIPT__", script)
        .replace("__DATA__", encoded)
    )
    private_write(destination, document)


def build_from_saved(
    root,
    destination,
    *,
    prices=None,
    features_path=None,
    forecasts_path=None,
    research_allocation_path=None,
    pdf=False,
    latest_features_path=None,
):
    """Read this root's own explicit demo manifest; never crawl client folders."""
    root = Path(root).resolve()
    if (root / "demo-manifest.json").is_file():
        manifest = json.loads((root / "demo-manifest.json").read_text())
        paths = []
        for record in manifest["reports"]:
            report = Path(record["report"])
            report = report if report.is_absolute() else root / report
            raw_source = report.parent / "recommendation.json"
            source = raw_source.resolve()
            if not source.is_relative_to(root) or raw_source.is_symlink():
                raise ValueError(
                    "Dashboard plans must stay inside the supplied private report root"
                )
            paths.append(source)
    else:
        paths = [root / "recommendation.json"]
    results = [json.loads(path.read_text()) for path in paths]
    market = (
        market_payload(prices, {r["price_session"] for r in results})
        if prices is not None
        else None
    )
    from investor_analytics import build_context

    context = build_context(
        results,
        prices=prices,
        features_path=features_path,
        forecasts_path=forecasts_path,
        research_allocation_path=research_allocation_path,
        latest_features_path=latest_features_path,
    )
    pdf_links = {}
    if pdf:
        from investor_pdf import render_investor_pdf

        for index, result in enumerate(results):
            name = f"investor-report-{index}.pdf"
            render_investor_pdf(result, context, Path(destination).parent / name)
            pdf_links[result["recommendation_id"]] = name
    render_dashboard(
        results, destination, market=market, context=context, pdf_links=pdf_links
    )
    return {
        "dashboard": str(Path(destination).resolve()),
        "plans": len(results),
        "market_snapshot_included": market is not None,
        "mode": "SAVED_PLAN_VIEWER_NO_ORDERS_NO_REAPPROVAL",
    }


def attach_training_report(
    existing, training_path, destination, *, allocation_lab=None
):
    """Preserve saved client plans/contexts and attach a separate validated lab."""
    from html.parser import HTMLParser
    from strategy_report import load_training_report

    class Payload(HTMLParser):
        def __init__(self):
            super().__init__()
            self.inside = False
            self.parts = []
            self.count = 0

        def handle_starttag(self, tag, attrs):
            if tag == "script" and dict(attrs).get("id") == "investor-data":
                self.inside = True
                self.count += 1

        def handle_endtag(self, tag):
            if tag == "script":
                self.inside = False

        def handle_data(self, value):
            if self.inside:
                self.parts.append(value)

    parser = Payload()
    parser.feed(Path(existing).read_text())
    if parser.count != 1:
        raise ValueError("Exactly one saved investor payload required")
    payload = json.loads("".join(parser.parts))
    payload["training"] = load_training_report(training_path)
    if allocation_lab is not None:
        payload["allocation_lab"] = allocation_lab
    payload["viewer_version"] = 3
    render_payload(payload, destination)
    return {
        "dashboard": str(Path(destination).resolve()),
        "training_run": payload["training"]["run_id"],
        "plans_unchanged": True,
    }


def viewer_handler(document):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_GET(self):
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            if (
                host
                not in {
                    f"localhost:{self.server.server_port}",
                    f"127.0.0.1:{self.server.server_port}",
                }
                or origin
                and origin != f"http://{host}"
            ):
                self.send_error(403)
                return
            import re

            target = Path(document)
            if re.fullmatch(r"/investor-report-[0-9]+\.pdf", self.path):
                candidate = target.parent / self.path[1:]
                if not candidate.is_file() or candidate.is_symlink():
                    self.send_error(404)
                    return
                target = candidate
            elif self.path not in ("/", "/index.html"):
                self.send_error(404)
                return
            body = target.read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/pdf"
                if target.suffix == ".pdf"
                else "text/html; charset=utf-8",
            )
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, default=Path("var/product-preview"))
    parser.add_argument("--prices", type=Path)
    parser.add_argument("--macro-features", type=Path)
    parser.add_argument(
        "--latest-macro-features",
        type=Path,
        help="Separate current/revised FRED overlay; never replaces plan-time data",
    )
    parser.add_argument("--macro-forecasts", type=Path)
    parser.add_argument("--research-allocation", type=Path)
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Create private per-plan PDF reports alongside the dashboard",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("var/investor-dashboard/index.html")
    )
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Invalid port")
    if args.prices:
        import pandas as pd

        prices = pd.read_csv(args.prices, index_col=0, parse_dates=True)
    else:
        prices = None
    print(
        json.dumps(
            build_from_saved(
                args.reports,
                args.output,
                prices=prices,
                features_path=args.macro_features,
                forecasts_path=args.macro_forecasts,
                research_allocation_path=args.research_allocation,
                pdf=args.pdf,
                latest_features_path=args.latest_macro_features,
            ),
            indent=2,
        ),
        flush=True,
    )
    if args.serve:
        server = ThreadingHTTPServer(
            ("127.0.0.1", args.port), viewer_handler(args.output)
        )
        print(f"Local dashboard: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
