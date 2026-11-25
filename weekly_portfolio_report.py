"""Source-bound printable companion to the weekly research dashboard."""

from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, PageBreak


def report_pdf(data, output):
    styles = getSampleStyleSheet()
    styles["BodyText"].fontSize = 9
    styles["BodyText"].leading = 12
    story = []
    def paragraph(text, style="BodyText"):
        item = Paragraph(escape(str(text)), styles[style])
        item.spaceAfter = 5
        story.append(item)
    def table(rows, widths):
        wrapped = [[Paragraph(escape(str(cell)), styles["BodyText"]) for cell in row] for row in rows]
        t = Table(wrapped, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ede9fe")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, -1), .3, colors.HexColor("#dddde5"))]))
        t.spaceAfter = 14
        story.append(t)
    def pct(value):
        return "Unavailable" if value is None else f"{value:.2%}"
    paragraph("Weekly portfolio research", "Title")
    paragraph(f"Completed market week: {data['market_session']} | Client review required", "Heading2")
    paragraph("Three adaptive holding periods plus an aggregate strategy. No trading authority.")
    paragraph(data["methodology"])
    table([["Candidate", "Model volatility", "Effective holdings", "Cash"]] + [
        [c["policy"]["label"], pct(c["estimated_volatility"]), f"{c['effective_holdings']:.1f}",
         pct(c["group_weights"].get("cash", 0))] for c in data["candidates"].values()], [180, 110, 105, 105])
    paragraph("How to interpret the dashboard", "Heading2")
    for warning in data["limitations"]:
        paragraph(warning)
    paragraph(f"Observed sample: {data['first_week']} to {data['market_session']}; {data['weekly_observations']} weekly returns.")
    paragraph("Eligible symbols: " + ", ".join(data["eligible_symbols"]))
    paragraph("Excluded for insufficient complete history: " + (", ".join(data["excluded_insufficient_history"]) or "None"))
    for candidate in data["candidates"].values():
        story.append(PageBreak())
        paragraph(candidate["policy"]["label"].replace("·", "-"), "Title")
        if candidate.get("strategy_mix"):
            paragraph("Data-optimized strategy proportions", "Heading2")
            table([["Horizon sleeve", "Weight"]] + [[name, pct(weight)] for name, weight in candidate["strategy_mix"].items()], [360, 140])
            paragraph(candidate["strategy_note"])
        paragraph(f"Selected risky assets: {candidate.get('asset_count', 'See allocation table')}. Weights refresh from completed market data.")
        paragraph("Capital allocation and signed variance contributions", "Heading2")
        table([["Asset / exposure", "Weight", "Risk share", "Bucket"]] + [
            [f"{r['symbol']} / {r['region']}", pct(r["weight"]), pct(r["risk_share"]), r["bucket"]]
            for r in candidate["allocations"]], [235, 75, 80, 110])
        paragraph("Conditional projections - not calibrated predictions", "Heading2")
        table([["Period", "5th / median / 95th return", "Loss frequency", "95th drawdown"]] + [
            [label, " / ".join(pct(p[k]) for k in ("p05_return", "median_return", "p95_return")),
             pct(p["loss_frequency"]), pct(p["p95_drawdown"])]
            for label, p in [(label, candidate["projections"][key]) for label, key in
                (("Month (4w)", "4"), ("Quarter (13w)", "13"), ("Year (52w)", "52"), ("3 years (156w)", "156"))]],
            [95, 215, 95, 95])
        paragraph("Causal historical replay and stress", "Heading2")
        replay = candidate["replay"]
        paragraph(f"{replay['weeks']} weekly returns; total return {pct(replay['total_return'])}; volatility "
                  f"{pct(replay['annualized_volatility'])}; weekly-close drawdown {pct(replay['max_drawdown'])}. {replay['timing']}. {replay['note']}.")
        baseline = candidate["baseline_60_40"]
        paragraph(f"Same-period 60% SPY / 40% IEF reference: return {pct(baseline['total_return'])}; "
                  f"weekly-close drawdown {pct(baseline['max_drawdown'])}; same next-close fills and costs. "
                  "This historical comparison does not establish future outperformance.")
        stress = candidate["historical_static_stress"]
        paragraph(f"Worst observed fixed-weight 13-week block ending {stress['end']}: {pct(stress['return_13w'])}. {stress['note']}.")
        for name, loss in candidate["declared_shocks"].items():
            paragraph(f"Declared hypothetical {name.lower()}: {pct(loss)} before fees. Shocks are assumptions, not predictions.")
        paragraph("Why these holdings", "Heading2")
        for row in candidate["allocations"]:
            paragraph(f"{row['symbol']} - {row['justification']}")
        paragraph("Diversification by mandate", "Heading2")
        table([["Exposure label (not country look-through)", "Capital weight"]] + [
            [name, pct(weight)] for name, weight in candidate["exposure_labels"].items()], [360, 140])
        paragraph("Underlying holdings evidence", "Heading2")
        exposure = candidate.get("economic_exposures")
        if exposure is None:
            paragraph("Not supplied. Registered geographic labels are not verified underlying holdings coverage.")
        else:
            paragraph(f"Review status: {exposure['status']}; risky capital covered: "
                      f"{pct(exposure['covered_risky_fraction'])}; cutoff: {exposure['evidence_cutoff']}.")
            paragraph("Supplied reviewed-file integrity only; independent issuer authentication, rights and execution approval remain separate. Limits are post-optimization review checks.")
            for breach in exposure['breaches']:
                paragraph(f"Review exception: {breach['dimension']} / {breach['exposure']}: "
                          f"{pct(breach['weight'])} versus declared limit {pct(breach['limit'])}.")
    story.append(PageBreak())
    paragraph("Dashboard evidence snapshot", "Title")
    context = data.get("dashboard_context", {})
    if context:
        paragraph(f"Saved dashboard market session {context['market_session']}; training {context['training_status']}; "
                  f"macro inputs available: {context['macro_available']}; engine status {context['engine_status']}; "
                  f"dynamic strategy status {context['dynamic_status']}.")
        paragraph("The following saved plans use their own dated assumptions and are separate from the weekly candidates. "
                  "Their expected returns are unvalidated planning priors, not the weekly model projections.")
        for plan in context["plans"]:
            paragraph(plan["title"], "Heading2")
            paragraph(f"Status {plan['status']}; planning volatility {pct(plan['volatility'])}; "
                      f"unvalidated planning return {pct(plan['expected_return'])}.")
            table([["Saved holding", "Weight"]] + [[s, pct(w)] for s, w in plan["weights"].items() if w > 0], [360, 140])
            for warning in plan["limitations"]:
                paragraph(warning)
        growth = context["growth"]
        paragraph(growth["name"], "Heading2")
        paragraph(f"Status {growth['status']}; historical window {growth['start']} to {growth['end']}. "
                  "Historical performance is separate from a forecast or a release approval.")
        table([["Growth reference holding", "Weight"]] + [[s, pct(w)] for s, w in growth["weights"].items()], [360, 140])
        metric_rows = [["Historical reference", "Metric", "Value"]]
        for name, values in growth["metrics"].items():
            if isinstance(values, dict):
                for metric in ("total_return", "cagr", "annual_volatility", "maximum_drawdown"):
                    if isinstance(values.get(metric), (int, float)):
                        metric_rows.append([name, metric.replace("_", " "), pct(values[metric])])
        table(metric_rows, [200, 190, 110])
        for warning in growth["limitations"]:
            paragraph(warning)
        paragraph(f"Bound dashboard document SHA-256: {context['document_sha256']}")
    story.append(PageBreak())
    paragraph("Review and evidence", "Title")
    alpha = data.get('macro_alpha_monitor')
    if alpha:
        paragraph("Shared macro alpha research monitor", "Heading2")
        paragraph(f"Signal session {alpha['market_session']}; {alpha['status']}. Separate from weekly candidate weights. "
                  "Experimental 63-session released-condition regime probabilities; no demonstrated forecasting advantage.")
        table([["Regime", "Research probability", "Frequency baseline"]] + [
            [name.replace('_', ' '), pct(alpha['prediction']['probabilities'][i]) if alpha['prediction']['probabilities'] else 'Unavailable',
             pct(alpha['prediction']['baseline'][i])] for i,name in enumerate(alpha['regimes'])], [250,125,125])
        paragraph('Included components: ' + ', '.join(alpha['prediction']['feature_names']))
        for name,reason in alpha['missing_components'].items():
            paragraph(f"Excluded {name}: {reason}")
        paragraph('Research monitoring only. Portfolio alpha activation, risk controls and execution gates are unchanged.')
    paragraph("Before adopting a candidate, review holding period, liquidity needs, tax, product availability, "
              "currency exposure, overlapping underlying holdings, concentration and ability to bear loss. "
              "This report records research only; it does not record client approval.")
    paragraph(f"Research ID: {data['research_id']}")
    for name, digest in data.get("input_evidence", {}).items():
        paragraph(f"{name}: {digest}")
    paragraph("Scope: automated weekly candidates, allocations, projections, stress, saved dashboard plans, training availability and growth-reference evidence. "
              "Existing scenario-specific saved-plan PDFs and cycle-lab downloadable evidence retain their separate complete records. "
              "News is dated third-party context and is not used to optimize these weekly allocations.")
    def footer(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#615878"))
        canvas.drawString(48, 27, f"Weekly research | {data['market_session']} | Review required")
        canvas.drawRightString(548, 27, str(doc.page))
    SimpleDocTemplate(str(output), pagesize=(596, 842), rightMargin=48, leftMargin=48,
                      topMargin=45, bottomMargin=48, title="Weekly portfolio research").build(story, onFirstPage=footer, onLaterPages=footer)
