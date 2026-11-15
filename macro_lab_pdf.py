"""Macro-driven candidate allocation, every asset role and scenario metrics PDF."""

import os
from pathlib import Path
import tempfile

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import PageBreak, SimpleDocTemplate, TableStyle

from investor_pdf import LineChart, NAVY, MUTED, paragraph, percent, styles, table
from assetroles import ASSET_ROLES


def allocation_flowables(result, training=None, width=495):
    s = styles()

    def p(value, kind="InvestorBody"):
        return paragraph(value, s[kind])

    story = [
        p("Macro-driven strategy allocation", "InvestorTitle"),
        p(result["strategy"].replace("_", " ").title()),
        p(
            f"Market session {result['market_session']} / macro signal {result['macro_as_of']} / {result['mode']}",
            "InvestorSmall",
        ),
        p(
            "SHADOW SCENARIO ONLY. Hypothetical evaluation account; not the selected client plan. No orders or investment approval."
        ),
        p(
            f"Calculated {result.get('calculated_at', 'archived')} / supplied forecast {result.get('forecast_supplied_at', 'archived')}",
            "InvestorSmall",
        ),
        p(
            "Calculation ID: "
            + result.get("result_id", "unavailable")
            + " / training run: "
            + (training or {}).get("run_id", "unavailable"),
            "InvestorSmall",
        ),
        p(
            "Capital allocation, signed variance contribution and economic role",
            "InvestorHeading",
        ),
    ]
    rows = [["Asset", "Economic role / candidate use", "Capital", "Variance"]]
    for symbol, role in ASSET_ROLES.items():
        w = result["cash"] if symbol == "USD_CASH" else result["weights"].get(symbol, 0)
        rows.append(
            [
                symbol,
                role + (" Allocated." if w > 1e-8 else " Not allocated."),
                percent(w),
                percent(result["risk_contributions"][symbol]),
            ]
        )
    role_table = table(rows, [65, width - 207, 70, 72], s["InvestorSmall"])
    role_table.setStyle(
        TableStyle(
            [
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story += [
        role_table,
        p(
            "Cash is separate from invested Treasury reserves. Negative variance shares are estimated offsets, not negative holdings. Zero-variance cash-only accounts have undefined percentage risk shares.",
            "InvestorSmall",
        ),
        PageBreak(),
        p("Macro-conditioned scenarios", "InvestorTitle"),
        p(
            f"Forecast tilt remains capped at {percent(result['forecast_tilt_weight'])}. Current market covariance and strategy risk limits were retained.",
            "InvestorSmall",
        ),
    ]
    rows = [["Supplied future economic regime", "Scenario weight"]] + [
        [r.replace("_", " ").title(), percent(result["forecast_weights"][r])]
        for r in result["forecast_weights"]
    ]
    story.append(table(rows, [width * 0.72, width * 0.28], s["InvestorSmall"]))
    sim = result.get("simulation", {})
    if sim.get("status") == "CONDITIONAL_RESEARCH_SCENARIOS":
        story.append(
            p(
                f"{sim['paths']} paths / {sim['quarters']} quarters ({sim['quarters'] * 63} market sessions)",
                "InvestorHeading",
            )
        )
        metrics = [
            ("Median total return", sim["median_return"]),
            (
                "5th / 95th percentile total return",
                percent(sim["p05_return"]) + " / " + percent(sim["p95_return"]),
            ),
            ("Median annualized volatility", sim["median_annualized_volatility"]),
            ("95th percentile maximum account drawdown", sim["p95_max_drawdown"]),
            ("Conditional terminal-loss frequency", sim["terminal_loss_frequency"]),
            (
                "Horizon VaR / expected shortfall 95%",
                percent(sim["horizon_var95_loss"])
                + " / "
                + percent(sim["horizon_es95_loss"]),
            ),
            (
                "Conditional frequency of >5% drawdown",
                sim["five_percent_drawdown_exceedance"],
            ),
        ]
        story.append(
            table(
                [["Conditional scenario metric", "Estimate"]]
                + [
                    [k, percent(v) if isinstance(v, (float, int)) else v]
                    for k, v in metrics
                ],
                [width * 0.72, width * 0.28],
                s["InvestorSmall"],
            )
        )
        story += [
            p("Median simulated wealth index", "InvestorHeading"),
            LineChart(
                [1, *sim["fan"][1]],
                ["Decision", "Scenario horizon"],
                width=width,
                height=150,
            ),
            p(
                "Pointwise uncertainty bands and asset risk chart are available interactively. These estimates are not calibrated future probabilities or guaranteed loss limits.",
                "InvestorSmall",
            ),
        ]
    else:
        story.append(
            p(
                "Simulation unavailable: insufficient regime-specific observed history. No source observations have been invented."
            )
        )
    story += [PageBreak(), p("Risk controls and training evidence", "InvestorTitle")]
    budgets = result.get("requested_risk_budgets")
    feasible = result.get("feasible_risk_budgets")
    rows = [["Economic sleeve", "Requested / feasible variance budget"]]
    for i, name in enumerate(
        ["Equities", "Nominal bonds", "Inflation-linked bonds", "Gold", "Commodities"]
    ):
        rows.append(
            [
                name,
                (percent(budgets[i]) + " / " + percent(feasible[i]))
                if budgets and feasible
                else "Cash-only / unavailable",
            ]
        )
    story += [
        table(rows, [width * 0.5, width * 0.5], s["InvestorSmall"]),
        p(
            f"Forecast volatility {percent(result['forecast_annual_volatility'])}; cash {percent(result['cash'])}; risk-budget residual {result['risk_budget_error']:.2e}.",
            "InvestorSmall",
        ),
        p(
            f"Carried hypothetical-account drawdown {percent(result['account']['drawdown'])}; persistent cash lock {result['account']['locked']}. Drawdowns are measured; the current policy has no fixed account drawdown lock or return target.",
            "InvestorSmall",
        ),
    ]
    if training:
        gate = training["classifier"]["latest_gate"]
        story += [
            p("Frozen later-period strategy evaluation", "InvestorHeading"),
            p(
                f"{training['evaluation']['start']} to {training['evaluation']['end']}; source market session {training['market_session']}; data-quarantine decisions: {training['evaluation_quarantined_sessions']}.",
                "InvestorSmall",
            ),
        ]
        rows = [["Strategy", "Net return", "Maximum drawdown", "Volatility"]]
        for row in training["strategies"]:
            rows.append(
                [
                    row["name"].replace("_", " ").title(),
                    percent(row["metrics"]["total_return"]),
                    percent(row["metrics"]["max_drawdown"]),
                    percent(row["metrics"]["volatility"]),
                ]
            )
        story.append(
            table(
                rows,
                [width * 0.43, width * 0.19, width * 0.19, width * 0.19],
                s["InvestorSmall"],
            )
        )
        story.append(
            p(
                f"Latest model alpha gate {'enabled' if gate['enabled'] else 'OFF - frequency baseline retained'}. Fitting a classifier does not demonstrate predictive advantage.",
                "InvestorSmall",
            )
        )
    story += [p("Simulation assumptions", "InvestorHeading")] + [
        p(note, "InvestorSmall") for note in sim.get("assumptions", [])
    ]
    return story


def render_allocation_pdf(result, destination, training=None, *, contract=None):
    if not result.get("weights"):
        raise ValueError("No feasible candidate to export")
    from portfolio_contract import validate_contract

    if contract:
        validate_contract(contract)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(suffix=".pdf", dir=path.parent)
    os.close(fd)

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, A4[1] - 45, A4[0], 45, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(50, A4[1] - 29, "REGIME / MACRO ALLOCATION LAB")
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(
            50,
            25,
            "Private shadow strategy / no orders / conditional research scenarios",
        )
        canvas.drawRightString(A4[0] - 50, 25, f"Page {doc.page}")
        canvas.restoreState()

    try:
        SimpleDocTemplate(
            temporary,
            pagesize=A4,
            leftMargin=50,
            rightMargin=50,
            topMargin=64,
            bottomMargin=46,
            title="REGIME macro-driven strategy allocation",
        ).build(
            allocation_flowables(result, training)
            + (
                [
                    paragraph(
                        "Portfolio contract: "
                        + contract["contract_id"]
                        + " / valuation "
                        + contract["valuation_session"],
                        styles()["InvestorSmall"],
                    )
                ]
                if contract
                else []
            ),
            onFirstPage=decorate,
            onLaterPages=decorate,
        )
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()
    return path
