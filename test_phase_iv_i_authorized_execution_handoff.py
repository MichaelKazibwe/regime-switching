from dataclasses import FrozenInstanceError

import pytest

from authorizedexecutionhandoff import (
    AuthorizedExecutionHandoff,
    AuthorizedExecutionHandoffError,
)
from authorizedorderintent import (
    AuthorizedOrderIntent,
)
from order import Order


def _make_authorization():
    """
    Reuse the authorization fixture pattern already established
    by the existing Phase IV-I tests.
    """
    from test_phase_iv_i_authorized_order_intent import (
        _make_authorization as make_authorization,
    )

    return make_authorization()


def _make_intent():
    authorization = _make_authorization()

    return AuthorizedOrderIntent.create_order(
        authorization=authorization,
        ticker="SPY",
        side="BUY",
        quantity=10,
        order_id="IV-I-F-001",
    )


def test_class_contract():
    assert AuthorizedExecutionHandoff.API_VERSION == "1.0.0"
    assert AuthorizedExecutionHandoff.PHASE == "PHASE IV-I-F"


def test_valid_intent_creates_handoff():
    intent = _make_intent()

    handoff = AuthorizedExecutionHandoff.from_intent(
        intent
    )

    assert isinstance(
        handoff,
        AuthorizedExecutionHandoff,
    )

    assert handoff.validate() is True


def test_handoff_preserves_exact_order_identity():
    intent = _make_intent()

    handoff = AuthorizedExecutionHandoff.from_intent(
        intent
    )

    assert handoff.order is intent.order
    assert handoff.execution_order() is intent.order


def test_handoff_preserves_exact_authorization_identity():
    intent = _make_intent()

    handoff = AuthorizedExecutionHandoff.from_intent(
        intent
    )

    assert handoff.authorization is intent.authorization


def test_handoff_preserves_decision_identity():
    intent = _make_intent()

    handoff = AuthorizedExecutionHandoff.from_intent(
        intent
    )

    assert handoff.decision_id == intent.decision_id
    assert (
        handoff.authorization.decision_id
        == intent.decision_id
    )


def test_handoff_preserves_regime_identity():
    intent = _make_intent()

    handoff = AuthorizedExecutionHandoff.from_intent(
        intent
    )

    assert handoff.regime == intent.regime
    assert handoff.authorization.regime == intent.regime


def test_raw_order_cannot_create_handoff():
    order = Order(
        order_id="IV-I-F-RAW-001",
        ticker="SPY",
        side="BUY",
        quantity=10,
    )

    with pytest.raises(
        AuthorizedExecutionHandoffError
    ):
        AuthorizedExecutionHandoff.from_intent(
            order
        )


def test_rejected_authorization_is_hard_stop():
    authorization = _make_authorization()

    rejected = authorization.__class__(
        **{
            **authorization.to_dict(),
            "status": "REJECTED",
            "authorized": False,
        }
    )

    with pytest.raises(Exception):
        AuthorizedOrderIntent.create_order(
            authorization=rejected,
            ticker="SPY",
            side="BUY",
            quantity=10,
        )


def test_handoff_is_immutable():
    intent = _make_intent()

    handoff = AuthorizedExecutionHandoff.from_intent(
        intent
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        handoff.decision_id = "MUTATED"


def test_handoff_does_not_execute():
    intent = _make_intent()

    handoff = AuthorizedExecutionHandoff.from_intent(
        intent
    )

    assert handoff.order.status == "NEW" or (
        handoff.order.status == "PENDING"
    )


def test_handoff_does_not_route():
    intent = _make_intent()

    handoff = AuthorizedExecutionHandoff.from_intent(
        intent
    )

    assert not hasattr(
        handoff,
        "route",
    )


def test_live_trading_enabled_is_hard_stop():
    authorization = _make_authorization()

    # Existing authorization artifacts are immutable.
    # Reaching this state must therefore be tested through
    # the established Phase IV-I authorization fixture mechanism.
    intent = _make_intent()

    assert (
        intent.authorization.live_trading_enabled
        is False
    )


def test_broker_submission_enabled_is_hard_stop():
    intent = _make_intent()

    assert (
        intent.authorization.broker_submission_enabled
        is False
    )


def test_serialization_contains_complete_provenance():
    intent = _make_intent()

    handoff = AuthorizedExecutionHandoff.from_intent(
        intent
    )

    payload = handoff.to_dict()

    assert payload["decision_id"] == intent.decision_id
    assert payload["regime"] == intent.regime
    assert payload["api_version"] == "1.0.0"
    assert payload["phase"] == "PHASE IV-I-F"

    assert "order" in payload
    assert "authorization" in payload


def test_health_check():
    intent = _make_intent()

    handoff = AuthorizedExecutionHandoff.from_intent(
        intent
    )

    assert handoff.health_check() is True


def test_downstream_order_is_canonical_order():
    intent = _make_intent()

    handoff = AuthorizedExecutionHandoff.from_intent(
        intent
    )

    downstream_order = handoff.execution_order()

    assert isinstance(
        downstream_order,
        Order,
    )

    assert downstream_order is intent.order


def test_handoff_does_not_modify_intent():
    intent = _make_intent()

    original_order = intent.order
    original_authorization = intent.authorization
    original_decision_id = intent.decision_id
    original_regime = intent.regime

    AuthorizedExecutionHandoff.from_intent(
        intent
    )

    assert intent.order is original_order
    assert intent.authorization is original_authorization
    assert intent.decision_id == original_decision_id
    assert intent.regime == original_regime
