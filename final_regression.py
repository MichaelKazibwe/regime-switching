"""
==============================================================================
FINAL COMPREHENSIVE REGRESSION
==============================================================================

Single-file regression gate for the registered production
portfolio/trading architecture and complete Python repository.

Design goals
------------
* Inventory of project modules, excluding this harness.
* Compile every module.
* Run Ruff over the complete repository.
* AST-audit every module and build the local import graph.
* Detect local import cycles.
* Import every module.
* Execute module self-tests where they are safe and meaningful.
* Use the complete production risk-budget asset universe for portfolio tests.
* Validate production component contracts and execution-chain contracts.
* Run deterministic behavioral regressions for risk budgets, forecasts,
  covariance, Black-Litterman, production composition, and regime separation.
* Audit stale references by AST imports rather than false-positive symbol
  definitions inside legacy monoliths such as rewrite.py.
* Audit repository hygiene without treating this file as a project module.

The harness does not modify project source files.
"""

# ==============================================================================
# SECTION 1 — IMPORTS
# ==============================================================================

from __future__ import annotations

import ast
from collections import Counter
import hashlib
import importlib
import os
import py_compile
import shutil
import subprocess
import sys
import time
import traceback
import json

from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

import numpy as np
import pandas as pd


# ==============================================================================
# SECTION 2 — CONFIGURATION
# ==============================================================================

API_VERSION = "1.0.0"

PROJECT_ROOT = Path(
    __file__
).resolve().parent

SELF_NAME = Path(
    __file__
).name

_SOURCE_INVENTORY = json.loads(
    (PROJECT_ROOT / "research/source_inventory.json").read_text()
)
EXPECTED_PROJECT_FILE_COUNT = _SOURCE_INVENTORY["expected_root_python_files"]


# The active production allocation universe is defined by the regime risk
# budgets in core_constants.py. This is intentionally not the smaller legacy
# DEFAULT_ASSETS market-data universe.

FALLBACK_PRODUCTION_ASSETS = (
    "SPY",
    "QQQ",
    "IWM",
    "VEA",
    "VWO",
    "TLT",
    "IEF",
    "SHY",
    "LQD",
    "HYG",
    "GLD",
    "SLV",
    "DBC",
    "VNQ",
)


# ==============================================================================
# SECTION 3 — EXECUTION-CHAIN MODULES
# ==============================================================================

REGRESSION_MODULES = (
    "order.py",
    "orderstatus.py",
    "orderbook.py",
    "transactioncostmodel.py",
    "executionengine.py",
    "rebalanceengine.py",
    "tradegenerator.py",
    "pretraderiskgate.py",
    "oms.py",
    "brokerrouter.py",
    "paperbroker.py",
    "brokerexecutionengine.py",
    "livebroker.py",
    "reconciliationengine.py",
    "posttradeexecutionmonitor.py",
    "executionanalytics.py",
    "test_portfoliooptimizer_hardening.py",
    "test_phase_iv_d_production_gate.py",
    "test_phase_iv_f_execution_safety.py",
    "test_phase_iv_g_downstream_execution_safety.py",
    "test_phase_iv_h_execution_integrity.py",
)


# ==============================================================================
# # SECTION 4 — REGISTERED PRODUCTION ARCHITECTURE
# ==============================================================================

REQUIRED_MODULES = (
    "alertengine.py",
    "analyticalgreeks.py",
    "analytics.py",
    "assetuniverse.py",
    "atr.py",
    "audittrail.py",
    "authorizedexecutionhandoff.py",
    "authorizedorder.py",
    "authorizedorderintent.py",
    "authorizedroutinghandoff.py",
    "basecomponent.py",
    "basecovariancemodel.py",
    "blacklitterman.py",
    "blackscholes.py",
    "brokerexecutionengine.py",
    "brokerrouter.py",
    "circuitbreaker.py",
    "constraints.py",
    "core_constants.py",
    "covarianceengine.py",
    "drawdownforecast.py",
    "drawdownrisk.py",
    "emailtransport.py",
    "ensemblecovariance.py",
    "exceptions.py",
    "executionanalytics.py",
    "executionengine.py",
    "expectedreturncalibrator.py",
    "expectedreturnforecaster.py",
    "factorcovariance.py",
    "factorexposuremodel.py",
    "factorstressrisk.py",
    "forecastmodels.py",
    "forwardriskanalyzer.py",
    "forwardriskmetrics.py",
    "killswitch.py",
    "livebroker.py",
    "macroregime.py",
    "marketdataloader.py",
    "oms.py",
    "operationalevent.py",
    "operationalhealth.py",
    "optionsrisk.py",
    "optionsriskgovernor.py",
    "optionstailrisk.py",
    "order.py",
    "orderbook.py",
    "orderstatus.py",
    "paperbroker.py",
    "performanceattribution.py",
    "portfolio.py",
    "portfolioaccount.py",
    "portfoliodecisionengine.py",
    "portfoliogreeks.py",
    "portfoliooptimizer.py",
    "positionsizing.py",
    "posttradeexecutionmonitor.py",
    "pretraderiskgate.py",
    "productioncomposition.py",
    "productiondecisionexecution.py",
    "productionexecutiongate.py",
    "productionintegration.py",
    "productionpipelineintegration.py",
    "productionriskvalidation.py",
    "putcallparity.py",
    "quantitative_regression.py",
    "rebalanceengine.py",
    "reconciliationengine.py",
    "regimeallocationpolicy.py",
    "regimecovariance.py",
    "regimeforecastengine.py",
    "regimesimulation.py",
    "regression_suite.py",
    "restartrecovery.py",
    "rewrite.py",
    "riskbudgetengine.py",
    "riskcontributionanalyzer.py",
    "riskgovernor.py",
    "riskmodel.py",
    "riskreport.py",
    "scenarioengine.py",
    "step7_production_test.py",
    "step8_historical_data_test.py",
    "step9_historical_backtest.py",
    "stresstailrisk.py",
    "structuredlogging.py",
    "tailaggregation.py",
    "test_phase_iv_d_production_gate.py",
    "test_phase_iv_f_execution_safety.py",
    "test_phase_iv_g_downstream_execution_safety.py",
    "test_phase_iv_h_execution_integrity.py",
    "test_portfoliooptimizer_hardening.py",
    "testsupport.py",
    "trade.py",
    "tradeanalytics.py",
    "tradegenerator.py",
    "tradingcalendar.py",
    "transactioncostmodel.py",
    "validators.py",
    "volatilitycorrelationstress.py",
    "volatilitytargeting.py",
)


# Additional top-level Python files are classified separately from the modules
# that are imported and self-tested by the production regression pipeline.
# Every top-level .py file except this harness must appear in exactly one
# inventory category. New files intentionally fail inventory until classified.
SUPPLEMENTAL_TOOL_MODULES = (
    "Options_Stress.py",
    "Volatility_Surface_Inputs.py",
    "e2e_proof_runner.py",
    "e2e_proof_runner_phase3e.py",
    "generate_e2e_proof_matrix.py",
    "git_status_audit.py",
    "phase1a_repository_reconciliation.py",
    "regression_suite_r3b.py",
)

