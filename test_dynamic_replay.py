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
