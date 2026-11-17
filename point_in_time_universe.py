"""Point-in-time membership adapter; missing vendor evidence stays unqualified."""

from datetime import datetime
import re


def eligible_at(events, session, decision_time):
    decision = datetime.fromisoformat(decision_time.replace("Z", "+00:00"))
    if decision.tzinfo is None:
        raise ValueError("Aware membership decision timestamp required")
    session = datetime.fromisoformat(session).date()
    known = {}
    for event in events:
        effective = datetime.fromisoformat(event["effective_date"]).date()
        available = datetime.fromisoformat(event["available_at"].replace("Z", "+00:00"))
        if (
            available.tzinfo is None
            or event["action"] not in {"ADMIT", "REMOVE"}
            or not event.get("permanent_id")
            or not event.get("source")
            or not re.fullmatch("[0-9a-f]{64}", event["source_sha256"])
            or event.get("rights_reviewed") is not True
        ):
            raise ValueError("Reviewed point-in-time membership evidence required")
        if available > decision or effective > session:
            continue
        key = event["permanent_id"]
        previous = known.get(key)
        order = (effective, available)
        if previous and previous[0] == order and previous[1] != event:
            raise ValueError("Conflicting membership events")
        if not previous or order > previous[0]:
            known[key] = (order, event)
    eligible = sorted(
        v[1]["symbol"] for v in known.values() if v[1]["action"] == "ADMIT"
    )
    if len(eligible) != len(set(eligible)):
        raise ValueError("Ambiguous permanent-ID to symbol membership")
    return dict(
        status="OBSERVED_MEMBERSHIP" if known else "PIT_MEMBERSHIP_UNAVAILABLE",
        eligible_symbols=eligible,
        observed_identities=len(known),
        coverage_certified=False,
        execution_qualified=False,
    )


def corporate_action_return(
    before, after, *, shares_per_old_share=1.0, cash_per_old_share=0.0
):
    """Auditable split/cash arithmetic; provider event authenticity is a separate gate."""
    import math

    values = [before, after, shares_per_old_share, cash_per_old_share]
    if (
        any(isinstance(v, bool) or not math.isfinite(v) for v in values)
        or min(before, shares_per_old_share) <= 0
        or min(after, cash_per_old_share) < 0
    ):
        raise ValueError(
            "Explicit finite corporate-action prices, share ratio and cash required"
        )
    return (after * shares_per_old_share + cash_per_old_share) / before - 1