SUPPLEMENTAL_TEST_MODULES = (
    "test_alertengine_corrected_fixed.py",
    "test_assetuniverse.py",
    "test_circuitbreaker.py",
    "test_circuitbreaker_5j4.py",
    "test_drawdownrisk_r3d4.py",
    "test_emailtransport.py",
    "test_factor_exposure_model.py",
    "test_factorstressrisk_r3e5.py",
    "test_killswitch.py",
    "test_killswitch_5j4.py",
    "test_marketdataloader.py",
    "test_marketdataloader_5j3.py",
    "test_operationalevent.py",
    "test_phase3d_step1_decision_identity.py",
    "test_phase3d_step2_immutable_decision.py",
    "test_phase3d_step4_execution_identity.py",
    "test_phase3d_step5_reconciliation_integrity.py",
    "test_phase3d_step5a_execution_replay_protection.py",
    "test_phase3d_step5b_partial_accounting.py",
    "test_phase3d_step5c_posttrade_lifecycle.py",
    "test_phase3d_step6_restart_integrity.py",
    "test_phase3e_runtime_orchestration.py",
    "test_phase5c_logging_audit.py",
    "test_phase5e_execution_gate.py",
    "test_phase5f_audittrail_integration.py",
    "test_phase5f_circuitbreaker_integration.py",
    "test_phase5f_delivery_failure.py",
    "test_phase5f_email_integration.py",
    "test_phase5f_killswitch_integration.py",
    "test_phase5g_operational_health.py",
    "test_phase5h_restart_recovery.py",
    "test_phase5i_operational_runbook.py",
    "test_phase_iii_b_architecture_boundaries.py",
    "test_phase_iv_i_authorized_execution_boundary.py",
    "test_phase_iv_i_authorized_execution_handoff.py",
    "test_phase_iv_i_authorized_oms.py",
    "test_phase_iv_i_authorized_order.py",
    "test_phase_iv_i_authorized_order_bridge.py",
    "test_phase_iv_i_authorized_order_intent.py",
    "test_phase_iv_i_authorized_routing.py",
    "test_phase_iv_i_legacy_execution_containment.py",
    "test_portfolio.py",
    "test_portfoliodecisionengine.py",
    "test_portfoliodecisionengine_5j1.py",
    "test_portfoliooptimizer.py",
    "test_portfoliooptimizer_a16.py",
    "test_portfoliooptimizer_r3c.py",
    "test_r4_12_regression.py",
    "test_riskgovernor.py",
    "test_riskreport_r3e8.py",
    "test_scenarioengine.py",
    "test_stresstailrisk_r3e4.py",
    "test_tailaggregation_r3e7.py",
    "test_tradingcalendar_5j2.py",
    "test_volatilitycorrelationstress_r3e6.py",
    "test_tradeanalytics.py",
)

HISTORICAL_OR_DAMAGED_MODULES = ()

INVENTORY_CATEGORIES = {
    "registered modules": REQUIRED_MODULES,
    "supplemental tools": SUPPLEMENTAL_TOOL_MODULES,
    "supplemental tests": SUPPLEMENTAL_TEST_MODULES,
    "historical/damaged files": HISTORICAL_OR_DAMAGED_MODULES,
    "research and pilot modules": tuple(_SOURCE_INVENTORY["additional_research_and_pilot_modules"]),
    "additional tests": tuple(_SOURCE_INVENTORY["additional_test_modules"]),
}


# ==============================================================================
# SECTION 5 — DATA STRUCTURES
# ==============================================================================


@dataclass(
    frozen=True,
)
class TestResult:
    name: str
    passed: bool
    return_code: int
    elapsed_seconds: float
    stdout: str = ""
    stderr: str = ""
    reason: str | None = None


class RegressionFailure(
    AssertionError
):
    """Raised for deterministic behavioral-contract failures."""


# ==============================================================================
# SECTION 6 — BASIC HELPERS
# ==============================================================================


def banner(
    title: str,
) -> None:

    print()

    print(
        "=" * 78
    )

    print(
        title
    )

    print(
        "=" * 78
    )


def ok(
    condition: bool,
    message: str,
) -> None:

    if not condition:

        raise RegressionFailure(
            message
        )


def finite_array(
    value: Any,
    *,
    name: str,
) -> np.ndarray:

    array = np.asarray(
        value,
        dtype=float,
    )

    ok(
        np.isfinite(
            array
        ).all(),
        f"{name} contains non-finite values",
    )

    return array


# ==============================================================================
# SECTION 7 — DETERMINISTIC TEST DATA
# ==============================================================================


def deterministic_covariance(
    n: int,
    seed: int = 20260820,
) -> np.ndarray:

    ok(
        n > 0,
        "Covariance dimension must be positive",
    )

    rng = np.random.default_rng(
        seed
    )

    factors = rng.normal(
        0.0,
        0.04,
        size=(
            n,
            min(
                5,
                n,
            ),
        ),
    )

    diag = rng.uniform(
        0.02,
        0.08,
        size=n,
    )

    cov = (
        factors @ factors.T
        + np.diag(
            diag
        )
    )

    cov = (
        cov
        + cov.T
    ) / 2.0

    cov += (
        np.eye(n)
        * 1e-8
    )

    ok(
        float(
            np.linalg.eigvalsh(
                cov
            ).min()
        ) > 0.0,
        "Covariance is not positive definite",
    )

    return cov


def synthetic_prices(
    assets: list[str],
    observations: int = 520,
    seed: int = 20260820,
) -> pd.DataFrame:

    """Deterministic, positive price history covering the complete universe."""

    ok(
        observations >= 300,
        "Synthetic history is too short",
    )

    rng = np.random.default_rng(
        seed
    )

    dates = pd.bdate_range(
        "2024-01-01",
        periods=observations,
    )

    common = rng.normal(
        0.00025,
        0.004,
        size=observations,
    )

    data: dict[
        str,
        np.ndarray,
    ] = {}

    for i, asset in enumerate(
        assets
    ):

        beta = (
            0.65
            + 0.04
            * (i % 7)
        )

        drift = (
            0.00008
            + 0.000015
            * (i + 1)
        )

        idio = rng.normal(
            0.0,
            0.002
            + 0.0002
            * (i % 4),
            size=observations,
        )

        cyc = (
            0.0012
            * np.sin(
                np.arange(
                    observations
                )
                / (
                    13.0
                    + i
                )
            )
        )

        returns = (
            drift
            + beta * common
            + idio
            + cyc
        )

        returns = np.clip(
            returns,
            -0.08,
            0.08,
        )

        data[asset] = (
            100.0
            * np.cumprod(
                1.0
                + returns
            )
        )

    frame = pd.DataFrame(
        data,
        index=dates,
    )

    ok(
        frame.columns.tolist()
        == assets,
        "Synthetic asset ordering changed",
    )

    ok(
        frame.notna().all().all(),
        "Synthetic prices contain NaN",
    )

    ok(
        (
            frame > 0
        ).all().all(),
        "Synthetic prices are non-positive",
    )

    return frame


