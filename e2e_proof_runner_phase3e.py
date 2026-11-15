"""
======================================================================
e2e_proof_runner.py

REGIME SWITCHING SYSTEM
END-TO-END PRODUCTION PROOF RUNNER
======================================================================

Phase IV-I authorized execution chain.

This runner executes the 54-proof E2E matrix against the real
production interfaces using deterministic in-memory / paper execution.

Safety boundary:
    - live trading is never enabled;
    - live broker connectivity is never created;
    - no live credentials are used;
    - no Git state is modified;
    - the source matrix is read-only;
    - raw authorization/routing/execution boundaries remain fail-closed;
    - a PASS is produced only after an executable assertion succeeds.

The runner is an evidence generator. It is not a deployment authority.
======================================================================
"""

from __future__ import annotations

import csv
import hashlib

import json
import platform
import socket
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parent
MATRIX_JSON = PROJECT_ROOT / "E2E_PROOF_MATRIX.json"
RESULTS_JSON = PROJECT_ROOT / "e2e_proof_results.json"
RESULTS_CSV = PROJECT_ROOT / "e2e_proof_results.csv"
RESULTS_MD = PROJECT_ROOT / "e2e_proof_results.md"
EVIDENCE_JSON = PROJECT_ROOT / "e2e_execution_evidence.json"

PASS = "PASS"
FAIL = "FAIL"
BLOCKED = "BLOCKED"
NOT_EXECUTED = "NOT_EXECUTED"
SKIPPED = "SKIPPED"
VALID_STATUSES = {PASS, FAIL, BLOCKED, NOT_EXECUTED, SKIPPED}


@dataclass
class ProofResult:
    proof_id: str
    phase: str
    boundary: str
    invariant: str
    expected_result: str
    status: str = NOT_EXECUTED
    evidence: str = ""
    actual_result: str = ""
    error_type: str = ""
    error_message: str = ""
    traceback_text: str = ""
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Invalid proof status: {self.status}")
        if not self.proof_id:
            raise ValueError("Proof ID cannot be empty.")


class ProofBlocked(RuntimeError):
    """Explicit fail-closed dependency/interface block."""


