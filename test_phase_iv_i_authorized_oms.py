from __future__ import annotations

import pytest

from authorizedorderintent import (
    AuthorizedOrderIntent,
)
from oms import (
    OMS,
    OMSAuthorizationError,
)
from order import Order
from productionexecutiongate import (
    ExecutionAuthorization,
    ExecutionAuthorizationStatus,
)


def _make_authorization() -> ExecutionAuthorization:
    return ExecutionAuthorization(
        status=ExecutionAuthorizationStatus.AUTHORIZED,
        authorized=True,
        decision_id="DECISION-I-E-001",
        regime="NORMAL",
        weights={
            "SPY": 1.0,
        },
        portfolio_volatility=0.10,
        portfolio_variance=0.01,
        gross_exposure=1.0,
        net_exposure=1.0,
        risk_contributions={
            "SPY": 0.01,
        },
        risk_contribution_pct={
            "SPY": 1.0,
        },
        risk_validation_passed=True,
        live_trading_enabled=False,
        broker_submission_enabled=False,
        warnings=(),
        errors=(),
        diagnostics={},
        api_version="1.0.0",
        phase="PHASE IV-B.5",
    )


def _make_intent() -> AuthorizedOrderIntent:
    authorization = _make_authorization()

    order = Order(
        order_id="IV-I-E-001",
        ticker="SPY",
        side="BUY",
        quantity=10.0,
    )

    return AuthorizedOrderIntent(
        order=order,
        authorization=authorization,
        decision_id="DECISION-I-E-001",
        regime="NORMAL",
    )


def test_authorized_submission_accepts_valid_intent() -> None:
    oms = OMS()

    intent = _make_intent()

    submitted = oms.submit_authorized_order(
        intent
    )

    assert submitted is intent.order
    assert submitted.order_id == "IV-I-E-001"
    assert submitted.status == "PENDING"
    assert oms.has_order("IV-I-E-001")


def test_authorized_submission_preserves_order_identity() -> None:
    oms = OMS()

    intent = _make_intent()

    submitted = oms.submit_authorized_order(
        intent
    )

    assert submitted is intent.order


def test_raw_order_is_rejected_by_authorized_boundary() -> None:
    oms = OMS()

    order = Order(
        order_id="IV-I-E-RAW",
        ticker="SPY",
        side="BUY",
        quantity=10.0,
    )

    with pytest.raises(
        OMSAuthorizationError
    ):
        oms.submit_authorized_order(
            order
        )


def test_rejected_authorization_is_hard_stop() -> None:
    authorization = _make_authorization()

    rejected = ExecutionAuthorization(
        status=ExecutionAuthorizationStatus.REJECTED,
        authorized=False,
        decision_id=authorization.decision_id,
        regime=authorization.regime,
        weights=authorization.weights,
        portfolio_volatility=authorization.portfolio_volatility,
        portfolio_variance=authorization.portfolio_variance,
        gross_exposure=authorization.gross_exposure,
        net_exposure=authorization.net_exposure,
        risk_contributions=authorization.risk_contributions,
        risk_contribution_pct=authorization.risk_contribution_pct,
        risk_validation_passed=False,
        live_trading_enabled=False,
        broker_submission_enabled=False,
        warnings=(),
        errors=("REJECTED",),
        diagnostics={},
        api_version="1.0.0",
        phase="PHASE IV-B.5",
    )

    intent = AuthorizedOrderIntent(
        order=Order(
            order_id="IV-I-E-REJECTED",
            ticker="SPY",
            side="BUY",
            quantity=10.0,
        ),
        authorization=rejected,
        decision_id=authorization.decision_id,
        regime=authorization.regime,
    )

    oms = OMS()

    with pytest.raises(
        OMSAuthorizationError
    ):
        oms.submit_authorized_order(
            intent
        )

    assert not oms.has_order(
        "IV-I-E-REJECTED"
    )