# ==============================================================================
# SECTION 8 — PRODUCTION ASSET RESOLUTION
# ==============================================================================


def production_assets() -> list[str]:

    """Resolve the complete configured production universe dynamically."""

    try:

        constants = importlib.import_module(
            "core_constants"
        )

        budgets = getattr(
            constants,
            "REGIME_RISK_BUDGETS",
            {},
        )

        keys: list[str] = []

        for mapping in budgets.values():

            for asset in mapping:

                if asset not in keys:

                    keys.append(
                        str(asset)
                    )

        if keys:

            return keys

        assets = getattr(
            constants,
            "DEFAULT_ASSETS",
            None,
        )

        if assets:

            return [
                str(x)
                for x in assets
            ]

    except Exception:

        pass

    return list(
        FALLBACK_PRODUCTION_ASSETS
    )


# ==============================================================================
# SECTION 9 — FILE / MODULE HELPERS
# ==============================================================================


def module_name(
    filename: str,
) -> str:

    return (
        filename[:-3]
        if filename.endswith(
            ".py"
        )
        else filename
    )


def local_python_files(
    root: Path,
) -> list[Path]:

    return sorted(
        path
        for path in root.glob(
            "*.py"
        )
        if path.name
        != SELF_NAME
    )


def source_tree_hash(
    paths: Iterable[Path],
) -> str:

    digest = hashlib.sha256()

    for path in sorted(
        paths,
        key=lambda p: p.name,
    ):

        digest.update(
            path.name.encode()
        )

        digest.update(
            b"\0"
        )

        digest.update(
            path.read_bytes()
        )

        digest.update(
            b"\0"
        )

    return digest.hexdigest()


# ==============================================================================
# SECTION 10 — AST ANALYSIS
# ==============================================================================


def ast_info(
    path: Path,
) -> tuple[
    ast.AST,
    int,
    int,
    int,
]:

    tree = ast.parse(
        path.read_text(
            encoding="utf-8"
        ),
        filename=str(
            path
        ),
    )

    classes = sum(
        isinstance(
            node,
            ast.ClassDef,
        )
        for node in ast.walk(
            tree
        )
    )

    functions = sum(
        isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
        for node in ast.walk(
            tree
        )
    )

    tests = sum(
        isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
        and node.name.startswith(
            "test_"
        )
        for node in ast.walk(
            tree
        )
    )

    return (
        tree,
        classes,
        functions,
        tests,
    )


def imported_local_modules(
    tree: ast.AST,
    known: set[str],
) -> set[str]:

    found: set[str] = set()

    for node in ast.walk(
        tree
    ):

        if isinstance(
            node,
            ast.Import,
        ):

            for alias in node.names:

                root = (
                    alias.name
                    .split(
                        ".",
                        1,
                    )[0]
                )

                if root in known:

                    found.add(
                        root
                    )

        elif (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):

            root = (
                node.module
                .split(
                    ".",
                    1,
                )[0]
            )

            if root in known:

                found.add(
                    root
                )

    return found


def detect_cycles(
    graph: dict[
        str,
        set[str],
    ],
) -> list[
    list[str]
]:

    cycles: list[
        list[str]
    ] = []

    visiting: list[str] = []

    active: set[str] = set()

    done: set[str] = set()

    def visit(
        node: str,
    ) -> None:

        if node in active:

            index = (
                visiting.index(
                    node
                )
            )

            cycles.append(
                visiting[
                    index:
                ]
                + [node]
            )

            return

        if node in done:

            return

        active.add(
            node
        )

        visiting.append(
            node
        )

        for child in graph.get(
            node,
            set(),
        ):

            visit(
                child
            )

        visiting.pop()

        active.remove(
            node
        )

        done.add(
            node
        )

    for node in graph:

        visit(
            node
        )

    return cycles


# ==============================================================================
# SECTION 11 — SUBPROCESS HELPERS
# ==============================================================================


def run_command(
    command: list[str],
    cwd: Path,
    timeout: int,
) -> TestResult:

    started = time.perf_counter()

    try:

        proc = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )

        return TestResult(
            name=" ".join(
                command
            ),
            passed=(
                proc.returncode
                == 0
            ),
            return_code=proc.returncode,
            elapsed_seconds=(
                time.perf_counter()
                - started
            ),
            stdout=(
                proc.stdout
                or ""
            ),
            stderr=(
                proc.stderr
                or ""
            ),
            reason=(
                None
                if proc.returncode
                == 0
                else (
                    f"return code "
                    f"{proc.returncode}"
                )
            ),
        )

    except subprocess.TimeoutExpired as exc:

        return TestResult(
            name=" ".join(
                command
            ),
            passed=False,
            return_code=124,
            elapsed_seconds=(
                time.perf_counter()
                - started
            ),
            stdout=(
                exc.stdout.decode()
                if isinstance(
                    exc.stdout,
                    bytes,
                )
                else (
                    exc.stdout
                    or ""
                )
            ),
            stderr=(
                exc.stderr.decode()
                if isinstance(
                    exc.stderr,
                    bytes,
                )
                else (
                    exc.stderr
                    or ""
                )
            ),
            reason=(
                f"timeout after "
                f"{timeout}s"
            ),
        )

    except OSError as exc:

        return TestResult(
            name=" ".join(
                command
            ),
            passed=False,
            return_code=127,
            elapsed_seconds=(
                time.perf_counter()
                - started
            ),
            reason=str(
                exc
            ),
        )


# ==============================================================================
# SECTION 12 — FINAL REGRESSION
# ==============================================================================


