from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
import json

import numpy as np
import pandas as pd
import pytest

from refresh_strategy_dashboard import retire_extensions
from portfolio_risk_envelope import assess
from forecast_calibration import nonoverlap_origins, evaluate
from managed_portfolio_risk import review as account_review
from strategy_integrity import fingerprint


def test_refresh_retires_unbound_extensions_without_changing_plans():
    payload = dict(
        plans=[dict(id="saved", allocation={"SPY": 0.2})],
        pdf_links={"saved": "plan.pdf", "dynamic": "dynamic.pdf"},
        dynamic_portfolio={"old": True},
        return_engines={"old": True},
    )
    original = deepcopy(payload["plans"])
    retire_extensions(payload)
    assert payload["plans"] == original
    assert payload["pdf_links"] == {"saved": "plan.pdf"}
    assert "dynamic_portfolio" not in payload and "return_engines" not in payload


@pytest.fixture
def history():
    rng = np.random.default_rng(721)
    return pd.DataFrame(
        rng.normal(0, 0.004, (252, 8)),
        index=pd.bdate_range("2025-01-01", periods=252),
        columns=list("ABCDEFGH"),
    )


def test_pending_buys_cannot_hide_asset_concentration(history):
    assert assess(dict.fromkeys(history.columns, 0.1), history)["status"] != "REJECT"
    result = assess(
        dict.fromkeys(history.columns, 0.1), history, pending_buys={"A": 0.2}
    )
    assert "asset" in result["breaches"] and "gross" in result["breaches"]
    assert not result["execution_enabled"]


def test_missing_held_history_and_negative_weights_fail_closed(history):
    with pytest.raises(ValueError, match="Missing held"):
        assess({"UNKNOWN": 0.1}, history)
    with pytest.raises(ValueError, match="long-only"):
        assess({"A": -0.1}, history)
    history.iloc[-1, 0] = np.nan
    with pytest.raises(ValueError, match="Incomplete"):
        assess({"A": 0.1}, history)


def test_correlation_shock_diagnostic_is_at_least_observed_volatility(history):
    r = assess(dict.fromkeys(history.columns, 0.1), history)
    assert r["full_correlation_volatility"] >= r["metrics"]["volatility"]
    assert r["measured_exposures_status"].startswith("BLOCKED")


def test_quarterly_labels_keep_session_horizon_across_missing_macro():
    f = [{"macro_valid": True} for _ in range(100)]
    f[0]["macro_valid"] = False
    f[12]["macro_valid"] = False
    origins = nonoverlap_origins(f, 0, 80, 10)
    assert all(b - a >= 10 for a, b in zip(origins, origins[1:]))
    assert all(f[i]["macro_valid"] and f[i + 10]["macro_valid"] for i in origins)


def test_no_matured_forecasts_are_explicitly_blocked():
    from test_four_macro_strategies import features, settings

    f = features(200)
    for row in f:
        row["macro_valid"] = False
    r = evaluate(f, settings(), freeze=120, origins=[], regularization=0.1, shrink=0.25)
    assert r["outcomes"] == 0 and r["model_brier"] is None
    assert r["status"] == "BLOCKED_NO_MATURED_OUTCOMES"


def test_account_risk_requires_provider_and_exact_request_binding():
    now = datetime(2026, 11, 2, 16, tzinfo=timezone.utc)
    with pytest.raises(PermissionError, match="provider"):
        account_review({}, None, {}, now)
    with pytest.raises(PermissionError, match="binding"):
        account_review(
            {}, lambda _: dict(as_of=now.isoformat(), request_sha256="wrong"), {}, now
        )
    with pytest.raises(PermissionError, match="stale"):
        account_review(
            {},
            lambda _: dict(
                as_of="2026-11-01T16:00:00+00:00", request_sha256=fingerprint({})
            ),
            {},
            now,
        )


def test_retry_budget_stops_unbounded_failed_runs(tmp_path, monkeypatch):
    import local_observation_scheduler as jobs

    monkeypatch.setattr(jobs, "usable_session", lambda _: pd.Timestamp("2026-10-30"))
    calls = []
    monkeypatch.setattr(
        jobs,
        "run_bounded",
        lambda *_, **__: calls.append(True) or SimpleNamespace(returncode=2),
    )
    assert [jobs.tick(tmp_path) for _ in range(4)] == [2, 2, 2, 2]
    assert len(calls) == 3
    report = json.loads(
        (tmp_path / "var/local-observation-scheduler/heartbeat.json").read_text()
    )
    assert report["status"] == "RETRY_BUDGET_EXHAUSTED"
    assert (tmp_path / "var/local-observation-scheduler/alerts/latest.json").is_file()


