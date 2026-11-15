"""Synthetic packaging check only; never investment performance evidence."""

import argparse
from pathlib import Path
import json
import numpy as np
import pandas as pd

from assetuniverse import DIVERSIFIED_ASSETS
from clientmandate import CashRate, ClientMandate
from investment_product import save_result
from productallocation import PlanningCosts
from productaudit import archive, archival_arguments, replay
from recommendationservice import recommend


def run(output):
    output = Path(output)
    dates = pd.bdate_range(end="2025-10-29", periods=400)
    symbols = list(DIVERSIFIED_ASSETS)
    rng = np.random.default_rng(73)
    prices = pd.DataFrame(
        100
        * np.exp(
            np.cumsum(rng.normal(0.0001, 0.004, (len(dates), len(symbols))), axis=0)
        ),
        index=dates,
        columns=symbols,
    )
    stamp = "2025-10-29T21:00:00+00:00"
    mandate = ClientMandate(
        "synthetic-image-smoke",
        "preservation",
        "USD",
        "",
        "",
        3.0,
        100000.0,
        0.05,
        0.05,
        investment_experience="illustrative",
        tax_account_type="tax_exempt",
    )
    rate = CashRate("USD", 0.0, stamp, "SYNTHETIC_BUILD_CHECK_NOT_VERIFIED", False)
    arguments = archival_arguments(
        decision_time=stamp,
        fx_to_base=None,
        current=None,
        costs=PlanningCosts(),
        sell_tax_rates=None,
        risk_state=None,
        equity_fraction=1.0,
        trend_confirmed=False,
        historical_preview=True,
        paths=100,
        annual_tax_drag=None,
    )
    result = recommend(mandate, prices, rate, **{**arguments, "costs": PlanningCosts()})
    result["input_snapshot"] = archive(
        output / "snapshots", result, mandate, prices, rate, arguments
    )
    assert replay(output / "snapshots", result["input_snapshot"])["matches"]
    assert not result["qualification"]["public_recommendations_enabled"]
    save_result(result, output)
    assert (output / "index.html").is_file()
    evidence = dict(
        status="SYNTHETIC_ENGINEERING_SMOKE_PASSED",
        replay_matches=True,
        public_release=False,
    )
    (output / "smoke.json").write_text(json.dumps(evidence))
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(run(parser.parse_args().output))
