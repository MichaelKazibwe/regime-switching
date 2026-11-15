"""Fail-closed execution and durable state for a single paper portfolio."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime
import math
from typing import Any

import numpy as np
import pandas as pd

from authorizedexecutionhandoff import AuthorizedExecutionHandoff
from authorizedroutinghandoff import AuthorizedRoutingHandoff
from brokerrouter import BrokerRouter
from oms import OMS
from paperbroker import PaperBroker
from executionengine import ExecutionEngine
from transactioncostmodel import TransactionCostModel
from paperstore import SQLitePaperStore, SnapshotConflictError
from portfolioaccount import PortfolioAccount
from productionpipelineintegration import ProductionPipelineStatus
from reconciliationengine import ReconciliationEngine, ReconciliationStatus
from rebalanceengine import RebalanceEngine
from authorizedorderintent import AuthorizedOrderIntent


class PaperExecutionError(RuntimeError):
    """Raised when a paper execution cycle cannot safely complete."""


def _json_safe(value: Any) -> Any:
    """Convert nested immutable domain records to strict JSON values."""
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_safe(value.to_dict())
    if isinstance(value, float) and not math.isfinite(value):
        raise PaperExecutionError("Paper session state contains non-finite values.")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise PaperExecutionError(f"Unsupported persisted value: {type(value).__name__}.")


class PaperExecutionSession:
    """Execute an approved decision against the deterministic paper broker.

    Each externally visible lifecycle transition is checkpointed. Recovery
    restores the exact OMS/account/broker state; open orders cause a hard stop
    for operator review instead of automatic resubmission.
    """

    SNAPSHOT_KEY = "paper-execution-session"
    SCHEMA_VERSION = 2

    def __init__(
        self,
        store: SQLitePaperStore,
        initial_cash: float,
        commission_rate: float = 0.0005,
        slippage_rate: float = 0.001,
    ) -> None:
        self.store = store
        self.snapshot = store.load_snapshot(self.SNAPSHOT_KEY)
        self.revision = 0 if self.snapshot is None else self.snapshot.revision
        payload = {} if self.snapshot is None else self.snapshot.payload
        self.last_rebalance_data_as_of = payload.get("last_rebalance_data_as_of")
        self.valuation_history = list(payload.get("valuation_history", []))
        self.first_benchmark_price = payload.get("first_benchmark_price")
        self.initial_nav = float(payload.get("initial_nav", initial_cash))
        if payload and payload.get("schema_version") not in {1, self.SCHEMA_VERSION}:
            raise PaperExecutionError("Unsupported paper session snapshot version.")
        try:
            self.account = (
                PortfolioAccount(initial_cash)
                if not payload
                else PortfolioAccount.from_dict(payload["account"])
            )
            if payload:
                self.oms = OMS.from_dict(payload["oms"])
            else:
                self.oms = OMS(
                    execution_engine=ExecutionEngine(
                        transaction_cost_model=TransactionCostModel(
                            commission_rate=commission_rate,
                            slippage_rate=slippage_rate,
                        )
                    )
                )
            self.broker = (
                PaperBroker()
                if not payload
                else PaperBroker.from_dict(payload["broker"])
            )
            self.reconciliation = (
                ReconciliationEngine()
                if not payload or payload.get("reconciliation") is None
                else ReconciliationEngine.from_dict(payload["reconciliation"])
            )
        except Exception as exc:
            raise PaperExecutionError(f"Unable to restore paper session: {exc}") from exc
        if self.broker.broker_name != "PAPER":
            raise PaperExecutionError("Restored broker is not the PAPER broker.")
        model = self.oms.execution_engine.transaction_cost_model
        if not math.isclose(model.commission_rate, commission_rate, rel_tol=0.0, abs_tol=1e-12):
            raise PaperExecutionError(
                "Configured commission_rate differs from the persisted paper session."
            )
        if not math.isclose(model.slippage_rate, slippage_rate, rel_tol=0.0, abs_tol=1e-12):
            raise PaperExecutionError(
                "Configured slippage_rate differs from the persisted paper session."
            )
        if self.oms.order_book.active():
            raise PaperExecutionError(
                "Recovered state has outstanding OMS orders; reconcile manually before a new cycle."
            )

    def _checkpoint(self, cycle_id: str, phase: str) -> None:
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "cycle_id": cycle_id,
            "phase": phase,
            "last_rebalance_data_as_of": self.last_rebalance_data_as_of,
            "valuation_history": self.valuation_history,
            "first_benchmark_price": self.first_benchmark_price,
            "initial_nav": self.initial_nav,
            "account": self.account.to_dict(),
            "oms": self.oms.to_dict(),
            "broker": self.broker.to_dict(),
            "reconciliation": self.reconciliation.to_dict(),
        }
        payload = _json_safe(payload)
        try:
            saved = self.store.save_snapshot(
                self.SNAPSHOT_KEY,
                payload,
                schema_version=self.SCHEMA_VERSION,
                expected_revision=self.revision,
            )
        except SnapshotConflictError as exc:
            raise PaperExecutionError("Concurrent paper session writer detected.") from exc
        self.revision = saved.revision

    def _operator_metrics(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Mark holdings and costs from the most recent validated price row."""
        price_frame = inputs["prices"]
        prices = price_frame.iloc[-1].astype(float).to_dict()
        data_as_of = inputs["data_as_of"]
        if isinstance(data_as_of, str):
            data_as_of = datetime.fromisoformat(data_as_of.replace("Z", "+00:00"))
        data_as_of_text = data_as_of.isoformat()
        benchmark = str(inputs.get("benchmark", "SPY"))
        benchmark_price = float(prices.get(benchmark, 0.0))
        if benchmark_price <= 0:
            raise PaperExecutionError(f"Missing positive benchmark price for {benchmark}.")
        if self.first_benchmark_price is None:
            self.first_benchmark_price = benchmark_price
        nav = self.account.portfolio_value(pd.Series(prices, dtype=float))
        valuation = {
            "data_as_of": data_as_of_text,
            "nav": nav,
            "benchmark_price": benchmark_price,
        }
        if self.valuation_history and self.valuation_history[-1]["data_as_of"] == data_as_of_text:
            self.valuation_history[-1] = valuation
        else:
            self.valuation_history.append(valuation)
        portfolio_return = nav / self.initial_nav - 1.0
        benchmark_return = benchmark_price / self.first_benchmark_price - 1.0
        drawdown = min(
            (
                item["nav"] / max(
                    self.initial_nav,
                    *(past["nav"] for past in self.valuation_history[:index + 1]),
                ) - 1.0
                for index, item in enumerate(self.valuation_history)
            ),
            default=0.0,
        )
        return {
            "data_as_of": data_as_of_text,
            "portfolio_value": nav,
            "cash": self.account.cash,
            "cumulative_return_since_start": portfolio_return,
            "benchmark": benchmark,
            "benchmark_return_since_first_observation": benchmark_return,
            "active_return_since_start": portfolio_return - benchmark_return,
            "maximum_drawdown_since_start": drawdown,
            "cumulative_transaction_costs": float(sum(self.account.cost_history)),
            "cumulative_turnover": float(sum(self.account.turnover_history)),
            "valuation_observations": len(self.valuation_history),
            "positions_by_market_value": {
                ticker: {
                    "shares": position.shares,
                    "market_value": position.shares * float(prices[ticker]),
                    "weight": position.shares * float(prices[ticker]) / nav if nav else 0.0,
                }
                for ticker, position in self.account.positions.items()
                if ticker in prices
            },
            "fill_model": "latest_adjusted_close_with_separate_commission_and_slippage_costs",
            "fill_limitations": [
                "No intraday quote, spread, depth, or market impact data is available.",
                "Orders fill fully at the close; delayed, partial, and reject scenarios are covered only by broker lifecycle tests.",
            ],
        }

    def execute(
        self,
        result: Any,
        inputs: dict[str, Any],
        cycle_id: str,
        cash_buffer_fraction: float = 0.01,
        rebalance_interval_days: int = 21,
    ) -> dict[str, Any]:
        if result.status != ProductionPipelineStatus.APPROVED or not result.approved:
            metrics = self._operator_metrics(inputs)
            self._checkpoint(cycle_id, "DECISION_NOT_EXECUTED")
            return {
                "status": "NOT_EXECUTED",
                "reason": "decision_not_approved",
                "orders": [],
                "cash": self.account.cash,
                "positions": {ticker: position.shares for ticker, position in self.account.positions.items()},
                "operator_metrics": metrics,
            }

        gate = result.stage_results.get("production_execution_gate", {})
        authorization = gate.get("authorization")
        if authorization is None or not authorization.authorized:
            raise PaperExecutionError("Approved decision lacks a valid execution authorization.")
        if authorization.live_trading_enabled or authorization.broker_submission_enabled:
            raise PaperExecutionError("Authorization violates the paper-only execution boundary.")

        data_as_of = inputs["data_as_of"]
        if isinstance(data_as_of, str):
            data_as_of = datetime.fromisoformat(data_as_of.replace("Z", "+00:00"))
        if self.last_rebalance_data_as_of:
            previous_as_of = datetime.fromisoformat(
                self.last_rebalance_data_as_of.replace("Z", "+00:00")
            )
            elapsed_days = (data_as_of.date() - previous_as_of.date()).days
            if elapsed_days < rebalance_interval_days:
                metrics = self._operator_metrics(inputs)
                self._checkpoint(cycle_id, "REBALANCE_NOT_DUE")
                return {
                    "status": "NOT_DUE",
                    "reason": "rebalance_interval_not_elapsed",
                    "days_since_rebalance": elapsed_days,
                    "orders": [],
                    "cash": self.account.cash,
                    "positions": {ticker: position.shares for ticker, position in self.account.positions.items()},
                    "operator_metrics": metrics,
                }

        prices = inputs["prices"].iloc[-1].to_dict()
        target_weights = {
            ticker: float(weight) * (1.0 - cash_buffer_fraction)
            for ticker, weight in result.weights.items()
        }
        planned = RebalanceEngine().generate_orders(self.account, target_weights, prices)
        planned.sort(key=lambda order: (order.side != "SELL", order.ticker))
        self._checkpoint(cycle_id, "PLAN_CREATED")
        router = BrokerRouter()
        router.register_broker(self.broker)
        router.default_broker = "PAPER"
        receipts: list[dict[str, Any]] = []

        for index, planned_order in enumerate(planned, start=1):
            order_id = f"PAPER-{cycle_id}-{index:04d}"
            intent = AuthorizedOrderIntent.create_order(
                authorization,
                ticker=planned_order.ticker,
                side=planned_order.side,
                quantity=planned_order.quantity,
                order_id=order_id,
            )
            order = self.oms.submit_authorized_order(intent)
            execution_handoff = AuthorizedExecutionHandoff.from_intent(intent)
            routing_handoff = AuthorizedRoutingHandoff.from_execution_handoff(execution_handoff)
            self._checkpoint(cycle_id, f"ORDER_SUBMITTED:{order_id}")

            route = router.route_authorized_order(routing_handoff, broker_name="PAPER")
            if not route.approved:
                raise PaperExecutionError(f"Paper broker route rejected {order_id}: {route.reason}")
            self._checkpoint(cycle_id, f"ORDER_ROUTED:{order_id}")

            fill = self.broker.fill_order(order_id, execution_price=float(prices[order.ticker]))
            self._checkpoint(cycle_id, f"ORDER_FILLED:{order_id}")
            self.oms.execute_authorized_order(execution_handoff, fill, self.account)
            trade = self.oms.last_trade
            self._checkpoint(cycle_id, f"ACCOUNTED:{order_id}")

            broker_order = self.broker.get_order(order_id)
            account_position = self.account.positions.get(order.ticker)
            position_shares = 0.0 if account_position is None else account_position.shares
            reconciliation = self.reconciliation.reconcile_order(
                self.oms.order_book.get_order(order_id),
                broker_order,
                account_position=position_shares,
            )
            if reconciliation.status != ReconciliationStatus.MATCHED or not reconciliation.approved:
                self._checkpoint(cycle_id, f"RECONCILIATION_BREAK:{order_id}")
                raise PaperExecutionError(
                    f"Paper order reconciliation failed for {order_id}: {reconciliation.to_dict()}"
                )
            receipts.append({
                "order_id": order_id,
                "ticker": order.ticker,
                "side": order.side,
                "quantity": order.quantity,
                "fill_price": fill.execution_price,
                "fill_quantity": fill.quantity,
                "commission": 0.0 if trade is None else trade.commission,
                "estimated_slippage_cost": 0.0 if trade is None else trade.slippage,
                "total_transaction_cost": 0.0 if trade is None else trade.total_cost,
                "status": order.status,
                "decision_id": order.decision_id,
                "reconciliation": reconciliation.to_dict(),
            })
            self._checkpoint(cycle_id, f"RECONCILED:{order_id}")

        self.last_rebalance_data_as_of = data_as_of.isoformat()
        metrics = self._operator_metrics(inputs)
        self._checkpoint(cycle_id, "CYCLE_COMPLETE")

        return {
            "status": "EXECUTED" if receipts else "NO_ORDERS",
            "orders": receipts,
            "account": self.account.summary(),
            "positions": {ticker: position.shares for ticker, position in self.account.positions.items()},
            "cash": self.account.cash,
            "operator_metrics": metrics,
        }
