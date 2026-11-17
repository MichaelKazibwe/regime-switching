"""Local recommendations/simulations product. Never connects to a broker."""

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from assetuniverse import DIVERSIFIED_ASSETS
from clientmandate import CashRate, ClientMandate
from investmentcatalog import catalogue_payload
from productallocation import PlanningCosts
from productreport import private_write, render_report
from recommendationservice import recommend
from recommendationrisk import RecommendationRiskState
from productaudit import archive, archival_arguments, replay


def load_json(path):
    return json.loads(Path(path).read_text())


def save_result(result, output, *, context=None, market=None, pdf=False):
    output = Path(output)
    private_write(
        output / "recommendation.json", json.dumps(result, indent=2, allow_nan=False)
    )
    if context is not None or pdf:
        from investor_dashboard import render_dashboard

        links = {}
        if pdf:
            from investor_pdf import render_investor_pdf

            render_investor_pdf(result, context or {}, output / "investor-report-0.pdf")
            links[result["recommendation_id"]] = "investor-report-0.pdf"
        render_dashboard(
            [result],
            output / "index.html",
            context=context,
            market=market,
            pdf_links=links,
        )
    else:
        render_report(result, output / "index.html")
    if result["allocation"]["weights"]:
        frame = pd.DataFrame(
            {
                "symbol": list(result["allocation"]["weights"]),
                "capital_weight": list(result["allocation"]["weights"].values()),
            }
        )
        private_write(output / "allocation.csv", frame.to_csv(index=False))
    return {
        "profile": result["mandate"]["profile"],
        "status": result["allocation"]["status"],
        "public_release": result["qualification"]["public_recommendations_enabled"],
        "report": str((output / "index.html").resolve()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--latest-macro-features",
        type=Path,
        help="Separate current/revised FRED overlay",
    )
    parser.add_argument(
        "--macro-features",
        type=Path,
        help="Dated point-in-time macro feature JSON for reports",
    )
    parser.add_argument(
        "--macro-forecasts",
        type=Path,
        help="Optional archived 63-session classifier JSON",
    )
    parser.add_argument(
        "--research-allocation",
        type=Path,
        help="Separate archived 26-asset target audit",
    )
    parser.add_argument(
        "--pdf", action="store_true", help="Include private investor PDF reports"
    )
    parser.add_argument(
        "--replay",
        type=Path,
        help="Recommendation JSON containing an input snapshot manifest",
    )
    parser.add_argument("--snapshot-root", type=Path)
    parser.add_argument("--mandate", type=Path)
    parser.add_argument("--prices", type=Path)
    parser.add_argument("--cash-rate", type=Path)
    parser.add_argument("--fx-to-base", type=Path)
    parser.add_argument("--current-weights", type=Path)
    parser.add_argument("--annual-tax-drag", type=Path)
    parser.add_argument(
        "--fund-expenses",
        type=Path,
        help="Annual expense fractions including zero for base cash",
    )
    parser.add_argument("--sale-tax-rates", type=Path)
    parser.add_argument(
        "--costs",
        type=Path,
        help="Observed cost inputs and their source; defaults are illustrative",
    )
    parser.add_argument("--risk-state", type=Path)
    parser.add_argument("--risk-reviewer")
    parser.add_argument("--risk-review-evidence", type=Path)
    parser.add_argument("--equity-fraction", type=float, default=1.0)
    parser.add_argument("--trend-confirmed", action="store_true")
    parser.add_argument("--approval-root", type=Path)
    parser.add_argument("--as-of")
    parser.add_argument("--historical-preview", action="store_true")
    parser.add_argument("--paths", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=Path("var/product-preview"))
    args = parser.parse_args()
    if args.replay:
        if not args.snapshot_root:
            parser.error("--replay requires --snapshot-root")
        print(
            json.dumps(
                replay(args.snapshot_root, load_json(args.replay)["input_snapshot"]),
                indent=2,
            )
        )
        return
    private_write(
        args.output / "instrument-catalogue.json", json.dumps(catalogue_payload(), indent=2)
    )
    if args.demo:
        if args.mandate or args.prices or args.cash_rate or args.as_of:
            parser.error(
                "Demo uses the preserved historical bundle; do not mix current-input flags"
            )
        raw = pd.read_csv(
            "var/research/horizon-analysis/observed-history.csv",
            index_col=0,
            parse_dates=True,
        )
        prices = raw.loc[
            raw.index < pd.Timestamp("2025-10-30"), list(DIVERSIFIED_ASSETS)
        ].copy()
        for symbol, path in [
            ("DBMF", "var/research/three-year-goal-v5/dbmf-observed-prices.csv"),
            (
                "ALLW",
                "var/research/institutional-refinement-v4/allw-observed-prices.csv",
            ),
        ]:
            prices[symbol] = pd.read_csv(path, index_col=0, parse_dates=True)[
                symbol
            ].reindex(prices.index)
        date = "2025-10-29T21:00:00+00:00"
        # Explicit zero-rate demonstration, not a fabricated observed yield.
        rate = CashRate(
            "USD", 0.0, date, "DEMO_EXPLICIT_ZERO_YIELD_NOT_VERIFIED", False
        )
        manifest = []
        profiles = [
            ("preservation", 0.05, 3.0, None),
            ("balanced", 0.20, 7.0, None),
            ("growth", 0.35, 10.0, None),
            ("original_goal", 0.05, 3.0, 0.50),
        ]
        for name, loss, years, target in profiles:
            mandate = ClientMandate(
                "demo-" + name,
                "preservation" if name == "original_goal" else name,
                "USD",
                "",
                "",
                years,
                100000.0,
                loss,
                loss,
                target,
                investment_experience="illustrative",
                allow_alternatives=name in {"balanced", "growth"},
                tax_account_type="tax_exempt",
            )
            result = recommend(
                mandate,
                prices,
                rate,
                decision_time=date,
                historical_preview=True,
                paths=args.paths,
            )
            arguments = archival_arguments(
                decision_time=date,
                fx_to_base=None,
                current=None,
                costs=PlanningCosts(),
                sell_tax_rates=None,
                risk_state=None,
                equity_fraction=1.0,
                trend_confirmed=False,
                historical_preview=True,
                paths=args.paths,
                annual_tax_drag=None,
            )
            result["input_snapshot"] = archive(
                args.output / name / "snapshots",
                result,
                mandate,
                prices,
                rate,
                arguments,
            )
            from investor_analytics import build_context
            from investor_dashboard import market_payload

            display_context = build_context(
                [result],
                prices=prices,
                features_path=args.macro_features,
                forecasts_path=args.macro_forecasts,
                research_allocation_path=args.research_allocation,
                latest_features_path=args.latest_macro_features,
            )
            manifest.append(
                save_result(
                    result,
                    args.output / name,
                    context=display_context,
                    market=market_payload(prices, {result["price_session"]}),
                    pdf=args.pdf,
                )
            )
        private_write(
            args.output / "demo-manifest.json",
            json.dumps(
                {
                    "mode": "HISTORICAL_ILLUSTRATIONS_NOT_CLIENT_RECOMMENDATIONS",
                    "catalogue_count": len(catalogue_payload()),
                    "reports": manifest,
                    "prices_sha256": hashlib.sha256(
                        prices.to_csv().encode()
                    ).hexdigest(),
                },
                indent=2,
            ),
        )
        from investor_dashboard import build_from_saved

        build_from_saved(
            args.output,
            args.output / "index.html",
            prices=prices,
            features_path=args.macro_features,
            forecasts_path=args.macro_forecasts,
            research_allocation_path=args.research_allocation,
            latest_features_path=args.latest_macro_features,
            pdf=args.pdf,
        )
        print(json.dumps(manifest, indent=2))
        return
    if not all((args.mandate, args.prices, args.cash_rate, args.as_of)):
        parser.error("Supply --demo, or --mandate --prices --cash-rate --as-of")
    mandate = ClientMandate(**load_json(args.mandate)).validate()
    prices = pd.read_csv(args.prices, index_col=0, parse_dates=True)
    key = hashlib.sha256(mandate.client_id.encode()).hexdigest()[:24]
    state_path = args.risk_state or args.output / f"risk-state-{key}.json"
    from productstate import account_lock

    with account_lock(state_path):
        _plan(args, parser, mandate, prices, key, state_path)


def _plan(args, parser, mandate, prices, key, state_path):
    state = None
    if state_path.exists():
        saved = load_json(state_path)
        if (
            saved["client_key"] != key
            or saved["base_currency"] != mandate.base_currency
        ):
            raise ValueError("Risk state account/currency mismatch")
        state = saved["state"]
    if args.risk_reviewer or args.risk_review_evidence:
        if not (args.risk_reviewer and args.risk_review_evidence and state is not None):
            parser.error(
                "Risk review requires an existing state, named reviewer and evidence file"
            )
        if (
            not args.risk_review_evidence.is_file()
            or args.risk_review_evidence.is_symlink()
        ):
            raise ValueError("Risk review evidence must be a regular file")
        import base64

        evidence = args.risk_review_evidence.read_bytes()
        digest = hashlib.sha256(evidence).hexdigest()
        reviewed = RecommendationRiskState.restore(state)
        state = reviewed.acknowledge_review(
            args.risk_reviewer,
            digest,
            str(prices.index[-1].date()),
            loss_preference=None,
        )
        private_write(
            args.output / "risk-reviews" / f"{digest}.json",
            json.dumps(
                {
                    "review": reviewed.last_review,
                    "evidence_base64": base64.b64encode(evidence).decode(),
                },
                indent=2,
            ),
        )
    fx = (
        __import__("productallocation").read_fx_csv(args.fx_to_base)
        if args.fx_to_base
        else None
    )
    result = recommend(
        mandate,
        prices,
        CashRate(**load_json(args.cash_rate)),
        decision_time=args.as_of,
        fx_to_base=fx,
        current=load_json(args.current_weights) if args.current_weights else None,
        annual_fund_expenses=load_json(args.fund_expenses)
        if args.fund_expenses
        else None,
        annual_tax_drag=load_json(args.annual_tax_drag)
        if args.annual_tax_drag
        else None,
        sell_tax_rates=load_json(args.sale_tax_rates) if args.sale_tax_rates else None,
        risk_state=state,
        equity_fraction=args.equity_fraction,
        trend_confirmed=args.trend_confirmed,
        historical_preview=args.historical_preview,
        approval_root=args.approval_root,
        paths=args.paths,
        costs=PlanningCosts(**load_json(args.costs)) if args.costs else PlanningCosts(),
    )
    result["input_snapshot"] = archive(
        args.output / "snapshots",
        result,
        mandate,
        prices,
        CashRate(**load_json(args.cash_rate)),
        archival_arguments(
            decision_time=args.as_of,
            annual_fund_expenses=load_json(args.fund_expenses)
            if args.fund_expenses
            else None,
            fx_to_base=fx,
            current=load_json(args.current_weights) if args.current_weights else None,
            costs=PlanningCosts(**load_json(args.costs))
            if args.costs
            else PlanningCosts(),
            sell_tax_rates=load_json(args.sale_tax_rates)
            if args.sale_tax_rates
            else None,
            risk_state=state,
            equity_fraction=args.equity_fraction,
            trend_confirmed=args.trend_confirmed,
            historical_preview=args.historical_preview,
            paths=args.paths,
            annual_tax_drag=load_json(args.annual_tax_drag)
            if args.annual_tax_drag
            else None,
        ),
    )
    private_write(
        state_path,
        json.dumps(
            {
                "client_key": key,
                "base_currency": mandate.base_currency,
                "state": result["risk_state"],
            },
            indent=2,
        ),
    )
    from investor_analytics import build_context
    from investor_dashboard import market_payload

    display_context = build_context(
        [result],
        prices=prices,
        features_path=args.macro_features,
        forecasts_path=args.macro_forecasts,
        research_allocation_path=args.research_allocation,
        latest_features_path=args.latest_macro_features,
    )
    print(
        json.dumps(
            save_result(
                result,
                args.output,
                context=display_context,
                market=market_payload(prices, {result["price_session"]}),
                pdf=args.pdf,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
