import pytest

from authorizedexecutionhandoff import (
    AuthorizedExecutionHandoff,
    AuthorizedExecutionHandoffError,
)
from authorizedorderintent import AuthorizedOrderIntent
from brokerexecutionengine import (
    BrokerExecutionEngine,
)
from order import Order
from portfolioaccount import PortfolioAccount
from productionexecutiongate import (
    ExecutionAuthorization,
    ExecutionAuthorizationStatus,
)
from paperbroker import PaperBroker


def _make_authorization():
    return ExecutionAuthorization(
        status=ExecutionAuthorizationStatus.AUTHORIZED,
        authorized=True,
        decision_id="DECISION-IV-I-F-001",
        regime="NORMAL",
        weights={"SPY": 1.0},
        portfolio_volatility=0.10,
        portfolio_variance=0.01,
        gross_exposure=1.0,
        net_exposure=1.0,
        risk_contributions={"SPY": 0.01},
        risk_contribution_pct={"SPY": 1.0},
        risk_validation_passed=True,
        live_trading_enabled=False,
        broker_submission_enabled=False,
        warnings=(),
        errors=(),
        diagnostics={},
        api_version="1.0.0",
        phase="PHASE IV-B.5",
    )


def _make_order():
    return Order(
        order_id="ORD-IV-I-F-000001",
        ticker="SPY",
        side="BUY",
        quantity=10.0,
    )


def _make_handoff():
    intent = AuthorizedOrderIntent.from_authorization(
        authorization=_make_authorization(),
        order=_make_order(),
    )

    return AuthorizedExecutionHandoff.from_intent(
        intent
    )


def test_authorized_execution_boundary_requires_handoff():
    engine = BrokerExecutionEngine()

    with pytest.raises(
        AuthorizedExecutionHandoffError
    ):
        engine.execute_authorized_receipt(
            handoff=_make_order(),
            receipt=None,
            account=None,
        )


def test_valid_handoff_passes_validation():
    handoff = _make_handoff()

    assert handoff.validate() is True


def test_handoff_preserves_exact_order_identity():
    handoff = _make_handoff()

    assert (
        handoff.execution_order()
        is handoff.order
    )


def test_public_api_exposes_authorized_execution_boundary():
    engine = BrokerExecutionEngine()

    assert (
        "execute_authorized_receipt"
        in engine.PUBLIC_METHODS
    )


def test_handoff_does_not_enable_live_trading():
    handoff = _make_handoff()

    assert (
        handoff.authorization.live_trading_enabled
        is False
    )


def test_handoff_does_not_enable_broker_submission():
    handoff = _make_handoff()

    assert (
        handoff.authorization.broker_submission_enabled
        is False
    )


def test_authorized_execution_preserves_decision_id():
    engine = BrokerExecutionEngine()

    handoff = _make_handoff()

    order = handoff.execution_order()

    broker = PaperBroker()

    account = PortfolioAccount(
        initial_cash=100_000.0,
    )

    broker.submit_order(order)

    receipt = broker.fill_order(
        order.order_id,
        execution_price=100.0,
    )

    result = engine.execute_authorized_receipt(
        handoff=handoff,
        receipt=receipt,
        account=account,
    )

    assert result.approved is True

    assert (
        result.authorization_provenance["decision_id"]
        == handoff.decision_id
    )


def test_authorized_execution_preserves_regime():
    engine = BrokerExecutionEngine()

    handoff = _make_handoff()

    order = handoff.execution_order()

    broker = PaperBroker()

    account = PortfolioAccount(
        initial_cash=100_000.0,
    )

    broker.submit_order(order)

    receipt = broker.fill_order(
        order.order_id,
        execution_price=100.0,
    )

    result = engine.execute_authorized_receipt(
        handoff=handoff,
        receipt=receipt,
        account=account,
    )

    assert (
        result.authorization_provenance["regime"]
        == handoff.regime
    )


def test_authorized_execution_preserves_exact_order_identity():
    engine = BrokerExecutionEngine()

    handoff = _make_handoff()

    order = handoff.execution_order()

    broker = PaperBroker()

    account = PortfolioAccount(
        initial_cash=100_000.0,
    )

    broker.submit_order(order)

    receipt = broker.fill_order(
        order.order_id,
        execution_price=100.0,
    )

    result = engine.execute_authorized_receipt(
        handoff=handoff,
        receipt=receipt,
        account=account,
    )

    provenance = result.authorization_provenance

    assert provenance["order"]["order_id"] == order.order_id
    assert provenance["order"]["ticker"] == order.ticker
    assert provenance["order"]["side"] == order.side
    assert provenance["order"]["quantity"] == order.quantity


def test_authorized_execution_preserves_authorization_artifact():
    engine = BrokerExecutionEngine()

    handoff = _make_handoff()

    order = handoff.execution_order()

    broker = PaperBroker()

    account = PortfolioAccount(
        initial_cash=100_000.0,
    )

    broker.submit_order(order)

    receipt = broker.fill_order(
        order.order_id,
        execution_price=100.0,
    )

    result = engine.execute_authorized_receipt(
        handoff=handoff,
        receipt=receipt,
        account=account,
    )

    provenance = result.authorization_provenance

    assert (
        provenance["authorization"]
        == handoff.authorization.to_dict()
    )


def test_authorized_execution_preserves_handoff_phase():
    engine = BrokerExecutionEngine()

    handoff = _make_handoff()

    order = handoff.execution_order()

    broker = PaperBroker()

    account = PortfolioAccount(
        initial_cash=100_000.0,
    )

    broker.submit_order(order)

    receipt = broker.fill_order(
        order.order_id,
        execution_price=100.0,
    )

    result = engine.execute_authorized_receipt(
        handoff=handoff,
        receipt=receipt,
        account=account,
    )

    assert (
        result.authorization_provenance["phase"]
        == "PHASE IV-I-F"
    )
