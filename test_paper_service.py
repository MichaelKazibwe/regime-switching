import json
from datetime import datetime, timezone

from paper_service import _safe_error_message, run_once
from paperconfig import PaperRuntimeConfig
from productiondecisionexecution import ProductionDecisionExecution


def test_paper_service_writes_operator_report(tmp_path) -> None:
    now = datetime.now(timezone.utc)
    returns = ProductionDecisionExecution.build_returns()
    observations = {
        "portfolio": ProductionDecisionExecution.build_portfolio(),
        "returns": returns,
        "prices": ProductionDecisionExecution.build_prices(returns),
        "regimes": ProductionDecisionExecution.build_regimes(),
        "macro_data": ProductionDecisionExecution.build_macro_data(),
        "scenarios": ProductionDecisionExecution.build_scenarios(),
        "data_as_of": now,
        "data_source": "DETERMINISTIC_TEST_FIXTURE",
    }
    config = PaperRuntimeConfig(
        state_database=tmp_path / "state.sqlite3",
        audit_log=tmp_path / "audit.jsonl",
        report_directory=tmp_path / "reports",
        alert_file=tmp_path / "alerts.jsonl",
    )

    report = run_once(config, "service-cycle", input_provider=lambda: observations)

    stored = json.loads((config.report_directory / "service-cycle.json").read_text())
    assert report["status"] == "APPROVED"
    assert stored["decision"]["paper_execution"]["status"] == "EXECUTED"
    assert stored["decision"]["risk_validation"]["risk_budget"]["budget_error"] <= 1e-6
    execution = stored["decision"]["paper_execution"]
    assert execution["operator_metrics"]["positions_by_market_value"]
    assert execution["operator_metrics"]["cumulative_transaction_costs"] > 0
    assert execution["orders"][0]["commission"] > 0
    assert stored["configuration"]["slippage_rate"] == config.slippage_rate
    assert config.dashboard_file.exists()
    assert "Paper Portfolio Operations" in config.dashboard_file.read_text()
    assert not config.alert_file.exists()


def test_failure_report_redacts_secrets(monkeypatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "fred-secret-value")
    message = _safe_error_message(
        RuntimeError("request failed api_key=fred-secret-value&series=GDP")
    )
    assert "fred-secret-value" not in message
    assert "api_key=[REDACTED]" in message
