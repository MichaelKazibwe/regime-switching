# ======================================================================
# AUTHORIZED ORDER INTENT
# PHASE IV-I-C / IV-I-D
# ======================================================================

"""
Authorized Order Intent
-----------------------

Phase IV-I-C establishes the immutable provenance boundary between:

    ExecutionAuthorization
            +
          Order
            ↓
    AuthorizedOrderIntent

The object preserves the authorization context that permitted an Order
to be created without modifying the canonical Order contract.

Design principles
-----------------
1. ExecutionAuthorization remains authoritative.
2. Order remains the canonical execution object.
3. Authorization provenance must not be discarded.
4. REJECTED authorization cannot produce an intent.
5. FAILED authorization cannot produce an intent.
6. authorized=False cannot produce an intent.
7. Failed risk validation cannot produce an intent.
8. Live trading remains disabled.
9. Broker submission remains disabled.
10. The authorized ticker must belong to the authorization scope.
11. The Order must pass Order.validate().
12. The authorization object is immutable.
13. The intent is immutable.
14. The intent does not submit an order.
15. The intent does not route an order.
16. The intent does not communicate with a broker.
17. The intent does not communicate with OMS.
18. The intent does not mutate portfolio state.
"""

# ======================================================================
# SECTION 1
# IMPORTS
# ======================================================================

from __future__ import annotations

from dataclasses import (
    dataclass,
)

from typing import (
    Any,
    ClassVar,
)

from order import (
    Order,
)

from productionexecutiongate import (
    ExecutionAuthorization,
    ExecutionAuthorizationStatus,
)


# ======================================================================
# SECTION 2
# EXCEPTIONS
# ======================================================================


class AuthorizedOrderIntentError(
    RuntimeError
):
    """
    Raised when an authorized order intent cannot be safely constructed.
    """

    pass


# ======================================================================
# SECTION 3
# AUTHORIZED ORDER INTENT
# ======================================================================


