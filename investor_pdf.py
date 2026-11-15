"""Private investor PDF with dated macro context, full universe and risk charts."""

from __future__ import annotations

from html import escape
import os
from pathlib import Path
import tempfile

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

from assetuniverse import DIVERSIFIED_ASSETS
from investmentcatalog import catalogue

NAVY = colors.HexColor("#153945")
TEAL = colors.HexColor("#177b68")
MUTED = colors.HexColor("#627a7a")
PALE = colors.HexColor("#edf5f2")
LINE = colors.HexColor("#dbe6e1")


def safe(value):
    return escape(
        str(value)
        .replace("–", "-")
        .replace("—", "-")
        .replace("·", "/")
        .replace("→", "to")
    )


def percent(value):
    return f"{100 * value:.2f}%" if isinstance(value, (int, float)) else "Unavailable"


def styles():
    result = getSampleStyleSheet()
    result.add(
        ParagraphStyle(
            name="InvestorTitle",
            fontName="Helvetica",
            fontSize=26,
            leading=31,
            textColor=NAVY,
            spaceAfter=14,
        )
    )
    result.add(
        ParagraphStyle(
            name="InvestorHeading",
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=NAVY,
            spaceBefore=12,
            spaceAfter=9,
        )
    )
    result.add(
        ParagraphStyle(
            name="InvestorBody",
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=NAVY,
            spaceAfter=7,
        )
    )
    result.add(
        ParagraphStyle(
            name="InvestorSmall",
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=MUTED,
            spaceAfter=5,
        )
    )
    return result


def paragraph(value, style):
    return Paragraph(safe(value), style)


