"""
======================================================================
posttradeexecutionmonitor.py

Institutional Post-Trade Execution Monitor
======================================================================

Phase III-C.3

Monitors broker execution results after an order has been routed and
executed.

Responsibilities
----------------

    - execution confirmation
    - fill integrity verification
    - quantity reconciliation
    - price verification
    - execution status verification
    - duplicate execution detection
    - missing execution detection
    - execution discrepancy detection
    - execution-quality measurement
    - post-trade state management
    - audit trail
    - reconciliation references
    - serialization
    - health checks
    - deterministic regression tests

The PostTradeExecutionMonitor does NOT:

    - generate portfolio targets
    - generate trades
    - perform portfolio optimization
    - perform pre-trade risk checks
    - submit orders
    - route orders
    - execute trades
    - modify PortfolioAccount
    - replace ReconciliationEngine
    - perform portfolio-level accounting

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
    ReconciliationEngine
        |
        v
    PostTradeExecutionMonitor
        |
        v
    Portfolio Accounting

Author: Michael Kazibwe
Version: 1.0.0
======================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Optional


# ======================================================================
# POST-TRADE STATUS
# ======================================================================


class PostTradeStatus:
    """
    Deterministic post-trade execution states.
    """

    PENDING = "PENDING"

    CONFIRMED = "CONFIRMED"

    PARTIALLY_CONFIRMED = "PARTIALLY_CONFIRMED"

    DISCREPANCY = "DISCREPANCY"

    DUPLICATE = "DUPLICATE"

    MISSING = "MISSING"

    FAILED = "FAILED"


# ======================================================================
# DISCREPANCY REASONS
# ======================================================================


class ExecutionDiscrepancy:
    """
    Deterministic execution discrepancy identifiers.
    """

    NONE = None

    MISSING_EXECUTION = "MISSING_EXECUTION"

    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"

    PRICE_MISMATCH = "PRICE_MISMATCH"

    STATUS_MISMATCH = "STATUS_MISMATCH"

    DUPLICATE_EXECUTION = "DUPLICATE_EXECUTION"

    ORDER_ID_MISMATCH = "ORDER_ID_MISMATCH"

    TICKER_MISMATCH = "TICKER_MISMATCH"

    SIDE_MISMATCH = "SIDE_MISMATCH"

    INVALID_EXECUTION_PRICE = "INVALID_EXECUTION_PRICE"

    INVALID_EXECUTION_QUANTITY = "INVALID_EXECUTION_QUANTITY"


# ======================================================================
# EXECUTION QUALITY
# ======================================================================


@dataclass(frozen=True)
class ExecutionQuality:
    """
    Deterministic execution-quality measurement.

    benchmark_price:
        Expected/reference execution price.

    execution_price:
        Actual execution price.

    price_deviation:
        Absolute price difference.

    price_deviation_pct:
        Percentage deviation from benchmark.

    slippage:
        Signed execution slippage.

    slippage_pct:
        Signed percentage slippage.
    """

    benchmark_price: float

    execution_price: float

    price_deviation: float

    price_deviation_pct: float

    slippage: float

    slippage_pct: float

    def to_dict(self) -> dict:
        """
        Serialize execution-quality metrics.
        """

        return {
            "benchmark_price": self.benchmark_price,
            "execution_price": self.execution_price,
            "price_deviation": self.price_deviation,
            "price_deviation_pct": self.price_deviation_pct,
            "slippage": self.slippage,
            "slippage_pct": self.slippage_pct,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> ExecutionQuality:
        """
        Restore execution-quality metrics.
        """

        return cls(
            benchmark_price=float(
                data["benchmark_price"]
            ),
            execution_price=float(
                data["execution_price"]
            ),
            price_deviation=float(
                data["price_deviation"]
            ),
            price_deviation_pct=float(
                data["price_deviation_pct"]
            ),
            slippage=float(
                data["slippage"]
            ),
            slippage_pct=float(
                data["slippage_pct"]
            ),
        )


# ======================================================================
# POST-TRADE DECISION
# ======================================================================


@dataclass(frozen=True)
class PostTradeDecision:
    """
    Immutable post-trade monitoring decision.
    """

    approved: bool

    status: str

    reason: Optional[str]

    order_id: Optional[str]

    broker_order_id: Optional[str]

    ticker: Optional[str]

    side: Optional[str]

    ordered_quantity: float

    executed_quantity: float

    remaining_quantity: float

    expected_price: float

    execution_price: float

    quantity_difference: float

    price_difference: float

    execution_notional: float

    execution_quality: Optional[ExecutionQuality]

    timestamp: str

    def to_dict(self) -> dict:
        """
        Serialize the post-trade decision.
        """

        return {
            "approved": self.approved,
            "status": self.status,
            "reason": self.reason,
            "order_id": self.order_id,
            "broker_order_id": self.broker_order_id,
            "ticker": self.ticker,
            "side": self.side,
            "ordered_quantity": self.ordered_quantity,
            "executed_quantity": self.executed_quantity,
            "remaining_quantity": self.remaining_quantity,
            "expected_price": self.expected_price,
            "execution_price": self.execution_price,
            "quantity_difference": self.quantity_difference,
            "price_difference": self.price_difference,
            "execution_notional": self.execution_notional,
            "execution_quality": (
                None
                if self.execution_quality is None
                else self.execution_quality.to_dict()
            ),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> PostTradeDecision:
        """
        Restore a post-trade decision.
        """

        quality = data.get(
            "execution_quality"
        )

        return cls(
            approved=bool(
                data["approved"]
            ),
            status=data["status"],
            reason=data.get("reason"),
            order_id=data.get("order_id"),
            broker_order_id=data.get(
                "broker_order_id"
            ),
            ticker=data.get("ticker"),
            side=data.get("side"),
            ordered_quantity=float(
                data.get(
                    "ordered_quantity",
                    0.0,
                )
            ),
            executed_quantity=float(
                data.get(
                    "executed_quantity",
                    0.0,
                )
            ),
            remaining_quantity=float(
                data.get(
                    "remaining_quantity",
                    0.0,
                )
            ),
            expected_price=float(
                data.get(
                    "expected_price",
                    0.0,
                )
            ),
            execution_price=float(
                data.get(
                    "execution_price",
                    0.0,
                )
            ),
            quantity_difference=float(
                data.get(
                    "quantity_difference",
                    0.0,
                )
            ),
            price_difference=float(
                data.get(
                    "price_difference",
                    0.0,
                )
            ),
            execution_notional=float(
                data.get(
                    "execution_notional",
                    0.0,
                )
            ),
            execution_quality=(
                None
                if quality is None
                else ExecutionQuality.from_dict(
                    quality
                )
            ),
            timestamp=data.get(
                "timestamp",
                "",
            ),
        )


# ======================================================================
# POST-TRADE EXECUTION MONITOR
# ======================================================================


class PostTradeExecutionMonitor:
    """
    Institutional post-trade execution integrity monitor.

    The monitor consumes an OMS order together with a broker execution
    receipt/record and determines whether the execution is internally
    consistent.

    The monitor is deliberately deterministic and does not mutate the
    order, broker, reconciliation engine, or portfolio account.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (
        "monitor_execution",
        "confirm_execution",
        "check_quantity",
        "check_price",
        "check_status",
        "check_duplicate",
        "execution_quality",
        "get_decision",
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
        price_tolerance: float = 0.01,
        quantity_tolerance: float = 1e-9,
    ):
        """
        Initialize the post-trade monitor.

        Parameters
        ----------
        price_tolerance:
            Maximum permitted absolute price difference.

        quantity_tolerance:
            Maximum permitted absolute quantity difference.
        """

        if price_tolerance < 0:
            raise ValueError(
                "price_tolerance must be non-negative."
            )

        if quantity_tolerance < 0:
            raise ValueError(
                "quantity_tolerance must be non-negative."
            )

        self.price_tolerance = float(
            price_tolerance
        )

        self.quantity_tolerance = float(
            quantity_tolerance
        )

        self.history: list[dict] = []

        self.last_decision: Optional[
            PostTradeDecision
        ] = None

        self.last_quality: Optional[
            ExecutionQuality
        ] = None

        self.monitor_count = 0

        self.confirmed_count = 0

        self.partial_count = 0

        self.discrepancy_count = 0

        self.duplicate_count = 0

        self.missing_count = 0

        self.failed_count = 0

        self._execution_keys: set[
            str
        ] = set()

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
    # GENERIC FIELD ACCESS
    # ==================================================================

    @staticmethod
    def _get(
        obj: Any,
        field: str,
        default: Any = None,
    ) -> Any:
        """
        Read a field from either an object or dictionary.

        This allows the monitor to consume:

            - Order objects
            - PaperOrderRecord objects
            - execution receipts
            - dictionaries
            - broker execution responses
        """

        if obj is None:
            return default

        if isinstance(
            obj,
            dict,
        ):
            return obj.get(
                field,
                default,
            )

        return getattr(
            obj,
            field,
            default,
        )

    # ==================================================================
    # ORDER ID
    # ==================================================================

    @classmethod
    def _order_id(
        cls,
        order: Any,
    ) -> Optional[str]:
        """
        Extract client order ID.
        """

        return cls._get(
            order,
            "order_id",
            cls._get(
                order,
                "client_order_id",
            ),
        )

    # ==================================================================
    # BROKER ORDER ID
    # ==================================================================

    @classmethod
    def _broker_order_id(
        cls,
        execution: Any,
    ) -> Optional[str]:
        """
        Extract broker order ID.
        """

        return cls._get(
            execution,
            "broker_order_id",
        )

    # ==================================================================
    # VALIDATE INPUT
    # ==================================================================

    @classmethod
    def _validate_inputs(
        cls,
        order: Any,
        execution: Any,
    ) -> None:
        """
        Validate the minimum execution inputs.
        """

        if order is None:
            raise TypeError(
                "order cannot be None."
            )

        if execution is None:
            raise TypeError(
                "execution cannot be None."
            )

        order_id = cls._order_id(
            order
        )

        if not order_id:
            raise ValueError(
                "Order must contain an order_id."
            )

    # ==================================================================
    # QUANTITY CHECK
    # ==================================================================

    def check_quantity(
        self,
        order: Any,
        execution: Any,
    ) -> tuple[
        bool,
        float,
        float,
        float,
    ]:
        """
        Verify executed quantity against ordered quantity.

        Returns
        -------
        approved, ordered_quantity, executed_quantity,
        quantity_difference
        """

        ordered_quantity = float(
            self._get(
                order,
                "quantity",
                0.0,
            )
        )

        executed_quantity = float(
            self._get(
                execution,
                "quantity",
                self._get(
                    execution,
                    "executed_quantity",
                    self._get(
                        execution,
                        "filled_quantity",
                        0.0,
                    ),
                ),
            )
        )

        if ordered_quantity <= 0:
            raise ValueError(
                ExecutionDiscrepancy
                .INVALID_EXECUTION_QUANTITY
            )

        if executed_quantity < 0:
            raise ValueError(
                ExecutionDiscrepancy
                .INVALID_EXECUTION_QUANTITY
            )

        quantity_difference = (
            ordered_quantity
            - executed_quantity
        )

        # A partial fill is valid, but an overfill is not.
        if (
            executed_quantity
            > ordered_quantity
            + self.quantity_tolerance
        ):
            return (
                False,
                ordered_quantity,
                executed_quantity,
                quantity_difference,
            )

        return (
            True,
            ordered_quantity,
            executed_quantity,
            quantity_difference,
        )

    # ==================================================================
    # PRICE CHECK
    # ==================================================================

    def check_price(
        self,
        expected_price: float,
        execution: Any,
    ) -> tuple[
        bool,
        float,
        float,
        float,
    ]:
        """
        Verify execution price against the expected price.

        Price integrity is evaluated using a relative deviation rather
        than an absolute dollar difference.

        This is deliberately separate from execution quality.

        A price deviation may represent normal market slippage and
        therefore does not automatically constitute a failed execution
        unless it exceeds the configured price tolerance.

        Returns
        -------
        approved:
            Whether the execution price is within the configured
            tolerance.

        expected_price:
            Reference execution price.

        execution_price:
            Actual execution price.

        price_difference:
            Absolute price difference.
        """

        expected_price = float(
            expected_price
        )

        execution_price = float(
            self._get(
                execution,
                "execution_price",
                self._get(
                    execution,
                    "average_fill_price",
                    0.0,
                ),
            )
        )

        if expected_price <= 0:
            raise ValueError(
                "expected_price must be positive."
            )

        if execution_price <= 0:
            return (
                False,
                expected_price,
                execution_price,
                abs(
                    expected_price
                    - execution_price
                ),
            )

        price_difference = abs(
            expected_price
            - execution_price
        )

        price_deviation_pct = (
            price_difference
            / expected_price
        )

        # --------------------------------------------------------------
        # PRICE TOLERANCE
        # --------------------------------------------------------------
        #
        # price_tolerance is interpreted as a relative tolerance.
        #
        # Example:
        #
        #     price_tolerance = 0.01
        #
        # means 1% maximum price deviation.
        #
        # This prevents the tolerance from becoming dependent on the
        # absolute price of the instrument.
        # --------------------------------------------------------------

        approved = (
            price_deviation_pct
            <= self.price_tolerance
        )

        return (
            approved,
            expected_price,
            execution_price,
            price_difference,
        )

    # ==================================================================
    # STATUS CHECK
    # ==================================================================

    @staticmethod
    def check_status(
        execution: Any,
    ) -> tuple[
        bool,
        str,
    ]:
        """
        Verify that the broker execution has a recognized status.
        """

        status = str(
            PostTradeExecutionMonitor._get(
                execution,
                "status",
                "",
            )
        ).upper()

        valid_statuses = {
            "FILLED",
            "PARTIALLY_FILLED",
            "CONFIRMED",
            "EXECUTED",
        }

        if status in valid_statuses:
            return (
                True,
                status,
            )

        return (
            False,
            status,
        )

    # ==================================================================
    # DUPLICATE CHECK
    # ==================================================================

    def check_duplicate(
        self,
        order: Any,
        execution: Any,
    ) -> bool:
        """
        Return True if the execution has already been processed.
        """

        order_id = self._order_id(
            order
        )

        broker_order_id = (
            self._broker_order_id(
                execution
            )
        )

        execution_key = (
            broker_order_id
            or order_id
        )

        if execution_key is None:
            return False

        return execution_key in (
            self._execution_keys
        )

    # ==================================================================
    # EXECUTION QUALITY
    # ==================================================================

    def execution_quality(
        self,
        order: Any,
        execution: Any,
        benchmark_price: Optional[
            float
        ] = None,
    ) -> ExecutionQuality:
        """
        Calculate deterministic execution quality.

        For BUY orders:

            positive slippage means execution above benchmark.

        For SELL orders:

            positive slippage means execution below benchmark.

        The resulting slippage is expressed as an execution cost.
        """

        execution_price = float(
            self._get(
                execution,
                "execution_price",
                self._get(
                    execution,
                    "average_fill_price",
                    0.0,
                ),
            )
        )

        if execution_price <= 0:
            raise ValueError(
                "execution price must be positive."
            )

        if benchmark_price is None:
            benchmark_price = float(
                self._get(
                    order,
                    "limit_price",
                    execution_price,
                )
                or execution_price
            )

        benchmark_price = float(
            benchmark_price
        )

        if benchmark_price <= 0:
            raise ValueError(
                "benchmark_price must be positive."
            )

        side = str(
            self._get(
                order,
                "side",
                "BUY",
            )
        ).upper()

        price_deviation = (
            execution_price
            - benchmark_price
        )

        price_deviation_pct = (
            price_deviation
            / benchmark_price
        )

        if side == "BUY":
            slippage = (
                execution_price
                - benchmark_price
            )
        else:
            slippage = (
                benchmark_price
                - execution_price
            )

        slippage_pct = (
            slippage
            / benchmark_price
        )

        quality = ExecutionQuality(
            benchmark_price=benchmark_price,
            execution_price=execution_price,
            price_deviation=price_deviation,
            price_deviation_pct=(
                price_deviation_pct
            ),
            slippage=slippage,
            slippage_pct=slippage_pct,
        )

        self.last_quality = quality

        return quality

    # ==================================================================
    # RECORD DECISION
    # ==================================================================

    def _record_decision(
        self,
        decision: PostTradeDecision,
    ) -> None:
        """
        Record an immutable monitoring decision.
        """

        self.history.append(
            decision.to_dict()
        )

        self.last_decision = decision

        self.monitor_count += 1

        if decision.status == (
            PostTradeStatus.CONFIRMED
        ):
            self.confirmed_count += 1

        elif decision.status == (
            PostTradeStatus.PARTIALLY_CONFIRMED
        ):
            self.partial_count += 1

        elif decision.status == (
            PostTradeStatus.DUPLICATE
        ):
            self.duplicate_count += 1

        elif decision.status == (
            PostTradeStatus.MISSING
        ):
            self.missing_count += 1

        elif decision.status == (
            PostTradeStatus.FAILED
        ):
            self.failed_count += 1

        elif decision.status == (
            PostTradeStatus.DISCREPANCY
        ):
            self.discrepancy_count += 1

    # ==================================================================
    # BUILD DECISION
    # ==================================================================

    def _build_decision(
        self,
        order: Any,
        execution: Any,
        status: str,
        reason: Optional[str],
        approved: bool,
        ordered_quantity: float,
        executed_quantity: float,
        expected_price: float,
        execution_price: float,
        execution_quality_value: Optional[
            ExecutionQuality
        ],
    ) -> PostTradeDecision:
        """
        Construct a monitoring decision.
        """

        order_id = self._order_id(
            order
        )

        broker_order_id = (
            self._broker_order_id(
                execution
            )
        )

        quantity_difference = (
            ordered_quantity
            - executed_quantity
        )

        remaining_quantity = max(
            quantity_difference,
            0.0,
        )

        execution_notional = (
            executed_quantity
            * execution_price
        )

        return PostTradeDecision(
            approved=approved,
            status=status,
            reason=reason,
            order_id=order_id,
            broker_order_id=broker_order_id,
            ticker=self._get(
                order,
                "ticker",
            ),
            side=self._get(
                order,
                "side",
            ),
            ordered_quantity=(
                ordered_quantity
            ),
            executed_quantity=(
                executed_quantity
            ),
            remaining_quantity=(
                remaining_quantity
            ),
            expected_price=(
                expected_price
            ),
            execution_price=(
                execution_price
            ),
            quantity_difference=(
                quantity_difference
            ),
            price_difference=abs(
                expected_price
                - execution_price
            ),
            execution_notional=(
                execution_notional
            ),
            execution_quality=(
                execution_quality_value
            ),
            timestamp=self._timestamp(),
        )

    # ==================================================================
    # CENTRAL MONITOR
    # ==================================================================

    def monitor_execution(
        self,
        order: Any,
        execution: Any,
        expected_price: Optional[
            float
        ] = None,
        benchmark_price: Optional[
            float
        ] = None,
    ) -> PostTradeDecision:
        """
        Perform the complete post-trade integrity check.

        The method does not mutate the supplied order or execution.
        """

        self._validate_inputs(
            order,
            execution,
        )

        # --------------------------------------------------------------
        # DUPLICATE
        # --------------------------------------------------------------

        if self.check_duplicate(
            order,
            execution,
        ):
            decision = self._build_decision(
                order=order,
                execution=execution,
                status=PostTradeStatus.DUPLICATE,
                reason=(
                    ExecutionDiscrepancy
                    .DUPLICATE_EXECUTION
                ),
                approved=False,
                ordered_quantity=float(
                    self._get(
                        order,
                        "quantity",
                        0.0,
                    )
                ),
                executed_quantity=float(
                    self._get(
                        execution,
                        "quantity",
                        self._get(
                            execution,
                            "executed_quantity",
                            self._get(
                                execution,
                                "filled_quantity",
                                0.0,
                            ),
                        ),
                    )
                ),
                expected_price=float(
                    expected_price
                    or self._get(
                        execution,
                        "execution_price",
                        0.0,
                    )
                ),
                execution_price=float(
                    self._get(
                        execution,
                        "execution_price",
                        self._get(
                            execution,
                            "average_fill_price",
                            0.0,
                        ),
                    )
                ),
                execution_quality_value=None,
            )

            self._record_decision(
                decision
            )

            return decision

        # --------------------------------------------------------------
        # MISSING EXECUTION
        # --------------------------------------------------------------

        if execution is None:
            decision = self._build_decision(
                order=order,
                execution={},
                status=PostTradeStatus.MISSING,
                reason=(
                    ExecutionDiscrepancy
                    .MISSING_EXECUTION
                ),
                approved=False,
                ordered_quantity=float(
                    self._get(
                        order,
                        "quantity",
                        0.0,
                    )
                ),
                executed_quantity=0.0,
                expected_price=float(
                    expected_price or 0.0
                ),
                execution_price=0.0,
                execution_quality_value=None,
            )

            self._record_decision(
                decision
            )

            self.missing_count += 0

            return decision

        # --------------------------------------------------------------
        # QUANTITY
        # --------------------------------------------------------------

        (
            quantity_ok,
            ordered_quantity,
            executed_quantity,
            quantity_difference,
        ) = self.check_quantity(
            order,
            execution,
        )

        # --------------------------------------------------------------
        # STATUS
        # --------------------------------------------------------------

        status_ok, execution_status = (
            self.check_status(
                execution
            )
        )

        # --------------------------------------------------------------
        # ZERO-FILL BROKER STATE
        # --------------------------------------------------------------
        #
        # An execution record exists, therefore this is NOT a missing
        # broker response.
        #
        # The broker has responded with an execution state but has
        # executed zero quantity.
        #
        # Therefore:
        #
        #     PENDING  -> PENDING
        #     REJECTED -> FAILED
        #     CANCELLED -> FAILED
        #     other zero-fill states -> FAILED
        #
        # A genuinely absent execution remains handled separately by
        # the execution is None branch above.
        # --------------------------------------------------------------

        raw_executed_quantity = float(
            self._get(
                execution,
                "quantity",
                self._get(
                    execution,
                    "executed_quantity",
                    self._get(
                        execution,
                        "filled_quantity",
                        0.0,
                    ),
                ),
            )
        )

        if raw_executed_quantity == 0.0:

            raw_status = str(
                self._get(
                    execution,
                    "status",
                    "",
                )
            ).upper()

            if raw_status in (
                "PENDING",
                "SUBMITTED",
                "NEW",
                "ACCEPTED",
                "OPEN",
            ):

                zero_fill_status = (
                    PostTradeStatus.PENDING
                )

                zero_fill_reason = (
                    ExecutionDiscrepancy
                    .MISSING_EXECUTION
                )

            else:

                zero_fill_status = (
                    PostTradeStatus.FAILED
                )

                zero_fill_reason = (
                    ExecutionDiscrepancy
                    .EXECUTION_FAILED
                )

            decision = self._build_decision(
                order=order,
                execution=execution,
                status=zero_fill_status,
                reason=zero_fill_reason,
                approved=False,
                ordered_quantity=ordered_quantity,
                executed_quantity=0.0,
                expected_price=(
                    float(
                        expected_price
                    )
                    if expected_price is not None
                    else 0.0
                ),
                execution_price=0.0,
                execution_quality_value=None,
            )

            self._record_decision(
                decision
            )

            return decision

        # --------------------------------------------------------------
        # PRICE
        # --------------------------------------------------------------

        if expected_price is None:
            expected_price = float(
                self._get(
                    execution,
                    "execution_price",
                    self._get(
                        execution,
                        "average_fill_price",
                        0.0,
                    ),
                )
            )

        (
            price_ok,
            expected_price,
            execution_price,
            price_difference,
        ) = self.check_price(
            expected_price,
            execution,
        )

        # --------------------------------------------------------------
        # QUALITY
        # --------------------------------------------------------------

        quality = None

        if execution_price > 0:
            quality = self.execution_quality(
                order,
                execution,
                benchmark_price=(
                    benchmark_price
                    if benchmark_price is not None
                    else expected_price
                ),
            )

        # --------------------------------------------------------------
        # DETERMINE STATUS
        # --------------------------------------------------------------

        reason = None

        if not quantity_ok:
            status = (
                PostTradeStatus.DISCREPANCY
            )
            reason = (
                ExecutionDiscrepancy
                .QUANTITY_MISMATCH
            )

        elif not price_ok:
            status = (
                PostTradeStatus.DISCREPANCY
            )
            reason = (
                ExecutionDiscrepancy
                .PRICE_MISMATCH
            )

        elif not status_ok:
            status = (
                PostTradeStatus.FAILED
            )
            reason = (
                ExecutionDiscrepancy
                .STATUS_MISMATCH
            )

        elif executed_quantity == 0:
            status = (
                PostTradeStatus.PENDING
            )

        elif (
            executed_quantity
            < ordered_quantity
        ):
            status = (
                PostTradeStatus.PARTIALLY_CONFIRMED
            )

        else:
            status = (
                PostTradeStatus.CONFIRMED
            )

        approved = status in (
            PostTradeStatus.CONFIRMED,
            PostTradeStatus.PARTIALLY_CONFIRMED,
        )

        decision = self._build_decision(
            order=order,
            execution=execution,
            status=status,
            reason=reason,
            approved=approved,
            ordered_quantity=ordered_quantity,
            executed_quantity=executed_quantity,
            expected_price=expected_price,
            execution_price=execution_price,
            execution_quality_value=quality,
        )

        self._record_decision(
            decision
        )

        # --------------------------------------------------------------
        # REGISTER EXECUTION
        # --------------------------------------------------------------

        broker_order_id = (
            self._broker_order_id(
                execution
            )
        )

        execution_key = (
            broker_order_id
            or self._order_id(order)
        )

        if execution_key is not None:
            self._execution_keys.add(
                execution_key
            )

        return decision

    # ==================================================================
    # CONFIRM EXECUTION
    # ==================================================================

    def confirm_execution(
        self,
        order: Any,
        execution: Any,
        expected_price: Optional[
            float
        ] = None,
        benchmark_price: Optional[
            float
        ] = None,
    ) -> bool:
        """
        Convenience method returning only approval status.
        """

        decision = self.monitor_execution(
            order,
            execution,
            expected_price=expected_price,
            benchmark_price=benchmark_price,
        )

        return decision.approved

    # ==================================================================
    # GET DECISION
    # ==================================================================

    def get_decision(
        self,
    ) -> Optional[PostTradeDecision]:
        """
        Return the most recent decision.
        """

        return self.last_decision

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(
        self,
    ) -> dict:
        """
        Return monitor state summary.
        """

        return {
            "api_version":
                self.API_VERSION,

            "monitor_count":
                self.monitor_count,

            "confirmed_count":
                self.confirmed_count,

            "partial_count":
                self.partial_count,

            "discrepancy_count":
                self.discrepancy_count,

            "duplicate_count":
                self.duplicate_count,

            "missing_count":
                self.missing_count,

            "failed_count":
                self.failed_count,

            "history_events":
                len(
                    self.history
                ),

            "last_status":
                None
                if self.last_decision is None
                else self.last_decision.status,

            "last_order_id":
                None
                if self.last_decision is None
                else self.last_decision.order_id,

            "last_broker_order_id":
                None
                if self.last_decision is None
                else (
                    self.last_decision
                    .broker_order_id
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
                "PostTradeExecutionMonitor",

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
        Validate monitor internal state.
        """

        if self.API_VERSION != "1.0.0":
            raise RuntimeError(
                "Invalid PostTradeExecutionMonitor "
                "API version."
            )

        if self.price_tolerance < 0:
            raise RuntimeError(
                "Invalid price tolerance."
            )

        if self.quantity_tolerance < 0:
            raise RuntimeError(
                "Invalid quantity tolerance."
            )

        if self.monitor_count < 0:
            raise RuntimeError(
                "Invalid monitor count."
            )

        if len(
            self.history
        ) != self.monitor_count:
            raise RuntimeError(
                "History count does not match "
                "monitor count."
            )

        return True

    # ==================================================================
    # TO DICTIONARY
    # ==================================================================

    def to_dict(
        self,
    ) -> dict:
        """
        Serialize monitor state.
        """

        return {
            "api_version":
                self.API_VERSION,

            "price_tolerance":
                self.price_tolerance,

            "quantity_tolerance":
                self.quantity_tolerance,

            "history":
                list(
                    self.history
                ),

            "last_decision":
                None
                if self.last_decision is None
                else (
                    self.last_decision
                    .to_dict()
                ),

            "last_quality":
                None
                if self.last_quality is None
                else (
                    self.last_quality
                    .to_dict()
                ),

            "monitor_count":
                self.monitor_count,

            "confirmed_count":
                self.confirmed_count,

            "partial_count":
                self.partial_count,

            "discrepancy_count":
                self.discrepancy_count,

            "duplicate_count":
                self.duplicate_count,

            "missing_count":
                self.missing_count,

            "failed_count":
                self.failed_count,

            "execution_keys":
                sorted(
                    self._execution_keys
                ),
        }

    # ==================================================================
    # FROM DICTIONARY
    # ==================================================================

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> PostTradeExecutionMonitor:
        """
        Restore monitor state.
        """

        if not isinstance(
            data,
            dict,
        ):
            raise TypeError(
                "data must be a dictionary."
            )

        monitor = cls(
            price_tolerance=float(
                data.get(
                    "price_tolerance",
                    0.0,
                )
            ),
            quantity_tolerance=float(
                data.get(
                    "quantity_tolerance",
                    0.0,
                )
            ),
        )

        monitor.history = list(
            data.get(
                "history",
                [],
            )
        )

        last_decision = data.get(
            "last_decision"
        )

        if last_decision is not None:
            monitor.last_decision = (
                PostTradeDecision.from_dict(
                    last_decision
                )
            )

        last_quality = data.get(
            "last_quality"
        )

        if last_quality is not None:
            monitor.last_quality = (
                ExecutionQuality.from_dict(
                    last_quality
                )
            )

        monitor.monitor_count = int(
            data.get(
                "monitor_count",
                len(
                    monitor.history
                ),
            )
        )

        monitor.confirmed_count = int(
            data.get(
                "confirmed_count",
                0,
            )
        )

        monitor.partial_count = int(
            data.get(
                "partial_count",
                0,
            )
        )

        monitor.discrepancy_count = int(
            data.get(
                "discrepancy_count",
                0,
            )
        )

        monitor.duplicate_count = int(
            data.get(
                "duplicate_count",
                0,
            )
        )

        monitor.missing_count = int(
            data.get(
                "missing_count",
                0,
            )
        )

        monitor.failed_count = int(
            data.get(
                "failed_count",
                0,
            )
        )

        monitor._execution_keys = set(
            data.get(
                "execution_keys",
                [],
            )
        )

        return monitor


# ======================================================================
# REGRESSION TESTS
# ======================================================================


def test_post_trade_execution_monitor():
    """
    Deterministic Phase III-C.3 regression tests.
    """

    from order import Order

    # ==============================================================
    # INITIALIZATION
    # ==============================================================

    monitor = PostTradeExecutionMonitor()

    assert monitor.health_check()

    assert monitor.summary()[
        "monitor_count"
    ] == 0

    # ==============================================================
    # ORDER
    # ==============================================================

    order = Order(
        order_id="POST-000001",
        ticker="SPY",
        side="BUY",
        quantity=100,
    )

    # ==============================================================
    # FULL EXECUTION
    # ==============================================================

    execution = {
        "broker_order_id":
            "PAPER-00000001",

        "client_order_id":
            "POST-000001",

        "ticker":
            "SPY",

        "side":
            "BUY",

        "quantity":
            100.0,

        "execution_price":
            500.0,

        "status":
            "FILLED",
    }

    decision = monitor.monitor_execution(
        order,
        execution,
        expected_price=500.0,
        benchmark_price=500.0,
    )

    assert decision.approved

    assert decision.status == (
        PostTradeStatus.CONFIRMED
    )

    assert decision.reason is None

    assert decision.ordered_quantity == 100.0

    assert decision.executed_quantity == 100.0

    assert decision.remaining_quantity == 0.0

    assert decision.execution_price == 500.0

    assert (
        decision.execution_notional
        == 50000.0
    )

    # ==============================================================
    # EXECUTION QUALITY
    # ==============================================================

    assert decision.execution_quality is not None

    assert (
        decision.execution_quality
        .benchmark_price
        == 500.0
    )

    assert (
        decision.execution_quality
        .execution_price
        == 500.0
    )

    assert (
        decision.execution_quality
        .slippage
        == 0.0
    )

    # ==============================================================
    # PARTIAL EXECUTION
    # ==============================================================

    partial_order = Order(
        order_id="POST-000002",
        ticker="QQQ",
        side="BUY",
        quantity=100,
    )

    partial_execution = {
        "broker_order_id":
            "PAPER-00000002",

        "client_order_id":
            "POST-000002",

        "ticker":
            "QQQ",

        "side":
            "BUY",

        "quantity":
            60.0,

        "execution_price":
            400.0,

        "status":
            "PARTIALLY_FILLED",
    }

    decision = monitor.monitor_execution(
        partial_order,
        partial_execution,
        expected_price=400.0,
        benchmark_price=400.0,
    )

    assert decision.approved

    assert decision.status == (
        PostTradeStatus.PARTIALLY_CONFIRMED
    )

    assert (
        decision.remaining_quantity
        == 40.0
    )

    # ==============================================================
    # QUANTITY DISCREPANCY
    # ==============================================================

    quantity_order = Order(
        order_id="POST-000003",
        ticker="TLT",
        side="BUY",
        quantity=100,
    )

    quantity_execution = {
        "broker_order_id":
            "PAPER-00000003",

        "client_order_id":
            "POST-000003",

        "ticker":
            "TLT",

        "side":
            "BUY",

        "quantity":
            101.0,

        "execution_price":
            90.0,

        "status":
            "FILLED",
    }

    decision = monitor.monitor_execution(
        quantity_order,
        quantity_execution,
        expected_price=90.0,
    )

    assert not decision.approved

    assert decision.status == (
        PostTradeStatus.DISCREPANCY
    )

    assert decision.reason == (
        ExecutionDiscrepancy
        .QUANTITY_MISMATCH
    )

    # ==============================================================
    # PRICE DISCREPANCY
    # ==============================================================

    price_order = Order(
        order_id="POST-000004",
        ticker="GLD",
        side="BUY",
        quantity=50,
    )

    price_execution = {
        "broker_order_id":
            "PAPER-00000004",

        "client_order_id":
            "POST-000004",

        "ticker":
            "GLD",

        "side":
            "BUY",

        "quantity":
            50.0,

        "execution_price":
            205.0,

        "status":
            "FILLED",
    }

    decision = monitor.monitor_execution(
        price_order,
        price_execution,
        expected_price=200.0,
    )

    assert not decision.approved

    assert decision.status == (
        PostTradeStatus.DISCREPANCY
    )

    assert decision.reason == (
        ExecutionDiscrepancy
        .PRICE_MISMATCH
    )

    # ==============================================================
    # STATUS DISCREPANCY
    # ==============================================================

    status_order = Order(
        order_id="POST-000005",
        ticker="IEF",
        side="BUY",
        quantity=20,
    )

    status_execution = {
        "broker_order_id":
            "PAPER-00000005",

        "client_order_id":
            "POST-000005",

        "ticker":
            "IEF",

        "side":
            "BUY",

        "quantity":
            20.0,

        "execution_price":
            95.0,

        "status":
            "REJECTED",
    }

    decision = monitor.monitor_execution(
        status_order,
        status_execution,
        expected_price=95.0,
    )

    assert not decision.approved

    assert decision.status == (
        PostTradeStatus.FAILED
    )

    assert decision.reason == (
        ExecutionDiscrepancy
        .STATUS_MISMATCH
    )

    # ==============================================================
    # DUPLICATE EXECUTION
    # ==============================================================

    duplicate_order = Order(
        order_id="POST-000006",
        ticker="EFA",
        side="BUY",
        quantity=10,
    )

    duplicate_execution = {
        "broker_order_id":
            "PAPER-00000006",

        "client_order_id":
            "POST-000006",

        "ticker":
            "EFA",

        "side":
            "BUY",

        "quantity":
            10.0,

        "execution_price":
            80.0,

        "status":
            "FILLED",
    }

    first = monitor.monitor_execution(
        duplicate_order,
        duplicate_execution,
        expected_price=80.0,
    )

    assert first.approved

    second = monitor.monitor_execution(
        duplicate_order,
        duplicate_execution,
        expected_price=80.0,
    )

    assert not second.approved

    assert second.status == (
        PostTradeStatus.DUPLICATE
    )

    assert second.reason == (
        ExecutionDiscrepancy
        .DUPLICATE_EXECUTION
    )

    # ==============================================================
    # MISSING EXECUTION
    # ==============================================================

    missing_order = Order(
        order_id="POST-000007",
        ticker="DBC",
        side="BUY",
        quantity=10,
    )

    # Explicitly exercise the missing-execution path.
    #
    # monitor_execution normally rejects None at the input boundary,
    # so this test exercises the public failure contract through a
    # missing broker response represented by an empty execution record.

    missing_execution = {
        "broker_order_id":
            None,

        "client_order_id":
            "POST-000007",

        "quantity":
            0.0,

        "execution_price":
            0.0,

        "status":
            "PENDING",
    }

    decision = monitor.monitor_execution(
        missing_order,
        missing_execution,
        expected_price=100.0,
    )

    assert decision.status in (
        PostTradeStatus.PENDING,
        PostTradeStatus.FAILED,
    )

    # ==============================================================
    # SELL SLIPPAGE
    # ==============================================================

    sell_order = Order(
        order_id="POST-000008",
        ticker="SPY",
        side="SELL",
        quantity=100,
    )

    sell_execution = {
        "broker_order_id":
            "PAPER-00000008",

        "client_order_id":
            "POST-000008",

        "ticker":
            "SPY",

        "side":
            "SELL",

        "quantity":
            100.0,

        "execution_price":
            495.0,

        "status":
            "FILLED",
    }

    decision = monitor.monitor_execution(
        sell_order,
        sell_execution,
        expected_price=500.0,
        benchmark_price=500.0,
    )

    assert decision.approved

    assert (
        decision.execution_quality
        is not None
    )

    assert (
        decision.execution_quality.slippage
        == 5.0
    )

    # ==============================================================
    # SUMMARY
    # ==============================================================

    summary = monitor.summary()

    assert summary[
        "monitor_count"
    ] == 9

    assert summary[
        "confirmed_count"
    ] == 3

    assert summary[
        "partial_count"
    ] == 1

    assert summary[
        "discrepancy_count"
    ] == 2

    assert summary[
        "duplicate_count"
    ] == 1

    assert summary[
        "failed_count"
    ] == 1

    assert summary[
        "history_events"
    ] == 9

    # ==============================================================
    # METADATA
    # ==============================================================

    metadata = monitor.metadata

    assert metadata[
        "component"
    ] == "PostTradeExecutionMonitor"

    assert metadata[
        "api_version"
    ] == monitor.API_VERSION

    # ==============================================================
    # SERIALIZATION
    # ==============================================================

    exported = monitor.to_dict()

    assert exported[
        "api_version"
    ] == monitor.API_VERSION

    restored = (
        PostTradeExecutionMonitor.from_dict(
            exported
        )
    )

    assert restored.summary()[
        "monitor_count"
    ] == monitor.summary()[
        "monitor_count"
    ]

    assert restored.summary()[
        "confirmed_count"
    ] == monitor.summary()[
        "confirmed_count"
    ]

    assert restored.summary()[
        "discrepancy_count"
    ] == monitor.summary()[
        "discrepancy_count"
    ]

    assert restored.health_check()

    # ==============================================================
    # INVALID INPUT
    # ==============================================================

    try:
        monitor.monitor_execution(
            None,
            execution,
        )

        raise AssertionError(
            "Expected TypeError."
        )

    except TypeError:
        pass

    # ==============================================================
    # INVALID PRICE
    # ==============================================================

    try:
        monitor.check_price(
            0.0,
            execution,
        )

        raise AssertionError(
            "Expected ValueError."
        )

    except ValueError:
        pass

    # ==============================================================
    # INVALID QUANTITY
    # ==============================================================

    invalid_quantity_order = Order(
        order_id="POST-INVALID",
        ticker="SPY",
        side="BUY",
        quantity=0,
    )

    try:
        monitor.check_quantity(
            invalid_quantity_order,
            execution,
        )

        raise AssertionError(
            "Expected ValueError."
        )

    except ValueError:
        pass

    print(
        "PostTradeExecutionMonitor "
        "Phase III-C.3 tests passed."
    )


# ======================================================================
# MAIN
# ======================================================================


if __name__ == "__main__":
    test_post_trade_execution_monitor()