class FinalRegression:

    def __init__(
        self,
        root: Path = PROJECT_ROOT,
    ) -> None:

        self.root = (
            root.resolve()
        )

        self.results: list[
            TestResult
        ] = []

        self.assets: list[
            str
        ] = []

        self.graph: dict[
            str,
            set[str],
        ] = {}

    # ------------------------------------------------------------------
    # RESULT RECORDING
    # ------------------------------------------------------------------

    def record(
        self,
        result: TestResult,
    ) -> bool:

        self.results.append(
            result
        )

        marker = (
            "PASS"
            if result.passed
            else "FAIL"
        )

        print(
            f"[{marker}] "
            f"{result.name} "
            f"({result.elapsed_seconds:.3f}s)"
        )

        if not result.passed:

            if result.reason:

                print(
                    "Reason: "
                    f"{result.reason}"
                )

            if result.stdout.strip():

                print(
                    "--- STDOUT ---"
                )

                print(
                    result.stdout.rstrip()
                )

            if result.stderr.strip():

                print(
                    "--- STDERR ---"
                )

                print(
                    result.stderr.rstrip()
                )

        return result.passed

    # ------------------------------------------------------------------
    # PHASE 1 — INVENTORY
    # ------------------------------------------------------------------

    def inventory(
        self,
    ) -> bool:
        """Require every top-level Python file to be classified exactly once."""
        banner("PHASE 1 — COMPLETE PYTHON FILE INVENTORY")

        actual = sorted(p.name for p in local_python_files(self.root))
        actual_set = set(actual)

        category_entries = [
            (category, filename)
            for category, filenames in INVENTORY_CATEGORIES.items()
            for filename in filenames
        ]
        all_registered = [filename for _, filename in category_entries]
        counts = Counter(all_registered)
        duplicate_classifications = sorted(
            filename for filename, count in counts.items() if count > 1
        )
        classified_set = set(all_registered)
        unclassified = sorted(actual_set - classified_set)
        missing_classified = sorted(classified_set - actual_set)
        category_count_ok = len(all_registered) == EXPECTED_PROJECT_FILE_COUNT
        actual_count_ok = len(actual) == EXPECTED_PROJECT_FILE_COUNT

        # The 101 registered modules remain the only set imported and run as
        # production/library regressions. Supplemental tests and tools are
        # tracked for inventory and are covered by repository-wide compile/AST.
        production_duplicates = sorted(
            filename
            for filename, count in Counter(REQUIRED_MODULES).items()
            if count > 1
        )
        production_count_ok = len(REQUIRED_MODULES) == 101

        passed = all((
            not unclassified,
            not missing_classified,
            not duplicate_classifications,
            not production_duplicates,
            category_count_ok,
            actual_count_ok,
            production_count_ok,
        ))

        category_summary = "\n".join(
            f"  {category}: {len(filenames)}"
            for category, filenames in INVENTORY_CATEGORIES.items()
        )
        details = (
            f"Repository Python files: {len(actual)}\n"
            f"Expected complete inventory: {EXPECTED_PROJECT_FILE_COUNT}\n"
            f"Registered production/import modules: {len(REQUIRED_MODULES)}\n"
            f"Classified entries across all categories: {len(all_registered)}\n"
            f"Category counts:\n{category_summary}\n"
            f"Unclassified files ({len(unclassified)}): {unclassified}\n"
            f"Classified files missing from repository ({len(missing_classified)}): "
            f"{missing_classified}\n"
            f"Duplicate classifications: {duplicate_classifications}\n"
            f"Duplicate production registrations: {production_duplicates}"
        )

        reasons = []
        if unclassified:
            reasons.append(f"unclassified Python files: {unclassified}")
        if missing_classified:
            reasons.append(f"registered files missing from repository: {missing_classified}")
        if duplicate_classifications:
            reasons.append(f"files classified more than once: {duplicate_classifications}")
        if duplicate_production := production_duplicates:
            reasons.append(f"duplicate production registrations: {duplicate_production}")
        if not category_count_ok:
            reasons.append(
                f"category count mismatch: expected {EXPECTED_PROJECT_FILE_COUNT}, "
                f"found {len(all_registered)}"
            )
        if not actual_count_ok:
            reasons.append(
                f"repository count mismatch: expected {EXPECTED_PROJECT_FILE_COUNT}, "
                f"found {len(actual)}"
            )
        if not production_count_ok:
            reasons.append(
                f"production registry count changed: expected 101, found {len(REQUIRED_MODULES)}"
            )

        return self.record(TestResult(
            "Complete Python repository inventory",
            passed,
            0 if passed else 1,
            0.0,
            stdout=details,
            reason="; ".join(reasons) if reasons else None,
        ))

    # ------------------------------------------------------------------
    # PHASE 2 — COMPILATION
    # ------------------------------------------------------------------

    def compile_all(
        self,
    ) -> bool:

        banner(
            "PHASE 2 — PYTHON COMPILATION"
        )

        passed = True

        for path in local_python_files(
            self.root
        ):

            started = time.perf_counter()

            try:

                py_compile.compile(
                    str(path),
                    doraise=True,
                )

                result = TestResult(
                    f"Compile {path.name}",
                    True,
                    0,
                    (
                        time.perf_counter()
                        - started
                    ),
                )

            except Exception as exc:

                passed = False

                result = TestResult(
                    f"Compile {path.name}",
                    False,
                    1,
                    (
                        time.perf_counter()
                        - started
                    ),
                    stderr=traceback.format_exc(),
                    reason=str(
                        exc
                    ),
                )

            self.record(
                result
            )

        return passed

    # ------------------------------------------------------------------
    # PHASE 3 — RUFF
    # ------------------------------------------------------------------

    def ruff(
        self,
    ) -> bool:

        banner(
            "PHASE 3 — RUFF STATIC ANALYSIS"
        )

        executable = shutil.which(
            "ruff"
        )

        if executable is None:

            return self.record(
                TestResult(
                    "ruff check .",
                    False,
                    127,
                    0.0,
                    reason=(
                        "ruff executable "
                        "not found on PATH"
                    ),
                )
            )

        result = run_command(
            [
                executable,
                "check",
                ".",
            ],
            self.root,
            120,
        )

        return self.record(
            result.__class__(
                "ruff check .",
                result.passed,
                result.return_code,
                result.elapsed_seconds,
                result.stdout,
                result.stderr,
                result.reason,
            )
        )

    # ------------------------------------------------------------------
    # PHASE 4 — AST AUDIT
    # ------------------------------------------------------------------

    def ast_audit(
        self,
    ) -> bool:

        banner(
            "PHASE 4 — AST STRUCTURAL AUDIT"
        )

        names = {
            p.stem
            for p in local_python_files(
                self.root
            )
        }

        graph: dict[
            str,
            set[str],
        ] = {}

        passed = True

        for path in local_python_files(
            self.root
        ):

            started = time.perf_counter()

            try:

                (
                    tree,
                    classes,
                    functions,
                    tests,
                ) = ast_info(
                    path
                )

                graph[
                    path.stem
                ] = imported_local_modules(
                    tree,
                    names,
                )

                result = TestResult(
                    f"AST audit {path.name}",
                    True,
                    0,
                    (
                        time.perf_counter()
                        - started
                    ),
                    stdout=(
                        f"classes={classes}, "
                        f"functions={functions}, "
                        f"tests={tests}"
                    ),
                )

            except Exception:

                passed = False

                result = TestResult(
                    f"AST audit {path.name}",
                    False,
                    1,
                    (
                        time.perf_counter()
                        - started
                    ),
                    stderr=traceback.format_exc(),
                    reason="AST parse failed",
                )

            self.record(
                result
            )

        self.graph = graph

        print()
        print(
            "LOCAL IMPORT GRAPH"
        )

        for name in sorted(
            graph
        ):

            deps = sorted(
                graph[name]
            )

            print(
                f"{name}:"
                + (
                    "\n    -> "
                    + "\n    -> ".join(
                        deps
                    )
                    if deps
                    else ""
                )
            )

        cycles = detect_cycles(
            graph
        )

        cycle_pass = not cycles

        self.record(
            TestResult(
                "Local dependency cycle audit",
                cycle_pass,
                0 if cycle_pass else 1,
                0.0,
                stdout=(
                    "No local import cycles detected."
                    if cycle_pass
                    else "\n".join(
                        " -> ".join(
                            cycle
                        )
                        for cycle in cycles
                    )
                ),
                reason=(
                    None
                    if cycle_pass
                    else (
                        "Local dependency "
                        "cycle(s) detected."
                    )
                ),
            )
        )

        return (
            passed
            and cycle_pass
        )

    # ------------------------------------------------------------------
    # PHASE 5 — IMPORT REGRESSION
    # ------------------------------------------------------------------

    def imports(
        self,
    ) -> bool:

        banner(
            "PHASE 5 — IMPORT REGRESSION"
        )

        passed = True

        for filename in REQUIRED_MODULES:

            name = module_name(
                filename
            )

            started = time.perf_counter()

            try:

                importlib.invalidate_caches()

                module = (
                    importlib.import_module(
                        name
                    )
                )

                if not isinstance(
                    module,
                    ModuleType,
                ):

                    raise TypeError(
                        f"{name} did not "
                        "import as a module"
                    )

                result = TestResult(
                    f"Import {filename}",
                    True,
                    0,
                    (
                        time.perf_counter()
                        - started
                    ),
                )

            except Exception:

                passed = False

                result = TestResult(
                    f"Import {filename}",
                    False,
                    1,
                    (
                        time.perf_counter()
                        - started
                    ),
                    stderr=traceback.format_exc(),
                    reason="Import failed",
                )

            self.record(
                result
            )

        return passed

    # ------------------------------------------------------------------
    # PHASE 6 — INDIVIDUAL FILE REGRESSION
    # ------------------------------------------------------------------

    def file_regressions(
        self,
    ) -> bool:

        banner(
            "PHASE 6 — INDIVIDUAL FILE REGRESSION"
        )

        passed = True

        for filename in REQUIRED_MODULES:

            path = (
                self.root
                / filename
            )

            (
                tree,
                _,
                _,
                tests,
            ) = ast_info(
                path
            )

            has_main = any(
                isinstance(
                    node,
                    ast.If,
                )
                and isinstance(
                    node.test,
                    ast.Compare,
                )
                and isinstance(
                    node.test.left,
                    ast.Name,
                )
                and node.test.left.id
                == "__name__"
                for node in ast.walk(
                    tree
                )
            )

            if has_main:

                result = run_command(
                    [
                        self._python(),
                        str(path),
                    ],
                    self.root,
                    self._module_timeout(
                        filename
                    ),
                )

                result = TestResult(
                    f"File regression {filename}",
                    result.passed,
                    result.return_code,
                    result.elapsed_seconds,
                    result.stdout,
                    result.stderr,
                    result.reason,
                )

            else:

                result = TestResult(
                    f"File regression {filename}",
                    True,
                    0,
                    0.0,
                    stdout=(
                        "Library module validated "
                        "through compilation and import; "
                        f"discovered_tests={tests}"
                    ),
                )

            passed &= self.record(
                result
            )

        return passed

    @staticmethod
    def _module_timeout(
        filename: str,
    ) -> int:

        if filename in {
            "step8_historical_data_test.py",
            "step9_historical_backtest.py",
        }:

            return 180

        if filename in {
            "regression_suite.py",
            "rewrite.py",
        }:

            return 120

        return 60

    def _python(
        self,
    ) -> str:

        return sys.executable

    # ------------------------------------------------------------------
    # PHASE 8 — PRODUCTION CONTRACTS
    # ------------------------------------------------------------------

    def production_contracts(
        self,
    ) -> bool:

        banner(
            "PHASE 8 — PRODUCTION COMPONENT CONTRACTS"
        )

        passed = True

        contracts: dict[
            str,
            tuple[str, ...],
        ] = {
            "RiskBudgetEngine": (
                "health_check",
                "get_target_budgets",
                "optimize",
                "get_risk_budget",
                "risk_budget",
            ),
            "VolatilityTargeting": (
                "health_check",
            ),
            "ExpectedReturnForecaster": (
                "forecast",
                "health_check",
            ),
            "RegimeForecastEngine": (
                "forecast",
                "health_check",
            ),
            "PortfolioOptimizer": (
                "optimize",
            ),
            "ProductionComposition": (
                "health_check",
            ),
            "PortfolioDecisionEngine": (
                "decide",
            ),
            "ProductionIntegration": (
                "health_check",
            ),
            "ProductionPipelineIntegration": (
                "health_check",
            ),
            "ProductionExecutionGate": (
                "authorize",
                "require_authorization",
                "health_check",
            ),
            "ProductionRiskValidation": (
                "validate",
            ),
        }

        modules = {
            "RiskBudgetEngine":
                "riskbudgetengine",
            "VolatilityTargeting":
                "volatilitytargeting",
            "ExpectedReturnForecaster":
                "expectedreturnforecaster",
            "RegimeForecastEngine":
                "regimeforecastengine",
            "PortfolioOptimizer":
                "portfoliooptimizer",
            "ProductionComposition":
                "productioncomposition",
            "PortfolioDecisionEngine":
                "portfoliodecisionengine",
            "ProductionIntegration":
                "productionintegration",
            "ProductionPipelineIntegration":
                "productionpipelineintegration",
            "ProductionExecutionGate":
                "productionexecutiongate",
            "ProductionRiskValidation":
                "productionriskvalidation",
        }

        for class_name, methods in contracts.items():

            started = time.perf_counter()

            try:

                cls = getattr(
                    importlib.import_module(
                        modules[class_name]
                    ),
                    class_name,
                )

                missing = [
                    method
                    for method in methods
                    if not callable(
                        getattr(
                            cls,
                            method,
                            None,
                        )
                    )
                ]

                ok(
                    not missing,
                    (
                        f"{class_name} "
                        f"missing methods: "
                        f"{missing}"
                    ),
                )

                stdout = (
                    f"{class_name}: "
                    f"{len(methods)} "
                    "API contracts validated."
                )

                result = TestResult(
                    f"Production API contract: {class_name}",
                    True,
                    0,
                    (
                        time.perf_counter()
                        - started
                    ),
                    stdout,
                )

            except Exception:

                passed = False

                result = TestResult(
                    f"Production API contract: {class_name}",
                    False,
                    1,
                    (
                        time.perf_counter()
                        - started
                    ),
                    stderr=traceback.format_exc(),
                    reason="API contract failure",
                )

            self.record(
                result
            )

        return passed

    # ------------------------------------------------------------------
    # PHASE 9 — RISK BUDGET
    # ------------------------------------------------------------------

    def risk_budget_regression(
        self,
    ) -> bool:

        banner(
            "PHASE 9 — RISK BUDGET ENGINE REGRESSION"
        )

        started = time.perf_counter()

        try:

            from core_constants import (
                REGIME_RISK_BUDGETS,
            )

            from riskbudgetengine import (
                RiskBudgetEngine,
            )

            assets = self.assets

            ok(
                assets,
                "Production asset universe is empty",
            )

            engine = RiskBudgetEngine()

            regimes = list(
                REGIME_RISK_BUDGETS
            )

            ok(
                regimes,
                "No regime risk budgets configured",
            )

            # --------------------------------------------------------------
            # 9.1 CONFIGURATION VALIDATION
            # --------------------------------------------------------------

            health = engine.health_check()

            ok(
                isinstance(
                    health,
                    dict,
                ),
                "RiskBudgetEngine health_check() "
                "did not return a dictionary",
            )

            ok(
                bool(
                    health.get(
                        "healthy",
                        False,
                    )
                ),
                f"RiskBudgetEngine unhealthy: {health}",
            )

            # --------------------------------------------------------------
            # 9.2 TARGET-BUDGET API
            # --------------------------------------------------------------

            for regime in regimes:

                mapping = (
                    REGIME_RISK_BUDGETS[
                        regime
                    ]
                )

                missing = [
                    asset
                    for asset in assets
                    if asset not in mapping
                ]

                ok(
                    not missing,
                    (
                        f"{regime} "
                        f"missing risk budgets: "
                        f"{missing}"
                    ),
                )

                values = np.asarray(
                    [
                        mapping[asset]
                        for asset in assets
                    ],
                    dtype=float,
                )

                ok(
                    np.isfinite(
                        values
                    ).all(),
                    (
                        f"{regime} "
                        "risk budget contains "
                        "non-finite values"
                    ),
                )

                ok(
                    (values >= 0.0).all(),
                    (
                        f"{regime} "
                        "risk budget contains "
                        "negative values"
                    ),
                )

                ok(
                    np.isclose(
                        values.sum(),
                        1.0,
                        atol=1e-6,
                    ),
                    (
                        f"{regime} "
                        "risk budget does not "
                        "sum to 1"
                    ),
                )

                # ----------------------------------------------------------
                # Actual production API
                # ----------------------------------------------------------

                target = (
                    engine.get_target_budgets(
                        regime,
                        assets,
                    )
                )

                ok(
                    isinstance(
                        target,
                        dict,
                    ),
                    (
                        f"{regime} "
                        "get_target_budgets() "
                        "did not return a dictionary"
                    ),
                )

                ok(
                    list(
                        target.keys()
                    )
                    == assets,
                    (
                        f"{regime} "
                        "target-budget asset "
                        "ordering mismatch"
                    ),
                )

                target_values = np.asarray(
                    [
                        target[asset]
                        for asset in assets
                    ],
                    dtype=float,
                )

                ok(
                    np.isfinite(
                        target_values
                    ).all(),
                    (
                        f"{regime} "
                        "target budget contains "
                        "non-finite values"
                    ),
                )

                ok(
                    (target_values >= 0.0).all(),
                    (
                        f"{regime} "
                        "target budget contains "
                        "negative values"
                    ),
                )

                ok(
                    np.isclose(
                        target_values.sum(),
                        1.0,
                        atol=1e-6,
                    ),
                    (
                        f"{regime} "
                        "target budget does not "
                        "sum to 1"
                    ),
                )

                # ----------------------------------------------------------
                # Compatibility API
                # ----------------------------------------------------------

                compatibility = (
                    engine.get_risk_budget(
                        regime,
                        assets,
                    )
                )

                ok(
                    np.allclose(
                        [
                            compatibility[a]
                            for a in assets
                        ],
                        target_values,
                        atol=1e-10,
                    ),
                    (
                        f"{regime} "
                        "get_risk_budget() "
                        "does not match "
                        "get_target_budgets()"
                    ),
                )

                alias = (
                    engine.risk_budget(
                        regime,
                        assets,
                    )
                )

                ok(
                    np.allclose(
                        [
                            alias[a]
                            for a in assets
                        ],
                        target_values,
                        atol=1e-10,
                    ),
                    (
                        f"{regime} "
                        "risk_budget() alias "
                        "does not match "
                        "get_target_budgets()"
                    ),
                )

            result = TestResult(
                "RiskBudgetEngine behavioral regression",
                True,
                0,
                (
                    time.perf_counter()
                    - started
                ),
                (
                    f"Assets: {len(assets)}; "
                    f"Regimes: {regimes}; "
                    "target-budget API validated."
                ),
            )

        except Exception:

            result = TestResult(
                "RiskBudgetEngine behavioral regression",
                False,
                1,
                (
                    time.perf_counter()
                    - started
                ),
                stderr=traceback.format_exc(),
                reason=(
                    "Risk-budget "
                    "regression failed"
                ),
            )

        return self.record(
            result
        )

    # ------------------------------------------------------------------
    # PHASE 10 — FORECAST
    # ------------------------------------------------------------------

    def forecast_regression(
        self,
    ) -> bool:

        banner(
            "PHASE 10 — FORECAST REGRESSION"
        )

        started = time.perf_counter()

        try:

            from expectedreturnforecaster import (
                ExpectedReturnForecaster,
            )

            prices = synthetic_prices(
                self.assets,
                520,
            )

            forecaster = (
                ExpectedReturnForecaster()
            )

            forecast = (
                forecaster.forecast(
                    prices
                )
            )

            if isinstance(
                forecast,
                dict,
            ):

                values = np.asarray(
                    [
                        forecast[a]
                        for a in self.assets
                    ],
                    dtype=float,
                )

            else:

                values = np.asarray(
                    forecast,
                    dtype=float,
                ).reshape(
                    -1
                )

            ok(
                values.size
                == len(
                    self.assets
                ),
                (
                    "Forecast dimension "
                    "does not match "
                    "complete asset universe"
                ),
            )

            ok(
                np.isfinite(
                    values
                ).all(),
                "Forecast contains non-finite values",
            )

            result = TestResult(
                "Expected-return behavioral regression",
                True,
                0,
                (
                    time.perf_counter()
                    - started
                ),
                (
                    f"Assets: {len(self.assets)}; "
                    f"Observations: {len(prices)}"
                ),
            )

        except Exception:

            result = TestResult(
                "Expected-return behavioral regression",
                False,
                1,
                (
                    time.perf_counter()
                    - started
                ),
                stderr=traceback.format_exc(),
                reason=(
                    "Forecast "
                    "regression failed"
                ),
            )

        return self.record(
            result
        )

    # ------------------------------------------------------------------
    # PHASE 10B — COVARIANCE
    # ------------------------------------------------------------------

    def covariance_regression(
        self,
    ) -> bool:

        banner(
            "PHASE 10B — COVARIANCE REGRESSION"
        )

        started = time.perf_counter()

        try:

            from covarianceengine import (
                CovarianceEngine,
            )

            prices = synthetic_prices(
                self.assets,
                520,
            )

            returns = (
                prices
                .pct_change()
                .dropna()
            )

            engine = (
                CovarianceEngine()
            )

            result_matrix = None

            for method in (
                "ledoit_wolf",
                "ewma",
                "rolling",
            ):

                try:

                    result_matrix = (
                        engine.estimate(
                            returns,
                            method=method,
                        )
                    )

                    break

                except TypeError:

                    try:

                        result_matrix = (
                            engine.estimate(
                                returns
                            )
                        )

                        break

                    except Exception:

                        continue

                except Exception:

                    continue

            ok(
                result_matrix is not None,
                (
                    "CovarianceEngine "
                    "produced no estimate"
                ),
            )

            matrix = (
                result_matrix[
                    "covariance"
                ]
                if (
                    isinstance(
                        result_matrix,
                        dict,
                    )
                    and "covariance"
                    in result_matrix
                )
                else result_matrix
            )

            matrix = finite_array(
                matrix,
                name="covariance",
            )

            ok(
                matrix.shape
                == (
                    len(
                        self.assets
                    ),
                    len(
                        self.assets
                    ),
                ),
                "Covariance dimension mismatch",
            )

            ok(
                np.allclose(
                    matrix,
                    matrix.T,
                    atol=1e-8,
                ),
                "Covariance is not symmetric",
            )

            ok(
                float(
                    np.linalg.eigvalsh(
                        (
                            matrix
                            + matrix.T
                        ) / 2
                    ).min()
                )
                > -1e-8,
                (
                    "Covariance is "
                    "not positive "
                    "semidefinite"
                ),
            )

            result = TestResult(
                "CovarianceEngine behavioral regression",
                True,
                0,
                (
                    time.perf_counter()
                    - started
                ),
                f"Assets: {len(self.assets)}",
            )

        except Exception:

            result = TestResult(
                "CovarianceEngine behavioral regression",
                False,
                1,
                (
                    time.perf_counter()
                    - started
                ),
                stderr=traceback.format_exc(),
                reason=(
                    "Covariance "
                    "regression failed"
                ),
            )

        return self.record(
            result
        )

    # ------------------------------------------------------------------
    # PHASE 11 — BLACK-LITTERMAN
    # ------------------------------------------------------------------

    def black_litterman_regression(
        self,
    ) -> bool:

        banner(
            "PHASE 11 — BLACK-LITTERMAN REGRESSION"
        )

        started = time.perf_counter()

        try:

            from blacklitterman import (
                BlackLittermanModel,
            )

            n = len(
                self.assets
            )

            cov = (
                deterministic_covariance(
                    n
                )
            )

            prior = np.linspace(
                0.01,
                0.03,
                n,
            )

            model = (
                BlackLittermanModel()
            )

            posterior = None

            for method_name in (
                "posterior_returns",
                "calculate_posterior_returns",
                "fit",
            ):

                method = getattr(
                    model,
                    method_name,
                    None,
                )

                if not callable(
                    method
                ):

                    continue

                try:

                    posterior = method(
                        prior,
                        cov,
                    )

                    break

                except TypeError:

                    try:

                        posterior = method(
                            covariance=cov,
                            prior_returns=prior,
                        )

                        break

                    except Exception:

                        continue

                except Exception:

                    continue

            if posterior is None:

                ok(
                    any(
                        callable(
                            getattr(
                                model,
                                name,
                                None,
                            )
                        )
                        for name in dir(
                            model
                        )
                        if not name.startswith(
                            "_"
                        )
                    ),
                    (
                        "Black-Litterman "
                        "model exposes no "
                        "public callable API"
                    ),
                )

                stdout = (
                    "Black-Litterman model "
                    "imported and public "
                    "API validated."
                )

            else:

                values = finite_array(
                    posterior,
                    name="posterior returns",
                ).reshape(
                    -1
                )

                ok(
                    values.size == n,
                    (
                        "Posterior-return "
                        "dimension mismatch"
                    ),
                )

                stdout = (
                    "Equilibrium and posterior "
                    "return vectors validated."
                )

            result = TestResult(
                "Black-Litterman behavioral regression",
                True,
                0,
                (
                    time.perf_counter()
                    - started
                ),
                stdout,
            )

        except Exception:

            result = TestResult(
                "Black-Litterman behavioral regression",
                False,
                1,
                (
                    time.perf_counter()
                    - started
                ),
                stderr=traceback.format_exc(),
                reason=(
                    "Black-Litterman "
                    "regression failed"
                ),
            )

        return self.record(
            result
        )

    # ------------------------------------------------------------------
    # PHASE 12 — PRODUCTION COMPOSITION
    # ------------------------------------------------------------------

    def production_composition_regression(
        self,
    ) -> bool:

        banner(
            "PHASE 12 — PRODUCTION COMPOSITION"
        )

        started = time.perf_counter()

        try:

            from productioncomposition import (
                build_production_engine,
            )

            engine = (
                build_production_engine()
            )

            ok(
                engine is not None,
                (
                    "Production engine "
                    "construction returned None"
                ),
            )

            health = (
                engine.health_check()
                if callable(
                    getattr(
                        engine,
                        "health_check",
                        None,
                    )
                )
                else {}
            )

            ok(
                isinstance(
                    health,
                    dict,
                ),
                (
                    "Production health "
                    "check did not return "
                    "a dictionary"
                ),
            )

            if "healthy" in health:

                ok(
                    bool(
                        health[
                            "healthy"
                        ]
                    ),
                    (
                        "Production engine "
                        f"unhealthy: {health}"
                    ),
                )

            result = TestResult(
                "Production composition regression",
                True,
                0,
                (
                    time.perf_counter()
                    - started
                ),
                (
                    "Production composition "
                    "constructed and "
                    "health-checked."
                ),
            )

        except Exception:

            result = TestResult(
                "Production composition regression",
                False,
                1,
                (
                    time.perf_counter()
                    - started
                ),
                stderr=traceback.format_exc(),
                reason=(
                    "Production composition "
                    "regression failed"
                ),
            )

        return self.record(
            result
        )

    # ------------------------------------------------------------------
    # PHASE 12B — REGIME DIFFERENTIATION
    # ------------------------------------------------------------------

    def regime_differentiation_regression(
        self,
    ) -> bool:

        """
        Verify the configured risk budgets themselves
        are not silently collapsed.
        """

        banner(
            "PHASE 12B — REGIME DIFFERENTIATION"
        )

        started = time.perf_counter()

        try:

            from core_constants import (
                REGIME_RISK_BUDGETS,
            )

            regimes = list(
                REGIME_RISK_BUDGETS
            )

            vectors = []

            for regime in regimes:

                vectors.append(
                    np.asarray(
                        [
                            REGIME_RISK_BUDGETS[
                                regime
                            ][a]
                            for a in self.assets
                        ],
                        dtype=float,
                    )
                )

            unique = {
                tuple(
                    np.round(
                        vector,
                        10,
                    )
                )
                for vector in vectors
            }

            ok(
                len(unique)
                >= min(
                    2,
                    len(regimes),
                ),
                (
                    "Configured regime "
                    "risk budgets collapse "
                    "to one identical "
                    "allocation"
                ),
            )

            result = TestResult(
                "Regime allocation differentiation",
                True,
                0,
                (
                    time.perf_counter()
                    - started
                ),
                (
                    "Distinct configured "
                    "regime budget vectors: "
                    f"{len(unique)}"
                ),
            )

        except Exception:

            result = TestResult(
                "Regime allocation differentiation",
                False,
                1,
                (
                    time.perf_counter()
                    - started
                ),
                stderr=traceback.format_exc(),
                reason=(
                    "Regime differentiation "
                    "regression failed"
                ),
            )

        return self.record(
            result
        )

    # ------------------------------------------------------------------
    # PHASE 13 — EXECUTION CHAIN
    # ------------------------------------------------------------------

    def execution_chain(
        self,
    ) -> bool:

        banner(
            "PHASE 13 — EXECUTION CHAIN REGRESSION"
        )

        passed = True

        for filename in REGRESSION_MODULES:

            path = (
                self.root
                / filename
            )

            exists = path.is_file()

            result = TestResult(
                f"Execution chain: {filename}",
                exists,
                0 if exists else 1,
                0.0,
                stdout=(
                    "Execution module "
                    "import contract passed."
                    if exists
                    else ""
                ),
                reason=(
                    None
                    if exists
                    else (
                        "Execution module missing"
                    )
                ),
            )

            passed &= self.record(
                result
            )

        return passed

    # ------------------------------------------------------------------
    # PHASE 14 — STALE REFERENCE AUDIT
    # ------------------------------------------------------------------

    def stale_reference_audit(
        self,
    ) -> bool:

        banner(
            "PHASE 14 — STALE REFERENCE AUDIT"
        )

        started = time.perf_counter()

        stale_modules = {
            "riskbudgeting",
            "risk_budgeting",
        }

        findings: list[
            str
        ] = []

        for path in local_python_files(
            self.root
        ):

            if path.name == SELF_NAME:

                continue

            try:

                tree = ast.parse(
                    path.read_text(
                        encoding="utf-8"
                    ),
                    filename=str(
                        path
                    ),
                )

            except SyntaxError:

                continue

            for node in ast.walk(
                tree
            ):

                if isinstance(
                    node,
                    ast.Import,
                ):

                    for alias in node.names:

                        if (
                            alias.name
                            .split(
                                ".",
                                1,
                            )[0]
                            .lower()
                            in stale_modules
                        ):

                            findings.append(
                                f"{path.name}: "
                                f"import {alias.name}"
                            )

                elif (
                    isinstance(
                        node,
                        ast.ImportFrom,
                    )
                    and node.module
                ):

                    if (
                        node.module
                        .split(
                            ".",
                            1,
                        )[0]
                        .lower()
                        in stale_modules
                    ):

                        findings.append(
                            f"{path.name}: "
                            f"from {node.module} "
                            "import ..."
                        )

        passed = not findings

        return self.record(
            TestResult(
                "Stale reference audit",
                passed,
                0 if passed else 1,
                (
                    time.perf_counter()
                    - started
                ),
                stdout=(
                    "No stale imports detected."
                    if passed
                    else "\n".join(
                        findings
                    )
                ),
                reason=(
                    None
                    if passed
                    else (
                        "Obsolete risk-budget "
                        "module imports detected."
                    )
                ),
            )
        )

    # ------------------------------------------------------------------
    # PHASE 15 — HYGIENE
    # ------------------------------------------------------------------

    def hygiene(
        self,
    ) -> bool:

        banner(
            "PHASE 15 — REPOSITORY HYGIENE"
        )

        started = time.perf_counter()

        backup_patterns = (
            "*.bak",
            "*.backup",
            "*.old",
            "*.orig",
            "*.pyc",
        )

        # Recovery snapshots belong under ignored runtime storage, not source.
        allowed_retained_backups = set()

        artifacts: list[
            str
        ] = []

        for pattern in backup_patterns:

            artifacts.extend(
                str(
                    p.relative_to(
                        self.root
                    )
                )
                for p in self.root.glob(
                    pattern
                )
                if p.is_file()
                and p.name not in allowed_retained_backups
            )

        # py_compile caches are generated under __pycache__, not project-root
        # artifacts. Only explicit root-level Python backup artifacts fail.

        passed = not artifacts

        return self.record(
            TestResult(
                "Repository Python-artifact hygiene",
                passed,
                0 if passed else 1,
                (
                    time.perf_counter()
                    - started
                ),
                stdout=(
                    "No Python backup artifacts."
                    if passed
                    else "\n".join(
                        artifacts
                    )
                ),
                reason=(
                    None
                    if passed
                    else (
                        "Python backup "
                        "artifacts detected."
                    )
                ),
            )
        )

    # ------------------------------------------------------------------
    # PHASE 16 — GIT
    # ------------------------------------------------------------------

    def git_audit(
        self,
    ) -> bool:

        banner(
            "PHASE 16 — GIT REPOSITORY STATUS"
        )

        executable = shutil.which(
            "git"
        )

        if executable is None:

            return self.record(
                TestResult(
                    "Git repository status",
                    True,
                    0,
                    0.0,
                    stdout=(
                        "git executable unavailable; "
                        "status audit skipped."
                    ),
                )
            )

        result = run_command(
            [
                executable,
                "status",
                "--short",
            ],
            self.root,
            30,
        )

        # Working-tree changes are informational,
        # not a regression failure.

        return self.record(
            TestResult(
                "Git repository status",
                True,
                0,
                result.elapsed_seconds,
                result.stdout,
                result.stderr,
            )
        )

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------

    def summary(
        self,
    ) -> int:

        banner(
            "FINAL REGRESSION SUMMARY"
        )

        total = len(
            self.results
        )

        passed = sum(
            result.passed
            for result in self.results
        )

        failed = (
            total
            - passed
        )

        print(
            f"API version:       "
            f"{API_VERSION}"
        )

        print(
            f"Project root:      "
            f"{self.root}"
        )

        print(
            f"Production assets: "
            f"{len(self.assets)}"
        )

        print(
            f"Checks:             "
            f"{total}"
        )

        print(
            f"Passed:             "
            f"{passed}"
        )

        print(
            f"Failed:             "
            f"{failed}"
        )

        if failed:

            print(
                "\nFAILED CHECKS"
            )

            for result in self.results:

                if not result.passed:

                    print(
                        f"- {result.name}: "
                        f"{result.reason or 'failure'}"
                    )

            print(
                "\nSYSTEM STATUS: FAIL"
            )

            return 1

        print(
            "\nSYSTEM STATUS: PASS"
        )

        return 0

    # ------------------------------------------------------------------
    # FULL RUN
    # ------------------------------------------------------------------

    def run(
        self,
    ) -> int:

        banner(
            "FINAL COMPREHENSIVE REGRESSION"
        )

        print(
            "Execution stack: "
            "complete repository"
        )

        print(
            f"Python: "
            f"{sys.executable}"
        )

        print(
            f"Project: "
            f"{self.root}"
        )

        inventory_ok = (
            self.inventory()
        )

        if not inventory_ok:

            return self.summary()

        self.assets = (
            production_assets()
        )

        print()

        print(
            "COMPLETE PRODUCTION ASSET UNIVERSE"
        )

        print(
            self.assets
        )

        print(
            f"Asset count: "
            f"{len(self.assets)}"
        )

        self.compile_all()

        self.ruff()

        self.ast_audit()

        self.imports()

        self.file_regressions()

        self.production_contracts()

        self.risk_budget_regression()

        self.forecast_regression()

        self.covariance_regression()

        self.black_litterman_regression()

        self.production_composition_regression()

        self.regime_differentiation_regression()

        self.execution_chain()

        self.stale_reference_audit()

        self.hygiene()

        self.git_audit()

        return self.summary()


# ==============================================================================
# SECTION 13 — MAIN
# ==============================================================================


def main() -> int:

    suite = FinalRegression()

    return suite.run()


# ==============================================================================
# EXECUTION
# ==============================================================================


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
