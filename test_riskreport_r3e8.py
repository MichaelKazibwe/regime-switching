"""Dedicated R3E.8 tests for PortfolioRiskReport."""

from __future__ import annotations

import numpy as np

from riskreport import PortfolioRiskReport, PortfolioRiskReportError


def test_report_assembly() -> None:
    engine = PortfolioRiskReport(nav=100_000.0)

    result = engine.build(
        weights={"SPY": 0.60, "TLT": 0.40},
        performance={
            "annual_return": 0.10,
            "CAGR": 0.09,
            "annual_return_estimate": 0.11,
        },
        risk={
            "annual_volatility": 0.15,
            "VaR_95": 0.025,
            "CVaR_95": 0.035,
            "VaR_99": 0.045,
            "CVaR_99": 0.060,
        },
    )

    assert np.isclose(result.capital["gross_exposure"], 1.0)
    assert np.isclose(result.capital["net_exposure"], 1.0)
    assert result.risk_metrics["VaR_95"] == 0.025
    assert result.risk_metrics["CVaR_95"] == 0.035


def test_report_preserves_upstream_metrics() -> None:
    engine = PortfolioRiskReport()

    result = engine.build(
        performance={
            "sharpe": 1.2,
            "sortino": 1.5,
            "calmar": 0.9,
        },
        risk_adjusted={
            "information_ratio": 0.6,
            "alpha": 0.03,
            "beta": 0.85,
        },
        drawdown={
            "current_drawdown": -0.05,
            "maximum_drawdown": -0.15,
            "drawdown_duration": 20,
        },
    )

    assert result.risk_adjusted_metrics["sharpe"] == 1.2
    assert result.risk_adjusted_metrics["sortino"] == 1.5
    assert result.risk_adjusted_metrics["information_ratio"] == 0.6
    assert result.drawdown_metrics["maximum_drawdown"] == -0.15


def test_report_tail_metrics() -> None:
    engine = PortfolioRiskReport()

    result = engine.build(
        tail_risk={
            "risk_of_ruin": 0.02,
            "prob_dd_10pct": 0.30,
            "prob_dd_20pct": 0.10,
            "prob_dd_30pct": 0.03,
            "prob_dd_50pct": 0.005,
        }
    )

    assert result.tail_risk["risk_of_ruin"] == 0.02
    assert result.tail_risk["P_DD_gt_10"] == 0.30
    assert result.tail_risk["P_DD_gt_20"] == 0.10
    assert result.tail_risk["P_DD_gt_30"] == 0.03
    assert result.tail_risk["P_DD_gt_50"] == 0.005


def test_governor_status_mapping() -> None:
    engine = PortfolioRiskReport()

    amber = engine.build(
        risk_governance={
            "action": "REDUCE",
            "approved": True,
            "breaches": ["annual_volatility"],
        }
    )

    assert amber.risk_status == "AMBER"
    assert "reduced portfolio exposure" in (
        amber.status_reasons[0]
    )

    red = engine.build(
        risk_governance={
            "action": "REJECT",
            "approved": False,
        }
    )

    assert red.risk_status == "RED"


def test_status_override() -> None:
    engine = PortfolioRiskReport()

    result = engine.build(
        status_override="GREEN",
        risk_governance={
            "action": "REJECT",
            "approved": False,
        },
    )

    assert result.risk_status == "GREEN"
    assert result.status_reasons == (
        "Status supplied explicitly.",
    )


def test_missing_values_are_not_guessed() -> None:
    engine = PortfolioRiskReport()

    result = engine.build()

    assert result.risk_metrics["VaR_95"] is None
    assert result.risk_metrics["CVaR_95"] is None
    assert result.drawdown_metrics["maximum_drawdown"] is None
    assert result.options_risk["net_delta"] is None


