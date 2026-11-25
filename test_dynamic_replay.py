from evaluate_dynamic_portfolio import replay_dynamic
from test_institutional_return_engines import market  # noqa: F401


def test_dynamic_replay_uses_later_fills_and_costs(market):  # noqa: F811
    prices = market.iloc[:260]
    free, trades = replay_dynamic(prices, {}, cost=0)
    paid, _ = replay_dynamic(prices, {}, cost=0.003)
    assert trades and all(t["decision_session"] < t["fill_session"] for t in trades)
    assert paid.equity.iloc[-1] < free.equity.iloc[-1]
    assert free.regime.eq("MARKET_ONLY_DEGRADED").all()


def test_fill_day_price_cannot_change_preexisting_first_target(market):  # noqa: F811
    prices = market.iloc[:255].copy()
    _, before = replay_dynamic(prices, {})
    prices.iloc[253:] *= 2
    _, after = replay_dynamic(prices, {})
    assert before[0]["weights"] == after[0]["weights"]


def test_shared_causal_decisions_preserve_each_cost_run_exactly(market, monkeypatch):  # noqa: F811
    import pandas as pd
    import evaluate_dynamic_portfolio as module
    prices = market.iloc[:280]
    independent = {cost: replay_dynamic(prices, {}, cost=cost) for cost in (0., .0015, .003)}
    original = module.allocate
    calls = []
    def counted(ctx):
        calls.append(ctx["decision_session"])
        return original(ctx)
    monkeypatch.setattr(module, "allocate", counted)
    runner, candidates = module.Replay(prices, {}), {}
    for cost, (expected, trades) in independent.items():
        actual, cached_trades = module._replay_dynamic(runner, candidates, cost=cost)
        pd.testing.assert_frame_equal(actual, expected, check_exact=True)
        assert cached_trades == trades
    assert len(calls) == len(set(calls)) == len(candidates)
    assert independent[0.][0].equity.iloc[-1] > independent[.003][0].equity.iloc[-1]
