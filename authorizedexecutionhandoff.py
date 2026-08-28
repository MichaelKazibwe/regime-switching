"""
======================================================================
authorizedexecutionhandoff.py

PHASE IV-I-F — AUTHORIZED EXECUTION HANDOFF

Institutional authorization-to-execution handoff contract.

This module establishes the controlled boundary between:

    AuthorizedOrderIntent
            ↓
    AuthorizedExecutionHandoff
            ↓
    ExecutionEngine / BrokerExecutionEngine

The handoff:

    - validates authorization provenance;
    - preserves exact Order identity;
    - preserves exact authorization identity;
    - preserves decision identity;
    - preserves regime identity;
    - remains immutable;
    - performs no execution;
    - performs no broker routing;
    - performs no portfolio mutation;
    - cannot enable live trading;
    - cannot enable broker submission.

It does NOT:

    - create authorization;
    - create orders;
    - submit orders;
    - route orders;
    - execute trades;
    - mutate PortfolioAccount state.

Author: Michael Kazibwe
======================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Any

from authorizedorderintent import (
    AuthorizedOrderIntent,
    AuthorizedOrderIntentError,
)
from order import Order


# ======================================================================
# EXCEPTIONS
# ======================================================================


class AuthorizedExecutionHandoffError(
    RuntimeError
):
    """
    Raised when an AuthorizedOrderIntent cannot safely cross
    the authorization-to-execution handoff boundary.
    """

    pass


# ======================================================================
# AUTHORIZED EXECUTION HANDOFF
# ======================================================================


@dataclass(frozen=True)
class AuthorizedExecutionHandoff:
    """
    Immutable execution handoff envelope.

    This object does not execute an order.

    It establishes that the canonical Order being handed downstream
    was validated through an AuthorizedOrderIntent.
    """

    order: Order

    authorization: Any

    decision_id: str

    regime: str

    API_VERSION: ClassVar[str] = "1.0.0"

    PHASE: ClassVar[str] = "PHASE IV-I-F"

    # ==================================================================
    # CONSTRUCTION
    # ==================================================================

    @classmethod
    def from_intent(
        cls,
        intent: AuthorizedOrderIntent,
    ) -> "AuthorizedExecutionHandoff":
        """
        Construct an execution handoff from a valid
        AuthorizedOrderIntent.

        No execution or routing occurs.
        """

        if not isinstance(
            intent,
            AuthorizedOrderIntent,
        ):
            raise AuthorizedExecutionHandoffError(
                (
                    "AuthorizedExecutionHandoff requires an "
                    "AuthorizedOrderIntent."
                )
            )

        try:
            intent.validate()

        except (
            AuthorizedOrderIntentError,
            TypeError,
            ValueError,
            RuntimeError,
        ) as exc:
            raise AuthorizedExecutionHandoffError(
                (
                    "AuthorizedOrderIntent failed validation "
                    "at the execution handoff boundary: "
                    f"{exc}"
                )
            ) from exc

        if not isinstance(
            intent.order,
            Order,
        ):
            raise AuthorizedExecutionHandoffError(
                "AuthorizedOrderIntent does not contain a canonical Order."
            )

        if intent.authorization is None:
            raise AuthorizedExecutionHandoffError(
                "AuthorizedOrderIntent has no authorization artifact."
            )

        handoff = cls(
            order=intent.order,
            authorization=intent.authorization,
            decision_id=intent.decision_id,
            regime=intent.regime,
        )

        handoff.validate()

        return handoff

    # ==================================================================
    # VALIDATION
    # ==================================================================

    def validate(
        self,
    ) -> bool:
        """
        Validate the complete execution handoff contract.
        """

        if not isinstance(
            self.order,
            Order,
        ):
            raise AuthorizedExecutionHandoffError(
                "Handoff order must be an Order."
            )

        if self.authorization is None:
            raise AuthorizedExecutionHandoffError(
                "Handoff authorization cannot be None."
            )

        if not isinstance(
            self.decision_id,
            str,
        ) or not self.decision_id:
            raise AuthorizedExecutionHandoffError(
                "Handoff decision_id must be non-empty."
            )

        if not isinstance(
            self.regime,
            str,
        ) or not self.regime:
            raise AuthorizedExecutionHandoffError(
                "Handoff regime must be non-empty."
            )

        authorization_decision_id = getattr(
            self.authorization,
            "decision_id",
            None,
        )

        if authorization_decision_id != self.decision_id:
            raise AuthorizedExecutionHandoffError(
                (
                    "Handoff decision_id does not match "
                    "authorization decision_id."
                )
            )

        authorization_regime = getattr(
            self.authorization,
            "regime",
            None,
        )

        if authorization_regime != self.regime:
            raise AuthorizedExecutionHandoffError(
                (
                    "Handoff regime does not match "
                    "authorization regime."
                )
            )

        authorized = getattr(
            self.authorization,
            "authorized",
            False,
        )

        if not authorized:
            raise AuthorizedExecutionHandoffError(
                "Execution handoff requires authorized=True."
            )

        status = getattr(
            self.authorization,
            "status",
            None,
        )

        status_name = getattr(
            status,
            "name",
            status,
        )

        if status_name != "AUTHORIZED":
            raise AuthorizedExecutionHandoffError(
                (
                    "Execution handoff requires AUTHORIZED "
                    f"authorization status; received {status}."
                )
            )

        if getattr(
            self.authorization,
            "live_trading_enabled",
            False,
        ):
            raise AuthorizedExecutionHandoffError(
                "Live trading cannot be enabled at the execution handoff."
            )

        if getattr(
            self.authorization,
            "broker_submission_enabled",
            False,
        ):
            raise AuthorizedExecutionHandoffError(
                (
                    "Broker submission cannot be enabled "
                    "at the execution handoff."
                )
            )

        try:
            self.order.validate()

        except Exception as exc:
            raise AuthorizedExecutionHandoffError(
                (
                    "Canonical Order failed validation at "
                    f"execution handoff: {exc}"
                )
            ) from exc

        return True

    # ==================================================================
    # DOWNSTREAM ORDER ACCESS
    # ==================================================================

    def execution_order(
        self,
    ) -> Order:
        """
        Return the exact canonical Order for downstream execution.

        This method does not execute or route the order.
        """

        self.validate()

        return self.order

    # ==================================================================
    # PROVENANCE
    # ==================================================================

    @property
    def order_id(
        self,
    ) -> str:
        return self.order.order_id

    @property
    def ticker(
        self,
    ) -> str:
        return self.order.ticker

    @property
    def side(
        self,
    ) -> str:
        return self.order.side

    @property
    def quantity(
        self,
    ) -> float:
        return self.order.quantity

    @property
    def authorized(
        self,
    ) -> bool:
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
        Serialize complete handoff provenance.
        """

        self.validate()

        authorization_to_dict = getattr(
            self.authorization,
            "to_dict",
            None,
        )

        if not callable(
            authorization_to_dict
        ):
            raise AuthorizedExecutionHandoffError(
                "Authorization artifact does not expose to_dict()."
            )

        return {
            "order": self.order.to_dict(),
            "authorization": authorization_to_dict(),
            "decision_id": self.decision_id,
            "regime": self.regime,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
        }

    # ==================================================================
    # HEALTH
    # ==================================================================

    def health_check(
        self,
    ) -> bool:
        return self.validate()


# ======================================================================
# REGRESSION TEST
# ======================================================================


def test_authorized_execution_handoff() -> None:
    """
    Minimal standalone contract test.

    Full regression coverage belongs in the dedicated
    test_phase_iv_i_authorized_execution_handoff.py module.
    """

    assert AuthorizedExecutionHandoff.API_VERSION == "1.0.0"

    assert AuthorizedExecutionHandoff.PHASE == (
        "PHASE IV-I-F"
    )


if __name__ == "__main__":
    test_authorized_execution_handoff()

    print(
        "PHASE IV-I-F AUTHORIZED EXECUTION HANDOFF "
        "CONTRACT TESTS PASSED."
    )
