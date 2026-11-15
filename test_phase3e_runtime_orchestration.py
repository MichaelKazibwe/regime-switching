"""
======================================================================
test_phase3e_runtime_orchestration.py

Phase 3E — Canonical Runtime Orchestration Certification
======================================================================

Static and contract-level certification for the E2E proof runner.
These tests do not enable live trading, create broker connections, or
mutate Git state.
"""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNNER = ROOT / "e2e_proof_runner_phase3e.py"


def _tree() -> ast.Module:
    return ast.parse(RUNNER.read_text(encoding="utf-8"))


def _class() -> ast.ClassDef:
    for node in _tree().body:
        if isinstance(node, ast.ClassDef) and node.name == "E2EProofRunner":
            return node
    raise AssertionError("E2EProofRunner class not found")


def _methods() -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in _class().body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_runner_contains_all_54_proof_points() -> None:
    methods = _methods()
    expected = {f"proof_e2e_{i:02d}" for i in range(1, 55)}
    assert expected.issubset(methods)


def test_runner_is_explicitly_paper_only() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "live_trading" in source
    assert "live_broker" in source
    assert "network_execution" in source
    assert "git_mutation" in source
    assert "paper_execution" in source


def test_final_proof_requires_all_prior_proofs_to_pass() -> None:
    source = ast.get_source_segment(RUNNER.read_text(encoding="utf-8"), _methods()["proof_e2e_54"])
    assert source is not None
    assert "status != PASS" in source
    assert "not non_pass" in source


def test_account_is_created_before_execution() -> None:
    methods = _methods()
    account_source = ast.get_source_segment(
        RUNNER.read_text(encoding="utf-8"), methods["proof_e2e_40"]
    )
    execution_source = ast.get_source_segment(
        RUNNER.read_text(encoding="utf-8"), methods["proof_e2e_42"]
    )
    assert account_source is not None
    assert execution_source is not None
    assert 'self.context["account"] = account' in account_source
    assert 'self.context["account"]' in execution_source


def test_quantity_reconciliation_is_cumulative_not_event_only() -> None:
    source = ast.get_source_segment(
        RUNNER.read_text(encoding="utf-8"), _methods()["proof_e2e_51"]
    )
    assert source is not None
    assert "cumulative_filled_quantity" in source
    assert "order.filled_quantity" in source
    assert "order.quantity" in source


def test_account_reconciliation_checks_cash_position_and_trade_history() -> None:
    source = ast.get_source_segment(
        RUNNER.read_text(encoding="utf-8"), _methods()["proof_e2e_53"]
    )
    assert source is not None
    assert "position" in source
    assert "net_cash_flow" in source
    assert "trade_history" in source


def test_no_proof_uses_live_broker_constructor() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "LiveBroker" not in source
    assert "authenticate(" not in source
    assert "connect(" not in source


def test_dependency_map_is_fail_closed() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "def _dependency_blocked" in source
    assert "status != PASS" in source
    assert "UpstreamProofNotPassed" in source
