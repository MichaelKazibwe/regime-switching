"""Observable high-water mark and gradual reductions with explicit re-entry.

Recommendation controls only. This does not guarantee a loss bound or authorize
trading. Operational incidents freeze new recommendations for operator review.
"""

from dataclasses import asdict, dataclass
import math


@dataclass
class RecommendationRiskState:
    peak: float = 1.0
    last_session: str | None = None
    recovery_confirmations: int = 0
    exposure_multiplier: float = 1.0
    review_required: bool = False
    prior_breach: bool = False
    last_equity: float | None = None
    last_drawdown: float = 0.0
    last_review: dict | None = None

    def update(
        self,
        equity,
        session,
        *,
        loss_preference,
        trend_confirmed,
        operational_incident=False,
    ):
        from datetime import date

        date.fromisoformat(session)
        if (
            isinstance(equity, bool)
            or isinstance(loss_preference, bool)
            or not math.isfinite(equity)
            or equity <= 0
            or (loss_preference is not None and not 0 < loss_preference <= 1)
            or not isinstance(trend_confirmed, bool)
            or not isinstance(operational_incident, bool)
        ):
            raise ValueError("Invalid risk observation")
        if self.last_session and session < self.last_session:
            raise ValueError("Out-of-order risk session")
        if self.last_session == session:
            if self.last_equity != equity:
                raise ValueError("Conflicting same-session valuation")
            return self.payload()
        self.peak = max(self.peak, equity)
        drawdown = equity / self.peak - 1
        if loss_preference is None:
            self.review_required = self.review_required or operational_incident
            if not self.review_required:
                self.exposure_multiplier = 1.0
            self.recovery_confirmations = 0
        else:
            self.prior_breach = self.prior_breach or drawdown < -loss_preference
            self.review_required = (
                self.review_required
                or operational_incident
                or drawdown < -loss_preference
            )
            desired = max(0.10, min(1.0, 1 + drawdown / max(loss_preference, 0.001)))
            if (
                desired < self.exposure_multiplier
                and drawdown < self.last_drawdown - 1e-12
            ):
                self.exposure_multiplier = desired
                self.recovery_confirmations = 0
            elif trend_confirmed and not self.review_required:
                self.recovery_confirmations += 1
                if self.recovery_confirmations >= 5:
                    self.exposure_multiplier = min(1.0, self.exposure_multiplier + 0.05)
                    self.recovery_confirmations = 0
            else:
                self.recovery_confirmations = 0
        self.last_session = session
        self.last_equity = float(equity)
        self.last_drawdown = float(drawdown)
        return {**self.payload(), "observed_drawdown": drawdown}

    def payload(self):
        return asdict(self)

    def acknowledge_review(
        self, reviewer, evidence_sha256, session, *, loss_preference
    ):
        from datetime import date
        import re

        date.fromisoformat(session)
        if (
            not reviewer.strip()
            or not re.fullmatch("[0-9a-f]{64}", evidence_sha256)
            or self.last_session is None
            or session < self.last_session
            or not 0 < loss_preference <= 1
            or self.last_drawdown < -loss_preference
        ):
            raise ValueError(
                "Risk review needs evidence and a recovered account within its loss preference"
            )
        self.last_review = {
            "reviewer": reviewer,
            "evidence_sha256": evidence_sha256,
            "session": session,
        }
        self.review_required = False
        self.recovery_confirmations = 0
        return self.payload()

    @classmethod
    def restore(cls, payload):
        obj = cls(**payload)
        if (
            isinstance(obj.peak, bool)
            or isinstance(obj.exposure_multiplier, bool)
            or not math.isfinite(obj.peak)
            or obj.peak <= 0
            or not math.isfinite(obj.exposure_multiplier)
            or not 0.1 <= obj.exposure_multiplier <= 1
            or not isinstance(obj.recovery_confirmations, int)
            or isinstance(obj.recovery_confirmations, bool)
            or not 0 <= obj.recovery_confirmations < 5
            or not isinstance(obj.review_required, bool)
            or not isinstance(obj.prior_breach, bool)
        ):
            raise ValueError("Invalid saved risk state")
        if obj.last_session:
            from datetime import date

            date.fromisoformat(obj.last_session)
        if (
            not math.isfinite(obj.last_drawdown)
            or not -1 <= obj.last_drawdown <= 0
            or obj.last_equity is not None
            and (not math.isfinite(obj.last_equity) or obj.last_equity <= 0)
        ):
            raise ValueError("Invalid saved valuation state")
        if obj.last_review is not None:
            import re

            if (
                not isinstance(obj.last_review, dict)
                or set(obj.last_review) != {"reviewer", "evidence_sha256", "session"}
                or not obj.last_review["reviewer"].strip()
                or not re.fullmatch("[0-9a-f]{64}", obj.last_review["evidence_sha256"])
            ):
                raise ValueError("Invalid saved risk review")
        return obj
