"""Authenticated backend acceptance; no broker, client account or email actions."""

import argparse
from datetime import datetime, timezone
import getpass
from http.cookiejar import CookieJar
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor

from strategy_receipts import atomic_json


def verify(origin, username, password, *, allow_stale=False):
    origin = origin.rstrip("/")
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    csrf = None
    checks = {}
    def request(path, body=None, expected=200, authenticated=True):
        headers = {"Origin": origin}
        if body is not None:
            headers["Content-Type"] = "application/json"
            if csrf and authenticated:
                headers["X-CSRF-Token"] = csrf
        client = opener if authenticated else build_opener()
        try:
            response = client.open(Request(origin + path, data=None if body is None else json.dumps(body).encode(),
                                           headers=headers), timeout=120)
        except HTTPError as error:
            response = error
        status, raw = response.code, response.read()
        if status != expected:
            raise AssertionError(f"Unexpected status for {path}: {status}; expected {expected}")
        return raw
    request("/api/dashboard", expected=401, authenticated=False)
    request("/healthz", authenticated=False)
    checks["anonymous_financial_access_denied"] = True
    login = json.loads(request("/api/login", dict(username=username, password=password)))
    if login["next"] == "/password":
        raise ValueError("Complete the required password change in the browser first")
    session = json.loads(request("/api/session"))
    csrf = session["csrf"]
    checks["individual_session"] = True
    payload = json.loads(request("/api/dashboard"))
    for key in ["plans", "training", "allocation_lab", "growth_resilience", "dynamic_portfolio",
                "return_engines", "latest_market", "context", "catalogue"]:
        if key not in payload:
            raise AssertionError("Required dashboard module unavailable: " + key)
    checks["all_dashboard_modules"] = True
    status = json.loads(request("/api/dashboard-status"))
    checks["current_completed_session"] = not status["stale"] and status["error"] is None
    request("/api/observations")
    news = json.loads(request("/api/news"))
    checks["news_has_disclosed_status"] = "status" in news
    benchmark = json.loads(request("/api/benchmark"))
    checks["cycle_benchmark_installed"] = benchmark.get("status") == "RESEARCH_BENCHMARK"
    if payload.get("pdf_links"):
        key = next(iter(payload["pdf_links"]))
        checks["saved_pdf_export"] = request("/api/portfolio-pdf", dict(profile_id=key)).startswith(b"%PDF-")
    if session["role"] == "tester" and checks["current_completed_session"]:
        result = json.loads(request("/api/reallocate", dict(
            strategy="economic_balance", forecast_weights={r: .25 for r in payload["allocation_lab"]["regimes"]},
            quarters=1, mode="user_scenario")))
        if result.get("weights") is not None:
            checks["scenario_capital_reconciles"] = abs(sum(result["weights"].values()) + result["cash"] - 1) < 1e-8
            checks["scenario_pdf_export"] = request("/api/scenario-pdf", dict(result_id=result["result_id"])).startswith(b"%PDF-")
    elif session["role"] == "viewer":
        request("/api/reallocate", {}, expected=403)
        checks["viewer_cannot_calculate"] = True
    request("/api/orders", {}, expected=404)
    checks["no_order_routes"] = True
    request("/api/logout", {})
    request("/api/dashboard", expected=401)
    checks["logout_revokes_session"] = True
    engineering = all(v for k, v in checks.items() if k != "current_completed_session")
    return dict(checked_at=datetime.now(timezone.utc).isoformat(), checks=checks,
                software_passed=engineering, data_current=checks["current_completed_session"],
                ready_for_private_pilot=engineering and checks["current_completed_session"],
                archive_test_only=bool(allow_stale and not checks["current_completed_session"]),
                execution_enabled=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-stale-for-ui-test", action="store_true")
    args = parser.parse_args()
    result = verify(args.origin, args.username, getpass.getpass("Pilot password: "),
                    allow_stale=args.allow_stale_for_ui_test)
    atomic_json(args.output, result)
    print(json.dumps({k: result[k] for k in ["software_passed", "data_current", "ready_for_private_pilot"]}))
    raise SystemExit(0 if result["software_passed"] and (result["data_current"] or args.allow_stale_for_ui_test) else 2)
