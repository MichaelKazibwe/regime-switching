from dataclasses import FrozenInstanceError

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
    decision_id="DECISION-I-C-001",
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
        weights={"SPY": 1.0},
        portfolio_volatility=0.10,
        portfolio_variance=0.01,
        gross_exposure=1.0,
        net_exposure=1.0,
        risk_contributions={"SPY": 0.01},
        risk_contribution_pct={"SPY": 1.0},
        risk_validation_passed=risk_validation_passed,
        live_trading_enabled=live_trading_enabled,
        broker_submission_enabled=broker_submission_enabled,
        warnings=(),
        errors=(),
        diagnostics={},
        api_version="1.0.0",
        phase="PHASE IV-B.5",
    )


def _make_order(
    *,
    order_id="ORD-I-C-000001",
    ticker="SPY",
    side="BUY",
    quantity=100.0,
):
    return Order(
        order_id=order_id,
        ticker=ticker,
        side=side,
        quantity=quantity,
    )


def _make_intent(
    *,
    order=None,
    authorization=None,
    decision_id="DECISION-I-C-001",
    regime="NORMAL",
):
    if authorization is None:
        authorization = _make_authorization(
            decision_id=decision_id,
            regime=regime,
        )

    if order is None:
        order = _make_order()

    return AuthorizedOrderIntent(
        order=order,
        authorization=authorization,
        decision_id=decision_id,
        regime=regime,
    )


def test_class_contract():
    assert AuthorizedOrderIntent.API_VERSION == "1.0.0"
    assert AuthorizedOrderIntent.PHASE == "PHASE IV-I-C"


def test_valid_intent_passes_validation():
    intent = _make_intent()

    assert intent.validate() is True


def test_intent_is_immutable():
    intent = _make_intent()

    with pytest.raises(FrozenInstanceError):
        intent.decision_id = "FORGED"


def test_rejected_authorization_cannot_validate():
    authorization = _make_authorization(
        status=ExecutionAuthorizationStatus.REJECTED,
        authorized=False,
    )

    intent = _make_intent(
        authorization=authorization,
    )

    with pytest.raises(AuthorizedOrderIntentError):
        intent.validate()


def test_failed_authorization_cannot_validate():
    authorization = _make_authorization(
        status=ExecutionAuthorizationStatus.FAILED,
        authorized=False,
    )

    intent = _make_intent(
        authorization=authorization,
    )

    with pytest.raises(AuthorizedOrderIntentError):
        intent.validate()


def test_authorized_false_cannot_validate():
    authorization = _make_authorization(
        authorized=False,
    )

    intent = _make_intent(
        authorization=authorization,
    )

    with pytest.raises(AuthorizedOrderIntentError):
        intent.validate()


def test_risk_validation_failure_cannot_validate():
    authorization = _make_authorization(
        risk_validation_passed=False,
    )

    intent = _make_intent(
        authorization=authorization,
    )

    with pytest.raises(AuthorizedOrderIntentError):
        intent.validate()


def test_live_trading_enabled_cannot_validate():
    authorization = _make_authorization(
        live_trading_enabled=True,
    )

    intent = _make_intent(
        authorization=authorization,
    )

    with pytest.raises(AuthorizedOrderIntentError):
        intent.validate()


def test_broker_submission_enabled_cannot_validate():
    authorization = _make_authorization(
        broker_submission_enabled=True,
    )

    intent = _make_intent(
        authorization=authorization,
    )

    with pytest.raises(AuthorizedOrderIntentError):
        intent.validate()


def test_decision_id_mismatch_cannot_validate():
    authorization = _make_authorization(
        decision_id="AUTH-DECISION-001",
    )

    intent = _make_intent(
        authorization=authorization,
        decision_id="DIFFERENT-DECISION",
    )

    with pytest.raises(AuthorizedOrderIntentError):
        intent.validate()


def test_regime_mismatch_cannot_validate():
    authorization = _make_authorization(
        regime="NORMAL",
    )

    intent = _make_intent(
        authorization=authorization,
        regime="STRESS",
    )

    with pytest.raises(AuthorizedOrderIntentError):
        intent.validate()


def test_order_is_preserved():
    order = _make_order(
        order_id="ORD-I-C-PRESERVED",
    )

    intent = _make_intent(
        order=order,
    )

    assert intent.order is order
    assert intent.order.order_id == "ORD-I-C-PRESERVED"


def test_authorization_is_preserved():
    authorization = _make_authorization()

    intent = _make_intent(
        authorization=authorization,
    )

    assert intent.authorization is authorization
    assert (
        intent.authorization.decision_id
        == "DECISION-I-C-001"
    )


def test_authorization_order_identity_is_not_rewritten():
    order = _make_order(
        order_id="ORD-I-C-IDENTITY",
    )

    authorization = _make_authorization(
        decision_id="DECISION-I-C-IDENTITY",
    )

    intent = _make_intent(
        order=order,
        authorization=authorization,
        decision_id="DECISION-I-C-IDENTITY",
    )

    assert intent.order.order_id == "ORD-I-C-IDENTITY"
    assert (
        intent.authorization.decision_id
        == "DECISION-I-C-IDENTITY"
    )
    assert (
        intent.decision_id
        == intent.authorization.decision_id
    )


def test_serialization_contains_provenance():
    intent = _make_intent()

    payload = intent.to_dict()

    assert payload["decision_id"] == "DECISION-I-C-001"
    assert payload["regime"] == "NORMAL"
    assert payload["api_version"] == "1.0.0"
    assert payload["phase"] == "PHASE IV-I-C"
    assert "order" in payload
    assert "authorization" in payload


def test_factory_has_no_execution_side_effects():
    intent = _make_intent()

    assert isinstance(intent.order, Order)
    assert intent.order.status == "PENDING"


def test_only_authorized_artifacts_are_valid():
    authorization = _make_authorization()

    intent = _make_intent(
        authorization=authorization,
    )

    assert intent.validate() is True
