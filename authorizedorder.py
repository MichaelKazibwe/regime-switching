# ======================================================================
# AUTHORIZED ORDER FACTORY
# PHASE IV-I-A
# ======================================================================

"""
Authorized Order Factory
------------------------

Phase IV-I-A establishes the controlled bridge between the
ProductionExecutionGate authorization artifact and the canonical
Order object.

Design principles
-----------------
1. ExecutionAuthorization remains authoritative.
2. No Order may be created through this factory without authorization.
3. REJECTED authorization is a hard stop.
4. FAILED authorization is a hard stop.
5. authorized=False is a hard stop.
6. Missing decision_id is a hard stop.
7. Missing regime is a hard stop.
8. Failed risk validation is a hard stop.
9. Live trading remains disabled.
10. Broker submission remains disabled.
11. This factory does not submit orders.
12. This factory does not route orders.
13. This factory does not communicate with brokers.
14. This factory does not communicate with OMS.
15. This factory does not mutate portfolio state.
16. Order remains the canonical downstream execution object.
17. Order.validate() remains the final structural order validator.
"""

# ======================================================================
# SECTION 1
# IMPORTS
# ======================================================================

from __future__ import annotations

from typing import Any

from order import Order

from productionexecutiongate import (
    ExecutionAuthorization,
    ExecutionAuthorizationStatus,
    ProductionExecutionGate,
    ProductionExecutionGateError,
)


# ======================================================================
# SECTION 2
# EXCEPTIONS
# ======================================================================


class AuthorizedOrderError(
    RuntimeError
):
    """
    Raised when an Order cannot safely be created from an execution
    authorization.
    """

    pass


# ======================================================================
# SECTION 3
# AUTHORIZED ORDER FACTORY
# ======================================================================


