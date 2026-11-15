from datetime import datetime, timezone
from pathlib import Path
import json
from types import SimpleNamespace
import pandas as pd
from strategy_integrity import file_hash
import scheduled_p1_research as jobs


def test_weekly_uses_bound_sources_and_does_not_repeat(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "usable_session", lambda _: pd.Timestamp("2026-10-30"))
    operations = tmp_path / "operations"
    operations.mkdir()
    job = tmp_path / "job"
    (job / "dashboard").mkdir(parents=True)
    bundle = job / "dashboard/latest-strategy-run.json"
    bundle.write_text("{}")
    (operations / "latest-job.json").write_text(
        json.dumps(
            dict(status="PASSED_SHADOW_ONLY", market_session="2026-10-30", job=str(job))
        )
    )
    root = tmp_path / "research"
    calls = []

    def completed(command, **kwargs):
        calls.append(True)
        output = Path(command[-1])
        output.mkdir()
        status = json.loads((root / "latest.json").read_text())
        protocol = output / "protocol.json"
        protocol.write_text("{}")
        (output / "assessment.json").write_text(
            json.dumps(
                dict(
                    source_hashes={
                        str(Path(p).resolve()): h
                        for p, h in status["source_hashes"].items()
                    },
                    promotion_enabled=False,
                    execution_enabled=False,
                    status="COMPLETED_REVIEW_ONLY",
                    bundle_sha256=file_hash(bundle),
                    artifacts={"protocol.json": file_hash(protocol)},
                )
            )
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(jobs, "run_bounded", completed)
    now = datetime(2026, 10, 30, 23, tzinfo=timezone.utc)
    assert jobs.run(root, operations, now=now)["status"] == "COMPLETED_REVIEW_ONLY"
    assert (
        jobs.run(root, operations, now=now)["status"]
        == "ALREADY_STUDIED_OR_RETRY_LIMIT"
    )
    assert calls == [True]


def test_weekly_waits_for_valid_daily_job(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "usable_session", lambda _: pd.Timestamp("2026-10-30"))
    (tmp_path / "latest-job.json").write_text(json.dumps(dict(status="FAILED")))
    assert (
        jobs.run(
            tmp_path / "research",
            tmp_path,
            now=datetime(2026, 10, 30, 23, tzinfo=timezone.utc),
        )["status"]
        == "BLOCKED_DAILY_VALIDATION"
    )
