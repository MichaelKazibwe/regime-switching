"""
======================================================================
brokerrouter.py

Institutional Broker Router
======================================================================

Routes approved OMS orders to the appropriate broker adapter.

Responsibilities
----------------

    - broker registration
    - broker selection
    - deterministic routing
    - default broker management
    - order submission to broker adapters
    - broker availability checks
    - routing audit trail
    - serialization
    - metadata
    - health checks
    - regression tests

The BrokerRouter does NOT:

    - generate portfolio targets
    - generate trades
    - perform portfolio optimization
    - perform pre-trade risk checks
    - manage the OrderBook
    - calculate transaction costs
    - directly modify PortfolioAccount
    - implement broker-specific execution logic

Those responsibilities belong to:

    RebalanceEngine
    TradeGenerator
    PreTradeRiskGate
    OMS
    TransactionCostModel
    PaperBroker / LiveBroker
    ExecutionEngine
    PortfolioAccount

Architecture
------------

    Portfolio
        |
        v
    RebalanceEngine
        |
        v
    TradeGenerator
        |
        v
    PreTradeRiskGate
        |
        v
    OMS
        |
        v
    BrokerRouter
        |
        +----------------+
        |                |
        v                v
    PaperBroker       LiveBroker

Author: Michael Kazibwe
Version: 1.0.0
======================================================================
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Optional

from order import Order


# ======================================================================
# BROKER ADAPTER
# ======================================================================


class BrokerAdapter(ABC):
    """
    Abstract broker interface.

    Concrete brokers must implement this interface.

    The router depends only on this abstraction and therefore does not
    contain broker-specific execution logic.
    """

    API_VERSION = "1.0.0"

    @property
    @abstractmethod
    def broker_name(self) -> str:
        """
        Return the broker's unique name.
        """
        raise NotImplementedError

    @abstractmethod
    def submit_order(
        self,
        order: Order,
    ) -> Any:
        """
        Submit an order to the broker.
        """
        raise NotImplementedError

    @abstractmethod
    def cancel_order(
        self,
        order_id: str,
    ) -> Any:
        """
        Cancel an order at the broker.
        """
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> bool:
        """
        Return broker health status.
        """
        raise NotImplementedError


# ======================================================================
# ROUTING RESULT
# ======================================================================


class RoutingResult:
    """
    Immutable-style routing result.

    Contains the broker selected and the broker response.
    """

    API_VERSION = "1.0.0"

    def __init__(
        self,
        approved: bool,
        order_id: Optional[str],
        broker: Optional[str],
        response: Any = None,
        reason: Optional[str] = None,
        timestamp: Optional[str] = None,
    ):

        self.approved = bool(
            approved
        )

        self.order_id = order_id

        self.broker = broker

        self.response = response

        self.reason = reason

        self.timestamp = (
            timestamp
            if timestamp is not None
            else datetime.now(
                UTC
            ).isoformat()
        )

    def to_dict(self) -> dict:
        """
        Serialize the routing result.
        """

        return {
            "api_version":
                self.API_VERSION,

            "approved":
                self.approved,

            "order_id":
                self.order_id,

            "broker":
                self.broker,

            "response":
                self.response,

            "reason":
                self.reason,

            "timestamp":
                self.timestamp,
        }


# ======================================================================
# BROKER ROUTER
# ======================================================================


class BrokerRouter:
    """
    Institutional broker routing engine.

    Routes approved Order objects to registered broker adapters.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (
        "register_broker",
        "unregister_broker",
        "set_default_broker",
        "get_broker",
        "available_brokers",
        "route_order",
        "route_batch",
        "health_check",
        "summary",
        "metadata",
        "to_dict",
        "from_dict",
    )

    # ==================================================================
    # CONSTRUCTOR
    # ==================================================================

    def __init__(
        self,
        default_broker: Optional[str] = None,
    ):
        """
        Initialize the broker router.

        Parameters
        ----------
        default_broker:
            Optional broker name used when route_order() does not
            explicitly specify a broker.
        """

        self._brokers: dict[
            str,
            BrokerAdapter,
        ] = {}

        self.default_broker = (
            default_broker
        )

        self.routing_history: list[
            dict
        ] = []

        self.last_result: Optional[
            RoutingResult
        ] = None

        self.route_count = 0

    # ==================================================================
    # TIMESTAMP
    # ==================================================================

    @staticmethod
    def _timestamp() -> str:
        """
        Return a UTC timestamp.
        """

        return datetime.now(
            UTC
        ).isoformat()

    # ==================================================================
    # BROKER NAME
    # ==================================================================

    @staticmethod
    def _normalize_broker_name(
        broker_name: str,
    ) -> str:
        """
        Normalize broker names.
        """

        if not isinstance(
            broker_name,
            str,
        ):
            raise TypeError(
                "broker_name must be a string."
            )

        broker_name = (
            broker_name
            .strip()
            .upper()
        )

        if not broker_name:
            raise ValueError(
                "broker_name cannot be empty."
            )

        return broker_name

    # ==================================================================
    # REGISTER BROKER
    # ==================================================================

    def register_broker(
        self,
        broker: BrokerAdapter,
    ) -> None:
        """
        Register a broker adapter.
        """

        if not isinstance(
            broker,
            BrokerAdapter,
        ):
            raise TypeError(
                "broker must implement BrokerAdapter."
            )

        name = self._normalize_broker_name(
            broker.broker_name
        )

        if name in self._brokers:
            raise ValueError(
                f"Broker '{name}' is already registered."
            )

        self._brokers[name] = broker

        if self.default_broker is None:
            self.default_broker = name

    # ==================================================================
    # UNREGISTER BROKER
    # ==================================================================

    def unregister_broker(
        self,
        broker_name: str,
    ) -> None:
        """
        Remove a registered broker.
        """

        name = self._normalize_broker_name(
            broker_name
        )

        if name not in self._brokers:
            raise KeyError(
                f"Broker '{name}' is not registered."
            )

        del self._brokers[name]

        if self.default_broker == name:
            self.default_broker = None

    # ==================================================================
    # SET DEFAULT BROKER
    # ==================================================================

    def set_default_broker(
        self,
        broker_name: str,
    ) -> None:
        """
        Set the default routing broker.
        """

        name = self._normalize_broker_name(
            broker_name
        )

        if name not in self._brokers:
            raise KeyError(
                f"Broker '{name}' is not registered."
            )

        self.default_broker = name

    # ==================================================================
    # GET BROKER
    # ==================================================================

    def get_broker(
        self,
        broker_name: str,
    ) -> BrokerAdapter:
        """
        Retrieve a registered broker.
        """

        name = self._normalize_broker_name(
            broker_name
        )

        if name not in self._brokers:
            raise KeyError(
                f"Broker '{name}' is not registered."
            )

        return self._brokers[name]

    # ==================================================================
    # AVAILABLE BROKERS
    # ==================================================================

    def available_brokers(
        self,
    ) -> list[str]:
        """
        Return registered broker names.
        """

        return sorted(
            self._brokers.keys()
        )

    # ==================================================================
    # ORDER VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_order(
        order: Order,
    ) -> None:
        """
        Validate an Order before routing.
        """

        if not isinstance(
            order,
            Order,
        ):
            raise TypeError(
                "order must be an Order object."
            )

        order.validate()

    # ==================================================================
    # ROUTING AUDIT
    # ==================================================================

    def _record_route(
        self,
        result: RoutingResult,
    ) -> None:
        """
        Record a routing event.
        """

        self.routing_history.append(
            result.to_dict()
        )

        self.last_result = result

    # ==================================================================
    # ROUTE ORDER
    # ==================================================================

    def route_order(
        self,
        order: Order,
        broker_name: Optional[str] = None,
    ) -> RoutingResult:
        """
        Route one order to a broker.

        If broker_name is omitted, the configured default broker
        is used.

        The router does not modify the order itself.
        """

        self._validate_order(
            order
        )

        selected_name = (
            broker_name
            if broker_name is not None
            else self.default_broker
        )

        if selected_name is None:
            result = RoutingResult(
                approved=False,
                order_id=order.order_id,
                broker=None,
                reason="NO_DEFAULT_BROKER",
            )

            self._record_route(
                result
            )

            raise RuntimeError(
                "No broker specified and no default broker configured."
            )

        selected_name = (
            self._normalize_broker_name(
                selected_name
            )
        )

        broker = self.get_broker(
            selected_name
        )

        if not broker.health_check():

            result = RoutingResult(
                approved=False,
                order_id=order.order_id,
                broker=selected_name,
                reason="BROKER_UNHEALTHY",
            )

            self._record_route(
                result
            )

            raise RuntimeError(
                f"Broker '{selected_name}' is unhealthy."
            )

        try:

            response = broker.submit_order(
                order
            )

        except Exception as exc:

            result = RoutingResult(
                approved=False,
                order_id=order.order_id,
                broker=selected_name,
                reason="BROKER_SUBMISSION_FAILED",
                response={
                    "error": str(exc),
                    "error_type":
                        type(exc).__name__,
                },
            )

            self._record_route(
                result
            )

            raise RuntimeError(
                f"Broker submission failed for "
                f"order '{order.order_id}': {exc}"
            ) from exc

        self.route_count += 1

        result = RoutingResult(
            approved=True,
            order_id=order.order_id,
            broker=selected_name,
            response=response,
        )

        self._record_route(
            result
        )

        return result

    # ==================================================================
    # ROUTE BATCH
    # ==================================================================

    def route_batch(
        self,
        orders: list[Order],
        broker_name: Optional[str] = None,
    ) -> list[RoutingResult]:
        """
        Route a batch of orders.

        Orders are processed sequentially and deterministically.
        """

        if not isinstance(
            orders,
            list,
        ):
            raise TypeError(
                "orders must be a list."
            )

        results = []

        for order in orders:

            results.append(
                self.route_order(
                    order,
                    broker_name,
                )
            )

        return results

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(self) -> dict:
        """
        Return router state summary.
        """

        successful = sum(
            result.get(
                "approved",
                False,
            )
            for result in self.routing_history
        )

        failed = len(
            self.routing_history
        ) - successful

        return {
            "api_version":
                self.API_VERSION,

            "registered_brokers":
                len(self._brokers),

            "available_brokers":
                self.available_brokers(),

            "default_broker":
                self.default_broker,

            "route_count":
                self.route_count,

            "successful_routes":
                successful,

            "failed_routes":
                failed,

            "routing_events":
                len(self.routing_history),

            "last_order_id":
                None
                if self.last_result is None
                else self.last_result.order_id,

            "last_broker":
                None
                if self.last_result is None
                else self.last_result.broker,
        }

    # ==================================================================
    # METADATA
    # ==================================================================

    @property
    def metadata(self) -> dict:
        """
        Return module metadata.
        """

        return {
            "component":
                "BrokerRouter",

            "api_version":
                self.API_VERSION,

            "public_methods":
                list(
                    self.PUBLIC_METHODS
                ),

            "summary":
                self.summary(),
        }

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ) -> bool:
        """
        Validate router and registered broker health.
        """

        if self.API_VERSION != "1.0.0":
            raise RuntimeError(
                "Invalid BrokerRouter API version."
            )

        if self.default_broker is not None:

            if (
                self.default_broker
                not in self._brokers
            ):

                raise RuntimeError(
                    "Default broker is not registered."
                )

        for name, broker in (
            self._brokers.items()
        ):

            normalized = (
                self._normalize_broker_name(
                    broker.broker_name
                )
            )

            if normalized != name:
                raise RuntimeError(
                    f"Broker registry key mismatch for '{name}'."
                )

            if not broker.health_check():
                raise RuntimeError(
                    f"Broker '{name}' is unhealthy."
                )

        return True

    # ==================================================================
    # TO DICTIONARY
    # ==================================================================

    def to_dict(self) -> dict:
        """
        Serialize router configuration and routing history.

        Broker adapter objects themselves are deliberately not
        serialized because their runtime connections belong to the
        broker layer.
        """

        return {
            "api_version":
                self.API_VERSION,

            "default_broker":
                self.default_broker,

            "route_count":
                self.route_count,

            "routing_history":
                list(
                    self.routing_history
                ),
        }

    # ==================================================================
    # FROM DICTIONARY
    # ==================================================================

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> BrokerRouter:
        """
        Restore router state.

        Broker adapters must be registered separately after
        deserialization.
        """

        if not isinstance(
            data,
            dict,
        ):
            raise TypeError(
                "data must be a dictionary."
            )

        router = cls(
            default_broker=data.get(
                "default_broker"
            )
        )

        router.route_count = int(
            data.get(
                "route_count",
                0,
            )
        )

        router.routing_history = list(
            data.get(
                "routing_history",
                [],
            )
        )

        return router


