"""Failure-path acceptance for the reviewed operational contracts."""

import json
from pathlib import Path

import pytest


def test_source_only_image_contains_subprocess_collection_entrypoints(tmp_path):
    from pilot_release import stage

    source = Path(__file__).resolve().parent
    manifest = stage(source, tmp_path / "release", allow_dirty=True, source_only=True)
    required = {
        "live_observation_cycle.py",
        "market_quality.py",
        "run_return_engine_cycle.py",
        "evaluate_institutional_engines.py",
        "dynamic_forward.py",
        "daily_alpha_training.py",
        "pilot_pipeline.py",
    }
    assert required <= set(manifest["files"])
    assert all((tmp_path / "release/image" / name).is_file() for name in required)


def test_portable_bootstrap_relocates_every_active_artifact_path(tmp_path, monkeypatch):
    import pilot_release
    from pilot_pipeline import bootstrap_snapshot

    root = tmp_path / "var/pilot-input/evidence"
    root.mkdir(parents=True)
    (root / "original-bundle.json").write_text(
        json.dumps(
            dict(
                capture="/unavailable-host/capture.json",
                training_report="/unavailable-host/report.json",
                benchmark_extension="/unavailable-host/extension",
                portfolio_contracts="/unavailable-host/contracts.json",
            )
        )
    )
    (root.parent / "snapshot-manifest.json").write_text(
        json.dumps(dict(market_session="2026-11-16"))
    )
    doc = tmp_path / "materialized/investor-dashboard.html"
    doc.parent.mkdir()
    doc.write_text("synthetic")
    monkeypatch.setattr(pilot_release, "materialize_snapshot", lambda *a: doc)
    bootstrap_snapshot(tmp_path)
    bundle = json.loads(
        (tmp_path / "var/pilot-pipeline/portable-bundle.json").read_text()
    )
    for key in [
        "capture",
        "training_report",
        "benchmark_extension",
        "portfolio_contracts",
    ]:
        assert Path(bundle[key]).is_relative_to(tmp_path)
    assert not bundle["portable_derivation"]["creates_new_observations"]


def test_weekly_publication_rejects_rollback_and_keeps_pointer(tmp_path, monkeypatch):
    import weekly_portfolios
    from research_publisher import filesystem_publish
    from strategy_integrity import fingerprint, file_hash

    destination = tmp_path / "published"
    body = dict(
        market_session="2026-11-13", execution_enabled=False, promotion_enabled=False
    )
    revision = fingerprint(body)
    prior = destination / revision
    prior.mkdir(parents=True)
    (prior / "recommendations.json").write_text(
        json.dumps({**body, "research_id": revision})
    )
    (prior / "dashboard-report.pdf").write_bytes(b"%PDF-synthetic")
    (prior / "manifest.json").write_text(
        json.dumps(
            dict(
                files={
                    name: file_hash(prior / name)
                    for name in ["recommendations.json", "dashboard-report.pdf"]
                }
            )
        )
    )
    (destination / "latest.json").write_text(json.dumps({"research_id": revision}))
    source = tmp_path / "older"
    source.mkdir()

    def verify(path):
        return dict(
            research_id="new" if Path(path) == prior else "old",
            market_session="2026-11-13" if Path(path) == prior else "2026-11-06",
        )

    monkeypatch.setattr(weekly_portfolios, "verify", verify)
    with pytest.raises(ValueError, match="rollback"):
        filesystem_publish(source, destination, kind="weekly")
    assert json.loads((destination / "latest.json").read_text()) == {
        "research_id": revision
    }
    assert not (destination / "old").exists()
    from research_publisher import historical_weekly_session

    (prior / "dashboard-report.pdf").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        historical_weekly_session(prior)


