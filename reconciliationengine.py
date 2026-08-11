"""
======================================================================
reconciliationengine.py

Institutional Execution Reconciliation Engine
======================================================================

Phase III-C.2

The ReconciliationEngine provides the post-routing control boundary
between:

    OMS
    BrokerRouter
    PaperBroker
    LiveBroker
    BrokerExecutionEngine
    PortfolioAccount

Responsibilities
----------------

    - reconcile OMS order state against broker state
    - reconcile broker execution quantities
    - reconcile execution prices
    - reconcile order lifecycle state
    - identify missing broker orders
    - identify missing OMS orders
    - identify quantity discrepancies
    - identify price discrepancies
    - identify status discrepancies
    - identify account-position discrepancies
    - produce deterministic reconciliation decisions
    - maintain reconciliation audit history
    - provide serialization
    - provide metadata
    - provide health checks
    - provide regression tests

The ReconciliationEngine does NOT:

    - submit orders
    - cancel orders
    - execute trades
    - modify OMS state
    - modify broker state
    - modify PortfolioAccount
    - generate portfolio targets
    - perform portfolio optimization
    - perform pre-trade risk checks
    - calculate transaction costs

Any remediation must occur through the appropriate execution,
OMS, broker, or accounting component.

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
        +--------------------+
        |                    |
        v                    v
    PaperBroker          LiveBroker
        |                    |
        +---------+----------+
                  |
                  v
        BrokerExecutionEngine
                  |
                  v
        ReconciliationEngine
                  |
        +---------+---------+
        |         |         |
        v         v         v
       OMS      Broker    Account

Design Principles
-----------------

    1. Read-only reconciliation.
    2. Deterministic decisions.
    3. No hidden state mutation.
    4. Explicit discrepancy classification.
    5. Immutable reconciliation results.
    6. Full audit trail.
    7. Serialization support.
    8. Broker-independent interface.
    9. No circular dependencies.
   10. Production modules expose API_VERSION, PUBLIC_METHODS,
       metadata, and health_check().

Author: Michael Kazibwe
Version: 1.0.0
======================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import isclose, isfinite
from typing import Any, Optional


# ======================================================================
# RECONCILIATION STATUS
# ======================================================================


class ReconciliationStatus:
    """
    Top-level reconciliation outcomes.
    """

    MATCHED = "MATCHED"
    DISCREPANCY = "DISCREPANCY"
    MISSING_OMS_ORDER = "MISSING_OMS_ORDER"
    MISSING_BROKER_ORDER = "MISSING_BROKER_ORDER"
    INVALID_INPUT = "INVALID_INPUT"


# ======================================================================
# DISCREPANCY TYPES
# ======================================================================


class DiscrepancyType:
    """
    Deterministic discrepancy classifications.
    """

    NONE = "NONE"

    MISSING_OMS_ORDER = (
        "MISSING_OMS_ORDER"
    )

    MISSING_BROKER_ORDER = (
        "MISSING_BROKER_ORDER"
    )

    STATUS_MISMATCH = (
        "STATUS_MISMATCH"
    )

    QUANTITY_MISMATCH = (
        "QUANTITY_MISMATCH"
    )

    FILLED_QUANTITY_MISMATCH = (
        "FILLED_QUANTITY_MISMATCH"
    )

    REMAINING_QUANTITY_MISMATCH = (
        "REMAINING_QUANTITY_MISMATCH"
    )

    PRICE_MISMATCH = (
        "PRICE_MISMATCH"
    )

    TICKER_MISMATCH = (
        "TICKER_MISMATCH"
    )

    SIDE_MISMATCH = (
        "SIDE_MISMATCH"
    )

    IDENTIFIER_MISMATCH = (
        "IDENTIFIER_MISMATCH"
    )

    ACCOUNT_POSITION_MISMATCH = (
        "ACCOUNT_POSITION_MISMATCH"
    )

    INVALID_BROKER_STATE = (
        "INVALID_BROKER_STATE"
    )

    INVALID_OMS_STATE = (
        "INVALID_OMS_STATE"
    )


# ======================================================================
# RECONCILIATION DECISION
# ======================================================================


@dataclass(frozen=True)
class ReconciliationDecision:
    """
    Immutable result of one reconciliation operation.
    """

    status: str

    discrepancy_type: str

    approved: bool

    order_id: Optional[str]

    broker_order_id: Optional[str]

    ticker: Optional[str]

    side: Optional[str]

    oms_status: Optional[str]

    broker_status: Optional[str]

    oms_quantity: float

    broker_quantity: float

    oms_filled_quantity: float

    broker_filled_quantity: float

    oms_remaining_quantity: float

    broker_remaining_quantity: float

    oms_average_fill_price: float

    broker_average_fill_price: float

    account_position: Optional[float]

    expected_position: Optional[float]

    reason: Optional[str]

    timestamp: str

    def to_dict(self) -> dict:
        """
        Serialize the reconciliation decision.
        """

        return {
            "api_version":
                "1.0.0",

            "status":
                self.status,

            "discrepancy_type":
                self.discrepancy_type,

            "approved":
                self.approved,

            "order_id":
                self.order_id,

            "broker_order_id":
                self.broker_order_id,

            "ticker":
                self.ticker,

            "side":
                self.side,

            "oms_status":
                self.oms_status,

            "broker_status":
                self.broker_status,

            "oms_quantity":
                self.oms_quantity,

            "broker_quantity":
                self.broker_quantity,

            "oms_filled_quantity":
                self.oms_filled_quantity,

            "broker_filled_quantity":
                self.broker_filled_quantity,

            "oms_remaining_quantity":
                self.oms_remaining_quantity,

            "broker_remaining_quantity":
                self.broker_remaining_quantity,

            "oms_average_fill_price":
                self.oms_average_fill_price,

            "broker_average_fill_price":
                self.broker_average_fill_price,

            "account_position":
                self.account_position,

            "expected_position":
                self.expected_position,

            "reason":
                self.reason,

            "timestamp":
                self.timestamp,
        }


# ======================================================================
# RECONCILIATION ENGINE
# ======================================================================


class ReconciliationEngine:
    """
    Institutional post-trade reconciliation engine.

    The engine compares normalized OMS, broker, and optional account
    state without modifying any external object.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (
        "reconcile_order",
        "reconcile_batch",
        "reconcile_account_position",
        "summary",
        "metadata",
        "health_check",
        "to_dict",
        "from_dict",
    )

    # ==================================================================
    # CONSTRUCTOR
    # ==================================================================

    def __init__(
        self,
        quantity_tolerance: float = 1e-9,
        price_tolerance: float = 1e-9,
        position_tolerance: float = 1e-9,
    ):
        """
        Initialize the reconciliation engine.
        """

        if quantity_tolerance < 0:
            raise ValueError(
                "quantity_tolerance must be non-negative."
            )

        if price_tolerance < 0:
            raise ValueError(
                "price_tolerance must be non-negative."
            )

        if position_tolerance < 0:
            raise ValueError(
                "position_tolerance must be non-negative."
            )

        self.quantity_tolerance = float(
            quantity_tolerance
        )

        self.price_tolerance = float(
            price_tolerance
        )

        self.position_tolerance = float(
            position_tolerance
        )

        self.reconciliation_history: list[
            dict
        ] = []

        self.last_decision: Optional[
            ReconciliationDecision
        ] = None

        self.reconciliation_count = 0

        self.matched_count = 0

        self.discrepancy_count = 0

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
    # NUMBER NORMALIZATION
    # ==================================================================

    @staticmethod
    def _number(
        value: Any,
        default: float = 0.0,
    ) -> float:
        """
        Convert a value to a finite float.
        """

        if value is None:
            return float(default)

        try:

            result = float(
                value
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise ValueError(
                f"Value '{value}' cannot be converted "
                "to a numeric value."
            ) from exc

        if not isfinite(result):
            raise ValueError(
                "Numeric values must be finite."
            )

        return result

    # ==================================================================
    # OBJECT ATTRIBUTE
    # ==================================================================

    @staticmethod
    def _attribute(
        obj: Any,
        name: str,
        default: Any = None,
    ) -> Any:
        """
        Safely retrieve an object attribute.
        """

        if obj is None:
            return default

        return getattr(
            obj,
            name,
            default,
        )

    # ==================================================================
    # STATUS NORMALIZATION
    # ==================================================================

    @staticmethod
    def _normalize_status(
        status: Any,
    ) -> Optional[str]:
        """
        Normalize an order status.
        """

        if status is None:
            return None

        if hasattr(
            status,
            "name",
        ):

            status = status.name

        return str(
            status
        ).strip().upper()

    # ==================================================================
    # IDENTIFIER VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_identifier(
        value: Optional[str],
        field_name: str,
    ) -> None:
        """
        Validate an optional order identifier.
        """

        if value is not None and not isinstance(
            value,
            str,
        ):

            raise TypeError(
                f"{field_name} must be a string or None."
            )

    # ==================================================================
    # OBJECT NORMALIZATION
    # ==================================================================

    def _normalize_oms(
        self,
        order: Any,
    ) -> dict:
        """
        Normalize an OMS Order object or compatible record.
        """

        if order is None:
            return {}

        order_id = self._attribute(
            order,
            "order_id",
        )

        ticker = self._attribute(
            order,
            "ticker",
        )

        side = self._attribute(
            order,
            "side",
        )

        status = self._normalize_status(
            self._attribute(
                order,
                "status",
            )
        )

        quantity = self._number(
            self._attribute(
                order,
                "quantity",
                0.0,
            )
        )

        filled_quantity = self._number(
            self._attribute(
                order,
                "filled_quantity",
                0.0,
            )
        )

        remaining_quantity = self._attribute(
            order,
            "remaining_quantity",
            None,
        )

        if remaining_quantity is None:

            remaining_quantity = max(
                quantity - filled_quantity,
                0.0,
            )

        else:

            remaining_quantity = self._number(
                remaining_quantity
            )

        average_fill_price = self._number(
            self._attribute(
                order,
                "average_fill_price",
                0.0,
            )
        )

        broker_order_id = self._attribute(
            order,
            "broker_order_id",
        )

        return {
            "order_id":
                order_id,

            "broker_order_id":
                broker_order_id,

            "ticker":
                ticker,

            "side":
                None
                if side is None
                else str(side).upper(),

            "status":
                status,

            "quantity":
                quantity,

            "filled_quantity":
                filled_quantity,

            "remaining_quantity":
                remaining_quantity,

            "average_fill_price":
                average_fill_price,
        }

    # ==================================================================
    # BROKER NORMALIZATION
    # ==================================================================

    def _normalize_broker(
        self,
        record: Any,
    ) -> dict:
        """
        Normalize a broker-side order record or compatible object.
        """

        if record is None:
            return {}

        broker_order_id = self._attribute(
            record,
            "broker_order_id",
        )

        client_order_id = self._attribute(
            record,
            "client_order_id",
        )

        ticker = self._attribute(
            record,
            "ticker",
        )

        side = self._attribute(
            record,
            "side",
        )

        status = self._normalize_status(
            self._attribute(
                record,
                "status",
            )
        )

        quantity = self._number(
            self._attribute(
                record,
                "quantity",
                0.0,
            )
        )

        filled_quantity = self._number(
            self._attribute(
                record,
                "filled_quantity",
                0.0,
            )
        )

        remaining_quantity = self._attribute(
            record,
            "remaining_quantity",
            None,
        )

        if remaining_quantity is None:

            remaining_quantity = max(
                quantity - filled_quantity,
                0.0,
            )

        else:

            remaining_quantity = self._number(
                remaining_quantity
            )

        average_fill_price = self._number(
            self._attribute(
                record,
                "average_fill_price",
                0.0,
            )
        )

        return {
            "order_id":
                client_order_id,

            "broker_order_id":
                broker_order_id,

            "ticker":
                ticker,

            "side":
                None
                if side is None
                else str(side).upper(),

            "status":
                status,

            "quantity":
                quantity,

            "filled_quantity":
                filled_quantity,

            "remaining_quantity":
                remaining_quantity,

            "average_fill_price":
                average_fill_price,
        }

    # ==================================================================
    # FLOAT COMPARISON
    # ==================================================================

    def _same_quantity(
        self,
        first: float,
        second: float,
    ) -> bool:
        """
        Compare quantities using configured tolerance.
        """

        return isclose(
            first,
            second,
            rel_tol=0.0,
            abs_tol=self.quantity_tolerance,
        )

    def _same_price(
        self,
        first: float,
        second: float,
    ) -> bool:
        """
        Compare prices using configured tolerance.
        """

        return isclose(
            first,
            second,
            rel_tol=0.0,
            abs_tol=self.price_tolerance,
        )

    # ==================================================================
    # BUILD DECISION
    # ==================================================================

    def _build_decision(
        self,
        status: str,
        discrepancy_type: str,
        approved: bool,
        oms: dict,
        broker: dict,
        reason: Optional[str],
        account_position: Optional[float] = None,
        expected_position: Optional[float] = None,
    ) -> ReconciliationDecision:
        """
        Construct and store a reconciliation decision.
        """

        decision = ReconciliationDecision(

            status=status,

            discrepancy_type=(
                discrepancy_type
            ),

            approved=bool(
                approved
            ),

            order_id=(
                oms.get(
                    "order_id"
                )
                or broker.get(
                    "order_id"
                )
            ),

            broker_order_id=(
                oms.get(
                    "broker_order_id"
                )
                or broker.get(
                    "broker_order_id"
                )
            ),

            ticker=(
                oms.get(
                    "ticker"
                )
                or broker.get(
                    "ticker"
                )
            ),

            side=(
                oms.get(
                    "side"
                )
                or broker.get(
                    "side"
                )
            ),

            oms_status=(
                oms.get(
                    "status"
                )
            ),

            broker_status=(
                broker.get(
                    "status"
                )
            ),

            oms_quantity=self._number(
                oms.get(
                    "quantity",
                    0.0,
                )
            ),

            broker_quantity=self._number(
                broker.get(
                    "quantity",
                    0.0,
                )
            ),

            oms_filled_quantity=self._number(
                oms.get(
                    "filled_quantity",
                    0.0,
                )
            ),

            broker_filled_quantity=self._number(
                broker.get(
                    "filled_quantity",
                    0.0,
                )
            ),

            oms_remaining_quantity=self._number(
                oms.get(
                    "remaining_quantity",
                    0.0,
                )
            ),

            broker_remaining_quantity=self._number(
                broker.get(
                    "remaining_quantity",
                    0.0,
                )
            ),

            oms_average_fill_price=self._number(
                oms.get(
                    "average_fill_price",
                    0.0,
                )
            ),

            broker_average_fill_price=self._number(
                broker.get(
                    "average_fill_price",
                    0.0,
                )
            ),

            account_position=(
                None
                if account_position is None
                else self._number(
                    account_position
                )
            ),

            expected_position=(
                None
                if expected_position is None
                else self._number(
                    expected_position
                )
            ),

            reason=reason,

            timestamp=self._timestamp(),
        )

        self.last_decision = decision

        self.reconciliation_history.append(
            decision.to_dict()
        )

        self.reconciliation_count += 1

        if status == ReconciliationStatus.MATCHED:

            self.matched_count += 1

        else:

            self.discrepancy_count += 1

        return decision

    # ==================================================================
    # RECONCILE ORDER
    # ==================================================================

    def reconcile_order(
        self,
        oms_order: Any,
        broker_order: Any,
        account_position: Optional[float] = None,
        expected_position: Optional[float] = None,
    ) -> ReconciliationDecision:
        """
        Reconcile one OMS order against one broker order.

        This method is strictly read-only.
        """

        oms = self._normalize_oms(
            oms_order
        )

        broker = self._normalize_broker(
            broker_order
        )

        if not oms and not broker:

            return self._build_decision(

                ReconciliationStatus.INVALID_INPUT,

                DiscrepancyType.INVALID_OMS_STATE,

                False,

                oms,

                broker,

                "Both OMS and broker order records are missing.",

                account_position,

                expected_position,

            )

        if not oms:

            return self._build_decision(

                ReconciliationStatus.MISSING_OMS_ORDER,

                DiscrepancyType.MISSING_OMS_ORDER,

                False,

                oms,

                broker,

                "Broker order exists but no OMS order was supplied.",

                account_position,

                expected_position,

            )

        if not broker:

            return self._build_decision(

                ReconciliationStatus.MISSING_BROKER_ORDER,

                DiscrepancyType.MISSING_BROKER_ORDER,

                False,

                oms,

                broker,

                "OMS order exists but no broker order was supplied.",

                account_position,

                expected_position,

            )

        oms_order_id = oms.get(
            "order_id"
        )

        broker_client_order_id = broker.get(
            "order_id"
        )

        if (
            oms_order_id is not None
            and broker_client_order_id is not None
            and oms_order_id
            != broker_client_order_id
        ):

            return self._build_decision(

                ReconciliationStatus.DISCREPANCY,

                DiscrepancyType.IDENTIFIER_MISMATCH,

                False,

                oms,

                broker,

                "OMS and broker client order identifiers do not match.",

                account_position,

                expected_position,

            )

        if (
            oms.get("ticker") is not None
            and broker.get("ticker") is not None
            and oms["ticker"]
            != broker["ticker"]
        ):

            return self._build_decision(

                ReconciliationStatus.DISCREPANCY,

                DiscrepancyType.TICKER_MISMATCH,

                False,

                oms,

                broker,

                "OMS and broker tickers do not match.",

                account_position,

                expected_position,

            )

        if (
            oms.get("side") is not None
            and broker.get("side") is not None
            and oms["side"]
            != broker["side"]
        ):

            return self._build_decision(

                ReconciliationStatus.DISCREPANCY,

                DiscrepancyType.SIDE_MISMATCH,

                False,

                oms,

                broker,

                "OMS and broker sides do not match.",

                account_position,

                expected_position,

            )

        if not self._same_quantity(
            oms["quantity"],
            broker["quantity"],
        ):

            return self._build_decision(

                ReconciliationStatus.DISCREPANCY,

                DiscrepancyType.QUANTITY_MISMATCH,

                False,

                oms,

                broker,

                "OMS and broker order quantities do not match.",

                account_position,

                expected_position,

            )

        if not self._same_quantity(
            oms["filled_quantity"],
            broker["filled_quantity"],
        ):

            return self._build_decision(

                ReconciliationStatus.DISCREPANCY,

                DiscrepancyType.FILLED_QUANTITY_MISMATCH,

                False,

                oms,

                broker,

                "OMS and broker filled quantities do not match.",

                account_position,

                expected_position,

            )

        if not self._same_quantity(
            oms["remaining_quantity"],
            broker["remaining_quantity"],
        ):

            return self._build_decision(

                ReconciliationStatus.DISCREPANCY,

                DiscrepancyType.REMAINING_QUANTITY_MISMATCH,

                False,

                oms,

                broker,

                "OMS and broker remaining quantities do not match.",

                account_position,

                expected_position,

            )

        oms_price = oms[
            "average_fill_price"
        ]

        broker_price = broker[
            "average_fill_price"
        ]

        if (
            oms["filled_quantity"] > 0
            or broker["filled_quantity"] > 0
        ):

            if not self._same_price(
                oms_price,
                broker_price,
            ):

                return self._build_decision(

                    ReconciliationStatus.DISCREPANCY,

                    DiscrepancyType.PRICE_MISMATCH,

                    False,

                    oms,

                    broker,

                    "OMS and broker average fill prices do not match.",

                    account_position,

                    expected_position,

                )

        if (
            oms.get("status") is None
            or broker.get("status") is None
        ):

            return self._build_decision(

                ReconciliationStatus.DISCREPANCY,

                DiscrepancyType.INVALID_BROKER_STATE,

                False,

                oms,

                broker,

                "One or both order records have no lifecycle status.",

                account_position,

                expected_position,

            )

        if (
            oms["status"] != broker["status"]
            and not self._statuses_compatible(
                oms["status"],
                broker["status"],
            )
        ):

            return self._build_decision(

                ReconciliationStatus.DISCREPANCY,

                DiscrepancyType.STATUS_MISMATCH,

                False,

                oms,

                broker,

                "OMS and broker lifecycle states are inconsistent.",

                account_position,

                expected_position,

            )

        if (
            account_position is not None
            and expected_position is not None
        ):

            account_value = self._number(
                account_position
            )

            expected_value = self._number(
                expected_position
            )

            if not isclose(
                account_value,
                expected_value,
                rel_tol=0.0,
                abs_tol=self.position_tolerance,
            ):

                return self._build_decision(

                    ReconciliationStatus.DISCREPANCY,

                    DiscrepancyType.ACCOUNT_POSITION_MISMATCH,

                    False,

                    oms,

                    broker,

                    "Account position does not match expected position.",

                    account_position,

                    expected_position,

                )

        return self._build_decision(

            ReconciliationStatus.MATCHED,

            DiscrepancyType.NONE,

            True,

            oms,

            broker,

            "OMS, broker, and supplied account state are reconciled.",

            account_position,

            expected_position,

        )

    # ==================================================================
    # STATUS COMPATIBILITY
    # ==================================================================

    @staticmethod
    def _statuses_compatible(
        oms_status: str,
        broker_status: str,
    ) -> bool:
        """
        Determine whether OMS and broker lifecycle states are
        semantically compatible despite using different vocabularies.
        """

        compatible = {
            (
                "PENDING",
                "SUBMITTED",
            ),

            (
                "PARTIALLY_FILLED",
                "PARTIALLY_FILLED",
            ),

            (
                "FILLED",
                "FILLED",
            ),

            (
                "CANCELLED",
                "CANCELLED",
            ),

            (
                "REJECTED",
                "REJECTED",
            ),
        }

        return (
            oms_status,
            broker_status,
        ) in compatible

    # ==================================================================
    # RECONCILE ACCOUNT POSITION
    # ==================================================================

    def reconcile_account_position(
        self,
        ticker: str,
        expected_position: float,
        actual_position: float,
    ) -> ReconciliationDecision:
        """
        Reconcile an expected position against an actual account
        position.

        This operation has no order dependency and is useful for
        post-trade account reconciliation.
        """

        if not isinstance(
            ticker,
            str,
        ):

            raise TypeError(
                "ticker must be a string."
            )

        ticker = ticker.strip().upper()

        if not ticker:

            raise ValueError(
                "ticker cannot be empty."
            )

        expected = self._number(
            expected_position
        )

        actual = self._number(
            actual_position
        )

        matched = isclose(
            expected,
            actual,
            rel_tol=0.0,
            abs_tol=self.position_tolerance,
        )

        status = (
            ReconciliationStatus.MATCHED
            if matched
            else ReconciliationStatus.DISCREPANCY
        )

        discrepancy_type = (
            DiscrepancyType.NONE
            if matched
            else DiscrepancyType.ACCOUNT_POSITION_MISMATCH
        )

        reason = (
            "Account position matches expected position."
            if matched
            else "Account position does not match expected position."
        )

        return self._build_decision(

            status,

            discrepancy_type,

            matched,

            {
                "order_id":
                    None,

                "broker_order_id":
                    None,

                "ticker":
                    ticker,

                "side":
                    None,

                "status":
                    None,

                "quantity":
                    0.0,

                "filled_quantity":
                    0.0,

                "remaining_quantity":
                    0.0,

                "average_fill_price":
                    0.0,
            },

            {
                "order_id":
                    None,

                "broker_order_id":
                    None,

                "ticker":
                    ticker,

                "side":
                    None,

                "status":
                    None,

                "quantity":
                    0.0,

                "filled_quantity":
                    0.0,

                "remaining_quantity":
                    0.0,

                "average_fill_price":
                    0.0,
            },

            reason,

            actual,

            expected,

        )

    # ==================================================================
    # RECONCILE BATCH
    # ==================================================================

    def reconcile_batch(
        self,
        pairs: list,
    ) -> list[ReconciliationDecision]:
        """
        Reconcile a deterministic batch of order pairs.

        Each item must be a two-element tuple/list:

            (oms_order, broker_order)

        A three-element item is also supported:

            (oms_order, broker_order, account_position)

        A four-element item is supported for explicit expected position:

            (
                oms_order,
                broker_order,
                account_position,
                expected_position,
            )
        """

        if not isinstance(
            pairs,
            list,
        ):

            raise TypeError(
                "pairs must be a list."
            )

        results = []

        for pair in pairs:

            if not isinstance(
                pair,
                (tuple, list),
            ):

                raise TypeError(
                    "Each reconciliation pair must be a tuple or list."
                )

            if len(pair) == 2:

                result = self.reconcile_order(
                    pair[0],
                    pair[1],
                )

            elif len(pair) == 3:

                result = self.reconcile_order(
                    pair[0],
                    pair[1],
                    pair[2],
                )

            elif len(pair) == 4:

                result = self.reconcile_order(
                    pair[0],
                    pair[1],
                    pair[2],
                    pair[3],
                )

            else:

                raise ValueError(
                    "Each reconciliation item must contain "
                    "2, 3, or 4 elements."
                )

            results.append(
                result
            )

        return results

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(self) -> dict:
        """
        Return reconciliation statistics.
        """

        return {
            "api_version":
                self.API_VERSION,

            "reconciliation_count":
                self.reconciliation_count,

            "matched_count":
                self.matched_count,

            "discrepancy_count":
                self.discrepancy_count,

            "match_rate":
                (
                    self.matched_count
                    / self.reconciliation_count
                    if self.reconciliation_count
                    else 0.0
                ),

            "history_events":
                len(
                    self.reconciliation_history
                ),

            "last_status":
                None
                if self.last_decision is None
                else self.last_decision.status,

            "last_discrepancy":
                None
                if self.last_decision is None
                else self.last_decision.discrepancy_type,
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
                "ReconciliationEngine",

            "api_version":
                self.API_VERSION,

            "public_methods":
                list(
                    self.PUBLIC_METHODS
                ),

            "quantity_tolerance":
                self.quantity_tolerance,

            "price_tolerance":
                self.price_tolerance,

            "position_tolerance":
                self.position_tolerance,

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
        Validate reconciliation engine state.
        """

        if self.API_VERSION != "1.0.0":

            raise RuntimeError(
                "Invalid ReconciliationEngine API version."
            )

        if self.quantity_tolerance < 0:

            raise RuntimeError(
                "Invalid quantity tolerance."
            )

        if self.price_tolerance < 0:

            raise RuntimeError(
                "Invalid price tolerance."
            )

        if self.position_tolerance < 0:

            raise RuntimeError(
                "Invalid position tolerance."
            )

        if self.reconciliation_count < 0:

            raise RuntimeError(
                "Invalid reconciliation count."
            )

        if self.matched_count < 0:

            raise RuntimeError(
                "Invalid matched count."
            )

        if self.discrepancy_count < 0:

            raise RuntimeError(
                "Invalid discrepancy count."
            )

        if (
            self.matched_count
            + self.discrepancy_count
            != self.reconciliation_count
        ):

            raise RuntimeError(
                "Reconciliation counters are inconsistent."
            )

        return True

    # ==================================================================
    # TO DICTIONARY
    # ==================================================================

    def to_dict(self) -> dict:
        """
        Serialize reconciliation engine state.
        """

        return {
            "api_version":
                self.API_VERSION,

            "quantity_tolerance":
                self.quantity_tolerance,

            "price_tolerance":
                self.price_tolerance,

            "position_tolerance":
                self.position_tolerance,

            "reconciliation_count":
                self.reconciliation_count,

            "matched_count":
                self.matched_count,

            "discrepancy_count":
                self.discrepancy_count,

            "reconciliation_history":
                list(
                    self.reconciliation_history
                ),

            "last_decision":
                None
                if self.last_decision is None
                else self.last_decision.to_dict(),
        }

    # ==================================================================
    # FROM DICTIONARY
    # ==================================================================

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> ReconciliationEngine:
        """
        Restore reconciliation engine state.
        """

        if not isinstance(
            data,
            dict,
        ):

            raise TypeError(
                "data must be a dictionary."
            )

        engine = cls(

            quantity_tolerance=float(
                data.get(
                    "quantity_tolerance",
                    1e-9,
                )
            ),

            price_tolerance=float(
                data.get(
                    "price_tolerance",
                    1e-9,
                )
            ),

            position_tolerance=float(
                data.get(
                    "position_tolerance",
                    1e-9,
                )
            ),
        )

        engine.reconciliation_count = int(
            data.get(
                "reconciliation_count",
                0,
            )
        )

        engine.matched_count = int(
            data.get(
                "matched_count",
                0,
            )
        )

        engine.discrepancy_count = int(
            data.get(
                "discrepancy_count",
                0,
            )
        )

        engine.reconciliation_history = list(
            data.get(
                "reconciliation_history",
                [],
            )
        )

        last = data.get(
            "last_decision"
        )

        if last is not None:

            engine.last_decision = (
                ReconciliationDecision(
                    status=last[
                        "status"
                    ],

                    discrepancy_type=last[
                        "discrepancy_type"
                    ],

                    approved=bool(
                        last[
                            "approved"
                        ]
                    ),

                    order_id=last.get(
                        "order_id"
                    ),

                    broker_order_id=last.get(
                        "broker_order_id"
                    ),

                    ticker=last.get(
                        "ticker"
                    ),

                    side=last.get(
                        "side"
                    ),

                    oms_status=last.get(
                        "oms_status"
                    ),

                    broker_status=last.get(
                        "broker_status"
                    ),

                    oms_quantity=float(
                        last.get(
                            "oms_quantity",
                            0.0,
                        )
                    ),

                    broker_quantity=float(
                        last.get(
                            "broker_quantity",
                            0.0,
                        )
                    ),

                    oms_filled_quantity=float(
                        last.get(
                            "oms_filled_quantity",
                            0.0,
                        )
                    ),

                    broker_filled_quantity=float(
                        last.get(
                            "broker_filled_quantity",
                            0.0,
                        )
                    ),

                    oms_remaining_quantity=float(
                        last.get(
                            "oms_remaining_quantity",
                            0.0,
                        )
                    ),

                    broker_remaining_quantity=float(
                        last.get(
                            "broker_remaining_quantity",
                            0.0,
                        )
                    ),

                    oms_average_fill_price=float(
                        last.get(
                            "oms_average_fill_price",
                            0.0,
                        )
                    ),

                    broker_average_fill_price=float(
                        last.get(
                            "broker_average_fill_price",
                            0.0,
                        )
                    ),

                    account_position=(
                        None
                        if last.get(
                            "account_position"
                        ) is None
                        else float(
                            last[
                                "account_position"
                            ]
                        )
                    ),

                    expected_position=(
                        None
                        if last.get(
                            "expected_position"
                        ) is None
                        else float(
                            last[
                                "expected_position"
                            ]
                        )
                    ),

                    reason=last.get(
                        "reason"
                    ),

                    timestamp=last.get(
                        "timestamp",
                        "",
                    ),
                )
            )

        return engine


# ======================================================================
# REGRESSION TESTS
# ======================================================================


def test_reconciliation_engine():
    """
    Deterministic regression suite.
    """

    from order import Order

    # ==============================================================
    # ENGINE
    # ==============================================================

    engine = ReconciliationEngine()

    assert engine.API_VERSION == "1.0.0"

    assert engine.health_check()

    # ==============================================================
    # MATCHED ORDER
    # ==============================================================

    oms_order = Order(
        order_id="RECON-000001",
        ticker="SPY",
        side="BUY",
        quantity=100,
    )

    oms_order.status = "FILLED"
    oms_order.filled_quantity = 100.0
    oms_order.average_fill_price = 500.0

    @dataclass
    class TestBrokerOrder:
        broker_order_id: str
        client_order_id: str
        ticker: str
        side: str
        quantity: float
        status: str
        average_fill_price: float
        filled_quantity: float
        remaining_quantity: float

    broker_order = TestBrokerOrder(
        broker_order_id="PAPER-00000001",
        client_order_id="RECON-000001",
        ticker="SPY",
        side="BUY",
        quantity=100.0,
        status="FILLED",
        average_fill_price=500.0,
        filled_quantity=100.0,
        remaining_quantity=0.0,
    )

    decision = engine.reconcile_order(
        oms_order,
        broker_order,
    )

    assert decision.approved

    assert decision.status == (
        ReconciliationStatus.MATCHED
    )

    assert decision.discrepancy_type == (
        DiscrepancyType.NONE
    )

    assert decision.order_id == (
        "RECON-000001"
    )

    # ==============================================================
    # QUANTITY MISMATCH
    # ==============================================================

    quantity_mismatch = TestBrokerOrder(
        broker_order_id="PAPER-00000002",
        client_order_id="RECON-000001",
        ticker="SPY",
        side="BUY",
        quantity=90.0,
        status="FILLED",
        average_fill_price=500.0,
        filled_quantity=90.0,
        remaining_quantity=0.0,
    )

    decision = engine.reconcile_order(
        oms_order,
        quantity_mismatch,
    )

    assert not decision.approved

    assert decision.discrepancy_type == (
        DiscrepancyType.QUANTITY_MISMATCH
    )

    # ==============================================================
    # PRICE MISMATCH
    # ==============================================================

    price_mismatch = TestBrokerOrder(
        broker_order_id="PAPER-00000003",
        client_order_id="RECON-000001",
        ticker="SPY",
        side="BUY",
        quantity=100.0,
        status="FILLED",
        average_fill_price=501.0,
        filled_quantity=100.0,
        remaining_quantity=0.0,
    )

    decision = engine.reconcile_order(
        oms_order,
        price_mismatch,
    )

    assert not decision.approved

    assert decision.discrepancy_type == (
        DiscrepancyType.PRICE_MISMATCH
    )

    # ==============================================================
    # STATUS MISMATCH
    # ==============================================================

    status_mismatch = TestBrokerOrder(
        broker_order_id="PAPER-00000004",
        client_order_id="RECON-000001",
        ticker="SPY",
        side="BUY",
        quantity=100.0,
        status="CANCELLED",
        average_fill_price=500.0,
        filled_quantity=100.0,
        remaining_quantity=0.0,
    )

    decision = engine.reconcile_order(
        oms_order,
        status_mismatch,
    )

    assert not decision.approved

    assert decision.discrepancy_type == (
        DiscrepancyType.STATUS_MISMATCH
    )

    # ==============================================================
    # MISSING BROKER ORDER
    # ==============================================================

    decision = engine.reconcile_order(
        oms_order,
        None,
    )

    assert not decision.approved

    assert decision.status == (
        ReconciliationStatus.MISSING_BROKER_ORDER
    )

    # ==============================================================
    # MISSING OMS ORDER
    # ==============================================================

    decision = engine.reconcile_order(
        None,
        broker_order,
    )

    assert not decision.approved

    assert decision.status == (
        ReconciliationStatus.MISSING_OMS_ORDER
    )

    # ==============================================================
    # IDENTIFIER MISMATCH
    # ==============================================================

    identifier_mismatch = TestBrokerOrder(
        broker_order_id="PAPER-00000005",
        client_order_id="WRONG-ID",
        ticker="SPY",
        side="BUY",
        quantity=100.0,
        status="FILLED",
        average_fill_price=500.0,
        filled_quantity=100.0,
        remaining_quantity=0.0,
    )

    decision = engine.reconcile_order(
        oms_order,
        identifier_mismatch,
    )

    assert not decision.approved

    assert decision.discrepancy_type == (
        DiscrepancyType.IDENTIFIER_MISMATCH
    )

    # ==============================================================
    # ACCOUNT POSITION MATCH
    # ==============================================================

    decision = engine.reconcile_account_position(
        "SPY",
        expected_position=100.0,
        actual_position=100.0,
    )

    assert decision.approved

    assert decision.status == (
        ReconciliationStatus.MATCHED
    )

    # ==============================================================
    # ACCOUNT POSITION MISMATCH
    # ==============================================================

    decision = engine.reconcile_account_position(
        "SPY",
        expected_position=100.0,
        actual_position=90.0,
    )

    assert not decision.approved

    assert decision.discrepancy_type == (
        DiscrepancyType.ACCOUNT_POSITION_MISMATCH
    )

    # ==============================================================
    # BATCH
    # ==============================================================

    batch = engine.reconcile_batch(
        [
            (
                oms_order,
                broker_order,
            ),
            (
                oms_order,
                quantity_mismatch,
            ),
        ]
    )

    assert len(batch) == 2

    assert batch[0].approved

    assert not batch[1].approved

    # ==============================================================
    # SERIALIZATION
    # ==============================================================

    exported = engine.to_dict()

    restored = (
        ReconciliationEngine.from_dict(
            exported
        )
    )

    assert restored.API_VERSION == (
        engine.API_VERSION
    )

    assert restored.reconciliation_count == (
        engine.reconciliation_count
    )

    assert restored.matched_count == (
        engine.matched_count
    )

    assert restored.discrepancy_count == (
        engine.discrepancy_count
    )

    assert restored.last_decision is not None

    assert (
        restored.last_decision.status
        == engine.last_decision.status
    )

    assert (
        restored.last_decision.discrepancy_type
        == engine.last_decision.discrepancy_type
    )

    # ==============================================================
    # SUMMARY
    # ==============================================================

    summary = engine.summary()

    assert summary[
        "api_version"
    ] == engine.API_VERSION

    assert summary[
        "reconciliation_count"
    ] == 11

    assert summary[
        "matched_count"
    ] == 3

    assert summary[
        "discrepancy_count"
    ] == 8

    assert summary[
        "history_events"
    ] == 11

    # ==============================================================
    # HEALTH
    # ==============================================================

    assert engine.health_check()

    print(
        "ReconciliationEngine Phase III-C.2 tests passed."
    )


# ======================================================================
# MAIN
# ======================================================================


if __name__ == "__main__":

    test_reconciliation_engine()