from oms import OMS
from order import Order
from orderbook import OrderBook
from paperbroker import PaperBroker
from paperconfig import PaperRuntimeConfig
from paperexecution import PaperExecutionError, PaperExecutionSession
from paperstore import SQLitePaperStore
from portfolioaccount import PortfolioAccount
from reconciliationengine import ReconciliationEngine
import pytest


def test_orderbook_round_trip_preserves_order_lifecycle_buckets() -> None:
    book = OrderBook()
    active = Order("SPY", "BUY", 2, order_id="paper-active")
    completed = Order("TLT", "SELL", 1, order_id="paper-completed")
    book.add_order(active)
    book.active_orders.pop(completed.order_id, None)
    book.completed_orders[completed.order_id] = completed
    book.last_order = active

    restored = OrderBook.from_dict(book.to_dict())

    assert restored.get_order("paper-active").ticker == "SPY"
    assert restored.get_order("paper-completed").ticker == "TLT"
    assert restored.last_order is restored.get_order("paper-active")


def test_oms_round_trip_preserves_orderbook_and_execution_engines() -> None:
    oms = OMS()
    order = Order("SPY", "BUY", 2, order_id="paper-order")
    oms.order_book.add_order(order)

    restored = OMS.from_dict(oms.to_dict())

    assert restored.order_book.get_order("paper-order").ticker == "SPY"
    assert restored.order_book.active_count == 1
    assert restored.execution_engine is restored.broker_execution_engine.execution_engine


def test_recovery_fails_closed_when_snapshot_contains_open_order(tmp_path) -> None:
    config = PaperRuntimeConfig(
        state_database=tmp_path / "state.sqlite3",
        audit_log=tmp_path / "audit.jsonl",
    )
    store = SQLitePaperStore(config.state_database)
    oms = OMS()
    oms.order_book.add_order(Order("SPY", "BUY", 1, order_id="interrupted-order"))
    store.save_snapshot(
        PaperExecutionSession.SNAPSHOT_KEY,
        {
            "schema_version": PaperExecutionSession.SCHEMA_VERSION,
            "cycle_id": "interrupted-cycle",
            "phase": "ORDER_SUBMITTED:interrupted-order",
            "last_rebalance_data_as_of": None,
            "account": PortfolioAccount(config.initial_cash).to_dict(),
            "oms": oms.to_dict(),
            "broker": PaperBroker().to_dict(),
            "reconciliation": ReconciliationEngine().to_dict(),
        },
        schema_version=PaperExecutionSession.SCHEMA_VERSION,
        expected_revision=0,
    )

    with pytest.raises(PaperExecutionError, match="outstanding OMS orders"):
        PaperExecutionSession(store, config.initial_cash)