def test_mapping_validation() -> None:
    engine = PortfolioRiskReport()

    try:
        engine.build(
            performance=["invalid"]  # type: ignore[arg-type]
        )
    except PortfolioRiskReportError:
        pass
    else:
        raise AssertionError(
            "Invalid performance input should be rejected."
        )


def test_render_contract() -> None:
    engine = PortfolioRiskReport(nav=100_000.0)

    result = engine.build(
        weights={"SPY": 0.60, "TLT": 0.40},
        performance={
            "annual_return": 0.12,
            "CAGR": 0.11,
            "annual_return_estimate": 0.13,
        },
        risk={
            "annual_volatility": 0.15,
            "VaR_95": 0.025,
            "CVaR_95": 0.035,
            "VaR_99": 0.045,
            "CVaR_99": 0.060,
        },
        drawdown={
            "current_drawdown": -0.04,
            "maximum_drawdown": -0.12,
            "drawdown_duration": 18,
            "recovery_time": 30,
            "time_under_water": 18,
        },
        risk_adjusted={
            "sharpe": 0.8,
            "sortino": 1.1,
            "calmar": 0.9,
            "information_ratio": 0.5,
            "alpha": 0.02,
            "beta": 0.85,
        },
        trade_quality={
            "trades": 100,
            "win_rate": 0.55,
            "average_winner": 1.8,
            "average_loser": -1.0,
            "reward_risk": 1.8,
            "expectancy": 0.54,
            "profit_factor": 2.2,
            "break_even_win_rate": 0.3571,
        },
        position_risk={
            "kelly_fraction": 0.20,
            "fractional_kelly": 0.05,
            "atr_risk_per_position": 0.005,
            "largest_risk_contributor": "SPY",
            "largest_factor_exposure": "Equity Beta",
        },
        tail_risk={
            "risk_of_ruin": 0.01,
            "prob_dd_10pct": 0.15,
            "prob_dd_20pct": 0.04,
            "prob_dd_30pct": 0.01,
            "prob_dd_50pct": 0.001,
        },
        options_risk={
            "net_delta": 0.0,
            "gamma": 0.0,
            "vega": 0.0,
            "put_call_parity_deviation": 0.0,
            "zomma": 0.0,
        },
        risk_governance={
            "action": "PASS",
            "approved": True,
        },
    )

    text = engine.render(result)

    required = (
        "PORTFOLIO RISK REPORT",
        "Annual Return",
        "CAGR",
        "Annual Volatility",
        "VaR 95%",
        "CVaR 95%",
        "Current Drawdown",
        "Maximum Drawdown",
        "Sharpe",
        "Sortino",
        "Calmar",
        "Information Ratio",
        "Kelly Fraction",
        "Fractional Kelly",
        "ATR Risk / Position",
        "Risk of Ruin",
        "Net Delta",
        "Gamma",
        "Vega",
        "Zomma",
        "RISK STATUS: GREEN",
    )

    for label in required:
        assert label in text


def test_contract_and_health() -> None:
    engine = PortfolioRiskReport()

    assert engine.metadata["analytics_only"] is True
    assert engine.metadata["governance"] is False
    assert engine.metadata["execution"] is False

    validation = engine.validate()
    assert validation["valid"] is True

    health = engine.health_check()
    assert health["healthy"] is True

    # to_dict() serializes the latest completed report. Build a minimal
    # report first rather than calling it before any report exists.
    engine.build()
    payload = engine.to_dict()

    assert payload is not None
    assert payload["capital"]["NAV"] == 100_000.0


if __name__ == "__main__":
    test_report_assembly()
    test_report_preserves_upstream_metrics()
    test_report_tail_metrics()
    test_governor_status_mapping()
    test_status_override()
    test_missing_values_are_not_guessed()
    test_mapping_validation()
    test_render_contract()
    test_contract_and_health()

    print(
        "PortfolioRiskReport R3E.8 tests: 9/9 passed."
    )
    print("R3E.8 STATUS: PASS")
