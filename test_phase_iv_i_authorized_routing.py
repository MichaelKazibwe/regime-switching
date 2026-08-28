import pytest

from authorizedexecutionhandoff import AuthorizedExecutionHandoff
from authorizedroutinghandoff import (
    AuthorizedRoutingHandoff,
    AuthorizedRoutingHandoffError,
)
from authorizedorderintent import AuthorizedOrderIntent
from brokerrouter import BrokerRouter
from order import Order
from paperbroker import PaperBroker
from productionexecutiongate import (
    ExecutionAuthorization,
    ExecutionAuthorizationStatus,
)


def _make_authorization():
    return ExecutionAuthorization(
        status=ExecutionAuthorizationStatus.AUTHORIZED,
        authorized=True,
        decision_id="DECISION-IV-I-G-001",
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
        order_id="ORD-IV-I-G-000001",
        ticker="SPY",
        side="BUY",
        quantity=10.0,
    )


def _make_routing_handoff():
    intent = AuthorizedOrderIntent.from_authorization(
        authorization=_make_authorization(),
        order=_make_order(),
    )

    execution_handoff = AuthorizedExecutionHandoff.from_intent(
        intent
    )

    return AuthorizedRoutingHandoff.from_execution_handoff(
        execution_handoff
    )


def _make_router():
    router = BrokerRouter()

    router.register_broker(
        PaperBroker()
    )

    return router


def test_class_contract():
    assert AuthorizedRoutingHandoff.API_VERSION == "1.0.0"
    assert AuthorizedRoutingHandoff.PHASE == "PHASE IV-I-G"


def test_valid_routing_handoff_passes_validation():
    handoff = _make_routing_handoff()

    assert handoff.validate() is True


def test_routing_handoff_preserves_exact_order_identity():
    handoff = _make_routing_handoff()

    assert handoff.routing_order() is (
        handoff.execution_handoff.order
    )


def test_raw_order_cannot_cross_authorized_routing_boundary():
    router = _make_router()

    with pytest.raises(
        AuthorizedRoutingHandoffError
    ):
        router.route_authorized_order(
            _make_order()
        )


def test_authorized_routing_is_exposed():
    router = _make_router()

    assert (
        "route_authorized_order"
        in router.PUBLIC_METHODS
    )


def test_authorized_routing_succeeds():
    router = _make_router()
    handoff = _make_routing_handoff()

    result = router.route_authorized_order(
        handoff
    )

    assert result.approved is True
    assert result.order_id == handoff.order_id
    assert result.broker == "PAPER"


def test_authorized_routing_preserves_decision_id():
    router = _make_router()
    handoff = _make_routing_handoff()

    result = router.route_authorized_order(
        handoff
    )

    assert (
        result.authorization_provenance[
            "decision_id"
        ]
        == handoff.decision_id
    )


def test_authorized_routing_preserves_regime():
    router = _make_router()
    handoff = _make_routing_handoff()

    result = router.route_authorized_order(
        handoff
    )

    assert (
        result.authorization_provenance[
            "regime"
        ]
        == handoff.regime
    )


def test_authorized_routing_preserves_exact_order_identity():
    router = _make_router()
    handoff = _make_routing_handoff()

    result = router.route_authorized_order(
        handoff
    )

    assert (
        result.authorization_provenance[
            "order"
        ]["order_id"]
        == handoff.order_id
    )


def test_authorized_routing_preserves_authorization_artifact():
    router = _make_router()
    handoff = _make_routing_handoff()

    result = router.route_authorized_order(
        handoff
    )

    authorization = (
        result.authorization_provenance[
            "authorization"
        ]
    )

    assert (
        authorization["decision_id"]
        == handoff.decision_id
    )

    assert (
        authorization["regime"]
        == handoff.regime
    )


def test_authorized_routing_does_not_enable_live_trading():
    handoff = _make_routing_handoff()

    assert (
        handoff.authorization.live_trading_enabled
        is False
    )


def test_authorized_routing_does_not_enable_broker_submission():
    handoff = _make_routing_handoff()

    assert (
        handoff.authorization.broker_submission_enabled
        is False
    )


def test_routing_history_contains_authorization_provenance():
    router = _make_router()
    handoff = _make_routing_handoff()

    router.route_authorized_order(
        handoff
    )

    assert len(
        router.routing_history
    ) == 1

    history = router.routing_history[0]

    assert (
        history[
            "authorization_provenance"
        ]["decision_id"]
        == handoff.decision_id
    )


def test_routing_handoff_is_immutable():
    handoff = _make_routing_handoff()

    with pytest.raises(
        Exception
    ):
        handoff.execution_handoff = None
