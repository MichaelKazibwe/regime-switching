# ======================================================================
# PHASE IV-I-B
# AUTHORIZED ORDER FACTORY REGRESSION TESTS
# ======================================================================

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from authorizedorder import (
    AuthorizedOrderError,
    AuthorizedOrderFactory,
)

from productionexecutiongate import (
    ExecutionAuthorization,
    ExecutionAuthorizationStatus,
)


# ======================================================================
# TEST AUTHORIZATION FACTORY
# ======================================================================


def _authorized() -> ExecutionAuthorization:
    return ExecutionAuthorization(
        status=ExecutionAuthorizationStatus.AUTHORIZED,
        authorized=True,
        decision_id="PHASE-IV-I-B-001",
        regime="NORMAL",
        weights={
            "SPY": 0.60,
            "QQQ": 0.40,
        },
        portfolio_volatility=0.15,
        portfolio_variance=0.0225,
        gross_exposure=1.0,
        net_exposure=1.0,
        risk_contributions={
            "SPY": 0.60,
            "QQQ": 0.40,
        },
        risk_contribution_pct={
            "SPY": 0.60,
            "QQQ": 0.40,
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


def _rejected() -> ExecutionAuthorization:
    authorization = _authorized()

    return ExecutionAuthorization(
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


def _failed() -> ExecutionAuthorization:
    authorization = _authorized()

    return ExecutionAuthorization(
        status=ExecutionAuthorizationStatus.FAILED,
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
        errors=("FAILED",),
        diagnostics={},
        api_version="1.0.0",
        phase="PHASE IV-B.5",
    )


# ======================================================================
# BASIC HEALTH
# ======================================================================


def test_factory_health() -> None:

    factory = AuthorizedOrderFactory()

    assert factory.health_check()

    assert factory.API_VERSION == "1.0.0"

    assert factory.PHASE == "PHASE IV-I-A"


# ======================================================================
# AUTHORIZED ORDER CREATION
# ======================================================================


def test_authorized_order_creation() -> None:

    factory = AuthorizedOrderFactory()

    authorization = _authorized()

    order = factory.create_order(
        authorization=authorization,
        ticker="SPY",
        side="BUY",
        quantity=100,
    )

    assert order.ticker == "SPY"

    assert order.side == "BUY"

    assert order.quantity == 100

    assert order.order_type == "MARKET"

    assert order.time_in_force == "DAY"

    assert order.validate()

    assert factory.creation_count == 1

    assert factory.last_order is order


# ======================================================================
# CUSTOM ORDER ID
# ======================================================================


def test_authorized_order_preserves_explicit_order_id() -> None:

    factory = AuthorizedOrderFactory()

    order = factory.create_order(
        authorization=_authorized(),
        ticker="QQQ",
        side="SELL",
        quantity=25,
        order_id="PHASE-IV-I-B-ORDER-001",
    )

    assert order.order_id == (
        "PHASE-IV-I-B-ORDER-001"
    )


# ======================================================================
# REJECTED AUTHORIZATION
# ======================================================================


def test_rejected_authorization_cannot_create_order() -> None:

    factory = AuthorizedOrderFactory()

    with pytest.raises(
        AuthorizedOrderError
    ):

        factory.create_order(
            authorization=_rejected(),
            ticker="SPY",
            side="BUY",
            quantity=100,
        )

    assert factory.creation_count == 0

    assert factory.last_order is None


# ======================================================================
# FAILED AUTHORIZATION
# ======================================================================


def test_failed_authorization_cannot_create_order() -> None:

    factory = AuthorizedOrderFactory()

    with pytest.raises(
        AuthorizedOrderError
    ):

        factory.create_order(
            authorization=_failed(),
            ticker="SPY",
            side="BUY",
            quantity=100,
        )

    assert factory.creation_count == 0

    assert factory.last_order is None


# ======================================================================
# AUTHORIZED FLAG
# ======================================================================


def test_authorized_false_cannot_create_order() -> None:

    authorization = _authorized()

    authorization = ExecutionAuthorization(
        status=ExecutionAuthorizationStatus.AUTHORIZED,
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
        risk_validation_passed=True,
        live_trading_enabled=False,
        broker_submission_enabled=False,
        warnings=(),
        errors=(),
        diagnostics={},
        api_version="1.0.0",
        phase="PHASE IV-B.5",
    )

    factory = AuthorizedOrderFactory()

    with pytest.raises(
        AuthorizedOrderError
    ):

        factory.create_order(
            authorization=authorization,
            ticker="SPY",
            side="BUY",
            quantity=100,
        )


# ======================================================================
# RISK VALIDATION
# ======================================================================


def test_failed_risk_validation_cannot_create_order() -> None:

    authorization = _authorized()

    authorization = ExecutionAuthorization(
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
        errors=("RISK_FAILED",),
        diagnostics={},
        api_version="1.0.0",
        phase="PHASE IV-B.5",
    )

    factory = AuthorizedOrderFactory()

    with pytest.raises(
        AuthorizedOrderError
    ):

        factory.create_order(
            authorization=authorization,
            ticker="SPY",
            side="BUY",
            quantity=100,
        )


# ======================================================================
# LIVE TRADING HARD STOP
# ======================================================================


def test_live_trading_enabled_is_hard_stop() -> None:

    authorization = _authorized()

    authorization = ExecutionAuthorization(
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

    factory = AuthorizedOrderFactory()

    with pytest.raises(
        AuthorizedOrderError
    ):

        factory.create_order(
            authorization=authorization,
            ticker="SPY",
            side="BUY",
            quantity=100,
        )


# ======================================================================
# BROKER SUBMISSION HARD STOP
# ======================================================================


def test_broker_submission_enabled_is_hard_stop() -> None:

    authorization = _authorized()

    authorization = ExecutionAuthorization(
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

    factory = AuthorizedOrderFactory()

    with pytest.raises(
        AuthorizedOrderError
    ):

        factory.create_order(
            authorization=authorization,
            ticker="SPY",
            side="BUY",
            quantity=100,
        )


# ======================================================================
# UNAUTHORIZED TICKER
# ======================================================================


def test_unauthorized_ticker_cannot_create_order() -> None:

    factory = AuthorizedOrderFactory()

    with pytest.raises(
        AuthorizedOrderError
    ):

        factory.create_order(
            authorization=_authorized(),
            ticker="AAPL",
            side="BUY",
            quantity=100,
        )


# ======================================================================
# INVALID SIDE
# ======================================================================


def test_invalid_side_cannot_create_order() -> None:

    factory = AuthorizedOrderFactory()

    with pytest.raises(
        AuthorizedOrderError
    ):

        factory.create_order(
            authorization=_authorized(),
            ticker="SPY",
            side="HOLD",
            quantity=100,
        )


# ======================================================================
# INVALID QUANTITY
# ======================================================================


def test_invalid_quantity_cannot_create_order() -> None:

    factory = AuthorizedOrderFactory()

    with pytest.raises(
        AuthorizedOrderError
    ):

        factory.create_order(
            authorization=_authorized(),
            ticker="SPY",
            side="BUY",
            quantity=0,
        )


# ======================================================================
# IMMUTABLE AUTHORIZATION
# ======================================================================


def test_authorization_is_immutable() -> None:

    authorization = _authorized()

    with pytest.raises(
        FrozenInstanceError
    ):

        authorization.authorized = False


# ======================================================================
# BATCH CREATION
# ======================================================================


def test_batch_creation() -> None:

    factory = AuthorizedOrderFactory()

    orders = factory.create_orders(
        authorization=_authorized(),
        intents=[
            {
                "ticker": "SPY",
                "side": "BUY",
                "quantity": 100,
            },
            {
                "ticker": "QQQ",
                "side": "SELL",
                "quantity": 50,
            },
        ],
    )

    assert len(orders) == 2

    assert orders[0].ticker == "SPY"

    assert orders[1].ticker == "QQQ"

    assert factory.creation_count == 2


# ======================================================================
# NO SUBMISSION / ROUTING
# ======================================================================


def test_factory_only_creates_orders() -> None:

    factory = AuthorizedOrderFactory()

    order = factory.create_order(
        authorization=_authorized(),
        ticker="SPY",
        side="BUY",
        quantity=10,
    )

    assert order.status == "PENDING"

    assert not order.is_submitted()

    assert factory.last_order is order


# ======================================================================
# TEST ENTRYPOINT
# ======================================================================


if __name__ == "__main__":

    pytest.main(
        [
            __file__,
            "-v",
        ]
    )
