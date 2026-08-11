"""
======================================================================
paperbroker.py

Institutional Paper Broker
======================================================================

Deterministic simulated broker adapter for the institutional
execution architecture.

Responsibilities
----------------

    - receive orders from BrokerRouter
    - maintain broker-side order state
    - validate incoming orders
    - assign broker execution identifiers
    - submit paper orders
    - cancel paper orders
    - simulate deterministic fills
    - maintain execution records
    - maintain broker audit history
    - expose broker health
    - expose metadata
    - provide serialization
    - provide regression tests

The PaperBroker does NOT:

    - generate portfolio targets
    - generate trades
    - perform portfolio optimization
    - perform pre-trade risk checks
    - manage the OMS OrderBook
    - modify PortfolioAccount
    - calculate portfolio-level risk
    - perform live brokerage connectivity

Portfolio accounting remains the responsibility of the
appropriate execution/accounting layer.

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
        v
    PaperBroker
        |
        v
    Execution Receipt

Author: Michael Kazibwe
Version: 1.0.0
======================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Optional

from order import Order
from brokerrouter import BrokerAdapter


# ======================================================================
# PAPER ORDER STATUS
# ======================================================================


class PaperOrderStatus:
    """
    Broker-side paper order states.

    These states are deliberately separate from OrderStatus because
    broker execution state and OMS lifecycle state represent different
    layers of the architecture.
    """

    SUBMITTED = "SUBMITTED"

    PARTIALLY_FILLED = "PARTIALLY_FILLED"

    FILLED = "FILLED"

    CANCEL_PENDING = "CANCEL_PENDING"

    CANCELLED = "CANCELLED"

    REJECTED = "REJECTED"


# ======================================================================
# PAPER ORDER RECORD
# ======================================================================


@dataclass
class PaperOrderRecord:
    """
    Broker-side representation of a submitted paper order.

    This object is owned by the PaperBroker.

    It does not replace the OMS Order object.
    """

    broker_order_id: str

    client_order_id: str

    ticker: str

    side: str

    quantity: float

    status: str

    submitted_price: Optional[float] = None

    average_fill_price: float = 0.0

    filled_quantity: float = 0.0

    remaining_quantity: float = 0.0

    broker: str = "PAPER"

    currency: str = "USD"

    timestamp: str = ""

    last_update: str = ""

    def to_dict(self) -> dict:
        """
        Serialize the paper order record.
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

            "submitted_price":
                self.submitted_price,

            "average_fill_price":
                self.average_fill_price,

            "filled_quantity":
                self.filled_quantity,

            "remaining_quantity":
                self.remaining_quantity,

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
    ) -> PaperOrderRecord:
        """
        Restore a PaperOrderRecord from a dictionary.
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

            submitted_price=data.get(
                "submitted_price"
            ),

            average_fill_price=float(
                data.get(
                    "average_fill_price",
                    0.0,
                )
            ),

            filled_quantity=float(
                data.get(
                    "filled_quantity",
                    0.0,
                )
            ),

            remaining_quantity=float(
                data.get(
                    "remaining_quantity",
                    data[
                        "quantity"
                    ],
                )
            ),

            broker=data.get(
                "broker",
                "PAPER",
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
# PAPER EXECUTION RECEIPT
# ======================================================================


@dataclass(frozen=True)
class PaperExecutionReceipt:
    """
    Deterministic execution receipt produced by the PaperBroker.
    """

    broker_order_id: str

    client_order_id: str

    ticker: str

    side: str

    quantity: float

    execution_price: float

    status: str

    timestamp: str

    broker: str = "PAPER"

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
# PAPER BROKER
# ======================================================================


class PaperBroker(BrokerAdapter):
    """
    Institutional deterministic paper broker.

    The broker implements the BrokerAdapter interface required by
    BrokerRouter.

    It simulates broker-side order handling without connecting to
    external markets.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (
        "submit_order",
        "cancel_order",
        "fill_order",
        "get_order",
        "has_order",
        "active_orders",
        "completed_orders",
        "cancelled_orders",
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
        broker_name: str = "PAPER",
        currency: str = "USD",
    ):
        """
        Initialize the paper broker.

        Parameters
        ----------
        broker_name:
            Unique broker identifier.

        currency:
            Default broker account currency.
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

        self._broker_name = (
            broker_name
        )

        self.currency = currency

        self._healthy = True

        self._sequence = 0

        self.orders: dict[
            str,
            PaperOrderRecord,
        ] = {}

        self.execution_history: list[
            dict
        ] = []

        self.audit_history: list[
            dict
        ] = []

        self.last_order: Optional[
            PaperOrderRecord
        ] = None

        self.last_execution: Optional[
            PaperExecutionReceipt
        ] = None

        self.submission_count = 0

        self.fill_count = 0

        self.cancel_count = 0

    # ==================================================================
    # BROKER NAME
    # ==================================================================

    @property
    def broker_name(self) -> str:
        """
        Return the broker identifier.
        """

        return self._broker_name

    # ==================================================================
    # TIMESTAMP
    # ==================================================================

    @staticmethod
    def _timestamp() -> str:
        """
        Return the current UTC timestamp.
        """

        return datetime.now(
            UTC
        ).isoformat()

    # ==================================================================
    # BROKER ORDER ID
    # ==================================================================

    def _next_broker_order_id(
        self,
    ) -> str:
        """
        Generate a deterministic broker-side order identifier.
        """

        self._sequence += 1

        return (
            f"{self._broker_name}-"
            f"{self._sequence:08d}"
        )

    # ==================================================================
    # ORDER VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_order(
        order: Order,
    ) -> None:
        """
        Validate an incoming OMS Order.
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
    # AUDIT EVENT
    # ==================================================================

    def _record_audit(
        self,
        event: str,
        order: Optional[
            PaperOrderRecord
        ] = None,
        reason: Optional[str] = None,
    ) -> None:
        """
        Record a broker audit event.
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
    # SUBMIT ORDER
    # ==================================================================

    def submit_order(
        self,
        order: Order,
    ) -> dict:
        """
        Submit an order to the paper broker.

        The order is accepted into broker-side state.

        The method does NOT fill the order automatically.

        This deliberate separation allows the execution layer to
        determine the simulated execution price and fill quantity.
        """

        self._validate_order(
            order
        )

        if not self._healthy:
            raise RuntimeError(
                "Paper broker is unhealthy."
            )

        client_order_id = (
            order.order_id
        )

        if client_order_id in {
            record.client_order_id
            for record in self.orders.values()
        }:
            raise ValueError(
                f"Order '{client_order_id}' "
                "has already been submitted."
            )

        timestamp = (
            self._timestamp()
        )

        broker_order_id = (
            self._next_broker_order_id()
        )

        record = PaperOrderRecord(
            broker_order_id=(
                broker_order_id
            ),

            client_order_id=(
                client_order_id
            ),

            ticker=order.ticker,

            side=order.side,

            quantity=float(
                order.quantity
            ),

            status=(
                PaperOrderStatus.SUBMITTED
            ),

            submitted_price=None,

            average_fill_price=0.0,

            filled_quantity=0.0,

            remaining_quantity=float(
                order.quantity
            ),

            broker=self.broker_name,

            currency=(
                getattr(
                    order,
                    "currency",
                    self.currency,
                )
            ),

            timestamp=timestamp,

            last_update=timestamp,
        )

        self.orders[
            broker_order_id
        ] = record

        self.last_order = record

        self.submission_count += 1

        self._record_audit(
            "SUBMIT",
            record,
        )

        return {
            "broker":
                self.broker_name,

            "broker_order_id":
                broker_order_id,

            "client_order_id":
                client_order_id,

            "status":
                record.status,

            "timestamp":
                timestamp,
        }

    # ==================================================================
    # FIND ORDER
    # ==================================================================

    def _find_record(
        self,
        order_id: str,
    ) -> PaperOrderRecord:
        """
        Find an order using either broker or client order ID.
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
            f"Paper order '{order_id}' not found."
        )

    # ==================================================================
    # GET ORDER
    # ==================================================================

    def get_order(
        self,
        order_id: str,
    ) -> PaperOrderRecord:
        """
        Retrieve a paper broker order.
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
        Return whether the broker knows the order.
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
        Cancel a paper order.

        Only submitted or partially filled orders may be cancelled.
        """

        record = self._find_record(
            order_id
        )

        if record.status in (
            PaperOrderStatus.FILLED,
            PaperOrderStatus.CANCELLED,
            PaperOrderStatus.REJECTED,
        ):
            raise RuntimeError(
                f"Order '{record.client_order_id}' "
                f"cannot be cancelled from "
                f"status '{record.status}'."
            )

        timestamp = (
            self._timestamp()
        )

        record.status = (
            PaperOrderStatus.CANCELLED
        )

        record.last_update = timestamp

        self.cancel_count += 1

        self._record_audit(
            "CANCEL",
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
    # FILL ORDER
    # ==================================================================

    def fill_order(
        self,
        order_id: str,
        execution_price: float,
        quantity: Optional[float] = None,
    ) -> PaperExecutionReceipt:
        """
        Simulate a deterministic execution.

        Parameters
        ----------
        order_id:
            Broker or client order identifier.

        execution_price:
            Simulated execution price.

        quantity:
            Quantity to fill.

            If omitted, the entire remaining quantity is filled.

        Important
        ---------

        This method changes ONLY broker-side state.

        It does NOT modify PortfolioAccount.
        """

        if execution_price <= 0:
            raise ValueError(
                "execution_price must be positive."
            )

        record = self._find_record(
            order_id
        )

        if record.status in (
            PaperOrderStatus.FILLED,
            PaperOrderStatus.CANCELLED,
            PaperOrderStatus.REJECTED,
        ):
            raise RuntimeError(
                f"Order '{record.client_order_id}' "
                f"cannot be filled from "
                f"status '{record.status}'."
            )

        fill_quantity = (
            record.remaining_quantity
            if quantity is None
            else float(quantity)
        )

        if fill_quantity <= 0:
            raise ValueError(
                "Fill quantity must be positive."
            )

        if fill_quantity > (
            record.remaining_quantity
        ):
            raise ValueError(
                "Fill quantity exceeds remaining quantity."
            )

        previous_filled = (
            record.filled_quantity
        )

        previous_average = (
            record.average_fill_price
        )

        new_filled = (
            previous_filled
            + fill_quantity
        )

        if previous_filled == 0:

            new_average = (
                execution_price
            )

        else:

            new_average = (
                (
                    previous_average
                    * previous_filled
                )
                + (
                    execution_price
                    * fill_quantity
                )
            ) / new_filled

        record.filled_quantity = (
            new_filled
        )

        record.remaining_quantity = (
            record.quantity
            - new_filled
        )

        record.average_fill_price = (
            new_average
        )

        record.submitted_price = (
            execution_price
        )

        timestamp = (
            self._timestamp()
        )

        if record.remaining_quantity == 0:

            record.status = (
                PaperOrderStatus.FILLED
            )

        else:

            record.status = (
                PaperOrderStatus.PARTIALLY_FILLED
            )

        record.last_update = timestamp

        receipt = PaperExecutionReceipt(
            broker_order_id=(
                record.broker_order_id
            ),

            client_order_id=(
                record.client_order_id
            ),

            ticker=record.ticker,

            side=record.side,

            quantity=fill_quantity,

            execution_price=(
                float(execution_price)
            ),

            status=record.status,

            timestamp=timestamp,

            broker=self.broker_name,
        )

        self.execution_history.append(
            receipt.to_dict()
        )

        self.last_execution = receipt

        self.last_order = record

        self.fill_count += 1

        self._record_audit(
            "FILL",
            record,
        )

        return receipt

    # ==================================================================
    # ACTIVE ORDERS
    # ==================================================================

    def active_orders(
        self,
    ) -> list[PaperOrderRecord]:
        """
        Return broker orders that remain executable.
        """

        return [
            record
            for record in self.orders.values()
            if record.status in (
                PaperOrderStatus.SUBMITTED,
                PaperOrderStatus.PARTIALLY_FILLED,
            )
        ]

    # ==================================================================
    # COMPLETED ORDERS
    # ==================================================================

    def completed_orders(
        self,
    ) -> list[PaperOrderRecord]:
        """
        Return fully filled orders.
        """

        return [
            record
            for record in self.orders.values()
            if record.status
            == PaperOrderStatus.FILLED
        ]

    # ==================================================================
    # CANCELLED ORDERS
    # ==================================================================

    def cancelled_orders(
        self,
    ) -> list[PaperOrderRecord]:
        """
        Return cancelled orders.
        """

        return [
            record
            for record in self.orders.values()
            if record.status
            == PaperOrderStatus.CANCELLED
        ]

    # ==================================================================
    # HEALTH
    # ==================================================================

    def health_check(
        self,
    ) -> bool:
        """
        Return broker health status.
        """

        if self.API_VERSION != "1.0.0":
            raise RuntimeError(
                "Invalid PaperBroker API version."
            )

        if not self.broker_name:
            raise RuntimeError(
                "Paper broker name is empty."
            )

        if not self.currency:
            raise RuntimeError(
                "Paper broker currency is empty."
            )

        if self._sequence < 0:
            raise RuntimeError(
                "Invalid broker sequence."
            )

        for broker_order_id, record in (
            self.orders.items()
        ):

            if (
                broker_order_id
                != record.broker_order_id
            ):
                raise RuntimeError(
                    "Broker order registry mismatch."
                )

            if record.quantity <= 0:
                raise RuntimeError(
                    "Paper order quantity must be positive."
                )

            if record.filled_quantity < 0:
                raise RuntimeError(
                    "Filled quantity cannot be negative."
                )

            if record.remaining_quantity < 0:
                raise RuntimeError(
                    "Remaining quantity cannot be negative."
                )

            if (
                record.filled_quantity
                + record.remaining_quantity
                != record.quantity
            ):
                raise RuntimeError(
                    "Paper order quantity accounting mismatch."
                )

        return bool(
            self._healthy
        )

    # ==================================================================
    # SET HEALTH
    # ==================================================================

    def set_health(
        self,
        healthy: bool,
    ) -> None:
        """
        Set simulated broker health.

        Intended for testing and controlled simulation.
        """

        self._healthy = bool(
            healthy
        )

        self._record_audit(
            "HEALTH_UPDATE",
            reason=(
                "HEALTHY"
                if self._healthy
                else "UNHEALTHY"
            ),
        )

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(
        self,
    ) -> dict:
        """
        Return broker summary statistics.
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

            "registered_orders":
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

            "submission_count":
                self.submission_count,

            "fill_count":
                self.fill_count,

            "cancel_count":
                self.cancel_count,

            "execution_events":
                len(
                    self.execution_history
                ),

            "audit_events":
                len(
                    self.audit_history
                ),

            "last_order_id":
                None
                if self.last_order is None
                else self.last_order.client_order_id,

            "last_broker_order_id":
                None
                if self.last_order is None
                else self.last_order.broker_order_id,
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
                "PaperBroker",

            "api_version":
                self.API_VERSION,

            "broker_name":
                self.broker_name,

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

            "sequence":
                self._sequence,

            "submission_count":
                self.submission_count,

            "fill_count":
                self.fill_count,

            "cancel_count":
                self.cancel_count,

            "orders": {
                key:
                    value.to_dict()
                for key, value
                in self.orders.items()
            },

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
    ) -> PaperBroker:
        """
        Restore PaperBroker state.
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
                "PAPER",
            ),

            currency=data.get(
                "currency",
                "USD",
            ),
        )

        broker._healthy = bool(
            data.get(
                "healthy",
                True,
            )
        )

        broker._sequence = int(
            data.get(
                "sequence",
                0,
            )
        )

        broker.submission_count = int(
            data.get(
                "submission_count",
                0,
            )
        )

        broker.fill_count = int(
            data.get(
                "fill_count",
                0,
            )
        )

        broker.cancel_count = int(
            data.get(
                "cancel_count",
                0,
            )
        )

        broker.orders = {
            key:
                PaperOrderRecord.from_dict(
                    value
                )
            for key, value
            in data.get(
                "orders",
                {},
            ).items()
        }

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

        if broker.orders:

            broker.last_order = (
                list(
                    broker.orders.values()
                )[-1]
            )

        if broker.execution_history:

            broker.last_execution = (
                PaperExecutionReceipt(
                    **broker.execution_history[
                        -1
                    ]
                )
            )

        return broker


