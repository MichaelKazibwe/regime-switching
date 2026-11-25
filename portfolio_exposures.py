"""Evidence-required look-through exposures; unknown holdings never imply diversification."""

from datetime import datetime
import math
from collections import defaultdict
from pathlib import Path

from strategy_integrity import file_hash, strict_json


def reviewed_evidence(root, decision_time):
    """Validate supplied private holdings and explicit review limits.

    Hashes demonstrate retained-file integrity, not issuer authenticity, data
    rights or independent approval. No evidence is downloaded or manufactured.
    """
    root = Path(root)
    if decision_time.tzinfo is None or root.is_symlink():
        raise ValueError("Aware cutoff and non-symlink evidence root required")
    manifest = root / "manifest.json"
    if manifest.is_symlink():
        raise ValueError("Evidence symlinks forbidden")
    data = strict_json(manifest)
    if data.get("schema_version") != 1 or data.get("execution_enabled") is not False:
        raise ValueError("Review-only holdings evidence required")
    records = data["records"]
    if not isinstance(records, dict) or len(records) > 10000:
        raise ValueError("Bounded holdings evidence required")
    hashes = {"manifest.json": file_hash(manifest)}
    for record in records.values():
        name = record["source_file"]
        if not isinstance(name, str) or Path(name).name != name or name in {"", ".", "..", "manifest.json"}:
            raise ValueError("Local evidence basename required")
        path = root / name
        if path.is_symlink() or file_hash(path) != record["source_sha256"]:
            raise ValueError("Holdings source checksum mismatch")
        for key in ("available_at", "reviewed_at"):
            stamp = datetime.fromisoformat(record[key].replace("Z", "+00:00"))
            if stamp.tzinfo is None or stamp > decision_time:
                raise ValueError("Holdings evidence must be available and reviewed by cutoff")
        if not isinstance(record["reviewer"], str) or not record["reviewer"].strip():
            raise ValueError("Identified holdings reviewer required")
        hashes[name] = record["source_sha256"]
    # Validate the declared policy even for an empty/all-cash portfolio.
    assess_exposures({}, {}, decision_time.date(), limits=data["limits"],
                     minimum_coverage=data["minimum_coverage"], max_age_days=data["max_age_days"])
    return dict(records=records, limits=data["limits"],
                minimum_coverage=data["minimum_coverage"], max_age_days=data["max_age_days"],
                source_hashes=hashes, cutoff=decision_time.isoformat(),
                authority="SUPPLIED_REVIEWED_FILES_NOT_INDEPENDENT_AUTHENTICATION",
                execution_enabled=False)


def assess_exposures(
    weights, records, as_of, *, limits=None, minimum_coverage=0.95, max_age_days=45
):
    date = datetime.fromisoformat(str(as_of)).date()
    if (
        not 0 < minimum_coverage <= 1
        or not isinstance(max_age_days, int)
        or not 1 <= max_age_days <= 366
    ):
        raise ValueError("Bounded exposure coverage and freshness required")
    if limits is None:
        limits = dict(issuer=0.15, country=0.65, currency=0.80, sector=0.35)
    if set(limits) != {"issuer", "country", "currency", "sector"} or any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
        or not 0 < v <= 1 for v in limits.values()
    ):
        raise ValueError("Explicit look-through concentration limits required")
    totals = {k: defaultdict(float) for k in limits}
    coverage = 0.0
    unknown = []
    if (
        any(
            isinstance(w, bool) or not math.isfinite(w) or w < 0
            for w in weights.values()
        )
        or sum(weights.values()) > 1 + 1e-9
    ):
        raise ValueError("Finite long-only portfolio capital weights required")
    risky = sum(w for s, w in weights.items() if s != "USD_CASH")
    for symbol, weight in weights.items():
        if symbol == "USD_CASH" or weight == 0:
            continue
        evidence = records.get(symbol)
        if not evidence:
            unknown.append(symbol)
            continue
        observed = datetime.fromisoformat(evidence["as_of"]).date()
        if (
            not evidence.get("source_sha256")
            or not evidence.get("reviewer")
            or not 0 <= (date - observed).days <= max_age_days
        ):
            unknown.append(symbol)
            continue
        rows = evidence["constituents"]
        if (
            not rows
            or any(not math.isfinite(r["weight"]) or r["weight"] < 0 for r in rows)
            or abs(sum(r["weight"] for r in rows) - 1) > 1e-6
        ):
            raise ValueError(
                "Complete nonnegative normalized look-through holdings required"
            )
        for row in rows:
            for key in limits:
                if not row.get(key):
                    raise ValueError(
                        "Each constituent needs issuer, country, economic currency and sector"
                    )
                totals[key][row[key]] += weight * row["weight"]
        coverage += weight
    fraction = coverage / risky if risky > 0 else 1.0
    breaches = [
        dict(dimension=k, exposure=name, weight=value, limit=limits[k])
        for k, values in totals.items()
        for name, value in values.items()
        if value > limits[k] + 1e-9
    ]
    status = (
        "PASS" if fraction >= minimum_coverage and not breaches else "REJECT_OR_REVIEW"
    )
    return dict(
        status=status,
        covered_risky_fraction=fraction,
        unknown_symbols=unknown,
        exposures={k: dict(v) for k, v in totals.items()},
        breaches=breaches,
        execution_qualified=False,
        assumptions="Economic exposures require supplied reviewed holdings; listing currency/country is not substituted.",
    )