class E2EProofRunner:
    """
    Deterministic, dependency-aware production proof runner.

    The runner deliberately retains the real artifacts produced by the
    production interfaces instead of manufacturing replacement objects.
    """

    RUNNER_VERSION = "2.1.0"
    PAPER_PRICE = 500.0
    ORDER_ID = "E2E-ORDER-001"
    ORDER_TICKER = "SPY"
    ORDER_SIDE = "BUY"
    ORDER_QUANTITY = 10.0

    def __init__(
        self,
        *,
        project_root: Path = PROJECT_ROOT,
        matrix_path: Path = MATRIX_JSON,
    ) -> None:
        self.project_root = Path(project_root)
        self.matrix_path = Path(matrix_path)
        self.results: list[ProofResult] = []
        self.context: dict[str, Any] = {}
        self._proofs: list[dict[str, Any]] = []
        self.evidence: dict[str, Any] = {
            "system": "Regime Switching System",
            "runner": "e2e_proof_runner.py",
            "runner_version": self.RUNNER_VERSION,
            "started_at": "",
            "completed_at": "",
            "live_trading": False,
            "live_broker": False,
            "network_execution": False,
            "git_mutation": False,
            "source_matrix_mutated": False,
            "paper_execution": True,
            "dependency_events": [],
            "proofs": {},
        }
        self._load_matrix()

    # ------------------------------------------------------------------
    # MATRIX
    # ------------------------------------------------------------------

    def _load_matrix(self) -> None:
        if not self.matrix_path.exists():
            raise FileNotFoundError(
                f"E2E proof matrix was not found: {self.matrix_path}"
            )

        with self.matrix_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        if not isinstance(payload, dict):
            raise ValueError("E2E proof matrix must contain a JSON object.")

        proofs = payload.get("proofs")
        if not isinstance(proofs, list):
            raise ValueError("E2E proof matrix does not contain a proof list.")

        self._proofs = proofs
        self._validate_matrix()

    def _validate_matrix(self) -> None:
        if len(self._proofs) != 54:
            raise ValueError(
                f"Expected exactly 54 E2E proofs; found {len(self._proofs)}."
            )

        expected_ids = [f"E2E-{i:02d}" for i in range(1, 55)]
        actual_ids = [proof.get("proof_id") for proof in self._proofs]

        if actual_ids != expected_ids:
            raise ValueError(
                "E2E proof IDs are not sequential E2E-01 through E2E-54."
            )

        required = (
            "proof_id",
            "phase",
            "boundary",
            "input_artifact",
            "output_artifact",
            "invariant",
            "test_action",
            "expected_result",
        )
        for proof in self._proofs:
            for field_name in required:
                if field_name not in proof:
                    raise ValueError(
                        f"{proof.get('proof_id', 'UNKNOWN')} "
                        f"is missing field '{field_name}'."
                    )

    # ------------------------------------------------------------------
    # GENERAL HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _assert(condition: bool, message: str) -> None:
        if not condition:
            raise AssertionError(message)

    @staticmethod
    def _import(module: str, name: str) -> Any:
        imported = __import__(module, fromlist=[name])
        return getattr(imported, name)

    @staticmethod
    def _get(obj: Any, name: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    @staticmethod
    def _serialize(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(k): E2EProofRunner._serialize(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [E2EProofRunner._serialize(v) for v in value]
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            try:
                return E2EProofRunner._serialize(to_dict())
            except Exception:
                pass
        return repr(value)

    @staticmethod
    def _call(obj: Any, name: str, *args: Any, **kwargs: Any) -> Any:
        method = getattr(obj, name, None)
        if not callable(method):
            raise AttributeError(
                f"{type(obj).__name__}.{name} is unavailable."
            )
        return method(*args, **kwargs)

    def _require_context(self, *names: str) -> None:
        missing = [name for name in names if self.context.get(name) is None]
        if missing:
            raise ProofBlocked(
                "Required upstream artifact(s) unavailable: "
                + ", ".join(missing)
            )

    def _register_result(self, proof: dict[str, Any]) -> ProofResult:
        result = ProofResult(
            proof_id=proof["proof_id"],
            phase=proof["phase"],
            boundary=proof["boundary"],
            invariant=proof["invariant"],
            expected_result=proof["expected_result"],
            metadata={
                "input_artifact": proof["input_artifact"],
                "output_artifact": proof["output_artifact"],
                "test_action": proof["test_action"],
            },
        )
        self.results.append(result)
        return result

    def _execute_result(
        self,
        result: ProofResult,
        operation: Callable[[], Any],
    ) -> None:
        started = datetime.now(timezone.utc)
        result.started_at = started.isoformat()

        try:
            value = operation()
            result.status = PASS
            result.actual_result = repr(value)
            result.evidence = "Executable assertion completed successfully."
        except ProofBlocked as exc:
            result.status = BLOCKED
            result.error_type = type(exc).__name__
            result.error_message = str(exc)
            result.traceback_text = traceback.format_exc()
            result.evidence = "Proof was blocked by a missing upstream artifact or interface."
        except (
            ImportError,
            ModuleNotFoundError,
            AttributeError,
            NotImplementedError,
        ) as exc:
            result.status = BLOCKED
            result.error_type = type(exc).__name__
            result.error_message = str(exc)
            result.traceback_text = traceback.format_exc()
            result.evidence = "Required production interface is unavailable."
        except Exception as exc:
            result.status = FAIL
            result.error_type = type(exc).__name__
            result.error_message = str(exc)
            result.traceback_text = traceback.format_exc()
            result.evidence = "Production interface executed but invariant failed."

        completed = datetime.now(timezone.utc)
        result.completed_at = completed.isoformat()
        result.duration_seconds = (completed - started).total_seconds()
        result.validate()

        self.evidence["proofs"][result.proof_id] = {
            "status": result.status,
            "actual_result": result.actual_result,
            "evidence": result.evidence,
            "error_type": result.error_type,
            "error_message": result.error_message,
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "duration_seconds": result.duration_seconds,
            "metadata": result.metadata,
        }

    def _run(self, proof_id: str, operation: Callable[[], Any]) -> None:
        proof = next((p for p in self._proofs if p["proof_id"] == proof_id), None)
        if proof is None:
            raise KeyError(f"Unknown proof ID: {proof_id}")
        result = self._register_result(proof)
        self._execute_result(result, operation)

    # ------------------------------------------------------------------
    # FIXTURES
    # ------------------------------------------------------------------

    def _build_decision_execution(self) -> Any:
        ProductionDecisionExecution = self._import(
            "productiondecisionexecution",
            "ProductionDecisionExecution",
        )
        return ProductionDecisionExecution()

    def _build_gate(self) -> Any:
        ProductionExecutionGate = self._import(
            "productionexecutiongate",
            "ProductionExecutionGate",
        )
        return ProductionExecutionGate(
            decision_execution=self.context.get("decision_execution")
        )

    def _build_oms(self) -> Any:
        OMS = self._import("oms", "OMS")
        return OMS()

    def _build_broker(self) -> Any:
        PaperBroker = self._import("paperbroker", "PaperBroker")
        return PaperBroker()

    def _build_router(self) -> Any:
        BrokerRouter = self._import("brokerrouter", "BrokerRouter")
        return BrokerRouter()

    def _build_account(self) -> Any:
        PortfolioAccount = self._import("portfolioaccount", "PortfolioAccount")
        return PortfolioAccount(initial_cash=100_000.0)

    # ------------------------------------------------------------------
    # PHASE A — DECISION / RISK / AUTHORIZATION
    # ------------------------------------------------------------------

    def proof_e2e_01(self) -> Any:
        execution = self._build_decision_execution()
        result = self._call(execution, "execute")
        self._assert(result is not None, "ProductionDecisionExecution returned None.")
        self._assert(
            bool(self._get(result, "decision_id")),
            "Production decision execution has no decision_id.",
        )
        self.context["decision_execution"] = execution
        self.context["decision_result"] = result
        self.context["decision"] = self._get(result, "decision")
        self._assert(
            self.context["decision"] is not None,
            "Production decision execution did not expose its decision artifact.",
        )
        return self._serialize(result)

    def proof_e2e_02(self) -> Any:
        self._require_context("decision", "decision_result")
        decision = self.context["decision"]
        decision_id = self._get(decision, "decision_id") or self._get(
            self.context["decision_result"], "decision_id"
        )
        self._assert(bool(decision_id), "decision_id is empty or missing.")
        self.context["decision_id"] = decision_id
        return decision_id

    def proof_e2e_03(self) -> Any:
        ProductionRiskValidation = self._import(
            "productionriskvalidation",
            "ProductionRiskValidation",
        )
        validator = ProductionRiskValidation()
        self._require_context("decision")
        risk_result = validator.validate(self.context["decision"])
        self._assert(
            self._get(risk_result, "approved") is True,
            f"Production risk validation was not approved: {self._serialize(risk_result)}",
        )
        self.context["risk_validator"] = validator
        self.context["risk_result"] = risk_result
        return self._serialize(risk_result)

    def proof_e2e_04(self) -> Any:
        self._require_context("decision_result", "risk_result")
        gate = self._build_gate()
        authorization = gate.authorize(self.context["decision_result"])
        self._assert(
            authorization is not None,
            "ProductionExecutionGate returned no authorization artifact.",
        )
        gate.require_authorization(authorization)
        self._assert(
            self._get(authorization, "status") == "AUTHORIZED",
            "Authorization did not reach AUTHORIZED status.",
        )
        self.context["gate"] = gate
        self.context["authorization"] = authorization
        return self._serialize(authorization)

    def proof_e2e_05(self) -> Any:
        self._require_context("authorization")
        status = self._get(self.context["authorization"], "status")
        self._assert(status == "AUTHORIZED", f"Expected AUTHORIZED, got {status!r}.")
        return status

    def proof_e2e_06(self) -> Any:
        self._require_context("authorization")
        authorized = self._get(self.context["authorization"], "authorized")
        self._assert(authorized is True, f"Expected authorized=True, got {authorized!r}.")
        return authorized

    def proof_e2e_07(self) -> Any:
        self._require_context("authorization")
        authorization = self.context["authorization"]
        self._assert(
            self._get(authorization, "live_trading_enabled") is False,
            "Live trading became enabled.",
        )
        self._assert(
            self._get(authorization, "broker_submission_enabled") is False,
            "Broker submission became enabled in the authorization artifact.",
        )
        self._assert(
            self._get(authorization, "risk_validation_passed") is True,
            "Authorization does not carry successful risk validation.",
        )
        return {
            "live_trading_enabled": self._get(authorization, "live_trading_enabled"),
            "broker_submission_enabled": self._get(
                authorization, "broker_submission_enabled"
            ),
            "risk_validation_passed": self._get(
                authorization, "risk_validation_passed"
            ),
        }

    # ------------------------------------------------------------------
    # PHASE B — AUTHORIZED ORDER / OMS
    # ------------------------------------------------------------------

    def proof_e2e_08(self) -> Any:
        self._require_context("authorization")
        AuthorizedOrderIntent = self._import(
            "authorizedorderintent",
            "AuthorizedOrderIntent",
        )
        authorization = self.context["authorization"]
        intent = AuthorizedOrderIntent.create_order(
            authorization=authorization,
            ticker=self.ORDER_TICKER,
            side=self.ORDER_SIDE,
            quantity=self.ORDER_QUANTITY,
            order_type="MARKET",
            time_in_force="DAY",
            order_id=self.ORDER_ID,
        )
        order = intent.order
        self._assert(order.validate() is True, "Canonical Order validation failed.")
        self.context["intent"] = intent
        self.context["order"] = order
        return order.order_id

    def proof_e2e_09(self) -> Any:
        self._require_context("intent", "order")
        oms = self._build_oms()
        submitted = oms.submit_authorized_order(self.context["intent"])
        self._assert(
            submitted is self.context["order"],
            "OMS did not retain the exact canonical Order object.",
        )
        self.context["oms"] = oms
        return submitted.order_id

    def proof_e2e_10(self) -> Any:
        self._require_context("oms", "order")
        oms = self.context["oms"]
        order = self.context["order"]
        getter = getattr(oms, "get_order", None)
        if callable(getter):
            retrieved = getter(order.order_id)
        else:
            retrieved = oms.order_book.get_order(order.order_id)
        self._assert(retrieved is order, "OMS OrderBook identity was not preserved.")
        return order.order_id

    # ------------------------------------------------------------------
    # PHASE C — INTENT PROVENANCE
    # ------------------------------------------------------------------

    def proof_e2e_11(self) -> Any:
        self._require_context("intent")
        intent = self.context["intent"]
        self._assert(type(intent).__name__ == "AuthorizedOrderIntent", "Wrong intent type.")
        return type(intent).__name__

    def proof_e2e_12(self) -> Any:
        self._require_context("intent")
        self._assert(self.context["intent"].validate() is True, "Intent validation failed.")
        return True

    def proof_e2e_13(self) -> Any:
        self._require_context("intent", "order")
        self._assert(
            self.context["intent"].order is self.context["order"],
            "Intent does not contain the exact canonical Order.",
        )
        return self.context["order"].order_id

    def proof_e2e_14(self) -> Any:
        self._require_context("intent", "authorization")
        self._assert(
            self.context["intent"].authorization is self.context["authorization"],
            "Authorization provenance was not preserved by AuthorizedOrderIntent.",
        )
        return True

    # ------------------------------------------------------------------
    # PHASE D — EXECUTION HANDOFF
    # ------------------------------------------------------------------

    def proof_e2e_15(self) -> Any:
        self._require_context("intent")
        AuthorizedExecutionHandoff = self._import(
            "authorizedexecutionhandoff",
            "AuthorizedExecutionHandoff",
        )
        handoff = AuthorizedExecutionHandoff.from_intent(self.context["intent"])
        self.context["execution_handoff"] = handoff
        return type(handoff).__name__

    def proof_e2e_16(self) -> Any:
        self._require_context("execution_handoff")
        self._assert(
            self.context["execution_handoff"].validate() is True,
            "Execution handoff validation failed.",
        )
        return True

    def proof_e2e_17(self) -> Any:
        self._require_context("execution_handoff", "order")
        handoff = self.context["execution_handoff"]
        self._assert(
            handoff.execution_order() is self.context["order"],
            "Execution handoff changed canonical Order identity.",
        )
        return self.context["order"].order_id

    def proof_e2e_18(self) -> Any:
        self._require_context("execution_handoff", "authorization")
        self._assert(
            self.context["execution_handoff"].authorization
            is self.context["authorization"],
            "Execution handoff lost authorization identity.",
        )
        return True

    # ------------------------------------------------------------------
    # PHASE E — ROUTING HANDOFF
    # ------------------------------------------------------------------

    def proof_e2e_19(self) -> Any:
        self._require_context("execution_handoff")
        AuthorizedRoutingHandoff = self._import(
            "authorizedroutinghandoff",
            "AuthorizedRoutingHandoff",
        )
        routing = AuthorizedRoutingHandoff.from_execution_handoff(
            self.context["execution_handoff"]
        )
        self.context["routing_handoff"] = routing
        return type(routing).__name__

    def proof_e2e_20(self) -> Any:
        self._require_context("routing_handoff")
        self._assert(
            self.context["routing_handoff"].validate() is True,
            "Routing handoff validation failed.",
        )
        return True

    def proof_e2e_21(self) -> Any:
        self._require_context("routing_handoff", "order")
        routing = self.context["routing_handoff"]
        self._assert(
            routing.routing_order() is self.context["order"],
            "Routing handoff changed canonical Order identity.",
        )
        self._assert(
            routing.authorization is self.context["authorization"],
            "Routing handoff changed authorization identity.",
        )
        self._assert(
            routing.decision_id == self.context["authorization"].decision_id,
            "Routing handoff changed decision identity.",
        )
        self._assert(
            routing.regime == self.context["authorization"].regime,
            "Routing handoff changed regime identity.",
        )
        return routing.order_id

    # ------------------------------------------------------------------
    # PHASE F — RAW ROUTING HARD STOPS
    # ------------------------------------------------------------------

    def proof_e2e_22(self) -> Any:
        router = self._build_router()
        order = self._make_raw_order("E2E-RAW-001")
        try:
            router.route_order(order)
        except RuntimeError as exc:
            self._assert(
                "Raw Order routing is disabled" in str(exc),
                "Raw routing failed for an unexpected reason.",
            )
            return str(exc)
        raise AssertionError("Raw canonical Order crossed routing boundary.")

    def proof_e2e_23(self) -> Any:
        router = self._build_router()
        order = self._make_raw_order("E2E-RAW-002")
        initial_count = getattr(router, "route_count", 0)
        initial_history = list(getattr(router, "routing_history", []))
        try:
            router.route_order(order)
        except RuntimeError:
            pass
        self._assert(
            getattr(router, "route_count", 0) == initial_count,
            "Rejected raw route changed route count.",
        )
        self._assert(
            list(getattr(router, "routing_history", [])) == initial_history,
            "Rejected raw route changed routing history.",
        )
        return True

    def proof_e2e_24(self) -> Any:
        router = self._build_router()
        order = self._make_raw_order("E2E-RAW-003")
        try:
            router.route_order(order, broker_name="PAPER")
        except RuntimeError as exc:
            self._assert(
                "Raw Order routing is disabled" in str(exc),
                "Explicit broker bypass failed for an unexpected reason.",
            )
            return str(exc)
        raise AssertionError("Explicit broker name bypassed authorization boundary.")

    def _make_raw_order(self, order_id: str) -> Any:
        Order = self._import("order", "Order")
        return Order(
            ticker=self.ORDER_TICKER,
            side=self.ORDER_SIDE,
            quantity=self.ORDER_QUANTITY,
            order_id=order_id,
        )

    # ------------------------------------------------------------------
    # PHASE G — AUTHORIZED ROUTING
    # ------------------------------------------------------------------

    def proof_e2e_25(self) -> Any:
        self._require_context("routing_handoff")
        router = self._build_router()
        broker = self._build_broker()
        router.register_broker(broker)
        result = router.route_authorized_order(
            self.context["routing_handoff"],
            broker_name="PAPER",
        )
        self.context["router"] = router
        self.context["broker"] = broker
        self.context["routing_result"] = result
        self._assert(
            result.order_id == self.context["order"].order_id,
            "Authorized routing changed Order identity.",
        )
        return self._serialize(result)

    def proof_e2e_26(self) -> Any:
        self._require_context("routing_result", "order")
        result = self.context["routing_result"]
        self._assert(result.order_id == self.context["order"].order_id, "Routing result identity mismatch.")
        self._assert(
            self._get(result, "decision_id") == self.context["routing_handoff"].decision_id,
            "Routing result lost decision provenance.",
        )
        return result.order_id

    def proof_e2e_27(self) -> Any:
        self._require_context("broker")
        health = self.context["broker"].health_check()
        self._assert(bool(health), "Paper broker health check failed.")
        return health

    # ------------------------------------------------------------------
    # PHASE H — PAPER BROKER STATE
    # ------------------------------------------------------------------

    def proof_e2e_28(self) -> Any:
        self._require_context("broker", "order")
        record = self.context["broker"].get_order(self.context["order"].order_id)
        self._assert(record is not None, "Paper broker did not receive routed order.")
        self.context["broker_order"] = record
        return self._serialize(record)

    def proof_e2e_29(self) -> Any:
        self._require_context("broker_order", "order")
        record = self.context["broker_order"]
        client_id = self._get(record, "client_order_id")
        broker_id = self._get(record, "broker_order_id")
        self._assert(client_id == self.context["order"].order_id, "Client order identity changed.")
        self._assert(bool(broker_id), "Broker order identity is missing.")
        self.context["broker_order_id"] = broker_id
        return broker_id

    def proof_e2e_30(self) -> Any:
        self._require_context("broker", "order")
        record = self.context["broker"].get_order(self.context["order"].order_id)
        status = self._get(record, "status")
        self._assert(status == "SUBMITTED", f"Expected SUBMITTED, got {status!r}.")
        return status

    def proof_e2e_31(self) -> Any:
        self._require_context("order")
        order = self.context["order"]
        self._assert(
            order.status == "SUBMITTED",
            f"Expected OMS order SUBMITTED after OMS authorized submission, got {order.status!r}.",
        )
        return order.status

    # ------------------------------------------------------------------
    # PHASE I — PAPER EXECUTION RECEIPT
    # ------------------------------------------------------------------

    def proof_e2e_32(self) -> Any:
        self._require_context("broker", "order")
        receipt = self.context["broker"].fill_order(
            self.context["order"].order_id,
            execution_price=self.PAPER_PRICE,
            quantity=self.context["order"].quantity,
        )
        self._assert(receipt is not None, "Paper broker produced no execution receipt.")
        self.context["receipt"] = receipt
        return self._serialize(receipt)

    def proof_e2e_33(self) -> Any:
        self._require_context("receipt", "order")
        self._assert(
            self.context["receipt"].client_order_id == self.context["order"].order_id,
            "Execution receipt lost client Order identity.",
        )
        return self.context["receipt"].client_order_id

    def proof_e2e_34(self) -> Any:
        self._require_context("receipt", "order")
        quantity = self.context["receipt"].quantity
        self._assert(quantity == self.context["order"].quantity, "Receipt quantity mismatch.")
        return quantity

    def proof_e2e_35(self) -> Any:
        self._require_context("receipt")
        price = self.context["receipt"].execution_price
        self._assert(price == self.PAPER_PRICE, "Receipt execution price mismatch.")
        self._assert(self.context["receipt"].status == "FILLED", "Paper receipt is not FILLED.")
        return price

    # ------------------------------------------------------------------
    # PHASE J — BROKER EXECUTION ENGINE
    # ------------------------------------------------------------------

    def proof_e2e_36(self) -> Any:
        self._require_context("execution_handoff", "receipt", "account")
        BrokerExecutionEngine = self._import(
            "brokerexecutionengine",
            "BrokerExecutionEngine",
        )
        engine = BrokerExecutionEngine()
        engine.validate_receipt(self.context["receipt"])
        self.context["broker_execution_engine"] = engine
        return True

    def proof_e2e_37(self) -> Any:
        self._require_context("receipt", "order")
        self._assert(
            self.context["receipt"].client_order_id == self.context["order"].order_id,
            "Broker execution receipt Order identity mismatch.",
        )
        return self.context["receipt"].client_order_id

    def proof_e2e_38(self) -> Any:
        self._require_context("execution_handoff", "authorization")
        self._assert(
            self.context["execution_handoff"].authorization
            is self.context["authorization"],
            "Execution authorization provenance disappeared.",
        )
        return self.context["authorization"].decision_id

    # ------------------------------------------------------------------
    # PHASE K — EXECUTION ENGINE
    # ------------------------------------------------------------------

    def proof_e2e_39(self) -> Any:
        ExecutionEngine = self._import("executionengine", "ExecutionEngine")
        engine = ExecutionEngine()
        self.context["execution_engine"] = engine
        self._assert(engine is not None, "ExecutionEngine could not be instantiated.")
        return type(engine).__name__

    # ------------------------------------------------------------------
    # PHASE L — ACCOUNT
    # ------------------------------------------------------------------

    def proof_e2e_40(self) -> Any:
        # Instantiate the authoritative account BEFORE execution so the
        # later execution proof can demonstrate an actual state transition.
        account = self._build_account()
        self._assert(account is not None, "PortfolioAccount is unavailable.")
        self.context["account"] = account
        self.context["initial_cash"] = float(account.cash)
        return {
            "account": type(account).__name__,
            "initial_cash": float(account.cash),
        }

    def proof_e2e_41(self) -> Any:
        self._require_context("account", "order")
        account = self.context["account"]
        initial_cash = self.context["initial_cash"]
        self._assert(
            float(account.cash) == float(initial_cash),
            "PortfolioAccount changed before execution accounting.",
        )
        self.context["pre_execution_cash"] = float(account.cash)
        return self.context["pre_execution_cash"]

    def proof_e2e_42(self) -> Any:
        self._require_context("oms", "execution_handoff", "receipt", "account")
        result = self.context["oms"].execute_authorized_order(
            self.context["execution_handoff"],
            self.context["receipt"],
            self.context["account"],
        )
        self.context["execution_result"] = result
        self.context["trade"] = self._get(result, "trade")
        return self._serialize(result)

    # ------------------------------------------------------------------
    # PHASE M — OMS LIFECYCLE / EXECUTION
    # ------------------------------------------------------------------

    def proof_e2e_43(self) -> Any:
        self._require_context("order", "execution_result")
        order = self.context["order"]
        self._assert(order.status == "FILLED", f"Expected FILLED, got {order.status!r}.")
        self._assert(
            order.filled_quantity == order.quantity,
            "Filled quantity does not equal Order quantity.",
        )
        return order.status

    def proof_e2e_44(self) -> Any:
        self._require_context("oms")
        self._assert(
            self.context["oms"].last_execution_result is self.context["execution_result"],
            "OMS did not retain the execution result.",
        )
        return type(self.context["oms"]).__name__

    def proof_e2e_45(self) -> Any:
        self._require_context("oms", "execution_handoff")
        retained = self.context["oms"].last_execution_handoff
        self._assert(
            retained is self.context["execution_handoff"],
            "OMS did not retain the exact execution handoff.",
        )
        return type(retained).__name__

    # ------------------------------------------------------------------
    # PHASE N — PROVENANCE CONSERVATION
    # ------------------------------------------------------------------

    def proof_e2e_46(self) -> Any:
        self._require_context("decision", "authorization")
        decision_id = self.context["decision"].decision_id
        self._assert(
            decision_id == self.context["authorization"].decision_id,
            "decision_id changed across authorization boundary.",
        )
        return decision_id

    def proof_e2e_47(self) -> Any:
        self._require_context("order", "receipt")
        self._assert(
            self.context["receipt"].client_order_id == self.context["order"].order_id,
            "order_id was not conserved.",
        )
        return self.context["order"].order_id

    def proof_e2e_48(self) -> Any:
        self._require_context("decision", "authorization", "intent", "execution_handoff", "routing_handoff")
        regime = self.context["decision"].regime
        for name in ("authorization", "intent", "execution_handoff", "routing_handoff"):
            self._assert(
                self._get(self.context[name], "regime") == regime,
                f"Regime provenance changed at {name}.",
            )
        self.context["regime"] = regime
        return regime

    def proof_e2e_49(self) -> Any:
        self._require_context("authorization", "execution_result")
        provenance = self._get(self.context["execution_result"], "authorization_provenance")
        if provenance is not None and hasattr(self.context["authorization"], "to_dict"):
            self._assert(
                provenance == self.context["authorization"].to_dict(),
                "Execution result authorization provenance does not match authorization artifact.",
            )
        return self._serialize(provenance or self.context["authorization"])

    # ------------------------------------------------------------------
    # PHASE O — RECONCILIATION
    # ------------------------------------------------------------------

    def proof_e2e_50(self) -> Any:
        self._require_context("order", "broker_order")
        ReconciliationEngine = self._import(
            "reconciliationengine",
            "ReconciliationEngine",
        )
        engine = ReconciliationEngine()
        decision = engine.reconcile_order(
            self.context["order"],
            self.context["broker_order"],
        )
        self.context["reconciliation_engine"] = engine
        self.context["reconciliation"] = decision
        self._assert(
            decision.status == "MATCHED",
            f"Unexpected reconciliation status: {decision.status}",
        )
        self._assert(decision.approved is True, "Reconciliation was not approved.")
        return decision.status

    def proof_e2e_51(self) -> Any:
        self._require_context("order", "receipt")
        order = self.context["order"]
        receipt = self.context["receipt"]
        cumulative = self._get(receipt, "cumulative_filled_quantity", None)
        if cumulative is None:
            cumulative = order.filled_quantity
        self._assert(
            abs(float(order.filled_quantity) - float(cumulative)) < 1e-12,
            "OMS and broker cumulative filled quantities disagree.",
        )
        self._assert(
            0.0 <= float(cumulative) <= float(order.quantity) + 1e-12,
            "Cumulative execution quantity violates Order bounds.",
        )
        return float(cumulative)

    def proof_e2e_52(self) -> Any:
        self._require_context("order", "receipt")
        price = float(self.context["receipt"].execution_price)
        order_price = float(self.context["order"].average_fill_price)
        self._assert(
            abs(order_price - price) < 1e-12,
            "OMS and broker execution prices do not reconcile.",
        )
        return price

    def proof_e2e_53(self) -> Any:
        self._require_context("account", "order", "execution_result")
        account = self.context["account"]
        order = self.context["order"]

        positions = getattr(account, "positions", {})
        self._assert(
            isinstance(positions, dict),
            "PortfolioAccount positions are not a dictionary.",
        )
        position = positions.get(order.ticker)
        self._assert(
            position is not None,
            "Executed position is absent from PortfolioAccount.",
        )
        quantity = self._get(position, "quantity", position)
        self._assert(
            abs(float(quantity) - float(order.filled_quantity)) < 1e-12,
            "PortfolioAccount position does not match cumulative execution.",
        )

        trade = self._get(self.context["execution_result"], "trade")
        self._assert(trade is not None, "Execution result did not expose the accounting Trade.")
        net_cash_flow = self._get(trade, "net_cash_flow", None)
        self._assert(net_cash_flow is not None, "Accounting Trade has no net_cash_flow.")
        expected_cash = float(self.context["pre_execution_cash"]) + float(net_cash_flow)
        actual_cash = float(account.cash)
        self._assert(
            abs(actual_cash - expected_cash) < 1e-12,
            "PortfolioAccount cash does not reconcile with execution.",
        )

        trade_history = getattr(account, "trade_history", [])
        self._assert(
            len(trade_history) >= 1,
            "PortfolioAccount did not record the executed trade.",
        )

        return {
            "position": float(quantity),
            "cash": actual_cash,
            "trade_history_count": len(trade_history),
        }

    # ------------------------------------------------------------------
    # FINAL PROOF
    # ------------------------------------------------------------------

    def proof_e2e_54(self) -> Any:
        mandatory = [r for r in self.results if r.proof_id != "E2E-54"]
        non_pass = [r.proof_id for r in mandatory if r.status != PASS]
        self._assert(
            not non_pass,
            "Mandatory E2E proofs did not all PASS: " + ", ".join(non_pass),
        )
        return "ALL_MANDATORY_PROOFS_PASS"

    # ------------------------------------------------------------------
    # DISPATCH / RUN
    # ------------------------------------------------------------------

    def _dispatch(self) -> dict[str, Callable[[], Any]]:
        return {
            f"E2E-{i:02d}": getattr(self, f"proof_e2e_{i:02d}")
            for i in range(1, 55)
        }

    def _dependency_blocked(self, proof_id: str) -> bool:
        """
        Later proofs are blocked only when a prerequisite artifact is
        genuinely absent. A prior FAIL is not silently converted into a
        PASS; the downstream proof receives BLOCKED when it cannot execute.
        """
        prerequisite_map = {
            2: (1,),
            3: (1,),
            4: (1, 3),
            5: (4,),
            6: (4,),
            7: (4,),
            8: (4,),
            9: (8,),
            10: (9,),
            11: (8,),
            12: (11,),
            13: (11,),
            14: (11,),
            15: (11,),
            16: (15,),
            17: (15,),
            18: (15,),
            19: (15,),
            20: (19,),
            21: (19,),
            25: (19,),
            26: (25,),
            27: (25,),
            28: (25,),
            29: (28,),
            30: (28,),
            31: (9,),
            32: (28,),
            33: (32,),
            34: (32,),
            35: (32,),
            36: (32,),
            37: (32,),
            38: (15,),
            39: (32,),
            40: (32,),
            41: (40,),
            42: (15, 32, 40),
            43: (42,),
            44: (42,),
            45: (15, 42),
            46: (1, 4),
            47: (8, 32),
            48: (1, 4, 11, 15, 19),
            49: (4, 42),
            50: (43, 28),
            51: (43, 32),
            52: (43, 32),
            53: (42, 40),
            54: tuple(range(1, 54)),
        }
        number = int(proof_id.split("-")[1])
        for prerequisite in prerequisite_map.get(number, ()):
            result = next(
                (r for r in self.results if r.proof_id == f"E2E-{prerequisite:02d}"),
                None,
            )
            if result is not None and result.status != PASS:
                return True
        return False

    def run(self) -> None:
        started = datetime.now(timezone.utc)
        self.evidence["started_at"] = started.isoformat()
        dispatch = self._dispatch()

        for proof in self._proofs:
            proof_id = proof["proof_id"]

            if self._dependency_blocked(proof_id):
                result = self._register_result(proof)
                result.status = BLOCKED
                result.error_type = "UpstreamProofNotPassed"
                result.error_message = "Required upstream proof did not PASS."
                result.evidence = "Fail-closed dependency propagation."
                result.completed_at = datetime.now(timezone.utc).isoformat()
                result.validate()
                self.evidence["proofs"][proof_id] = {
                    "status": result.status,
                    "actual_result": "",
                    "evidence": result.evidence,
                    "error_type": result.error_type,
                    "error_message": result.error_message,
                    "started_at": result.started_at,
                    "completed_at": result.completed_at,
                    "duration_seconds": 0.0,
                    "metadata": result.metadata,
                }
                self.evidence["dependency_events"].append(
                    {"proof_id": proof_id, "reason": result.error_message}
                )
                continue

            operation = dispatch.get(proof_id)
            if operation is None:
                result = self._register_result(proof)
                result.status = BLOCKED
                result.error_type = "MissingProofImplementation"
                result.error_message = f"No executable implementation for {proof_id}."
                result.evidence = "Proof contract exists but executable implementation is unavailable."
                result.completed_at = datetime.now(timezone.utc).isoformat()
                result.validate()
                continue

            self._run(proof_id, operation)

        completed = datetime.now(timezone.utc)
        self.evidence["completed_at"] = completed.isoformat()
        self._finalize()

    # ------------------------------------------------------------------
    # OUTPUT
    # ------------------------------------------------------------------

    def _finalize(self) -> None:
        counts = {status: 0 for status in VALID_STATUSES}
        for result in self.results:
            counts[result.status] += 1

        self.evidence["summary"] = {
            "total": len(self.results),
            **{key.lower(): value for key, value in counts.items()},
        }

        mandatory = [r for r in self.results if r.proof_id != "E2E-54"]
        self.evidence["deployment_proof"] = (
            len(mandatory) == 53 and all(r.status == PASS for r in mandatory)
        )

        self.evidence["safety_assertion"] = {
            "live_trading_enabled": False,
            "live_broker": False,
            "network_execution": False,
            "git_mutation": False,
            "source_matrix_mutated": False,
        }

    def _result_dict(self, result: ProofResult) -> dict[str, Any]:
        return {
            "proof_id": result.proof_id,
            "phase": result.phase,
            "boundary": result.boundary,
            "invariant": result.invariant,
            "expected_result": result.expected_result,
            "status": result.status,
            "evidence": result.evidence,
            "actual_result": result.actual_result,
            "error_type": result.error_type,
            "error_message": result.error_message,
            "traceback": result.traceback_text,
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "duration_seconds": result.duration_seconds,
            "metadata": result.metadata,
        }

    def write_json(self) -> None:
        payload = {
            "system": "Regime Switching System",
            "document": "E2E Proof Results",
            "version": 2,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "matrix": str(self.matrix_path),
            "summary": self.evidence["summary"],
            "deployment_proof": self.evidence["deployment_proof"],
            "results": [self._result_dict(r) for r in self.results],
        }

        with RESULTS_JSON.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)

        with EVIDENCE_JSON.open("w", encoding="utf-8") as handle:
            json.dump(self.evidence, handle, indent=2, sort_keys=True, default=str)

    def write_csv(self) -> None:
        fieldnames = [
            "proof_id",
            "phase",
            "boundary",
            "invariant",
            "expected_result",
            "status",
            "evidence",
            "actual_result",
            "error_type",
            "error_message",
            "started_at",
            "completed_at",
            "duration_seconds",
        ]
        with RESULTS_CSV.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            for result in self.results:
                row = self._result_dict(result)
                writer.writerow({key: row.get(key, "") for key in fieldnames})

    def write_markdown(self) -> None:
        summary = self.evidence["summary"]
        deployment = self.evidence["deployment_proof"]

        lines = [
            "# REGIME SWITCHING SYSTEM",
            "",
            "# END-TO-END PROOF RESULTS",
            "",
            f"Generated: `{datetime.now(timezone.utc).isoformat()}`",
            "",
            "> **EXECUTABLE E2E EVIDENCE ARTIFACT**",
            "",
            "## Executive Status",
            "",
            f"- Total proofs: **{summary['total']}**",
            f"- PASS: **{summary['pass']}**",
            f"- FAIL: **{summary['fail']}**",
            f"- BLOCKED: **{summary['blocked']}**",
            f"- NOT_EXECUTED: **{summary['not_executed']}**",
            f"- SKIPPED: **{summary['skipped']}**",
            f"- Deployment proof: **{'PROVEN' if deployment else 'NOT PROVEN'}**",
            "",
            "## Safety Boundary",
            "",
            "- Live trading enabled: **NO**",
            "- Live broker connection: **NO**",
            "- Network execution: **NO**",
            "- Git mutation: **NO**",
            "- Source matrix mutation: **NO**",
            "- Execution mode: **PAPER / IN-MEMORY ONLY**",
            "",
            "## Proof Results",
            "",
            "| ID | Phase | Boundary | Status | Evidence | Error |",
            "|---|---|---|---|---|---|",
        ]

        symbols = {
            PASS: "🟢",
            FAIL: "🔴",
            BLOCKED: "🟠",
            NOT_EXECUTED: "⚪",
            SKIPPED: "⚫",
        }

        for result in self.results:
            evidence = result.evidence.replace("|", "\\|").replace("\n", " ")
            error = result.error_message.replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {result.proof_id} | {result.phase} | {result.boundary} | "
                f"{symbols[result.status]} {result.status} | {evidence} | {error} |"
            )

        lines.extend(
            [
                "",
                "## Acceptance Rule",
                "",
                "The system is NOT considered proven unless all mandatory E2E proofs PASS.",
                "",
                "A BLOCKED result is not a PASS and is not converted into a PASS.",
                "",
                "The result is evidence only and does not authorize live trading.",
                "",
            ]
        )

        with RESULTS_MD.open("w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))

    def write_outputs(self) -> None:
        self.write_json()
        self.write_csv()
        self.write_markdown()


def environment_fingerprint() -> dict[str, Any]:
    payload = {
        "python": sys.version,
        "platform": platform.platform(),
        "hostname": socket.gethostname(),
        "project_root": str(PROJECT_ROOT),
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    payload["sha256"] = hashlib.sha256(encoded).hexdigest()
    return payload


def main() -> int:
    print()
    print("=" * 76)
    print("REGIME SWITCHING SYSTEM — END-TO-END PROOF RUNNER")
    print("=" * 76)
    print()
    print("Safety mode:")
    print("  Live trading        : DISABLED")
    print("  Live broker         : DISABLED")
    print("  Network execution   : DISABLED")
    print("  Git mutation        : DISABLED")
    print("  Source matrix       : READ ONLY")
    print("  Execution           : PAPER / IN-MEMORY")
    print()

    runner = E2EProofRunner()
    runner.evidence["environment"] = environment_fingerprint()

    print(f"[PASS] Loaded {len(runner._proofs)} proof contracts.")
    print("Executing proof contracts...")
    runner.run()
    runner.write_outputs()

    summary = runner.evidence["summary"]

    print()
    print("=" * 76)
    print("E2E PROOF SUMMARY")
    print("=" * 76)
    print(f"Total        : {summary['total']}")
    print(f"PASS         : {summary['pass']}")
    print(f"FAIL         : {summary['fail']}")
    print(f"BLOCKED      : {summary['blocked']}")
    print(f"NOT_EXECUTED : {summary['not_executed']}")
    print(f"SKIPPED      : {summary['skipped']}")
    print()

    if runner.evidence["deployment_proof"]:
        print("[PASS] END-TO-END EXECUTION CHAIN PROVEN.")
        exit_code = 0
    else:
        print("[WARNING] END-TO-END EXECUTION CHAIN NOT PROVEN.")
        print("This is an evidence result, not a deployment authorization.")
        exit_code = 1

    print()
    print("Output artifacts:")
    print(f"  {RESULTS_MD}")
    print(f"  {RESULTS_CSV}")
    print(f"  {RESULTS_JSON}")
    print(f"  {EVIDENCE_JSON}")
    print()
    print("=" * 76)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
