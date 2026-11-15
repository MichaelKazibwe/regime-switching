import pytest
from ibkr_paper_probe import snapshot, GatewayReader


class Reader:
    def __init__(self):
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        if path.endswith("accounts"):
            return [dict(accountId="DU123", type="DEMO")]
        if path.endswith("positions/0"):
            return [dict(acctId="DU123", conid=1, position=2)]
        if "positions/" in path:
            return []
        return {"USD": dict(acctcode="DU123", cashbalance=100, settledcash=90)}


def test_read_only_account_discovery_pagination_and_cash():
    reader = Reader()
    result = snapshot(reader, "DU123")
    assert len(result["positions"]) == 1 and not result["execution_enabled"]
    assert reader.calls[0] == "/portfolio/accounts"


def test_real_account_and_order_urls_rejected_without_network():
    with pytest.raises(ValueError):
        snapshot(Reader(), "U123")
    with pytest.raises(ValueError):
        GatewayReader().get("/iserver/account/DU123/orders")


def test_wrong_account_position_never_becomes_snapshot():
    reader = Reader()
    original = reader.get

    def bad(path):
        rows = original(path)
        if path.endswith("positions/0"):
            rows[0]["acctId"] = "DU999"
        return rows

    reader.get = bad
    with pytest.raises(ValueError, match="Wrong-account"):
        snapshot(reader, "DU123")


def test_connection_failure_is_not_an_empty_qualified_account():
    class Offline:
        def get(self, path):
            raise TimeoutError("synthetic outage")

    with pytest.raises(TimeoutError):
        snapshot(Offline(), "DU123")
