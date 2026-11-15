from datetime import timedelta
import hashlib
import hmac
import pytest
from test_managed_execution import system, NOW, Reader  # noqa: F401
from managed_api import ManagedPaperAPI
from managed_evidence import readiness, source_identity, REVIEWS
from ibkr_paper_orders import IBKRPaperOrders
from strategy_integrity import canonical, file_hash


def test_api_uses_server_owned_quotes_permits_and_account_grants(system):  # noqa: F811
    e, t, a, c, q, p, sig = system
    api = ManagedPaperAPI(
        e,
        instruments={"SPY": c},
        quote_reader=lambda *_: q,
        permit_reader=lambda *_: (p, sig),
        transport_reader=lambda _: IBKRPaperOrders(a.account, Reader()),
        broker_reader=lambda _: None,
        local_reader=lambda _: None,
    )
    request = dict(
        action="prepare",
        tenant=a.tenant,
        account=a.account,
        payload=dict(instrument_id="SPY", quantity="1", client_id="one"),
    )
    assert api.handle(t, request) == "PAPER_QUEUED"
    with pytest.raises(ValueError):
        api.handle(t, {**request, "payload": {**request["payload"], "quote": q}})
    with pytest.raises(PermissionError):
        api.handle(t, {**request, "tenant": "other"})
    assert (
        api.handle(t, {**request, "action": "orders", "payload": {}})["orders"][0][
            "client_id"
        ]
        == "one"
    )
    with pytest.raises(PermissionError):
        api.handle(t, {**request, "action": "live_enable"})


def test_signed_receipts_bind_sources_image_account_expiry_and_artifacts(
    system,  # noqa: F811
    tmp_path,  # noqa: F811
):  # noqa: F811
    _, _, scope, *_ = system
    artifact = tmp_path / "review.txt"
    artifact.write_text("SYNTHETIC TEST REVIEW - NOT A REAL APPROVAL")
    image = "sha256:" + "a" * 64
    key = b"review-key-for-test-only-32-bytes!!"
    receipts = []
    for check in REVIEWS:
        body = dict(
            reviewer="TEST",
            check=check,
            status="PASS",
            source_id=source_identity(),
            image_digest=image,
            tenant=scope.tenant,
            account=scope.account,
            mode="PAPER",
            reviewed_at=NOW.isoformat(),
            expires_at=(NOW + timedelta(days=1)).isoformat(),
            artifacts=[dict(path=artifact.name, sha256=file_hash(artifact))],
        )
        receipts.append(
            {
                **body,
                "signature": hmac.new(
                    key, canonical(body).encode(), hashlib.sha256
                ).hexdigest(),
            }
        )
    report = readiness(receipts, {"TEST": key}, scope, image, tmp_path, now=NOW)
    assert report["status"] == "READY_FOR_INDEPENDENT_PAPER_REVIEW"
    assert not report["execution_enabled"] and not report["release_approved"]
    assert (
        readiness(
            receipts,
            {"TEST": key},
            scope,
            image,
            tmp_path,
            client_account=True,
            now=NOW,
        )["status"]
        == "BLOCKED"
    )
    assert (
        readiness(
            receipts, {"TEST": key}, scope, "sha256:" + "b" * 64, tmp_path, now=NOW
        )["status"]
        == "BLOCKED"
    )
    assert (
        readiness(
            receipts, {"TEST": key}, scope, image, tmp_path, now=NOW + timedelta(days=2)
        )["status"]
        == "BLOCKED"
    )
    artifact.write_text("changed")
    assert (
        readiness(receipts, {"TEST": key}, scope, image, tmp_path, now=NOW)["status"]
        == "BLOCKED"
    )


def test_no_receipts_can_silently_qualify_account(system, tmp_path):  # noqa: F811
    report = readiness([], {}, system[2], "sha256:" + "a" * 64, tmp_path, now=NOW)
    assert report["status"] == "BLOCKED" and report["missing"]


def test_api_to_paper_adapter_to_durable_broker_event(system):  # noqa: F811
    e, t, a, c, q, p, sig = system
    requests = []

    def writer(*args):
        requests.append(args)
        return [dict(order_id="77", order_status="Submitted")]

    transport = IBKRPaperOrders(a.account, Reader(), writer)
    api = ManagedPaperAPI(
        e,
        instruments={"SPY": c},
        quote_reader=lambda *_: q,
        permit_reader=lambda *_: (p, sig),
        transport_reader=lambda _: transport,
        broker_reader=lambda _: None,
        local_reader=lambda _: None,
    )
    envelope = dict(tenant=a.tenant, account=a.account)
    api.handle(
        t,
        {
            **envelope,
            "action": "prepare",
            "payload": dict(instrument_id="SPY", quantity="1", client_id="api-order"),
        },
    )
    receipt = api.handle(
        t, {**envelope, "action": "dispatch", "payload": dict(client_id="api-order")}
    )
    assert receipt["broker_id"] == "77" and len(requests) == 1
    e.event(
        t,
        a,
        dict(
            tenant=a.tenant,
            account=a.account,
            event_id="fill",
            broker_id="77",
            status="FILLED",
            cumulative_filled="1",
            cumulative_notional="100",
            cumulative_fee="0",
            trade_date="2026-11-02",
            settlement_date="2026-11-03",
        ),
    )
    assert (
        api.handle(t, {**envelope, "action": "orders", "payload": {}})["orders"][0][
            "state"
        ]
        == "FILLED"
    )
    with pytest.raises(PermissionError):
        api.handle(
            t,
            {**envelope, "action": "dispatch", "payload": dict(client_id="api-order")},
        )


def test_paper_http_writer_default_deny_and_verified_discovery_order():
    from ibkr_paper_orders import GatewayPaperWriter

    writer = GatewayPaperWriter("DU123")
    payload = {"orders": [dict(acctId="DU123")]}
    with pytest.raises(PermissionError):
        writer("POST", "/iserver/account/DU123/orders", payload)
    writer.submission_enabled = True
    with pytest.raises(PermissionError):
        writer("POST", "/iserver/reply/123", {})
    calls = []
    writer.get = lambda _: [dict(accountId="DU123", type="DEMO")]

    def exchange(method, path, body=None):
        calls.append((method, path))
        return {"accounts": ["DU123"]} if method == "GET" else [dict(order_id="99")]

    writer._exchange = exchange
    assert (
        writer("POST", "/iserver/account/DU123/orders", payload)[0]["order_id"] == "99"
    )
    assert calls[0] == ("GET", "/iserver/accounts") and calls[1][0] == "POST"
    with pytest.raises(PermissionError):
        writer("DELETE", "/iserver/account/DU123/order/-1", None)
