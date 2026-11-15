from datetime import datetime, timedelta, timezone

from paper_runtime import PaperDecisionRunner
from paperconfig import PaperRuntimeConfig
from paperexecution import PaperExecutionSession
from paperstore import SQLitePaperStore
from productiondecisionexecution import ProductionDecisionExecution


def _inputs(as_of: datetime) -> dict:
    returns = ProductionDecisionExecution.build_returns()
    return {
        "portfolio": ProductionDecisionExecution.build_portfolio(),
        "returns": returns,
        "prices": ProductionDecisionExecution.build_prices(returns),
        "regimes": ProductionDecisionExecution.build_regimes(),
        "macro_data": ProductionDecisionExecution.build_macro_data(),
        "scenarios": ProductionDecisionExecution.build_scenarios(),
        "data_as_of": as_of,
        "data_source": "DETERMINISTIC_TEST_FIXTURE",
    }


def test_paper_cycle_routes_fills_reconciles_and_recovers(tmp_path) -> None:
    now = datetime.now(timezone.utc)
    config = PaperRuntimeConfig(
        state_database=tmp_path / "paper.sqlite3",
        audit_log=tmp_path / "audit.jsonl",
    )
    store = SQLitePaperStore(config.state_database)
    session = PaperExecutionSession(store, config.initial_cash)
    inputs = _inputs(now)
    runner = PaperDecisionRunner(
        config,
        store=store,
        input_provider=lambda: inputs,
        execution_handler=lambda result, observations, cycle: session.execute(
            result,
            observations,
            cycle,
            cash_buffer_fraction=config.cash_buffer_fraction,
        ),
        clock=lambda: now,
    )

    event = runner.run_once("paper-integration")
    result = event.payload["result"]

    execution = result["paper_execution"]
    assert result["status"] == "APPROVED"
    assert execution["status"] == "EXECUTED"
    assert len(execution["orders"]) > 0
    assert result["risk_validation"]["risk_validation"]["risk_budget_compliant"] is True
    assert result["risk_validation"]["risk_budget"]["budget_error"] <= 1e-6
    assert all(order["reconciliation"]["approved"] for order in execution["orders"])
    assert all(order["decision_id"] == result["decision_id"] for order in execution["orders"])
    assert all(order["total_transaction_cost"] > 0 for order in execution["orders"])
    assert execution["operator_metrics"]["portfolio_value"] > 0
    assert execution["operator_metrics"]["cumulative_transaction_costs"] > 0
    assert execution["operator_metrics"]["benchmark"] == "SPY"
    assert execution["operator_metrics"]["valuation_observations"] == 1

    restored = PaperExecutionSession(store, config.initial_cash)
    assert restored.account.summary()["positions"] == len(config.assets)
    assert restored.broker.fill_count == len(execution["orders"])
    assert restored.oms.order_book.active_count == 0
    assert store.verify_event_chain()

    next_day = now + timedelta(days=1)
    next_runner = PaperDecisionRunner(
        config,
        store=store,
        input_provider=lambda: _inputs(next_day),
        execution_handler=lambda output, observations, cycle: restored.execute(
            output,
            observations,
            cycle,
            cash_buffer_fraction=config.cash_buffer_fraction,
            rebalance_interval_days=config.rebalance_interval_days,
        ),
        clock=lambda: next_day,
    )
    next_event = next_runner.run_once("next-day")
    assert next_event.payload["result"]["paper_execution"]["status"] == "NOT_DUE"
    assert restored.broker.fill_count == len(execution["orders"])
    assert runner.run_once("paper-integration") == event
