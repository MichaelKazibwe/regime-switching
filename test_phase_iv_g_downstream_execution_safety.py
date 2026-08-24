"""
Phase IV-G — Downstream Execution Safety Boundary
==================================================

Regression and hardening tests for the downstream execution path.

These tests are deliberately aligned with the existing Phase IV-F
authorization model:

    - ExecutionAuthorizationStatus uses immutable string constants.
    - ExecutionAuthorization is a frozen dataclass.
    - ProductionExecutionGate.require_authorization() is the final
      authorization hard-stop.
    - LiveBroker is independently fail-closed and requires:
          healthy broker
          connected broker
          authenticated broker
          healthy transport
          explicitly enabled live trading

Phase IV-G therefore verifies the existing contracts rather than
inventing a second authorization model.
"""

from __future__ import annotations

import pytest


# ======================================================================
# HELPERS
# ======================================================================


def _rejected_authorization():
    """Build the complete rejected authorization artifact required by
    the current ProductionExecutionGate contract.
    """
    from productionexecutiongate import (
        ExecutionAuthorization,
        ExecutionAuthorizationStatus,
    )

    return ExecutionAuthorization(
        status=ExecutionAuthorizationStatus.REJECTED,
        authorized=False,
        decision_id="PHASE-IV-G-REJECTED",
        regime="neutral",
        weights={"SPY": 1.0},
        portfolio_volatility=0.10,
        portfolio_variance=0.01,
        gross_exposure=1.0,
        net_exposure=1.0,
        risk_contributions={"SPY": 0.01},
        risk_contribution_pct={"SPY": 1.0},
        risk_validation_passed=False,
        live_trading_enabled=False,
        broker_submission_enabled=False,
        warnings=("Phase IV-G rejected authorization.",),
        errors=("Risk validation failed.",),
        diagnostics={
            "phase_iv_g_test": True,
            "authorization_boundary": "REJECTED",
        },
        api_version="1.0.0",
        phase="IV-B.5",
    )


# ======================================================================
# PHASE IV-F AUTHORIZATION BOUNDARY
# ======================================================================


def test_phase_iv_f_authorization_boundary_remains_authoritative() -> None:
    from productionexecutiongate import (
        ExecutionAuthorizationStatus,
        ProductionExecutionGate,
    )

    gate = ProductionExecutionGate()

    assert hasattr(gate, "require_authorization")
    assert ExecutionAuthorizationStatus.AUTHORIZED == "AUTHORIZED"
    assert ExecutionAuthorizationStatus.REJECTED == "REJECTED"
    assert ExecutionAuthorizationStatus.FAILED == "FAILED"


def test_rejected_authorization_cannot_cross_execution_boundary() -> None:
    from productionexecutiongate import ProductionExecutionGate

    gate = ProductionExecutionGate()
    rejected = _rejected_authorization()

    with pytest.raises(Exception):
        gate.require_authorization(rejected)


def test_missing_authorization_is_fail_closed() -> None:
    from productionexecutiongate import ProductionExecutionGate

    gate = ProductionExecutionGate()

    with pytest.raises(Exception):
        gate.require_authorization(None)


def test_execution_authorization_is_immutable() -> None:
    authorization = _rejected_authorization()

    with pytest.raises((AttributeError, TypeError)):
        authorization.authorized = True


def test_rejected_authorization_cannot_become_authorized() -> None:
    from productionexecutiongate import ProductionExecutionGate

    gate = ProductionExecutionGate()
    rejected = _rejected_authorization()

    assert rejected.status == "REJECTED"
    assert rejected.authorized is False
    assert rejected.risk_validation_passed is False

    with pytest.raises(Exception):
        gate.require_authorization(rejected)


def test_authorization_artifact_contains_required_execution_metadata() -> None:
    authorization = _rejected_authorization()
    payload = authorization.to_dict()

    required_keys = {
        "status",
        "authorized",
        "decision_id",
        "regime",
        "weights",
        "portfolio_volatility",
        "portfolio_variance",
        "gross_exposure",
        "net_exposure",
        "risk_contributions",
        "risk_contribution_pct",
        "risk_validation_passed",
        "live_trading_enabled",
        "broker_submission_enabled",
        "warnings",
        "errors",
        "diagnostics",
        "api_version",
        "phase",
    }

    assert required_keys.issubset(payload)
    assert payload["status"] == "REJECTED"
    assert payload["authorized"] is False
    assert payload["risk_validation_passed"] is False


# ======================================================================
# LIVE BROKER FAIL-CLOSED BOUNDARY
# ======================================================================


def test_live_broker_starts_fail_closed() -> None:
    from livebroker import LiveBroker

    broker = LiveBroker()

    assert broker.health_check()
    assert not broker._connected
    assert not broker._authenticated
    assert not broker._live_trading_enabled


def test_live_broker_cannot_submit_before_connection() -> None:
    from livebroker import LiveBroker
    from order import Order

    broker = LiveBroker()

    order = Order(
        order_id="PHASE-IV-G-LIVE-000001",
        ticker="SPY",
        side="BUY",
        quantity=1.0,
    )

    with pytest.raises(RuntimeError, match="LIVE_BROKER_DISCONNECTED"):
        broker.submit_order(order)


def test_live_broker_cannot_enable_trading_before_connection() -> None:
    from livebroker import LiveBroker

    broker = LiveBroker()

    with pytest.raises(
        RuntimeError,
        match="broker disconnected",
    ):
        broker.enable_live_trading()

    assert not broker._live_trading_enabled


def test_live_broker_cannot_authenticate_without_transport() -> None:
    from livebroker import LiveBroker

    broker = LiveBroker()

    with pytest.raises(
        RuntimeError,
        match="No broker transport configured",
    ):
        broker.authenticate()

    assert not broker._authenticated


def test_live_broker_cannot_authenticate_before_connection() -> None:
    from livebroker import (
        LiveBroker,
        _TestLiveTransport,
    )

    broker = LiveBroker(
        broker_name="LIVE",
        currency="USD",
        transport=_TestLiveTransport(),
    )

    with pytest.raises(
        RuntimeError,
        match="connected before authentication",
    ):
        broker.authenticate()

    assert not broker._authenticated


def test_live_broker_remains_disabled_after_construction() -> None:
    from livebroker import LiveBroker

    broker = LiveBroker()

    assert broker._live_trading_enabled is False


# ======================================================================
# MODULE CONTRACT / IMPORT REGRESSION
# ======================================================================


def test_phase_iv_g_modules_are_importable() -> None:
    import brokerexecutionengine
    import brokerrouter
    import executionengine
    import livebroker
    import oms
    import order
    import orderbook
    import paperbroker
    import posttradeexecutionmonitor
    import pretraderiskgate
    import productiondecisionexecution
    import productionexecutiongate
    import productionintegration
    import productionpipelineintegration
    import reconciliationengine
    import tradegenerator

    modules = (
        brokerexecutionengine,
        brokerrouter,
        executionengine,
        livebroker,
        oms,
        order,
        orderbook,
        paperbroker,
        posttradeexecutionmonitor,
        pretraderiskgate,
        productiondecisionexecution,
        productionexecutiongate,
        productionintegration,
        productionpipelineintegration,
        reconciliationengine,
        tradegenerator,
    )

    for module in modules:
        assert module is not None


# ======================================================================
# MAIN
# ======================================================================


if __name__ == "__main__":
    raise SystemExit(
        pytest.main(
            [
                "-q",
                __file__,
            ]
        )
    )