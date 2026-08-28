"""
======================================================================
PHASE IV-I-D
AUTHORIZED ORDER INTENT CREATION BRIDGE TESTS
======================================================================
"""

import pytest

from authorizedorderintent import (
    AuthorizedOrderIntent,
    AuthorizedOrderIntentError,
)

from order import Order

from productionexecutiongate import (
    ExecutionAuthorization,
    ExecutionAuthorizationStatus,
)


def _make_authorization(
    *,
    status=ExecutionAuthorizationStatus.AUTHORIZED,
    authorized=True,
    decision_id="DECISION-IV-I-D-001",
    regime="NORMAL",
    risk_validation_passed=True,
    live_trading_enabled=False,
    broker_submission_enabled=False,
):
    return ExecutionAuthorization(
        status=status,
        authorized=authorized,
        decision_id=decision_id,
        regime=regime,
        weights={
            "SPY": 0.50,
            "QQQ": 0.30,
            "TLT": 0.20,
        },
        portfolio_volatility=0.10,
        portfolio_variance=0.01,
        gross_exposure=1.0,
        net_exposure=1.0,
        risk_contributions={
            "SPY": 0.50,
            "QQQ": 0.30,
            "TLT": 0.20,
        },
        risk_contribution_pct={
            "SPY": 50.0,
            "QQQ": 30.0,
            "TLT": 20.0,
        },
        risk_validation_passed=risk_validation_passed,
        live_trading_enabled=live_trading_enabled,
        broker_submission_enabled=broker_submission_enabled,
        warnings=(),
        errors=(),
        diagnostics={},
        api_version="1.0.0",
        phase="PHASE IV-B.5",
    )


def test_create_order_returns_authorized_order_intent():
    authorization = _make_authorization()

    intent = AuthorizedOrderIntent.create_order(
        authorization=authorization,
        ticker="SPY",
        side="BUY",
        quantity=100.0,
    )

    assert isinstance(
        intent,
        AuthorizedOrderIntent,
    )

    assert isinstance(
        intent.order,
        Order,
    )

    assert intent.validate() is True


def test_create_order_preserves_authorization_provenance():
    authorization = _make_authorization(
        decision_id="DECISION-PROVENANCE-001",
        regime="DEFENSIVE",
    )

    intent = AuthorizedOrderIntent.create_order(
        authorization=authorization,
        ticker="QQQ",
        side="SELL",
        quantity=25.0,
        order_id="IV-ID-000001",
    )

    assert intent.authorization is authorization
    assert intent.decision_id == "DECISION-PROVENANCE-001"
    assert intent.regime == "DEFENSIVE"
    assert intent.order_id == "IV-ID-000001"


def test_create_order_preserves_explicit_order_identity():
    authorization = _make_authorization()

    intent = AuthorizedOrderIntent.create_order(
        authorization=authorization,
        ticker="SPY",
        side="BUY",
        quantity=10.0,
        order_id="AUTHORIZED-ORDER-0001",
    )

    assert intent.order.order_id == "AUTHORIZED-ORDER-0001"


def test_rejected_authorization_is_hard_stop():
    authorization = _make_authorization(
        status=ExecutionAuthorizationStatus.REJECTED,
        authorized=False,
    )

    with pytest.raises(AuthorizedOrderIntentError):
        AuthorizedOrderIntent.create_order(
            authorization=authorization,
            ticker="SPY",
            side="BUY",
            quantity=10.0,
        )


def test_failed_authorization_is_hard_stop():
    authorization = _make_authorization(
        status=ExecutionAuthorizationStatus.FAILED,
        authorized=False,
    )

    with pytest.raises(AuthorizedOrderIntentError):
        AuthorizedOrderIntent.create_order(
            authorization=authorization,
            ticker="SPY",
            side="BUY",
            quantity=10.0,
        )


def test_authorized_false_is_hard_stop():
    authorization = _make_authorization(
        authorized=False,
    )

    with pytest.raises(AuthorizedOrderIntentError):
        AuthorizedOrderIntent.create_order(
            authorization=authorization,
            ticker="SPY",
            side="BUY",
            quantity=10.0,
        )


def test_failed_risk_validation_is_hard_stop():
    authorization = _make_authorization(
        risk_validation_passed=False,
    )

    with pytest.raises(AuthorizedOrderIntentError):
        AuthorizedOrderIntent.create_order(
            authorization=authorization,
            ticker="SPY",
            side="BUY",
            quantity=10.0,
        )


def test_live_trading_enabled_is_hard_stop():
    authorization = _make_authorization(
        live_trading_enabled=True,
    )

    with pytest.raises(AuthorizedOrderIntentError):
        AuthorizedOrderIntent.create_order(
            authorization=authorization,
            ticker="SPY",
            side="BUY",
            quantity=10.0,
        )