def test_failed_risk_validation_is_hard_stop() -> None:
    authorization = _make_authorization()

    failed = ExecutionAuthorization(
        status=ExecutionAuthorizationStatus.AUTHORIZED,
        authorized=True,
        decision_id=authorization.decision_id,
        regime=authorization.regime,
        weights=authorization.weights,
        portfolio_volatility=authorization.portfolio_volatility,
        portfolio_variance=authorization.portfolio_variance,
        gross_exposure=authorization.gross_exposure,
        net_exposure=authorization.net_exposure,
        risk_contributions=authorization.risk_contributions,
        risk_contribution_pct=authorization.risk_contribution_pct,
        risk_validation_passed=False,
        live_trading_enabled=False,
        broker_submission_enabled=False,
        warnings=(),
        errors=(),
        diagnostics={},
        api_version="1.0.0",
        phase="PHASE IV-B.5",
    )

    intent = AuthorizedOrderIntent(
        order=Order(
            order_id="IV-I-E-RISK",
            ticker="SPY",
            side="BUY",
            quantity=10.0,
        ),
        authorization=failed,
        decision_id=authorization.decision_id,
        regime=authorization.regime,
    )

    oms = OMS()

    with pytest.raises(
        OMSAuthorizationError
    ):
        oms.submit_authorized_order(
            intent
        )

    assert not oms.has_order(
        "IV-I-E-RISK"
    )


def test_live_trading_enabled_is_hard_stop() -> None:
    authorization = _make_authorization()

    unsafe = ExecutionAuthorization(
        status=ExecutionAuthorizationStatus.AUTHORIZED,
        authorized=True,
        decision_id=authorization.decision_id,
        regime=authorization.regime,
        weights=authorization.weights,
        portfolio_volatility=authorization.portfolio_volatility,
        portfolio_variance=authorization.portfolio_variance,
        gross_exposure=authorization.gross_exposure,
        net_exposure=authorization.net_exposure,
        risk_contributions=authorization.risk_contributions,
        risk_contribution_pct=authorization.risk_contribution_pct,
        risk_validation_passed=True,
        live_trading_enabled=True,
        broker_submission_enabled=False,
        warnings=(),
        errors=(),
        diagnostics={},
        api_version="1.0.0",
        phase="PHASE IV-B.5",
    )

    intent = AuthorizedOrderIntent(
        order=Order(
            order_id="IV-I-E-LIVE",
            ticker="SPY",
            side="BUY",
            quantity=10.0,
        ),
        authorization=unsafe,
        decision_id=authorization.decision_id,
        regime=authorization.regime,
    )

    oms = OMS()

    with pytest.raises(
        OMSAuthorizationError
    ):
        oms.submit_authorized_order(
            intent
        )


def test_broker_submission_enabled_is_hard_stop() -> None:
    authorization = _make_authorization()

    unsafe = ExecutionAuthorization(
        status=ExecutionAuthorizationStatus.AUTHORIZED,
        authorized=True,
        decision_id=authorization.decision_id,
        regime=authorization.regime,
        weights=authorization.weights,
        portfolio_volatility=authorization.portfolio_volatility,
        portfolio_variance=authorization.portfolio_variance,
        gross_exposure=authorization.gross_exposure,
        net_exposure=authorization.net_exposure,
        risk_contributions=authorization.risk_contributions,
        risk_contribution_pct=authorization.risk_contribution_pct,
        risk_validation_passed=True,
        live_trading_enabled=False,
        broker_submission_enabled=True,
        warnings=(),
        errors=(),
        diagnostics={},
        api_version="1.0.0",
        phase="PHASE IV-B.5",
    )

    intent = AuthorizedOrderIntent(
        order=Order(
            order_id="IV-I-E-BROKER",
            ticker="SPY",
            side="BUY",
            quantity=10.0,
        ),
        authorization=unsafe,
        decision_id=authorization.decision_id,
        regime=authorization.regime,
    )

    oms = OMS()

    with pytest.raises(
        OMSAuthorizationError
    ):
        oms.submit_authorized_order(
            intent
        )


def test_authorized_submission_does_not_execute() -> None:
    oms = OMS()

    intent = _make_intent()

    submitted = oms.submit_authorized_order(
        intent
    )

    assert submitted.status == "PENDING"
    assert oms.last_trade is None


def test_authorized_submission_does_not_route() -> None:
    oms = OMS()

    intent = _make_intent()

    oms.submit_authorized_order(
        intent
    )

    assert oms.has_order(
        "IV-I-E-001"
    )


def test_oms_public_api_exposes_authorized_submission() -> None:
    oms = OMS()

    assert (
        "submit_authorized_order"
        in oms.public_methods
    )


def test_existing_raw_submission_contract_remains_intact() -> None:
    oms = OMS()

    order = Order(
        order_id="IV-I-E-RAW-COMPAT",
        ticker="SPY",
        side="BUY",
        quantity=10.0,
    )

    submitted = oms.submit_order(
        order
    )

    assert submitted is order
    assert submitted.status == "PENDING"