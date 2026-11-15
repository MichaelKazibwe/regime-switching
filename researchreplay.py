"""Re-run stored paper decisions without routing or submitting orders."""

from __future__ import annotations

from typing import Any

import numpy as np

from paperconfig import PaperRuntimeConfig
from paper_runtime import (
    _canonicalize,
    _without_decision_identity,
    build_research_configuration,
)
from paperstore import SQLitePaperStore
from productionpipelineintegration import ProductionPipelineIntegration
from researchdatastore import ResearchArtifactError, ResearchDataStore


class ResearchReplayError(RuntimeError):
    """Raised when a saved decision cannot be reproduced exactly."""


def _decision_core(result: Any) -> dict[str, Any]:
    execution_stage = result.stage_results.get("production_decision_execution")
    portfolio_decision = getattr(execution_stage, "decision", None)
    return {
        "status": result.status,
        "approved": bool(result.approved),
        "regime": result.regime,
        "weights": result.weights,
        "portfolio_return": result.portfolio_return,
        "portfolio_variance": result.portfolio_variance,
        "portfolio_volatility": result.portfolio_volatility,
        "gross_exposure": result.gross_exposure,
        "net_exposure": result.net_exposure,
        "risk_contributions": result.risk_contributions,
        "risk_contribution_pct": result.risk_contribution_pct,
        "expected_returns": getattr(portfolio_decision, "expected_returns", {}),
        "covariance": getattr(portfolio_decision, "covariance", {}),
        "scenario_results": result.scenario_results,
        "risk_validation": _without_decision_identity(
            _canonicalize(
                result.stage_results.get("production_risk_validation", {})
            )
        ),
        "errors": result.errors,
        "warnings": result.warnings,
    }


def replay_decision(
    store: SQLitePaperStore,
    research_store: ResearchDataStore,
    event_id: str,
) -> dict[str, Any]:
    """Validate provenance and rerun one stored decision in decision-only mode."""
    if not store.read_only:
        raise ResearchReplayError("Replay requires a read-only paper database connection.")
    if not store.verify_event_chain():
        raise ResearchReplayError("Paper event hash chain is invalid.")
    event = store.get_event(event_id)
    if event is None:
        raise ResearchReplayError(f"Paper cycle event not found: {event_id}")
    manifest = event.payload.get("research_snapshot")
    if not isinstance(manifest, dict):
        raise ResearchReplayError("Paper cycle has no research snapshot manifest.")

    try:
        envelope = research_store.load_snapshot(manifest)
    except ResearchArtifactError as exc:
        raise ResearchReplayError(str(exc)) from exc

    saved_provenance = envelope["provenance"]
    current_provenance = research_store.runtime_provenance()
    provenance_fields = (
        "code_revision",
        "source_tree_sha256",
        "dependency_lock_sha256",
        "dependency_environment_sha256",
        "python_version",
        "locked_packages",
    )
    differences = [
        field
        for field in provenance_fields
        if saved_provenance.get(field) != current_provenance.get(field)
    ]
    if differences:
        raise ResearchReplayError(
            "Exact replay requires the original source and runtime; mismatched provenance: "
            + ", ".join(differences)
        )
    if current_provenance["dependency_mismatches"]:
        raise ResearchReplayError("Installed runtime packages differ from the locked environment.")

    saved_configuration = envelope["configuration"]
    try:
        config = PaperRuntimeConfig(**saved_configuration["paper_runtime"])
    except Exception as exc:
        raise ResearchReplayError(f"Stored paper configuration is invalid: {exc}") from exc
    current_configuration = build_research_configuration(config)
    current_configuration_fingerprint = research_store.fingerprint(current_configuration)
    if current_configuration_fingerprint != manifest["configuration_fingerprint"]:
        raise ResearchReplayError("Effective strategy or paper configuration has changed.")

    inputs = envelope["inputs"]
    if research_store.fingerprint(inputs) != manifest["input_fingerprint"]:
        raise ResearchReplayError("Restored research inputs do not match their fingerprint.")
    expected_event_fingerprint = event.payload.get("input_fingerprint")
    if expected_event_fingerprint != manifest["input_fingerprint"]:
        raise ResearchReplayError("Database event and snapshot input fingerprints differ.")

    pipeline_inputs = {
        key: value
        for key, value in inputs.items()
        if key in {"portfolio", "returns", "prices", "regimes", "macro_data", "scenarios"}
    }
    execution_state = envelope.get("execution_state")
    numpy_random_state = (
        execution_state.get("numpy_random_state")
        if isinstance(execution_state, dict)
        else None
    )
    if numpy_random_state is None:
        raise ResearchReplayError("Snapshot is missing the decision-time NumPy random state.")
    replay_pipeline = ProductionPipelineIntegration()
    prior_numpy_random_state = np.random.get_state()
    try:
        np.random.set_state(numpy_random_state)
        result = replay_pipeline.execute(pipeline_inputs)
    except Exception as exc:
        raise ResearchReplayError(f"Production decision replay failed: {exc}") from exc
    finally:
        np.random.set_state(prior_numpy_random_state)
    decision_fingerprint = research_store.fingerprint(
        _canonicalize(_decision_core(result))
    )
    expected_decision_fingerprint = event.payload.get("decision_fingerprint")
    if not expected_decision_fingerprint:
        raise ResearchReplayError("Paper event does not contain a decision fingerprint.")
    if decision_fingerprint != expected_decision_fingerprint:
        recorded_summary = event.payload.get("result", {})
        replayed_core = _decision_core(result)
        recorded_core = {
            key: recorded_summary.get(key)
            for key in replayed_core
        }
        differences = [
            key
            for key in replayed_core
            if research_store.fingerprint(_canonicalize(replayed_core[key]))
            != research_store.fingerprint(_canonicalize(recorded_core[key]))
        ]
        raise ResearchReplayError(
            "Replayed decision differs from the recorded decision"
            + (": " + ", ".join(differences) if differences else ".")
        )

    return {
        "event_id": event.event_id,
        "snapshot_id": manifest["artifact_id"],
        "input_fingerprint": manifest["input_fingerprint"],
        "configuration_fingerprint": manifest["configuration_fingerprint"],
        "decision_fingerprint": decision_fingerprint,
        "decision_status": str(result.status),
        "approved": bool(result.approved),
        "regime": result.regime,
        "weights": result.weights,
        "exact_match": True,
        "orders_submitted": 0,
        "mode": "REPLAY_ONLY",
    }
