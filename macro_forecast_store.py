"""Preserve issued probabilities exactly across equivalent platform recalculations."""

import os
from datetime import date
from pathlib import Path

from macro_alpha import build as calculate
from strategy_integrity import strict_json, fingerprint, numerically_equivalent


def retain_issued(result, state_root):
    session, protocol = result["market_session"], result["protocol_id"]
    date.fromisoformat(session)
    if len(protocol) != 64 or any(c not in "0123456789abcdef" for c in protocol):
        raise ValueError("Valid forecast protocol required")
    path = Path(state_root) / f"{session}-{protocol}.json"
    if not path.exists():
        return result
    if path.is_symlink():
        raise ValueError("Issued forecast symlinks forbidden")
    prior = strict_json(path)["forecast"]
    prior_body = {k: v for k, v in prior.items() if k != "forecast_id"}
    body = {k: v for k, v in result.items() if k != "forecast_id"}
    if (
        fingerprint(prior_body) != prior["forecast_id"]
        or fingerprint(body) != result["forecast_id"]
    ):
        raise ValueError("Issued forecast integrity mismatch")
    if not numerically_equivalent(body, prior_body):
        raise ValueError(
            "Issued forecast evidence differs; an explicit protocol migration is required"
        )
    # The original issued bytes/probabilities retain authority for this origin.
    # This never rewrites, averages or substitutes a new forecast identity.
    return prior


def build(capture, training, *, state_root=None):
    return retain_issued(
        calculate(capture, training),
        state_root or os.environ.get("PILOT_MACRO_ALPHA_STATE_ROOT", "var/macro-alpha"),
    )