def test_broker_submission_enabled_is_hard_stop():
    authorization = _make_authorization(
        broker_submission_enabled=True,
    )

    with pytest.raises(AuthorizedOrderIntentError):
        AuthorizedOrderIntent.create_order(
            authorization=authorization,
            ticker="SPY",
            side="BUY",
            quantity=10.0,
        )


def test_unauthorized_ticker_is_hard_stop():
    authorization = _make_authorization()

    with pytest.raises(AuthorizedOrderIntentError):
        AuthorizedOrderIntent.create_order(
            authorization=authorization,
            ticker="GLD",
            side="BUY",
            quantity=10.0,
        )


def test_invalid_side_is_hard_stop():
    authorization = _make_authorization()

    with pytest.raises(AuthorizedOrderIntentError):
        AuthorizedOrderIntent.create_order(
            authorization=authorization,
            ticker="SPY",
            side="HOLD",
            quantity=10.0,
        )


def test_invalid_quantity_is_hard_stop():
    authorization = _make_authorization()

    with pytest.raises(AuthorizedOrderIntentError):
        AuthorizedOrderIntent.create_order(
            authorization=authorization,
            ticker="SPY",
            side="BUY",
            quantity=0.0,
        )


def test_invalid_order_type_is_hard_stop():
    authorization = _make_authorization()

    with pytest.raises(AuthorizedOrderIntentError):
        AuthorizedOrderIntent.create_order(
            authorization=authorization,
            ticker="SPY",
            side="BUY",
            quantity=10.0,
            order_type="INVALID",
        )


def test_invalid_time_in_force_is_hard_stop():
    authorization = _make_authorization()

    with pytest.raises(AuthorizedOrderIntentError):
        AuthorizedOrderIntent.create_order(
            authorization=authorization,
            ticker="SPY",
            side="BUY",
            quantity=10.0,
            time_in_force="INVALID",
        )


def test_batch_creation():
    authorization = _make_authorization()

    intents = AuthorizedOrderIntent.create_orders(
        authorization=authorization,
        intents=[
            {
                "ticker": "SPY",
                "side": "BUY",
                "quantity": 10.0,
                "order_id": "BATCH-001",
            },
            {
                "ticker": "QQQ",
                "side": "SELL",
                "quantity": 20.0,
                "order_id": "BATCH-002",
            },
            {
                "ticker": "TLT",
                "side": "BUY",
                "quantity": 30.0,
                "order_id": "BATCH-003",
            },
        ],
    )

    assert len(intents) == 3

    assert all(
        isinstance(
            intent,
            AuthorizedOrderIntent,
        )
        for intent in intents
    )

    assert [
        intent.order_id
        for intent in intents
    ] == [
        "BATCH-001",
        "BATCH-002",
        "BATCH-003",
    ]


def test_batch_creation_rejects_invalid_authorization_before_orders():
    authorization = _make_authorization(
        status=ExecutionAuthorizationStatus.REJECTED,
        authorized=False,
    )

    with pytest.raises(AuthorizedOrderIntentError):
        AuthorizedOrderIntent.create_orders(
            authorization=authorization,
            intents=[
                {
                    "ticker": "SPY",
                    "side": "BUY",
                    "quantity": 10.0,
                }
            ],
        )


def test_create_order_has_no_execution_side_effect():
    authorization = _make_authorization()

    intent = AuthorizedOrderIntent.create_order(
        authorization=authorization,
        ticker="SPY",
        side="BUY",
        quantity=10.0,
    )

    assert intent.order.status == "PENDING"
    assert intent.order.filled_quantity == 0.0
    assert intent.order.average_fill_price == 0.0


def test_create_order_does_not_route_or_submit():
    authorization = _make_authorization()

    intent = AuthorizedOrderIntent.create_order(
        authorization=authorization,
        ticker="SPY",
        side="BUY",
        quantity=10.0,
    )

    # Creation alone must never advance the canonical order
    # beyond its initial state.
    assert intent.order.status == "PENDING"
    assert intent.order.is_open() is True


def test_intent_remains_immutable():
    authorization = _make_authorization()

    intent = AuthorizedOrderIntent.create_order(
        authorization=authorization,
        ticker="SPY",
        side="BUY",
        quantity=10.0,
    )

    with pytest.raises(
        AttributeError
    ):
        intent.decision_id = "MUTATED"


def test_serialization_retains_bridge_provenance():
    authorization = _make_authorization(
        decision_id="SERIALIZED-D-001",
        regime="NORMAL",
    )

    intent = AuthorizedOrderIntent.create_order(
        authorization=authorization,
        ticker="SPY",
        side="BUY",
        quantity=15.0,
        order_id="SERIALIZED-ORDER-001",
    )

    payload = intent.to_dict()

    assert payload["decision_id"] == "SERIALIZED-D-001"
    assert payload["regime"] == "NORMAL"
    assert payload["order"]["order_id"] == "SERIALIZED-ORDER-001"
    assert payload["authorization"]["decision_id"] == (
        "SERIALIZED-D-001"
    )
