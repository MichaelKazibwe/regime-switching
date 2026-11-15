import pytest

import run_return_engine_cycle as runner


def test_dynamic_failure_precedes_ledger_and_dashboard_mutation(tmp_path, monkeypatch):
    calls = []

    def blocked(*_):
        raise ValueError("risk blocked")

    monkeypatch.setattr(runner, "refresh_dynamic", blocked)
    for name in ("advance", "publish", "evaluate", "assess"):
        monkeypatch.setattr(runner, name, lambda *_, **__: calls.append("mutation"))
    with pytest.raises(ValueError, match="risk blocked"):
        runner.cycle("unused", root=tmp_path)
    assert calls == []
    assert not (tmp_path / "latest.json").exists()
    assert not (tmp_path / "dynamic-latest.json").exists()