# ======================================================================
# TEST BROKER
# ======================================================================


class _TestBroker(BrokerAdapter):
    """
    Deterministic broker adapter used exclusively by regression tests.

    This class is intentionally private and is not part of the
    production broker layer.
    """

    def __init__(
        self,
        name: str = "TESTBROKER",
    ):

        self._name = (
            name.upper()
        )

        self.submitted_orders: list[
            str
        ] = []

        self.cancelled_orders: list[
            str
        ] = []

        self.healthy = True

    @property
    def broker_name(self) -> str:
        return self._name

    def submit_order(
        self,
        order: Order,
    ) -> dict:

        if not isinstance(
            order,
            Order,
        ):
            raise TypeError(
                "order must be an Order object."
            )

        self.submitted_orders.append(
            order.order_id
        )

        return {
            "broker":
                self._name,

            "order_id":
                order.order_id,

            "status":
                "SUBMITTED",
        }

    def cancel_order(
        self,
        order_id: str,
    ) -> dict:

        self.cancelled_orders.append(
            order_id
        )

        return {
            "broker":
                self._name,

            "order_id":
                order_id,

            "status":
                "CANCEL_REQUESTED",
        }

    def health_check(
        self,
    ) -> bool:

        return self.healthy


# ======================================================================
# REGRESSION TESTS
# ======================================================================


