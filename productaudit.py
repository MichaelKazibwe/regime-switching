"""Exact private input snapshots and numerical replay for recommendations."""

from dataclasses import asdict
from pathlib import Path

from clientmandate import CashRate, ClientMandate, aware_time
from productallocation import PlanningCosts
from productrelease import release_manifest
from researchdatastore import ResearchDataStore


def archive(root, result, mandate, prices, cash_rate, arguments):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    store = ResearchDataStore(root)
    inputs = {
        "mandate": asdict(mandate),
        "prices": prices,
        "cash_rate": asdict(cash_rate),
        "arguments": arguments,
        "expected_numerics": {
            k: result[k] for k in ("allocation", "simulations", "risk_state")
        },
    }
    manifest = store.write_snapshot(
        inputs,
        input_fingerprint=store.fingerprint(inputs),
        configuration=result["release"],
        provenance={
            "kind": "RECOMMENDATION_INPUT_SNAPSHOT",
            "recommendation_id": result["recommendation_id"],
        },
    )
    (root / manifest["relative_path"]).chmod(0o600)
    return manifest


def replay(root, manifest):
    from recommendationservice import recommend

    store = ResearchDataStore(root)
    envelope = store.load_snapshot(manifest)
    if envelope["configuration"]["release_id"] != release_manifest()["release_id"]:
        raise ValueError(
            "Replay requires the same reviewed source and dependency environment"
        )
    data = envelope["inputs"]
    arguments = data["arguments"].copy()
    arguments["costs"] = PlanningCosts(**arguments["costs"])
    arguments["approval_root"] = (
        None  # Replay verifies calculations, never restores public approval.
    )
    arguments["clock"] = lambda: aware_time(arguments["decision_time"])
    actual = recommend(
        ClientMandate(**data["mandate"]),
        data["prices"],
        CashRate(**data["cash_rate"]),
        **arguments,
    )
    numerical = {k: actual[k] for k in ("allocation", "simulations", "risk_state")}
    matches = store.fingerprint(numerical) == store.fingerprint(
        data["expected_numerics"]
    )
    return {
        "kind": "REPLAY_VERIFICATION_ONLY",
        "matches": matches,
        "public_recommendations_enabled": False,
        "broker_submission_enabled": False,
        "original_recommendation_id": envelope["provenance"]["recommendation_id"],
    }


def archival_arguments(
    *,
    decision_time,
    fx_to_base,
    current,
    costs,
    sell_tax_rates,
    risk_state,
    equity_fraction,
    trend_confirmed,
    historical_preview,
    paths,
    annual_tax_drag,
    annual_fund_expenses=None,
):
    return {
        "decision_time": decision_time,
        "fx_to_base": fx_to_base,
        "current": current,
        "costs": asdict(costs),
        "sell_tax_rates": sell_tax_rates,
        "risk_state": risk_state,
        "equity_fraction": equity_fraction,
        "trend_confirmed": trend_confirmed,
        "historical_preview": historical_preview,
        "paths": paths,
        "annual_tax_drag": annual_tax_drag,
        "annual_fund_expenses": annual_fund_expenses,
    }
