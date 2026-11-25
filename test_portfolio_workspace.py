from copy import deepcopy
from datetime import datetime, timezone

import pytest

from portfolio_workspace import context, compare, workspace
from review_workflow import record_decision, history
from strategy_integrity import fingerprint
from strategy_receipts import atomic_json


def research():
    candidate = dict(
        policy=dict(label="Balanced research", weeks=52),
        allocations=[dict(symbol="SPY", weight=.3, risk_share=1.),
                     dict(symbol="USD_CASH", weight=.7, risk_share=0.)],
        estimated_volatility=.1, effective_holdings=1.72,
        group_weights=dict(equity=.3, cash=.7), replay=dict(total_return=.02),
        projections={"52":dict(median_return=.03)}, declared_shocks={"Test":-.1})
    return dict(market_session="2026-11-13", generated_at="2026-11-18T22:00:00+00:00",
                research_id="a"*64, candidates={"aggregate":candidate},
                limitations=["Research only"], methodology="Test",
                execution_enabled=False, promotion_enabled=False)


def test_context_separates_prices_context_account_and_scenarios():
    r=research()
    c=context(r,"aggregate",{"source.py":"b"*64},"2026-11-18")
    assert c["context"]["price_as_of"]=="2026-11-13"
    assert c["context"]["context_as_of"]=="2026-11-18"
    assert c["account_performance"] is None
    assert c["replay"]["kind"] != c["projections"]["kind"]
    assert not c["context"]["execution_enabled"]
    with pytest.raises(ValueError,match="predate"):
        context(r,"aggregate",{"source.py":"b"*64},"2026-11-12")
    r["candidates"]["aggregate"]["allocations"].append(dict(symbol="SPY",weight=0.,risk_share=0.))
    with pytest.raises(ValueError,match="Unique"):
        context(r,"aggregate",{"source.py":"b"*64},"2026-11-18")


def test_same_weights_new_revision_is_not_a_rebalance_and_different_models_are_not_compared():
    r=research()
    old=deepcopy(r)
    old["generated_at"]="2026-11-17T22:00:00+00:00"
    old["research_id"]="c"*64
    c=context(r,"aggregate",{"source.py":"b"*64},"2026-11-18")
    p=context(old,"aggregate",{"source.py":"b"*64},"2026-11-18")
    assert compare(c,p)["status"]=="UNCHANGED_ALLOCATION"
    r["candidates"]["aggregate"]["allocations"][0]["weight"]=.4
    r["candidates"]["aggregate"]["allocations"][1]["weight"]=.6
    c=context(r,"aggregate",{"source.py":"b"*64},"2026-11-18")
    result=compare(c,p)
    assert result["status"]=="ALLOCATION_CHANGED"
    assert sum(row["delta"] for row in result["changes"])==pytest.approx(0)
    p["context"]["model_id"]="changed"
    assert compare(c,p)["status"]=="INCOMPARABLE_POLICY_OR_SCOPE"
    p["context"]=deepcopy(c["context"])
    with pytest.raises(ValueError,match="precede"):
        compare(c,p)


def test_workspace_never_fabricates_history():
    result=workspace(research(),{"source.py":"b"*64},"2026-11-18")
    row=result["portfolios"]["aggregate"]
    assert row["comparison"]["status"]=="NO_COMPARABLE_PRIOR_VERSION"
    assert row["account_performance"] is None
    assert not result["qualification"]["production_approval"]


def test_review_history_is_actor_scoped_and_rejects_tampering(tmp_path):
    target=dict(recommendation_id="proposal", mandate={"horizon":52}, as_of="2026-11-13",
                release={"release_id":"a"*64}, allocation={"USD_CASH":1.})
    record=record_decision(tmp_path,target,reviewer="alice",decision="CHANGES_REQUESTED",
                           rationale="Review underlying exposure coverage",expected_revision=fingerprint(target))
    assert history(tmp_path,reviewer="alice")[0]==record
    with pytest.raises(ValueError,match="integrity"):
        history(tmp_path,reviewer="bob")
    row={**record,"execution_enabled":True}
    atomic_json(tmp_path/(record["review_id"]+".json"),row)
    with pytest.raises(ValueError,match="integrity"):
        history(tmp_path,reviewer="alice",now=datetime(2027,1,1,tzinfo=timezone.utc))


def test_holdings_evidence_rejects_changed_sources_future_reviews_and_implicit_limits(tmp_path):
    from portfolio_exposures import reviewed_evidence
    from strategy_integrity import file_hash
    source=tmp_path/'issuer.json'
    source.write_text('{"fixture":true}')
    record=dict(source_file=source.name, source_sha256=file_hash(source), reviewer='Fixture reviewer',
                available_at='2026-11-17T12:00:00Z', reviewed_at='2026-11-18T12:00:00Z',
                as_of='2026-11-16', constituents=[])
    manifest=dict(schema_version=1, execution_enabled=False, records={'ETF':record},
                  limits=dict(issuer=.15,country=.65,currency=.8,sector=.35),
                  minimum_coverage=.95,max_age_days=45)
    atomic_json(tmp_path/'manifest.json',manifest)
    cutoff=datetime(2026,11,19,tzinfo=timezone.utc)
    assert reviewed_evidence(tmp_path,cutoff)['source_hashes'][source.name]==file_hash(source)
    with pytest.raises(ValueError,match='cutoff'):
        reviewed_evidence(tmp_path,datetime(2026,11,18,tzinfo=timezone.utc))
    manifest['limits']={}
    atomic_json(tmp_path/'manifest.json',manifest)
    with pytest.raises(ValueError,match='limits'):
        reviewed_evidence(tmp_path,cutoff)
    source.write_text('modified source')
    with pytest.raises(ValueError,match='checksum'):
        reviewed_evidence(tmp_path,cutoff)
