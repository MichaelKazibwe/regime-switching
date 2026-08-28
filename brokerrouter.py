"""
======================================================================
brokerrouter.py

Institutional Broker Router
======================================================================

Routes authorization-bound OMS orders to the appropriate broker
adapter.

Responsibilities
----------------

    - broker registration
    - broker selection
    - deterministic authorized routing
    - default broker management
    - authorized order submission to broker adapters
    - broker availability checks
    - routing audit trail
    - serialization
    - metadata
    - health checks
    - legacy raw-routing containment
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
    - create authorization
    - modify authorization
    - enable live trading
    - enable broker submission independently of authorization

Those responsibilities belong to:

    RebalanceEngine
    TradeGenerator
    PreTradeRiskGate
    OMS
    TransactionCostModel
    PaperBroker / LiveBroker
    ExecutionEngine
    PortfolioAccount
    Authorization / Handoff layers

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
    AuthorizedOrderIntent
        |
        v
    AuthorizedExecutionHandoff
        |
        v
    AuthorizedRoutingHandoff
        |
        v
    BrokerRouter.route_authorized_order()
        |
        v
    BrokerRouter._route_authorized_order()
        |
        +----------------+
        |                |
        v                v
    PaperBroker       LiveBroker


LEGACY / RAW ROUTING

    Raw Order
        |
        X
    route_order()
        |
        X
    Broker submission


RAW BATCH ROUTING

    list[Order]
        |
        X
    route_batch()
        |
        X
    Broker submission


Security Boundary
-----------------

The production broker-submission boundary requires an
AuthorizedRoutingHandoff.

The legacy public methods:

    route_order()
    route_batch()

remain present for API compatibility but are deliberately
fail-closed.

They MUST NOT submit raw Order objects to a broker.

Only:

    route_authorized_order(
        AuthorizedRoutingHandoff
    )

may cross the production routing boundary.

Author: Michael Kazibwe
Version: 1.1.0
======================================================================
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Optional

from order import Order

from authorizedroutinghandoff import (
    AuthorizedRoutingHandoff,
    AuthorizedRoutingHandoffError,
)


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
    def broker_name(
        self,
    ) -> str:
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
    def health_check(
        self,
    ) -> bool:
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

    Authorization provenance is preserved when the routing operation
    crosses the authorized routing boundary.
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
        authorization_provenance: Optional[dict] = None,
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

        self.authorization_provenance = (
            authorization_provenance
        )

    def to_dict(
        self,
    ) -> dict:
        """
        Serialize the routing result.
        """

        return {
            "api_version":
                self.API_VERSION,

            "approved":
                self.approved,

            "authorization_provenance":
                self.authorization_provenance,

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

    Production broker submission requires an
    AuthorizedRoutingHandoff.

    Raw Order routing APIs remain available only as fail-closed
    compatibility surfaces.
    """

    API_VERSION = "1.1.0"

    PUBLIC_METHODS = (
        "register_broker",
        "unregister_broker",
        "set_default_broker",
        "get_broker",
        "available_brokers",
        "route_order",
        "route_authorized_order",
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
            Optional broker name used by the authorized routing path
            when no explicit broker is supplied.
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

        normalized = (
            broker_name
            .strip()
            .upper()
        )

        if not normalized:
            raise ValueError(
                "broker_name cannot be empty."
            )

        return normalized

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
    # INTERNAL AUTHORIZED ROUTING IMPLEMENTATION
    # ==================================================================

    def _route_authorized_order(
        self,
        order: Order,
        broker_name: Optional[str] = None,
    ) -> RoutingResult:
        """
        Internal broker-routing implementation.

        IMPORTANT
        ---------

        This method is intentionally private.

        It is called only after route_authorized_order() has validated
        an AuthorizedRoutingHandoff.

        It performs:

            - canonical Order validation;
            - broker selection;
            - broker health validation;
            - broker submission;
            - routing accounting;
            - routing audit.

        It does NOT:

            - create authorization;
            - validate authorization;
            - modify authorization;
            - create an Order;
            - modify PortfolioAccount;
            - execute portfolio accounting;
            - enable live trading independently.

        The authorization boundary is therefore established by the
        public route_authorized_order() method before this method is
        reached.
        """

        # --------------------------------------------------------------
        # CANONICAL ORDER VALIDATION
        # --------------------------------------------------------------

        self._validate_order(
            order
        )

        # --------------------------------------------------------------
        # BROKER SELECTION
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # BROKER LOOKUP
        # --------------------------------------------------------------

        broker = self.get_broker(
            selected_name
        )

        # --------------------------------------------------------------
        # BROKER HEALTH
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # BROKER SUBMISSION
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # ROUTING ACCOUNTING
        # --------------------------------------------------------------

        self.route_count += 1

        # --------------------------------------------------------------
        # ROUTING RESULT
        # --------------------------------------------------------------

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
    # AUTHORIZED ROUTE ORDER
    # ==================================================================

    def route_authorized_order(
        self,
        handoff: AuthorizedRoutingHandoff,
        broker_name: Optional[str] = None,
    ) -> RoutingResult:
        """
        Route an authorization-bound Order.

        Phase IV-I-G / Phase IV-I-J authorized routing boundary.

        The method requires an immutable
        AuthorizedRoutingHandoff and preserves the complete
        upstream authorization provenance.

        The method is the ONLY public production routing method
        permitted to cross into broker submission.

        It does NOT:

            - create authorization;
            - modify authorization;
            - create an Order;
            - perform portfolio risk authorization;
            - enable live trading;
            - independently authorize broker submission.
        """

        # --------------------------------------------------------------
        # HANDOFF TYPE
        # --------------------------------------------------------------

        if not isinstance(
            handoff,
            AuthorizedRoutingHandoff,
        ):
            raise AuthorizedRoutingHandoffError(
                (
                    "route_authorized_order requires an "
                    "AuthorizedRoutingHandoff."
                )
            )

        # --------------------------------------------------------------
        # HANDOFF VALIDATION
        # --------------------------------------------------------------

        try:

            handoff.validate()

        except Exception as exc:

            raise AuthorizedRoutingHandoffError(
                (
                    "Authorized routing handoff rejected: "
                    f"{exc}"
                )
            ) from exc

        # --------------------------------------------------------------
        # CANONICAL ORDER
        # --------------------------------------------------------------

        order = handoff.routing_order()

        if not isinstance(
            order,
            Order,
        ):
            raise AuthorizedRoutingHandoffError(
                (
                    "Authorized routing handoff does not contain "
                    "a canonical Order."
                )
            )

        # --------------------------------------------------------------
        # COMPLETE UPSTREAM PROVENANCE
        # --------------------------------------------------------------

        provenance = (
            handoff.execution_handoff.to_dict()
        )

        # --------------------------------------------------------------
        # AUTHORIZED ROUTING
        # --------------------------------------------------------------
        #
        # CRITICAL J.12 CHANGE:
        #
        # Do NOT call route_order().
        #
        # route_order() is the legacy raw-order compatibility API and
        # is deliberately fail-closed.
        #
        # Authorized routing delegates directly to the private routing
        # implementation after the AuthorizedRoutingHandoff has been
        # validated.
        #

        history_length_before = len(
            self.routing_history
        )

        result = self._route_authorized_order(
            order,
            broker_name=broker_name,
        )

        # --------------------------------------------------------------
        # AUTHORIZATION-AWARE RESULT
        # --------------------------------------------------------------

        authorized_result = RoutingResult(
            approved=result.approved,
            order_id=result.order_id,
            broker=result.broker,
            response=result.response,
            reason=result.reason,
            timestamp=result.timestamp,
            authorization_provenance=provenance,
        )

        # --------------------------------------------------------------
        # REPLACE ROUTING AUDIT ENTRY
        # --------------------------------------------------------------

        if len(
            self.routing_history
        ) > history_length_before:

            self.routing_history[
                history_length_before
            ] = authorized_result.to_dict()

        self.last_result = (
            authorized_result
        )

        return authorized_result

    # ==================================================================
    # LEGACY RAW ROUTE ORDER
    # ==================================================================

    def route_order(
        self,
        order: Order,
        broker_name: Optional[str] = None,
    ) -> RoutingResult:
        """
        Legacy raw-order routing API.

        PHASE IV-I-J.12
        ----------------

        Raw Order objects are prohibited from crossing the production
        broker-submission boundary.

        This method remains present for API compatibility but is
        deliberately fail-closed.

        Production routing MUST use:

            route_authorized_order(
                AuthorizedRoutingHandoff
            )

        The arguments are intentionally accepted so existing callers
        receive a deterministic RuntimeError rather than an unexpected
        Python signature error.

        No:

            - Order validation
            - broker selection
            - broker health check
            - broker submission
            - routing count mutation
            - routing-history mutation

        occurs here.
        """

        raise RuntimeError(
            "Raw Order routing is disabled. "
            "Use route_authorized_order() with an "
            "AuthorizedRoutingHandoff."
        )

    # ==================================================================
    # LEGACY RAW ROUTE BATCH
    # ==================================================================

    def route_batch(
        self,
        orders: list[Order],
        broker_name: Optional[str] = None,
    ) -> list[RoutingResult]:
        """
        Legacy raw-order batch routing API.

        PHASE IV-I-J.12
        ----------------

        Raw Order batches are prohibited from crossing the production
        broker-submission boundary.

        This method remains present for API compatibility but is
        deliberately fail-closed.

        Production batch routing must use explicit authorization-bound
        handoffs.

        No broker submission is performed.
        """

        raise RuntimeError(
            "Raw Order batch routing is disabled. "
            "Use authorized routing handoffs."
        )

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(
        self,
    ) -> dict:
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

        failed = (
            len(
                self.routing_history
            )
            - successful
        )

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
    def metadata(
        self,
    ) -> dict:
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

            "raw_routing_fail_closed":
                True,

            "authorized_routing_required":
                True,

            "production_routing_boundary":
                "route_authorized_order",

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

        if self.API_VERSION != "1.1.0":
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

    def to_dict(
        self,
    ) -> dict:
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
    def broker_name(
        self,
    ) -> str:
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

    These embedded tests explicitly verify the Phase IV-I-J.12
    raw-routing containment contract.
    """

    # ==============================================================
    # CONSTRUCTION
    # ==============================================================

    router = BrokerRouter()

    assert (
        router.API_VERSION
        == "1.1.0"
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
        router.get_broker(
            "PAPER"
        )
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
    # J.12 RAW ROUTING CONTAINMENT
    # ==============================================================

    initial_route_count = (
        router.route_count
    )

    initial_history_length = len(
        router.routing_history
    )

    initial_submissions = list(
        broker.submitted_orders
    )

    try:

        router.route_order(
            order
        )

        raise AssertionError(
            "Expected RuntimeError"
        )

    except RuntimeError as exc:

        assert (
            "Raw Order routing is disabled"
            in str(exc)
        )

    assert (
        router.route_count
        == initial_route_count
    )

    assert (
        len(
            router.routing_history
        )
        == initial_history_length
    )

    assert (
        broker.submitted_orders
        == initial_submissions
    )

    # ==============================================================
    # J.12 RAW EXPLICIT-BROKER ROUTING CONTAINMENT
    # ==============================================================

    try:

        router.route_order(
            order,
            broker_name="PAPER",
        )

        raise AssertionError(
            "Expected RuntimeError"
        )

    except RuntimeError as exc:

        assert (
            "Raw Order routing is disabled"
            in str(exc)
        )

    assert (
        broker.submitted_orders
        == initial_submissions
    )

    # ==============================================================
    # J.12 RAW BATCH ROUTING CONTAINMENT
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

    try:

        router.route_batch(
            orders
        )

        raise AssertionError(
            "Expected RuntimeError"
        )

    except RuntimeError as exc:

        assert (
            "Raw Order batch routing is disabled"
            in str(exc)
        )

    assert (
        broker.submitted_orders
        == initial_submissions
    )

    # ==============================================================
    # EXPLICIT BROKER REGISTRATION
    # ==============================================================

    second_broker = _TestBroker(
        "SECOND"
    )

    router.register_broker(
        second_broker
    )

    assert (
        "SECOND"
        in router.available_brokers()
    )

    # ==============================================================
    # EXPLICIT DEFAULT BROKER
    # ==============================================================

    router.set_default_broker(
        "SECOND"
    )

    assert (
        router.default_broker
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
            _TestBroker(
                "SECOND"
            )
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
            "Raw Order routing is disabled"
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

    # Raw routing must fail closed BEFORE broker health or
    # submission logic is reached.

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
            "Raw Order routing is disabled"
            in str(exc)
        )

    # ==============================================================
    # SERIALIZATION
    # ==============================================================

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

    assert (
        "route_authorized_order"
        in metadata["public_methods"]
    )

    assert (
        metadata["raw_routing_fail_closed"]
        is True
    )

    assert (
        metadata["authorized_routing_required"]
        is True
    )

    assert (
        metadata["production_routing_boundary"]
        == "route_authorized_order"
    )

    # ==============================================================
    # FINAL HEALTH
    # ==============================================================

    unhealthy.healthy = True

    assert router.health_check()

    router.unregister_broker(
        "UNHEALTHY"
    )

    assert router.health_check()

    print(
        "BrokerRouter Phase IV-I-J.12 "
        "raw routing containment tests passed."
    )


# ======================================================================
# MAIN
# ======================================================================


if __name__ == "__main__":
    test_broker_router()