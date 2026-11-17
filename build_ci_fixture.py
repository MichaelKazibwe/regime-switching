"""Generate isolated synthetic, sealed end-to-end evidence; never production data."""

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import shutil

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

SOURCE = Path(__file__).resolve().parent


def build(destination, *, resume=False):
    destination = Path(destination).resolve()
    if destination.exists() and (
        not resume or (destination / "fixture.json").is_file()
    ):
        raise ValueError(
            "Use a new isolated QA destination or explicitly resume an incomplete fixture"
        )
    destination.mkdir(parents=True, mode=0o700, exist_ok=resume)
    work = destination / "workspace"
    work.mkdir(exist_ok=resume)
    for p in SOURCE.glob("*.py"):
        shutil.copyfile(p, work / p.name)
    for folder in ["dashboard", "pilot", "research"]:
        shutil.copytree(SOURCE / folder, work / folder, dirs_exist_ok=resume)
    for pattern in ("requirements-*.lock", "Dockerfile*", ".dockerignore"):
        for p in SOURCE.glob(pattern):
            if p.is_file():
                shutil.copyfile(p, work / p.name)
    previous = Path.cwd()
    os.chdir(work)
    os.environ["PILOT_ALLOW_SYNTHETIC_QA"] = "1"
    os.environ["PILOT_MACRO_ALPHA_STATE_ROOT"] = str(work / "var/macro-alpha")
    try:
        from strategy_training_data import usable_session
        from strategy_receipts import atomic_json
        from strategy_integrity import file_hash
        from global_asset_registry import load_registry
        from macrovintage import MacroVintageData
        from live_strategy_training import train
        from investor_dashboard import build_from_saved
        from test_investment_product import mandate
        from recommendationservice import recommend
        from clientmandate import CashRate
        from refresh_strategy_dashboard import integrate
        from cycle_benchmark import run as benchmark
        from weekly_portfolios import run as weekly
        from macro_alpha import build as alpha, record
        from pilot_release import stage

        capture = work / "capture"
        if resume:
            saved = json.loads((capture / "capture.json").read_text())
            now = datetime.fromisoformat(saved["captured_at"])
            session = pd.Timestamp(saved["price_session"])
            prices = pd.read_csv(capture / "prices.csv", index_col=0, parse_dates=True)
            training = sorted((work / "training").glob("*/training-report.json"))[-1]
            from strategy_report import load_training_report

            if not load_training_report(training)["current_numerical_source_match"]:
                raise ValueError("Fixture checkpoint source changed; use a new fixture")
        else:
            now = datetime.now(timezone.utc)
            session = usable_session(now)
            dates = (
                mcal.get_calendar("NYSE").schedule("2017-01-01", session.date()).index
            )
            capture = work / "capture"
            capture.mkdir()
            symbols = [
                s
                for s, i in load_registry().instruments.items()
                if i.listing_currency == "USD"
            ]
            rng = np.random.default_rng(20261117)
            values = rng.normal(0.00012, 0.006, (len(dates), len(symbols)))
            for s in ["SGOV", "SHY", "IEF"]:
                values[:, symbols.index(s)] *= 0.08 if s == "SGOV" else 0.35
            prices = pd.DataFrame(
                100 * np.cumprod(1 + values, axis=0), index=dates, columns=symbols
            )
            prices.to_csv(capture / "prices.csv")
            manifest = dict(series={}, cutoff=str(session.date()))
            monthly = pd.date_range("2015-01-01", session, freq="MS")
            for key in ["UNRATE", "CPIAUCSL", "INDPRO", "DGS10", "DGS3MO"]:
                idx = dates if key.startswith("DGS") else monthly
                t = np.arange(len(idx))
                if key == "UNRATE":
                    observed = 4.5 + 0.8 * np.sin(t / 7)
                elif key == "INDPRO":
                    observed = 100 + 0.08 * t + 4 * np.sin(t / 8)
                elif key == "CPIAUCSL":
                    observed = 200 * np.exp(0.002 * t + 0.004 * np.sin(t / 3))
                else:
                    observed = 3.0 + np.sin(t / 180) + (0.6 if key == "DGS10" else 0)
                releases = pd.DataFrame(
                    dict(
                        date=idx,
                        realtime_start=idx
                        + (
                            pd.Timedelta(0)
                            if key.startswith("DGS")
                            else pd.Timedelta(days=15)
                        ),
                        value=observed,
                    )
                )
                releases = releases[releases.realtime_start <= session]
                manifest["series"][key] = MacroVintageData(releases).freeze(
                    capture / (key + ".csv")
                )
            atomic_json(capture / "macro-manifest.json", manifest)
            files = [p for p in capture.iterdir() if p.is_file()]
            atomic_json(
                capture / "capture.json",
                dict(
                    status="CAPTURED_FOR_SHADOW_TRAINING",
                    synthetic_fixture=True,
                    captured_at=now.isoformat(),
                    price_session=str(session.date()),
                    publication_buffer_minutes=15,
                    base_currency="USD",
                    universe_contract=load_registry().payload(),
                    prices=str(capture / "prices.csv"),
                    macro_manifest=str(capture / "macro-manifest.json"),
                    files={p.name: file_hash(p) for p in files},
                    limitations=[
                        "SYNTHETIC CI FIXTURE. Not financial observations or investment evidence."
                    ],
                ),
            )
            training = train(capture / "capture.json", work / "training")
        stamp = (
            mcal.get_calendar("NYSE")
            .schedule(session.date(), session.date())
            .market_close.iloc[0]
            .isoformat()
        )
        plans = work / "var/product-preview"
        plans.mkdir(parents=True, exist_ok=resume)
        reports = []
        for profile in ["preservation", "balanced", "growth"]:
            result = recommend(
                mandate(profile, horizon_years=1.0),
                prices,
                CashRate("USD", 0.0, stamp, "SYNTHETIC_QA", False),
                decision_time=stamp,
                historical_preview=True,
                paths=100,
            )
            folder = plans / profile
            folder.mkdir(exist_ok=resume)
            atomic_json(folder / "recommendation.json", result)
            reports.append(dict(report=str(folder / "report.html")))
        atomic_json(plans / "demo-manifest.json", dict(reports=reports))
        dashboard = work / "dashboard-output/investor-dashboard.html"
        dashboard.parent.mkdir(exist_ok=resume)
        build_from_saved(plans, dashboard, prices=prices, pdf=True)
        extension = work / "extension"
        extension.mkdir(exist_ok=resume)
        prices[["XLV"]].to_csv(extension / "XLV-adjusted.csv")
        atomic_json(
            extension / "news.json",
            dict(
                status="SYNTHETIC_QA",
                headlines=[],
                fetched_at=now.isoformat(),
                limitations=["Synthetic CI fixture"],
            ),
        )
        atomic_json(
            extension / "capture.json",
            dict(
                market_session=str(session.date()),
                captured_at=now.isoformat(),
                prices_sha256=file_hash(extension / "XLV-adjusted.csv"),
                news_sha256=file_hash(extension / "news.json"),
                price_source="SYNTHETIC_QA",
            ),
        )
        integrate(
            capture / "capture.json", training, dashboard, benchmark_extension=extension
        )
        bundle = dashboard.parent / "latest-strategy-run.json"
        pointer = work / "var/dashboard-live/latest.json"
        atomic_json(
            pointer,
            dict(
                document=str(dashboard),
                document_sha256=file_hash(dashboard),
                bundle=str(bundle),
                bundle_sha256=file_hash(bundle),
                market_session=str(session.date()),
                execution_enabled=False,
            ),
        )
        benchmark(bundle, work / "var/cycle-benchmark/fixture")
        weekly(bundle, work / "weekly")
        forecast = alpha(capture / "capture.json", training)
        record(
            forecast,
            json.loads((training.parent / "features.json").read_text()),
            work / "var/macro-alpha",
        )
        release = stage(
            SOURCE,
            destination / "release",
            allow_dirty=True,
            pointer=pointer,
            benchmark=work / "var/cycle-benchmark/fixture/benchmark.json",
        )
        from research_publisher import filesystem_publish

        filesystem_publish(
            destination / "release/runtime/pilot-input",
            destination / "daily-published",
            kind="daily",
        )
        filesystem_publish(
            work / "weekly", destination / "weekly-published", kind="weekly"
        )
        atomic_json(
            destination / "fixture.json",
            dict(
                synthetic_fixture=True,
                source_release_id=release["release_id"],
                snapshot=str(destination / "release/runtime/pilot-input/launch.json"),
                weekly=str(work / "weekly"),
                execution_enabled=False,
                public_data_qualification=False,
            ),
        )
        return destination / "fixture.json"
    finally:
        os.chdir(previous)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    print(build(args.output, resume=args.resume))
