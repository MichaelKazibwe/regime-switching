"""Exercise the authenticated loopback viewer without touching saved client plans."""

import json
from pathlib import Path
import re
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def verify():
    log = Path("var/dashboard-service/manual.log").read_text()
    token = re.findall(r"8770/#([a-f0-9]{64})", log)[-1]
    base = "http://127.0.0.1:8770"

    def request(path, body=None, authenticated=True):
        headers = {"Authorization": "Bearer " + token} if authenticated else {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = Request(
            base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
        )
        with urlopen(req, timeout=120) as response:
            return response.read()

    try:
        request("/api/dashboard", authenticated=False)
        raise AssertionError("Unauthenticated access accepted")
    except HTTPError as error:
        assert error.code == 401
    data = json.loads(request("/api/dashboard"))
    status = json.loads(request("/api/dashboard-status"))
    session = status["market_session"]
    assert not status["stale"] and status["error"] is None
    assert data["latest_market"]["session"] == session
    assert len(data["latest_market"]["instruments"]) == 28
    assert data["growth_resilience"]["end"] == session
    assert data["return_engines"]["assessment"]["market_session"] == session
    assert data["dynamic_portfolio"]["snapshot"]["decision_session"] == session
    runtime = json.loads(request("/api/observations"))
    assert runtime["prospective"]["last_session"] == session
    assert all(c["last_session"] == session for c in runtime["cohorts"].values())
    pdf_count = 0
    for key in data["pdf_links"]:
        assert request("/api/portfolio-pdf", dict(profile_id=key)).startswith(b"%PDF-")
        pdf_count += 1
    saved = data["allocation_lab"]["results"]["economic_balance"]["latest_model"]
    assert request("/api/scenario-pdf", dict(result_id=saved["result_id"])).startswith(
        b"%PDF-"
    )
    from smartregimeportfolio import REGIMES

    custom = json.loads(
        request(
            "/api/reallocate",
            dict(
                strategy="economic_balance",
                forecast_weights={r: 0.25 for r in REGIMES},
                quarters=1,
                mode="user_scenario",
            ),
        )
    )
    assert abs(sum(custom["weights"].values()) + custom["cash"] - 1) < 1e-8
    assert request("/api/scenario-pdf", dict(result_id=custom["result_id"])).startswith(
        b"%PDF-"
    )
    try:
        request(
            "/api/reallocate",
            dict(
                strategy="economic_balance", forecast_weights={r: -1 for r in REGIMES}
            ),
        )
        raise AssertionError("Negative macro input accepted")
    except HTTPError as error:
        assert error.code == 400
    news = json.loads(request("/api/news"))
    assert news["status"] in {
        "LIVE_HEADLINES",
        "AGED_HEADLINES",
        "UNAVAILABLE",
        "CACHED_AFTER_REFRESH_FAILURE",
    }
    result = dict(
        status="PASSED",
        market_session=session,
        portfolio_pdfs=pdf_count,
        scenario_pdf=True,
        authentication=True,
        news_status=news["status"],
        all_cohorts_current=True,
        custom_scenario=True,
        invalid_macro_rejected=True,
    )
    Path("var/dashboard-verification/latest.json").write_text(
        json.dumps(result, indent=2)
    )
    return result


if __name__ == "__main__":
    print(verify())
