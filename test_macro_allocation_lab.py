from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace

import pytest

from assetuniverse import DIVERSIFIED_ASSETS
from assetroles import ASSET_ROLES
from fourregimestrategies import FourMacroStrategies
from macro_allocation_lab import recalculate, simulate_candidate, validate_forecast
from smartregimeportfolio import REGIMES
from test_goal_portfolio import inputs
from strategy_dashboard_server import handler, shell


@pytest.fixture
def lab():
    _, prices, daily, states = inputs()
    s = next(iter(states.values()))
    policy = FourMacroStrategies()
    h = daily.iloc[s["i"] - 251 : s["i"] + 1][s["symbols"]]
    signal = {**s["signal"], "macro_valid": True}
    forecast = {"as_of": signal["as_of"], "used": [0.25] * 4, "enabled": False}
    return {
        "policy": policy,
        "active": s["symbols"],
        "history": h,
        "sample_history": h,
        "covariance": s["covariance"],
        "trends": s["trends"],
        "signal": signal,
        "pools": {r: list(range(1, 200)) for r in REGIMES},
        "accounts": {
            n: {
                "drawdown": 0.0,
                "locked": False,
                "tail_multiplier": 1.0,
                "guard_start": 0.02,
                "guard_lock": 0.04,
            }
            for n in policy.config["strategies"]
        },
        "report": {
            "market_session": str(prices.index[-1].date()),
            "classifier": {"latest_forecast": forecast},
        },
    }


@pytest.mark.parametrize("name", list(FourMacroStrategies().config["strategies"]))
def test_recalculation_reconciles_capital_risk_and_preserves_policy(lab, name):
    config = deepcopy(lab["policy"].config)
    r = recalculate(
        lab,
        name,
        dict(zip(REGIMES, [0.25] * 4)),
        quarters=1,
        paths=100,
        mode="latest_model",
    )
    assert r["status"] == "SHADOW_SCENARIO_CANDIDATE"
    assert sum(r["weights"].values()) + r["cash"] == pytest.approx(1, abs=1e-6)
    assert set(r["weights"]) == set(DIVERSIFIED_ASSETS)
    assert max(r["weights"].values()) <= 0.250001
    assert max(v for v in r["risk_contributions"].values() if v is not None) <= 0.250001
    assert r["risk_budget_error"] <= 1e-6 and not r["execution_enabled"]
    assert set(ASSET_ROLES) == set(DIVERSIFIED_ASSETS) | {"DBMF", "ALLW", "USD_CASH"}
    assert lab["policy"].config == config
    assert r["simulation"]["paths"] == 100
    assert (
        r["simulation"]["p05_return"]
        <= r["simulation"]["median_return"]
        <= r["simulation"]["p95_return"]
    )


def test_model_mode_cannot_bypass_predictive_gate(lab):
    with pytest.raises(ValueError, match="validation gate"):
        recalculate(
            lab,
            "economic_balance",
            dict(zip(REGIMES, [1.0, 0.0, 0.0, 0.0])),
            mode="latest_model",
        )


@pytest.mark.parametrize(
    "values", [[1, 1, 1, 1], [float("nan"), 0, 0, 1], [-1, 1, 1, 0], [True, 0, 0, 0]]
)
def test_invalid_forecast_weights_rejected(values):
    with pytest.raises(ValueError):
        validate_forecast(dict(zip(REGIMES, values)))


def test_scenario_coverage_and_resource_bounds_fail_closed(lab):
    weights = {s: 0.0 for s in DIVERSIFIED_ASSETS}
    weights["SPY"] = 0.2
    forecast = dict(zip(REGIMES, [1.0, 0.0, 0.0, 0.0]))
    lab["pools"][REGIMES[0]] = []
    r = simulate_candidate(
        lab,
        weights,
        0.8,
        forecast,
        lab["accounts"]["economic_balance"],
        quarters=1,
        paths=100,
    )
    assert r["status"] == "BLOCKED_SCENARIO_COVERAGE"
    with pytest.raises(ValueError):
        simulate_candidate(
            lab,
            weights,
            0.8,
            forecast,
            lab["accounts"]["economic_balance"],
            paths=100000,
        )


def test_service_shell_has_no_financial_payload_and_api_requires_auth():
    assert b"connect-src" in shell() and b"Authorization" in shell()

    class App:
        payload = {"private-client": "PRIVATE_FINANCIAL_PAYLOAD"}

    server_handler = handler(App(), "a" * 64)
    h = object.__new__(server_handler)
    h.server = SimpleNamespace(server_port=8768)
    h.wfile = BytesIO()
    h.send_response = lambda code: setattr(h, "code", code)
    h.send_header = lambda *args: None
    h.end_headers = lambda: None
    h.headers = {"Host": "127.0.0.1:8768"}
    h.path = "/"
    h.do_GET()
    assert h.code == 200 and b"PRIVATE_FINANCIAL_PAYLOAD" not in h.wfile.getvalue()
    h.wfile = BytesIO()
    h.path = "/api/dashboard"
    h.do_GET()
    assert h.code == 401
    h.headers["Authorization"] = "Bearer " + "a" * 64
    h.wfile = BytesIO()
    h.do_GET()
    assert h.code == 200 and b"PRIVATE_FINANCIAL_PAYLOAD" in h.wfile.getvalue()
    h.headers["Origin"] = "https://untrusted.invalid"
    h.do_GET()
    assert h.code == 403


def test_supplied_macro_weights_change_allocation_without_changing_constraints(lab):
    a = recalculate(
        lab, "economic_balance", dict(zip(REGIMES, [0.25] * 4)), quarters=1, paths=100
    )
    b = recalculate(
        lab,
        "economic_balance",
        dict(zip(REGIMES, [0.0, 0.0, 1.0, 0.0])),
        quarters=1,
        paths=100,
    )
    assert a["weights"] != b["weights"]
    for result in (a, b):
        assert result["forecast_tilt_weight"] == 0.2
        assert sum(result["weights"].values()) + result["cash"] == pytest.approx(
            1, abs=1e-6
        )
        assert (
            max(v for v in result["risk_contributions"].values() if v is not None)
            <= 0.250001
        )


def test_conditional_paths_preserve_existing_cash_lock_and_peak(lab):
    account = {
        **lab["accounts"]["economic_balance"],
        "drawdown": -0.041,
        "locked": True,
    }
    weights = {s: 0.0 for s in DIVERSIFIED_ASSETS}
    r = simulate_candidate(
        lab,
        weights,
        1.0,
        dict(zip(REGIMES, [0.25] * 4)),
        account,
        quarters=1,
        paths=100,
    )
    assert r["median_return"] == pytest.approx(0)
    assert r["terminal_loss_frequency"] == 0
    assert r["p95_max_drawdown"] == pytest.approx(0.041)
