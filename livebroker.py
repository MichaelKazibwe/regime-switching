"""
======================================================================
livebroker.py

Institutional Live Broker Adapter
======================================================================

Phase III-C.1

Production-oriented broker adapter boundary for live execution.

The LiveBroker implements the BrokerAdapter contract used by
BrokerRouter while deliberately keeping external broker connectivity
behind an isolated transport interface.

Responsibilities
----------------

    - live broker adapter contract
    - broker registration compatibility
    - connection state management
    - authentication boundary
    - broker health checks
    - live order submission boundary
    - live order cancellation boundary
    - broker order status lookup
    - execution receipt normalization
    - broker/client order ID tracking
    - audit trail
    - deterministic test transport
    - serialization
    - metadata
    - health checks
    - regression tests

The LiveBroker does NOT:

    - generate portfolio targets
    - generate trades
    - perform portfolio optimization
    - perform pre-trade portfolio risk calculations
    - manage the OMS OrderBook
    - modify PortfolioAccount
    - calculate portfolio-level transaction costs
    - perform portfolio accounting
    - implement broker-specific API logic directly

External broker connectivity is isolated behind BrokerTransport.

IMPORTANT
---------

Live trading is FAIL-CLOSED.

A LiveBroker instance starts with live trading disabled.

A real order cannot be submitted unless:

    1. the broker is healthy
    2. the broker is connected
    3. authentication is established
    4. live trading has explicitly been enabled
    5. a transport has been configured

The module contains no hard-coded broker credentials.

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
        +------------------+
        |                  |
        v                  v
    PaperBroker        LiveBroker
                           |
                           v
                   BrokerExecutionEngine
                           |
                           v
                    ExecutionEngine
                           |
                           v
                    PortfolioAccount

Author: Michael Kazibwe
Version: 1.0.0
======================================================================
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Optional

from brokerrouter import BrokerAdapter
from order import Order


# ======================================================================
# LIVE ORDER STATUS
# ======================================================================


class LiveOrderStatus:
    """
    Normalized live broker order states.

    These states are intentionally independent from OMS OrderStatus.
    """

    SUBMITTED = "SUBMITTED"

    ACCEPTED = "ACCEPTED"

    PARTIALLY_FILLED = "PARTIALLY_FILLED"

    FILLED = "FILLED"

    CANCEL_PENDING = "CANCEL_PENDING"

    CANCELLED = "CANCELLED"

    REJECTED = "REJECTED"

    UNKNOWN = "UNKNOWN"


# ======================================================================
# BROKER TRANSPORT
# ======================================================================


class BrokerTransport(ABC):
    """
    Abstract external broker transport.

    The LiveBroker depends only on this interface.

    A real broker implementation should provide a concrete transport
    without modifying LiveBroker itself.
    """

    API_VERSION = "1.0.0"

    @abstractmethod
    def connect(self) -> bool:
        """
        Establish broker connectivity.
        """
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> bool:
        """
        Disconnect from broker.
        """
        raise NotImplementedError

    @abstractmethod
    def authenticate(self) -> bool:
        """
        Authenticate with broker.
        """
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> bool:
        """
        Return transport health.
        """
        raise NotImplementedError

    @abstractmethod
    def submit_order(
        self,
        order: Order,
    ) -> dict:
        """
        Submit an order to the external broker.
        """
        raise NotImplementedError

    @abstractmethod
    def cancel_order(
        self,
        broker_order_id: str,
    ) -> dict:
        """
        Cancel a broker-side order.
        """
        raise NotImplementedError

    @abstractmethod
    def get_order(
        self,
        broker_order_id: str,
    ) -> dict:
        """
        Retrieve broker-side order status.
        """
        raise NotImplementedError


# ======================================================================
# LIVE ORDER RECORD
# ======================================================================


@dataclass
class LiveOrderRecord:
    """
    Normalized broker-side live order record.
    """

    broker_order_id: str

    client_order_id: str

    ticker: str

    side: str

    quantity: float

    status: str

    filled_quantity: float = 0.0

    remaining_quantity: float = 0.0

    average_fill_price: float = 0.0

    broker: str = "LIVE"

    currency: str = "USD"

    timestamp: str = ""

    last_update: str = ""

    def to_dict(self) -> dict:
        """
        Serialize the live order record.
        """

        return {
            "broker_order_id":
                self.broker_order_id,

            "client_order_id":
                self.client_order_id,

            "ticker":
                self.ticker,

            "side":
                self.side,

            "quantity":
                self.quantity,

            "status":
                self.status,

            "filled_quantity":
                self.filled_quantity,

            "remaining_quantity":
                self.remaining_quantity,

            "average_fill_price":
                self.average_fill_price,

            "broker":
                self.broker,

            "currency":
                self.currency,

            "timestamp":
                self.timestamp,

            "last_update":
                self.last_update,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> LiveOrderRecord:
        """
        Restore a LiveOrderRecord.
        """

        return cls(
            broker_order_id=data[
                "broker_order_id"
            ],

            client_order_id=data[
                "client_order_id"
            ],

            ticker=data[
                "ticker"
            ],

            side=data[
                "side"
            ],

            quantity=float(
                data[
                    "quantity"
                ]
            ),

            status=data[
                "status"
            ],

            filled_quantity=float(
                data.get(
                    "filled_quantity",
                    0.0,
                )
            ),

            remaining_quantity=float(
                data.get(
                    "remaining_quantity",
                    data["quantity"],
                )
            ),

            average_fill_price=float(
                data.get(
                    "average_fill_price",
                    0.0,
                )
            ),

            broker=data.get(
                "broker",
                "LIVE",
            ),

            currency=data.get(
                "currency",
                "USD",
            ),

            timestamp=data.get(
                "timestamp",
                "",
            ),

            last_update=data.get(
                "last_update",
                "",
            ),
        )


# ======================================================================
# LIVE EXECUTION RECEIPT
# ======================================================================


@dataclass(frozen=True)
class LiveExecutionReceipt:
    """
    Normalized execution receipt.

    This object is immutable once created.
    """

    broker_order_id: str

    client_order_id: str

    ticker: str

    side: str

    quantity: float

    execution_price: float

    status: str

    timestamp: str

    broker: str = "LIVE"

    def to_dict(self) -> dict:
        """
        Serialize the execution receipt.
        """

        return {
            "broker_order_id":
                self.broker_order_id,

            "client_order_id":
                self.client_order_id,

            "ticker":
                self.ticker,

            "side":
                self.side,

            "quantity":
                self.quantity,

            "execution_price":
                self.execution_price,

            "status":
                self.status,

            "timestamp":
                self.timestamp,

            "broker":
                self.broker,
        }


# ======================================================================
# LIVE BROKER
# ======================================================================


class LiveBroker(BrokerAdapter):
    """
    Fail-closed institutional live broker adapter.

    No external broker API is hard-coded into this class.

    A concrete BrokerTransport must be supplied for actual connectivity.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (
        "connect",
        "disconnect",
        "authenticate",
        "enable_live_trading",
        "disable_live_trading",
        "set_transport",
        "submit_order",
        "cancel_order",
        "get_order",
        "has_order",
        "refresh_order",
        "health_check",
        "set_health",
        "active_orders",
        "completed_orders",
        "cancelled_orders",
        "rejected_orders",
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
        broker_name: str = "LIVE",
        currency: str = "USD",
        transport: Optional[
            BrokerTransport
        ] = None,
    ):
        """
        Initialize the live broker.

        Live trading is disabled by default.
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

        if not isinstance(
            currency,
            str,
        ):
            raise TypeError(
                "currency must be a string."
            )

        currency = (
            currency
            .strip()
            .upper()
        )

        if not currency:
            raise ValueError(
                "currency cannot be empty."
            )

        if transport is not None and not isinstance(
            transport,
            BrokerTransport,
        ):
            raise TypeError(
                "transport must implement BrokerTransport."
            )

        self._broker_name = broker_name

        self.currency = currency

        self.transport = transport

        # --------------------------------------------------------------
        # SAFETY STATE
        # --------------------------------------------------------------

        self._healthy = True

        self._connected = False

        self._authenticated = False

        self._live_trading_enabled = False

        # --------------------------------------------------------------
        # ORDER STATE
        # --------------------------------------------------------------

        self.orders: dict[
            str,
            LiveOrderRecord,
        ] = {}

        self.execution_history: list[
            dict
        ] = []

        self.audit_history: list[
            dict
        ] = []

        self.last_order: Optional[
            LiveOrderRecord
        ] = None

        self.last_execution: Optional[
            LiveExecutionReceipt
        ] = None

        self.submission_count = 0

        self.cancel_count = 0

        self.execution_count = 0

    # ==================================================================
    # BROKER NAME
    # ==================================================================

    @property
    def broker_name(
        self,
    ) -> str:
        """
        Return broker identifier.
        """

        return self._broker_name

    # ==================================================================
    # TIMESTAMP
    # ==================================================================

    @staticmethod
    def _timestamp() -> str:
        """
        Return current UTC timestamp.
        """

        return datetime.now(
            UTC
        ).isoformat()

    # ==================================================================
    # TRANSPORT
    # ==================================================================

    def set_transport(
        self,
        transport: BrokerTransport,
    ) -> None:
        """
        Configure the broker transport.

        Setting a new transport resets connection and authentication
        state.
        """

        if not isinstance(
            transport,
            BrokerTransport,
        ):
            raise TypeError(
                "transport must implement BrokerTransport."
            )

        self.transport = transport

        self._connected = False

        self._authenticated = False

        self._record_audit(
            "TRANSPORT_CONFIGURED"
        )

    # ==================================================================
    # CONNECTION
    # ==================================================================

    def connect(self) -> bool:
        """
        Establish broker connectivity.

        Live trading remains disabled after connection until explicitly
        enabled.
        """

        if self.transport is None:
            raise RuntimeError(
                "No broker transport configured."
            )

        if not self._healthy:
            raise RuntimeError(
                "Live broker is unhealthy."
            )

        result = self.transport.connect()

        if not result:
            self._connected = False

            self._record_audit(
                "CONNECT_FAILED"
            )

            raise RuntimeError(
                "Broker transport connection failed."
            )

        self._connected = True

        self._record_audit(
            "CONNECTED"
        )

        return True

    # ==================================================================
    # DISCONNECT
    # ==================================================================

    def disconnect(self) -> bool:
        """
        Disconnect broker transport.

        Live trading is automatically disabled.
        """

        self._live_trading_enabled = False

        self._authenticated = False

        if self.transport is None:
            self._connected = False

            self._record_audit(
                "DISCONNECTED"
            )

            return True

        result = self.transport.disconnect()

        self._connected = False

        self._authenticated = False

        self._record_audit(
            "DISCONNECTED"
        )

        return bool(
            result
        )

    # ==================================================================
    # AUTHENTICATE
    # ==================================================================

    def authenticate(self) -> bool:
        """
        Authenticate with the broker transport.
        """

        if self.transport is None:
            raise RuntimeError(
                "No broker transport configured."
            )

        if not self._connected:
            raise RuntimeError(
                "Broker must be connected before authentication."
            )

        result = self.transport.authenticate()

        if not result:
            self._authenticated = False

            self._record_audit(
                "AUTHENTICATION_FAILED"
            )

            raise RuntimeError(
                "Broker authentication failed."
            )

        self._authenticated = True

        self._record_audit(
            "AUTHENTICATED"
        )

        return True

    # ==================================================================
    # ENABLE LIVE TRADING
    # ==================================================================

    def enable_live_trading(self) -> bool:
        """
        Explicitly enable live order submission.

        All required safety conditions must be satisfied.
        """

        if not self._healthy:
            raise RuntimeError(
                "Cannot enable live trading: broker unhealthy."
            )

        if not self._connected:
            raise RuntimeError(
                "Cannot enable live trading: broker disconnected."
            )

        if not self._authenticated:
            raise RuntimeError(
                "Cannot enable live trading: broker unauthenticated."
            )

        if self.transport is None:
            raise RuntimeError(
                "Cannot enable live trading without transport."
            )

        if not self.transport.health_check():
            raise RuntimeError(
                "Cannot enable live trading: transport unhealthy."
            )

        self._live_trading_enabled = True

        self._record_audit(
            "LIVE_TRADING_ENABLED"
        )

        return True

    # ==================================================================
    # DISABLE LIVE TRADING
    # ==================================================================

    def disable_live_trading(
        self,
    ) -> bool:
        """
        Disable live order submission.
        """

        self._live_trading_enabled = False

        self._record_audit(
            "LIVE_TRADING_DISABLED"
        )

        return True

    # ==================================================================
    # ORDER VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_order(
        order: Order,
    ) -> None:
        """
        Validate incoming Order.
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
    # LIVE ORDER GATE
    # ==================================================================

    def _check_live_submission_gate(
        self,
    ) -> None:
        """
        Enforce fail-closed live submission controls.
        """

        if not self._healthy:
            raise RuntimeError(
                "LIVE_BROKER_UNHEALTHY"
            )

        if not self._connected:
            raise RuntimeError(
                "LIVE_BROKER_DISCONNECTED"
            )

        if not self._authenticated:
            raise RuntimeError(
                "LIVE_BROKER_UNAUTHENTICATED"
            )

        if not self._live_trading_enabled:
            raise RuntimeError(
                "LIVE_TRADING_DISABLED"
            )

        if self.transport is None:
            raise RuntimeError(
                "LIVE_BROKER_NO_TRANSPORT"
            )

        if not self.transport.health_check():
            self._healthy = False

            raise RuntimeError(
                "LIVE_BROKER_TRANSPORT_UNHEALTHY"
            )

    # ==================================================================
    # AUDIT
    # ==================================================================

    def _record_audit(
        self,
        event: str,
        order: Optional[
            LiveOrderRecord
        ] = None,
        reason: Optional[str] = None,
    ) -> None:
        """
        Record broker audit event.
        """

        self.audit_history.append(
            {
                "timestamp":
                    self._timestamp(),

                "event":
                    event,

                "broker":
                    self.broker_name,

                "broker_order_id":
                    None
                    if order is None
                    else order.broker_order_id,

                "client_order_id":
                    None
                    if order is None
                    else order.client_order_id,

                "ticker":
                    None
                    if order is None
                    else order.ticker,

                "status":
                    None
                    if order is None
                    else order.status,

                "reason":
                    reason,
            }
        )

    # ==================================================================
    # NORMALIZE BROKER RESPONSE
    # ==================================================================

    def _normalize_submission_response(
        self,
        order: Order,
        response: dict,
    ) -> LiveOrderRecord:
        """
        Convert broker transport response into a normalized record.
        """

        if not isinstance(
            response,
            dict,
        ):
            raise TypeError(
                "Broker submission response must be a dictionary."
            )

        broker_order_id = response.get(
            "broker_order_id"
        )

        if not broker_order_id:
            raise RuntimeError(
                "Broker response missing broker_order_id."
            )

        timestamp = response.get(
            "timestamp",
            self._timestamp(),
        )

        status = response.get(
            "status",
            LiveOrderStatus.SUBMITTED,
        )

        record = LiveOrderRecord(
            broker_order_id=str(
                broker_order_id
            ),

            client_order_id=order.order_id,

            ticker=order.ticker,

            side=order.side,

            quantity=float(
                order.quantity
            ),

            status=status,

            filled_quantity=float(
                response.get(
                    "filled_quantity",
                    0.0,
                )
            ),

            remaining_quantity=float(
                response.get(
                    "remaining_quantity",
                    order.quantity,
                )
            ),

            average_fill_price=float(
                response.get(
                    "average_fill_price",
                    0.0,
                )
            ),

            broker=self.broker_name,

            currency=getattr(
                order,
                "currency",
                self.currency,
            ),

            timestamp=timestamp,

            last_update=timestamp,
        )

        return record

    # ==================================================================
    # SUBMIT ORDER
    # ==================================================================

    def submit_order(
        self,
        order: Order,
    ) -> dict:
        """
        Submit an order to the live broker.

        This method is fail-closed.
        """

        self._validate_order(
            order
        )

        self._check_live_submission_gate()

        client_order_id = order.order_id

        for record in self.orders.values():

            if (
                record.client_order_id
                == client_order_id
            ):
                raise ValueError(
                    f"Order '{client_order_id}' "
                    "has already been submitted."
                )

        try:

            response = self.transport.submit_order(
                order
            )

        except Exception as exc:

            self._record_audit(
                "SUBMISSION_FAILED",
                reason=str(exc),
            )

            raise RuntimeError(
                f"Live broker submission failed: {exc}"
            ) from exc

        record = self._normalize_submission_response(
            order,
            response,
        )

        self.orders[
            record.broker_order_id
        ] = record

        self.last_order = record

        self.submission_count += 1

        self._record_audit(
            "SUBMITTED",
            record,
        )

        return {
            "broker":
                self.broker_name,

            "broker_order_id":
                record.broker_order_id,

            "client_order_id":
                record.client_order_id,

            "status":
                record.status,

            "timestamp":
                record.timestamp,
        }

    # ==================================================================
    # FIND ORDER
    # ==================================================================

    def _find_record(
        self,
        order_id: str,
    ) -> LiveOrderRecord:
        """
        Find an order by broker or client order ID.
        """

        if not isinstance(
            order_id,
            str,
        ):
            raise TypeError(
                "order_id must be a string."
            )

        if order_id in self.orders:
            return self.orders[
                order_id
            ]

        for record in self.orders.values():

            if (
                record.client_order_id
                == order_id
            ):
                return record

        raise KeyError(
            f"Live order '{order_id}' not found."
        )

    # ==================================================================
    # GET ORDER
    # ==================================================================

    def get_order(
        self,
        order_id: str,
    ) -> LiveOrderRecord:
        """
        Return local normalized order state.
        """

        return self._find_record(
            order_id
        )

    # ==================================================================
    # HAS ORDER
    # ==================================================================

    def has_order(
        self,
        order_id: str,
    ) -> bool:
        """
        Return whether the broker knows the specified order.

        The identifier may be either the broker order ID or the
        client/OMS order ID.
        """

        try:

            self._find_record(
                order_id
            )

            return True

        except KeyError:

            return False

    # ==================================================================
    # CANCEL ORDER
    # ==================================================================

    def cancel_order(
        self,
        order_id: str,
    ) -> dict:
        """
        Cancel a live broker order.
        """

        self._check_live_submission_gate()

        record = self._find_record(
            order_id
        )

        if record.status in (
            LiveOrderStatus.FILLED,
            LiveOrderStatus.CANCELLED,
            LiveOrderStatus.REJECTED,
        ):
            raise RuntimeError(
                f"Order '{record.client_order_id}' "
                f"cannot be cancelled from "
                f"status '{record.status}'."
            )

        try:

            response = self.transport.cancel_order(
                record.broker_order_id
            )

        except Exception as exc:

            self._record_audit(
                "CANCELLATION_FAILED",
                record,
                str(exc),
            )

            raise RuntimeError(
                f"Live broker cancellation failed: {exc}"
            ) from exc

        timestamp = self._timestamp()

        status = response.get(
            "status",
            LiveOrderStatus.CANCELLED,
        )

        record.status = status

        record.last_update = timestamp

        self.cancel_count += 1

        self._record_audit(
            "CANCELLED",
            record,
        )

        return {
            "broker":
                self.broker_name,

            "broker_order_id":
                record.broker_order_id,

            "client_order_id":
                record.client_order_id,

            "status":
                record.status,

            "timestamp":
                timestamp,
        }

    # ==================================================================
    # ORDER STATUS REFRESH
    # ==================================================================

    def refresh_order(
        self,
        order_id: str,
    ) -> LiveOrderRecord:
        """
        Refresh local order state from the broker.
        """

        self._check_live_submission_gate()

        record = self._find_record(
            order_id
        )

        try:

            response = self.transport.get_order(
                record.broker_order_id
            )

        except Exception as exc:

            self._record_audit(
                "STATUS_REFRESH_FAILED",
                record,
                str(exc),
            )

            raise RuntimeError(
                f"Broker order status refresh failed: {exc}"
            ) from exc

        if not isinstance(
            response,
            dict,
        ):
            raise TypeError(
                "Broker order status response must be a dictionary."
            )

        record.status = response.get(
            "status",
            record.status,
        )

        record.filled_quantity = float(
            response.get(
                "filled_quantity",
                record.filled_quantity,
            )
        )

        record.remaining_quantity = float(
            response.get(
                "remaining_quantity",
                record.remaining_quantity,
            )
        )

        record.average_fill_price = float(
            response.get(
                "average_fill_price",
                record.average_fill_price,
            )
        )

        record.last_update = self._timestamp()

        self._record_audit(
            "STATUS_REFRESH",
            record,
        )

        return record

    # ==================================================================
    # HEALTH
    # ==================================================================

    def set_health(
        self,
        healthy: bool,
    ) -> None:
        """
        Set broker health state.

        An unhealthy broker automatically disables live trading.
        """

        self._healthy = bool(
            healthy
        )

        if not self._healthy:
            self._live_trading_enabled = False

        self._record_audit(
            "HEALTH_CHANGED",
            reason=str(
                self._healthy
            ),
        )

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ) -> bool:
        """
        Validate broker and transport health.
        """

        if self.API_VERSION != "1.0.0":
            raise RuntimeError(
                "Invalid LiveBroker API version."
            )

        if not self._healthy:
            raise RuntimeError(
                "Live broker is unhealthy."
            )

        if self.transport is not None:

            if not self.transport.health_check():

                self._healthy = False

                self._live_trading_enabled = False

                raise RuntimeError(
                    "Live broker transport is unhealthy."
                )

        return True

    # ==================================================================
    # ACTIVE ORDERS
    # ==================================================================

    def active_orders(
        self,
    ) -> list[LiveOrderRecord]:
        """
        Return active broker orders.
        """

        return [
            record
            for record in self.orders.values()
            if record.status
            in (
                LiveOrderStatus.SUBMITTED,
                LiveOrderStatus.ACCEPTED,
                LiveOrderStatus.PARTIALLY_FILLED,
                LiveOrderStatus.CANCEL_PENDING,
            )
        ]

    # ==================================================================
    # COMPLETED ORDERS
    # ==================================================================

    def completed_orders(
        self,
    ) -> list[LiveOrderRecord]:
        """
        Return filled orders.
        """

        return [
            record
            for record in self.orders.values()
            if record.status
            == LiveOrderStatus.FILLED
        ]

    # ==================================================================
    # CANCELLED ORDERS
    # ==================================================================

    def cancelled_orders(
        self,
    ) -> list[LiveOrderRecord]:
        """
        Return cancelled orders.
        """

        return [
            record
            for record in self.orders.values()
            if record.status
            == LiveOrderStatus.CANCELLED
        ]

    # ==================================================================
    # REJECTED ORDERS
    # ==================================================================

    def rejected_orders(
        self,
    ) -> list[LiveOrderRecord]:
        """
        Return rejected orders.
        """

        return [
            record
            for record in self.orders.values()
            if record.status
            == LiveOrderStatus.REJECTED
        ]

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(
        self,
    ) -> dict:
        """
        Return broker state summary.
        """

        return {
            "api_version":
                self.API_VERSION,

            "broker":
                self.broker_name,

            "currency":
                self.currency,

            "healthy":
                self._healthy,

            "connected":
                self._connected,

            "authenticated":
                self._authenticated,

            "live_trading_enabled":
                self._live_trading_enabled,

            "transport_configured":
                self.transport is not None,

            "orders":
                len(self.orders),

            "active_orders":
                len(
                    self.active_orders()
                ),

            "completed_orders":
                len(
                    self.completed_orders()
                ),

            "cancelled_orders":
                len(
                    self.cancelled_orders()
                ),

            "rejected_orders":
                len(
                    self.rejected_orders()
                ),

            "submission_count":
                self.submission_count,

            "cancel_count":
                self.cancel_count,

            "execution_count":
                self.execution_count,

            "audit_events":
                len(
                    self.audit_history
                ),
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
                "LiveBroker",

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
    # TO DICTIONARY
    # ==================================================================

    def to_dict(
        self,
    ) -> dict:
        """
        Serialize broker state.

        Transport objects are deliberately excluded.
        """

        return {
            "api_version":
                self.API_VERSION,

            "broker_name":
                self.broker_name,

            "currency":
                self.currency,

            "healthy":
                self._healthy,

            "connected":
                self._connected,

            "authenticated":
                self._authenticated,

            # Never serialize an enabled live state as a trusted
            # executable state.
            "live_trading_enabled":
                False,

            "submission_count":
                self.submission_count,

            "cancel_count":
                self.cancel_count,

            "execution_count":
                self.execution_count,

            "orders":
                [
                    record.to_dict()
                    for record in self.orders.values()
                ],

            "execution_history":
                list(
                    self.execution_history
                ),

            "audit_history":
                list(
                    self.audit_history
                ),
        }

    # ==================================================================
    # FROM DICTIONARY
    # ==================================================================

    @classmethod
    def from_dict(
        cls,
        data: dict,
        transport: Optional[
            BrokerTransport
        ] = None,
    ) -> LiveBroker:
        """
        Restore broker state.

        Live trading is ALWAYS disabled after restoration.
        """

        if not isinstance(
            data,
            dict,
        ):
            raise TypeError(
                "data must be a dictionary."
            )

        broker = cls(
            broker_name=data.get(
                "broker_name",
                "LIVE",
            ),

            currency=data.get(
                "currency",
                "USD",
            ),

            transport=transport,
        )

        broker._healthy = bool(
            data.get(
                "healthy",
                True,
            )
        )

        # Never restore an executable connection state.

        broker._connected = False

        broker._authenticated = False

        broker._live_trading_enabled = False

        broker.submission_count = int(
            data.get(
                "submission_count",
                0,
            )
        )

        broker.cancel_count = int(
            data.get(
                "cancel_count",
                0,
            )
        )

        broker.execution_count = int(
            data.get(
                "execution_count",
                0,
            )
        )

        broker.orders = {}

        for item in data.get(
            "orders",
            [],
        ):

            record = LiveOrderRecord.from_dict(
                item
            )

            broker.orders[
                record.broker_order_id
            ] = record

            broker.last_order = record

        broker.execution_history = list(
            data.get(
                "execution_history",
                [],
            )
        )

        broker.audit_history = list(
            data.get(
                "audit_history",
                [],
            )
        )

        return broker


# ======================================================================
# DETERMINISTIC TEST TRANSPORT
# ======================================================================


class _TestLiveTransport(BrokerTransport):
    """
    Deterministic transport used exclusively by regression tests.

    This class does NOT connect to any external broker.
    """

    def __init__(
        self,
    ):
        self.connected = False

        self.authenticated = False

        self.healthy = True

        self.sequence = 0

        self.orders: dict[
            str,
            dict,
        ] = {}

        self.submitted = []

        self.cancelled = []

    def connect(
        self,
    ) -> bool:

        if not self.healthy:
            return False

        self.connected = True

        return True

    def disconnect(
        self,
    ) -> bool:

        self.connected = False

        self.authenticated = False

        return True

    def authenticate(
        self,
    ) -> bool:

        if not self.connected:
            return False

        if not self.healthy:
            return False

        self.authenticated = True

        return True

    def health_check(
        self,
    ) -> bool:

        return bool(
            self.healthy
        )

    def submit_order(
        self,
        order: Order,
    ) -> dict:

        if not self.connected:
            raise RuntimeError(
                "Transport is disconnected."
            )

        if not self.authenticated:
            raise RuntimeError(
                "Transport is unauthenticated."
            )

        self.sequence += 1

        broker_order_id = (
            f"TESTLIVE-{self.sequence:08d}"
        )

        self.orders[
            broker_order_id
        ] = {
            "broker_order_id":
                broker_order_id,

            "client_order_id":
                order.order_id,

            "status":
                LiveOrderStatus.ACCEPTED,

            "filled_quantity":
                0.0,

            "remaining_quantity":
                float(
                    order.quantity
                ),

            "average_fill_price":
                0.0,
        }

        self.submitted.append(
            order.order_id
        )

        return {
            "broker_order_id":
                broker_order_id,

            "client_order_id":
                order.order_id,

            "status":
                LiveOrderStatus.ACCEPTED,

            "filled_quantity":
                0.0,

            "remaining_quantity":
                float(
                    order.quantity
                ),

            "average_fill_price":
                0.0,

            "timestamp":
                datetime.now(
                    UTC
                ).isoformat(),
        }

    def cancel_order(
        self,
        broker_order_id: str,
    ) -> dict:

        if broker_order_id not in self.orders:
            raise KeyError(
                "Broker order not found."
            )

        record = self.orders[
            broker_order_id
        ]

        record["status"] = (
            LiveOrderStatus.CANCELLED
        )

        self.cancelled.append(
            broker_order_id
        )

        return {
            "broker_order_id":
                broker_order_id,

            "status":
                LiveOrderStatus.CANCELLED,
        }

    def get_order(
        self,
        broker_order_id: str,
    ) -> dict:

        if broker_order_id not in self.orders:
            raise KeyError(
                "Broker order not found."
            )

        return dict(
            self.orders[
                broker_order_id
            ]
        )


# ======================================================================
# REGRESSION TESTS
# ======================================================================


def test_livebroker():
    """
    Phase III-C.1 regression tests.
    """

    transport = _TestLiveTransport()

    broker = LiveBroker(
        broker_name="LIVE",
        currency="USD",
        transport=transport,
    )

    # ==============================================================
    # INITIAL SAFETY STATE
    # ==============================================================

    assert broker.broker_name == "LIVE"

    assert broker._healthy

    assert not broker._connected

    assert not broker._authenticated

    assert not broker._live_trading_enabled

    # ==============================================================
    # LIVE SUBMISSION MUST FAIL CLOSED
    # ==============================================================

    order = Order(
        order_id="LIVE-000001",
        ticker="SPY",
        side="BUY",
        quantity=100,
    )

    try:

        broker.submit_order(
            order
        )

        raise AssertionError(
            "Expected disconnected failure."
        )

    except RuntimeError as exc:

        assert (
            "LIVE_BROKER_DISCONNECTED"
            in str(exc)
        )

    # ==============================================================
    # CONNECT
    # ==============================================================

    assert broker.connect()

    assert broker._connected

    assert not broker._live_trading_enabled

    # ==============================================================
    # AUTHENTICATE
    # ==============================================================

    assert broker.authenticate()

    assert broker._authenticated

    assert not broker._live_trading_enabled

    # ==============================================================
    # ENABLE LIVE TRADING
    # ==============================================================

    assert broker.enable_live_trading()

    assert broker._live_trading_enabled

    # ==============================================================
    # SUBMIT
    # ==============================================================

    response = broker.submit_order(
        order
    )

    assert response is not None

    assert (
        response["client_order_id"]
        == "LIVE-000001"
    )

    assert (
        response["status"]
        == LiveOrderStatus.ACCEPTED
    )

    broker_order_id = (
        response["broker_order_id"]
    )

    assert broker.has_order(
        broker_order_id
    )

    record = broker.get_order(
        broker_order_id
    )

    assert (
        record.client_order_id
        == "LIVE-000001"
    )

    assert (
        record.quantity
        == 100
    )

    assert broker.summary()[
        "submission_count"
    ] == 1

    # ==============================================================
    # DUPLICATE ORDER PROTECTION
    # ==============================================================

    try:

        broker.submit_order(
            order
        )

        raise AssertionError(
            "Expected duplicate order failure."
        )

    except ValueError as exc:

        assert (
            "already been submitted"
            in str(exc)
        )

    # ==============================================================
    # REFRESH ORDER
    # ==============================================================

    refreshed = broker.refresh_order(
        broker_order_id
    )

    assert (
        refreshed.status
        == LiveOrderStatus.ACCEPTED
    )

    # ==============================================================
    # ACTIVE ORDER
    # ==============================================================

    assert len(
        broker.active_orders()
    ) == 1

    # ==============================================================
    # CANCEL
    # ==============================================================

    cancelled = broker.cancel_order(
        broker_order_id
    )

    assert (
        cancelled["status"]
        == LiveOrderStatus.CANCELLED
    )

    assert len(
        broker.cancelled_orders()
    ) == 1

    assert len(
        broker.active_orders()
    ) == 0

    # ==============================================================
    # DISABLE LIVE TRADING
    # ==============================================================

    assert broker.disable_live_trading()

    assert not broker._live_trading_enabled

    # ==============================================================
    # SUBMISSION BLOCKED AFTER DISABLE
    # ==============================================================

    order_two = Order(
        order_id="LIVE-000002",
        ticker="QQQ",
        side="BUY",
        quantity=50,
    )

    try:

        broker.submit_order(
            order_two
        )

        raise AssertionError(
            "Expected live trading disabled failure."
        )

    except RuntimeError as exc:

        assert (
            "LIVE_TRADING_DISABLED"
            in str(exc)
        )

    # ==============================================================
    # RE-ENABLE
    # ==============================================================

    assert broker.enable_live_trading()

    assert broker._live_trading_enabled

    # ==============================================================
    # SECOND ORDER
    # ==============================================================

    response_two = broker.submit_order(
        order_two
    )

    assert (
        response_two["client_order_id"]
        == "LIVE-000002"
    )

    # ==============================================================
    # HEALTH FAILURE
    # ==============================================================

    broker.set_health(
        False
    )

    assert not broker._healthy

    assert not broker._live_trading_enabled

    try:

        broker.health_check()

        raise AssertionError(
            "Expected health failure."
        )

    except RuntimeError as exc:

        assert (
            "unhealthy"
            in str(exc).lower()
        )

    # ==============================================================
    # RESTORE HEALTH
    # ==============================================================

    broker.set_health(
        True
    )

    assert broker.health_check()

    # ==============================================================
    # SERIALIZATION
    # ==============================================================

    exported = broker.to_dict()

    assert (
        exported["api_version"]
        == LiveBroker.API_VERSION
    )

    # Live trading must never be restored as enabled.

    assert (
        exported["live_trading_enabled"]
        is False
    )

    restored = LiveBroker.from_dict(
        exported
    )

    assert (
        restored.broker_name
        == broker.broker_name
    )

    assert (
        restored.currency
        == broker.currency
    )

    assert not restored._live_trading_enabled

    assert not restored._connected

    assert not restored._authenticated

    assert len(
        restored.orders
    ) == len(
        broker.orders
    )

    # ==============================================================
    # METADATA
    # ==============================================================

    metadata = broker.metadata

    assert (
        metadata["component"]
        == "LiveBroker"
    )

    assert (
        metadata["api_version"]
        == LiveBroker.API_VERSION
    )

    assert (
        "submit_order"
        in metadata["public_methods"]
    )

    # ==============================================================
    # SUMMARY
    # ==============================================================

    summary = broker.summary()

    assert (
        summary["api_version"]
        == LiveBroker.API_VERSION
    )

    assert (
        summary["broker"]
        == "LIVE"
    )

    assert (
        summary["transport_configured"]
        is True
    )

    # ==============================================================
    # DISCONNECT SAFETY
    # ==============================================================

    assert broker.disconnect()

    assert not broker._connected

    assert not broker._authenticated

    assert not broker._live_trading_enabled

    print(
        "LiveBroker Phase III-C.1 tests passed."
    )


# ======================================================================
# MAIN
# ======================================================================


if __name__ == "__main__":
    test_livebroker()