def test_broker_router():
    """
    Regression tests for BrokerRouter.
    """

    # ==============================================================
    # CONSTRUCTION
    # ==============================================================

    router = BrokerRouter()

    assert (
        router.API_VERSION
        == "1.0.0"
    )

    assert router.health_check()

    assert (
        router.available_brokers()
        == []
    )

    # ==============================================================
    # REGISTER BROKER
    # ==============================================================

    broker = _TestBroker(
        "PAPER"
    )

    router.register_broker(
        broker
    )

    assert (
        router.available_brokers()
        == ["PAPER"]
    )

    assert (
        router.default_broker
        == "PAPER"
    )

    assert (
        router.get_broker("PAPER")
        is broker
    )

    assert router.health_check()

    # ==============================================================
    # ORDER
    # ==============================================================

    order = Order(
        order_id="ROUTER-000001",
        ticker="SPY",
        side="BUY",
        quantity=100,
    )

    # ==============================================================
    # ROUTE
    # ==============================================================

    result = router.route_order(
        order
    )

    assert isinstance(
        result,
        RoutingResult,
    )

    assert result.approved

    assert (
        result.order_id
        == "ROUTER-000001"
    )

    assert (
        result.broker
        == "PAPER"
    )

    assert (
        result.response["status"]
        == "SUBMITTED"
    )

    assert (
        broker.submitted_orders
        == ["ROUTER-000001"]
    )

    # ==============================================================
    # ROUTE COUNT
    # ==============================================================

    assert (
        router.route_count
        == 1
    )

    # ==============================================================
    # BATCH
    # ==============================================================

    orders = [
        Order(
            order_id="ROUTER-000002",
            ticker="QQQ",
            side="BUY",
            quantity=50,
        ),
        Order(
            order_id="ROUTER-000003",
            ticker="TLT",
            side="SELL",
            quantity=25,
        ),
    ]

    results = router.route_batch(
        orders
    )

    assert len(
        results
    ) == 2

    assert all(
        result.approved
        for result in results
    )

    assert (
        router.route_count
        == 3
    )

    # ==============================================================
    # EXPLICIT BROKER
    # ==============================================================

    second_broker = _TestBroker(
        "SECOND"
    )

    router.register_broker(
        second_broker
    )

    explicit_order = Order(
        order_id="ROUTER-000004",
        ticker="GLD",
        side="BUY",
        quantity=10,
    )

    explicit_result = router.route_order(
        explicit_order,
        broker_name="SECOND",
    )

    assert (
        explicit_result.broker
        == "SECOND"
    )

    assert (
        second_broker.submitted_orders
        == ["ROUTER-000004"]
    )

    # ==============================================================
    # DEFAULT BROKER
    # ==============================================================

    router.set_default_broker(
        "SECOND"
    )

    default_order = Order(
        order_id="ROUTER-000005",
        ticker="IEF",
        side="BUY",
        quantity=20,
    )

    default_result = router.route_order(
        default_order
    )

    assert (
        default_result.broker
        == "SECOND"
    )

    # ==============================================================
    # BROKER LOOKUP
    # ==============================================================

    try:

        router.get_broker(
            "DOES_NOT_EXIST"
        )

        raise AssertionError(
            "Expected KeyError"
        )

    except KeyError:
        pass

    # ==============================================================
    # DUPLICATE REGISTRATION
    # ==============================================================

    try:

        router.register_broker(
            _TestBroker("SECOND")
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:
        pass

    # ==============================================================
    # UNREGISTER
    # ==============================================================

    router.unregister_broker(
        "SECOND"
    )

    assert (
        "SECOND"
        not in router.available_brokers()
    )

    assert (
        router.default_broker
        is None
    )

    # ==============================================================
    # NO BROKER
    # ==============================================================

    try:

        router.route_order(
            Order(
                order_id="ROUTER-000006",
                ticker="SPY",
                side="BUY",
                quantity=5,
            )
        )

        raise AssertionError(
            "Expected RuntimeError"
        )

    except RuntimeError as exc:

        assert (
            "No broker"
            in str(exc)
        )

    # ==============================================================
    # UNHEALTHY BROKER
    # ==============================================================

    unhealthy = _TestBroker(
        "UNHEALTHY"
    )

    unhealthy.healthy = False

    router.register_broker(
        unhealthy
    )

    router.set_default_broker(
        "UNHEALTHY"
    )

    try:

        router.route_order(
            Order(
                order_id="ROUTER-000007",
                ticker="SPY",
                side="BUY",
                quantity=5,
            )
        )

        raise AssertionError(
            "Expected RuntimeError"
        )

    except RuntimeError as exc:

        assert (
            "unhealthy"
            in str(exc).lower()
        )

    # ==============================================================
    # SERIALIZATION
    # ==============================================================

    router.set_default_broker(
        "UNHEALTHY"
    )

    exported = router.to_dict()

    restored = (
        BrokerRouter.from_dict(
            exported
        )
    )

    assert (
        restored.API_VERSION
        == router.API_VERSION
    )

    assert (
        restored.default_broker
        == router.default_broker
    )

    assert (
        restored.route_count
        == router.route_count
    )

    assert (
        restored.routing_history
        == router.routing_history
    )

    # ==============================================================
    # METADATA
    # ==============================================================

    metadata = router.metadata

    assert (
        metadata["component"]
        == "BrokerRouter"
    )

    assert (
        metadata["api_version"]
        == router.API_VERSION
    )

    assert (
        "route_order"
        in metadata["public_methods"]
    )

    # ==============================================================
    # FINAL HEALTH
    # ==============================================================

    router.unregister_broker(
        "UNHEALTHY"
    )

    assert router.health_check()

    print(
        "BrokerRouter Phase III-B.4 tests passed."
    )


# ======================================================================
# MAIN
# ======================================================================


if __name__ == "__main__":
    test_broker_router()