from copy import deepcopy
import pytest
from dynamic_preview import validate
from strategy_integrity import fingerprint, file_hash
from portfolio_contract import make_contract


def test_preview_rejects_resigned_contract_cash_and_source_changes(tmp_path):
    source = tmp_path / "source"
    source.write_text("frozen")
    snapshot = dict(
        weights={"SPY": 0.2},
        cash=0.8,
        decision_session="2026-10-30",
        execution_enabled=False,
        promotion_enabled=False,
        source_hashes={str(source): file_hash(source)},
        contract=make_contract(
            "Dynamic_Growth_Resilience",
            {"SPY": 0.2},
            "2026-10-30",
            "test",
            basis="TEST",
            performance="TEST",
        ),
    )
    snapshot["snapshot_id"] = fingerprint(snapshot)
    assessment = dict(end="2026-10-30", source_hashes={str(source): file_hash(source)})
    reconciliation = dict(
        release_approved=False,
        checks={
            k: dict(status="RECONCILED_LOCAL_REPLAY")
            for k in ("0bps", "15bps", "30bps")
        },
    )
    validate(snapshot, assessment, reconciliation)
    bad = deepcopy(snapshot)
    bad["cash"] = 0.5
    bad.pop("snapshot_id")
    bad["snapshot_id"] = fingerprint(bad)
    with pytest.raises(ValueError, match="cash"):
        validate(bad, assessment, reconciliation)
    source.write_text("changed")
    with pytest.raises(ValueError, match="source"):
        validate(snapshot, assessment, reconciliation)