@dataclass(
    frozen=True
)
class AuthorizedOrderIntent:
    """
    Immutable authorization-provenance envelope around an Order.

    This object connects the canonical Order to the exact
    ExecutionAuthorization under which it was created.

    It is an execution-intent artifact only.

    It does not:
        - submit the Order
        - route the Order
        - communicate with a broker
        - communicate with OMS
        - mutate portfolio state
    """

    # ------------------------------------------------------------------
    # 3.1 ORDER
    # ------------------------------------------------------------------

    order: Order

    # ------------------------------------------------------------------
    # 3.2 AUTHORIZATION
    # ------------------------------------------------------------------

    authorization: ExecutionAuthorization

    # ------------------------------------------------------------------
    # 3.3 PROVENANCE
    # ------------------------------------------------------------------

    decision_id: str

    regime: str

    # ------------------------------------------------------------------
    # 3.4 METADATA
    # ------------------------------------------------------------------

    API_VERSION: ClassVar[str] = "1.0.0"

    PHASE: ClassVar[str] = "PHASE IV-I-C"

    # ==================================================================
    # SECTION 4
    # VALIDATION
    # ==================================================================

    def validate(
        self,
    ) -> bool:
        """
        Validate the complete authorization/order relationship.
        """

        # --------------------------------------------------------------
        # Order type
        # --------------------------------------------------------------

        if not isinstance(
            self.order,
            Order,
        ):
            raise AuthorizedOrderIntentError(
                "AuthorizedOrderIntent.order must be an Order."
            )

        # --------------------------------------------------------------
        # Authorization type
        # --------------------------------------------------------------

        if not isinstance(
            self.authorization,
            ExecutionAuthorization,
        ):
            raise AuthorizedOrderIntentError(
                (
                    "AuthorizedOrderIntent.authorization must be "
                    "an ExecutionAuthorization."
                )
            )

        # --------------------------------------------------------------
        # Authorization status
        # --------------------------------------------------------------

        if (
            self.authorization.status
            != ExecutionAuthorizationStatus.AUTHORIZED
        ):
            raise AuthorizedOrderIntentError(
                (
                    "AuthorizedOrderIntent requires AUTHORIZED "
                    "execution authorization."
                )
            )

        # --------------------------------------------------------------
        # Authorization flag
        # --------------------------------------------------------------

        if not self.authorization.authorized:
            raise AuthorizedOrderIntentError(
                (
                    "AuthorizedOrderIntent requires "
                    "authorization.authorized=True."
                )
            )

        # --------------------------------------------------------------
        # Decision identity
        # --------------------------------------------------------------

        if not self.authorization.decision_id:
            raise AuthorizedOrderIntentError(
                "Execution authorization has no decision_id."
            )

        # --------------------------------------------------------------
        # Regime
        # --------------------------------------------------------------

        if not self.authorization.regime:
            raise AuthorizedOrderIntentError(
                "Execution authorization has no regime."
            )

        # --------------------------------------------------------------
        # Risk validation
        # --------------------------------------------------------------

        if not self.authorization.risk_validation_passed:
            raise AuthorizedOrderIntentError(
                (
                    "Execution authorization does not contain "
                    "successful risk validation."
                )
            )

        # --------------------------------------------------------------
        # Live trading
        # --------------------------------------------------------------

        if self.authorization.live_trading_enabled:
            raise AuthorizedOrderIntentError(
                (
                    "Live trading cannot be enabled for an "
                    "AuthorizedOrderIntent."
                )
            )

        # --------------------------------------------------------------
        # Broker submission
        # --------------------------------------------------------------

        if self.authorization.broker_submission_enabled:
            raise AuthorizedOrderIntentError(
                (
                    "Broker submission cannot be enabled for an "
                    "AuthorizedOrderIntent."
                )
            )

        # --------------------------------------------------------------
        # Provenance must match authorization.
        # --------------------------------------------------------------

        if (
            self.decision_id
            != self.authorization.decision_id
        ):
            raise AuthorizedOrderIntentError(
                (
                    "Intent decision_id does not match execution "
                    "authorization decision_id."
                )
            )

        if (
            self.regime
            != self.authorization.regime
        ):
            raise AuthorizedOrderIntentError(
                (
                    "Intent regime does not match execution "
                    "authorization regime."
                )
            )

        # --------------------------------------------------------------
        # Authorized instrument scope.
        # --------------------------------------------------------------

        if self.order.ticker not in self.authorization.weights:
            raise AuthorizedOrderIntentError(
                (
                    "Order ticker is outside the authorized portfolio "
                    f"scope: {self.order.ticker}"
                )
            )

        # --------------------------------------------------------------
        # Canonical Order validation.
        # --------------------------------------------------------------

        try:
            self.order.validate()

        except Exception as exc:

            raise AuthorizedOrderIntentError(
                (
                    "Order contained in AuthorizedOrderIntent failed "
                    f"validation: {exc}"
                )
            ) from exc

        return True

    # ==================================================================
    # SECTION 5
    # FACTORY
    # ==================================================================

    @classmethod
    def from_authorization(
        cls,
        authorization: ExecutionAuthorization,
        order: Order,
    ) -> "AuthorizedOrderIntent":
        """
        Construct an immutable intent from an authorized execution
        artifact and a canonical Order.
        """

        if not isinstance(
            authorization,
            ExecutionAuthorization,
        ):
            raise AuthorizedOrderIntentError(
                "authorization must be an ExecutionAuthorization."
            )

        if not isinstance(
            order,
            Order,
        ):
            raise AuthorizedOrderIntentError(
                "order must be an Order."
            )

        if (
            authorization.status
            != ExecutionAuthorizationStatus.AUTHORIZED
        ):
            raise AuthorizedOrderIntentError(
                (
                    "Cannot create AuthorizedOrderIntent from "
                    f"authorization status "
                    f"{authorization.status}."
                )
            )

        if not authorization.authorized:
            raise AuthorizedOrderIntentError(
                (
                    "Cannot create AuthorizedOrderIntent from "
                    "authorized=False."
                )
            )

        if not authorization.decision_id:
            raise AuthorizedOrderIntentError(
                "Cannot create intent without decision_id."
            )

        if not authorization.regime:
            raise AuthorizedOrderIntentError(
                "Cannot create intent without regime."
            )

        if not authorization.risk_validation_passed:
            raise AuthorizedOrderIntentError(
                "Cannot create intent after failed risk validation."
            )

        if authorization.live_trading_enabled:
            raise AuthorizedOrderIntentError(
                "Cannot create intent while live trading is enabled."
            )

        if authorization.broker_submission_enabled:
            raise AuthorizedOrderIntentError(
                (
                    "Cannot create intent while broker submission "
                    "is enabled."
                )
            )

        if order.ticker not in authorization.weights:
            raise AuthorizedOrderIntentError(
                (
                    "Order ticker is outside authorized portfolio "
                    f"scope: {order.ticker}"
                )
            )

        intent = cls(
            order=order,
            authorization=authorization,
            decision_id=authorization.decision_id,
            regime=authorization.regime,
        )

        intent.validate()

        return intent

    # ==================================================================
    # SECTION 6
    # AUTHORIZED ORDER CREATION BRIDGE
    # ==================================================================

    @classmethod
    def create_order(
        cls,
        authorization: ExecutionAuthorization,
        ticker: str,
        side: str,
        quantity: float,
        order_type: str = "MARKET",
        time_in_force: str = "DAY",
        limit_price: float | None = None,
        stop_price: float | None = None,
        order_id: str | None = None,
    ) -> "AuthorizedOrderIntent":
        """
        Create a canonical Order only after successful execution
        authorization and immediately bind it to that authorization.

        Phase IV-I-D is the controlled bridge between:

            ExecutionAuthorization
                    ↓
            canonical Order
                    ↓
            AuthorizedOrderIntent

        This method does not:
            - submit the order
            - route the order
            - communicate with a broker
            - communicate with OMS
            - mutate portfolio state
        """

        # --------------------------------------------------------------
        # Authorization object
        # --------------------------------------------------------------

        if not isinstance(
            authorization,
            ExecutionAuthorization,
        ):
            raise AuthorizedOrderIntentError(
                "authorization must be an ExecutionAuthorization."
            )

        # --------------------------------------------------------------
        # Authorization status
        # --------------------------------------------------------------

        if (
            authorization.status
            != ExecutionAuthorizationStatus.AUTHORIZED
        ):
            raise AuthorizedOrderIntentError(
                (
                    "Order creation requires AUTHORIZED execution "
                    f"authorization; received {authorization.status}."
                )
            )

        if not authorization.authorized:
            raise AuthorizedOrderIntentError(
                "Order creation requires authorized=True."
            )

        # --------------------------------------------------------------
        # Required authorization provenance
        # --------------------------------------------------------------

        if not authorization.decision_id:
            raise AuthorizedOrderIntentError(
                "Order creation requires authorization.decision_id."
            )

        if not authorization.regime:
            raise AuthorizedOrderIntentError(
                "Order creation requires authorization.regime."
            )

        if not authorization.risk_validation_passed:
            raise AuthorizedOrderIntentError(
                "Order creation requires successful risk validation."
            )

        # --------------------------------------------------------------
        # Execution controls
        # --------------------------------------------------------------

        if authorization.live_trading_enabled:
            raise AuthorizedOrderIntentError(
                "Live trading cannot be enabled during Phase IV-I-D."
            )

        if authorization.broker_submission_enabled:
            raise AuthorizedOrderIntentError(
                "Broker submission cannot be enabled during Phase IV-I-D."
            )

        # --------------------------------------------------------------
        # Instrument authorization scope
        # --------------------------------------------------------------

        if not isinstance(ticker, str) or not ticker.strip():
            raise AuthorizedOrderIntentError(
                "ticker must be a non-empty string."
            )

        if ticker not in authorization.weights:
            raise AuthorizedOrderIntentError(
                (
                    "Order ticker is outside the authorized portfolio "
                    f"scope: {ticker}"
                )
            )

        # --------------------------------------------------------------
        # Structural order validation
        # --------------------------------------------------------------

        if side not in ("BUY", "SELL"):
            raise AuthorizedOrderIntentError(
                "side must be BUY or SELL."
            )

        if quantity <= 0:
            raise AuthorizedOrderIntentError(
                "quantity must be positive."
            )

        if order_type not in (
            "MARKET",
            "LIMIT",
            "STOP",
            "STOP_LIMIT",
        ):
            raise AuthorizedOrderIntentError(
                "Unsupported order type."
            )

        if time_in_force not in (
            "DAY",
            "GTC",
            "IOC",
            "FOK",
        ):
            raise AuthorizedOrderIntentError(
                "Unsupported time-in-force."
            )

        # --------------------------------------------------------------
        # Construct the canonical Order
        # --------------------------------------------------------------

        order_kwargs: dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "order_type": order_type,
            "time_in_force": time_in_force,
            # Preserve the execution authorization's decision identity on
            # the canonical Order itself. Downstream broker and accounting
            # records already carry this field, so dropping it here breaks
            # end-to-end audit correlation.
            "decision_id": authorization.decision_id,
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
        # Canonical Order validation
        # --------------------------------------------------------------

        try:
            order.validate()

        except Exception as exc:
            raise AuthorizedOrderIntentError(
                (
                    "Constructed Order failed canonical validation: "
                    f"{exc}"
                )
            ) from exc

        # --------------------------------------------------------------
        # Bind exact authorization provenance
        # --------------------------------------------------------------

        return cls.from_authorization(
            authorization=authorization,
            order=order,
        )

    # ------------------------------------------------------------------
    # BATCH AUTHORIZED ORDER CREATION
    # ------------------------------------------------------------------

    @classmethod
    def create_orders(
        cls,
        authorization: ExecutionAuthorization,
        intents: list[dict[str, Any]],
    ) -> list["AuthorizedOrderIntent"]:
        """
        Create multiple AuthorizedOrderIntent objects from one
        ExecutionAuthorization.

        Every order is independently validated before becoming an
        AuthorizedOrderIntent.

        No order is submitted or routed.
        """

        if not isinstance(intents, list):
            raise TypeError(
                "intents must be a list."
            )

        # Validate the authorization before processing the batch.
        # This guarantees that an invalid authorization cannot result
        # in partial order creation.
        cls._validate_batch_authorization(
            authorization
        )

        results: list[AuthorizedOrderIntent] = []

        for intent in intents:

            if not isinstance(intent, dict):
                raise TypeError(
                    "Each order intent must be a dictionary."
                )

            results.append(
                cls.create_order(
                    authorization=authorization,
                    **intent,
                )
            )

        return results

    @classmethod
    def _validate_batch_authorization(
        cls,
        authorization: ExecutionAuthorization,
    ) -> None:
        """
        Validate authorization before beginning batch creation.
        """

        if not isinstance(
            authorization,
            ExecutionAuthorization,
        ):
            raise AuthorizedOrderIntentError(
                "authorization must be an ExecutionAuthorization."
            )

        if (
            authorization.status
            != ExecutionAuthorizationStatus.AUTHORIZED
        ):
            raise AuthorizedOrderIntentError(
                (
                    "Batch order creation requires AUTHORIZED "
                    f"authorization; received {authorization.status}."
                )
            )

        if not authorization.authorized:
            raise AuthorizedOrderIntentError(
                "Batch order creation requires authorized=True."
            )

        if not authorization.decision_id:
            raise AuthorizedOrderIntentError(
                "Batch order creation requires decision_id."
            )

        if not authorization.regime:
            raise AuthorizedOrderIntentError(
                "Batch order creation requires regime."
            )

        if not authorization.risk_validation_passed:
            raise AuthorizedOrderIntentError(
                "Batch order creation requires successful risk validation."
            )

        if authorization.live_trading_enabled:
            raise AuthorizedOrderIntentError(
                "Live trading cannot be enabled during Phase IV-I-D."
            )

        if authorization.broker_submission_enabled:
            raise AuthorizedOrderIntentError(
                "Broker submission cannot be enabled during Phase IV-I-D."
            )

        return None


    # ==================================================================
    # SECTION 7
    # SERIALIZATION
    # ==================================================================

    def to_dict(
        self,
    ) -> dict[str, Any]:
        """
        Serialize the intent while retaining complete provenance.
        """

        self.validate()

        return {
            "order": self.order.to_dict(),
            "authorization": self.authorization.to_dict(),
            "decision_id": self.decision_id,
            "regime": self.regime,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
        }

    # ==================================================================
    # SECTION 8
    # EXECUTION BOUNDARY METADATA
    # ==================================================================

    @property
    def order_id(
        self,
    ) -> str:
        """
        Return the canonical Order identity.
        """

        return self.order.order_id

    @property
    def ticker(
        self,
    ) -> str:
        """
        Return the canonical Order ticker.
        """

        return self.order.ticker

    @property
    def side(
        self,
    ) -> str:
        """
        Return the canonical Order side.
        """

        return self.order.side

    @property
    def quantity(
        self,
    ) -> float:
        """
        Return the canonical Order quantity.
        """

        return self.order.quantity

    @property
    def authorized(
        self,
    ) -> bool:
        """
        Return whether the underlying authorization is active.
        """

        return (
            self.authorization.authorized
            and
            self.authorization.status
            == ExecutionAuthorizationStatus.AUTHORIZED
        )

    # ==================================================================
    # SECTION 9
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ) -> bool:
        """
        Validate the complete intent.
        """

        return self.validate()


# ======================================================================
# SECTION 9
# REGRESSION TEST
# ======================================================================


def test_authorized_order_intent() -> None:
    """
    Minimal standalone regression test.

    Full adversarial tests belong in:
        test_phase_iv_i_authorized_order_intent.py
    """

    assert AuthorizedOrderIntent.API_VERSION == "1.0.0"

    assert AuthorizedOrderIntent.PHASE == (
        "PHASE IV-I-C"
    )


if __name__ == "__main__":

    test_authorized_order_intent()

    print(
        "PHASE IV-I-C AUTHORIZED ORDER INTENT TESTS PASSED."
    )
