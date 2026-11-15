"""
Phase 3D Step 1 regression tests.

Scope
-----
Certify decision identity uniqueness and strict restoration semantics before
moving to downstream lifecycle hardening.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

from portfoliodecisionengine import (  # noqa: E402
    PortfolioDecision,
    PortfolioDecisionEngine,
    PortfolioDecisionStatus,
)


def _decision(decision_id: str) -> PortfolioDecision:
    return PortfolioDecision(
        decision_id=decision_id,
        status=PortfolioDecisionStatus.APPROVED.value,
        approved=True,
        regime="EXPANSION",
        tickers=("SPY", "TLT"),
        weights={"SPY": 0.5, "TLT": 0.5},
        expected_returns={"SPY": 0.05, "TLT": 0.05},
        covariance={
            "SPY": {"SPY": 0.04, "TLT": 0.0},
            "TLT": {"SPY": 0.0, "TLT": 0.04},
        },
        portfolio_return=0.05,
        portfolio_volatility=0.2,
        portfolio_variance=0.04,
        gross_exposure=1.0,
        net_exposure=1.0,
        number_of_positions=2,
        risk_contributions={"SPY": 0.02, "TLT": 0.02},
        risk_contribution_pct={"SPY": 0.5, "TLT": 0.5},
        scenario_results={"status": "COMPLETED"},
        diagnostics={},
        warnings=(),
        errors=(),
        timestamp="2026-09-07T00:00:00+00:00",
        api_version="1.0.0",
    )


def test_reset_does_not_reuse_decision_id() -> None:
    engine = PortfolioDecisionEngine()

    first = engine._next_decision_id()
    engine.reset()
    second = engine._next_decision_id()

    assert first != second
    assert first.endswith("-00000001")
    assert second.endswith("-00000002")
    assert first.rsplit("-", 1)[0] == second.rsplit("-", 1)[0]


def test_fresh_engines_have_distinct_identity_namespaces() -> None:
    first = PortfolioDecisionEngine()
    second = PortfolioDecisionEngine()

    assert first._identity_namespace != second._identity_namespace
    assert first._next_decision_id() != second._next_decision_id()


def test_serialization_preserves_identity_namespace_and_sequence() -> None:
    engine = PortfolioDecisionEngine()
    first = engine._next_decision_id()
    state = engine.to_dict()

    restored = PortfolioDecisionEngine.from_dict(state)
    next_id = restored._next_decision_id()

    assert restored._identity_namespace == engine._identity_namespace
    assert next_id != first
    assert next_id.endswith("-00000002")
    assert next_id.rsplit("-", 1)[0] == first.rsplit("-", 1)[0]


def test_malformed_decision_state_fails_closed() -> None:
    decision = _decision("PDEC-LEGACY-00000001")
    state = PortfolioDecisionEngine().to_dict()
    state["decisions"] = [decision.to_dict(), {"not": "a valid decision"}]
    state["sequence"] = 1

    with pytest.raises((TypeError, ValueError, AttributeError)):
        PortfolioDecisionEngine.from_dict(state)


def test_duplicate_decision_ids_fail_closed() -> None:
    decision = _decision("PDEC-LEGACY-00000001")
    state = PortfolioDecisionEngine().to_dict()
    state["decisions"] = [decision.to_dict(), decision.to_dict()]
    state["sequence"] = 2

    with pytest.raises(ValueError, match="Duplicate decision_id"):
        PortfolioDecisionEngine.from_dict(state)
