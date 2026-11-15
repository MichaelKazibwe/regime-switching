from __future__ import annotations

from datetime import datetime, timezone
import hashlib

import numpy as np
import pandas as pd
import pytest

from paper_runtime import PaperDecisionRunner
from paperconfig import PaperRuntimeConfig
from paperstore import SQLitePaperStore
from productiondecisionexecution import ProductionDecisionExecution
from researchdatastore import ResearchArtifactError, ResearchDataStore
from researchreplay import replay_decision


def test_snapshot_round_trip_preserves_float_bits_and_pandas_types(tmp_path) -> None:
    index = pd.date_range("2025-01-02", periods=3, tz="UTC", name="session")
    frame = pd.DataFrame(
        {"close": np.array([0.1, 1.0 / 3.0, 101.125], dtype=np.float64)},
        index=index,
    )
    inputs = {
        "prices": frame,
        "series": pd.Series([0.1, -0.0, 1.0 / 3.0], index=index, name="signal"),
        "weights": {"SPY": 0.25, "TLT": 0.75},
        "regimes": ("EXPANSION", "CONTRACTION"),
    }
    store = ResearchDataStore(tmp_path / "snapshots")
    provenance = {"code_revision": "test-revision"}
    manifest = store.write_snapshot(
        inputs,
        input_fingerprint="a" * 64,
        configuration={"fee": 0.0005},
        provenance=provenance,
    )

    restored = store.load_snapshot(manifest)
    assert restored["inputs"]["prices"].equals(frame)
    assert restored["inputs"]["prices"].dtypes.equals(frame.dtypes)
    assert restored["inputs"]["series"].equals(inputs["series"])
    assert np.asarray(restored["inputs"]["series"], dtype=np.float64).view(np.uint64).tolist() == np.asarray(inputs["series"], dtype=np.float64).view(np.uint64).tolist()
    assert restored["inputs"]["regimes"] == inputs["regimes"]
    assert list(restored["inputs"]["weights"]) == list(inputs["weights"])
    artifact_path = tmp_path / "snapshots" / manifest["relative_path"]
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == manifest["artifact_id"]


def test_snapshot_detects_tampering_and_path_substitution(tmp_path) -> None:
    store = ResearchDataStore(tmp_path / "snapshots")
    manifest = store.write_snapshot(
        {"sample": [1, 2, 3]},
        input_fingerprint="b" * 64,
        configuration={},
        provenance={},
    )
    artifact_path = tmp_path / "snapshots" / manifest["relative_path"]
    artifact_path.write_bytes(artifact_path.read_bytes() + b"tamper")
    with pytest.raises(ResearchArtifactError, match="content hash"):
        store.load_snapshot(manifest)

    changed = {**manifest, "relative_path": "../outside.json.gz"}
    with pytest.raises(ResearchArtifactError, match="path"):
        store.load_snapshot(changed)


def test_paper_decision_can_be_replayed_without_writes_or_orders(tmp_path) -> None:
    now = datetime.now(timezone.utc)
    returns = ProductionDecisionExecution.build_returns()
    inputs = {
        "portfolio": ProductionDecisionExecution.build_portfolio(),
        "returns": returns,
        "prices": ProductionDecisionExecution.build_prices(returns),
        "regimes": ProductionDecisionExecution.build_regimes(),
        "macro_data": ProductionDecisionExecution.build_macro_data(),
        "scenarios": ProductionDecisionExecution.build_scenarios(),
        "data_as_of": now,
        "data_source": "DETERMINISTIC_REPLAY_FIXTURE",
    }
    database = tmp_path / "paper.sqlite3"
    snapshots = tmp_path / "research-snapshots"
    config = PaperRuntimeConfig(
        state_database=database,
        audit_log=tmp_path / "audit.jsonl",
        research_snapshot_directory=snapshots,
    )
    runner = PaperDecisionRunner(
        config,
        input_provider=lambda: inputs,
        clock=lambda: now,
    )
    original = runner.run_once("research-replay-cycle")
    assert original.payload["research_snapshot"]["artifact_id"]
    assert original.payload["decision_fingerprint"]

    read_only_store = SQLitePaperStore(database, read_only=True)
    snapshot_store = ResearchDataStore(snapshots)
    replay = replay_decision(
        read_only_store,
        snapshot_store,
        original.event_id,
    )
    assert replay["exact_match"] is True
    assert replay["orders_submitted"] == 0
    assert replay["mode"] == "REPLAY_ONLY"
    assert read_only_store.read_events() == (original,)
