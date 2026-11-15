from dataclasses import asdict
import io
import hashlib
import json
from types import SimpleNamespace

import pytest

from clientmandate import CashRate
from productaudit import archive, archival_arguments, replay
from productallocation import PlanningCosts
from productrelease import release_manifest
from recommendation_api import OperatorApplication, make_handler
from recommendationservice import recommend
from test_investment_product import STAMP, mandate, prices


def handler(headers=None, path="/health", body=b"{}"):
    application = SimpleNamespace(plan=lambda body: {"kind": "preview", "input": body})
    cls = make_handler(application, "a" * 40)
    obj = object.__new__(cls)
    obj.headers = {
        "Host": "localhost:8767",
        "Authorization": "Bearer " + "a" * 40,
        **(headers or {}),
    }
    obj.server = SimpleNamespace(server_port=8767)
    obj.path = path
    obj.rfile = io.BytesIO(body)
    results = []
    obj.send_json = lambda data, status=200: results.append((status, data))
    return obj, results


def test_operator_api_authenticates_before_reading_private_requests():
    obj, result = handler({"Authorization": "invalid"}, path="/v1/plan")
    obj.rfile = SimpleNamespace(
        read=lambda length: pytest.fail("Unauthorized body read")
    )
    obj.do_POST()
    assert result[0][0] == 401
    obj, result = handler({"Authorization": "é" * 40})
    obj.do_GET()
    assert result[0][0] == 401


@pytest.mark.parametrize(
    "headers", [{"Host": "evil.example:8767"}, {"Origin": "https://evil.example"}]
)
def test_operator_api_blocks_rebinding_and_cross_origin(headers):
    obj, result = handler(headers)
    obj.do_GET()
    assert result[0][0] == 403


def test_operator_api_bounds_json_and_never_exposes_broker_routes():
    obj, result = handler(
        {"Content-Type": "application/json", "Content-Length": "999999"},
        path="/v1/plan",
    )
    obj.do_POST()
    assert result[0][0] == 400
    obj, result = handler(path="/orders")
    obj.do_GET()
    assert result[0][0] == 404
    obj, result = handler()
    obj.do_GET()
    assert result[0][1]["broker_submission_enabled"] is False
    with pytest.raises(ValueError):
        make_handler(None, "short")


def test_exact_snapshot_replay_and_tamper_detection(tmp_path):
    m = mandate("preservation", drawdown_preference=0.05, financial_loss_capacity=0.05)
    p = prices()
    rate = CashRate("USD", 0.0, STAMP, "unit-rate")
    result = recommend(
        m, p, rate, decision_time=STAMP, historical_preview=True, paths=100
    )
    args = archival_arguments(
        decision_time=STAMP,
        fx_to_base=None,
        current=None,
        costs=PlanningCosts(),
        sell_tax_rates=None,
        risk_state=None,
        equity_fraction=1.0,
        trend_confirmed=False,
        historical_preview=True,
        paths=100,
        annual_tax_drag=None,
    )
    snapshot = archive(tmp_path, result, m, p, rate, args)
    verified = replay(tmp_path, snapshot)
    assert verified["matches"]
    assert not verified["public_recommendations_enabled"]
    file = tmp_path / snapshot["relative_path"]
    file.write_bytes(b"changed")
    with pytest.raises(Exception, match="hash mismatch"):
        replay(tmp_path, snapshot)


def test_operator_application_persists_account_risk_and_is_not_a_public_service(
    tmp_path,
):
    app = OperatorApplication(
        prices(),
        CashRate("USD", 0.0, STAMP, "unit-rate"),
        tmp_path,
        historical_preview=True,
        as_of=STAMP,
    )
    m = mandate("preservation", drawdown_preference=0.05, financial_loss_capacity=0.05)
    request = {"mandate": asdict(m), "paths": 100}
    first = app.plan(request)
    second = app.plan(request)
    assert first["recommendation_id"] == second["recommendation_id"]
    assert first["risk_state"] == second["risk_state"]
    assert not second["qualification"]["public_recommendations_enabled"]
    assert first["input_snapshot"]["artifact_id"]
    assert list(tmp_path.glob("*/state.json"))
    with pytest.raises(ValueError, match="Unsupported"):
        app.plan({**request, "approval_root": "/tmp/forged"})
    with pytest.raises(ValueError, match="active owner"):
        OperatorApplication(
            prices(),
            CashRate("USD", 0.0, STAMP, "unit-rate"),
            tmp_path,
            historical_preview=True,
            as_of=STAMP,
        )
    app.close()


def test_release_manifest_covers_the_recommendation_entry_points():
    manifest = release_manifest()
    assert {
        "recommendation_api.py",
        "investment_product.py",
        "assetuniverse.py",
        "productsimulation.py",
    } <= set(manifest["source_hashes"])
    assert manifest["broker_submission_enabled"] is False


def test_cli_checkpoints_risk_before_publishing_a_result(tmp_path, monkeypatch):
    import investment_product as cli
    import sys

    m = mandate("preservation")
    mp = tmp_path / "mandate.json"
    mp.write_text(json.dumps(asdict(m)))
    pp = tmp_path / "prices.csv"
    prices().to_csv(pp)
    rp = tmp_path / "rate.json"
    rp.write_text(json.dumps(asdict(CashRate("USD", 0.0, STAMP, "unit-rate"))))
    output = tmp_path / "out"
    key = hashlib.sha256(m.client_id.encode()).hexdigest()[:24]
    monkeypatch.setattr(
        cli,
        "recommend",
        lambda *args, **kwargs: {
            "risk_state": {"peak": 1.1},
            "recommendation_id": "checkpoint-fixture",
            "allocation": {"weights": None},
            "mandate": {"base_currency": "USD"},
            "price_session": "2025-10-29",
            "as_of": STAMP,
        },
    )
    monkeypatch.setattr(
        cli, "archive", lambda *args, **kwargs: {"artifact_id": "unit-fixture"}
    )

    def publish(result, directory, **report_options):
        saved = json.loads((directory / f"risk-state-{key}.json").read_text())
        assert saved["state"]["peak"] == 1.1
        return {"published": True}

    monkeypatch.setattr(cli, "save_result", publish)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "investment_product.py",
            "--mandate",
            str(mp),
            "--prices",
            str(pp),
            "--cash-rate",
            str(rp),
            "--as-of",
            STAMP,
            "--historical-preview",
            "--paths",
            "100",
            "--output",
            str(output),
        ],
    )
    cli.main()
