"""
======================================================================
executionanalytics.py

Institutional Execution Analytics Engine
======================================================================

Post-execution analytics and transaction-cost attribution layer.

Responsibilities
----------------

    - execution-quality measurement
    - slippage measurement
    - implementation shortfall
    - arrival-price analysis
    - benchmark analysis
    - fill-ratio analysis
    - explicit-cost analysis
    - implicit-cost analysis
    - total execution-cost analysis
    - broker-level analytics
    - ticker-level analytics
    - order-level analytics
    - portfolio-level execution aggregation
    - deterministic analytical records
    - serialization
    - metadata
    - health checks
    - regression tests

The ExecutionAnalytics engine does NOT:

    - submit orders
    - modify orders
    - modify PortfolioAccount
    - perform pre-trade risk checks
    - perform broker routing
    - perform reconciliation
    - approve or reject executions
    - generate trades
    - perform portfolio optimization

Those responsibilities belong to:

    OMS
    BrokerRouter
    PaperBroker / LiveBroker
    BrokerExecutionEngine
    ReconciliationEngine
    PostTradeExecutionMonitor
    TradeGenerator
    PortfolioOptimizer

Architecture
------------

    BrokerExecutionEngine
            |
            v
    ReconciliationEngine
            |
            v
    PostTradeExecutionMonitor
            |
            v
    ExecutionAnalytics
            |
            +--------------------+
            |                    |
            v                    v
    Order Analytics       Portfolio Analytics
            |
            v
    Performance Attribution

Author: Michael Kazibwe
Version: 1.0.0
======================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Optional


# ======================================================================
# EXECUTION ANALYTICS STATUS
# ======================================================================


class ExecutionAnalyticsStatus:
    """
    Analytical execution states.
    """

    ANALYZED = "ANALYZED"

    PARTIAL = "PARTIAL"

    FAILED = "FAILED"

    INVALID = "INVALID"


# ======================================================================
# EXECUTION ANALYTICS RESULT
# ======================================================================


@dataclass(frozen=True)
class ExecutionAnalyticsResult:
    """
    Immutable analytical result for one execution.
    """

    order_id: Optional[str]

    broker_order_id: Optional[str]

    ticker: Optional[str]

    side: Optional[str]

    broker: Optional[str]

    ordered_quantity: float

    executed_quantity: float

    remaining_quantity: float

    fill_ratio: float

    expected_price: float

    execution_price: float

    benchmark_price: float

    arrival_price: float

    price_difference: float

    price_difference_pct: float

    slippage: float

    slippage_pct: float

    implementation_shortfall: float

    implementation_shortfall_pct: float

    gross_notional: float

    explicit_cost: float

    implicit_cost: float

    total_execution_cost: float

    cost_per_share: float

    status: str

    timestamp: str

    def to_dict(self) -> dict:
        """
        Serialize the analytical result.
        """

        return {
            "order_id": self.order_id,
            "broker_order_id": self.broker_order_id,
            "ticker": self.ticker,
            "side": self.side,
            "broker": self.broker,
            "ordered_quantity": self.ordered_quantity,
            "executed_quantity": self.executed_quantity,
            "remaining_quantity": self.remaining_quantity,
            "fill_ratio": self.fill_ratio,
            "expected_price": self.expected_price,
            "execution_price": self.execution_price,
            "benchmark_price": self.benchmark_price,
            "arrival_price": self.arrival_price,
            "price_difference": self.price_difference,
            "price_difference_pct": self.price_difference_pct,
            "slippage": self.slippage,
            "slippage_pct": self.slippage_pct,
            "implementation_shortfall": (
                self.implementation_shortfall
            ),
            "implementation_shortfall_pct": (
                self.implementation_shortfall_pct
            ),
            "gross_notional": self.gross_notional,
            "explicit_cost": self.explicit_cost,
            "implicit_cost": self.implicit_cost,
            "total_execution_cost": self.total_execution_cost,
            "cost_per_share": self.cost_per_share,
            "status": self.status,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> ExecutionAnalyticsResult:
        """
        Restore an analytical result.
        """

        if not isinstance(data, dict):
            raise TypeError(
                "data must be a dictionary."
            )

        return cls(
            order_id=data.get("order_id"),
            broker_order_id=data.get(
                "broker_order_id"
            ),
            ticker=data.get("ticker"),
            side=data.get("side"),
            broker=data.get("broker"),
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
            fill_ratio=float(
                data.get(
                    "fill_ratio",
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
            benchmark_price=float(
                data.get(
                    "benchmark_price",
                    0.0,
                )
            ),
            arrival_price=float(
                data.get(
                    "arrival_price",
                    0.0,
                )
            ),
            price_difference=float(
                data.get(
                    "price_difference",
                    0.0,
                )
            ),
            price_difference_pct=float(
                data.get(
                    "price_difference_pct",
                    0.0,
                )
            ),
            slippage=float(
                data.get(
                    "slippage",
                    0.0,
                )
            ),
            slippage_pct=float(
                data.get(
                    "slippage_pct",
                    0.0,
                )
            ),
            implementation_shortfall=float(
                data.get(
                    "implementation_shortfall",
                    0.0,
                )
            ),
            implementation_shortfall_pct=float(
                data.get(
                    "implementation_shortfall_pct",
                    0.0,
                )
            ),
            gross_notional=float(
                data.get(
                    "gross_notional",
                    0.0,
                )
            ),
            explicit_cost=float(
                data.get(
                    "explicit_cost",
                    0.0,
                )
            ),
            implicit_cost=float(
                data.get(
                    "implicit_cost",
                    0.0,
                )
            ),
            total_execution_cost=float(
                data.get(
                    "total_execution_cost",
                    0.0,
                )
            ),
            cost_per_share=float(
                data.get(
                    "cost_per_share",
                    0.0,
                )
            ),
            status=data.get(
                "status",
                ExecutionAnalyticsStatus.ANALYZED,
            ),
            timestamp=data.get(
                "timestamp",
                "",
            ),
        )


# ======================================================================
# BROKER ANALYTICS
# ======================================================================


@dataclass(frozen=True)
class BrokerExecutionStatistics:
    """
    Aggregated execution statistics for one broker.
    """

    broker: str

    execution_count: int

    total_ordered_quantity: float

    total_executed_quantity: float

    total_notional: float

    total_execution_cost: float

    average_slippage_pct: float

    average_fill_ratio: float

    confirmed_count: int

    partial_count: int

    failed_count: int

    timestamp: str

    def to_dict(self) -> dict:
        """
        Serialize broker statistics.
        """

        return {
            "broker": self.broker,
            "execution_count": self.execution_count,
            "total_ordered_quantity": (
                self.total_ordered_quantity
            ),
            "total_executed_quantity": (
                self.total_executed_quantity
            ),
            "total_notional": self.total_notional,
            "total_execution_cost": (
                self.total_execution_cost
            ),
            "average_slippage_pct": (
                self.average_slippage_pct
            ),
            "average_fill_ratio": (
                self.average_fill_ratio
            ),
            "confirmed_count": self.confirmed_count,
            "partial_count": self.partial_count,
            "failed_count": self.failed_count,
            "timestamp": self.timestamp,
        }


# ======================================================================
# EXECUTION ANALYTICS ENGINE
# ======================================================================


class ExecutionAnalytics:
    """
    Institutional execution analytics engine.

    The engine consumes already-executed order information and produces
    deterministic execution-quality and transaction-cost measurements.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (
        "analyze_execution",
        "analyze_batch",
        "calculate_slippage",
        "calculate_implementation_shortfall",
        "calculate_fill_ratio",
        "calculate_execution_cost",
        "broker_statistics",
        "ticker_statistics",
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
        price_tolerance: float = 0.0,
        quantity_tolerance: float = 1e-9,
    ):
        """
        Initialize the analytics engine.

        Parameters
        ----------
        price_tolerance:
            Optional relative price tolerance used for classifying
            analytical price integrity.

        quantity_tolerance:
            Numerical tolerance for quantity comparisons.
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

        self.history: list[
            ExecutionAnalyticsResult
        ] = []

        self.last_result: Optional[
            ExecutionAnalyticsResult
        ] = None

        self.analysis_count = 0

        self.confirmed_count = 0

        self.partial_count = 0

        self.failed_count = 0

        self.invalid_count = 0

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
    # GENERIC VALUE ACCESS
    # ==================================================================

    @staticmethod
    def _get(
        source: Any,
        key: str,
        default: Any = None,
    ) -> Any:
        """
        Retrieve a value from either an object or dictionary.
        """

        if source is None:
            return default

        if isinstance(
            source,
            dict,
        ):
            return source.get(
                key,
                default,
            )

        return getattr(
            source,
            key,
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
        Retrieve an order identifier.
        """

        value = cls._get(
            order,
            "order_id",
        )

        if value is None:
            return None

        return str(value)

    # ==================================================================
    # BROKER ORDER ID
    # ==================================================================

    @classmethod
    def _broker_order_id(
        cls,
        execution: Any,
    ) -> Optional[str]:
        """
        Retrieve broker execution identifier.
        """

        value = cls._get(
            execution,
            "broker_order_id",
        )

        if value is None:
            return None

        return str(value)

    # ==================================================================
    # EXECUTION PRICE
    # ==================================================================

    @classmethod
    def _execution_price(
        cls,
        execution: Any,
    ) -> float:
        """
        Retrieve execution price.
        """

        value = cls._get(
            execution,
            "execution_price",
            cls._get(
                execution,
                "average_fill_price",
                0.0,
            ),
        )

        return float(value or 0.0)

    # ==================================================================
    # EXECUTED QUANTITY
    # ==================================================================

    @classmethod
    def _executed_quantity(
        cls,
        execution: Any,
    ) -> float:
        """
        Retrieve executed quantity.
        """

        value = cls._get(
            execution,
            "quantity",
            cls._get(
                execution,
                "executed_quantity",
                cls._get(
                    execution,
                    "filled_quantity",
                    0.0,
                ),
            ),
        )

        return float(value or 0.0)

    # ==================================================================
    # ORDER VALIDATION
    # ==================================================================

    @classmethod
    def _validate_inputs(
        cls,
        order: Any,
        execution: Any,
    ) -> None:
        """
        Validate the minimum analytical inputs.
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
                "order must contain an order_id."
            )

    # ==================================================================
    # FILL RATIO
    # ==================================================================

    def calculate_fill_ratio(
        self,
        ordered_quantity: float,
        executed_quantity: float,
    ) -> float:
        """
        Calculate executed quantity as a proportion of ordered quantity.
        """

        ordered_quantity = float(
            ordered_quantity
        )

        executed_quantity = float(
            executed_quantity
        )

        if ordered_quantity <= 0:
            raise ValueError(
                "ordered_quantity must be positive."
            )

        if executed_quantity < 0:
            raise ValueError(
                "executed_quantity cannot be negative."
            )

        if (
            executed_quantity
            > ordered_quantity
            + self.quantity_tolerance
        ):
            raise ValueError(
                "executed_quantity cannot exceed "
                "ordered_quantity."
            )

        ratio = (
            executed_quantity
            / ordered_quantity
        )

        return min(
            max(
                ratio,
                0.0,
            ),
            1.0,
        )

    # ==================================================================
    # SLIPPAGE
    # ==================================================================

    def calculate_slippage(
        self,
        side: str,
        benchmark_price: float,
        execution_price: float,
    ) -> tuple[
        float,
        float,
    ]:
        """
        Calculate execution slippage.

        BUY
            Positive slippage means execution above benchmark.

        SELL
            Positive slippage means execution below benchmark.

        Returns
        -------
        slippage, slippage_pct
        """

        if not isinstance(
            side,
            str,
        ):
            raise TypeError(
                "side must be a string."
            )

        side = side.strip().upper()

        if side not in (
            "BUY",
            "SELL",
        ):
            raise ValueError(
                "side must be BUY or SELL."
            )

        benchmark_price = float(
            benchmark_price
        )

        execution_price = float(
            execution_price
        )

        if benchmark_price <= 0:
            raise ValueError(
                "benchmark_price must be positive."
            )

        if execution_price <= 0:
            raise ValueError(
                "execution_price must be positive."
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

        return (
            slippage,
            slippage_pct,
        )

    # ==================================================================
    # IMPLEMENTATION SHORTFALL
    # ==================================================================

    def calculate_implementation_shortfall(
        self,
        side: str,
        arrival_price: float,
        execution_price: float,
        executed_quantity: float,
    ) -> tuple[
        float,
        float,
    ]:
        """
        Calculate implementation shortfall.

        The result is expressed as a positive execution cost when the
        trade moves against the investor.

        BUY
            execution above arrival is a cost.

        SELL
            execution below arrival is a cost.
        """

        if not isinstance(
            side,
            str,
        ):
            raise TypeError(
                "side must be a string."
            )

        side = side.strip().upper()

        if side not in (
            "BUY",
            "SELL",
        ):
            raise ValueError(
                "side must be BUY or SELL."
            )

        arrival_price = float(
            arrival_price
        )

        execution_price = float(
            execution_price
        )

        executed_quantity = float(
            executed_quantity
        )

        if arrival_price <= 0:
            raise ValueError(
                "arrival_price must be positive."
            )

        if execution_price <= 0:
            raise ValueError(
                "execution_price must be positive."
            )

        if executed_quantity < 0:
            raise ValueError(
                "executed_quantity cannot be negative."
            )

        if side == "BUY":
            price_impact = (
                execution_price
                - arrival_price
            )
        else:
            price_impact = (
                arrival_price
                - execution_price
            )

        shortfall = (
            price_impact
            * executed_quantity
        )

        shortfall_pct = (
            price_impact
            / arrival_price
        )

        return (
            shortfall,
            shortfall_pct,
        )

    # ==================================================================
    # EXECUTION COST
    # ==================================================================

    def calculate_execution_cost(
        self,
        implicit_cost: float,
        explicit_cost: float,
    ) -> tuple[
        float,
        float,
    ]:
        """
        Calculate total execution cost.

        Returns
        -------
        total_cost, cost_per_unit_basis
        """

        implicit_cost = float(
            implicit_cost
        )

        explicit_cost = float(
            explicit_cost
        )

        if implicit_cost < 0:
            raise ValueError(
                "implicit_cost cannot be negative."
            )

        if explicit_cost < 0:
            raise ValueError(
                "explicit_cost cannot be negative."
            )

        total_cost = (
            implicit_cost
            + explicit_cost
        )

        return (
            total_cost,
            total_cost,
        )

    # ==================================================================
    # ANALYZE EXECUTION
    # ==================================================================

    def analyze_execution(
        self,
        order: Any,
        execution: Any,
        expected_price: Optional[
            float
        ] = None,
        benchmark_price: Optional[
            float
        ] = None,
        arrival_price: Optional[
            float
        ] = None,
        explicit_cost: float = 0.0,
    ) -> ExecutionAnalyticsResult:
        """
        Analyze one completed or partially completed execution.

        This method does not modify the order or execution objects.
        """

        self._validate_inputs(
            order,
            execution,
        )

        ordered_quantity = float(
            self._get(
                order,
                "quantity",
                0.0,
            )
        )

        executed_quantity = (
            self._executed_quantity(
                execution
            )
        )

        if ordered_quantity <= 0:
            raise ValueError(
                "ordered quantity must be positive."
            )

        if executed_quantity < 0:
            raise ValueError(
                "executed quantity cannot be negative."
            )

        if (
            executed_quantity
            > ordered_quantity
            + self.quantity_tolerance
        ):
            raise ValueError(
                "executed quantity exceeds "
                "ordered quantity."
            )

        remaining_quantity = max(
            ordered_quantity
            - executed_quantity,
            0.0,
        )

        side = str(
            self._get(
                order,
                "side",
                "BUY",
            )
        ).upper()

        ticker = self._get(
            order,
            "ticker",
        )

        broker = self._get(
            execution,
            "broker",
            self._get(
                execution,
                "broker_name",
            ),
        )

        execution_price = (
            self._execution_price(
                execution
            )
        )

        if expected_price is None:
            expected_price = float(
                self._get(
                    execution,
                    "expected_price",
                    execution_price,
                )
                or execution_price
            )

        else:
            expected_price = float(
                expected_price
            )

        if benchmark_price is None:
            benchmark_price = float(
                self._get(
                    execution,
                    "benchmark_price",
                    expected_price,
                )
                or expected_price
            )

        else:
            benchmark_price = float(
                benchmark_price
            )

        if arrival_price is None:
            arrival_price = float(
                self._get(
                    execution,
                    "arrival_price",
                    benchmark_price,
                )
                or benchmark_price
            )

        else:
            arrival_price = float(
                arrival_price
            )

        if execution_price <= 0:
            raise ValueError(
                "execution price must be positive."
            )

        if expected_price <= 0:
            raise ValueError(
                "expected_price must be positive."
            )

        if benchmark_price <= 0:
            raise ValueError(
                "benchmark_price must be positive."
            )

        if arrival_price <= 0:
            raise ValueError(
                "arrival_price must be positive."
            )

        explicit_cost = float(
            explicit_cost
        )

        if explicit_cost < 0:
            raise ValueError(
                "explicit_cost cannot be negative."
            )

        # --------------------------------------------------------------
        # FILL RATIO
        # --------------------------------------------------------------

        fill_ratio = (
            self.calculate_fill_ratio(
                ordered_quantity,
                executed_quantity,
            )
        )

        # --------------------------------------------------------------
        # PRICE DIFFERENCE
        # --------------------------------------------------------------

        price_difference = (
            execution_price
            - expected_price
        )

        price_difference_pct = (
            price_difference
            / expected_price
        )

        # --------------------------------------------------------------
        # SLIPPAGE
        # --------------------------------------------------------------

        (
            slippage,
            slippage_pct,
        ) = self.calculate_slippage(
            side,
            benchmark_price,
            execution_price,
        )

        # --------------------------------------------------------------
        # IMPLEMENTATION SHORTFALL
        # --------------------------------------------------------------

        (
            implementation_shortfall,
            implementation_shortfall_pct,
        ) = self.calculate_implementation_shortfall(
            side,
            arrival_price,
            execution_price,
            executed_quantity,
        )

        # --------------------------------------------------------------
        # NOTIONAL
        # --------------------------------------------------------------

        gross_notional = (
            executed_quantity
            * execution_price
        )

        # --------------------------------------------------------------
        # IMPLICIT COST
        # --------------------------------------------------------------
        #
        # Only adverse price movement is treated as an execution cost.
        #
        # Favorable execution therefore does not create a negative
        # execution cost in the analytics layer.
        # --------------------------------------------------------------

        implicit_cost = max(
            implementation_shortfall,
            0.0,
        )

        total_execution_cost = (
            implicit_cost
            + explicit_cost
        )

        cost_per_share = (
            total_execution_cost
            / executed_quantity
            if executed_quantity > 0
            else 0.0
        )

        # --------------------------------------------------------------
        # STATUS
        # --------------------------------------------------------------

        raw_status = str(
            self._get(
                execution,
                "status",
                "",
            )
        ).upper()

        if raw_status in (
            "FILLED",
            "CONFIRMED",
            "EXECUTED",
        ):
            status = (
                ExecutionAnalyticsStatus.ANALYZED
                if fill_ratio >= (
                    1.0
                    - self.quantity_tolerance
                )
                else ExecutionAnalyticsStatus.PARTIAL
            )

        elif raw_status in (
            "PARTIALLY_FILLED",
            "PARTIAL",
        ):
            status = (
                ExecutionAnalyticsStatus.PARTIAL
            )

        else:
            status = (
                ExecutionAnalyticsStatus.FAILED
            )

        result = ExecutionAnalyticsResult(
            order_id=self._order_id(
                order
            ),
            broker_order_id=(
                self._broker_order_id(
                    execution
                )
            ),
            ticker=ticker,
            side=side,
            broker=(
                None
                if broker is None
                else str(broker)
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
            fill_ratio=fill_ratio,
            expected_price=expected_price,
            execution_price=execution_price,
            benchmark_price=benchmark_price,
            arrival_price=arrival_price,
            price_difference=price_difference,
            price_difference_pct=(
                price_difference_pct
            ),
            slippage=slippage,
            slippage_pct=slippage_pct,
            implementation_shortfall=(
                implementation_shortfall
            ),
            implementation_shortfall_pct=(
                implementation_shortfall_pct
            ),
            gross_notional=gross_notional,
            explicit_cost=explicit_cost,
            implicit_cost=implicit_cost,
            total_execution_cost=(
                total_execution_cost
            ),
            cost_per_share=cost_per_share,
            status=status,
            timestamp=self._timestamp(),
        )

        self.history.append(
            result
        )

        self.last_result = result

        self.analysis_count += 1

        if status == (
            ExecutionAnalyticsStatus.ANALYZED
        ):
            self.confirmed_count += 1

        elif status == (
            ExecutionAnalyticsStatus.PARTIAL
        ):
            self.partial_count += 1

        elif status == (
            ExecutionAnalyticsStatus.FAILED
        ):
            self.failed_count += 1

        elif status == (
            ExecutionAnalyticsStatus.INVALID
        ):
            self.invalid_count += 1

        return result

    # ==================================================================
    # ANALYZE BATCH
    # ==================================================================

    def analyze_batch(
        self,
        executions: list[
            tuple[Any, Any]
        ],
        expected_price: Optional[
            float
        ] = None,
        benchmark_price: Optional[
            float
        ] = None,
        arrival_price: Optional[
            float
        ] = None,
    ) -> list[
        ExecutionAnalyticsResult
    ]:
        """
        Analyze a deterministic batch of order/execution pairs.
        """

        if not isinstance(
            executions,
            list,
        ):
            raise TypeError(
                "executions must be a list."
            )

        results = []

        for item in executions:
            if not isinstance(
                item,
                tuple,
            ):
                raise TypeError(
                    "Each batch item must be "
                    "(order, execution)."
                )

            if len(item) != 2:
                raise ValueError(
                    "Each batch item must contain "
                    "exactly two elements."
                )

            order, execution = item

            results.append(
                self.analyze_execution(
                    order,
                    execution,
                    expected_price=(
                        expected_price
                    ),
                    benchmark_price=(
                        benchmark_price
                    ),
                    arrival_price=(
                        arrival_price
                    ),
                )
            )

        return results

    # ==================================================================
    # BROKER STATISTICS
    # ==================================================================

    def broker_statistics(
        self,
        broker: str,
    ) -> BrokerExecutionStatistics:
        """
        Aggregate execution statistics for one broker.
        """

        if not isinstance(
            broker,
            str,
        ):
            raise TypeError(
                "broker must be a string."
            )

        broker = broker.strip()

        if not broker:
            raise ValueError(
                "broker cannot be empty."
            )

        matching = [
            result
            for result in self.history
            if (
                result.broker == broker
            )
        ]

        execution_count = len(
            matching
        )

        if execution_count == 0:
            return BrokerExecutionStatistics(
                broker=broker,
                execution_count=0,
                total_ordered_quantity=0.0,
                total_executed_quantity=0.0,
                total_notional=0.0,
                total_execution_cost=0.0,
                average_slippage_pct=0.0,
                average_fill_ratio=0.0,
                confirmed_count=0,
                partial_count=0,
                failed_count=0,
                timestamp=self._timestamp(),
            )

        total_ordered_quantity = sum(
            result.ordered_quantity
            for result in matching
        )

        total_executed_quantity = sum(
            result.executed_quantity
            for result in matching
        )

        total_notional = sum(
            result.gross_notional
            for result in matching
        )

        total_execution_cost = sum(
            result.total_execution_cost
            for result in matching
        )

        average_slippage_pct = (
            sum(
                result.slippage_pct
                for result in matching
            )
            / execution_count
        )

        average_fill_ratio = (
            sum(
                result.fill_ratio
                for result in matching
            )
            / execution_count
        )

        confirmed_count = sum(
            result.status
            == ExecutionAnalyticsStatus.ANALYZED
            for result in matching
        )

        partial_count = sum(
            result.status
            == ExecutionAnalyticsStatus.PARTIAL
            for result in matching
        )

        failed_count = sum(
            result.status
            == ExecutionAnalyticsStatus.FAILED
            for result in matching
        )

        return BrokerExecutionStatistics(
            broker=broker,
            execution_count=execution_count,
            total_ordered_quantity=(
                total_ordered_quantity
            ),
            total_executed_quantity=(
                total_executed_quantity
            ),
            total_notional=total_notional,
            total_execution_cost=(
                total_execution_cost
            ),
            average_slippage_pct=(
                average_slippage_pct
            ),
            average_fill_ratio=(
                average_fill_ratio
            ),
            confirmed_count=confirmed_count,
            partial_count=partial_count,
            failed_count=failed_count,
            timestamp=self._timestamp(),
        )

    # ==================================================================
    # TICKER STATISTICS
    # ==================================================================

    def ticker_statistics(
        self,
        ticker: str,
    ) -> dict:
        """
        Aggregate execution statistics for one ticker.
        """

        if not isinstance(
            ticker,
            str,
        ):
            raise TypeError(
                "ticker must be a string."
            )

        ticker = ticker.strip()

        if not ticker:
            raise ValueError(
                "ticker cannot be empty."
            )

        matching = [
            result
            for result in self.history
            if (
                result.ticker == ticker
            )
        ]

        if not matching:
            return {
                "ticker": ticker,
                "execution_count": 0,
                "total_notional": 0.0,
                "total_execution_cost": 0.0,
                "average_slippage_pct": 0.0,
                "average_fill_ratio": 0.0,
            }

        count = len(
            matching
        )

        return {
            "ticker": ticker,
            "execution_count": count,
            "total_notional": sum(
                result.gross_notional
                for result in matching
            ),
            "total_execution_cost": sum(
                result.total_execution_cost
                for result in matching
            ),
            "average_slippage_pct": (
                sum(
                    result.slippage_pct
                    for result in matching
                )
                / count
            ),
            "average_fill_ratio": (
                sum(
                    result.fill_ratio
                    for result in matching
                )
                / count
            ),
        }

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(self) -> dict:
        """
        Return aggregate analytics state.
        """

        total_notional = sum(
            result.gross_notional
            for result in self.history
        )

        total_execution_cost = sum(
            result.total_execution_cost
            for result in self.history
        )

        average_slippage_pct = (
            sum(
                result.slippage_pct
                for result in self.history
            )
            / len(self.history)
            if self.history
            else 0.0
        )

        average_fill_ratio = (
            sum(
                result.fill_ratio
                for result in self.history
            )
            / len(self.history)
            if self.history
            else 0.0
        )

        return {
            "api_version":
                self.API_VERSION,

            "analysis_count":
                self.analysis_count,

            "confirmed_count":
                self.confirmed_count,

            "partial_count":
                self.partial_count,

            "failed_count":
                self.failed_count,

            "invalid_count":
                self.invalid_count,

            "history_events":
                len(self.history),

            "total_notional":
                total_notional,

            "total_execution_cost":
                total_execution_cost,

            "average_slippage_pct":
                average_slippage_pct,

            "average_fill_ratio":
                average_fill_ratio,

            "last_order_id":
                None
                if self.last_result is None
                else self.last_result.order_id,

            "last_broker_order_id":
                None
                if self.last_result is None
                else (
                    self.last_result
                    .broker_order_id
                ),

            "last_status":
                None
                if self.last_result is None
                else self.last_result.status,
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
                "ExecutionAnalytics",

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

    def health_check(self) -> bool:
        """
        Validate analytics engine state.
        """

        if self.API_VERSION != "1.0.0":
            raise RuntimeError(
                "Invalid ExecutionAnalytics API version."
            )

        if self.price_tolerance < 0:
            raise RuntimeError(
                "Invalid price tolerance."
            )

        if self.quantity_tolerance < 0:
            raise RuntimeError(
                "Invalid quantity tolerance."
            )

        if self.analysis_count != len(
            self.history
        ):
            raise RuntimeError(
                "Analysis count does not match history."
            )

        for result in self.history:

            if result.ordered_quantity <= 0:
                raise RuntimeError(
                    "Invalid ordered quantity in history."
                )

            if result.executed_quantity < 0:
                raise RuntimeError(
                    "Invalid executed quantity in history."
                )

            if (
                result.executed_quantity
                > result.ordered_quantity
                + self.quantity_tolerance
            ):
                raise RuntimeError(
                    "History contains an overfill."
                )

            if result.execution_price <= 0:
                raise RuntimeError(
                    "History contains invalid execution price."
                )

        return True

    # ==================================================================
    # TO DICTIONARY
    # ==================================================================

    def to_dict(self) -> dict:
        """
        Serialize analytics engine state.
        """

        return {
            "api_version":
                self.API_VERSION,

            "price_tolerance":
                self.price_tolerance,

            "quantity_tolerance":
                self.quantity_tolerance,

            "analysis_count":
                self.analysis_count,

            "confirmed_count":
                self.confirmed_count,

            "partial_count":
                self.partial_count,

            "failed_count":
                self.failed_count,

            "invalid_count":
                self.invalid_count,

            "history":
                [
                    result.to_dict()
                    for result in self.history
                ],
        }

    # ==================================================================
    # FROM DICTIONARY
    # ==================================================================

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> ExecutionAnalytics:
        """
        Restore analytics engine state.
        """

        if not isinstance(
            data,
            dict,
        ):
            raise TypeError(
                "data must be a dictionary."
            )

        engine = cls(
            price_tolerance=float(
                data.get(
                    "price_tolerance",
                    0.0,
                )
            ),
            quantity_tolerance=float(
                data.get(
                    "quantity_tolerance",
                    1e-9,
                )
            ),
        )

        engine.history = [
            ExecutionAnalyticsResult.from_dict(
                item
            )
            for item in data.get(
                "history",
                [],
            )
        ]

        engine.analysis_count = int(
            data.get(
                "analysis_count",
                len(
                    engine.history
                ),
            )
        )

        engine.confirmed_count = int(
            data.get(
                "confirmed_count",
                0,
            )
        )

        engine.partial_count = int(
            data.get(
                "partial_count",
                0,
            )
        )

        engine.failed_count = int(
            data.get(
                "failed_count",
                0,
            )
        )

        engine.invalid_count = int(
            data.get(
                "invalid_count",
                0,
            )
        )

        if engine.history:
            engine.last_result = (
                engine.history[-1]
            )

        return engine


# ======================================================================
# REGRESSION TESTS
# ======================================================================


def test_execution_analytics() -> None:
    """
    Deterministic regression tests for ExecutionAnalytics.
    """

    # ==============================================================
    # CONSTRUCTOR
    # ==============================================================

    analytics = ExecutionAnalytics()

    assert analytics.API_VERSION == "1.0.0"

    assert analytics.summary()[
        "analysis_count"
    ] == 0

    assert analytics.health_check()

    # ==============================================================
    # NORMAL BUY EXECUTION
    # ==============================================================

    buy_order = {
        "order_id": "EA-000001",
        "ticker": "SPY",
        "side": "BUY",
        "quantity": 100.0,
    }

    buy_execution = {
        "broker_order_id": "PAPER-00000001",
        "client_order_id": "EA-000001",
        "ticker": "SPY",
        "side": "BUY",
        "quantity": 100.0,
        "execution_price": 505.0,
        "status": "FILLED",
        "broker": "PAPER",
    }

    result = analytics.analyze_execution(
        buy_order,
        buy_execution,
        expected_price=500.0,
        benchmark_price=500.0,
        arrival_price=500.0,
    )

    assert result.status == (
        ExecutionAnalyticsStatus.ANALYZED
    )

    assert result.executed_quantity == 100.0

    assert result.fill_ratio == 1.0

    assert result.gross_notional == 50500.0

    assert result.slippage == 5.0

    assert result.slippage_pct == 0.01

    assert result.implementation_shortfall == 500.0

    assert result.total_execution_cost == 500.0

    assert result.cost_per_share == 5.0

    # ==============================================================
    # PARTIAL EXECUTION
    # ==============================================================

    partial_order = {
        "order_id": "EA-000002",
        "ticker": "QQQ",
        "side": "BUY",
        "quantity": 100.0,
    }

    partial_execution = {
        "broker_order_id": "PAPER-00000002",
        "client_order_id": "EA-000002",
        "quantity": 40.0,
        "execution_price": 400.0,
        "status": "PARTIALLY_FILLED",
        "broker": "PAPER",
    }

    partial_result = analytics.analyze_execution(
        partial_order,
        partial_execution,
        expected_price=400.0,
        benchmark_price=400.0,
        arrival_price=400.0,
    )

    assert partial_result.status == (
        ExecutionAnalyticsStatus.PARTIAL
    )

    assert partial_result.fill_ratio == 0.4

    assert partial_result.remaining_quantity == 60.0

    # ==============================================================
    # SELL EXECUTION
    # ==============================================================

    sell_order = {
        "order_id": "EA-000003",
        "ticker": "SPY",
        "side": "SELL",
        "quantity": 100.0,
    }

    sell_execution = {
        "broker_order_id": "PAPER-00000003",
        "client_order_id": "EA-000003",
        "quantity": 100.0,
        "execution_price": 495.0,
        "status": "FILLED",
        "broker": "PAPER",
    }

    sell_result = analytics.analyze_execution(
        sell_order,
        sell_execution,
        expected_price=500.0,
        benchmark_price=500.0,
        arrival_price=500.0,
    )

    assert sell_result.status == (
        ExecutionAnalyticsStatus.ANALYZED
    )

    assert sell_result.slippage == 5.0

    assert sell_result.slippage_pct == 0.01

    assert sell_result.implementation_shortfall == 500.0

    # ==============================================================
    # EXPLICIT COST
    # ==============================================================

    cost_order = {
        "order_id": "EA-000004",
        "ticker": "TLT",
        "side": "BUY",
        "quantity": 50.0,
    }

    cost_execution = {
        "broker_order_id": "PAPER-00000004",
        "client_order_id": "EA-000004",
        "quantity": 50.0,
        "execution_price": 100.0,
        "status": "FILLED",
        "broker": "PAPER",
    }

    cost_result = analytics.analyze_execution(
        cost_order,
        cost_execution,
        expected_price=100.0,
        benchmark_price=100.0,
        arrival_price=100.0,
        explicit_cost=25.0,
    )

    assert cost_result.implicit_cost == 0.0

    assert cost_result.explicit_cost == 25.0

    assert cost_result.total_execution_cost == 25.0

    assert cost_result.cost_per_share == 0.5

    # ==============================================================
    # FAVORABLE EXECUTION
    # ==============================================================

    favorable_order = {
        "order_id": "EA-000005",
        "ticker": "GLD",
        "side": "BUY",
        "quantity": 20.0,
    }

    favorable_execution = {
        "broker_order_id": "PAPER-00000005",
        "client_order_id": "EA-000005",
        "quantity": 20.0,
        "execution_price": 195.0,
        "status": "FILLED",
        "broker": "PAPER",
    }

    favorable_result = analytics.analyze_execution(
        favorable_order,
        favorable_execution,
        expected_price=200.0,
        benchmark_price=200.0,
        arrival_price=200.0,
    )

    assert favorable_result.slippage == -5.0

    assert favorable_result.implementation_shortfall == -100.0

    assert favorable_result.implicit_cost == 0.0

    assert favorable_result.total_execution_cost == 0.0

    # ==============================================================
    # CALCULATE FILL RATIO
    # ==============================================================

    assert (
        analytics.calculate_fill_ratio(
            100.0,
            50.0,
        )
        == 0.5
    )

    # ==============================================================
    # CALCULATE SLIPPAGE
    # ==============================================================

    slippage, slippage_pct = (
        analytics.calculate_slippage(
            "BUY",
            100.0,
            101.0,
        )
    )

    assert slippage == 1.0

    assert slippage_pct == 0.01

    slippage, slippage_pct = (
        analytics.calculate_slippage(
            "SELL",
            100.0,
            99.0,
        )
    )

    assert slippage == 1.0

    assert slippage_pct == 0.01

    # ==============================================================
    # IMPLEMENTATION SHORTFALL
    # ==============================================================

    shortfall, shortfall_pct = (
        analytics.calculate_implementation_shortfall(
            "BUY",
            100.0,
            102.0,
            50.0,
        )
    )

    assert shortfall == 100.0

    assert shortfall_pct == 0.02

    # ==============================================================
    # BROKER STATISTICS
    # ==============================================================

    broker_stats = (
        analytics.broker_statistics(
            "PAPER"
        )
    )

    assert broker_stats.execution_count == 5

    assert (
        broker_stats.total_ordered_quantity
        == 370.0
    )

    assert (
        broker_stats.total_executed_quantity
        == 310.0
    )

    assert (
        broker_stats.confirmed_count
        == 4
    )

    assert (
        broker_stats.partial_count
        == 1
    )

    # ==============================================================
    # TICKER STATISTICS
    # ==============================================================

    spy_stats = (
        analytics.ticker_statistics(
            "SPY"
        )
    )

    assert spy_stats[
        "execution_count"
    ] == 2

    assert spy_stats[
        "total_notional"
    ] == 100000.0

    # ==============================================================
    # SUMMARY
    # ==============================================================

    summary = analytics.summary()

    assert summary[
        "analysis_count"
    ] == 5

    assert summary[
        "confirmed_count"
    ] == 4

    assert summary[
        "partial_count"
    ] == 1

    assert summary[
        "failed_count"
    ] == 0

    assert summary[
        "history_events"
    ] == 5

    assert summary[
        "total_notional"
    ] == (
        50500.0
        + 16000.0
        + 49500.0
        + 5000.0
        + 3900.0
    )

    # ==============================================================
    # SERIALIZATION
    # ==============================================================

    serialized = analytics.to_dict()

    assert serialized[
        "api_version"
    ] == analytics.API_VERSION

    restored = (
        ExecutionAnalytics.from_dict(
            serialized
        )
    )

    assert restored.summary()[
        "analysis_count"
    ] == analytics.summary()[
        "analysis_count"
    ]

    assert restored.summary()[
        "confirmed_count"
    ] == analytics.summary()[
        "confirmed_count"
    ]

    assert len(
        restored.history
    ) == len(
        analytics.history
    )

    # ==============================================================
    # METADATA
    # ==============================================================

    metadata = analytics.metadata

    assert metadata[
        "component"
    ] == "ExecutionAnalytics"

    assert metadata[
        "api_version"
    ] == analytics.API_VERSION

    assert (
        "analyze_execution"
        in metadata[
            "public_methods"
        ]
    )

    # ==============================================================
    # HEALTH CHECK
    # ==============================================================

    assert analytics.health_check()

    assert restored.health_check()

    print(
        "ExecutionAnalytics Phase III-C.4 tests passed."
    )


# ======================================================================
# MODULE ENTRY POINT
# ======================================================================


if __name__ == "__main__":
    test_execution_analytics()