def test_watchdog_rejects_fresh_heartbeat_when_core_job_invalid(tmp_path, monkeypatch):
    import observation_watchdog as monitor

    now = datetime(2026, 11, 2, 16, tzinfo=timezone.utc)
    for directory, value in [
        (
            "local-observation-scheduler/heartbeat.json",
            dict(checked_at=now.isoformat(), status="COMPLETED"),
        ),
        (
            "live-observation-cycle/latest.json",
            dict(status="PASSED_SHADOW_ONLY", market_session="2026-10-30"),
        ),
    ]:
        path = tmp_path / directory
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(value))
    monkeypatch.setattr(
        monitor,
        "health",
        lambda *_: dict(status="ALERT_REQUIRED", expected_session="2026-10-30"),
    )
    assert monitor.check(tmp_path, now=now)["status"] == "ALERT_REQUIRED"
    monkeypatch.setattr(
        monitor,
        "health",
        lambda *_: dict(status="PENDING_SHADOW_JOB", expected_session="2026-11-02"),
    )
    assert monitor.check(tmp_path, now=now)["status"] == "PENDING_SHADOW_JOB"


def test_timeout_terminates_worker_process_group(tmp_path):
    import subprocess
    import sys
    from observation_process import run_bounded

    with (tmp_path / "log").open("w") as out:
        with pytest.raises(subprocess.TimeoutExpired):
            run_bounded(
                [sys.executable, "-c", "import time; time.sleep(20)"],
                cwd=tmp_path,
                stdout=out,
                stderr=subprocess.STDOUT,
                timeout=0.05,
            )


def test_account_risk_counts_pending_and_filled_orders_and_blocks_missing_evidence():
    from portfolio_risk_envelope import DEFAULT_LIMITS

    now = datetime(2026, 11, 2, 16, tzinfo=timezone.utc)
    returns = pd.DataFrame(
        {"A": np.random.default_rng(9).normal(0, 0.002, 252)},
        index=pd.bdate_range(end="2026-10-30", periods=252),
    )
    proposed = dict(
        instrument_id="1", currency="USD", side="BUY", quantity="1", notional="100"
    )
    request = dict(
        client_id="new",
        cash={"USD": "1000"},
        positions={},
        pending=[],
        proposed=proposed,
        traded_today="150",
    )

    def provider(r):
        return dict(
            as_of=now.isoformat(),
            request_sha256=fingerprint(r),
            marks={
                "1": dict(
                    price_per_share=100.0,
                    currency="USD",
                    symbol="A",
                    source="synthetic unit quote",
                    as_of=now.isoformat(),
                )
            },
            returns=returns,
        )

    permit = dict(
        max_daily_notional="200",
        portfolio_risk_limits={**DEFAULT_LIMITS, "positive_euler": 1},
        portfolio_exposure_limits=dict(
            portfolio_duration_ceiling=10,
            unhedged_fx_ceiling=1,
            maximum_country_weight=1,
            maximum_underlying_weight=1,
            maximum_adv_fraction=0.01,
        ),
    )
    with pytest.raises(PermissionError, match="Daily filled"):
        account_review(request, provider, permit, now)
    permit["max_daily_notional"] = "1000"
    with pytest.raises(PermissionError, match="financial/exposure"):
        account_review(request, provider, permit, now)
    request["pending"] = [
        {**proposed, "client_id": "old", "quantity": "2", "notional": "200"}
    ]
    with pytest.raises(PermissionError, match="statistical risk"):
        account_review(request, provider, permit, now)


def test_risk_candidate_is_causal_and_bounded():
    from test_institutional_return_engines import market
    from institutional_return_engines import context
    from resilient_candidate import propose

    prices = market.__wrapped__()
    i = len(prices) - 2
    ctx = context(prices, i, {})
    history = prices.pct_change(fill_method=None).iloc[i - 251 : i + 1]
    first = propose("economic_balance", ctx, history, "market_only_efficient")
    prices.iloc[-1] *= 10
    second = propose(
        "economic_balance", context(prices, i, {}), history, "market_only_efficient"
    )
    assert first == second
    assert max(first["weights"].values()) <= 0.250001
    assert first["cash"] >= 0.35 - 1e-6


def test_training_checkpoint_reuse_requires_unchanged_inputs(tmp_path, monkeypatch):
    import observation_recovery as recovery
    from strategy_integrity import file_hash

    directory = tmp_path / "dashboard"
    directory.mkdir()
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(dict(price_session="2026-11-02")))
    training = tmp_path / "training.json"
    training.write_text("{}")
    checkpoint = dict(
        capture=str(capture),
        training_report=str(training),
        benchmark_extension="test-extension",
        input_hashes={
            str(capture): file_hash(capture),
            str(training): file_hash(training),
        },
    )
    (directory / "training-checkpoint.json").write_text(json.dumps(checkpoint))
    monkeypatch.setattr(
        recovery,
        "load_training_report",
        lambda _: dict(
            current_numerical_source_match=True,
            market_session="2026-11-02",
            capture_sha256=file_hash(capture),
        ),
    )
    monkeypatch.setattr(recovery, "extended_prices", lambda *_: None)
    assert recovery.reusable_bundle(tmp_path, "2026-11-02")["training_report"] == str(
        training
    )
    training.write_text('{"tampered":true}')
    with pytest.raises(ValueError, match="checkpoint"):
        recovery.reusable_bundle(tmp_path, "2026-11-02")