# ======================================================================
# REGRESSION TESTS
# ======================================================================


def test_paper_broker():
    """
    Regression tests for PaperBroker.
    """

    # ==============================================================
    # CONSTRUCTION
    # ==============================================================

    broker = PaperBroker()

    assert (
        broker.broker_name
        == "PAPER"
    )

    assert (
        broker.API_VERSION
        == "1.0.0"
    )

    assert broker.health_check()

    assert (
        broker.summary()[
            "registered_orders"
        ]
        == 0
    )

    # ==============================================================
    # ORDER
    # ==============================================================

    order = Order(
        order_id="PAPER-000001",
        ticker="SPY",
        side="BUY",
        quantity=100,
    )

    # ==============================================================
    # SUBMIT
    # ==============================================================

    response = broker.submit_order(
        order
    )

    assert (
        response["broker"]
        == "PAPER"
    )

    assert (
        response["client_order_id"]
        == "PAPER-000001"
    )

    assert (
        response["status"]
        == PaperOrderStatus.SUBMITTED
    )

    broker_order_id = (
        response["broker_order_id"]
    )

    assert broker.has_order(
        "PAPER-000001"
    )

    assert broker.has_order(
        broker_order_id
    )

    assert (
        broker.summary()[
            "active_orders"
        ]
        == 1
    )

    # ==============================================================
    # RETRIEVE
    # ==============================================================

    record = broker.get_order(
        "PAPER-000001"
    )

    assert (
        record.client_order_id
        == "PAPER-000001"
    )

    assert (
        record.quantity
        == 100
    )

    assert (
        record.filled_quantity
        == 0
    )

    assert (
        record.remaining_quantity
        == 100
    )

    assert (
        record.status
        == PaperOrderStatus.SUBMITTED
    )

    # ==============================================================
    # PARTIAL FILL
    # ==============================================================

    partial = broker.fill_order(
        "PAPER-000001",
        execution_price=500.0,
        quantity=40,
    )

    assert (
        partial.status
        == PaperOrderStatus.PARTIALLY_FILLED
    )

    record = broker.get_order(
        "PAPER-000001"
    )

    assert (
        record.filled_quantity
        == 40
    )

    assert (
        record.remaining_quantity
        == 60
    )

    assert (
        record.average_fill_price
        == 500.0
    )

    assert (
        broker.summary()[
            "active_orders"
        ]
        == 1
    )

    # ==============================================================
    # FINAL FILL
    # ==============================================================

    final = broker.fill_order(
        "PAPER-000001",
        execution_price=510.0,
        quantity=60,
    )

    assert (
        final.status
        == PaperOrderStatus.FILLED
    )

    record = broker.get_order(
        "PAPER-000001"
    )

    assert (
        record.filled_quantity
        == 100
    )

    assert (
        record.remaining_quantity
        == 0
    )

    expected_average = (
        (
            40 * 500.0
            + 60 * 510.0
        )
        / 100
    )

    assert (
        record.average_fill_price
        == expected_average
    )

    assert (
        broker.summary()[
            "active_orders"
        ]
        == 0
    )

    assert (
        broker.summary()[
            "completed_orders"
        ]
        == 1
    )

    # ==============================================================
    # SECOND ORDER
    # ==============================================================

    second_order = Order(
        order_id="PAPER-000002",
        ticker="QQQ",
        side="SELL",
        quantity=50,
    )

    second_response = (
        broker.submit_order(
            second_order
        )
    )

    assert (
        second_response["status"]
        == PaperOrderStatus.SUBMITTED
    )

    # ==============================================================
    # CANCEL
    # ==============================================================

    cancelled = broker.cancel_order(
        "PAPER-000002"
    )

    assert (
        cancelled["status"]
        == PaperOrderStatus.CANCELLED
    )

    assert (
        broker.summary()[
            "cancelled_orders"
        ]
        == 1
    )

    # ==============================================================
    # INVALID FILL
    # ==============================================================

    try:

        broker.fill_order(
            "PAPER-000002",
            execution_price=500.0,
        )

        raise AssertionError(
            "Expected RuntimeError"
        )

    except RuntimeError:
        pass

    # ==============================================================
    # DUPLICATE ORDER
    # ==============================================================

    duplicate = Order(
        order_id="PAPER-000001",
        ticker="SPY",
        side="BUY",
        quantity=10,
    )

    try:

        broker.submit_order(
            duplicate
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:
        pass

    # ==============================================================
    # INVALID PRICE
    # ==============================================================

    third_order = Order(
        order_id="PAPER-000003",
        ticker="TLT",
        side="BUY",
        quantity=10,
    )

    broker.submit_order(
        third_order
    )

    try:

        broker.fill_order(
            "PAPER-000003",
            execution_price=0,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:
        pass

    # ==============================================================
    # HEALTH CONTROL
    # ==============================================================

    broker.set_health(
        False
    )

    assert not broker.health_check()

    try:

        broker.submit_order(
            Order(
                order_id="PAPER-000004",
                ticker="GLD",
                side="BUY",
                quantity=5,
            )
        )

        raise AssertionError(
            "Expected RuntimeError"
        )

    except RuntimeError:
        pass

    broker.set_health(
        True
    )

    assert broker.health_check()

    # ==============================================================
    # METADATA
    # ==============================================================

    metadata = broker.metadata

    assert (
        metadata["component"]
        == "PaperBroker"
    )

    assert (
        metadata["api_version"]
        == broker.API_VERSION
    )

    assert (
        "submit_order"
        in metadata["public_methods"]
    )

    assert (
        "fill_order"
        in metadata["public_methods"]
    )

    # ==============================================================
    # SERIALIZATION
    # ==============================================================

    exported = broker.to_dict()

    restored = (
        PaperBroker.from_dict(
            exported
        )
    )

    assert (
        restored.broker_name
        == broker.broker_name
    )

    assert (
        restored.currency
        == broker.currency
    )

    assert (
        restored._sequence
        == broker._sequence
    )

    assert (
        restored.submission_count
        == broker.submission_count
    )

    assert (
        restored.fill_count
        == broker.fill_count
    )

    assert (
        restored.cancel_count
        == broker.cancel_count
    )

    assert (
        restored.orders.keys()
        == broker.orders.keys()
    )

    assert (
        restored.execution_history
        == broker.execution_history
    )

    assert (
        restored.audit_history
        == broker.audit_history
    )

    assert restored.health_check()

    # ==============================================================
    # FINAL SUMMARY
    # ==============================================================

    summary = broker.summary()

    assert (
        summary["api_version"]
        == broker.API_VERSION
    )

    assert (
        summary["broker"]
        == "PAPER"
    )

    assert (
        summary["submission_count"]
        == 3
    )

    assert (
        summary["fill_count"]
        == 2
    )

    assert (
        summary["cancel_count"]
        == 1
    )

    print(
        "PaperBroker Phase III-B.5 tests passed."
    )


# ======================================================================
# MAIN
# ======================================================================


if __name__ == "__main__":
    test_paper_broker()