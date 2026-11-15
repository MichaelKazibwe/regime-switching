from __future__ import annotations

from paper_dashboard import render_dashboard


def test_dashboard_renders_operator_metrics_and_escapes_report_values() -> None:
    rendered = render_dashboard(
        [
            {
                "cycle_id": "cycle-<script>",
                "status": "APPROVED",
                "data_as_of": "2026-10-29T20:00:00+00:00",
                "decision": {
                    "regime": "EXPANSION",
                    "paper_execution": {
                        "operator_metrics": {
                            "portfolio_value": 1_025_000,
                            "cash": 250_000,
                            "cumulative_return_since_start": 0.025,
                            "active_return_since_start": -0.01,
                            "maximum_drawdown_since_start": -0.04,
                            "cumulative_turnover": 1.2,
                            "cumulative_transaction_costs": 500,
                        }
                    },
                },
            }
        ]
    )
    assert "1,025,000.00" in rendered
    assert "2.50%" in rendered
    assert "&lt;script&gt;" in rendered
    assert "<script>" not in rendered


def test_dashboard_handles_empty_report_history() -> None:
    assert "No valid paper cycle reports found" in render_dashboard([])
