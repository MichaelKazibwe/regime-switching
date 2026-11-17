"""Private viewer boundaries: archives retain identity and cannot become orders."""

import base64
from copy import deepcopy
import hashlib
import json
import re

import numpy as np
import pandas as pd
import pytest

from investor_dashboard import (
    build_from_saved,
    display_plan,
    market_payload,
    render_dashboard,
)


def saved_plan():
    return {
        "recommendation_id": "saved-test",
        "mandate": {
            "client_id": "PRIVATE-IDENTITY",
            "profile": "balanced",
            "base_currency": "USD",
            "account_value": 100000,
            "horizon_years": 1,
            "drawdown_preference": 0.2,
        },
        "price_session": "2025-10-29",
        "as_of": "2025-10-29T21:00:00+00:00",
        "historical_preview": True,
        "release": {
            "release_id": "old-release",
            "private_review_evidence": "PRIVATE-EVIDENCE",
        },
        "allocation": {"weights": None, "status": "BLOCKED_CONSTRAINTS"},
        "qualification": {
            "status": "OPERATOR_PREVIEW_ONLY",
            "checks": {"legal_scope": "BLOCKED"},
            "client_reasons": [],
            "public_recommendations_enabled": False,
        },
        "risk_state": {},
        "simulations": None,
        "limitations": ["Past observations do not guarantee returns."],
    }


def payload(path):
    html = path.read_text()
    return json.loads(
        re.search(
            r'<script id="investor-data" type="application/json">(.*?)</script>',
            html,
            re.S,
        )[1]
    )


def test_dashboard_preserves_archive_status_omits_private_identity_and_is_self_contained(
    tmp_path,
):
    result = saved_plan()
    before = deepcopy(result)
    destination = tmp_path / "index.html"
    render_dashboard([result], destination)
    assert result == before
    html = destination.read_text()
    data = payload(destination)
    assert data["plans"][0]["release_id"] == "old-release"
    assert data["plans"][0]["qualification"]["status"] == "OPERATOR_PREVIEW_ONLY"
    assert "PRIVATE-IDENTITY" not in html and "PRIVATE-EVIDENCE" not in html
    assert "<canvas" in html and 'src="https://' not in html and 'href="https://' not in html and "http://" not in html
    assert not re.search(r"<script[^>]+src=", html)
    script = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    assert f"'sha256-{digest}'" in html
    assert destination.stat().st_mode & 0o777 == 0o600
    assert len(data["catalogue"]) == len(__import__("investmentcatalog").catalogue())


def test_untrusted_text_cannot_close_data_script(tmp_path):
    result = saved_plan()
    result["limitations"] = ["</script><script>alert(1)</script>"]
    destination = tmp_path / "index.html"
    render_dashboard([result], destination)
    assert payload(destination)["plans"][0]["limitations"] == result["limitations"]
    assert "<script>alert(1)</script>" not in destination.read_text()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True])
def test_invalid_fan_rejected(value):
    result = saved_plan()
    line = [1.0] * 252
    line[0] = value
    result["simulations"] = {
        "years": 1,
        "fan": {"proposed": [line] * 3, "strategic_reference": [[1.0] * 252] * 3},
    }
    with pytest.raises(ValueError):
        display_plan(result)


def test_mismatched_horizon_rejected():
    result = saved_plan()
    result["simulations"] = {
        "years": 2,
        "fan": {
            "proposed": [[1.0] * 252] * 3,
            "strategic_reference": [[1.0] * 252] * 3,
        },
    }
    with pytest.raises(ValueError):
        display_plan(result)


def test_market_snapshot_uses_no_future_prices_or_forward_fill():
    prices = pd.DataFrame(
        {"SPY": [100, np.nan, 10000], "TIP": [10, 11, 100]},
        index=pd.to_datetime(["2025-10-28", "2025-10-29", "2025-10-30"]),
    )
    snapshot = market_payload(prices, {"2025-10-29"})["2025-10-29"]["instruments"]
    assert snapshot["SPY"] == {"close": None, "history": [["2025-10-28", 100.0]], "currency": "USD"}
    assert snapshot["TIP"]["close"] == 11
    assert snapshot["ALLW"] == {"close": None, "history": [], "currency": "USD"}


def test_manifest_cannot_read_another_client_folder(tmp_path):
    root = tmp_path / "reports"
    root.mkdir()
    (root / "demo-manifest.json").write_text(
        json.dumps(
            {"reports": [{"report": str(tmp_path / "another-client" / "index.html")}]}
        )
    )
    with pytest.raises(ValueError, match="inside"):
        build_from_saved(root, tmp_path / "viewer.html")


def test_single_saved_plan_and_multiple_examples_preserve_original_goal(tmp_path):
    root = tmp_path / "reports"
    root.mkdir()
    r = saved_plan()
    (root / "recommendation.json").write_text(json.dumps(r))
    build_from_saved(root, tmp_path / "single.html")
    assert len(payload(tmp_path / "single.html")["plans"]) == 1
    manifest = []
    for name in ["balanced", "original_goal"]:
        folder = root / name
        folder.mkdir()
        r = saved_plan()
        if name == "original_goal":
            r["mandate"]["target_total_return"] = 0.5
            r["mandate"]["profile"] = "preservation"
        (folder / "recommendation.json").write_text(json.dumps(r))
        manifest.append({"report": str(folder / "index.html")})
    (root / "demo-manifest.json").write_text(json.dumps({"reports": manifest}))
    summary = build_from_saved(root, tmp_path / "multiple.html")
    assert summary["plans"] == 2
    assert payload(tmp_path / "multiple.html")["plans"][1]["title"] == "Original goal"


def test_local_viewer_serves_only_named_pdf_and_dashboard_paths(tmp_path):
    from io import BytesIO
    from types import SimpleNamespace
    from investor_dashboard import viewer_handler

    document = tmp_path / "index.html"
    document.write_text("private dashboard")
    pdf = tmp_path / "investor-report-0.pdf"
    pdf.write_bytes(b"%PDF-private")
    handler = object.__new__(viewer_handler(document))
    handler.server = SimpleNamespace(server_port=8768)
    handler.headers = {"Host": "127.0.0.1:8768"}
    codes = []
    handler.send_response = codes.append
    handler.send_error = codes.append
    handler.send_header = lambda *args: None
    handler.end_headers = lambda: None
    handler.wfile = BytesIO()
    handler.path = "/investor-report-0.pdf"
    handler.do_GET()
    assert codes == [200] and handler.wfile.getvalue() == pdf.read_bytes()
    handler.path = "/recommendation.json"
    handler.do_GET()
    assert codes[-1] == 404
    handler.path = "/../investor-report-0.pdf"
    handler.do_GET()
    assert codes[-1] == 404
    handler.path = "/"
    handler.headers = {"Host": "untrusted.example"}
    handler.do_GET()
    assert codes[-1] == 403
