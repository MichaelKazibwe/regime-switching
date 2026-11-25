"""One portfolio context and semantic comparisons; no account or trade authority.

Callers supply verified weekly artifacts. Historical artifacts are checked against
their own seals, never recalculated using today's model.
"""

from datetime import date, datetime
from pathlib import Path
import math

from strategy_integrity import fingerprint, strict_json
from research_publisher import historical_weekly_session


def _stamp(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Aware research generation time required")
    return stamp


def proposal_weights(candidate):
    rows = candidate["allocations"]
    weights = {}
    for row in rows:
        value = row["weight"]
        if (row["symbol"] in weights or isinstance(value, bool)
                or not isinstance(value, (int, float)) or not math.isfinite(value)
                or value < 0):
            raise ValueError("Unique finite nonnegative portfolio weights required")
        weights[row["symbol"]] = float(value)
    if abs(sum(weights.values())-1) > 1e-8:
        raise ValueError("Portfolio capital must reconcile")
    return weights


def review_target(research, horizon):
    return dict(recommendation_id=research["research_id"]+":"+horizon,
                mandate=research["candidates"][horizon]["policy"],
                as_of=research["market_session"], release={"release_id":research["research_id"]},
                allocation=research["candidates"][horizon])


def context(research, horizon, source_hashes, market_session):
    if (not source_hashes or research.get("execution_enabled") is not False
            or research.get("promotion_enabled") is not False):
        raise ValueError("Verified review-only research sources required")
    candidate = research["candidates"][horizon]
    weights = proposal_weights(candidate)
    if any(not math.isfinite(r["risk_share"]) for r in candidate["allocations"]):
        raise ValueError("Finite signed variance contributions required")
    price_date = date.fromisoformat(research["market_session"])
    if date.fromisoformat(market_session) < price_date:
        raise ValueError("Market context cannot predate decision prices")
    _stamp(research["generated_at"])
    model_id = fingerprint(dict(sources=source_hashes, policy=candidate["policy"]))
    portfolio_id = "weekly:" + horizon
    basis = dict(
        portfolio_id=portfolio_id, kind="RESEARCH_PROPOSAL", revision=research["research_id"],
        model_id=model_id, price_as_of=price_date.isoformat(), context_as_of=market_session,
        generated_at=research["generated_at"], currency="USD",
        horizon_weeks=candidate["policy"]["weeks"], metric_basis="ADJUSTED_WEEKLY_RETURNS",
        cost_basis="15_BPS_RISKY_TURNOVER_ZERO_RESIDUAL_CASH_YIELD_NO_TAX",
        benchmark_id="OPTIONAL_SPY_60_IEF_40", approval_state="RESEARCH_REVIEW_REQUIRED",
        execution_enabled=False,
    )
    basis["context_id"] = fingerprint(basis)
    return dict(
        context=basis, title=candidate["policy"]["label"], horizon=horizon,
        review_revision=fingerprint(review_target(research, horizon)),
        allocations=candidate["allocations"], weights=weights,
        asset_count=sum(w > 0 for s, w in weights.items() if s != "USD_CASH"),
        cash=weights.get("USD_CASH", 0.), estimated_volatility=candidate["estimated_volatility"],
        effective_holdings=candidate["effective_holdings"], group_weights=candidate["group_weights"],
        replay=dict(kind="CAUSAL_RESEARCH_REPLAY", **candidate["replay"]),
        projections=dict(kind="UNCALIBRATED_CONDITIONAL_SCENARIOS", periods=candidate["projections"]),
        shocks=candidate["declared_shocks"], strategy_mix=candidate.get("strategy_mix"),
        exposure_evidence=candidate.get("economic_exposures", dict(
            status="NOT_SUPPLIED", covered_risky_fraction=None, execution_qualified=False)),
        account_performance=None,
        limitations=research["limitations"], methodology=research["methodology"],
    )


def compare(current, previous):
    """Target-to-target differences; never executable orders or realized turnover."""
    a, b = current["context"], previous["context"]
    if any(a[key] != b[key] for key in ("portfolio_id", "model_id", "currency", "metric_basis")):
        return dict(status="INCOMPARABLE_POLICY_OR_SCOPE", changes=[], execution_enabled=False)
    if (_stamp(b["generated_at"]) >= _stamp(a["generated_at"])
            or b["price_as_of"] > a["price_as_of"]):
        raise ValueError("Prior comparison must precede the current research artifact")
    changes = [
        dict(symbol=s, previous_weight=previous["weights"].get(s, 0.),
             proposed_weight=current["weights"].get(s, 0.),
             delta=current["weights"].get(s, 0.)-previous["weights"].get(s, 0.))
        for s in sorted(set(current["weights"]) | set(previous["weights"]))
        if abs(current["weights"].get(s, 0.)-previous["weights"].get(s, 0.)) >= 1e-6
    ]
    return dict(
        status="ALLOCATION_CHANGED" if changes else "UNCHANGED_ALLOCATION",
        previous_revision=b["revision"], previous_price_as_of=b["price_as_of"],
        changes=sorted(changes, key=lambda r: -abs(r["delta"])),
        risk_estimate_changed=abs(current["estimated_volatility"]-previous["estimated_volatility"]) > 1e-8,
        meaning="Proposed target weights versus prior proposed targets; not held positions, orders or realized trades",
        execution_enabled=False,
    )


def workspace(research, source_hashes, market_session, *, archive_root=None):
    portfolios = {k: context(research, k, source_hashes, market_session) for k in research["candidates"]}
    for value in portfolios.values():
        value["comparison"] = dict(status="NO_COMPARABLE_PRIOR_VERSION", changes=[], execution_enabled=False)
    rejected = 0
    prior = []
    if archive_root:
        root = Path(archive_root)
        if root.is_symlink():
            raise ValueError("Archive directory symlinks forbidden")
        # A bounded read; timestamps inside verified artifacts determine order.
        directories = sorted((p for p in root.iterdir() if p.is_dir()),
                             key=lambda p: p.stat().st_mtime, reverse=True)[:64]
        for directory in directories:
            if directory.name == research["research_id"]:
                continue
            if directory.is_symlink() or len(directory.name) != 64 or any(c not in "0123456789abcdef" for c in directory.name):
                continue
            try:
                if any((directory/name).is_symlink() for name in (
                        "manifest.json", "recommendations.json", "dashboard-report.pdf")):
                    raise ValueError("Archive artifact symlinks forbidden")
                historical_weekly_session(directory)
                data = strict_json(directory/"recommendations.json")
                if (data["research_id"] != directory.name
                        or _stamp(data["generated_at"]) >= _stamp(research["generated_at"])
                        or data["market_session"] > research["market_session"]):
                    continue
                manifest = strict_json(directory/"manifest.json")
                prior.append((data, manifest["source_hashes"]))
            except (OSError, ValueError, KeyError, TypeError):
                rejected += 1
        prior.sort(key=lambda item: _stamp(item[0]["generated_at"]), reverse=True)
        for key, value in portfolios.items():
            for old, sources in prior:
                if key not in old["candidates"]:
                    continue
                older = context(old, key, sources, market_session)
                result = compare(value, older)
                if result["status"] != "INCOMPARABLE_POLICY_OR_SCOPE":
                    value["comparison"] = result
                    break
            if rejected and value["comparison"]["status"] == "NO_COMPARABLE_PRIOR_VERSION":
                value["comparison"]["status"] = "PRIOR_EVIDENCE_UNAVAILABLE"
    return dict(
        schema_version=1, status="RESEARCH_WORKSPACE", revision=research["research_id"],
        default_horizon="aggregate" if "aggregate" in portfolios else next(iter(portfolios)),
        portfolios=portfolios, archive_checks=dict(maximum_directories=64, rejected=rejected),
        qualification=dict(independent_model_advantage="NOT_ESTABLISHED",
                           public_recommendations=False, production_approval=False),
        catalogue=dict(
            model=dict(source_identity=fingerprint(source_hashes),
                       source_hashes=source_hashes, owner="UNASSIGNED",
                       independent_validation="NOT_SUPPLIED", promotion_enabled=False),
            datasets=dict(price_session=research["market_session"],
                          market_context_session=market_session,
                          input_evidence=research.get("input_evidence", {}),
                          rights_qualification="NOT_ESTABLISHED_BY_SOFTWARE_HASHES",
                          independent_securities_reconciliation="NOT_SUPPLIED")),
        execution_enabled=False,
    )