def test_pipeline_reports_waiting_stage_and_always_writes_final_receipt(
    tmp_path, monkeypatch
):
    import pilot_pipeline as pipeline

    for name in ["collect", "benchmark", "train", "daily", "weekly"]:
        monkeypatch.setattr(pipeline, name, lambda *a, **kw: dict(status="AVAILABLE"))
    monkeypatch.setattr(pipeline, "bootstrap_snapshot", lambda *a: None)
    monkeypatch.setattr(pipeline, "runtime", lambda *a: {"synthetic": True})
    monkeypatch.setattr(
        pipeline, "weekly", lambda *a, **kw: dict(status="WAITING_FOR_COMPLETED_WEEK")
    )
    result = pipeline.run(tmp_path)
    assert result["status"] == "WAITING" and result["waiting_stages"] == ["weekly"]

    def broken(*args, **kwargs):
        raise TimeoutError("Synthetic publication timeout")

    monkeypatch.setattr(pipeline, "daily", broken)
    with pytest.raises(TimeoutError):
        pipeline.run(tmp_path)
    heartbeat = json.loads((tmp_path / "var/pilot-pipeline/heartbeat.json").read_text())
    assert heartbeat["status"] == "FAILED" and heartbeat["stage"] == "daily"
    assert heartbeat["finished_at"] and heartbeat["error_type"] == "TimeoutError"


def test_independent_comparison_catches_old_discrepancy_even_when_latest_matches(
    tmp_path, monkeypatch
):
    import numpy as np
    import pandas as pd
    import market_quality
    from strategy_integrity import file_hash

    dates = pd.bdate_range(end="2026-11-16", periods=300)
    prices = pd.DataFrame({"SYN": 100 * 1.001 ** np.arange(300)}, index=dates)
    panel = prices.copy()
    panel.iloc[-100, 0] *= 1.02
    csv = tmp_path / "prices.csv"
    panel.to_csv(csv)
    manifest = tmp_path / "provider.json"
    manifest.write_text(
        json.dumps(
            dict(
                provider="Synthetic independent fixture",
                basis="ADJUSTED_TOTAL_RETURN",
                source="Synthetic reviewed evidence",
                reviewer="QA",
                rights_reviewed=True,
                captured_at="2026-11-16T23:00:00Z",
                file=csv.name,
                sha256=file_hash(csv),
            )
        )
    )
    capture = tmp_path / "capture.json"
    capture.write_text("{}")
    monkeypatch.setattr(
        market_quality,
        "read_capture",
        lambda p: ({"price_session": "2026-11-16"}, prices),
    )
    monkeypatch.setattr(market_quality, "validate_prices", lambda p, *a, **kw: p)
    result = market_quality.review(capture, secondary=manifest)
    assert result["independent_provider"] == "DISCREPANCY_REVIEW_REQUIRED"
    assert result["independent_comparison"]["mismatches"] == ["SYN"]
    assert result["independent_comparison"]["comparison_sessions"] == 252


def test_independent_capture_uses_its_declared_universe_not_the_current_registry(
    tmp_path, monkeypatch
):
    import numpy as np
    import pandas as pd
    import pandas_market_calendars as mcal
    import market_quality
    from strategy_integrity import file_hash

    dates = mcal.get_calendar("NYSE").schedule("2020-01-01", "2026-11-16").index
    prices = pd.DataFrame({"MSFT": 100 * 1.0001 ** np.arange(len(dates))}, index=dates)
    csv = tmp_path / "prices.csv"
    prices.to_csv(csv)
    manifest = tmp_path / "provider.json"
    manifest.write_text(
        json.dumps(
            dict(
                provider="Synthetic independent fixture",
                basis="ADJUSTED_TOTAL_RETURN",
                source="Synthetic evidence",
                reviewer="QA",
                rights_reviewed=True,
                captured_at="2026-11-16T23:00:00Z",
                file=csv.name,
                sha256=file_hash(csv),
            )
        )
    )
    capture = tmp_path / "capture.json"
    capture.write_text("{}")
    monkeypatch.setattr(
        market_quality,
        "read_capture",
        lambda p: ({"price_session": "2026-11-16"}, prices),
    )
    assert (
        market_quality.review(capture, secondary=manifest)["independent_provider"]
        == "MATCHED_DAILY_RETURN_TOLERANCE"
    )
