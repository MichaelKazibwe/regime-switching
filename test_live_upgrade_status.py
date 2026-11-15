import pytest
from live_upgrade_status import inventory


def test_inventory_cannot_grant_execution_authority():
    result = inventory()
    assert len(result["tasks"]) == 26
    assert all(t["qualification"] == "OPEN" for t in result["tasks"])
    assert not result["execution_enabled"] and not result["release_approved"]


def test_missing_or_reordered_inventory_rejected(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text("| 02 | P0 | work | criterion | owner |")
    with pytest.raises(ValueError, match="26-item"):
        inventory(bad)
