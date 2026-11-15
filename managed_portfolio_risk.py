"""Pre-dispatch whole-account risk envelope from server-owned measured inputs."""

from datetime import datetime
from pathlib import Path
from decimal import Decimal
import hashlib
from copy import deepcopy
from managed_accounts import amount
import numpy as np
import pandas as pd

from portfolio_risk_envelope import assess
from economic_evidence import verify, portfolio_review
from strategy_integrity import fingerprint, strict_json
from strategy_training_data import usable_session


def review(request, provider, permit, now):
    if provider is None:
        raise PermissionError("Whole-account portfolio risk provider required")
    bound_request = fingerprint(request)
    doc = deepcopy(provider(deepcopy(request)))
    stamp = datetime.fromisoformat(doc["as_of"])
    if stamp.tzinfo is None or not 0 <= (now - stamp).total_seconds() <= 30:
        raise PermissionError("Whole-account market evidence stale")
    if doc["request_sha256"] != bound_request:
        raise PermissionError("Whole-account request/account binding mismatch")
    policy, exposures = (
        permit["portfolio_risk_limits"],
        permit["portfolio_exposure_limits"],
    )
    fraction_keys = (
        "unhedged_fx_ceiling",
        "maximum_country_weight",
        "maximum_underlying_weight",
        "maximum_adv_fraction",
    )
    if (
        any(
            isinstance(exposures[k], bool)
            or not np.isfinite(exposures[k])
            or not 0 < exposures[k] <= 1
            for k in fraction_keys
        )
        or not 0 < exposures["portfolio_duration_ceiling"] <= 40
    ):
        raise PermissionError("Reviewed measured-exposure limits required")
    cash = request["cash"]
    currency = request["proposed"]["currency"]
    if any(c != currency and float(v) != 0 for c, v in cash.items()):
        raise PermissionError(
            "Cross-currency valuation requires a qualified FX release"
        )
    values, quantities = {}, {}
    for instrument, position in request["positions"].items():
        if position["currency"] != currency:
            raise PermissionError("Unqualified cross-currency position")
        quantities[instrument] = float(position["quantity"])
    intents = [o for o in request["pending"] if o["client_id"] != request["client_id"]]
    all_orders = [*intents, request["proposed"]]
    daily_limit = amount(permit["max_daily_notional"])
    daily_usage = Decimal(request["traded_today"]) + sum(
        (Decimal(o["notional"]) for o in all_orders), Decimal(0)
    )
    if not daily_limit.is_finite() or daily_limit <= 0 or daily_usage > daily_limit:
        raise PermissionError("Daily filled plus pending notional cap")
    instruments = set(quantities) | {o["instrument_id"] for o in all_orders}
    for instrument in instruments:
        mark = doc["marks"][instrument]
        marked_at = datetime.fromisoformat(mark["as_of"])
        if marked_at.tzinfo is None or not 0 <= (now - marked_at).total_seconds() <= 30:
            raise PermissionError("Held or pending instrument mark stale")
        if (
            mark["currency"] != currency
            or not mark.get("source")
            or isinstance(mark["price_per_share"], bool)
            or not np.isfinite(mark["price_per_share"])
            or mark["price_per_share"] <= 0
        ):
            raise ValueError("Verified account-currency per-share marks required")
        values[instrument] = quantities.get(instrument, 0) * mark["price_per_share"]
    nav = sum(values.values()) + float(cash.get(currency, 0))
    if not np.isfinite(nav) or nav <= 0:
        raise PermissionError("Positive marked account NAV required")
    weights, pending = {}, {}
    for instrument, value in values.items():
        s = doc["marks"][instrument]["symbol"]
        weights[s] = weights.get(s, 0) + value / nav
    for order in intents:
        if order["currency"] != currency:
            raise PermissionError("Unqualified pending FX exposure")
        if order["side"] == "BUY":
            s = doc["marks"][order["instrument_id"]]["symbol"]
            pending[s] = (
                pending.get(s, 0)
                + max(
                    float(order["notional"]),
                    float(order["quantity"])
                    * doc["marks"][order["instrument_id"]]["price_per_share"],
                )
                / nav
            )
    proposed = request["proposed"]
    s = doc["marks"][proposed["instrument_id"]]["symbol"]
    size = (
        max(
            float(proposed["notional"]),
            float(proposed["quantity"])
            * doc["marks"][proposed["instrument_id"]]["price_per_share"],
        )
        / nav
    )
    before = {
        s: weights.get(s, 0) + pending.get(s, 0) for s in set(weights) | set(pending)
    }
    after = dict(before)
    after[s] = after.get(s, 0) + (
        size
        if proposed["side"] == "BUY"
        else -float(proposed["quantity"])
        * doc["marks"][proposed["instrument_id"]]["price_per_share"]
        / nav
    )
    history = doc["returns"]
    if not isinstance(history, pd.DataFrame):
        raise ValueError("Observed whole-account risk history required")
    if not isinstance(history.index, pd.DatetimeIndex) or history.index[
        -1
    ] != usable_session(now):
        raise PermissionError("Completed historical risk sessions required")
    checks = assess(after, history, limits=policy)
    old = assess(before, history, limits=policy)
    reducing = proposed["side"] == "SELL" and all(
        checks["metrics"][k] <= old["metrics"][k] + 1e-8 for k in checks["breaches"]
    )
    if checks["status"] == "REJECT" and not reducing:
        raise PermissionError("Whole-account statistical risk envelope breached")
    symbols = [s for s, w in after.items() if w > 0]
    evidence = verify(doc.get("evidence_root"), symbols, history.index, now=now)
    if not all(evidence["checks"].values()):
        raise PermissionError("Verified portfolio financial/exposure evidence required")
    measured = portfolio_review(
        {s: after[s] for s in symbols}, exposures, evidence, doc["evidence_root"]
    )
    if measured["status"] != "LOCAL_EXPOSURE_LIMIT_REVIEW_PASS":
        raise PermissionError("Measured duration/FX envelope breached")
    holdings = strict_json(Path(doc["evidence_root"]) / "exposures.json")["instruments"]
    countries, issuers = {}, {}
    for symbol in symbols:
        for key, result in (
            ("country_weights", countries),
            ("underlying_weights", issuers),
        ):
            distribution = holdings[symbol][key]
            fractions = list(distribution.values())
            if (
                not fractions
                or any(
                    isinstance(v, bool) or not np.isfinite(v) or v < 0
                    for v in fractions
                )
                or not np.isclose(sum(fractions), 1, atol=0.01)
            ):
                raise PermissionError(
                    "Complete measured holdings/country coverage required"
                )
            for k, v in distribution.items():
                result[k] = result.get(k, 0) + after[symbol] * v
        adv = holdings[symbol]["average_daily_notional"]
        if isinstance(adv, bool) or not np.isfinite(adv) or adv <= 0:
            raise PermissionError("Verified liquidity capacity required")
        participation = (
            sum(
                float(o["notional"])
                for o in all_orders
                if doc["marks"][o["instrument_id"]]["symbol"] == symbol
            )
            / adv
        )
        if participation > exposures["maximum_adv_fraction"]:
            raise PermissionError("Order exceeds measured ADV participation")
    if (
        max(countries.values(), default=0) > exposures["maximum_country_weight"]
        or max(issuers.values(), default=0) > exposures["maximum_underlying_weight"]
    ):
        raise PermissionError("Overlapping country/underlying exposure cap")
    return dict(
        request_sha256=fingerprint(request),
        as_of=doc["as_of"],
        marks_sha256=fingerprint(doc["marks"]),
        risk_history_sha256=hashlib.sha256(history.to_csv().encode()).hexdigest(),
        financial_evidence=evidence["details"],
        statistical=checks,
        measured=measured,
        countries=countries,
        underlyings=issuers,
        status="LOCAL_ACCOUNT_RISK_CHECK_PASS",
        execution_enabled=False,
    )