class AuthorizedOrderFactory:
    """
    Controlled Phase IV-I-A bridge from execution authorization to Order.

    This class creates Order objects only.

    It does not:
        - submit orders
        - route orders
        - communicate with brokers
        - communicate with OMS
        - mutate portfolio state
        - enable live trading
    """

    API_VERSION = "1.0.0"

    PHASE = "PHASE IV-I-A"

    # ------------------------------------------------------------------
    # 3.1 INITIALIZATION
    # ------------------------------------------------------------------

    def __init__(
        self,
        execution_gate: ProductionExecutionGate | None = None,
    ) -> None:

        self.execution_gate = (
            execution_gate
            if execution_gate is not None
            else ProductionExecutionGate()
        )

        self.creation_count = 0

        self.last_order: Order | None = None

    # ==================================================================
    # SECTION 4
    # AUTHORIZATION VALIDATION
    # ==================================================================

    def _validate_authorization(
        self,
        authorization: ExecutionAuthorization,
    ) -> None:
        """
        Enforce the complete Phase IV-B.5 authorization contract.
        """

        if not isinstance(
            authorization,
            ExecutionAuthorization,
        ):
            raise AuthorizedOrderError(
                "authorization must be an ExecutionAuthorization."
            )

        try:
            self.execution_gate.require_authorization(
                authorization
            )

        except (
            ProductionExecutionGateError,
            Exception,
        ) as exc:

            raise AuthorizedOrderError(
                "Execution authorization denied: "
                f"{exc}"
            ) from exc

        if (
            authorization.status
            != ExecutionAuthorizationStatus.AUTHORIZED
        ):
            raise AuthorizedOrderError(
                "Order creation requires AUTHORIZED status."
            )

        if not authorization.authorized:
            raise AuthorizedOrderError(
                "Order creation requires authorized=True."
            )

        if not authorization.decision_id:
            raise AuthorizedOrderError(
                "Order creation requires a decision_id."
            )

        if not authorization.regime:
            raise AuthorizedOrderError(
                "Order creation requires a regime."
            )

        if not authorization.risk_validation_passed:
            raise AuthorizedOrderError(
                "Order creation requires successful risk validation."
            )

        # --------------------------------------------------------------
        # Live trading must remain disabled.
        # --------------------------------------------------------------

        if authorization.live_trading_enabled:
            raise AuthorizedOrderError(
                "Live trading is disabled at Phase IV-I-A."
            )

        # --------------------------------------------------------------
        # Broker submission must remain disabled.
        # --------------------------------------------------------------

        if authorization.broker_submission_enabled:
            raise AuthorizedOrderError(
                "Broker submission is disabled at Phase IV-I-A."
            )

    # ==================================================================
    # SECTION 5
    # ORDER INPUT VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_order_inputs(
        ticker: str,
        side: str,
        quantity: float,
        order_type: str,
        time_in_force: str,
    ) -> None:
        """
        Validate order creation inputs before constructing Order.
        """

        if not isinstance(
            ticker,
            str,
        ) or not ticker.strip():

            raise AuthorizedOrderError(
                "ticker must be a non-empty string."
            )

        if side not in (
            "BUY",
            "SELL",
        ):
            raise AuthorizedOrderError(
                "side must be BUY or SELL."
            )

        if quantity <= 0:
            raise AuthorizedOrderError(
                "quantity must be positive."
            )

        if order_type not in (
            "MARKET",
            "LIMIT",
            "STOP",
            "STOP_LIMIT",
        ):
            raise AuthorizedOrderError(
                "Unsupported order type."
            )

        if time_in_force not in (
            "DAY",
            "GTC",
            "IOC",
            "FOK",
        ):
            raise AuthorizedOrderError(
                "Unsupported time-in-force."
            )

    # ==================================================================
    # SECTION 6
    # WEIGHT / INTENT VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_ticker_authorization_scope(
        authorization: ExecutionAuthorization,
        ticker: str,
    ) -> None:
        """
        Require the requested ticker to exist in the authorized portfolio
        scope.

        A zero authorized weight is not rejected here because an order
        can legitimately be a transition toward or away from a target
        position. The authorization scope itself must nevertheless
        contain the instrument.
        """

        if ticker not in authorization.weights:
            raise AuthorizedOrderError(
                (
                    "Ticker is outside the authorized portfolio scope: "
                    f"{ticker}"
                )
            )

    # ==================================================================
    # SECTION 7
    # CREATE ORDER
    # ==================================================================

    def create_order(
        self,
        authorization: ExecutionAuthorization,
        ticker: str,
        side: str,
        quantity: float,
        order_type: str = "MARKET",
        time_in_force: str = "DAY",
        limit_price: float | None = None,
        stop_price: float | None = None,
        order_id: str | None = None,
    ) -> Order:
        """
        Create one canonical Order from an authorized execution artifact.

        This method creates an Order only.

        It does not submit or route the resulting order.
        """

        # --------------------------------------------------------------
        # Authorization is checked before order creation.
        # --------------------------------------------------------------

        self._validate_authorization(
            authorization
        )

        # --------------------------------------------------------------
        # Validate structural order intent.
        # --------------------------------------------------------------

        self._validate_order_inputs(
            ticker=ticker,
            side=side,
            quantity=quantity,
            order_type=order_type,
            time_in_force=time_in_force,
        )

        # --------------------------------------------------------------
        # Ensure the instrument belongs to the authorized portfolio.
        # --------------------------------------------------------------

        self._validate_ticker_authorization_scope(
            authorization=authorization,
            ticker=ticker,
        )

        # --------------------------------------------------------------
        # Construct canonical Order.
        # --------------------------------------------------------------

        order_kwargs: dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "order_type": order_type,
            "time_in_force": time_in_force,
        }

        if limit_price is not None:
            order_kwargs["limit_price"] = limit_price

        if stop_price is not None:
            order_kwargs["stop_price"] = stop_price

        if order_id is not None:
            order_kwargs["order_id"] = order_id

        order = Order(
            **order_kwargs
        )

        # --------------------------------------------------------------
        # Canonical Order validator remains authoritative for structural
        # correctness.
        # --------------------------------------------------------------

        try:
            order.validate()

        except Exception as exc:

            raise AuthorizedOrderError(
                "Constructed Order failed validation: "
                f"{exc}"
            ) from exc

        self.creation_count += 1

        self.last_order = order

        return order

    # ==================================================================
    # SECTION 8
    # BATCH CREATION
    # ==================================================================

    def create_orders(
        self,
        authorization: ExecutionAuthorization,
        intents: list[dict[str, Any]],
    ) -> list[Order]:
        """
        Create multiple canonical Orders from one authorization.

        Every individual order is subjected to the same authorization
        and structural validation boundary.

        No order is submitted or routed.
        """

        self._validate_authorization(
            authorization
        )

        if not isinstance(
            intents,
            list,
        ):
            raise TypeError(
                "intents must be a list."
            )

        orders: list[Order] = []

        for intent in intents:

            if not isinstance(
                intent,
                dict,
            ):
                raise TypeError(
                    "Each order intent must be a dictionary."
                )

            order = self.create_order(
                authorization=authorization,
                **intent,
            )

            orders.append(
                order
            )

        return orders

    # ==================================================================
    # SECTION 9
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ) -> bool:
        """
        Verify that the factory is correctly configured.
        """

        if not isinstance(
            self.execution_gate,
            ProductionExecutionGate,
        ):
            return False

        if not self.API_VERSION:
            return False

        if not self.PHASE:
            return False

        return True

    # ==================================================================
    # SECTION 10
    # SERIALIZATION
    # ==================================================================

    def to_dict(
        self,
    ) -> dict[str, Any]:
        """
        Return deterministic factory metadata.
        """

        return {
            "component": "AuthorizedOrderFactory",
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "creation_count": self.creation_count,
            "last_order_id": (
                None
                if self.last_order is None
                else self.last_order.order_id
            ),
        }


# ======================================================================
# SECTION 11
# REGRESSION TEST
# ======================================================================


def test_authorized_order_factory() -> None:
    """
    Basic Phase IV-I-A factory regression test.

    Full authorization-boundary tests belong in the dedicated Phase IV-I
    test module.
    """

    factory = AuthorizedOrderFactory()

    assert factory.health_check()

    assert factory.API_VERSION == "1.0.0"

    assert factory.PHASE == "PHASE IV-I-A"

    assert factory.to_dict()["component"] == (
        "AuthorizedOrderFactory"
    )


if __name__ == "__main__":

    test_authorized_order_factory()

    print(
        "PHASE IV-I-A AUTHORIZED ORDER FACTORY TESTS PASSED."
    )
