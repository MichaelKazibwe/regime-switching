"""Reviewed broker execution evidence to shortfall/latency diagnostics; no orders."""

from datetime import datetime
from pathlib import Path
import numpy as np
from executionanalytics import ExecutionAnalytics
from strategy_integrity import strict_json, file_hash, canonical


def number(value, *, positive=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not np.isfinite(value)
        or value < 0
        or positive
        and value == 0
    ):
        raise ValueError("Finite measured execution number required")
    return float(value)


def stamp(value, now):
    t = datetime.fromisoformat(value)
    if t.tzinfo is None or t > now:
        raise ValueError("Aware, nonfuture execution clock required")
    return t


def analyze(path=None, *, now):
    if path is None:
        return dict(
            status="UNAVAILABLE_NO_BROKER_EVIDENCE",
            orders=0,
            live_performance_verified=False,
        )
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Regular execution evidence required")
    d = strict_json(path)
    if (
        d["mode"] not in {"BROKER_PAPER", "BROKER_LIVE"}
        or d.get("verified") is not True
        or not d.get("reviewer")
        or d.get("reconciliation_status") != "MATCHED"
        or not d.get("raw_files")
    ):
        raise ValueError("Reviewed reconciled broker evidence required")
    stamp(d["as_of"], now)
    for entry in d["raw_files"]:
        f = path.parent / entry["file"]
        if (
            Path(entry["file"]).name != entry["file"]
            or f.is_symlink()
            or file_hash(f) != entry["sha256"]
        ):
            raise ValueError("Broker evidence hash mismatch")
    orders = {}
    for o in d["orders"]:
        key = (o["tenant"], o["account"], o["order_id"])
        if key in orders:
            raise ValueError("Duplicate broker order identity")
        if o["side"] not in {"BUY", "SELL"}:
            raise ValueError("Known order side required")
        number(o["quantity"], positive=True)
        number(o["arrival_price"], positive=True)
        if stamp(o["arrival_at"], now) > stamp(o["submitted_at"], now):
            raise ValueError("Arrival after submission")
        orders[key] = o
    grouped = {key: [] for key in orders}
    seen = {}
    for f in d["fills"]:
        key = (f["tenant"], f["account"], f["order_id"])
        identity = (*key, f["fill_id"])
        if identity in seen:
            if seen[identity] != canonical(f):
                raise ValueError("Conflicting execution event")
            continue
        seen[identity] = canonical(f)
        if key not in orders:
            raise ValueError("Unexplained broker fill")
        o = orders[key]
        for k in ("quantity", "price"):
            number(f[k], positive=True)
        number(f["fee"])
        if f["currency"] != o["currency"]:
            raise ValueError("Measured fee/quote FX conversion required")
        if (
            not stamp(o["submitted_at"], now)
            <= stamp(f["executed_at"], now)
            <= stamp(f["received_at"], now)
        ):
            raise ValueError("Invalid broker fill clocks")
        grouped[key].append(f)
    analytics = ExecutionAnalytics()
    results = []
    for key, o in orders.items():
        fills = grouped[key]
        quantity = sum(f["quantity"] for f in fills)
        if quantity > o["quantity"] + 1e-9:
            raise ValueError("Excess execution quantity")
        arrival = o["arrival_price"]
        unit = number(o.get("quote_to_currency", 1), positive=True)
        fees = sum(f["fee"] for f in fills)
        vwap = (
            sum(f["quantity"] * f["price"] for f in fills) / quantity
            if quantity
            else None
        )
        price_cost = (
            analytics.calculate_implementation_shortfall(
                o["side"], arrival, vwap, quantity
            )[0]
            * unit
            if quantity
            else None
        )
        denominator = arrival * quantity * unit
        shortfall = price_cost + fees if quantity else None
        ack = None
        if o.get("ack_at"):
            ack = (
                stamp(o["ack_at"], now) - stamp(o["submitted_at"], now)
            ).total_seconds()
            if ack < 0:
                raise ValueError("Negative acknowledgement latency")
        modeled = number(o.get("modeled_cost_bps", 15))
        results.append(
            dict(
                order_id=o["order_id"],
                currency=o["currency"],
                side=o["side"],
                filled=quantity,
                fill_ratio=quantity / o["quantity"],
                vwap=vwap,
                fees=fees,
                arrival_notional=denominator,
                realized_filled_shortfall=shortfall,
                shortfall_bps=shortfall / denominator * 10000 if denominator else None,
                modeled_cost_bps=modeled,
                ack_seconds=ack,
                callback_seconds=[
                    (
                        stamp(f["received_at"], now) - stamp(f["executed_at"], now)
                    ).total_seconds()
                    for f in fills
                ],
            )
        )
    currencies = {}
    for currency in sorted({r["currency"] for r in results}):
        rows = [r for r in results if r["currency"] == currency and r["filled"] > 0]
        notional = sum(r["arrival_notional"] for r in rows)
        currencies[currency] = dict(
            executed_notional=notional,
            shortfall=sum(r["realized_filled_shortfall"] for r in rows),
            shortfall_bps=sum(r["realized_filled_shortfall"] for r in rows)
            / notional
            * 10000
            if notional
            else None,
            modeled_bps=sum(r["modeled_cost_bps"] * r["arrival_notional"] for r in rows)
            / notional
            if notional
            else None,
        )
    return dict(
        status="REVIEWED_BROKER_DIAGNOSTICS",
        mode=d["mode"],
        as_of=d["as_of"],
        evidence_sha256=file_hash(path),
        orders=len(results),
        rows=results,
        currencies=currencies,
        live_performance_verified=False,
        limitation="Filled shortfall includes explicit fees; unfilled opportunity cost, FX and taxes are unavailable, never assumed zero. Paper fills are not live execution performance.",
    )
