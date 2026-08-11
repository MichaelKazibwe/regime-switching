"""
======================================================================
brokerexecutionengine.py

Institutional Broker Execution Engine
======================================================================

Phase III-B.6

Bridges broker-side execution receipts with the institutional
ExecutionEngine and PortfolioAccount.

Architecture
------------

    Order
       |
       v
    OMS
       |
       v
    BrokerRouter
       |
       v
    PaperBroker / LiveBroker
       |
       v
    BrokerExecutionEngine
       |
       v
    ExecutionEngine
       |
       v
    PortfolioAccount


Responsibilities
----------------

    - validate broker execution receipts
    - reconcile broker order identifiers
    - reconcile client order identifiers
    - validate execution quantities
    - validate execution prices
    - prevent duplicate execution processing
    - maintain execution reconciliation history
    - delegate accounting to ExecutionEngine
    - preserve deterministic execution state
    - support full fills
    - support partial broker receipts when the underlying
      ExecutionEngine supports quantity-aware execution
    - provide execution audit trail
    - provide metadata
    - provide serialization
    - provide health checks
    - provide regression tests

The BrokerExecutionEngine does NOT:

    - generate portfolio targets
    - generate trades
    - perform portfolio optimization
    - perform pre-trade risk checks
    - manage the OMS OrderBook
    - route orders to brokers
    - calculate transaction costs independently
    - directly modify PortfolioAccount
    - replace ExecutionEngine accounting logic

The existing ExecutionEngine remains the authoritative
portfolio-accounting execution component.

Author: Michael Kazibwe
Version: 1.0.0
======================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import inspect
from typing import Any, Optional

from executionengine import ExecutionEngine
from order import Order
from paperbroker import (
    PaperBroker,
    PaperExecutionReceipt,
)
from portfolioaccount import PortfolioAccount


# ======================================================================
# EXECUTION RECONCILIATION STATUS
# ======================================================================


class BrokerExecutionStatus:
    """
    Reconciliation states maintained by BrokerExecutionEngine.
    """

    RECEIVED = "RECEIVED"

    VALIDATED = "VALIDATED"

    EXECUTED = "EXECUTED"

    PARTIALLY_EXECUTED = "PARTIALLY_EXECUTED"

    REJECTED = "REJECTED"

    DUPLICATE = "DUPLICATE"

    FAILED = "FAILED"


# ======================================================================
# BROKER EXECUTION RESULT
# ======================================================================


@dataclass(frozen=True)
class BrokerExecutionResult:
    """
    Immutable result of broker execution reconciliation.
    """

    approved: bool

    status: str

    broker: Optional[str]

    broker_order_id: Optional[str]

    client_order_id: Optional[str]

    ticker: Optional[str]

    side: Optional[str]

    quantity: float

    execution_price: float

    reason: Optional[str]

    execution_id: Optional[str]

    timestamp: str

    trade: Any = None

    receipt: Optional[dict] = None

    def to_dict(self) -> dict:
        """
        Serialize the broker execution result.
        """

        trade_data = self.trade

        if hasattr(
            trade_data,
            "to_dict",
        ):
            trade_data = trade_data.to_dict()

        return {
            "approved": self.approved,
            "status": self.status,
            "broker": self.broker,
            "broker_order_id": self.broker_order_id,
            "client_order_id": self.client_order_id,
            "ticker": self.ticker,
            "side": self.side,
            "quantity": self.quantity,
            "execution_price": self.execution_price,
            "reason": self.reason,
            "execution_id": self.execution_id,
            "timestamp": self.timestamp,
            "trade": trade_data,
            "receipt": self.receipt,
        }


# ======================================================================
# BROKER EXECUTION ENGINE
# ======================================================================


class BrokerExecutionEngine:
    """
    Institutional broker execution reconciliation layer.

    This component receives broker-side execution information and
    delegates actual portfolio/accounting execution to ExecutionEngine.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (
        "execute_receipt",
        "fill_and_execute",
        "reconcile_receipt",
        "get_execution",
        "has_execution",
        "execution_history",
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
        execution_engine: Optional[
            ExecutionEngine
        ] = None,
    ):
        """
        Initialize the BrokerExecutionEngine.

        Parameters
        ----------
        execution_engine:
            Existing institutional ExecutionEngine.

        The supplied ExecutionEngine remains responsible for all
        PortfolioAccount accounting.
        """

        self.execution_engine = (
            execution_engine
            if execution_engine is not None
            else ExecutionEngine()
        )

        self.execution_history_records: list[
            dict
        ] = []

        self.execution_registry: dict[
            str,
            BrokerExecutionResult,
        ] = {}

        self.last_result: Optional[
            BrokerExecutionResult
        ] = None

        self.execution_count = 0

        self.success_count = 0

        self.partial_count = 0

        self.rejection_count = 0

        self.failure_count = 0

        self.duplicate_count = 0

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
    # EXECUTION ID
    # ==================================================================

    @staticmethod
    def _execution_id(
        broker_order_id: str,
        client_order_id: str,
        timestamp: str,
    ) -> str:
        """
        Generate a deterministic execution identifier.

        The identifier is based on broker order identity, client order
        identity and receipt timestamp.
        """

        normalized_broker = str(
            broker_order_id
        ).strip()

        normalized_client = str(
            client_order_id
        ).strip()

        normalized_timestamp = str(
            timestamp
        ).strip()

        return (
            f"{normalized_broker}:"
            f"{normalized_client}:"
            f"{normalized_timestamp}"
        )

    # ==================================================================
    # RECEIPT VALIDATION
    # ==================================================================

    @staticmethod
    def validate_receipt(
        receipt: PaperExecutionReceipt,
    ) -> bool:
        """
        Validate a broker execution receipt.
        """

        if not isinstance(
            receipt,
            PaperExecutionReceipt,
        ):
            raise TypeError(
                "receipt must be a "
                "PaperExecutionReceipt."
            )

        if not receipt.broker_order_id:
            raise ValueError(
                "Receipt must contain broker_order_id."
            )

        if not receipt.client_order_id:
            raise ValueError(
                "Receipt must contain client_order_id."
            )

        if not receipt.ticker:
            raise ValueError(
                "Receipt must contain ticker."
            )

        if receipt.side not in (
            "BUY",
            "SELL",
        ):
            raise ValueError(
                "Receipt side must be BUY or SELL."
            )

        if receipt.quantity <= 0:
            raise ValueError(
                "Receipt quantity must be positive."
            )

        if receipt.execution_price <= 0:
            raise ValueError(
                "Receipt execution_price must be positive."
            )

        if not receipt.status:
            raise ValueError(
                "Receipt must contain status."
            )

        return True

    # ==================================================================
    # ORDER VALIDATION
    # ==================================================================

    @staticmethod
    def validate_order(
        order: Order,
    ) -> bool:
        """
        Validate an OMS Order before reconciliation.
        """

        if not isinstance(
            order,
            Order,
        ):
            raise TypeError(
                "order must be an Order object."
            )

        order.validate()

        return True

    # ==================================================================
    # ACCOUNT VALIDATION
    # ==================================================================

    @staticmethod
    def validate_account(
        account: PortfolioAccount,
    ) -> bool:
        """
        Validate the portfolio account.
        """

        if not isinstance(
            account,
            PortfolioAccount,
        ):
            raise TypeError(
                "account must be a PortfolioAccount."
            )

        account.health_check()

        return True

    # ==================================================================
    # RECEIPT DICTIONARY
    # ==================================================================

    @staticmethod
    def _receipt_to_dict(
        receipt: PaperExecutionReceipt,
    ) -> dict:
        """
        Safely serialize a receipt.
        """

        if hasattr(
            receipt,
            "to_dict",
        ):
            return receipt.to_dict()

        return {
            "broker_order_id":
                receipt.broker_order_id,

            "client_order_id":
                receipt.client_order_id,

            "ticker":
                receipt.ticker,

            "side":
                receipt.side,

            "quantity":
                receipt.quantity,

            "execution_price":
                receipt.execution_price,

            "status":
                receipt.status,

            "timestamp":
                receipt.timestamp,

            "broker":
                receipt.broker,
        }

    # ==================================================================
    # ORDER / RECEIPT RECONCILIATION
    # ==================================================================

    def reconcile_receipt(
        self,
        order: Order,
        receipt: PaperExecutionReceipt,
    ) -> bool:
        """
        Verify that a broker receipt corresponds to the OMS order.
        """

        self.validate_order(
            order
        )

        self.validate_receipt(
            receipt
        )

        if (
            receipt.client_order_id
            != order.order_id
        ):
            raise ValueError(
                "Broker receipt client_order_id "
                "does not match OMS order_id."
            )

        if receipt.ticker != order.ticker:
            raise ValueError(
                "Broker receipt ticker does not "
                "match OMS order ticker."
            )

        if receipt.side != order.side:
            raise ValueError(
                "Broker receipt side does not "
                "match OMS order side."
            )

        if receipt.quantity > (
            float(order.quantity)
        ):
            raise ValueError(
                "Broker execution quantity cannot "
                "exceed OMS order quantity."
            )

        return True

    # ==================================================================
    # EXECUTION KEY
    # ==================================================================

    @staticmethod
    def _registry_key(
        receipt: PaperExecutionReceipt,
    ) -> str:
        """
        Return the primary broker execution registry key.

        Broker order ID is the authoritative identity for the
        broker-side execution lifecycle.
        """

        return (
            f"{receipt.broker}:"
            f"{receipt.broker_order_id}:"
            f"{receipt.client_order_id}"
        )

    # ==================================================================
    # DUPLICATE CHECK
    # ==================================================================

    def has_execution(
        self,
        execution_key: str,
    ) -> bool:
        """
        Return whether an execution has already been processed.
        """

        return (
            execution_key
            in self.execution_registry
        )

    # ==================================================================
    # GET EXECUTION
    # ==================================================================

    def get_execution(
        self,
        execution_key: str,
    ) -> BrokerExecutionResult:
        """
        Retrieve a previously processed execution.
        """

        if execution_key not in (
            self.execution_registry
        ):
            raise KeyError(
                f"Execution '{execution_key}' not found."
            )

        return self.execution_registry[
            execution_key
        ]

    # ==================================================================
    # RECORD RESULT
    # ==================================================================

    def _record_result(
        self,
        result: BrokerExecutionResult,
        execution_key: Optional[str] = None,
    ) -> None:
        """
        Record execution result in the reconciliation registry.
        """

        self.last_result = result

        self.execution_history_records.append(
            result.to_dict()
        )

        if execution_key is not None:
            self.execution_registry[
                execution_key
            ] = result

        if result.approved:

            if (
                result.status
                == BrokerExecutionStatus.EXECUTED
            ):

                self.success_count += 1

            elif (
                result.status
                == BrokerExecutionStatus.PARTIALLY_EXECUTED
            ):

                self.partial_count += 1

        elif (
            result.status
            == BrokerExecutionStatus.DUPLICATE
        ):

            self.duplicate_count += 1

        elif (
            result.status
            == BrokerExecutionStatus.REJECTED
        ):

            self.rejection_count += 1

        elif (
            result.status
            == BrokerExecutionStatus.FAILED
        ):

            self.failure_count += 1

    # ==================================================================
    # EXECUTION ENGINE CAPABILITY
    # ==================================================================

    def _supports_quantity_execution(
        self,
    ) -> bool:
        """
        Determine whether the underlying ExecutionEngine supports
        an explicit execution quantity.

        This avoids assuming a newer ExecutionEngine signature while
        remaining compatible with the existing three-argument API.
        """

        execute_method = getattr(
            self.execution_engine,
            "execute",
            None,
        )

        if execute_method is None:
            raise AttributeError(
                "ExecutionEngine does not expose execute()."
            )

        try:
            signature = inspect.signature(
                execute_method
            )

        except (
            TypeError,
            ValueError,
        ):

            return False

        parameters = signature.parameters

        if "quantity" in parameters:
            return True

        if "fill_quantity" in parameters:
            return True

        return False

    # ==================================================================
    # DELEGATE EXECUTION
    # ==================================================================

    def _delegate_execution(
        self,
        order: Order,
        account: PortfolioAccount,
        execution_price: float,
        quantity: float,
    ):
        """
        Delegate actual accounting execution to ExecutionEngine.

        No PortfolioAccount mutation is performed here.
        """

        execute_method = getattr(
            self.execution_engine,
            "execute",
            None,
        )

        if execute_method is None:
            raise AttributeError(
                "ExecutionEngine does not expose execute()."
            )

        full_quantity = float(
            order.quantity
        )

        requested_quantity = float(
            quantity
        )

        # --------------------------------------------------------------
        # FULL EXECUTION
        # --------------------------------------------------------------

        if requested_quantity == full_quantity:

            return execute_method(
                order,
                account,
                execution_price,
            )

        # --------------------------------------------------------------
        # PARTIAL EXECUTION
        # --------------------------------------------------------------

        if self._supports_quantity_execution():

            parameters = inspect.signature(
                execute_method
            ).parameters

            if "quantity" in parameters:

                return execute_method(
                    order,
                    account,
                    execution_price,
                    quantity=requested_quantity,
                )

            if "fill_quantity" in parameters:

                return execute_method(
                    order,
                    account,
                    execution_price,
                    fill_quantity=requested_quantity,
                )

        raise RuntimeError(
            "Underlying ExecutionEngine does not support "
            "quantity-aware partial execution."
        )

    # ==================================================================
    # EXECUTE RECEIPT
    # ==================================================================

    def execute_receipt(
        self,
        order: Order,
        receipt: PaperExecutionReceipt,
        account: PortfolioAccount,
    ) -> BrokerExecutionResult:
        """
        Reconcile a broker execution receipt and delegate the
        accounting operation to ExecutionEngine.
        """

        timestamp = self._timestamp()

        # --------------------------------------------------------------
        # VALIDATION
        # --------------------------------------------------------------

        try:

            self.validate_order(
                order
            )

            self.validate_receipt(
                receipt
            )

            self.validate_account(
                account
            )

            self.reconcile_receipt(
                order,
                receipt,
            )

        except (
            TypeError,
            ValueError,
            RuntimeError,
        ) as exc:

            result = BrokerExecutionResult(

                approved=False,

                status=(
                    BrokerExecutionStatus.REJECTED
                ),

                broker=getattr(
                    receipt,
                    "broker",
                    None,
                ),

                broker_order_id=getattr(
                    receipt,
                    "broker_order_id",
                    None,
                ),

                client_order_id=getattr(
                    receipt,
                    "client_order_id",
                    None,
                ),

                ticker=getattr(
                    receipt,
                    "ticker",
                    None,
                ),

                side=getattr(
                    receipt,
                    "side",
                    None,
                ),

                quantity=float(
                    getattr(
                        receipt,
                        "quantity",
                        0.0,
                    )
                ),

                execution_price=float(
                    getattr(
                        receipt,
                        "execution_price",
                        0.0,
                    )
                ),

                reason=str(
                    exc
                ),

                execution_id=None,

                timestamp=timestamp,

                trade=None,

                receipt=(
                    self._receipt_to_dict(
                        receipt
                    )
                    if isinstance(
                        receipt,
                        PaperExecutionReceipt,
                    )
                    else None
                ),
            )

            self._record_result(
                result
            )

            raise RuntimeError(
                f"Broker execution receipt rejected: {exc}"
            ) from exc

        # --------------------------------------------------------------
        # EXECUTION IDENTITY
        # --------------------------------------------------------------

        execution_key = (
            self._registry_key(
                receipt
            )
        )

        execution_id = (
            self._execution_id(
                receipt.broker_order_id,
                receipt.client_order_id,
                receipt.timestamp,
            )
        )

        # --------------------------------------------------------------
        # DUPLICATE EXECUTION
        # --------------------------------------------------------------

        if self.has_execution(
            execution_key
        ):

            self.duplicate_count += 1

            result = BrokerExecutionResult(

                approved=False,

                status=(
                    BrokerExecutionStatus.DUPLICATE
                ),

                broker=receipt.broker,

                broker_order_id=(
                    receipt.broker_order_id
                ),

                client_order_id=(
                    receipt.client_order_id
                ),

                ticker=receipt.ticker,

                side=receipt.side,

                quantity=float(
                    receipt.quantity
                ),

                execution_price=float(
                    receipt.execution_price
                ),

                reason="DUPLICATE_EXECUTION",

                execution_id=execution_id,

                timestamp=timestamp,

                trade=None,

                receipt=(
                    receipt.to_dict()
                ),
            )

            self.last_result = result

            self.execution_history_records.append(
                result.to_dict()
            )

            raise RuntimeError(
                "Duplicate broker execution detected."
            )

        # --------------------------------------------------------------
        # RECEIVED
        # --------------------------------------------------------------

        self.execution_count += 1

        # --------------------------------------------------------------
        # EXECUTION STATUS VALIDATION
        # --------------------------------------------------------------

        if receipt.status not in (
            "FILLED",
            "PARTIALLY_FILLED",
        ):

            result = BrokerExecutionResult(

                approved=False,

                status=(
                    BrokerExecutionStatus.REJECTED
                ),

                broker=receipt.broker,

                broker_order_id=(
                    receipt.broker_order_id
                ),

                client_order_id=(
                    receipt.client_order_id
                ),

                ticker=receipt.ticker,

                side=receipt.side,

                quantity=float(
                    receipt.quantity
                ),

                execution_price=float(
                    receipt.execution_price
                ),

                reason=(
                    "UNSUPPORTED_EXECUTION_STATUS"
                ),

                execution_id=execution_id,

                timestamp=timestamp,

                trade=None,

                receipt=(
                    receipt.to_dict()
                ),
            )

            self._record_result(
                result,
                execution_key,
            )

            raise RuntimeError(
                "Broker receipt does not represent "
                "an executable fill."
            )

        # --------------------------------------------------------------
        # DELEGATE TO EXECUTION ENGINE
        # --------------------------------------------------------------

        try:

            trade = self._delegate_execution(

                order,

                account,

                receipt.execution_price,

                receipt.quantity,

            )

        except Exception as exc:

            result = BrokerExecutionResult(

                approved=False,

                status=(
                    BrokerExecutionStatus.FAILED
                ),

                broker=receipt.broker,

                broker_order_id=(
                    receipt.broker_order_id
                ),

                client_order_id=(
                    receipt.client_order_id
                ),

                ticker=receipt.ticker,

                side=receipt.side,

                quantity=float(
                    receipt.quantity
                ),

                execution_price=float(
                    receipt.execution_price
                ),

                reason=str(
                    exc
                ),

                execution_id=execution_id,

                timestamp=timestamp,

                trade=None,

                receipt=(
                    receipt.to_dict()
                ),
            )

            self._record_result(
                result
            )

            raise RuntimeError(
                f"Broker execution delegation failed: {exc}"
            ) from exc

        # --------------------------------------------------------------
        # DETERMINE RECONCILIATION STATUS
        # --------------------------------------------------------------

        if receipt.status == "FILLED":

            reconciliation_status = (
                BrokerExecutionStatus.EXECUTED
            )

        else:

            reconciliation_status = (
                BrokerExecutionStatus.PARTIALLY_EXECUTED
            )

        # --------------------------------------------------------------
        # FINAL RESULT
        # --------------------------------------------------------------

        result = BrokerExecutionResult(

            approved=True,

            status=reconciliation_status,

            broker=receipt.broker,

            broker_order_id=(
                receipt.broker_order_id
            ),

            client_order_id=(
                receipt.client_order_id
            ),

            ticker=receipt.ticker,

            side=receipt.side,

            quantity=float(
                receipt.quantity
            ),

            execution_price=float(
                receipt.execution_price
            ),

            reason=None,

            execution_id=execution_id,

            timestamp=timestamp,

            trade=trade,

            receipt=(
                receipt.to_dict()
            ),

        )

        self._record_result(
            result,
            execution_key,
        )

        return result

    # ==================================================================
    # FILL AND EXECUTE
    # ==================================================================

    def fill_and_execute(
        self,
        broker: PaperBroker,
        order: Order,
        account: PortfolioAccount,
        execution_price: float,
        quantity: Optional[float] = None,
    ) -> BrokerExecutionResult:
        """
        Fill an order at the broker and immediately reconcile the
        resulting broker receipt through the ExecutionEngine.

        This method is the main integration path for PaperBroker.
        """

        if not isinstance(
            broker,
            PaperBroker,
        ):
            raise TypeError(
                "broker must be a PaperBroker."
            )

        self.validate_order(
            order
        )

        self.validate_account(
            account
        )

        if execution_price <= 0:
            raise ValueError(
                "execution_price must be positive."
            )

        receipt = broker.fill_order(

            order.order_id,

            execution_price,

            quantity,

        )

        return self.execute_receipt(

            order,

            receipt,

            account,

        )

    # ==================================================================
    # EXECUTION HISTORY
    # ==================================================================

    def execution_history(
        self,
    ) -> list[dict]:
        """
        Return a copy of the execution reconciliation history.
        """

        return list(
            self.execution_history_records
        )

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(
        self,
    ) -> dict:
        """
        Return execution engine state.
        """

        return {

            "api_version":
                self.API_VERSION,

            "execution_count":
                self.execution_count,

            "successful_executions":
                self.success_count,

            "partial_executions":
                self.partial_count,

            "rejections":
                self.rejection_count,

            "failures":
                self.failure_count,

            "duplicates":
                self.duplicate_count,

            "execution_events":
                len(
                    self.execution_history_records
                ),

            "registered_executions":
                len(
                    self.execution_registry
                ),

            "last_execution_id":
                None
                if self.last_result is None
                else self.last_result.execution_id,

            "last_status":
                None
                if self.last_result is None
                else self.last_result.status,

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
                "BrokerExecutionEngine",

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
        Validate BrokerExecutionEngine health.
        """

        if self.API_VERSION != "1.0.0":
            raise RuntimeError(
                "Invalid BrokerExecutionEngine API version."
            )

        if not hasattr(
            self.execution_engine,
            "execute",
        ):
            raise RuntimeError(
                "ExecutionEngine.execute() is unavailable."
            )

        health_check = getattr(
            self.execution_engine,
            "health_check",
            None,
        )

        if health_check is not None:
            health_check()

        return True

    # ==================================================================
    # TO DICTIONARY
    # ==================================================================

    def to_dict(
        self,
    ) -> dict:
        """
        Serialize broker execution state.

        The ExecutionEngine itself is deliberately not serialized.
        It remains a runtime dependency.
        """

        return {

            "api_version":
                self.API_VERSION,

            "execution_count":
                self.execution_count,

            "success_count":
                self.success_count,

            "partial_count":
                self.partial_count,

            "rejection_count":
                self.rejection_count,

            "failure_count":
                self.failure_count,

            "duplicate_count":
                self.duplicate_count,

            "execution_history":
                list(
                    self.execution_history_records
                ),

            "execution_registry":
                {
                    key:
                        value.to_dict()
                    for key, value
                    in self.execution_registry.items()
                },

            "last_result":
                None
                if self.last_result is None
                else self.last_result.to_dict(),

        }

    # ==================================================================
    # FROM DICTIONARY
    # ==================================================================

    @classmethod
    def from_dict(
        cls,
        data: dict,
        execution_engine: Optional[
            ExecutionEngine
        ] = None,
    ) -> BrokerExecutionEngine:
        """
        Restore BrokerExecutionEngine state.

        A runtime ExecutionEngine may be supplied separately.
        """

        if not isinstance(
            data,
            dict,
        ):
            raise TypeError(
                "data must be a dictionary."
            )

        engine = cls(
            execution_engine=execution_engine
        )

        engine.execution_count = int(
            data.get(
                "execution_count",
                0,
            )
        )

        engine.success_count = int(
            data.get(
                "success_count",
                0,
            )
        )

        engine.partial_count = int(
            data.get(
                "partial_count",
                0,
            )
        )

        engine.rejection_count = int(
            data.get(
                "rejection_count",
                0,
            )
        )

        engine.failure_count = int(
            data.get(
                "failure_count",
                0,
            )
        )

        engine.duplicate_count = int(
            data.get(
                "duplicate_count",
                0,
            )
        )

        engine.execution_history_records = list(
            data.get(
                "execution_history",
                [],
            )
        )

        # --------------------------------------------------------------
        # Restore registry as serialized dictionaries.
        #
        # We intentionally do not attempt to reconstruct the original
        # Trade object because the ExecutionEngine remains the runtime
        # owner of trade/accounting objects.
        # --------------------------------------------------------------

        registry_data = data.get(
            "execution_registry",
            {},
        )

        for key, value in registry_data.items():

            if not isinstance(
                value,
                dict,
            ):
                continue

            result = BrokerExecutionResult(

                approved=bool(
                    value.get(
                        "approved",
                        False,
                    )
                ),

                status=value.get(
                    "status",
                    BrokerExecutionStatus.FAILED,
                ),

                broker=value.get(
                    "broker"
                ),

                broker_order_id=value.get(
                    "broker_order_id"
                ),

                client_order_id=value.get(
                    "client_order_id"
                ),

                ticker=value.get(
                    "ticker"
                ),

                side=value.get(
                    "side"
                ),

                quantity=float(
                    value.get(
                        "quantity",
                        0.0,
                    )
                ),

                execution_price=float(
                    value.get(
                        "execution_price",
                        0.0,
                    )
                ),

                reason=value.get(
                    "reason"
                ),

                execution_id=value.get(
                    "execution_id"
                ),

                timestamp=value.get(
                    "timestamp",
                    "",
                ),

                trade=value.get(
                    "trade"
                ),

                receipt=value.get(
                    "receipt"
                ),

            )

            engine.execution_registry[
                key
            ] = result

        # --------------------------------------------------------------
        # Restore last result
        # --------------------------------------------------------------

        last_result = data.get(
            "last_result"
        )

        if isinstance(
            last_result,
            dict,
        ):

            engine.last_result = (
                BrokerExecutionResult(

                    approved=bool(
                        last_result.get(
                            "approved",
                            False,
                        )
                    ),

                    status=last_result.get(
                        "status",
                        BrokerExecutionStatus.FAILED,
                    ),

                    broker=last_result.get(
                        "broker"
                    ),

                    broker_order_id=last_result.get(
                        "broker_order_id"
                    ),

                    client_order_id=last_result.get(
                        "client_order_id"
                    ),

                    ticker=last_result.get(
                        "ticker"
                    ),

                    side=last_result.get(
                        "side"
                    ),

                    quantity=float(
                        last_result.get(
                            "quantity",
                            0.0,
                        )
                    ),

                    execution_price=float(
                        last_result.get(
                            "execution_price",
                            0.0,
                        )
                    ),

                    reason=last_result.get(
                        "reason"
                    ),

                    execution_id=last_result.get(
                        "execution_id"
                    ),

                    timestamp=last_result.get(
                        "timestamp",
                        "",
                    ),

                    trade=last_result.get(
                        "trade"
                    ),

                    receipt=last_result.get(
                        "receipt"
                    ),

                )
            )

        return engine


# ======================================================================
# REGRESSION TESTS
# ======================================================================


def test_broker_execution_engine():
    """
    Deterministic Phase III-B.6 regression tests.
    """

    # ==================================================================
    # IMPORTS
    # ==================================================================

    from paperbroker import PaperBroker

    # ==================================================================
    # ACCOUNT
    # ==================================================================

    account = PortfolioAccount(
        initial_cash=100_000.0
    )

    # ==================================================================
    # BROKER
    # ==================================================================

    broker = PaperBroker()

    # ==================================================================
    # EXECUTION ENGINE
    # ==================================================================

    execution_engine = ExecutionEngine()

    bridge = BrokerExecutionEngine(
        execution_engine=execution_engine
    )

    # ==================================================================
    # HEALTH
    # ==================================================================

    assert bridge.health_check()

    # ==================================================================
    # ORDER
    # ==================================================================

    order = Order(

        order_id="BEE-000001",

        ticker="SPY",

        side="BUY",

        quantity=100,

    )

    # ==================================================================
    # BROKER SUBMISSION
    # ==================================================================

    submission = broker.submit_order(
        order
    )

    assert submission[
        "client_order_id"
    ] == order.order_id

    assert broker.has_order(
        order.order_id
    )

    # ==================================================================
    # BROKER FILL
    # ==================================================================

    receipt = broker.fill_order(

        order.order_id,

        execution_price=500.0,

    )

    assert receipt is not None

    assert receipt.client_order_id == (
        order.order_id
    )

    assert receipt.quantity == 100

    assert receipt.execution_price == 500.0

    assert receipt.status == "FILLED"

    # ==================================================================
    # RECONCILIATION
    # ==================================================================

    result = bridge.execute_receipt(

        order,

        receipt,

        account,

    )

    assert result.approved

    assert result.status == (
        BrokerExecutionStatus.EXECUTED
    )

    assert result.broker == "PAPER"

    assert (
        result.client_order_id
        == order.order_id
    )

    assert result.broker_order_id == (
        receipt.broker_order_id
    )

    assert result.quantity == 100.0

    assert result.execution_price == 500.0

    assert result.execution_id is not None

    assert result.trade is not None

    # ==================================================================
    # ACCOUNTING HANDOFF
    # ==================================================================

    assert account.positions[
        "SPY"
    ].shares == 100

    # ==================================================================
    # EXECUTION REGISTRY
    # ==================================================================

    execution_key = (
        bridge._registry_key(
            receipt
        )
    )

    assert bridge.has_execution(
        execution_key
    )

    stored = bridge.get_execution(
        execution_key
    )

    assert stored.execution_id == (
        result.execution_id
    )

    # ==================================================================
    # DUPLICATE PROTECTION
    # ==================================================================

    try:

        bridge.execute_receipt(

            order,

            receipt,

            account,

        )

        raise AssertionError(
            "Expected duplicate execution rejection."
        )

    except RuntimeError as exc:

        assert (
            "Duplicate broker execution"
            in str(exc)
        )

    # ==================================================================
    # SECOND ORDER
    # ==================================================================

    second_order = Order(

        order_id="BEE-000002",

        ticker="QQQ",

        side="BUY",

        quantity=50,

    )

    broker.submit_order(
        second_order
    )

    second_receipt = broker.fill_order(

        second_order.order_id,

        execution_price=400.0,

    )

    second_result = (
        bridge.execute_receipt(

            second_order,

            second_receipt,

            account,

        )
    )

    assert second_result.approved

    assert second_result.status == (
        BrokerExecutionStatus.EXECUTED
    )

    assert account.positions[
        "QQQ"
    ].shares == 50

    # ==================================================================
    # MISMATCHED CLIENT ORDER
    # ==================================================================

    mismatched_order = Order(

        order_id="BEE-000003",

        ticker="TLT",

        side="BUY",

        quantity=10,

    )

    try:

        bridge.execute_receipt(

            mismatched_order,

            second_receipt,

            account,

        )

        raise AssertionError(
            "Expected receipt/order mismatch."
        )

    except RuntimeError as exc:

        assert (
            "Broker execution receipt rejected"
            in str(exc)
        )

    # ==================================================================
    # INVALID PRICE
    # ==================================================================

    invalid_order = Order(

        order_id="BEE-000004",

        ticker="GLD",

        side="BUY",

        quantity=10,

    )

    invalid_receipt = PaperExecutionReceipt(

        broker_order_id="PAPER-99999999",

        client_order_id="BEE-000004",

        ticker="GLD",

        side="BUY",

        quantity=10,

        execution_price=-1.0,

        status="FILLED",

        timestamp=(
            datetime.now(
                UTC
            ).isoformat()
        ),

    )

    try:

        bridge.execute_receipt(

            invalid_order,

            invalid_receipt,

            account,

        )

        raise AssertionError(
            "Expected invalid price rejection."
        )

    except RuntimeError as exc:

        assert (
            "execution_price"
            in str(exc)
        )

    # ==================================================================
    # SERIALIZATION
    # ==================================================================

    exported = bridge.to_dict()

    assert exported[
        "api_version"
    ] == BrokerExecutionEngine.API_VERSION

    assert exported[
        "execution_count"
    ] >= 2

    restored = (
        BrokerExecutionEngine.from_dict(
            exported,
            execution_engine=ExecutionEngine(),
        )
    )

    assert restored.execution_count == (
        bridge.execution_count
    )

    assert len(
        restored.execution_registry
    ) == len(
        bridge.execution_registry
    )

    # ==================================================================
    # SUMMARY
    # ==================================================================

    summary = bridge.summary()

    assert summary[
        "api_version"
    ] == BrokerExecutionEngine.API_VERSION

    assert summary[
        "successful_executions"
    ] >= 2

    assert summary[
        "duplicates"
    ] >= 1

    assert summary[
        "registered_executions"
    ] >= 2

    # ==================================================================
    # METADATA
    # ==================================================================

    metadata = bridge.metadata

    assert metadata[
        "component"
    ] == "BrokerExecutionEngine"

    assert metadata[
        "api_version"
    ] == BrokerExecutionEngine.API_VERSION

    assert "execute_receipt" in (
        metadata[
            "public_methods"
        ]
    )

    # ==================================================================
    # HISTORY
    # ==================================================================

    history = (
        bridge.execution_history()
    )

    assert len(history) >= 2

    # ==================================================================
    # NO DIRECT ACCOUNTING BY BRIDGE
    # ==================================================================

    assert account.positions[
        "SPY"
    ].shares == 100

    assert account.positions[
        "QQQ"
    ].shares == 50

    # ==================================================================
    # FINAL
    # ==================================================================

    print(
        "BrokerExecutionEngine Phase III-B.6 tests passed."
    )


# ======================================================================
# MAIN
# ======================================================================


if __name__ == "__main__":

    test_broker_execution_engine()