from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from paper_runtime import PaperDecisionRunner, PaperRuntimeError
from paperconfig import PaperRuntimeConfig
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


def test_paper_runner_uses_supplied_inputs_and_persists_cycle(tmp_path) -> None:
    now = datetime.now(timezone.utc)
    config = PaperRuntimeConfig(
        state_database=tmp_path / "paper.sqlite3",
        audit_log=tmp_path / "audit.jsonl",
    )
    calls = 0

    def provide_inputs() -> dict:
        nonlocal calls
        calls += 1
        return _inputs(now)

    runner = PaperDecisionRunner(
        config,
        store=SQLitePaperStore(config.state_database),
        input_provider=provide_inputs,
        clock=lambda: now,
    )
    event = runner.run_once("2026-10-29")
    retry = runner.run_once("2026-10-29")

    assert calls == 1
    assert retry == event
    assert event.payload["data_source"] == "DETERMINISTIC_TEST_FIXTURE"
    assert event.payload["input_fingerprint"]
    assert runner.store.verify_event_chain()
    assert runner.audit_trail.verify()["healthy"]


def test_paper_runner_rejects_stale_market_data(tmp_path) -> None:
    now = datetime.now(timezone.utc)
    config = PaperRuntimeConfig(
        state_database=tmp_path / "paper.sqlite3",
        audit_log=tmp_path / "audit.jsonl",
        maximum_price_age_hours=24,
    )
    runner = PaperDecisionRunner(
        config,
        input_provider=lambda: _inputs(now - timedelta(hours=25)),
        clock=lambda: now,
    )

    with pytest.raises(PaperRuntimeError, match="stale"):
        runner.run_once("stale-cycle")
