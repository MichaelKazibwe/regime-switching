from dataclasses import replace
from datetime import datetime, timezone
import fcntl

import pytest

from paper_backup import create_bundle, restore_bundle, verify_bundle
from paper_service import run_once
from paperconfig import PaperRuntimeConfig
from productiondecisionexecution import ProductionDecisionExecution


@pytest.fixture
def runtime(tmp_path):
    root = tmp_path / "runtime"
    config = PaperRuntimeConfig(
        state_database=root / "paper-state.sqlite3", audit_log=root / "paper-audit.jsonl",
        report_directory=root / "paper-reports", dashboard_file=root / "paper-dashboard.html",
        research_snapshot_directory=root / "research-snapshots", alert_file=root / "paper-alerts.jsonl",
    )
    returns = ProductionDecisionExecution.build_returns()
    inputs = {
        "portfolio": ProductionDecisionExecution.build_portfolio(), "returns": returns,
        "prices": ProductionDecisionExecution.build_prices(returns),
        "regimes": ProductionDecisionExecution.build_regimes(),
        "macro_data": ProductionDecisionExecution.build_macro_data(),
        "scenarios": ProductionDecisionExecution.build_scenarios(),
        "data_as_of": datetime.now(timezone.utc), "data_source": "DETERMINISTIC_TEST_FIXTURE",
    }
    run_once(config, "backup-fixture", input_provider=lambda: inputs)
    return root, config


def test_complete_bundle_restores_replays_and_detects_tampering(runtime, tmp_path):
    root, config = runtime
    bundle = tmp_path / "backup"
    result = create_bundle(config, root, bundle)
    assert result["cycles_verified"] == 1
    restored = tmp_path / "restored"
    result = restore_bundle(bundle, restored, replay=True)
    assert result["replays"][0]["exact_match"] is True
    assert result["replays"][0]["orders_submitted"] == 0
    assert verify_bundle(restored)["status"] == "PASS"
    restored_config = replace(config, state_database=restored / "paper-state.sqlite3",
                              audit_log=restored / "paper-audit.jsonl",
                              research_snapshot_directory=restored / "research-snapshots")
    assert create_bundle(restored_config, restored, tmp_path / "second-backup")["status"] == "PASS"
    with pytest.raises(ValueError, match="must not exist"):
        restore_bundle(bundle, restored)
    (bundle / "paper-audit.jsonl").write_text("tampered\n")
    with pytest.raises(ValueError, match="checksum"):
        verify_bundle(bundle)


def test_backup_refuses_active_worker_and_paths_outside_root(runtime, tmp_path):
    root, config = runtime
    with config.state_database.with_suffix(".sqlite3.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="Worker is active"):
            create_bundle(config, root, tmp_path / "blocked")
    with pytest.raises(ValueError, match="outside"):
        create_bundle(config, root, root / "recursive-backup")
    with pytest.raises(ValueError, match="inside runtime root"):
        create_bundle(replace(config, audit_log=tmp_path / "outside"), root, tmp_path / "invalid")
