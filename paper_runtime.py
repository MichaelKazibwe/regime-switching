"""Single-cycle paper decision runner.

The scheduler/data adapter is injected by the deployment environment. This
module never creates a live broker and never submits orders. It sends
caller-supplied, validated observations through the existing production
decision/risk/authorization pipeline and persists an idempotent cycle event.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

from paperconfig import PaperRuntimeConfig
from paperstore import SQLitePaperStore, StoredEvent
from audittrail import OperationalAuditTrail
from operationalevent import (
    OperationalEvent,
    OperationalEventType,
    OperationalSeverity,
    OperationalSource,
)
from productionpipelineintegration import (
    ProductionPipelineIntegration,
    ProductionPipelineStatus,
)
from portfoliodecisionengine import DEFAULT_DRAWDOWN_RNG_SEED
from core_constants import (
    DEFAULT_ASSETS,
    REGIME_RISK_BUDGETS,
    REGIME_VOL_TARGETS,
    RISK_BUDGETS,
    TRADING_DAYS,
    market_weights,
    settings as production_settings,
)
from researchdatastore import ResearchArtifactError, ResearchDataStore


class PaperRuntimeError(RuntimeError):
    """Raised when a paper decision cycle cannot safely run."""


def _canonicalize(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return {
            "kind": "dataframe",
            "json": value.to_json(
                orient="split",
                date_format="iso",
                double_precision=15,
            ),
        }
    if isinstance(value, pd.Series):
        return {
            "kind": "series",
            "json": value.to_json(date_format="iso", double_precision=15),
        }
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if is_dataclass(value):
        return _canonicalize(asdict(value))
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and not np.isfinite(value):
            raise PaperRuntimeError("Input payload contains a non-finite number.")
        return value
    raise PaperRuntimeError(
        f"Unsupported paper input type: {type(value).__name__}."
    )


def _without_decision_identity(value: Any) -> Any:
    """Drop per-run identities from fields used for reproducibility checks."""
    if isinstance(value, dict):
        return {
            key: _without_decision_identity(item)
            for key, item in value.items()
            if key != "decision_id"
        }
    if isinstance(value, list):
        return [_without_decision_identity(item) for item in value]
    return value


def build_research_configuration(config: PaperRuntimeConfig) -> dict[str, Any]:
    """Return effective, non-secret settings used by the decision pipeline."""
    return {
        "paper_runtime": {
            "mode": config.mode,
            "assets": list(config.assets),
            "benchmark": config.benchmark,
            "market_period": config.market_period,
            "maximum_price_age_hours": config.maximum_price_age_hours,
            "rebalance_interval_days": config.rebalance_interval_days,
            "initial_cash": config.initial_cash,
            "cash_buffer_fraction": config.cash_buffer_fraction,
            "commission_rate": config.commission_rate,
            "slippage_rate": config.slippage_rate,
            "timezone": config.timezone,
            "live_trading_enabled": config.live_trading_enabled,
            "broker_submission_enabled": config.broker_submission_enabled,
        },
        "production_strategy": {
            "assets": list(DEFAULT_ASSETS),
            "trading_days_per_year": TRADING_DAYS,
            "risk_budgets": RISK_BUDGETS,
            "regime_risk_budgets": REGIME_RISK_BUDGETS,
            "regime_volatility_targets": REGIME_VOL_TARGETS,
            "market_weights": {
                ticker: float(weight)
                for ticker, weight in zip(DEFAULT_ASSETS, np.asarray(market_weights).tolist())
            },
            "bl_tilt_strength": 0.0,
            "drawdown_rng_seed": DEFAULT_DRAWDOWN_RNG_SEED,
            "settings": {
                "yahoo_period": production_settings.yahoo_period,
                "max_position_weight": production_settings.max_position_weight,
                "max_leverage": production_settings.max_leverage,
                "max_turnover": production_settings.max_turnover,
            },
        },
        "data_policy": {
            "source": "YAHOO_FINANCE+FRED",
            "fred_series": {
                "unemployment": "UNRATE",
                "cpi": "CPIAUCSL",
                "gdp": "GDP",
                "ten_year": "DGS10",
                "two_year": "DGS2",
            },
            "release_lag_days": {"UNRATE": 45, "CPIAUCSL": 45, "GDP": 90},
            "fred_vintage_policy": "current_revised_series_with_conservative_release_lags",
        },
    }


class PaperDecisionRunner:
    """Run one externally scheduled decision cycle in enforced paper mode."""

    REQUIRED_INPUTS = frozenset(
        {
            "portfolio",
            "returns",
            "prices",
            "regimes",
            "macro_data",
            "data_as_of",
        }
    )
    OPTIONAL_INPUTS = frozenset({"scenarios", "data_source", "benchmark"})

    def __init__(
        self,
        config: PaperRuntimeConfig,
        *,
        pipeline: ProductionPipelineIntegration | None = None,
        store: SQLitePaperStore | None = None,
        audit_trail: OperationalAuditTrail | None = None,
        input_provider: Callable[[], dict[str, Any]],
        execution_handler: Callable[[Any, dict[str, Any], str], dict[str, Any]] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(config, PaperRuntimeConfig):
            raise TypeError("config must be a PaperRuntimeConfig")
        if not callable(input_provider):
            raise TypeError("input_provider must be callable")
        self.config = config
        self.pipeline = pipeline or ProductionPipelineIntegration()
        if not isinstance(self.pipeline, ProductionPipelineIntegration):
            raise TypeError("pipeline must be a ProductionPipelineIntegration")
        if (
            self.pipeline.LIVE_TRADING_ENABLED
            or self.pipeline.BROKER_SUBMISSION_ENABLED
        ):
            raise PaperRuntimeError("Pipeline is not in a fail-closed paper mode.")
        if self.pipeline.execution_gate.LIVE_TRADING_ENABLED:
            raise PaperRuntimeError("Execution gate reports live trading enabled.")
        if self.pipeline.execution_gate.BROKER_SUBMISSION_ENABLED:
            raise PaperRuntimeError("Execution gate reports broker submission enabled.")
        self.store = store or SQLitePaperStore(config.state_database)
        if not isinstance(self.store, SQLitePaperStore):
            raise TypeError("store must be a SQLitePaperStore")
        self.input_provider = input_provider
        self.research_data_store = ResearchDataStore(config.research_snapshot_directory)
        if execution_handler is not None and not callable(execution_handler):
            raise TypeError("execution_handler must be callable")
        self.execution_handler = execution_handler
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.audit_trail = audit_trail or OperationalAuditTrail(config.audit_log)
        if not isinstance(self.audit_trail, OperationalAuditTrail):
            raise TypeError("audit_trail must be an OperationalAuditTrail")
        if not self.store.verify_event_chain():
            raise PaperRuntimeError(
                "Paper state event chain failed integrity verification"
            )
        audit_health = self.audit_trail.health_check()
        if not audit_health.get("healthy", False):
            raise PaperRuntimeError(
                f"Operational audit trail is unhealthy: {audit_health}"
            )

    def _ensure_audit_record(self, stored: StoredEvent) -> None:
        """Write the durable paper-cycle event to the hash-chained audit log."""
        existing_ids = {
            record.event.get("event_id")
            for record in self.audit_trail.read()
        }
        if stored.event_id in existing_ids:
            return

        result = stored.payload.get("result", {})
        status = str(result.get("status", "FAILED"))
        severity = (
            OperationalSeverity.INFO
            if status == ProductionPipelineStatus.APPROVED
            else OperationalSeverity.WARNING
            if status
            in {
                ProductionPipelineStatus.REJECTED,
                ProductionPipelineStatus.BLOCKED,
            }
            else OperationalSeverity.ERROR
        )
        event = OperationalEvent(
            event_id=stored.event_id,
            event_type=OperationalEventType.AUDIT,
            severity=severity,
            source=OperationalSource.SYSTEM,
            timestamp=stored.occurred_at,
            message=f"Paper decision cycle completed with status {status}.",
            decision_id=result.get("decision_id"),
            regime=result.get("regime"),
            metadata={
                "cycle_id": stored.payload.get("cycle_id"),
                "input_fingerprint": stored.payload.get("input_fingerprint"),
                "data_as_of": stored.payload.get("data_as_of"),
                "data_source": stored.payload.get("data_source"),
                "status": status,
                "approved": bool(result.get("approved", False)),
            },
        )
        self.audit_trail.append(event)

    def _load_inputs(self) -> dict[str, Any]:
        inputs = self.input_provider()
        if not isinstance(inputs, dict):
            raise PaperRuntimeError("input_provider must return a dictionary")
        keys = set(inputs)
        missing = self.REQUIRED_INPUTS - keys
        unexpected = keys - self.REQUIRED_INPUTS - self.OPTIONAL_INPUTS
        if missing or unexpected:
            details = []
            if missing:
                details.append("missing=" + ",".join(sorted(missing)))
            if unexpected:
                details.append("unexpected=" + ",".join(sorted(unexpected)))
            raise PaperRuntimeError(
                "Invalid production input envelope: " + "; ".join(details)
            )
        if not isinstance(inputs["prices"], pd.DataFrame):
            raise PaperRuntimeError("prices must be a pandas DataFrame")
        if tuple(inputs["prices"].columns) != tuple(self.config.assets):
            raise PaperRuntimeError(
                "Price columns must match the canonical configured asset order"
            )
        if inputs["prices"].empty:
            raise PaperRuntimeError("Price history cannot be empty")
        as_of = inputs["data_as_of"]
        if isinstance(as_of, str):
            try:
                as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
            except ValueError as exc:
                raise PaperRuntimeError("data_as_of must be an ISO timestamp") from exc
        if not isinstance(as_of, datetime) or as_of.tzinfo is None:
            raise PaperRuntimeError("data_as_of must be timezone-aware")
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise PaperRuntimeError("paper runtime clock must return an aware datetime")
        age = now.astimezone(timezone.utc) - as_of.astimezone(timezone.utc)
        if age < timedelta(minutes=-5):
            raise PaperRuntimeError("data_as_of is too far in the future")
        if age > timedelta(hours=self.config.maximum_price_age_hours):
            raise PaperRuntimeError(
                f"Market data is stale ({age.total_seconds() / 3600:.1f} hours old)"
            )
        inputs["data_as_of"] = as_of.astimezone(timezone.utc).isoformat()
        inputs.setdefault("data_source", "UNSPECIFIED")
        return inputs

    def _research_configuration(self) -> dict[str, Any]:
        """Return effective settings without serializing provider secrets."""
        return build_research_configuration(self.config)

    def run_once(self, cycle_id: str) -> StoredEvent:
        """Run one decision cycle and persist its outcome idempotently."""
        if not isinstance(cycle_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", cycle_id):
            raise ValueError("cycle_id must be 1-96 safe identifier characters")

        event_id = f"paper-cycle:{cycle_id}"
        previous = self.store.get_event(event_id)
        if previous is not None:
            self._ensure_audit_record(previous)
            return previous

        inputs = self._load_inputs()
        input_fingerprint = self.research_data_store.fingerprint(inputs)

        try:
            provenance = self.research_data_store.runtime_provenance()
            if provenance["dependency_mismatches"]:
                raise PaperRuntimeError(
                    "Installed paper dependencies differ from requirements-paper.lock."
                )
            research_configuration = self._research_configuration()
            execution_state = {"numpy_random_state": np.random.get_state()}
            research_snapshot = self.research_data_store.write_snapshot(
                inputs,
                input_fingerprint=input_fingerprint,
                configuration=research_configuration,
                provenance=provenance,
                execution_state=execution_state,
            )
        except ResearchArtifactError as exc:
            raise PaperRuntimeError(f"Research snapshot could not be secured: {exc}") from exc

        # ProductionDecisionExecution receives these named, caller-supplied
        # inputs. It must not fall back to its synthetic regression fixture.
        pipeline_inputs = {
            key: value
            for key, value in inputs.items()
            if key in self.REQUIRED_INPUTS - {"data_as_of"}
            or key == "scenarios"
        }
        np.random.set_state(execution_state["numpy_random_state"])
        result = self.pipeline.execute(pipeline_inputs)
        if (
            result.status == ProductionPipelineStatus.APPROVED
            and not result.decision_id
        ):
            raise PaperRuntimeError("Approved decision is missing decision_id")

        execution = (
            {"status": "DECISION_ONLY", "orders": []}
            if self.execution_handler is None
            else self.execution_handler(result, inputs, cycle_id)
        )
        execution_stage = result.stage_results.get(
            "production_decision_execution"
        )
        portfolio_decision = getattr(execution_stage, "decision", None)

        summary = {
            "status": result.status,
            "approved": bool(result.approved),
            "decision_id": result.decision_id,
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
            "errors": result.errors,
            "warnings": result.warnings,
            "paper_execution": execution,
            "risk_validation": _canonicalize(
                result.stage_results.get("production_risk_validation", {})
            ),
        }
        decision_core = {
            key: summary[key]
            for key in (
                "status",
                "approved",
                "regime",
                "weights",
                "portfolio_return",
                "portfolio_variance",
                "portfolio_volatility",
                "gross_exposure",
                "net_exposure",
                "risk_contributions",
                "risk_contribution_pct",
                "expected_returns",
                "covariance",
                "scenario_results",
                "risk_validation",
                "errors",
                "warnings",
            )
        }
        decision_core["risk_validation"] = _without_decision_identity(
            decision_core["risk_validation"]
        )
        payload = {
            "cycle_id": cycle_id,
            "input_fingerprint": input_fingerprint,
            "research_snapshot": research_snapshot,
            "configuration_fingerprint": research_snapshot["configuration_fingerprint"],
            "decision_fingerprint": self.research_data_store.fingerprint(
                _canonicalize(decision_core)
            ),
            "data_as_of": inputs["data_as_of"],
            "data_source": inputs["data_source"],
            "configuration": {
                "mode": self.config.mode,
                "assets": list(self.config.assets),
                "benchmark": self.config.benchmark,
                "rebalance_interval_days": self.config.rebalance_interval_days,
                "maximum_price_age_hours": self.config.maximum_price_age_hours,
                "market_period": self.config.market_period,
                "initial_cash": self.config.initial_cash,
                "cash_buffer_fraction": self.config.cash_buffer_fraction,
                "commission_rate": self.config.commission_rate,
                "slippage_rate": self.config.slippage_rate,
                "timezone": self.config.timezone,
                "research_snapshot_directory": str(self.config.research_snapshot_directory),
            },
            "result": _canonicalize(summary),
        }
        stored = self.store.append_event(
            event_id=event_id,
            event_type="PAPER_DECISION_CYCLE",
            payload=payload,
        )
        self._ensure_audit_record(stored)
        return stored
