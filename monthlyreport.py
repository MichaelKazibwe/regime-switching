"""Build evidence-based monthly paper portfolio summaries and personalized PDFs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re
import tempfile
from zoneinfo import ZoneInfo

from paperstore import SQLitePaperStore
from tradingcalendar import TradingCalendar

REPORT_VERSION = 2
NY = ZoneInfo("America/New_York")


class MonthlyReportError(RuntimeError):
    pass


def number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def period_bounds(month: str):
    if not isinstance(month, str) or not re.fullmatch(r"[12][0-9]{3}-(0[1-9]|1[0-2])", month):
        raise MonthlyReportError("Month must be YYYY-MM")
    year, value = map(int, month.split("-"))
    start = datetime(year, value, 1, tzinfo=NY)
    end = datetime(year + (value == 12), 1 if value == 12 else value + 1, 1, tzinfo=NY)
    return start, end


def previous_month(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise MonthlyReportError("Scheduler clock must be timezone-aware")
    now = now.astimezone(NY)
    year, month = (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)
    return f"{year:04d}-{month:02d}"


def timestamp(value):
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise MonthlyReportError("Saved report timestamps must be timezone-aware")
    return stamp.astimezone(NY)


def metrics(record):
    return ((record.get("decision") or {}).get("paper_execution") or {}).get("operator_metrics") or {}


def build_summary(reports_directory: Path, month: str, *, database=None, now=None, portfolio_id="paper-default", macro_features=None, macro_forecasts=None, latest_macro_features=None):
    start, end = period_bounds(month)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or end > now:
        raise MonthlyReportError("Only completed months can be reported")
    records = []
    for path in sorted(reports_directory.glob("*.json")):
        if path.is_symlink():
            raise MonthlyReportError("Report source cannot be a symlink")
        raw = path.read_bytes()
        try:
            record = json.loads(raw)
            stamp = timestamp(record.get("data_as_of") or record.get("updated_at"))
            if not isinstance(metrics(record), dict) or not isinstance(metrics(record).get("positions_by_market_value") or {}, dict):
                raise ValueError("Invalid financial metrics")
        except (ValueError, TypeError, AttributeError) as exc:
            raise MonthlyReportError(f"Invalid saved report: {path.name}") from exc
        if stamp < end:
            records.append({"report": record, "stamp": stamp, "file": path.name,
                            "sha256": hashlib.sha256(raw).hexdigest()})
    records.sort(key=lambda item: (item["stamp"], str(item["report"].get("updated_at", ""))))
    selected = [item for item in records if item["stamp"] >= start]
    before = [item for item in records if item["stamp"] < start and number(metrics(item["report"]).get("portfolio_value")) is not None]
    opening = before[-1] if before else None
    sources = ([opening] if opening else []) + selected
    verified = False
    if sources and database and Path(database).is_file():
        store = SQLitePaperStore(database, read_only=True)
        if not store.integrity_check()["healthy"]:
            raise MonthlyReportError("Paper database integrity verification failed")
        for item in sources:
            report = item["report"]
            if not report.get("event_id") and number(metrics(report).get("portfolio_value")) is None:
                continue  # Failed cycles have operator reports but may have no decision event.
            event = store.get_event(report.get("event_id", ""))
            if (event is None or event.event_hash != report.get("event_hash")
                    or event.event_type != "PAPER_DECISION_CYCLE"
                    or event.payload.get("cycle_id") != report.get("cycle_id")
                    or (event.payload.get("result") or {}).get("status") != report.get("status")
                    or event.payload.get("result") != report.get("decision")
                    or event.payload.get("data_as_of") != report.get("data_as_of")):
                raise MonthlyReportError(f"Saved report does not match database evidence: {item['file']}")
        verified = True
    calendar = TradingCalendar()
    expected = []

    day = start
    while day < end:
        if calendar.is_trading_day(day):
            expected.append(day.date().isoformat())
        day += timedelta(days=1)
    observed = {}
    for item in selected:
        report = item["report"]
        nav = number(metrics(report).get("portfolio_value"))
        if nav is not None and nav >= 0:
            observed[item["stamp"].date().isoformat()] = item
    valuations = sorted(observed.values(), key=lambda item: item["stamp"])
    closing = valuations[-1] if valuations else None
    expected_opening = calendar.latest_completed_session(start)
    expected_closing = calendar.latest_completed_session(end)
    opening_valid = bool(opening and opening["stamp"].date() == expected_opening.date())
    closing_valid = bool(closing and closing["stamp"].date() == expected_closing.date())
    a = metrics(opening["report"]) if opening else {}
    b = metrics(closing["report"]) if closing else {}
    opening_nav, closing_nav = number(a.get("portfolio_value")), number(b.get("portfolio_value"))
    monthly_return = closing_nav / opening_nav - 1 if opening_valid and closing_valid and opening_nav and closing_nav is not None else None
    bench_a, bench_b = number(a.get("benchmark_return_since_first_observation")), number(b.get("benchmark_return_since_first_observation"))
    benchmark_return = ((1 + bench_b) / (1 + bench_a) - 1
                        if opening_valid and closing_valid and bench_a is not None and bench_b is not None
                        and bench_a > -1 and a.get("benchmark") == b.get("benchmark") else None)
    peak = opening_nav if opening_valid and opening_nav else None
    drawdown = None
    for item in valuations:
        nav = number(metrics(item["report"])["portfolio_value"])
        peak = max(peak or nav, nav)
        if peak:
            drawdown = min(drawdown or 0, nav / peak - 1)

    def delta(key):
        first, last = number(a.get(key)), number(b.get(key))
        return last - first if opening_valid and closing_valid and first is not None and last is not None and last >= first else None

    missing = [day for day in expected if day not in observed]
    counts = {}
    rebalances = orders = 0
    regimes = {}
    for item in selected:
        report = item["report"]
        status = str(report.get("status", "UNKNOWN"))
        counts[status] = counts.get(status, 0) + 1
        execution = (report.get("decision") or {}).get("paper_execution") or {}
        rebalances += execution.get("status") == "EXECUTED"
        orders += len(execution.get("orders") or [])
        regime = (report.get("decision") or {}).get("regime")
        if regime:
            regimes[str(regime)] = regimes.get(str(regime), 0) + 1
    source_files = [{key: item[key] for key in ("file", "sha256")} for item in sources]
    latest_overlay = None
    if latest_macro_features:
        if any(timestamp(r['as_of']) > now for r in latest_macro_features):
            raise MonthlyReportError('Future latest-macro availability timestamp')
        latest_overlay = macro_context_for_monthly(latest_macro_features, now)

    from investor_analytics import macro_context
    macro = macro_context(macro_features, (end - timedelta(microseconds=1)).isoformat(), forecasts=macro_forecasts) if macro_features else {"status": "UNAVAILABLE", "reason": "No dated macro archive attached to this monthly report."}

    return {
        "schema_version": REPORT_VERSION, "month": month, "portfolio_id": portfolio_id,
        "macro_context": macro,
        "latest_macro_overlay": latest_overlay,
        "source_fingerprint": hashlib.sha256(json.dumps(source_files, sort_keys=True).encode()).hexdigest(),
        "sources": source_files, "database_verified": verified, "cycle_count": len(selected),
        "coverage": "NO_DATA" if not valuations else "COMPLETE" if not missing and opening_valid and closing_valid else "PARTIAL",
        "expected_sessions": len(expected), "observed_sessions": len(observed), "missing_sessions": missing,
        "opening_boundary_available": opening_valid, "closing_boundary_available": closing_valid,
        "opening_nav": opening_nav if opening_valid else None, "closing_nav": closing_nav,
        "last_observation": closing["stamp"].isoformat() if closing else None,
        "monthly_return": monthly_return, "benchmark_return": benchmark_return,
        "active_return": monthly_return - benchmark_return if monthly_return is not None and benchmark_return is not None else None,
        "benchmark": b.get("benchmark", "SPY"), "observed_drawdown": drawdown,
        "monthly_costs": delta("cumulative_transaction_costs"), "monthly_turnover": delta("cumulative_turnover"),
        "cash": number(b.get("cash")), "holdings": b.get("positions_by_market_value") or {},
        "status_counts": counts, "regime_counts": regimes, "rebalances": rebalances, "orders": orders,
        "nav_history": [{"date": item["stamp"].date().isoformat(), "nav": number(metrics(item["report"])["portfolio_value"])}
                        for item in (([opening] if opening_valid else []) + valuations)],
    }



def macro_context_for_monthly(features, now):
    from investor_analytics import macro_context
    if any(r.get("source_kind") != "CURRENT_REVISED_FRED_NOT_HISTORICAL_VINTAGES" for r in features):
        raise MonthlyReportError("Latest overlay requires explicitly current/revised FRED features")
    value = macro_context(features, now.isoformat())
    if value.get("status") != "UNAVAILABLE":
        value["limitations"][0] = "Latest informational FRED snapshot, independent of the completed reporting month; training history is revised as of retrieval."
    return value


def money(value):
    return f"${value:,.2f}" if number(value) is not None else "Unavailable"


def pct(value, *, signed=True):
    return (f"{value:+.2%}" if signed else f"{value:.2%}") if number(value) is not None else "Unavailable"


def create_pdf(summary, *, user_id: str, name: str, output_directory: Path):
    """Publish an immutable PDF/summary pair; reuse it only after hash verification."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", user_id) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", summary["portfolio_id"]):
        raise MonthlyReportError("User and portfolio IDs must be safe identifiers")
    identity = {"summary": summary, "user_id": user_id, "name": name, "template_version": REPORT_VERSION,
                "renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, allow_nan=False).encode()).hexdigest()
    destination = output_directory / summary["portfolio_id"] / summary["month"] / user_id / fingerprint
    if destination.exists():
        metadata = json.loads((destination / "manifest.json").read_text())
        if (metadata["report_id"] != fingerprint
                or hashlib.sha256((destination / "report.pdf").read_bytes()).hexdigest() != metadata["pdf_sha256"]
                or hashlib.sha256((destination / "summary.json").read_bytes()).hexdigest() != metadata["summary_sha256"]):
            raise MonthlyReportError("Existing monthly PDF artifact is corrupt")
        return {**metadata, "pdf": destination / "report.pdf"}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
        root = Path(directory) / "artifact"
        root.mkdir(mode=0o700)
        generated_at = datetime.now(timezone.utc).isoformat()
        _render_pdf(root / "report.pdf", summary, name, fingerprint, generated_at)
        (root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n")
        metadata = {"report_id": fingerprint, "pdf_sha256": hashlib.sha256((root / "report.pdf").read_bytes()).hexdigest(),
                    "summary_sha256": hashlib.sha256((root / "summary.json").read_bytes()).hexdigest(),
                    "generated_at": generated_at, "month": summary["month"], "portfolio_id": summary["portfolio_id"], "user_id": user_id}
        (root / "manifest.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
        for path in root.iterdir():
            path.chmod(0o600)
        root.rename(destination)
    return {**metadata, "pdf": destination / "report.pdf"}


def _render_pdf(path, summary, name, report_id, generated_at):
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font_root = Path(reportlab.__file__).parent / "fonts"
    for font, filename in (("Regime", "Vera.ttf"), ("RegimeBold", "VeraBd.ttf")):
        if font not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(font, str(font_root / filename)))
    navy, teal, muted = colors.HexColor("#152c42"), colors.HexColor("#008775"), colors.HexColor("#677e90")
    border, pale = colors.HexColor("#dfe7ed"), colors.HexColor("#f2f6f8")
    styles = getSampleStyleSheet()
    for key in ("Normal", "BodyText"):
        styles[key].fontName = "Regime"
        styles[key].fontSize = 8.5
        styles[key].leading = 13
        styles[key].textColor = navy
    styles.add(ParagraphStyle("ReportTitle", fontName="RegimeBold", fontSize=25, leading=32, textColor=navy, spaceAfter=8))
    styles.add(ParagraphStyle("Section", fontName="RegimeBold", fontSize=13, leading=19, textColor=navy, spaceBefore=15, spaceAfter=9))
    styles.add(ParagraphStyle("Small", parent=styles["BodyText"], fontSize=7.5, leading=11, textColor=muted))
    styles.add(ParagraphStyle("Metric", fontName="RegimeBold", fontSize=15, leading=23, textColor=teal))
    styles.add(ParagraphStyle("Right", parent=styles["Small"], alignment=TA_RIGHT))
    def p(text, style="BodyText"):
        return Paragraph(escape(str(text)), styles[style])
    period = datetime.strptime(summary["month"], "%Y-%m").strftime("%B %Y")
    story = [p("MONTHLY PAPER PORTFOLIO REPORT", "Small"), p(period, "ReportTitle"),
             p(f"Prepared for {name}"), Spacer(1, 15)]
    coverage = f"{summary['coverage'].replace('_', ' ')}  |  {summary['observed_sessions']} of {summary['expected_sessions']} NYSE sessions recorded"
    band = Table([[p(coverage)]], colWidths=[499])
    band.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,-1), pale), ("BOX",(0,0),(-1,-1),.5,border), ("LEFTPADDING",(0,0),(-1,-1),12), ("TOPPADDING",(0,0),(-1,-1),9), ("BOTTOMPADDING",(0,0),(-1,-1),9)]))
    story += [band, Spacer(1,18)]
    labels = ["Closing NAV" if summary["closing_boundary_available"] else "Last observed NAV", "Month return", f"{summary['benchmark']} month return", "Observed drawdown"]
    values = [money(summary["closing_nav"]), pct(summary["monthly_return"]), pct(summary["benchmark_return"]), pct(summary["observed_drawdown"], signed=False)]
    def metric_cell(value):
        width = pdfmetrics.stringWidth(value, "RegimeBold", 15)
        size = min(15, 112 / max(width, 1) * 15)
        style = ParagraphStyle("MetricFit", parent=styles["Metric"], fontSize=size, leading=23)
        return Paragraph(escape(value), style)

    cards = Table([[p(label,"Small") for label in labels], [metric_cell(value) for value in values]], colWidths=[125,125,125,124])
    cards.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"), ("LEFTPADDING",(0,0),(-1,-1),0), ("BOTTOMPADDING",(0,0),(-1,0),4)]))
    story += [cards, p("Saved net asset value", "Section")]

    class NavChart(Flowable):
        def __init__(self):
            super().__init__()
            self.width, self.height = 499, 155

        def draw(self):
            canvas = self.canv
            points = summary["nav_history"]
            if not points:
                canvas.setFillColor(pale)
                canvas.roundRect(0, 0, self.width, self.height, 5, fill=1, stroke=0)
                canvas.setFillColor(muted)
                canvas.setFont("Regime", 10)
                canvas.drawCentredString(249, 81, "No saved valuations are available for this month.")
                canvas.setFont("Regime", 8)
                canvas.drawCentredString(249, 62, "Results appear here once monthly valuation records are available.")
                return
            values = [item["nav"] for item in points]
            low, high = min(values), max(values)
            padding = (high-low)*.15 or max(high*.01,1)
            low, high = low-padding, high+padding
            def x(index):
                return 7 + (index / max(len(points)-1,1))*420

            def y(value):
                return 24 + (value-low)/(high-low)*111
            for index in range(4):
                value = low + (high-low)*index/3
                canvas.setStrokeColor(border)
                canvas.line(0,y(value),430,y(value))
                canvas.setFont("Regime",7)
                canvas.setFillColor(muted)
                canvas.drawRightString(499,y(value)-3,f"${value:,.0f}")
            canvas.setStrokeColor(teal)
            canvas.setLineWidth(1.7)
            path = canvas.beginPath()
            path.moveTo(x(0),y(values[0]))
            for index,value in enumerate(values[1:],1):
                path.lineTo(x(index),y(value))
            canvas.drawPath(path)
            canvas.setFillColor(teal)
            canvas.circle(x(len(points)-1),y(values[-1]),2.5,fill=1,stroke=0)
            canvas.setFillColor(muted)
            canvas.setFont("Regime",7)
            canvas.drawString(0,6,points[0]["date"])
            canvas.drawRightString(430,6,points[-1]["date"])

    story += [NavChart(), p("Coverage and calculation notes", "Section")]
    notes = ["All figures describe the shared paper portfolio and saved historical valuations, not live brokerage assets.",
             "Month returns use the prior month's closing NAV and this month's closing NAV. A missing boundary is reported as unavailable; returns are not inferred from an incomplete period.",
             "Observed drawdown uses the available valuations within the month and the opening NAV when available. Missing sessions can understate drawdown."]
    if summary["coverage"] == "NO_DATA":
        notes.insert(0, "No saved paper valuation records were available for this month. This report does not establish that the account had no activity.")
    if not summary["database_verified"] and summary["sources"]:
        notes.insert(0, "PREVIEW: saved source records have not been verified against the paper database. Email delivery is blocked until verification succeeds.")
    if summary.get("kind") == "CONTRACT_BOUND_PROSPECTIVE_SHADOW":
        notes.insert(0,"Contract-bound shadow portfolio: " + summary["portfolio_id"] + ". USD values scale a declared illustrative notional, not a broker balance. Synthetic adjusted-return notionals are not shares.")
        notes += ["Portfolio contract: " + c["contract_id"] + " / valuation " + c["valuation_session"] for c in summary.get("portfolio_contracts",[])]
    for note in notes:
        story += [p(note,"Small"), Spacer(1,6)]
    story += [PageBreak(), p("Holdings and operations", "ReportTitle"),
              p("Last observed valuation: " + (summary["last_observation"] or "Unavailable"),"Small"), Spacer(1,14)]
    rows = [[p(text,"Small") for text in ("ASSET","SHARES","SAVED MARKET VALUE","WEIGHT")]]
    holdings = summary["holdings"]
    for symbol, position in sorted(holdings.items(), key=lambda item: number(item[1].get("market_value")) or 0, reverse=True):
        rows.append([p(symbol), p(f"{position['shares']:,.4f}" if number(position.get("shares")) is not None else "Unavailable"),
                     p(money(position.get("market_value"))), p(pct(position.get("weight"), signed=False))])
    if len(rows) == 1:
        rows.append([p("No saved holdings available"),p("-"),p("-"),p("-")])
    table = Table(rows, colWidths=[140,105,155,99], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),pale), ("LINEBELOW",(0,0),(-1,-1),.4,border),
                               ("VALIGN",(0,0),(-1,-1),"TOP"), ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4)]))
    story += [table, p("Monthly activity", "Section")]
    details = [("Opening NAV", money(summary["opening_nav"])), ("Recorded cycles", str(summary["cycle_count"])), ("Completed rebalances / simulated orders", f"{summary['rebalances']} / {summary['orders']}"),
               ("Period transaction costs", money(summary["monthly_costs"])), ("Period turnover", f"{summary['monthly_turnover']:.2f}x" if summary["monthly_turnover"] is not None else "Unavailable"),
               ("Active return versus benchmark", pct(summary["active_return"])), ("Last recorded cash", money(summary["cash"])),
               ("Cycle status counts", ", ".join(f"{key}: {value}" for key,value in summary["status_counts"].items()) or "No recorded cycles"),
               ("Regime observations", ", ".join(f"{key}: {value}" for key,value in summary["regime_counts"].items()) or "No recorded regimes")]
    operations = Table([[p(key,"Small"),p(value)] for key,value in details], colWidths=[235,264])
    operations.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"), ("TOPPADDING",(0,0),(-1,-1),3.5), ("BOTTOMPADDING",(0,0),(-1,-1),3.5)]))
    story += [operations, Spacer(1,12), p(f"Evidence reference: {report_id[:20]}. Source records: {len(summary['sources'])}. Missing sessions: {len(summary['missing_sessions'])}.","Small")]

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(navy)
        canvas.rect(0,A4[1]-51,A4[0],51,fill=1,stroke=0)
        canvas.setFont("RegimeBold",13)
        canvas.setFillColor(colors.white)
        canvas.drawString(48,A4[1]-31,"REGIME")
        canvas.setFont("Regime",7)
        canvas.drawRightString(A4[0]-48,A4[1]-29,"PORTFOLIO INTELLIGENCE / PAPER")
        canvas.setStrokeColor(border)
        canvas.line(48,43,A4[0]-48,43)
        canvas.setFillColor(muted)
        canvas.setFont("Regime",6.5)
        canvas.drawString(48,31,f"{period} | Monthly period: New York | Generated: {timestamp(generated_at).astimezone(ZoneInfo('Europe/Warsaw')).strftime('%d %b %Y %H:%M')} Warsaw")
        canvas.drawRightString(A4[0]-48,20,f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=48, rightMargin=48, topMargin=76, bottomMargin=57,
                            title=f"REGIME monthly paper report - {period}", author="REGIME Portfolio Intelligence")
    from investor_pdf import macro_flowables
    story += [PageBreak()] + macro_flowables(summary.get("macro_context"), width=499)
    if summary.get("latest_macro_overlay"):
        story += [PageBreak(), p("Latest macro overlay - captured after the reporting month; does not change the month's account results.", "Small")]
        story += macro_flowables(summary["latest_macro_overlay"], width=499)
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