def table(rows, widths, style):
    node = Table(
        [[paragraph(v, style) for v in row] for row in rows],
        colWidths=widths,
        repeatRows=1,
        hAlign="LEFT",
    )
    node.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PALE),
                ("LINEBELOW", (0, 0), (-1, -1), 0.35, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return node


class LineChart(Flowable):
    def __init__(
        self, values, labels, *, width=495, height=145, percentage=False, color=TEAL
    ):
        super().__init__()
        self.width, self.height = width, height
        self.values, self.labels, self.percentage, self.color = (
            values,
            labels,
            percentage,
            color,
        )

    def draw(self):
        c = self.canv
        valid = [v for v in self.values if isinstance(v, (int, float))]
        if len(valid) < 2:
            c.setFont("Helvetica", 9)
            c.setFillColor(MUTED)
            c.drawString(
                12, self.height / 2, "No sufficient dated observations available."
            )
            return
        lo, hi = min(valid), max(valid)
        pad = (hi - lo) * 0.15 or 0.01
        lo, hi = lo - pad, hi + pad
        if self.percentage and max(valid) <= 0:
            hi = 0
        left, right, top, bottom = 58, self.width - 12, self.height - 13, 25

        def x(i):
            return left + i / max(1, len(self.values) - 1) * (right - left)

        def y(v):
            return bottom + (v - lo) / (hi - lo) * (top - bottom)

        c.setFont("Helvetica", 7)
        for j in range(4):
            v = lo + (hi - lo) * j / 3
            c.setStrokeColor(LINE)
            c.setLineWidth(0.4)
            c.line(left, y(v), right, y(v))
            c.setFillColor(MUTED)
            c.drawRightString(
                left - 7, y(v) - 2, percent(v) if self.percentage else f"{v:.2f}"
            )
        c.setStrokeColor(self.color)
        c.setLineWidth(1.5)
        path = c.beginPath()
        started = False
        for i, v in enumerate(self.values):
            if not isinstance(v, (int, float)):
                started = False
                continue
            if started:
                path.lineTo(x(i), y(v))
            else:
                path.moveTo(x(i), y(v))
                started = True
        c.drawPath(path)
        c.setFillColor(MUTED)
        c.drawString(left, 6, self.labels[0])
        c.drawRightString(right, 6, self.labels[-1])


def macro_flowables(macro, *, width=495):
    """Reusable section for monthly paper PDFs too; caller must supply dated context."""
    s = styles()

    def p(v, kind="InvestorBody"):
        return paragraph(v, s[kind])

    story = [p("Macroeconomic intelligence", "InvestorTitle")]
    if not macro or macro.get("status") == "UNAVAILABLE":
        return story + [
            p(
                "Macro context unavailable. No dated macro feature archive was attached; no indicators or forecasts have been invented."
            )
        ]
    story += [
        p(
            f"Observed feature snapshot {macro['feature_date']} / available at {macro['as_of']}",
            "InvestorSmall",
        ),
        p(
            f"Dominant observed regime: {macro['current_regime'].replace('_', ' ').title()}"
        ),
        p(
            "Dated macro context; any latest overlay is independent of the saved portfolio. Forecasts are conditional research estimates, not official projections or streaming data.",
            "InvestorSmall",
        ),
    ]
    rows = [["Observed indicator", "Value", "Unit / source observation date"]]
    for i in macro["indicators"]:
        rows.append(
            [
                i["label"],
                f"{i['value']:.2f}",
                i["unit"] + " / " + ", ".join(i["observation_dates"]),
            ]
        )
    story += [
        table(rows, [width * 0.34, width * 0.13, width * 0.53], s["InvestorSmall"]),
        p("Four-quarter conditional outlook", "InvestorHeading"),
    ]
    rows = [
        [
            "Quarter",
            "IP growth %",
            "CPI YoY %",
            "Infl. mom. pp",
            "U mom. pp",
            "10Y-3M pp",
        ]
    ]
    for q in macro.get("quarterly", []):
        values = []
        for key in (
            "ip_growth",
            "inflation_yoy",
            "inflation_change",
            "unemployment_change",
            "yield_curve",
        ):
            v = q["variables"][key]
            values.append(f"{v['median']:.2f} [{v['p05']:.2f}, {v['p95']:.2f}]")
        rows.append([q["quarter"], *values])
    story += [
        table(rows, [width * 0.12] + [width * 0.176] * 5, s["InvestorSmall"]),
        p(
            "Entries: conditional median [5th, 95th percentile]. IP is trailing-six-month annualized growth; U is unemployment momentum. Ranges do not include every source of uncertainty.",
            "InvestorSmall",
        ),
    ]
    rows = [["Quarter", "Dominant scenario regime", "Strategy review lens"]]
    for q in macro.get("quarterly", []):
        rows.append(
            [
                q["quarter"],
                q["dominant_regime"].replace("_", " ").title(),
                q["strategy"],
            ]
        )
    story += [
        table(rows, [width * 0.16, width * 0.40, width * 0.44], s["InvestorSmall"]),
        p(macro["method"], "InvestorSmall"),
    ]
    story += [p(note, "InvestorSmall") for note in macro["limitations"]]
    return story


def render_investor_pdf(result, context, destination):
    s = styles()

    def p(v, kind="InvestorBody"):
        return paragraph(v, s[kind])

    width = A4[0] - 100
    selected = context.get("plans", {}).get(result["recommendation_id"], {})
    macro = selected.get("latest_macro") or selected.get("macro", {})
    diag = selected.get("diagnostics", {})
    weights = result["allocation"].get("weights") or {}
    shares = result["allocation"].get("variance_contributions") or {}
    research = context.get("research_allocation") or {}
    summary = (result.get("simulations") or {}).get("summary", {}).get("proposed", {})
    story = [
        p("Investor portfolio intelligence", "InvestorTitle"),
        p(
            f"{result['mandate']['profile'].title()} / price session {result['price_session']} / {result['mandate']['base_currency']}"
        ),
        p(
            f"{result['qualification']['status']} / saved non-executable plan; no approval or orders created.",
            "InvestorSmall",
        ),
        p(
            f"{sum(v > 1e-8 for k, v in weights.items() if k != 'USD_CASH')} invested ETFs; full 26-ETF core below. Zero weight is a deliberate absence, not a missing holding."
        ),
        p(
            f"Full-horizon scenario median return: {percent(summary.get('median_total_return'))} / P95 drawdown: {percent(summary.get('p95_drawdown_magnitude'))} / horizon: {result['mandate']['horizon_years']} years",
            "InvestorSmall",
        ),
        p("Complete allocation map", "InvestorHeading"),
    ]
    instruments = catalogue()
    rows = [
        ["ETF", "Economic group", "Plan capital", "Variance share", "Research target"]
    ]
    for symbol in DIVERSIFIED_ASSETS:
        rows.append(
            [
                symbol,
                instruments[symbol].bucket.replace("_", " "),
                percent(weights.get(symbol, 0)),
                percent(shares.get(symbol)),
                percent(research.get("weights", {}).get(symbol)),
            ]
        )
    for symbol in ("DBMF", "ALLW", "USD_CASH"):
        rows.append(
            [
                symbol,
                "extended"
                if symbol == "DBMF"
                else "benchmark only"
                if symbol == "ALLW"
                else "cash",
                percent(weights.get(symbol, 0)),
                percent(shares.get(symbol)),
                percent(research.get("cash")) if symbol == "USD_CASH" else "-",
            ]
        )
    story += [
        table(rows, [65, 98, 99, 105, width - 367], s["InvestorSmall"]),
        p(
            f"Research column: archived diversified target {research.get('date', 'unavailable')}; not the selected investor recommendation. Signed variance shares differ from capital weights. Treasury ETFs are invested assets, separate from cash.",
            "InvestorSmall",
        ),
        PageBreak(),
    ]
    if selected.get("latest_macro"):
        story.append(
            p(
                f"Latest macro overlay is informational. Portfolio allocation remains dated {result['price_session']}; no new recommendation or optimization has occurred.",
                "InvestorSmall",
            )
        )
    story += macro_flowables(macro, width=width)
    story += [
        PageBreak(),
        p("Risk metrics and charts", "InvestorTitle"),
        p(
            diag.get(
                "label", diag.get("reason", "No observed price history supplied.")
            ),
            "InvestorSmall",
        ),
    ]
    if diag.get("start"):
        story.append(
            p(
                f"Metrics cover {diag['start']} to {diag['end']}; charts show the latest 1,260 observed sessions.",
                "InvestorSmall",
            )
        )
    metrics = diag.get("metrics", {})
    rows = [
        ["Diagnostic metric", "Value"],
        [
            "Historical annualized volatility",
            percent(metrics.get("annualized_volatility")),
        ],
        ["Historical maximum drawdown", percent(metrics.get("max_drawdown"))],
        ["Daily historical VaR 95%", percent(metrics.get("historical_daily_var95"))],
        [
            "Daily historical expected shortfall 95%",
            percent(metrics.get("historical_daily_es95")),
        ],
        [
            "Planning annual volatility",
            percent(result["allocation"].get("planning_annual_volatility")),
        ],
        [
            "Investor loss preference",
            percent(result["mandate"].get("drawdown_preference")),
        ],
    ]
    story += [table(rows, [width * 0.65, width * 0.35], s["InvestorSmall"])]
    history = diag.get("history", [])
    labels = [row[0] for row in history]
    for title, index, percentage, color in [
        ("Fixed-weight wealth index", 1, False, TEAL),
        ("Peak-to-trough drawdown", 2, True, colors.HexColor("#b77c63")),
        ("63-session annualized volatility", 3, True, TEAL),
    ]:
        story += [
            p(title, "InvestorHeading"),
            LineChart(
                [r[index] for r in history],
                labels,
                width=width,
                height=115,
                percentage=percentage,
                color=color,
            ),
        ]
    story += [
        p(
            diag.get("assumptions", "No historical account performance inferred."),
            "InvestorSmall",
        ),
        PageBreak(),
        p("Portfolio and macro regimes", "InvestorTitle"),
        p(
            "Historical quarter outcomes grouped by conditions known before each quarter; not causal estimates.",
            "InvestorSmall",
        ),
    ]
    rows = [["Starting regime", "Quarters", "Mean quarter return", "P05 / P95 quarter"]]
    for r in diag.get("regimes", []):
        rows.append(
            [
                r["regime"].replace("_", " ").title(),
                r["quarters"],
                percent(r["mean_quarter_return"]),
                percent(r["p05"]) + " / " + percent(r["p95"]),
            ]
        )
    story += [
        table(
            rows,
            [width * 0.4, width * 0.12, width * 0.22, width * 0.26],
            s["InvestorSmall"],
        ),
        p("Conditional portfolio scenarios", "InvestorHeading"),
    ]
    rows = [
        ["Quarter", "Scenario regime", "Historical scenario mean", "Sample coverage"]
    ]
    for q in macro.get("quarterly", []):
        scenario = q.get("portfolio_scenario", {})
        rows.append(
            [
                q["quarter"],
                q["dominant_regime"].replace("_", " ").title(),
                percent(scenario.get("mean_quarter_return")),
                percent(scenario.get("coverage")),
            ]
        )
    story += [
        table(
            rows,
            [width * 0.16, width * 0.38, width * 0.25, width * 0.21],
            s["InvestorSmall"],
        ),
        p(
            "Scenario means weight historical quarter outcomes by simulated regime frequencies. These are not calibrated predictions of future returns. Low-count regimes are excluded; insufficient coverage yields unavailable.",
            "InvestorSmall",
        ),
        p("Strategy review guidance", "InvestorHeading"),
    ]
    for q in macro.get("quarterly", []):
        story += [
            p(f"{q['quarter']}: {q['strategy']}"),
            p(q["guidance"], "InvestorSmall"),
        ]
    story += [p("Original mandate and release limitations", "InvestorHeading")] + [
        p(note, "InvestorSmall") for note in result.get("limitations", [])[:5]
    ]
    allocation_lab = context.get("allocation_lab")
    if allocation_lab:
        from macro_lab_pdf import allocation_flowables

        selected_scenario = allocation_lab["results"]["economic_balance"][
            "latest_model"
        ]
        if selected_scenario.get("weights"):
            story += [PageBreak()] + allocation_flowables(
                selected_scenario, context.get("training"), width=width
            )
    growth = context.get("growth_resilience")
    if growth:
        story += [
            PageBreak(),
            p("Growth & Resilience reference", "InvestorTitle"),
            p(growth["objective"]),
            p(
                f"Observed common history: {growth['start']} to {growth['end']}. Strategic reference; not an approved investor recommendation.",
                "InvestorSmall",
            ),
        ]
        comparison = [["Reference", "CAGR", "Volatility", "Max decline"]]
        for name, values in growth["metrics"].items():
            comparison.append(
                [
                    name,
                    percent(values["cagr"]),
                    percent(values["annual_volatility"]),
                    percent(values["maximum_drawdown"]),
                ]
            )
        story += [
            table(
                comparison,
                [width * 0.43, width * 0.19, width * 0.19, width * 0.19],
                s["InvestorSmall"],
            ),
            p("Diversified capital and asset roles", "InvestorHeading"),
        ]
        allocation = [["Asset", "Capital", "Variance", "Economic role"]]
        for asset in growth["assets"]:
            allocation.append(
                [
                    asset["symbol"],
                    percent(asset["weight"]),
                    percent(asset["variance_share"]),
                    asset["purpose"],
                ]
            )
        story += [
            table(
                allocation,
                [width * 0.12, width * 0.13, width * 0.13, width * 0.62],
                s["InvestorSmall"],
            )
        ]
        story += [p(note, "InvestorSmall") for note in growth["limitations"]]
        story += [
            p(
                "Active objective has no fixed return requirement or account drawdown ceiling. Earlier saved plans retain their original historical assumptions; their targets are superseded for current policy.",
                "InvestorSmall",
            )
        ]
    contracts = context.get("portfolio_contracts", {})
    if contracts:
        from portfolio_contract import validate_contract

        story += [
            PageBreak(),
            p("Portfolio identities and performance basis", "InvestorTitle"),
            p(
                "Current allocations, historical strategy evaluation, and archived investor illustrations have separate identities. These references do not imply approval or broker assets."
            ),
        ]
        for key, contract in contracts.items():
            validate_contract(contract)
            story += [
                p(key.replace("_", " ").title(), "InvestorHeading"),
                p("Contract: " + contract["contract_id"], "InvestorSmall"),
                p(
                    f"Valuation {contract['valuation_session']} / policy {contract['policy_version']} / model {contract['model_run_id']}",
                    "InvestorSmall",
                ),
                p(
                    contract["allocation_basis"].replace("_", " ").capitalize()
                    + " / "
                    + contract["performance_basis"].replace("_", " ").capitalize(),
                    "InvestorSmall",
                ),
            ]
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(suffix=".pdf", dir=destination.parent)
    os.close(fd)

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, A4[1] - 45, A4[0], 45, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(50, A4[1] - 29, "REGIME / INVESTOR INTELLIGENCE")
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(
            50,
            25,
            (
                f"Private shadow strategy / {context['allocation_lab']['market_session']} / No trade authority"
                if context.get("allocation_lab") and doc.page > 4
                else f"Private historical planning preview / {result['price_session']} / No trade authority"
            ),
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
            title="REGIME investor macro and risk report",
            author="REGIME",
        ).build(story, onFirstPage=decorate, onLaterPages=decorate)
        os.replace(temporary, destination)
        destination.chmod(0o600)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()
    return destination
