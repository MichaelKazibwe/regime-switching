"""
======================================================================
regression_suite.py

Full System Regression Test
======================================================================

Institutional portfolio/trading system regression harness.

Purpose
-------

This module is the top-level regression gate for the execution stack.

It verifies:

    1. Python compilation
    2. Ruff static analysis
    3. Individual module regression tests
    4. Module execution order
    5. Process exit codes
    6. System-wide regression integrity
    7. Final regression summary

Execution architecture
-----------------------

    order.py
        |
        v
    orderstatus.py
        |
        v
    orderbook.py
        |
        v
    transactioncostmodel.py
        |
        v
    executionengine.py
        |
        v
    rebalanceengine.py
        |
        v
    tradegenerator.py
        |
        v
    pretraderiskgate.py
        |
        v
    oms.py
        |
        v
    brokerrouter.py
        |
        v
    paperbroker.py
        |
        v
    brokerexecutionengine.py
        |
        v
    livebroker.py
        |
        v
    reconciliationengine.py
        |
        v
    posttradeexecutionmonitor.py
        |
        v
    executionanalytics.py

The regression suite intentionally executes each module in a
subprocess so that:

    - failures cannot be hidden by shared interpreter state
    - module-level test blocks are actually exercised
    - exit codes are independently verified
    - stdout/stderr can be captured
    - the master suite behaves like a CI regression gate

Author: Michael Kazibwe
Version: 1.0.0
======================================================================
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ======================================================================
# CONSTANTS
# ======================================================================


API_VERSION = "1.0.0"

PROJECT_ROOT = Path(
    __file__
).resolve().parent


# ======================================================================
# MODULE EXECUTION ORDER
# ======================================================================


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
)


# ======================================================================
# REQUIRED MODULES
# ======================================================================


REQUIRED_MODULES = (
    "analytics.py",
    "assetuniverse.py",
    "factorexposuremodel.py",
    "forecastmodels.py",
    "forwardriskanalyzer.py",
    "forwardriskmetrics.py",
    "macroregime.py",
    "regimecovariance.py",
    "regimesimulation.py",
    "blacklitterman.py",
    "constraints.py",
    "core_constants.py",
    "covarianceengine.py",
    "ensemblecovariance.py",
    "expectedreturnforecaster.py",
    "factorcovariance.py",
    "portfoliooptimizer.py",
    "riskmodel.py",
    "scenarioengine.py",
    "transactioncostmodel.py",
    "validators.py",
    "portfolio.py",
    "portfolioaccount.py",
    "order.py",
    "orderstatus.py",
    "orderbook.py",
    "trade.py",
    "tradegenerator.py",
    "oms.py",
    "brokerrouter.py",
    "paperbroker.py",
    "brokerexecutionengine.py",
    "livebroker.py",
    "reconciliationengine.py",
    "posttradeexecutionmonitor.py",
    "executionanalytics.py",
)


# ======================================================================
# TEST RESULT
# ======================================================================


@dataclass(frozen=True)
class TestResult:
    """
    Immutable result for one regression operation.
    """

    name: str

    passed: bool

    return_code: int

    elapsed_seconds: float

    stdout: str

    stderr: str

    command: tuple[str, ...]

    reason: Optional[str] = None


# ======================================================================
# REGRESSION SUITE
# ======================================================================


class FullSystemRegression:
    """
    Master regression suite for the trading system.
    """

    # ==================================================================
    # CONSTRUCTOR
    # ==================================================================

    def __init__(
        self,
        project_root: Optional[
            Path
        ] = None,
        python_executable: Optional[
            str
        ] = None,
    ):
        """
        Initialize the regression suite.
        """

        self.project_root = (
            Path(project_root).resolve()
            if project_root is not None
            else PROJECT_ROOT
        )

        self.python_executable = (
            python_executable
            or sys.executable
        )

        self.results: list[
            TestResult
        ] = []

        self.started_at: Optional[
            float
        ] = None

        self.finished_at: Optional[
            float
        ] = None

    # ==================================================================
    # DISPLAY
    # ==================================================================

    @staticmethod
    def _banner(
        text: str,
    ) -> None:
        """
        Print a section banner.
        """

        print()
        print(
            "=" * 78
        )
        print(
            text
        )
        print(
            "=" * 78
        )

    # ==================================================================
    # DISPLAY RESULT
    # ==================================================================

    @staticmethod
    def _display_result(
        result: TestResult,
    ) -> None:
        """
        Print one test result.
        """

        if result.passed:
            marker = "PASS"
        else:
            marker = "FAIL"

        print(
            f"[{marker}] "
            f"{result.name} "
            f"({result.elapsed_seconds:.3f}s)"
        )

        if not result.passed:

            if result.reason:
                print(
                    f"Reason: {result.reason}"
                )

            if result.stdout.strip():
                print()
                print(
                    "--- STDOUT ---"
                )
                print(
                    result.stdout.rstrip()
                )

            if result.stderr.strip():
                print()
                print(
                    "--- STDERR ---"
                )
                print(
                    result.stderr.rstrip()
                )

    # ==================================================================
    # RECORD RESULT
    # ==================================================================

    def _record(
        self,
        result: TestResult,
    ) -> TestResult:
        """
        Store and display a test result.
        """

        self.results.append(
            result
        )

        self._display_result(
            result
        )

        return result

    # ==================================================================
    # RUN COMMAND
    # ==================================================================

    def _run_command(
        self,
        name: str,
        command: list[str],
        timeout: int = 120,
    ) -> TestResult:
        """
        Execute one subprocess regression check.
        """

        start = time.perf_counter()

        try:
            completed = (
                subprocess.run(
                    command,
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            )

            elapsed = (
                time.perf_counter()
                - start
            )

            passed = (
                completed.returncode
                == 0
            )

            reason = None

            if not passed:
                reason = (
                    "Command returned "
                    f"exit code "
                    f"{completed.returncode}."
                )

            return self._record(
                TestResult(
                    name=name,
                    passed=passed,
                    return_code=(
                        completed.returncode
                    ),
                    elapsed_seconds=elapsed,
                    stdout=(
                        completed.stdout
                        or ""
                    ),
                    stderr=(
                        completed.stderr
                        or ""
                    ),
                    command=tuple(
                        command
                    ),
                    reason=reason,
                )
            )

        except subprocess.TimeoutExpired as exc:

            elapsed = (
                time.perf_counter()
                - start
            )

            stdout = (
                exc.stdout
                if isinstance(
                    exc.stdout,
                    str,
                )
                else ""
            )

            stderr = (
                exc.stderr
                if isinstance(
                    exc.stderr,
                    str,
                )
                else ""
            )

            return self._record(
                TestResult(
                    name=name,
                    passed=False,
                    return_code=-1,
                    elapsed_seconds=elapsed,
                    stdout=stdout,
                    stderr=stderr,
                    command=tuple(
                        command
                    ),
                    reason=(
                        f"Command timed out "
                        f"after {timeout}s."
                    ),
                )
            )

        except OSError as exc:

            elapsed = (
                time.perf_counter()
                - start
            )

            return self._record(
                TestResult(
                    name=name,
                    passed=False,
                    return_code=-1,
                    elapsed_seconds=elapsed,
                    stdout="",
                    stderr="",
                    command=tuple(
                        command
                    ),
                    reason=str(
                        exc
                    ),
                )
            )

    # ==================================================================
    # PROJECT ROOT CHECK
    # ==================================================================

    def check_project_root(
        self,
    ) -> bool:
        """
        Verify that the regression suite is running from a valid
        project directory.
        """

        self._banner(
            "PHASE 0 — PROJECT ROOT"
        )

        exists = (
            self.project_root.exists()
            and self.project_root.is_dir()
        )

        result = TestResult(
            name="Project root",
            passed=exists,
            return_code=(
                0
                if exists
                else 1
            ),
            elapsed_seconds=0.0,
            stdout=str(
                self.project_root
            ),
            stderr="",
            command=(),
            reason=(
                None
                if exists
                else (
                    "Project root does not exist."
                )
            ),
        )

        self._record(
            result
        )

        return exists

    # ==================================================================
    # PYTHON VERSION
    # ==================================================================

    def check_python_version(
        self,
    ) -> bool:
        """
        Verify Python is available.
        """

        self._banner(
            "PHASE 1 — PYTHON RUNTIME"
        )

        command = [
            self.python_executable,
            "--version",
        ]

        result = self._run_command(
            "Python runtime",
            command,
            timeout=30,
        )

        return result.passed

    # ==================================================================
    # REQUIRED FILES
    # ==================================================================

    def check_required_files(
        self,
    ) -> bool:
        """
        Verify that all required modules exist.
        """

        self._banner(
            "PHASE 2 — REQUIRED MODULE FILES"
        )

        missing = []

        for filename in REQUIRED_MODULES:

            path = (
                self.project_root
                / filename
            )

            if not path.is_file():
                missing.append(
                    filename
                )

        passed = (
            len(missing)
            == 0
        )

        stdout = (
            "All required module files exist."
            if passed
            else (
                "Missing files:\n"
                + "\n".join(
                    missing
                )
            )
        )

        result = TestResult(
            name="Required module files",
            passed=passed,
            return_code=(
                0
                if passed
                else 1
            ),
            elapsed_seconds=0.0,
            stdout=stdout,
            stderr="",
            command=(),
            reason=(
                None
                if passed
                else (
                    "One or more required "
                    "modules are missing."
                )
            ),
        )

        self._record(
            result
        )

        return passed

    # ==================================================================
    # COMPILE ALL
    # ==================================================================

    def compile_all(
        self,
    ) -> bool:
        """
        Compile every Python module in the project.
        """

        self._banner(
            "PHASE 3 — PYTHON COMPILATION"
        )

        command = [
            self.python_executable,
            "-m",
            "py_compile",
            *[
                filename
                for filename in sorted(
                    path.name
                    for path in self.project_root.glob(
                        "*.py"
                    )
                )
            ],
        ]

        result = self._run_command(
            "py_compile *.py",
            command,
            timeout=120,
        )

        return result.passed

    # ==================================================================
    # RUFF CHECK
    # ==================================================================

    def ruff_check(
        self,
    ) -> bool:
        """
        Run Ruff across the complete project.

        If Ruff is unavailable, this is a hard failure because the
        project regression gate explicitly requires Ruff.
        """

        self._banner(
            "PHASE 4 — RUFF STATIC ANALYSIS"
        )

        ruff_path = shutil.which(
            "ruff"
        )

        if ruff_path is None:

            result = TestResult(
                name="ruff check .",
                passed=False,
                return_code=-1,
                elapsed_seconds=0.0,
                stdout="",
                stderr="",
                command=(
                    "ruff",
                    "check",
                    ".",
                ),
                reason=(
                    "ruff executable was not found "
                    "on PATH."
                ),
            )

            self._record(
                result
            )

            return False

        command = [
            ruff_path,
            "check",
            ".",
        ]

        result = self._run_command(
            "ruff check .",
            command,
            timeout=120,
        )

        return result.passed

    # ==================================================================
    # IMPORT SMOKE TEST
    # ==================================================================

    def import_smoke_test(
        self,
    ) -> bool:
        """
        Verify that every required module can be imported.

        This catches import-time failures that may not be exposed by
        individual module execution.
        """

        self._banner(
            "PHASE 5 — IMPORT SMOKE TEST"
        )

        failures = []

        start = time.perf_counter()

        for filename in REQUIRED_MODULES:

            module_name = filename[
                :-3
            ]

            try:
                importlib.import_module(
                    module_name
                )

            except Exception as exc:
                failures.append(
                    f"{module_name}: "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

        elapsed = (
            time.perf_counter()
            - start
        )

        passed = (
            len(failures)
            == 0
        )

        stdout = (
            "All required modules imported successfully."
            if passed
            else (
                "\n".join(
                    failures
                )
            )
        )

        result = TestResult(
            name="Import smoke test",
            passed=passed,
            return_code=(
                0
                if passed
                else 1
            ),
            elapsed_seconds=elapsed,
            stdout=stdout,
            stderr="",
            command=(
                "python",
                "import-smoke-test",
            ),
            reason=(
                None
                if passed
                else (
                    "One or more modules "
                    "failed to import."
                )
            ),
        )

        self._record(
            result
        )

        return passed

    # ==================================================================
    # INDIVIDUAL MODULE TESTS
    # ==================================================================

    def run_module_tests(
        self,
    ) -> bool:
        """
        Execute all module-level regression tests in dependency order.
        """

        self._banner(
            "PHASE 6 — MODULE REGRESSION TESTS"
        )

        all_passed = True

        for index, filename in enumerate(
            REGRESSION_MODULES,
            start=1,
        ):

            print()
            print(
                f"--- Module "
                f"{index}/"
                f"{len(REGRESSION_MODULES)}: "
                f"{filename} ---"
            )

            command = [
                self.python_executable,
                filename,
            ]

            result = self._run_command(
                f"Module test: {filename}",
                command,
                timeout=120,
            )

            if not result.passed:
                all_passed = False

                # Fail fast.
                #
                # The objective is to identify the first broken
                # component in dependency order rather than producing
                # a large cascade of secondary failures.
                print()
                print(
                    "REGRESSION STOPPED."
                )
                print(
                    f"First failing module: "
                    f"{filename}"
                )

                break

        return all_passed

    # ==================================================================
    # REGRESSION MODULE EXISTENCE
    # ==================================================================

    def check_regression_modules(
        self,
    ) -> bool:
        """
        Verify that every module expected to have an executable
        regression test exists.
        """

        self._banner(
            "PHASE 7 — REGRESSION MODULE INVENTORY"
        )

        missing = []

        for filename in (
            REGRESSION_MODULES
        ):

            path = (
                self.project_root
                / filename
            )

            if not path.is_file():
                missing.append(
                    filename
                )

        passed = (
            len(missing)
            == 0
        )

        stdout = (
            "All regression modules exist."
            if passed
            else (
                "Missing regression modules:\n"
                + "\n".join(
                    missing
                )
            )
        )

        result = TestResult(
            name="Regression module inventory",
            passed=passed,
            return_code=(
                0
                if passed
                else 1
            ),
            elapsed_seconds=0.0,
            stdout=stdout,
            stderr="",
            command=(),
            reason=(
                None
                if passed
                else (
                    "Regression module inventory "
                    "is incomplete."
                )
            ),
        )

        self._record(
            result
        )

        return passed

    # ==================================================================
    # EXECUTION CHAIN CHECK
    # ==================================================================

    def execution_chain_check(
        self,
    ) -> bool:
        """
        Verify that the expected execution-stack module sequence exists.

        This is intentionally an architectural check rather than a
        behavioral trading test.
        """

        self._banner(
            "PHASE 8 — EXECUTION CHAIN INTEGRITY"
        )

        expected_chain = (
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
        )

        actual_chain = tuple(
            filename
            for filename in REGRESSION_MODULES
        )

        passed = (
            actual_chain
            == expected_chain
        )

        stdout = (
            "Execution chain verified:\n"
            + " -> ".join(
                filename[:-3]
                for filename in actual_chain
            )
        )

        result = TestResult(
            name="Execution chain integrity",
            passed=passed,
            return_code=(
                0
                if passed
                else 1
            ),
            elapsed_seconds=0.0,
            stdout=stdout,
            stderr="",
            command=(),
            reason=(
                None
                if passed
                else (
                    "Execution module order differs "
                    "from the registered architecture."
                )
            ),
        )

        self._record(
            result
        )

        return passed

    # ==================================================================
    # GIT STATUS
    # ==================================================================

    def git_status_check(
        self,
    ) -> bool:
        """
        Report repository status when the project is a Git repository.

        This is informational rather than a failure gate.
        """

        self._banner(
            "PHASE 9 — REPOSITORY STATUS"
        )

        git_path = shutil.which(
            "git"
        )

        if git_path is None:

            result = TestResult(
                name="Git status",
                passed=True,
                return_code=0,
                elapsed_seconds=0.0,
                stdout=(
                    "Git executable not available; "
                    "status check skipped."
                ),
                stderr="",
                command=(),
            )

            self._record(
                result
            )

            return True

        command = [
            git_path,
            "status",
            "--short",
        ]

        result = self._run_command(
            "Git status",
            command,
            timeout=30,
        )

        if result.passed:

            if result.stdout.strip():
                print()
                print(
                    "Working tree changes:"
                )
                print(
                    result.stdout.rstrip()
                )

            else:
                print(
                    "Working tree clean."
                )

        return True

    # ==================================================================
    # FINAL SUMMARY
    # ==================================================================

    def summary(
        self,
    ) -> dict:
        """
        Return the complete regression summary.
        """

        passed = sum(
            result.passed
            for result in self.results
        )

        failed = sum(
            not result.passed
            for result in self.results
        )

        elapsed = 0.0

        if self.started_at is not None:

            end = (
                self.finished_at
                if self.finished_at is not None
                else time.perf_counter()
            )

            elapsed = (
                end
                - self.started_at
            )

        return {
            "api_version":
                API_VERSION,

            "project_root":
                str(
                    self.project_root
                ),

            "total_checks":
                len(
                    self.results
                ),

            "passed_checks":
                passed,

            "failed_checks":
                failed,

            "elapsed_seconds":
                elapsed,

            "system_status":
                (
                    "PASS"
                    if failed == 0
                    else "FAIL"
                ),
        }

    # ==================================================================
    # PRINT SUMMARY
    # ==================================================================

    def print_summary(
        self,
    ) -> None:
        """
        Print final regression summary.
        """

        summary = self.summary()

        self._banner(
            "FULL SYSTEM REGRESSION SUMMARY"
        )

        print(
            f"API version:       "
            f"{summary['api_version']}"
        )

        print(
            f"Project root:      "
            f"{summary['project_root']}"
        )

        print(
            f"Total checks:      "
            f"{summary['total_checks']}"
        )

        print(
            f"Passed checks:     "
            f"{summary['passed_checks']}"
        )

        print(
            f"Failed checks:     "
            f"{summary['failed_checks']}"
        )

        print(
            f"Elapsed seconds:   "
            f"{summary['elapsed_seconds']:.3f}"
        )

        print()

        print(
            "SYSTEM STATUS:     "
            f"{summary['system_status']}"
        )

        print()

        if summary[
            "system_status"
        ] == "PASS":

            print(
                "=" * 78
            )

            print(
                "FULL SYSTEM REGRESSION PASSED"
            )

            print(
                "=" * 78
            )

        else:

            print(
                "=" * 78
            )

            print(
                "FULL SYSTEM REGRESSION FAILED"
            )

            print(
                "=" * 78
            )

            print()

            print(
                "Failed checks:"
            )

            for result in self.results:

                if not result.passed:

                    print(
                        f"  - {result.name}"
                    )

    # ==================================================================
    # RUN FULL SUITE
    # ==================================================================

    def run(
        self,
    ) -> bool:
        """
        Execute the complete regression suite.
        """

        self.started_at = (
            time.perf_counter()
        )

        self._banner(
            "FULL SYSTEM REGRESSION SUITE"
        )

        print(
            "Execution stack regression gate"
        )

        print(
            f"Python: "
            f"{self.python_executable}"
        )

        print(
            f"Project: "
            f"{self.project_root}"
        )

        # --------------------------------------------------------------
        # PHASE 0
        # --------------------------------------------------------------

        if not self.check_project_root():
            self.finished_at = (
                time.perf_counter()
            )

            self.print_summary()

            return False

        # --------------------------------------------------------------
        # PHASE 1
        # --------------------------------------------------------------

        if not self.check_python_version():

            self.finished_at = (
                time.perf_counter()
            )

            self.print_summary()

            return False

        # --------------------------------------------------------------
        # PHASE 2
        # --------------------------------------------------------------

        if not self.check_required_files():

            self.finished_at = (
                time.perf_counter()
            )

            self.print_summary()

            return False

        # --------------------------------------------------------------
        # PHASE 3
        # --------------------------------------------------------------

        if not self.compile_all():

            self.finished_at = (
                time.perf_counter()
            )

            self.print_summary()

            return False

        # --------------------------------------------------------------
        # PHASE 4
        # --------------------------------------------------------------

        if not self.ruff_check():

            self.finished_at = (
                time.perf_counter()
            )

            self.print_summary()

            return False

        # --------------------------------------------------------------
        # PHASE 5
        # --------------------------------------------------------------

        if not self.import_smoke_test():

            self.finished_at = (
                time.perf_counter()
            )

            self.print_summary()

            return False

        # --------------------------------------------------------------
        # PHASE 6
        # --------------------------------------------------------------

        if not self.check_regression_modules():

            self.finished_at = (
                time.perf_counter()
            )

            self.print_summary()

            return False

        # --------------------------------------------------------------
        # PHASE 7
        # --------------------------------------------------------------

        if not self.execution_chain_check():

            self.finished_at = (
                time.perf_counter()
            )

            self.print_summary()

            return False

        # --------------------------------------------------------------
        # PHASE 8
        # --------------------------------------------------------------

        if not self.run_module_tests():

            self.finished_at = (
                time.perf_counter()
            )

            self.print_summary()

            return False

        # --------------------------------------------------------------
        # PHASE 9
        # --------------------------------------------------------------

        self.git_status_check()

        # --------------------------------------------------------------
        # FINISH
        # --------------------------------------------------------------

        self.finished_at = (
            time.perf_counter()
        )

        self.print_summary()

        return (
            self.summary()[
                "system_status"
            ]
            == "PASS"
        )


# ======================================================================
# REGRESSION SUITE TEST
# ======================================================================


def test_regression_suite_structure() -> None:
    """
    Validate the regression suite's own architecture.
    """

    suite = FullSystemRegression()

    assert (
        suite.API_VERSION
        if hasattr(
            suite,
            "API_VERSION",
        )
        else API_VERSION
    ) == API_VERSION

    assert (
        len(
            REGRESSION_MODULES
        )
        >= 1
    )

    assert (
        "order.py"
        in REGRESSION_MODULES
    )

    assert (
        "brokerexecutionengine.py"
        in REGRESSION_MODULES
    )

    assert (
        "livebroker.py"
        in REGRESSION_MODULES
    )

    assert (
        "reconciliationengine.py"
        in REGRESSION_MODULES
    )

    assert (
        "posttradeexecutionmonitor.py"
        in REGRESSION_MODULES
    )

    assert (
        "executionanalytics.py"
        in REGRESSION_MODULES
    )

    assert (
        REGRESSION_MODULES.index(
            "order.py"
        )
        <
        REGRESSION_MODULES.index(
            "orderbook.py"
        )
    )

    assert (
        REGRESSION_MODULES.index(
            "orderbook.py"
        )
        <
        REGRESSION_MODULES.index(
            "executionengine.py"
        )
    )

    assert (
        REGRESSION_MODULES.index(
            "executionengine.py"
        )
        <
        REGRESSION_MODULES.index(
            "oms.py"
        )
    )

    assert (
        REGRESSION_MODULES.index(
            "oms.py"
        )
        <
        REGRESSION_MODULES.index(
            "brokerrouter.py"
        )
    )

    assert (
        REGRESSION_MODULES.index(
            "brokerrouter.py"
        )
        <
        REGRESSION_MODULES.index(
            "brokerexecutionengine.py"
        )
    )

    assert (
        REGRESSION_MODULES.index(
            "brokerexecutionengine.py"
        )
        <
        REGRESSION_MODULES.index(
            "livebroker.py"
        )
    )

    assert (
        REGRESSION_MODULES.index(
            "livebroker.py"
        )
        <
        REGRESSION_MODULES.index(
            "reconciliationengine.py"
        )
    )

    assert (
        REGRESSION_MODULES.index(
            "reconciliationengine.py"
        )
        <
        REGRESSION_MODULES.index(
            "posttradeexecutionmonitor.py"
        )
    )

    assert (
        REGRESSION_MODULES.index(
            "posttradeexecutionmonitor.py"
        )
        <
        REGRESSION_MODULES.index(
            "executionanalytics.py"
        )
    )

    assert (
        suite.project_root.exists()
    )

    print(
        "RegressionSuite structure tests passed."
    )


# ======================================================================
# MAIN
# ======================================================================


def main() -> int:
    """
    Main process entry point.
    """

    suite = FullSystemRegression()

    success = suite.run()

    return (
        0
        if success
        else 1
    )


# ======================================================================
# MODULE ENTRY POINT
# ======================================================================


if __name__ == "__main__":

    test_regression_suite_structure()

    raise SystemExit(
        main()
    )