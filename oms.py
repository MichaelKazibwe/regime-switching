"""
======================================================================
oms.py

Institutional Order Management System

Central orchestration layer between:

    Order
    OrderStatus
    OrderBook
    ExecutionEngine
    BrokerExecutionEngine
    PortfolioAccount
    AuthorizedOrderIntent
    AuthorizedExecutionHandoff

Responsibilities:

    - order validation
    - order submission
    - submission integrity
    - authorization-provenance validation
    - order lifecycle management
    - authorized execution handoff
    - execution-result lifecycle handling
    - cancellation
    - rejection
    - audit trail
    - serialization
    - health checks

The OMS does NOT:

    - generate portfolio targets
    - calculate transaction costs
    - execute raw orders directly
    - call ExecutionEngine.execute() directly
    - modify portfolio accounting directly
    - create execution authorization
    - create execution handoffs from unauthorized artifacts
    - route orders directly to brokers

Execution architecture:

    AuthorizedOrderIntent
            |
            v
    AuthorizedExecutionHandoff
            |
            v
    OMS authorized execution boundary
            |
            v
    BrokerExecutionEngine
            |
            v
    ExecutionEngine
            |
            v
    PortfolioAccount

The existing ExecutionEngine remains the authoritative
portfolio-accounting execution component.

Phase:
    III-B.1 — Submission Integrity
    IV-I-E — Authorized Order OMS Boundary
    IV-I-J.3 — OMS Authorized Execution Boundary

Author: Michael Kazibwe
======================================================================
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from authorizedorderintent import AuthorizedOrderIntent
from authorizedexecutionhandoff import (
    AuthorizedExecutionHandoff,
    AuthorizedExecutionHandoffError,
)
from brokerexecutionengine import BrokerExecutionEngine
from executionengine import ExecutionEngine
from order import Order
from orderbook import OrderBook
from orderstatus import OrderStatus
from paperbroker import PaperExecutionReceipt
from portfolioaccount import PortfolioAccount
from pretraderiskgate import PreTradeRiskGate, RiskDecision


# ======================================================================
# EXCEPTIONS
# ======================================================================


class OMSAuthorizationError(RuntimeError):
    """
    Raised when an order reaches the OMS without valid
    production authorization provenance.
    """

    pass


# ======================================================================
# OMS
# ======================================================================


class OMS:
    """
    Institutional Order Management System.

    Phase III-B.1 introduces deterministic submission validation
    and rejection handling while preserving the Phase III-A API.

    Phase IV-I-E adds an explicit authorization-aware submission
    boundary through submit_authorized_order().

    Phase IV-I-J.3 adds the authorized execution boundary.

    Raw execution is deliberately fail-closed.

    The OMS may submit and manage orders, but it cannot execute a
    raw Order directly through ExecutionEngine.

    Authorized execution must cross:

        AuthorizedExecutionHandoff
                |
                v
        BrokerExecutionEngine
                |
                v
        ExecutionEngine
    """

    API_VERSION = "1.1.0"

    PHASE = "PHASE IV-I-J.3"

    # ==================================================================
    # REJECTION REASONS
    # ==================================================================

    INVALID_ORDER = "INVALID_ORDER"
    MISSING_ORDER_ID = "MISSING_ORDER_ID"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    INVALID_TICKER = "INVALID_TICKER"
    INVALID_SIDE = "INVALID_SIDE"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    INVALID_ORDER_TYPE = "INVALID_ORDER_TYPE"
    INVALID_LIMIT_PRICE = "INVALID_LIMIT_PRICE"
    INVALID_STOP_PRICE = "INVALID_STOP_PRICE"
    INVALID_STATUS = "INVALID_STATUS"

    # ==================================================================
    # CONSTRUCTOR
    # ==================================================================

    def __init__(
        self,
        order_book: Optional[OrderBook] = None,
        execution_engine: Optional[ExecutionEngine] = None,
        risk_gate: Optional[PreTradeRiskGate] = None,
        broker_execution_engine: Optional[
            BrokerExecutionEngine
        ] = None,
    ) -> None:

        self.order_book = (
            order_book
            if order_book is not None
            else OrderBook()
        )

        # --------------------------------------------------------------
        # AUTHORITATIVE ACCOUNTING ENGINE
        # --------------------------------------------------------------

        self.execution_engine = (
            execution_engine
            if execution_engine is not None
            else ExecutionEngine()
        )

        # --------------------------------------------------------------
        # BROKER EXECUTION RECONCILIATION LAYER
        # --------------------------------------------------------------

        self.broker_execution_engine = (
            broker_execution_engine
            if broker_execution_engine is not None
            else BrokerExecutionEngine(
                execution_engine=self.execution_engine
            )
        )

        # --------------------------------------------------------------
        # PRE-TRADE RISK
        # --------------------------------------------------------------

        self.risk_gate = (
            risk_gate
            if risk_gate is not None
            else PreTradeRiskGate()
        )

        # --------------------------------------------------------------
        # AUDIT STATE
        # --------------------------------------------------------------

        self.order_history: list[dict] = []

        self.last_order: Optional[Order] = None

        self.last_trade = None

        self.last_execution_result = None

        self.last_execution_handoff: Optional[
            AuthorizedExecutionHandoff
        ] = None

        self.last_risk_decision: Optional[
            RiskDecision
        ] = None

        self.last_rejection_reason: Optional[
            str
        ] = None

    # ==================================================================
    # TIMESTAMP
    # ==================================================================

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()

    # ==================================================================
    # AUDIT EVENT
    # ==================================================================

    def _record_event(
        self,
        order: Order,
        previous_status: str,
        new_status: str,
        event: str,
        reason: Optional[str] = None,
    ) -> None:

        self.order_history.append(
            {
                "timestamp": self._timestamp(),
                "order_id": getattr(
                    order,
                    "order_id",
                    None,
                ),
                "ticker": getattr(
                    order,
                    "ticker",
                    None,
                ),
                "previous_status": previous_status,
                "new_status": new_status,
                "event": event,
                "reason": reason,
            }
        )

        self.last_order = order

    # ==================================================================
    # REJECTION EVENT
    # ==================================================================

    def _record_rejection(
        self,
        order: Order,
        reason: str,
        previous_status: Optional[str] = None,
    ) -> Order:

        previous = (
            previous_status
            if previous_status is not None
            else getattr(
                order,
                "status",
                "UNKNOWN",
            )
        )

        order.status = OrderStatus.REJECTED.name

        self.last_rejection_reason = reason

        self._record_event(
            order,
            previous,
            OrderStatus.REJECTED.name,
            "REJECT",
            reason,
        )

        return order

    # ==================================================================
    # VALIDATE ORDER
    # ==================================================================

    @staticmethod
    def _validate_order(
        order: Order,
    ) -> bool:

        if not isinstance(
            order,
            Order,
        ):
            raise TypeError(
                "order must be an Order object."
            )

        if not getattr(
            order,
            "order_id",
            None,
        ):
            raise ValueError(
                OMS.MISSING_ORDER_ID
            )

        if not getattr(
            order,
            "ticker",
            None,
        ):
            raise ValueError(
                OMS.INVALID_TICKER
            )

        if getattr(
            order,
            "quantity",
            0,
        ) <= 0:
            raise ValueError(
                OMS.INVALID_QUANTITY
            )

        if getattr(
            order,
            "side",
            None,
        ) not in (
            "BUY",
            "SELL",
        ):
            raise ValueError(
                OMS.INVALID_SIDE
            )

        if getattr(
            order,
            "order_type",
            None,
        ) not in (
            "MARKET",
            "LIMIT",
            "STOP",
            "STOP_LIMIT",
        ):
            raise ValueError(
                OMS.INVALID_ORDER_TYPE
            )

        # --------------------------------------------------------------
        # LIMIT PRICE
        # --------------------------------------------------------------

        if order.order_type in (
            "LIMIT",
            "STOP_LIMIT",
        ):
            if (
                order.limit_price is None
                or order.limit_price <= 0
            ):
                raise ValueError(
                    OMS.INVALID_LIMIT_PRICE
                )

        # --------------------------------------------------------------
        # STOP PRICE
        # --------------------------------------------------------------

        if order.order_type in (
            "STOP",
            "STOP_LIMIT",
        ):
            if (
                order.stop_price is None
                or order.stop_price <= 0
            ):
                raise ValueError(
                    OMS.INVALID_STOP_PRICE
                )

        order.validate()

        return True

    # ==================================================================
    # VALIDATION REASON
    # ==================================================================

    @staticmethod
    def _validation_reason(
        order: object,
    ) -> str:

        if not isinstance(
            order,
            Order,
        ):
            return OMS.INVALID_ORDER

        if not getattr(
            order,
            "order_id",
            None,
        ):
            return OMS.MISSING_ORDER_ID

        if not getattr(
            order,
            "ticker",
            None,
        ):
            return OMS.INVALID_TICKER

        if getattr(
            order,
            "quantity",
            0,
        ) <= 0:
            return OMS.INVALID_QUANTITY

        if getattr(
            order,
            "side",
            None,
        ) not in (
            "BUY",
            "SELL",
        ):
            return OMS.INVALID_SIDE

        if getattr(
            order,
            "order_type",
            None,
        ) not in (
            "MARKET",
            "LIMIT",
            "STOP",
            "STOP_LIMIT",
        ):
            return OMS.INVALID_ORDER_TYPE

        if order.order_type in (
            "LIMIT",
            "STOP_LIMIT",
        ):
            if (
                order.limit_price is None
                or order.limit_price <= 0
            ):
                return OMS.INVALID_LIMIT_PRICE

        if order.order_type in (
            "STOP",
            "STOP_LIMIT",
        ):
            if (
                order.stop_price is None
                or order.stop_price <= 0
            ):
                return OMS.INVALID_STOP_PRICE

        return OMS.INVALID_ORDER

    # ==================================================================
    # SUBMISSION VALIDATION
    # ==================================================================

    def validate_submission(
        self,
        order: Order,
    ) -> bool:

        try:
            self._validate_order(order)

        except TypeError:
            raise

        except ValueError as exc:

            reason = str(exc)

            valid_reasons = (
                self.MISSING_ORDER_ID,
                self.INVALID_TICKER,
                self.INVALID_QUANTITY,
                self.INVALID_SIDE,
                self.INVALID_ORDER_TYPE,
                self.INVALID_LIMIT_PRICE,
                self.INVALID_STOP_PRICE,
                self.INVALID_ORDER,
            )

            if reason not in valid_reasons:
                reason = self._validation_reason(
                    order
                )

            raise ValueError(
                reason
            ) from exc

        return True

    # ==================================================================
    # CANONICAL ORDER SUBMISSION
    # ==================================================================

    def submit_order(
        self,
        order: Order,
    ) -> Order:
        """
        Canonical OMS submission API.

        This method validates and registers an Order.

        It does NOT:

            - authorize execution;
            - create an execution handoff;
            - route to a broker;
            - execute the order;
            - mutate PortfolioAccount.
        """

        # --------------------------------------------------------------
        # TYPE CHECK
        # --------------------------------------------------------------

        if not isinstance(
            order,
            Order,
        ):
            raise TypeError(
                "order must be an Order object."
            )

        # --------------------------------------------------------------
        # DUPLICATE CHECK
        # --------------------------------------------------------------

        if (
            getattr(
                order,
                "order_id",
                None,
            )
            and self.order_book.has_order(
                order.order_id
            )
        ):

            return self._record_rejection(
                order,
                self.DUPLICATE_ORDER,
                getattr(
                    order,
                    "status",
                    "UNKNOWN",
                ),
            )

        # --------------------------------------------------------------
        # VALIDATION
        # --------------------------------------------------------------

        try:
            self.validate_submission(
                order
            )

        except ValueError as exc:

            reason = str(exc)

            return self._record_rejection(
                order,
                reason,
                getattr(
                    order,
                    "status",
                    "UNKNOWN",
                ),
            )

        # --------------------------------------------------------------
        # VALIDATED
        # --------------------------------------------------------------

        previous_status = order.status

        order.status = (
            OrderStatus.VALIDATED.name
        )

        self._record_event(
            order,
            previous_status,
            order.status,
            "VALIDATE",
        )

        # --------------------------------------------------------------
        # ORDER BOOK
        # --------------------------------------------------------------

        self.order_book.add_order(
            order
        )

        # --------------------------------------------------------------
        # PENDING
        # --------------------------------------------------------------

        previous_status = order.status

        order.status = (
            OrderStatus.PENDING.name
        )

        self._record_event(
            order,
            previous_status,
            order.status,
            "SUBMIT",
        )

        self.last_rejection_reason = None

        return order

    # ==================================================================
    # AUTHORIZED ORDER SUBMISSION
    # ==================================================================

    def submit_authorized_order(
        self,
        intent: AuthorizedOrderIntent,
    ) -> Order:
        """
        Submit an Order through the Phase IV-I-E authorization boundary.

        This establishes authorization provenance for OMS submission.

        It does NOT execute the order.
        """

        # --------------------------------------------------------------
        # TYPE CHECK
        # --------------------------------------------------------------

        if not isinstance(
            intent,
            AuthorizedOrderIntent,
        ):
            raise OMSAuthorizationError(
                (
                    "submit_authorized_order requires an "
                    "AuthorizedOrderIntent."
                )
            )

        # --------------------------------------------------------------
        # AUTHORIZATION / PROVENANCE VALIDATION
        # --------------------------------------------------------------

        try:
            intent.validate()

        except Exception as exc:

            raise OMSAuthorizationError(
                (
                    "Authorized order intent rejected by OMS "
                    "authorization boundary: "
                    f"{exc}"
                )
            ) from exc

        # --------------------------------------------------------------
        # CANONICAL ORDER
        # --------------------------------------------------------------

        order = intent.order

        if not isinstance(
            order,
            Order,
        ):
            raise OMSAuthorizationError(
                (
                    "AuthorizedOrderIntent does not contain "
                    "a canonical Order."
                )
            )

        # --------------------------------------------------------------
        # CANONICAL OMS SUBMISSION
        # --------------------------------------------------------------

        return self.submit_order(
            order
        )

    # ==================================================================
    # AUTHORIZED EXECUTION HANDOFF CREATION
    # ==================================================================

    def create_authorized_execution_handoff(
        self,
        intent: AuthorizedOrderIntent,
    ) -> AuthorizedExecutionHandoff:
        """
        Create the immutable execution handoff from a valid
        AuthorizedOrderIntent.

        This method performs no execution and no broker routing.

        The resulting handoff preserves:

            - exact Order identity;
            - authorization identity;
            - decision identity;
            - regime identity.
        """

        if not isinstance(
            intent,
            AuthorizedOrderIntent,
        ):
            raise OMSAuthorizationError(
                (
                    "create_authorized_execution_handoff "
                    "requires an AuthorizedOrderIntent."
                )
            )

        try:
            handoff = (
                AuthorizedExecutionHandoff.from_intent(
                    intent
                )
            )

        except (
            AuthorizedExecutionHandoffError,
            TypeError,
            ValueError,
            RuntimeError,
        ) as exc:

            raise OMSAuthorizationError(
                (
                    "Authorized execution handoff rejected "
                    "by OMS boundary: "
                    f"{exc}"
                )
            ) from exc

        return handoff

    # ==================================================================
    # PRE-TRADE RISK CHECK
    # ==================================================================

    def check_order_risk(
        self,
        order: Order,
        account: PortfolioAccount,
        execution_price: float,
    ) -> RiskDecision:

        self._validate_order(
            order
        )

        decision = self.risk_gate.check(
            order,
            account,
            execution_price,
        )

        self.last_risk_decision = decision

        self.order_history.append(
            {
                "timestamp": self._timestamp(),
                "order_id": order.order_id,
                "ticker": order.ticker,
                "event": "RISK_CHECK",
                "approved": decision.approved,
                "reason": decision.reason,
            }
        )

        return decision

    # ==================================================================
    # FAIL-CLOSED RAW EXECUTION BOUNDARY
    # ==================================================================

    def execute_order(
        self,
        order_id: str,
        account: PortfolioAccount,
        execution_price: float,
    ):
        """
        Legacy execution entry point.

        IMPORTANT:

            Direct OMS execution is permanently disabled.

        This method is retained only to preserve API compatibility
        with existing callers and to provide an explicit hard stop.

        A raw order_id cannot cross the execution boundary.

        Execution requires:

            AuthorizedExecutionHandoff
                    +
            broker execution receipt
                    |
                    v
            execute_authorized_order()

        This method NEVER calls:

            ExecutionEngine.execute()
            BrokerExecutionEngine.execute_receipt()
        """

        raise OMSAuthorizationError(
            (
                "Direct OMS execution is disabled. "
                "Raw order execution cannot cross the authorized "
                "execution boundary. "
                "Use execute_authorized_order() with an "
                "AuthorizedExecutionHandoff and broker execution receipt."
            )
        )

    # ==================================================================
    # AUTHORIZED EXECUTION
    # ==================================================================

    def execute_authorized_order(
        self,
        handoff: AuthorizedExecutionHandoff,
        receipt: PaperExecutionReceipt,
        account: PortfolioAccount,
    ):
        """
        Execute a broker execution receipt through the authorized
        execution boundary.

        Required chain:

            AuthorizedExecutionHandoff
                    |
                    v
            BrokerExecutionEngine
                    |
                    v
            ExecutionEngine
                    |
                    v
            PortfolioAccount

        The OMS itself does not perform accounting.

        The OMS:

            1. requires a valid handoff;
            2. validates the handoff;
            3. obtains the exact canonical Order;
            4. verifies that the Order belongs to the OMS;
            5. runs the OMS pre-trade risk gate;
            6. delegates execution to BrokerExecutionEngine;
            7. updates OMS lifecycle state;
            8. records complete audit provenance.
        """

        # --------------------------------------------------------------
        # HANDOFF TYPE
        # --------------------------------------------------------------

        if not isinstance(
            handoff,
            AuthorizedExecutionHandoff,
        ):
            raise OMSAuthorizationError(
                (
                    "execute_authorized_order requires an "
                    "AuthorizedExecutionHandoff."
                )
            )

        # --------------------------------------------------------------
        # HANDOFF VALIDATION
        # --------------------------------------------------------------

        try:
            handoff.validate()

        except Exception as exc:

            raise OMSAuthorizationError(
                (
                    "Authorized execution handoff rejected "
                    "by OMS execution boundary: "
                    f"{exc}"
                )
            ) from exc

        # --------------------------------------------------------------
        # CANONICAL ORDER
        # --------------------------------------------------------------

        try:
            order = handoff.execution_order()

        except Exception as exc:

            raise OMSAuthorizationError(
                (
                    "Unable to obtain canonical Order from "
                    "AuthorizedExecutionHandoff: "
                    f"{exc}"
                )
            ) from exc

        if not isinstance(
            order,
            Order,
        ):
            raise OMSAuthorizationError(
                (
                    "AuthorizedExecutionHandoff does not contain "
                    "a canonical Order."
                )
            )

        # --------------------------------------------------------------
        # EXACT OMS ORDER IDENTITY
        # --------------------------------------------------------------

        if not self.order_book.has_order(
            order.order_id
        ):
            raise OMSAuthorizationError(
                (
                    "Authorized execution Order is not registered "
                    "in the OMS OrderBook."
                )
            )

        registered_order = (
            self.order_book.get_order(
                order.order_id
            )
        )

        # Identity, not merely equality, is authoritative.
        if registered_order is not order:
            raise OMSAuthorizationError(
                (
                    "Authorized execution Order identity does not "
                    "match the canonical OMS OrderBook object."
                )
            )

        # --------------------------------------------------------------
        # EXECUTABLE OMS STATE
        # --------------------------------------------------------------

        if order.status not in (
            OrderStatus.PENDING.name,
            OrderStatus.PARTIALLY_FILLED.name,
        ):
            raise RuntimeError(
                (
                    f"Order '{order.order_id}' is not executable "
                    f"from status '{order.status}'."
                )
            )

        # --------------------------------------------------------------
        # RECEIPT TYPE
        # --------------------------------------------------------------

        if not isinstance(
            receipt,
            PaperExecutionReceipt,
        ):
            raise TypeError(
                "receipt must be a PaperExecutionReceipt."
            )

        # --------------------------------------------------------------
        # RECEIPT ORDER IDENTITY
        # --------------------------------------------------------------

        if (
            receipt.client_order_id
            != order.order_id
        ):
            raise OMSAuthorizationError(
                (
                    "Broker execution receipt client_order_id "
                    "does not match the canonical OMS Order identity."
                )
            )

        # --------------------------------------------------------------
        # RECEIPT INSTRUMENT IDENTITY
        # --------------------------------------------------------------

        if receipt.ticker != order.ticker:
            raise OMSAuthorizationError(
                (
                    "Broker execution receipt ticker does not "
                    "match the canonical OMS Order."
                )
            )

        # --------------------------------------------------------------
        # RECEIPT SIDE IDENTITY
        # --------------------------------------------------------------

        if receipt.side != order.side:
            raise OMSAuthorizationError(
                (
                    "Broker execution receipt side does not "
                    "match the canonical OMS Order."
                )
            )

        # --------------------------------------------------------------
        # EXECUTION PRICE
        # --------------------------------------------------------------

        execution_price = float(
            receipt.execution_price
        )

        if execution_price <= 0:
            raise ValueError(
                "Broker execution receipt price must be positive."
            )

        # --------------------------------------------------------------
        # PRE-TRADE RISK
        # --------------------------------------------------------------

        decision = self.check_order_risk(
            order,
            account,
            execution_price,
        )

        if not decision.approved:
            raise RuntimeError(
                (
                    "Pre-trade risk check rejected "
                    f"order '{order.order_id}': "
                    f"{decision.reason}"
                )
            )

        # --------------------------------------------------------------
        # AUDIT — AUTHORIZED EXECUTION
        # --------------------------------------------------------------

        previous_status = order.status

        self.order_history.append(
            {
                "timestamp": self._timestamp(),
                "order_id": order.order_id,
                "ticker": order.ticker,
                "event": "AUTHORIZED_EXECUTION",
                "previous_status": previous_status,
                "decision_id": handoff.decision_id,
                "regime": handoff.regime,
                "authorization": (
                    handoff.authorization.to_dict()
                    if hasattr(
                        handoff.authorization,
                        "to_dict",
                    )
                    else None
                ),
                "receipt": receipt.to_dict(),
            }
        )

        # --------------------------------------------------------------
        # DELEGATE TO BROKER EXECUTION ENGINE
        # --------------------------------------------------------------

        try:
            result = (
                self.broker_execution_engine
                .execute_authorized_receipt(
                    handoff,
                    receipt,
                    account,
                )
            )

        except Exception:
            # Do not fabricate a lifecycle transition when downstream
            # execution failed or was rejected.
            raise

        self.last_execution_result = result

        # --------------------------------------------------------------
        # TRADE RESULT
        # --------------------------------------------------------------

        trade = getattr(
            result,
            "trade",
            None,
        )

        self.last_trade = trade

        # --------------------------------------------------------------
        # EXECUTION RESULT APPROVAL
        # --------------------------------------------------------------

        approved = bool(
            getattr(
                result,
                "approved",
                False,
            )
        )

        if not approved:
            reason = getattr(
                result,
                "reason",
                None,
            )

            raise RuntimeError(
                (
                    "Broker execution boundary rejected "
                    f"order '{order.order_id}': "
                    f"{reason}"
                )
            )

        # --------------------------------------------------------------
        # FILLED
        # --------------------------------------------------------------

        if order.status == (
            OrderStatus.FILLED.name
        ):

            self.order_book.complete_order(
                order.order_id
            )

            self._record_event(
                order,
                previous_status,
                OrderStatus.FILLED.name,
                "AUTHORIZED_FILL",
            )

        # --------------------------------------------------------------
        # PARTIAL FILL
        # --------------------------------------------------------------

        elif order.status == (
            OrderStatus.PARTIALLY_FILLED.name
        ):

            self._record_event(
                order,
                previous_status,
                OrderStatus.PARTIALLY_FILLED.name,
                "AUTHORIZED_PARTIAL_FILL",
            )

        # --------------------------------------------------------------
        # UNEXPECTED STATE
        # --------------------------------------------------------------

        else:

            raise RuntimeError(
                (
                    "Authorized execution produced unexpected "
                    f"order status '{order.status}'."
                )
            )

        # --------------------------------------------------------------
        # FINAL PROVENANCE EVENT
        # --------------------------------------------------------------

        self.order_history.append(
            {
                "timestamp": self._timestamp(),
                "order_id": order.order_id,
                "ticker": order.ticker,
                "event": "AUTHORIZED_EXECUTION_COMPLETE",
                "previous_status": previous_status,
                "new_status": order.status,
                "decision_id": handoff.decision_id,
                "regime": handoff.regime,
                "approved": approved,
                "execution_result": (
                    result.to_dict()
                    if hasattr(
                        result,
                        "to_dict",
                    )
                    else result
                ),
            }
        )

        self.last_execution_handoff = handoff

        return result

    # ==================================================================
    # CANCEL ORDER
    # ==================================================================

    def cancel_order(
        self,
        order_id: str,
        reason: Optional[str] = None,
    ) -> Order:

        order = self.order_book.get_order(
            order_id
        )

        if order.status in (
            OrderStatus.FILLED.name,
            OrderStatus.CANCELLED.name,
            OrderStatus.REJECTED.name,
            OrderStatus.EXPIRED.name,
        ):
            raise RuntimeError(
                (
                    f"Order '{order_id}' cannot be cancelled "
                    f"from status '{order.status}'."
                )
            )

        previous_status = order.status

        cancelled = self.order_book.cancel_order(
            order_id
        )

        self._record_event(
            cancelled,
            previous_status,
            OrderStatus.CANCELLED.name,
            "CANCEL",
            reason,
        )

        return cancelled

    # ==================================================================
    # REJECT EXISTING ORDER
    # ==================================================================

    def reject_order(
        self,
        order_id: str,
        reason: Optional[str] = None,
    ) -> Order:

        order = self.order_book.get_order(
            order_id
        )

        if order.status in (
            OrderStatus.FILLED.name,
            OrderStatus.CANCELLED.name,
            OrderStatus.REJECTED.name,
            OrderStatus.EXPIRED.name,
        ):
            raise RuntimeError(
                (
                    f"Order '{order_id}' cannot be rejected "
                    f"from status '{order.status}'."
                )
            )

        previous_status = order.status

        rejected = self.order_book.reject_order(
            order_id
        )

        self._record_event(
            rejected,
            previous_status,
            OrderStatus.REJECTED.name,
            "REJECT",
            reason,
        )

        self.last_rejection_reason = reason

        return rejected

    # ==================================================================
    # GET ORDER
    # ==================================================================

    def get_order(
        self,
        order_id: str,
    ) -> Order:

        return self.order_book.get_order(
            order_id
        )

    # ==================================================================
    # HAS ORDER
    # ==================================================================

    def has_order(
        self,
        order_id: str,
    ) -> bool:

        return self.order_book.has_order(
            order_id
        )

    # ==================================================================
    # ACTIVE ORDERS
    # ==================================================================

    def active_orders(
        self,
    ):

        return self.order_book.active()

    # ==================================================================
    # COMPLETED ORDERS
    # ==================================================================

    def completed_orders(
        self,
    ):

        return self.order_book.completed()

    # ==================================================================
    # CANCELLED ORDERS
    # ==================================================================

    def cancelled_orders(
        self,
    ):

        return self.order_book.cancelled()

    # ==================================================================
    # REJECTED ORDERS
    # ==================================================================

    def rejected_orders(
        self,
    ):

        return self.order_book.rejected()

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(
        self,
    ):

        return {
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "active_orders": (
                self.order_book.active_count
            ),
            "completed_orders": (
                self.order_book.completed_count
            ),
            "cancelled_orders": (
                self.order_book.cancelled_count
            ),
            "rejected_orders": (
                self.order_book.rejected_count
            ),
            "audit_events": len(
                self.order_history
            ),
            "last_order": (
                None
                if self.last_order is None
                else self.last_order.order_id
            ),
            "last_trade": (
                None
                if self.last_trade is None
                else getattr(
                    self.last_trade,
                    "trade_id",
                    None,
                )
            ),
            "last_execution_result": (
                None
                if self.last_execution_result is None
                else (
                    self.last_execution_result.to_dict()
                    if hasattr(
                        self.last_execution_result,
                        "to_dict",
                    )
                    else self.last_execution_result
                )
            ),
            "last_execution_handoff": (
                None
                if self.last_execution_handoff is None
                else {
                    "order_id": (
                        self.last_execution_handoff.order_id
                    ),
                    "decision_id": (
                        self.last_execution_handoff.decision_id
                    ),
                    "regime": (
                        self.last_execution_handoff.regime
                    ),
                    "authorized": (
                        self.last_execution_handoff.authorized
                    ),
                }
            ),
            "last_risk_decision": (
                None
                if self.last_risk_decision is None
                else self.last_risk_decision.to_dict()
            ),
            "last_rejection_reason": (
                self.last_rejection_reason
            ),
        }

    # ==================================================================
    # METADATA
    # ==================================================================

    @property
    def metadata(
        self,
    ):

        return {
            "component": "OMS",
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "summary": self.summary(),
        }

    # ==================================================================
    # PUBLIC METHODS
    # ==================================================================

    @property
    def public_methods(
        self,
    ):

        return [
            "submit_order",
            "submit_authorized_order",
            "create_authorized_execution_handoff",
            "validate_submission",
            "execute_order",
            "execute_authorized_order",
            "check_order_risk",
            "cancel_order",
            "reject_order",
            "get_order",
            "has_order",
            "active_orders",
            "completed_orders",
            "cancelled_orders",
            "rejected_orders",
            "summary",
            "health_check",
            "to_dict",
            "from_dict",
        ]

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ):

        # --------------------------------------------------------------
        # ACCOUNTING ENGINE
        # --------------------------------------------------------------

        if self.execution_engine is None:
            raise RuntimeError(
                "ExecutionEngine is unavailable."
            )

        self.execution_engine.health_check()

        # --------------------------------------------------------------
        # BROKER EXECUTION ENGINE
        # --------------------------------------------------------------

        if (
            self.broker_execution_engine
            is None
        ):
            raise RuntimeError(
                "BrokerExecutionEngine is unavailable."
            )

        self.broker_execution_engine.health_check()

        # --------------------------------------------------------------
        # RISK GATE
        # --------------------------------------------------------------

        if not hasattr(
            self.risk_gate,
            "check",
        ):
            raise RuntimeError(
                "PreTradeRiskGate is unavailable."
            )

        # --------------------------------------------------------------
        # ACTIVE ORDERS
        # --------------------------------------------------------------

        for order in self.order_book.active():

            order.validate()

            if order.status not in (
                OrderStatus.NEW.name,
                OrderStatus.VALIDATED.name,
                OrderStatus.PENDING.name,
                OrderStatus.PARTIALLY_FILLED.name,
                OrderStatus.SUSPENDED.name,
            ):
                raise RuntimeError(
                    (
                        "Invalid active order state: "
                        f"{order.status}"
                    )
                )

        return True

    # ==================================================================
    # TO DICTIONARY
    # ==================================================================

    def to_dict(
        self,
    ):

        return {
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "order_book": self.order_book.to_dict(),
            "execution_engine": self.execution_engine.to_dict(),
            "broker_execution_engine": self.broker_execution_engine.to_dict(),
            "order_history": list(
                self.order_history
            ),
            "last_order": (
                None
                if self.last_order is None
                else self.last_order.to_dict()
            ),
            "last_rejection_reason": (
                self.last_rejection_reason
            ),
            "summary": self.summary(),
        }

    # ==================================================================
    # FROM DICTIONARY
    # ==================================================================

    @classmethod
    def from_dict(
        cls,
        data,
    ):

        if not isinstance(
            data,
            dict,
        ):
            raise TypeError(
                "OMS data must be a dictionary."
            )

        oms = cls()

        execution_engine_data = data.get("execution_engine")
        broker_execution_data = data.get("broker_execution_engine")
        if execution_engine_data is not None:
            oms.execution_engine = ExecutionEngine.from_dict(execution_engine_data)
        if broker_execution_data is not None:
            oms.broker_execution_engine = BrokerExecutionEngine.from_dict(
                broker_execution_data,
                execution_engine=oms.execution_engine,
            )

        # Older snapshots only contained the OMS summary. New snapshots
        # retain canonical orders in every lifecycle bucket so restart
        # recovery does not lose open or completed order state.
        if data.get("order_book") is not None:
            oms.order_book = OrderBook.from_dict(data["order_book"])

        oms.order_history = list(
            data.get(
                "order_history",
                [],
            )
        )

        last_order = data.get(
            "last_order"
        )

        if last_order is not None:
            last_id = last_order.get("order_id")
            if last_id is not None and oms.order_book.has_order(last_id):
                oms.last_order = oms.order_book.get_order(last_id)
            else:
                oms.last_order = Order.from_dict(last_order)

        oms.last_rejection_reason = (
            data.get(
                "last_rejection_reason"
            )
        )

        return oms


# ======================================================================
# REGRESSION TESTS
# ======================================================================


def test_oms():
    """
    OMS regression tests.

    Phase III-B.1:
        - submission
        - validation
        - lifecycle
        - cancellation
        - rejection
        - risk

    Phase IV-I-E:
        - authorized submission boundary

    Phase IV-I-J.3:
        - raw execution hard stop
        - authorized execution boundary
        - exact Order identity
        - broker execution delegation
        - authorization provenance
    """

    # ==================================================================
    # FIXTURES
    # ==================================================================

    oms = OMS()
    risk_oms = OMS()

    account = PortfolioAccount(
        initial_cash=100000.0
    )

    restricted_account = PortfolioAccount(
        initial_cash=1000.0
    )

    # ==================================================================
    # PRE-TRADE RISK APPROVAL
    # ==================================================================

    approved_order = Order(
        order_id="OMS-RISK-000001",
        ticker="SPY",
        side="BUY",
        quantity=10,
    )

    submitted = risk_oms.submit_order(
        approved_order
    )

    assert submitted is approved_order

    decision = risk_oms.check_order_risk(
        approved_order,
        account,
        500.0,
    )

    assert decision.approved
    assert decision.reason is None
    assert decision.order_id == (
        "OMS-RISK-000001"
    )
    assert (
        risk_oms.last_risk_decision
        is decision
    )

    # ==================================================================
    # PRE-TRADE RISK REJECTION
    # ==================================================================

    rejected_order = Order(
        order_id="OMS-RISK-000002",
        ticker="SPY",
        side="BUY",
        quantity=10,
    )

    risk_oms.submit_order(
        rejected_order
    )

    decision = risk_oms.check_order_risk(
        rejected_order,
        restricted_account,
        500.0,
    )

    assert not decision.approved

    assert decision.reason == (
        PreTradeRiskGate.INSUFFICIENT_CASH
    )

    # Raw execution must now fail closed.
    try:

        risk_oms.execute_order(
            order_id="OMS-RISK-000002",
            account=restricted_account,
            execution_price=500.0,
        )

        raise AssertionError(
            "Expected OMSAuthorizationError"
        )

    except OMSAuthorizationError as exc:

        assert (
            "Direct OMS execution is disabled"
            in str(exc)
        )

        assert (
            rejected_order.filled_quantity
            == 0.0
        )

        assert (
            restricted_account.cash
            == 1000.0
        )

    # ==================================================================
    # VALID SUBMISSION
    # ==================================================================

    order = Order(
        order_id="OMS-000001",
        ticker="SPY",
        side="BUY",
        quantity=100,
    )

    submitted = oms.submit_order(
        order
    )

    assert submitted is order
    assert order.status == (
        OrderStatus.PENDING.name
    )

    assert oms.has_order(
        "OMS-000001"
    )

    assert oms.summary()[
        "active_orders"
    ] == 1

    assert (
        oms.last_rejection_reason
        is None
    )

    # ==================================================================
    # RAW EXECUTION MUST BE BLOCKED
    # ==================================================================

    try:

        oms.execute_order(
            order_id="OMS-000001",
            account=account,
            execution_price=500.0,
        )

        raise AssertionError(
            "Raw OMS execution bypass was not blocked."
        )

    except OMSAuthorizationError as exc:

        assert (
            "Direct OMS execution is disabled"
            in str(exc)
        )

    # Order/accounting must remain untouched.
    assert order.status == (
        OrderStatus.PENDING.name
    )

    assert account.cash == (
        100000.0
    )

    assert (
        order.filled_quantity
        == 0.0
    )

    # ==================================================================
    # CANCEL ORDER
    # ==================================================================

    cancel_order = Order(
        order_id="OMS-000002",
        ticker="QQQ",
        side="BUY",
        quantity=50,
    )

    oms.submit_order(
        cancel_order
    )

    cancelled = oms.cancel_order(
        "OMS-000002",
        reason="Regression test cancellation",
    )

    assert cancelled is cancel_order
    assert cancel_order.status == (
        OrderStatus.CANCELLED.name
    )
    assert oms.summary()[
        "cancelled_orders"
    ] == 1

    # ==================================================================
    # REJECT EXISTING ORDER
    # ==================================================================

    reject_order = Order(
        order_id="OMS-000003",
        ticker="TLT",
        side="BUY",
        quantity=20,
    )

    oms.submit_order(
        reject_order
    )

    rejected = oms.reject_order(
        "OMS-000003",
        reason="Regression test rejection",
    )

    assert rejected is reject_order
    assert reject_order.status == (
        OrderStatus.REJECTED.name
    )
    assert oms.summary()[
        "rejected_orders"
    ] == 1

    # ==================================================================
    # AUDIT TRAIL
    # ==================================================================

    assert len(
        oms.order_history
    ) >= 6

    assert (
        oms.order_history[0]["event"]
        == "VALIDATE"
    )

    assert (
        oms.order_history[1]["event"]
        == "SUBMIT"
    )

    # ==================================================================
    # INVALID TICKER
    # ==================================================================

    invalid_ticker = Order(
        order_id="OMS-INVALID-001",
        ticker="SPY",
        side="BUY",
        quantity=10,
    )
    # Deliberately corrupt the canonical identity for this negative test.
    # Order.__setattr__ correctly prevents normal mutation of identity
    # fields, so object.__setattr__ is used only for this invalid-boundary
    # regression fixture.
    object.__setattr__(
        invalid_ticker,
        "ticker",
        "",
    )

    rejected_invalid_ticker = (
        oms.submit_order(
            invalid_ticker
        )
    )

    assert (
        rejected_invalid_ticker
        is invalid_ticker
    )

    assert invalid_ticker.status == (
        OrderStatus.REJECTED.name
    )

    assert (
        oms.last_rejection_reason
        == OMS.INVALID_TICKER
    )

    assert not oms.order_book.active_orders.get(
        "OMS-INVALID-001"
    )

    assert (
        oms.order_history[-1]["event"]
        == "REJECT"
    )

    assert (
        oms.order_history[-1]["reason"]
        == OMS.INVALID_TICKER
    )

    # ==================================================================
    # INVALID SIDE
    # ==================================================================

    invalid_side = Order(
        order_id="OMS-INVALID-002",
        ticker="SPY",
        side="BUY",
        quantity=10,
    )
    object.__setattr__(
        invalid_side,
        "side",
        "LONG",
    )

    oms.submit_order(
        invalid_side
    )

    assert invalid_side.status == (
        OrderStatus.REJECTED.name
    )

    assert (
        oms.last_rejection_reason
        == OMS.INVALID_SIDE
    )

    # ==================================================================
    # INVALID QUANTITY
    # ==================================================================

    invalid_quantity = Order(
        order_id="OMS-INVALID-003",
        ticker="SPY",
        side="BUY",
        quantity=10,
    )
    object.__setattr__(
        invalid_quantity,
        "quantity",
        0,
    )

    oms.submit_order(
        invalid_quantity
    )

    assert invalid_quantity.status == (
        OrderStatus.REJECTED.name
    )

    assert (
        oms.last_rejection_reason
        == OMS.INVALID_QUANTITY
    )

    # ==================================================================
    # INVALID ORDER TYPE
    # ==================================================================

    invalid_type = Order(
        order_id="OMS-INVALID-004",
        ticker="SPY",
        side="BUY",
        quantity=10,
    )
    object.__setattr__(
        invalid_type,
        "order_type",
        "INVALID",
    )

    oms.submit_order(
        invalid_type
    )

    assert invalid_type.status == (
        OrderStatus.REJECTED.name
    )

    assert (
        oms.last_rejection_reason
        == OMS.INVALID_ORDER_TYPE
    )

    # ==================================================================
    # INVALID LIMIT PRICE
    # ==================================================================

    invalid_limit = Order(
        order_id="OMS-INVALID-005",
        ticker="SPY",
        side="BUY",
        quantity=10,
        order_type="LIMIT",
        limit_price=100.0,
    )
    invalid_limit.limit_price = None

    oms.submit_order(
        invalid_limit
    )

    assert invalid_limit.status == (
        OrderStatus.REJECTED.name
    )

    assert (
        oms.last_rejection_reason
        == OMS.INVALID_LIMIT_PRICE
    )

    # ==================================================================
    # DUPLICATE ORDER
    # ==================================================================

    duplicate = Order(
        order_id="OMS-000001",
        ticker="SPY",
        side="BUY",
        quantity=10,
    )

    duplicate_result = oms.submit_order(
        duplicate
    )

    assert duplicate_result is duplicate

    assert duplicate.status == (
        OrderStatus.REJECTED.name
    )

    assert (
        oms.last_rejection_reason
        == OMS.DUPLICATE_ORDER
    )

    # Existing order remains unchanged.
    assert (
        oms.get_order(
            "OMS-000001"
        )
        is order
    )

    assert order.status == (
        OrderStatus.PENDING.name
    )

    # ==================================================================
    # REJECTED SUBMISSIONS DO NOT ENTER ORDER BOOK
    # ==================================================================

    assert not oms.has_order(
        "OMS-INVALID-001"
    )

    assert not oms.has_order(
        "OMS-INVALID-002"
    )

    assert not oms.has_order(
        "OMS-INVALID-003"
    )

    assert not oms.has_order(
        "OMS-INVALID-004"
    )

    assert not oms.has_order(
        "OMS-INVALID-005"
    )

    # ==================================================================
    # AUDIT REJECTION EVENTS
    # ==================================================================

    rejection_events = [
        event
        for event in oms.order_history
        if event["event"] == "REJECT"
    ]

    assert len(
        rejection_events
    ) >= 6

    # ==================================================================
    # SERIALIZATION
    # ==================================================================

    exported = oms.to_dict()

    assert exported[
        "api_version"
    ] == OMS.API_VERSION

    assert exported[
        "last_rejection_reason"
    ] == OMS.DUPLICATE_ORDER

    restored = OMS.from_dict(
        exported
    )

    assert (
        restored.order_history
        == oms.order_history
    )

    assert restored.last_order is not None

    assert (
        restored.last_order.order_id
        == oms.last_order.order_id
    )

    assert (
        restored.last_rejection_reason
        == oms.last_rejection_reason
    )

    # ==================================================================
    # HEALTH
    # ==================================================================

    assert oms.health_check()

    # ==================================================================
    # PUBLIC API
    # ==================================================================

    assert (
        "submit_order"
        in oms.public_methods
    )

    assert (
        "submit_authorized_order"
        in oms.public_methods
    )

    assert (
        "create_authorized_execution_handoff"
        in oms.public_methods
    )

    assert (
        "validate_submission"
        in oms.public_methods
    )

    assert (
        "execute_order"
        in oms.public_methods
    )

    assert (
        "execute_authorized_order"
        in oms.public_methods
    )

    # ==================================================================
    # SUMMARY
    # ==================================================================

    metadata = oms.metadata

    assert metadata[
        "component"
    ] == "OMS"

    assert metadata[
        "api_version"
    ] == OMS.API_VERSION

    summary = oms.summary()

    assert summary[
        "api_version"
    ] == OMS.API_VERSION

    assert summary[
        "completed_orders"
    ] == 0

    assert summary[
        "cancelled_orders"
    ] == 1

    assert summary[
        "rejected_orders"
    ] == 1

    print(
        "OMS Phase III-B.1 / IV-I-E / IV-I-J.3 tests passed."
    )


# ======================================================================
# MAIN
# ======================================================================


if __name__ == "__main__":

    test_oms()
