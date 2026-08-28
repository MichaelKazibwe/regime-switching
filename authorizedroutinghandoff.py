"""
======================================================================
authorizedroutinghandoff.py

PHASE IV-I-G — AUTHORIZED ROUTING HANDOFF
======================================================================

Institutional execution-to-routing handoff contract.

This module establishes the controlled boundary between:

    AuthorizedExecutionHandoff
            ↓
    AuthorizedRoutingHandoff
            ↓
    BrokerRouter / RoutingEngine

The routing handoff:

    - validates execution-handoff provenance;
    - preserves the exact canonical Order;
    - preserves the exact authorization identity;
    - preserves decision identity;
    - preserves regime identity;
    - remains immutable;
    - performs no routing;
    - performs no broker submission;
    - performs no execution;
    - performs no portfolio mutation;
    - cannot enable live trading;
    - cannot enable broker submission.

It does NOT:

    - create authorization;
    - create orders;
    - modify orders;
    - create execution authorization;
    - submit orders;
    - route orders;
    - execute trades;
    - mutate PortfolioAccount state.

Author: Michael Kazibwe
Version: 1.0.0
======================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from authorizedexecutionhandoff import (
    AuthorizedExecutionHandoff,
    AuthorizedExecutionHandoffError,
)
from order import Order


# ======================================================================
# EXCEPTIONS
# ======================================================================


class AuthorizedRoutingHandoffError(
    RuntimeError
):
    """
    Raised when an AuthorizedExecutionHandoff cannot safely cross
    the execution-to-routing handoff boundary.
    """

    pass


# ======================================================================
# AUTHORIZED ROUTING HANDOFF
# ======================================================================


@dataclass(frozen=True)
class AuthorizedRoutingHandoff:
    """
    Immutable routing handoff envelope.

    This object does not route or submit an order.

    It establishes that the canonical Order being handed into the
    routing boundary remains bound to the validated authorization,
    decision identity, and regime identity established upstream.
    """

    execution_handoff: AuthorizedExecutionHandoff

    API_VERSION: ClassVar[str] = "1.0.0"

    PHASE: ClassVar[str] = "PHASE IV-I-G"

    # ==================================================================
    # CONSTRUCTION
    # ==================================================================

    @classmethod
    def from_execution_handoff(
        cls,
        handoff: AuthorizedExecutionHandoff,
    ) -> "AuthorizedRoutingHandoff":
        """
        Construct an AuthorizedRoutingHandoff from a valid
        AuthorizedExecutionHandoff.

        No routing, broker submission, or execution occurs.
        """

        if not isinstance(
            handoff,
            AuthorizedExecutionHandoff,
        ):
            raise AuthorizedRoutingHandoffError(
                (
                    "AuthorizedRoutingHandoff requires an "
                    "AuthorizedExecutionHandoff."
                )
            )

        try:
            handoff.validate()

        except (
            AuthorizedExecutionHandoffError,
            TypeError,
            ValueError,
            RuntimeError,
        ) as exc:
            raise AuthorizedRoutingHandoffError(
                (
                    "AuthorizedExecutionHandoff failed validation "
                    "at the routing handoff boundary: "
                    f"{exc}"
                )
            ) from exc

        if not isinstance(
            handoff.execution_order(),
            Order,
        ):
            raise AuthorizedRoutingHandoffError(
                (
                    "AuthorizedExecutionHandoff does not contain "
                    "a canonical Order."
                )
            )

        result = cls(
            execution_handoff=handoff,
        )

        result.validate()

        return result

    # ==================================================================
    # VALIDATION
    # ==================================================================

    def validate(
        self,
    ) -> bool:
        """
        Validate the complete authorized routing handoff contract.

        Validation is fail-closed.

        The underlying execution handoff is revalidated so that the
        routing boundary cannot silently accept an invalidated or
        malformed upstream authorization state.
        """

        if not isinstance(
            self.execution_handoff,
            AuthorizedExecutionHandoff,
        ):
            raise AuthorizedRoutingHandoffError(
                (
                    "Routing handoff requires an "
                    "AuthorizedExecutionHandoff."
                )
            )

        try:
            self.execution_handoff.validate()

        except (
            AuthorizedExecutionHandoffError,
            TypeError,
            ValueError,
            RuntimeError,
        ) as exc:
            raise AuthorizedRoutingHandoffError(
                (
                    "Underlying AuthorizedExecutionHandoff is invalid "
                    "at the routing boundary: "
                    f"{exc}"
                )
            ) from exc

        try:
            order = self.execution_handoff.execution_order()

        except Exception as exc:
            raise AuthorizedRoutingHandoffError(
                (
                    "Canonical Order could not be retrieved from "
                    "the AuthorizedExecutionHandoff: "
                    f"{exc}"
                )
            ) from exc

        if not isinstance(
            order,
            Order,
        ):
            raise AuthorizedRoutingHandoffError(
                (
                    "Routing handoff does not contain "
                    "a canonical Order."
                )
            )

        try:
            order.validate()

        except Exception as exc:
            raise AuthorizedRoutingHandoffError(
                (
                    "Canonical Order failed validation at "
                    f"routing handoff: {exc}"
                )
            ) from exc

        # --------------------------------------------------------------
        # Decision identity
        # --------------------------------------------------------------

        if not isinstance(
            self.execution_handoff.decision_id,
            str,
        ) or not self.execution_handoff.decision_id:
            raise AuthorizedRoutingHandoffError(
                "Routing handoff decision_id must be non-empty."
            )

        # --------------------------------------------------------------
        # Regime identity
        # --------------------------------------------------------------

        if not isinstance(
            self.execution_handoff.regime,
            str,
        ) or not self.execution_handoff.regime:
            raise AuthorizedRoutingHandoffError(
                "Routing handoff regime must be non-empty."
            )

        # --------------------------------------------------------------
        # Authorization identity
        # --------------------------------------------------------------

        authorization = (
            self.execution_handoff.authorization
        )

        if authorization is None:
            raise AuthorizedRoutingHandoffError(
                "Routing handoff authorization cannot be None."
            )

        authorization_decision_id = getattr(
            authorization,
            "decision_id",
            None,
        )

        if (
            authorization_decision_id
            != self.execution_handoff.decision_id
        ):
            raise AuthorizedRoutingHandoffError(
                (
                    "Routing handoff decision_id does not match "
                    "authorization decision_id."
                )
            )

        authorization_regime = getattr(
            authorization,
            "regime",
            None,
        )

        if (
            authorization_regime
            != self.execution_handoff.regime
        ):
            raise AuthorizedRoutingHandoffError(
                (
                    "Routing handoff regime does not match "
                    "authorization regime."
                )
            )

        authorized = getattr(
            authorization,
            "authorized",
            False,
        )

        if not authorized:
            raise AuthorizedRoutingHandoffError(
                "Routing handoff requires authorized=True."
            )

        status = getattr(
            authorization,
            "status",
            None,
        )

        status_name = getattr(
            status,
            "name",
            status,
        )

        if status_name != "AUTHORIZED":
            raise AuthorizedRoutingHandoffError(
                (
                    "Routing handoff requires AUTHORIZED "
                    f"authorization status; received {status}."
                )
            )

        # --------------------------------------------------------------
        # Live trading guard
        # --------------------------------------------------------------

        if getattr(
            authorization,
            "live_trading_enabled",
            False,
        ):
            raise AuthorizedRoutingHandoffError(
                (
                    "Live trading cannot be enabled at "
                    "the routing handoff."
                )
            )

        # --------------------------------------------------------------
        # Broker submission guard
        # --------------------------------------------------------------

        if getattr(
            authorization,
            "broker_submission_enabled",
            False,
        ):
            raise AuthorizedRoutingHandoffError(
                (
                    "Broker submission cannot be enabled "
                    "at the routing handoff."
                )
            )

        return True

    # ==================================================================
    # DOWNSTREAM ORDER ACCESS
    # ==================================================================

    def routing_order(
        self,
    ) -> Order:
        """
        Return the exact canonical Order entering the routing boundary.

        This method does not route, submit, or execute the Order.
        """

        self.validate()

        try:
            order = (
                self.execution_handoff.execution_order()
            )

        except Exception as exc:
            raise AuthorizedRoutingHandoffError(
                (
                    "Unable to retrieve canonical Order for "
                    f"routing: {exc}"
                )
            ) from exc

        if not isinstance(
            order,
            Order,
        ):
            raise AuthorizedRoutingHandoffError(
                (
                    "Authorized routing handoff does not contain "
                    "a canonical Order."
                )
            )

        return order

    # ==================================================================
    # PROVENANCE
    # ==================================================================

    @property
    def order_id(
        self,
    ) -> str:
        """
        Return the canonical Order identifier.
        """

        return self.routing_order().order_id

    @property
    def ticker(
        self,
    ) -> str:
        """
        Return the canonical Order ticker.
        """

        return self.routing_order().ticker

    @property
    def side(
        self,
    ) -> str:
        """
        Return the canonical Order side.
        """

        return self.routing_order().side

    @property
    def quantity(
        self,
    ) -> float:
        """
        Return the canonical Order quantity.
        """

        return self.routing_order().quantity

    @property
    def decision_id(
        self,
    ) -> str:
        """
        Return the upstream portfolio decision identifier.
        """

        return self.execution_handoff.decision_id

    @property
    def regime(
        self,
    ) -> str:
        """
        Return the upstream regime identifier.
        """

        return self.execution_handoff.regime

    @property
    def authorization(
        self,
    ) -> Any:
        """
        Return the exact upstream authorization artifact.

        No authorization is created or modified here.
        """

        return self.execution_handoff.authorization

    @property
    def authorized(
        self,
    ) -> bool:
        """
        Return the authorization state preserved by the handoff.
        """

        return bool(
            getattr(
                self.authorization,
                "authorized",
                False,
            )
        )

    # ==================================================================
    # SERIALIZATION
    # ==================================================================

    def to_dict(
        self,
    ) -> dict[str, Any]:
        """
        Serialize complete routing handoff provenance.
        """

        self.validate()

        execution_handoff_to_dict = getattr(
            self.execution_handoff,
            "to_dict",
            None,
        )

        if not callable(
            execution_handoff_to_dict
        ):
            raise AuthorizedRoutingHandoffError(
                (
                    "AuthorizedExecutionHandoff does not expose "
                    "to_dict()."
                )
            )

        return {
            "execution_handoff":
                execution_handoff_to_dict(),

            "decision_id":
                self.decision_id,

            "regime":
                self.regime,

            "order_id":
                self.order_id,

            "ticker":
                self.ticker,

            "side":
                self.side,

            "quantity":
                self.quantity,

            "authorized":
                self.authorized,

            "api_version":
                self.API_VERSION,

            "phase":
                self.PHASE,
        }

    # ==================================================================
    # HEALTH
    # ==================================================================

    def health_check(
        self,
    ) -> bool:
        """
        Return the current routing handoff health state.
        """

        return self.validate()


# ======================================================================
# REGRESSION TEST
# ======================================================================


def test_authorized_routing_handoff() -> None:
    """
    Minimal standalone contract test.

    Full regression coverage belongs in the dedicated
    test_phase_iv_i_authorized_routing_handoff.py module.
    """

    assert (
        AuthorizedRoutingHandoff.API_VERSION
        == "1.0.0"
    )

    assert (
        AuthorizedRoutingHandoff.PHASE
        == "PHASE IV-I-G"
    )


# ======================================================================
# MODULE ENTRY POINT
# ======================================================================


if __name__ == "__main__":
    test_authorized_routing_handoff()

    print(
        "PHASE IV-I-G AUTHORIZED ROUTING HANDOFF "
        "CONTRACT TESTS PASSED."
    )