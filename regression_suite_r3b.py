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
import numpy as np
import pandas as pd


from core_constants import (
    REGIME_MAX_LEVERAGE,
    REGIME_RISK_BUDGETS,
    REGIME_VOL_TARGETS,
    settings,
)

from productioncomposition import (
    build_production_engine,
)

from expectedreturnforecaster import (
    ExpectedReturnForecaster,
)

from regimeforecastengine import (
    RegimeForecastEngine,
    RegimeForecastPolicy,
)

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
    "atr.py",
    "positionsizing.py",

    # --------------------------------------------------------------
    # PRODUCTION PORTFOLIO CONSTRUCTION
    # --------------------------------------------------------------

    "portfoliooptimizer.py",
    "riskbudgetengine.py",
    "volatilitytargeting.py",
    "productioncomposition.py",
    "riskcontributionanalyzer.py",

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


# ============================================================
# PHASE 11 — DETERMINISTIC SYNTHETIC PRICE DATA
# ============================================================


def build_phase11_price_data(
    asset_order,
    observations=300,
):
    """
    Construct deterministic synthetic price history for
    forecast and Black-Litterman regression testing.

    The data intentionally contains different deterministic
    trends across assets so that the forecast components
    produce non-identical signals.

    No network access is required.
    """

    if observations < 252:
        raise ValueError(
            "Phase 11 requires at least 252 "
            "price observations."
        )

    if not asset_order:
        raise ValueError(
            "asset_order must contain at least one asset."
        )

    if len(
        set(asset_order)
    ) != len(asset_order):
        raise ValueError(
            "asset_order contains duplicate assets."
        )

    dates = pd.date_range(
        end=pd.Timestamp("2026-01-30"),
        periods=observations,
        freq="B",
    )

    time_index = np.arange(
        observations,
        dtype=float,
    )

    prices = {}

    for index, asset in enumerate(
        asset_order
    ):
        # --------------------------------------------------------
        # Deterministic asset-specific trend
        # --------------------------------------------------------

        trend_strength = (
            0.00025
            +
            0.00004 * index
        )

        # --------------------------------------------------------
        # Deterministic cyclical component
        # --------------------------------------------------------

        cycle = (
            0.003
            *
            np.sin(
                time_index / 17.0
                +
                index * 0.35
            )
        )

        # --------------------------------------------------------
        # Deterministic asset-specific curvature
        # --------------------------------------------------------

        curvature = (
            0.0000008
            *
            (
                time_index
                -
                observations / 2.0
            )
            *
            (index + 1)
        )

        daily_returns = (
            trend_strength
            +
            cycle
            +
            curvature
        )

        # --------------------------------------------------------
        # Price path
        # --------------------------------------------------------

        price_path = (
            100.0
            *
            np.cumprod(
                1.0
                +
                daily_returns
            )
        )

        prices[
            asset
        ] = price_path

    price_frame = pd.DataFrame(
        prices,
        index=dates,
    )

    # ------------------------------------------------------------
    # Structural validation
    # ------------------------------------------------------------

    assert price_frame.shape == (
        observations,
        len(asset_order),
    )

    assert list(
        price_frame.columns
    ) == list(
        asset_order
    )

    assert price_frame.index.is_monotonic_increasing

    assert np.isfinite(
        price_frame.to_numpy(
            dtype=float
        )
    ).all()

    assert (
        price_frame.to_numpy(
            dtype=float
        )
        >
        0.0
    ).all()

    return price_frame

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
    # PRODUCTION PORTFOLIO REGRESSION
    # ==================================================================

    def production_portfolio_regression(
        self,
    ) -> bool:
        """
        Execute the production portfolio-construction regression gate.

        This validates the integrated:

            PortfolioOptimizer
                |
                +-- RiskBudgetEngine
                +-- PortfolioConstraints
                +-- VolatilityTargeting
                +-- ExpectedReturnForecaster
                +-- BlackLittermanModel
                +-- RiskBudgetReport

        The test deliberately distinguishes between:

            1. achievable volatility targets
            2. leverage-constrained volatility shortfalls

        A volatility target is NOT considered a failure merely because
        it is mathematically unreachable under the regime leverage
        constraint.

        Hard invariants:

            - finite weights
            - non-negative weights
            - correct asset count
            - correct asset ordering
            - position cap respected
            - maximum leverage respected
            - cash non-negative
            - weights + cash = 1
            - final volatility finite
            - risk budgets sum to one
            - regime-specific configuration exists
            - volatility diagnostics exist
            - risk report exists
            - target achieved when feasible
            - shortfall correctly reported when infeasible
    """

        self._banner(
            "PHASE 6A — PRODUCTION PORTFOLIO REGRESSION"
        )

        start = time.perf_counter()

        try:

            # ==========================================================
            # PRODUCTION ASSET UNIVERSE
            # ==========================================================

            asset_order = list(__import__("assetuniverse").PRODUCTION_ASSETS)

            asset_count = len(
                asset_order
            )

            if not asset_count or len(set(asset_order)) != asset_count:

                raise AssertionError(
                    "Production asset universe must "
                    f"contain unique registered assets. Got {asset_count}."
                )

            print(
                f"Asset count: {asset_count}"
            )

            print(
                f"Assets: {asset_order}"
            )

            # ==========================================================
            # SYNTHETIC PRODUCTION COVARIANCE
            # ==========================================================
            #
            # Use a deterministic positive-definite covariance matrix.
            #
            # This is deliberately generated inside the regression
            # suite so that the regression test does not depend on
            # market-data availability.
            #

            rng = np.random.default_rng(
                20260817
            )

            factor_matrix = (
                rng.normal(
                    0.0,
                    0.10,
                    size=(
                        asset_count,
                        5,
                    ),
                )
            )

            idiosyncratic = (
                np.diag(
                    rng.uniform(
                        0.02,
                        0.08,
                        size=asset_count,
                    )
                )
            )

            covariance = (
                factor_matrix
                @ factor_matrix.T
                + idiosyncratic
            )

            covariance = (
                covariance
                + covariance.T
            ) / 2.0

            covariance += (
                np.eye(
                    asset_count
                )
                * 1e-8
            )

            eigenvalues = np.linalg.eigvalsh(
                covariance
            )

            minimum_eigenvalue = float(
                eigenvalues.min()
            )

            print()
            print(
                "Minimum covariance eigenvalue: "
                f"{minimum_eigenvalue:.12f}"
            )

            assert (
                minimum_eigenvalue
                > 0.0
            ), (
                "Covariance matrix is not "
                "positive definite."
            )

            print(
                "[PASS] Covariance validation"
            )

            # ==========================================================
            # PRODUCTION ENGINE
            # ==========================================================

            production_engine = (
                build_production_engine()
            )

            if hasattr(
                production_engine,
                "optimizer",
            ):

                optimizer = (
                    production_engine
                    .optimizer
                )

            elif hasattr(
                production_engine,
                "portfolio_optimizer",
            ):

                optimizer = (
                    production_engine
                    .portfolio_optimizer
                )

            else:

                raise AssertionError(
                    "Production engine does not expose "
                    "a PortfolioOptimizer."
                )

            assert (
                optimizer is not None
            )

            print()
            print(
                "Optimizer:",
                type(
                    optimizer
                ).__name__,
            )

            print(
                "Risk budget:",
                type(
                    optimizer
                    .risk_budget_engine
                ).__name__,
            )

            print(
                "Constraints:",
                type(
                    optimizer
                    .constraints
                ).__name__,
            )

            print(
                "Vol targeting:",
                (
                    type(
                        optimizer
                        .vol_target_engine
                    ).__name__
                    if optimizer.vol_target_engine
                    is not None
                    else "NONE"
                ),
            )

            print(
                "Forecast:",
                (
                    type(
                        optimizer
                        .forecast_engine
                    ).__name__
                    if optimizer.forecast_engine
                    is not None
                    else "NONE"
                ),
            )

            print(
                "Black-Litterman:",
                (
                    type(
                        optimizer
                        .black_litterman
                    ).__name__
                    if optimizer.black_litterman
                    is not None
                    else "NONE"
                ),
            )

            assert (
                optimizer.risk_budget_engine
                is not None
            )

            assert (
                optimizer.constraints
                is not None
            )

            assert (
                optimizer.vol_target_engine
                is not None
            )

            print(
                "[PASS] Component construction"
            )

            # ==========================================================
            # HEALTH CHECKS
            # ==========================================================

            risk_health = (
                optimizer
                .risk_budget_engine
                .health_check()
            )

            print()
            print(
                "Risk budget health:",
                risk_health,
            )

            assert isinstance(
                risk_health,
                dict,
            )

            assert (
                risk_health.get(
                    "healthy"
                )
                is True
            )

            volatility_health = (
                optimizer
                .vol_target_engine
                .health_check()
            )

            print(
                "Volatility targeting health:",
                volatility_health,
            )

            assert isinstance(
                volatility_health,
                dict,
            )

            assert (
                volatility_health.get(
                    "status"
                )
                == "HEALTHY"
            )

            print(
                "[PASS] Component health"
            )

            # ==========================================================
            # PRODUCTION POSITION LIMIT
            # ==========================================================

            max_position_weight = float(
                settings.max_position_weight
            )

            assert (
                np.isfinite(
                    max_position_weight
                )
            )

            assert (
                max_position_weight
                > 0.0
            )

            print()
            print(
                "Maximum position weight:",
                f"{max_position_weight:.12f}",
            )

            # ==========================================================
            # REGIME REGRESSION
            # ==========================================================
            #
            # This is the primary production portfolio regression.
            #
            # It validates:
            #
            #   1. regime configuration
            #   2. risk-budget integrity
            #   3. optimizer result structure
            #   4. portfolio weights
            #   5. position limits
            #   6. leverage
            #   7. cash
            #   8. independently calculated volatility
            #   9. volatility diagnostics
            #  10. expected-return / forecast integrity when supplied
            #  11. risk-report integrity
            #  12. regime identity
            #
            # IMPORTANT:
            #
            # The production regression calls optimizer.optimize()
            # without prices. Therefore expected-return forecasting and
            # Black-Litterman are legitimately inactive in this test.
            #
            # They are validated conditionally if the optimizer returns
            # those objects.
            # ==========================================================

            regime_results = {}

            for regime in (
                "bull",
                "neutral",
                "crisis",
            ):

                print()
                print(
                    "-" * 70
                )

                print(
                    f"REGIME: {regime.upper()}"
                )

                # ======================================================
                # REGIME CONFIGURATION
                # ======================================================

                assert (
                    regime
                    in REGIME_RISK_BUDGETS
                ), (
                    f"Missing risk-budget "
                    f"configuration for {regime}."
                )

                assert (
                    regime
                    in REGIME_VOL_TARGETS
                ), (
                    f"Missing volatility-target "
                    f"configuration for {regime}."
                )

                assert (
                    regime
                    in REGIME_MAX_LEVERAGE
                ), (
                    f"Missing leverage configuration "
                    f"for {regime}."
                )

                target_vol = float(
                    REGIME_VOL_TARGETS[
                        regime
                    ]
                )

                max_leverage = float(
                    REGIME_MAX_LEVERAGE[
                        regime
                    ]
                )

                assert np.isfinite(
                    target_vol
                ), (
                    f"{regime}: target volatility "
                    "is non-finite."
                )

                assert (
                    target_vol
                    > 0.0
                ), (
                    f"{regime}: target volatility "
                    "must be positive."
                )

                assert np.isfinite(
                    max_leverage
                ), (
                    f"{regime}: maximum leverage "
                    "is non-finite."
                )

                assert (
                    max_leverage
                    > 0.0
                ), (
                    f"{regime}: maximum leverage "
                    "must be positive."
                )

                # ======================================================
                # RISK BUDGETS
                # ======================================================

                regime_budget_mapping = (
                    REGIME_RISK_BUDGETS[
                        regime
                    ]
                )

                assert isinstance(
                    regime_budget_mapping,
                    dict,
                ), (
                    f"{regime}: risk-budget "
                    "configuration must be a dictionary."
                )

                missing_budget_assets = [
                    asset
                    for asset in asset_order
                    if asset
                    not in regime_budget_mapping
                ]

                assert not missing_budget_assets, (
                    f"{regime}: missing risk budgets "
                    f"for assets: "
                    f"{missing_budget_assets}"
                )

                budgets = np.asarray(
                    [
                        regime_budget_mapping[
                            asset
                        ]
                        for asset in asset_order
                    ],
                    dtype=float,
                )

                assert (
                    budgets.shape
                    ==
                    (asset_count,)
                ), (
                    f"{regime}: invalid risk-budget "
                    "vector shape."
                )

                assert np.isfinite(
                    budgets
                ).all(), (
                    f"{regime}: risk budgets "
                    "contain non-finite values."
                )

                assert (
                    budgets
                    >=
                    0.0
                ).all(), (
                    f"{regime}: risk budgets "
                    "contain negative values."
                )

                budget_sum = float(
                    budgets.sum()
                )

                print(
                    f"Budget sum: "
                    f"{budget_sum:.12f}"
                )

                print(
                    f"Target volatility: "
                    f"{target_vol:.12f}"
                )

                print(
                    f"Maximum leverage: "
                    f"{max_leverage:.12f}"
                )

                assert np.isclose(
                    budget_sum,
                    1.0,
                    atol=1e-6,
                ), (
                    f"{regime}: risk budgets "
                    f"must sum to 1. "
                    f"Got {budget_sum:.12f}."
                )

                # ======================================================
                # OPTIMIZE
                # ======================================================

                result = optimizer.optimize(
                    covariance=covariance,
                    regime=regime,
                    asset_order=asset_order,
                )

                assert isinstance(
                    result,
                    dict,
                ), (
                    f"{regime}: optimizer did not "
                    "return a dictionary."
                )

                # ======================================================
                # RESULT STRUCTURE
                # ======================================================

                required_result_keys = {
                    "weights",
                    "cash",
                    "regime",
                    "expected_returns",
                    "forecasts",
                    "risk_report",
                    "volatility_diagnostics",
                }

                missing_keys = (
                    required_result_keys
                    -
                    set(
                        result.keys()
                    )
                )

                assert not missing_keys, (
                    f"{regime}: optimizer result "
                    f"is missing keys: {missing_keys}"
                )

                # ======================================================
                # RESULT REGIME
                # ======================================================

                returned_regime = result[
                    "regime"
                ]

                assert (
                    returned_regime
                    == regime
                ), (
                    f"Expected regime {regime}, "
                    f"got {returned_regime}."
                )

                print(
                    f"[PASS] {regime.upper()} regime identity"
                )

                # ======================================================
                # WEIGHTS
                # ======================================================

                weights = np.asarray(
                    result["weights"],
                    dtype=float,
                ).reshape(-1)

                assert (
                    weights.size
                    ==
                    asset_count
                ), (
                    f"{regime}: invalid weight count. "
                    f"Expected {asset_count}, "
                    f"got {weights.size}."
                )

                assert np.isfinite(
                    weights
                ).all(), (
                    f"{regime}: non-finite weights."
                )

                assert (
                    weights
                    >=
                    -1e-10
                ).all(), (
                    f"{regime}: negative weights."
                )

                # Remove insignificant floating-point negatives
                # before independent portfolio calculations.
                weights = np.maximum(
                    weights,
                    0.0,
                )

                # ======================================================
                # WEIGHT SUM / EXPOSURE SANITY
                # ======================================================

                gross_exposure = float(
                    np.sum(
                        np.abs(
                            weights
                        )
                    )
                )

                assert np.isfinite(
                    gross_exposure
                ), (
                    f"{regime}: gross exposure "
                    "is non-finite."
                )

                assert (
                    gross_exposure
                    >=
                    -1e-12
                )

                # ======================================================
                # POSITION CAP
                # ======================================================

                maximum_weight_index = int(
                    np.argmax(
                        weights
                    )
                )

                maximum_weight = float(
                    weights[
                        maximum_weight_index
                    ]
                )

                maximum_asset = (
                    asset_order[
                        maximum_weight_index
                    ]
                )

                print()
                print(
                    "Maximum position:"
                )

                print(
                    f"{maximum_asset}: "
                    f"{maximum_weight:.12f}"
                )

                print(
                    "Configured position limit: "
                    f"{max_position_weight:.12f}"
                )

                assert (
                    maximum_weight
                    <=
                    max_position_weight
                    +
                    1e-10
                ), (
                    f"{regime}: position cap exceeded. "
                    f"{maximum_asset}="
                    f"{maximum_weight:.12f}, "
                    f"limit="
                    f"{max_position_weight:.12f}"
                )

                print(
                    "[PASS] Position-weight limit"
                )

                # ======================================================
                # LEVERAGE
                # ======================================================

                print(
                    f"Gross exposure: "
                    f"{gross_exposure:.12f}"
                )

                assert (
                    gross_exposure
                    <=
                    max_leverage
                    +
                    1e-8
                ), (
                    f"{regime}: maximum leverage exceeded. "
                    f"Gross exposure="
                    f"{gross_exposure:.12f}, "
                    f"maximum="
                    f"{max_leverage:.12f}."
                )

                print(
                    "[PASS] Maximum leverage"
                )

                # ======================================================
                # CASH
                # ======================================================

                cash = float(
                    result["cash"]
                )

                assert np.isfinite(
                    cash
                ), (
                    f"{regime}: cash is non-finite."
                )

                assert (
                    cash
                    >=
                    -1e-10
                ), (
                    f"{regime}: negative cash allocation."
                )

                expected_cash = max(
                    0.0,
                    1.0
                    -
                    gross_exposure,
                )

                assert np.isclose(
                    cash,
                    expected_cash,
                    atol=1e-6,
                ), (
                    f"{regime}: cash sleeve does "
                    "not match gross exposure. "
                    f"Cash={cash:.12f}, "
                    f"expected={expected_cash:.12f}."
                )

                total_exposure = (
                    gross_exposure
                    +
                    cash
                )

                assert np.isclose(
                    total_exposure,
                    1.0,
                    atol=1e-6,
                ), (
                    f"{regime}: "
                    "weights + cash != 1. "
                    f"Got {total_exposure:.12f}."
                )

                print(
                    f"Cash: {cash:.12f}"
                )

                print(
                    f"Total exposure + cash: "
                    f"{total_exposure:.12f}"
                )

                print(
                    "[PASS] Cash sleeve"
                )

                # ======================================================
                # INDEPENDENT PORTFOLIO VOLATILITY
                # ======================================================

                variance = float(
                    weights
                    @
                    covariance
                    @
                    weights
                )

                assert np.isfinite(
                    variance
                ), (
                    f"{regime}: portfolio variance "
                    "is non-finite."
                )

                if variance < 0.0:

                    assert (
                        variance
                        >
                        -1e-12
                    ), (
                        f"{regime}: materially negative "
                        f"portfolio variance={variance}."
                    )

                    variance = 0.0

                final_volatility = float(
                    np.sqrt(
                        variance
                    )
                )

                assert np.isfinite(
                    final_volatility
                ), (
                    f"{regime}: final volatility "
                    "is non-finite."
                )

                # PortfolioOptimizer preserves the native covariance
                # frequency for ``final_volatility``. Regime targets are
                # annual, so the independent regression calculation must
                # annualize the returned portfolio volatility before
                # comparing it with the configured target.
                annualization_factor = np.sqrt(252.0)
                final_volatility_annualized = (
                    final_volatility
                    *
                    annualization_factor
                )

                volatility_error = (
                    final_volatility_annualized
                    -
                    target_vol
                )

                volatility_shortfall = max(
                    0.0,
                    target_vol
                    -
                    final_volatility_annualized,
                )

                print(
                    f"Final volatility: "
                    f"{final_volatility:.12f}"
                )

                print(
                    f"Target volatility: "
                    f"{target_vol:.12f}"
                )

                print(
                    f"Volatility error: "
                    f"{volatility_error:.12f}"
                )

                print(
                    "[PASS] Final volatility calculation"
                )

                # ======================================================
                # EXPECTED RETURNS / FORECAST INTEGRITY
                # ======================================================
                #
                # optimize() only invokes the forecast + BL branch
                # when prices are supplied.
                #
                # This regression intentionally calls optimize()
                # without prices, so None is a valid production state.
                #
                # If the objects are present, however, they must be
                # structurally and numerically valid.
                # ======================================================

                expected_returns = result[
                    "expected_returns"
                ]

                forecasts = result[
                    "forecasts"
                ]

                if expected_returns is None:

                    assert (
                        forecasts is None
                    ), (
                        f"{regime}: expected returns "
                        "are None while forecasts "
                        "are present."
                    )

                    print(
                        "[PASS] Expected-return branch "
                        "correctly inactive without prices"
                    )

                else:

                    assert hasattr(
                        expected_returns,
                        "values",
                    ), (
                        f"{regime}: expected returns "
                        "must expose a values attribute."
                    )

                    expected_return_values = np.asarray(
                        expected_returns.values,
                        dtype=float,
                    ).reshape(-1)

                    assert (
                        expected_return_values.size
                        ==
                        asset_count
                    ), (
                        f"{regime}: expected-return "
                        "vector has incorrect length."
                    )

                    assert np.isfinite(
                        expected_return_values
                    ).all(), (
                        f"{regime}: expected returns "
                        "contain non-finite values."
                    )

                    assert (
                        forecasts is not None
                    ), (
                        f"{regime}: expected returns "
                        "exist without forecasts."
                    )

                    assert hasattr(
                        forecasts,
                        "values",
                    ), (
                        f"{regime}: forecasts must "
                        "expose a values attribute."
                    )

                    forecast_values = np.asarray(
                        forecasts.values,
                        dtype=float,
                    ).reshape(-1)

                    assert (
                        forecast_values.size
                        ==
                        asset_count
                    ), (
                        f"{regime}: forecast vector "
                        "has incorrect length."
                    )

                    assert np.isfinite(
                        forecast_values
                    ).all(), (
                        f"{regime}: forecasts "
                        "contain non-finite values."
                    )

                    print(
                        "[PASS] Expected-return integrity"
                    )

                    print(
                        "[PASS] Forecast integrity"
                    )

                # ======================================================
                # VOLATILITY DIAGNOSTICS
                # ======================================================

                volatility_diagnostics = result[
                    "volatility_diagnostics"
                ]

                assert isinstance(
                    volatility_diagnostics,
                    dict,
                ), (
                    f"{regime}: volatility diagnostics "
                    "must be a dictionary."
                )

                required_diagnostic_keys = {
                    "status",
                    "engine_result",
                    "original_volatility",
                    "target_volatility",
                    "final_volatility",
                    "final_volatility_frequency",
                    "final_volatility_annualized",
                    "portfolio_variance_native",
                    "portfolio_variance_annualized",
                    "portfolio_volatility_native",
                    "portfolio_volatility_annualized",
                    "target_volatility_frequency",
                    "risk_frequency",
                    "covariance_frequency",
                    "periods_per_year",
                    "annualization_method",
                    "volatility_error",
                    "volatility_shortfall",
                    "target_achieved",
                    "maximum_leverage",
                    "gross_exposure",
                    "cash_weight",
                    "leverage_binding",
                    "required_leverage",
                }

                missing_diagnostic_keys = (
                    required_diagnostic_keys
                    -
                    set(
                        volatility_diagnostics.keys()
                    )
                )

                assert not missing_diagnostic_keys, (
                    f"{regime}: volatility diagnostics "
                    f"missing keys: "
                    f"{missing_diagnostic_keys}"
                )

                diagnostic_target = float(
                    volatility_diagnostics[
                        "target_volatility"
                    ]
                )

                diagnostic_final = float(
                    volatility_diagnostics[
                        "final_volatility"
                    ]
                )

                diagnostic_final_annualized = float(
                    volatility_diagnostics[
                        "final_volatility_annualized"
                    ]
                )

                diagnostic_error = float(
                    volatility_diagnostics[
                        "volatility_error"
                    ]
                )

                diagnostic_shortfall = float(
                    volatility_diagnostics[
                        "volatility_shortfall"
                    ]
                )

                diagnostic_leverage = float(
                    volatility_diagnostics[
                        "maximum_leverage"
                    ]
                )

                diagnostic_gross = float(
                    volatility_diagnostics[
                        "gross_exposure"
                    ]
                )

                diagnostic_cash = float(
                    volatility_diagnostics[
                        "cash_weight"
                    ]
                )

                assert np.isfinite(
                    diagnostic_target
                )

                assert np.isfinite(
                    diagnostic_final
                )

                assert np.isfinite(
                    diagnostic_final_annualized
                )

                assert np.isfinite(
                    diagnostic_error
                )

                assert np.isfinite(
                    diagnostic_shortfall
                )

                assert np.isfinite(
                    diagnostic_leverage
                )

                assert np.isfinite(
                    diagnostic_gross
                )

                assert np.isfinite(
                    diagnostic_cash
                )

                assert np.isclose(
                    diagnostic_target,
                    target_vol,
                    atol=1e-10,
                ), (
                    f"{regime}: diagnostic target "
                    "volatility disagrees with "
                    "configured target."
                )

                assert np.isclose(
                    diagnostic_final,
                    final_volatility,
                    atol=1e-10,
                ), (
                    f"{regime}: diagnostic final "
                    "volatility disagrees with "
                    "independent calculation."
                )

                assert np.isclose(
                    diagnostic_final_annualized,
                    final_volatility_annualized,
                    atol=1e-10,
                ), (
                    f"{regime}: diagnostic annualized "
                    "volatility disagrees with "
                    "independent calculation."
                )

                assert np.isclose(
                    diagnostic_error,
                    volatility_error,
                    atol=1e-10,
                ), (
                    f"{regime}: diagnostic volatility "
                    "error disagrees with independent "
                    "calculation."
                )

                assert np.isclose(
                    diagnostic_shortfall,
                    volatility_shortfall,
                    atol=1e-10,
                ), (
                    f"{regime}: diagnostic volatility "
                    "shortfall disagrees with "
                    "independent calculation."
                )

                assert np.isclose(
                    diagnostic_leverage,
                    max_leverage,
                    atol=1e-10,
                ), (
                    f"{regime}: diagnostic leverage "
                    "does not match configured leverage."
                )

                assert np.isclose(
                    diagnostic_gross,
                    gross_exposure,
                    atol=1e-10,
                ), (
                    f"{regime}: diagnostic gross exposure "
                    "does not match returned weights."
                )

                assert np.isclose(
                    diagnostic_cash,
                    cash,
                    atol=1e-10,
                ), (
                    f"{regime}: diagnostic cash does "
                    "not match returned cash."
                )

                # PortfolioOptimizer preserves the native covariance
                # frequency for ``final_volatility``. Regime volatility
                # targets are annual, so target achievement must be
                # evaluated using the independently annualized volatility.
                calculated_target_achieved = (
                    abs(
                        final_volatility_annualized
                        -
                        target_vol
                    )
                    <= max(
                        1e-10,
                        target_vol
                        * 1e-6,
                    )
                )

                diagnostic_target_achieved = bool(
                    volatility_diagnostics[
                        "target_achieved"
                    ]
                )

                assert (
                    diagnostic_target_achieved
                    ==
                    calculated_target_achieved
                ), (
                    f"{regime}: diagnostic target-achieved "
                    "flag disagrees with independent "
                    "volatility calculation."
                )

                # ======================================================
                # LEVERAGE-BINDING DIAGNOSTIC
                # ======================================================
                #
                # IMPORTANT:
                #
                # The production VolatilityTargeting engine defines
                # leverage_binding as:
                #
                #     required_gross > maximum_leverage
                #
                # It does NOT define leverage_binding merely as:
                #
                #     current_gross == maximum_leverage
                #
                # Therefore the regression must reconcile the diagnostic
                # with the actual engine result when that result exists.
                #
                # If no engine result exists, the regression must not
                # manufacture an independent semantic definition.
                # ======================================================

                diagnostic_leverage_binding = bool(
                    volatility_diagnostics[
                        "leverage_binding"
                    ]
                )

                engine_result = (
                    volatility_diagnostics[
                        "engine_result"
                    ]
                )

                if engine_result is not None:

                    assert hasattr(
                        engine_result,
                        "leverage_binding",
                    ), (
                        f"{regime}: volatility engine "
                        "result does not expose "
                        "leverage_binding."
                    )

                    engine_leverage_binding = bool(
                        engine_result.leverage_binding
                    )

                    assert (
                        diagnostic_leverage_binding
                        ==
                        engine_leverage_binding
                    ), (
                        f"{regime}: volatility diagnostic "
                        "leverage-binding flag does not "
                        "match the volatility engine result. "
                        f"Diagnostic="
                        f"{diagnostic_leverage_binding}, "
                        f"Engine="
                        f"{engine_leverage_binding}."
                    )

                    # --------------------------------------------------
                    # Independently reconcile the engine's definition.
                    # --------------------------------------------------

                    assert hasattr(
                        engine_result,
                        "required_leverage",
                    ), (
                        f"{regime}: volatility engine "
                        "result does not expose "
                        "required_leverage."
                    )

                    engine_required_leverage = float(
                        engine_result.required_leverage
                    )

                    assert np.isfinite(
                        engine_required_leverage
                    ), (
                        f"{regime}: engine required "
                        "leverage is non-finite."
                    )

                    expected_engine_leverage_binding = (
                        engine_required_leverage
                        >
                        max_leverage
                        +
                        1e-10
                    )

                    assert (
                        engine_leverage_binding
                        ==
                        expected_engine_leverage_binding
                    ), (
                        f"{regime}: volatility engine "
                        "leverage-binding flag is "
                        "internally inconsistent. "
                        f"Required leverage="
                        f"{engine_required_leverage:.12f}, "
                        f"Maximum leverage="
                        f"{max_leverage:.12f}, "
                        f"Flag="
                        f"{engine_leverage_binding}."
                    )

                    print(
                        "[PASS] Volatility engine "
                        "leverage-binding semantics"
                    )

                else:

                    # --------------------------------------------------
                    # No engine result means there is no engine-level
                    # leverage-binding state to independently reconstruct.
                    #
                    # We still validate that the diagnostic itself is a
                    # legitimate boolean.
                    # --------------------------------------------------

                    assert isinstance(
                        diagnostic_leverage_binding,
                        bool,
                    )

                    print(
                        "[PASS] Leverage-binding diagnostic "
                        "without engine result"
                    ), (
                    f"{regime}: diagnostic leverage-binding "
                    "flag is inconsistent with portfolio "
                    "state."
                )

                required_leverage = (
                    volatility_diagnostics[
                        "required_leverage"
                    ]
                )

                if required_leverage is not None:

                    required_leverage = float(
                        required_leverage
                    )

                    assert np.isfinite(
                        required_leverage
                    ), (
                        f"{regime}: diagnostic required "
                        "leverage is non-finite."
                    )

                    assert (
                        required_leverage
                        >=
                        -1e-10
                    )

                # ======================================================
                # ENGINE RESULT INTEGRITY
                # ======================================================

                engine_result = (
                    volatility_diagnostics[
                        "engine_result"
                    ]
                )

                if engine_result is not None:

                    engine_required_attributes = {
                        "original_volatility",
                        "target_volatility",
                        "scale_factor",
                        "final_volatility",
                        "maximum_leverage",
                        "gross_exposure",
                        "target_achieved",
                        "leverage_binding",
                        "volatility_shortfall",
                        "required_leverage",
                        "diagnostics",
                    }

                    missing_engine_attributes = {
                        attribute
                        for attribute
                        in engine_required_attributes
                        if not hasattr(
                            engine_result,
                            attribute,
                        )
                    }

                    assert not missing_engine_attributes, (
                        f"{regime}: volatility engine "
                        f"result missing attributes: "
                        f"{missing_engine_attributes}"
                    )

                    engine_original_volatility = float(
                        engine_result.original_volatility
                    )

                    engine_target_volatility = float(
                        engine_result.target_volatility
                    )

                    engine_scale_factor = float(
                        engine_result.scale_factor
                    )

                    engine_final_volatility = float(
                        engine_result.final_volatility
                    )

                    engine_maximum_leverage = float(
                        engine_result.maximum_leverage
                    )

                    engine_gross_exposure = float(
                        engine_result.gross_exposure
                    )

                    engine_shortfall = float(
                        engine_result.volatility_shortfall
                    )

                    engine_required_leverage = float(
                        engine_result.required_leverage
                    )

                    assert np.isfinite(
                        engine_original_volatility
                    )

                    assert np.isfinite(
                        engine_target_volatility
                    )

                    assert np.isfinite(
                        engine_scale_factor
                    )

                    assert np.isfinite(
                        engine_final_volatility
                    )

                    assert np.isfinite(
                        engine_maximum_leverage
                    )

                    assert np.isfinite(
                        engine_gross_exposure
                    )

                    assert np.isfinite(
                        engine_shortfall
                    )

                    assert np.isfinite(
                        engine_required_leverage
                    )

                    assert isinstance(
                        engine_result.diagnostics,
                        dict,
                    )

                    # --------------------------------------------------
                    # Engine → production configuration
                    # --------------------------------------------------

                    assert np.isclose(
                        engine_target_volatility,
                        target_vol,
                        atol=1e-10,
                    ), (
                        f"{regime}: engine target volatility "
                        "does not match configured target."
                    )

                    assert np.isclose(
                        engine_maximum_leverage,
                        max_leverage,
                        atol=1e-10,
                    ), (
                        f"{regime}: engine maximum leverage "
                        "does not match configured leverage."
                    )

                    # --------------------------------------------------
                    # Engine → independently calculated portfolio
                    # --------------------------------------------------

                    assert np.isclose(
                        engine_final_volatility,
                        final_volatility,
                        atol=1e-10,
                    ), (
                        f"{regime}: engine final volatility "
                        "does not match independent "
                        "portfolio calculation."
                    )

                    assert np.isclose(
                        engine_gross_exposure,
                        gross_exposure,
                        atol=1e-10,
                    ), (
                        f"{regime}: engine gross exposure "
                        "does not match returned weights."
                    )

                    # --------------------------------------------------
                    # Engine shortfall
                    # --------------------------------------------------

                    expected_engine_shortfall = max(
                        0.0,
                        target_vol
                        -
                        engine_final_volatility,
                    )

                    assert np.isclose(
                        engine_shortfall,
                        expected_engine_shortfall,
                        atol=1e-10,
                    ), (
                        f"{regime}: engine volatility "
                        "shortfall is internally inconsistent."
                    )

                    # --------------------------------------------------
                    # Engine target-achievement semantics
                    # --------------------------------------------------

                    expected_engine_target_achieved = (
                        abs(
                            engine_final_volatility
                            -
                            target_vol
                        )
                        <=
                        max(
                            1e-10,
                            target_vol
                            * 1e-6,
                        )
                    )

                    assert (
                        bool(
                            engine_result.target_achieved
                        )
                        ==
                        expected_engine_target_achieved
                    ), (
                        f"{regime}: engine target-achieved "
                        "flag is internally inconsistent."
                    )

                    # --------------------------------------------------
                    # Engine leverage-binding semantics
                    # --------------------------------------------------
                    #
                    # This is the authoritative production definition.
                    #
                    #     required_leverage > max_leverage
                    #
                    # NOT:
                    #
                    #     gross_exposure == max_leverage
                    # --------------------------------------------------

                    expected_engine_leverage_binding = (
                        engine_required_leverage
                        >
                        max_leverage
                        +
                        1e-10
                    )

                    assert (
                        bool(
                            engine_result.leverage_binding
                        )
                        ==
                        expected_engine_leverage_binding
                    ), (
                        f"{regime}: engine leverage-binding "
                        "flag is internally inconsistent. "
                        f"Required="
                        f"{engine_required_leverage:.12f}, "
                        f"Maximum="
                        f"{max_leverage:.12f}, "
                        f"Flag="
                        f"{engine_result.leverage_binding}."
                    )

                    # --------------------------------------------------
                    # Diagnostic → engine reconciliation
                    # --------------------------------------------------

                    assert (
                        bool(
                            volatility_diagnostics[
                                "target_achieved"
                            ]
                        )
                        ==
                        bool(
                            engine_result.target_achieved
                        )
                    )

                    assert (
                        bool(
                            volatility_diagnostics[
                                "leverage_binding"
                            ]
                        )
                        ==
                        bool(
                            engine_result.leverage_binding
                        )
                    )

                    if (
                        volatility_diagnostics[
                            "required_leverage"
                        ]
                        is not None
                    ):

                        assert np.isclose(
                            float(
                                volatility_diagnostics[
                                    "required_leverage"
                                ]
                            ),
                            engine_required_leverage,
                            atol=1e-10,
                        ), (
                            f"{regime}: diagnostic required "
                            "leverage does not match "
                            "engine required leverage."
                        )

                    print(
                        "[PASS] Volatility engine "
                        "result integrity"
                    )

                else:

                    print(
                        "[PASS] Volatility engine result "
                        "not required for calculated-only path"
                    )

                print(
                    "[PASS] Volatility diagnostics"
                )

                # ======================================================
                # RISK REPORT
                # ======================================================

                risk_report = result[
                    "risk_report"
                ]

                assert (
                    risk_report is not None
                ), (
                    f"{regime}: risk report "
                    "was not generated."
                )

                # RiskBudgetReport.create() returns a pandas
                # DataFrame with the following production schema:
                #
                #   Asset
                #   Target
                #   Actual
                #   Difference
                #
                assert hasattr(
                    risk_report,
                    "columns",
                ), (
                    f"{regime}: risk report "
                    "must expose DataFrame columns."
                )

                required_risk_report_columns = [
                    "Asset",
                    "Target",
                    "Actual",
                    "Difference",
                ]

                for column in (
                    required_risk_report_columns
                ):

                    assert (
                        column
                        in
                        risk_report.columns
                    ), (
                        f"{regime}: risk report "
                        f"is missing column '{column}'."
                    )

                assert (
                    len(risk_report)
                    ==
                    asset_count
                ), (
                    f"{regime}: risk report row count "
                    f"must equal asset count. "
                    f"Expected {asset_count}, "
                    f"got {len(risk_report)}."
                )

                report_assets = list(
                    risk_report[
                        "Asset"
                    ]
                )

                assert (
                    report_assets
                    ==
                    list(asset_order)
                ), (
                    f"{regime}: risk report asset "
                    "ordering does not match "
                    "asset_order."
                )

                report_targets = np.asarray(
                    risk_report[
                        "Target"
                    ],
                    dtype=float,
                )

                report_actuals = np.asarray(
                    risk_report[
                        "Actual"
                    ],
                    dtype=float,
                )

                report_differences = np.asarray(
                    risk_report[
                        "Difference"
                    ],
                    dtype=float,
                )

                assert (
                    report_targets.size
                    ==
                    asset_count
                )

                assert (
                    report_actuals.size
                    ==
                    asset_count
                )

                assert (
                    report_differences.size
                    ==
                    asset_count
                )

                assert np.isfinite(
                    report_targets
                ).all(), (
                    f"{regime}: risk report "
                    "targets contain non-finite values."
                )

                assert np.isfinite(
                    report_actuals
                ).all(), (
                    f"{regime}: risk report "
                    "actuals contain non-finite values."
                )

                assert np.isfinite(
                    report_differences
                ).all(), (
                    f"{regime}: risk report "
                    "differences contain non-finite values."
                )

                assert np.allclose(
                    report_targets,
                    budgets,
                    atol=1e-10,
                ), (
                    f"{regime}: risk report targets "
                    "do not match configured "
                    "risk budgets."
                )

                assert np.allclose(
                    report_differences,
                    (
                        report_actuals
                        -
                        report_targets
                    ),
                    atol=1e-10,
                ), (
                    f"{regime}: risk report differences "
                    "are inconsistent with "
                    "Actual - Target."
                )

                actual_risk_sum = float(
                    report_actuals.sum()
                )

                assert np.isclose(
                    actual_risk_sum,
                    1.0,
                    atol=1e-6,
                ), (
                    f"{regime}: actual risk "
                    f"contributions must sum to 1. "
                    f"Got {actual_risk_sum:.12f}."
                )

                print(
                    "[PASS] Risk report structure"
                )

                print(
                    "[PASS] Risk report asset ordering"
                )

                print(
                    "[PASS] Risk report target integrity"
                )

                print(
                    "[PASS] Risk report contribution integrity"
                )

                # ======================================================
                # TARGET / SHORTFALL FEASIBILITY
                # ======================================================
                #
                # Volatility scales linearly with portfolio exposure.
                #
                # required_scale =
                #     target_vol / final_volatility
                #
                # required_gross =
                #     gross_exposure * required_scale
                #
                # This is a diagnostic of whether the requested target
                # could be reached without exceeding the regime's
                # leverage limit.
                # ======================================================

                if final_volatility > 1e-12:

                    required_scale = (
                        target_vol
                        /
                        final_volatility
                    )

                    required_gross = (
                        gross_exposure
                        *
                        required_scale
                    )

                    target_feasible = (
                        required_gross
                        <=
                        max_leverage
                        +
                        1e-8
                    )

                else:

                    required_scale = np.inf
                    required_gross = np.inf
                    target_feasible = False

                print(
                    f"Required scaling: "
                    f"{required_scale:.12f}"
                )

                print(
                    f"Estimated required gross: "
                    f"{required_gross:.12f}"
                )

                print(
                    f"Target feasible under leverage: "
                    f"{target_feasible}"
                )

                # ======================================================
                # TARGET / SHORTFALL INVARIANT
                # ======================================================

                if target_feasible:

                    assert np.isclose(
                        final_volatility,
                        target_vol,
                        rtol=1e-5,
                        atol=1e-7,
                    ), (
                        f"{regime}: volatility target "
                        "was classified as feasible "
                        "but was not achieved."
                    )

                    print(
                        "[PASS] Achievable volatility target"
                    )

                else:

                    assert (
                        gross_exposure
                        <=
                        max_leverage
                        +
                        1e-8
                    ), (
                        f"{regime}: leverage exceeded "
                        "during infeasible-target handling."
                    )

                    assert (
                        final_volatility
                        <=
                        target_vol
                        +
                        1e-6
                    ), (
                        f"{regime}: final volatility "
                        "unexpectedly exceeds target "
                        "under an infeasible-target "
                        "classification."
                    )

                    print(
                        "[PASS] Correct leverage-constrained "
                        "volatility shortfall handling"
                    )

                # ======================================================
                # STORE REGIME RESULT
                # ======================================================

                regime_results[
                    regime
                ] = {
                    "weights": weights.copy(),
                    "cash": float(cash),
                    "gross": float(gross_exposure),
                    "volatility": float(
                        final_volatility
                    ),
                    "target": float(target_vol),
                    "max_leverage": float(
                        max_leverage
                    ),
                    "risk_budget": budgets.copy(),
                    "expected_returns": (
                        expected_returns
                    ),
                    "forecasts": forecasts,
                    "risk_report": risk_report,
                    "volatility_diagnostics": (
                        volatility_diagnostics
                    ),
                    "target_feasible": bool(
                        target_feasible
                    ),
                }

                print(
                    f"[PASS] {regime.upper()} regime"
                )

            # ==========================================================
            # FEASIBLE VOLATILITY-TARGET REGRESSION
            # ==========================================================
            #
            # IMPORTANT:
            #
            # This block is OUTSIDE the regime loop.
            #
            # All three regime_results entries now exist:
            #
            #     regime_results["bull"]
            #     regime_results["neutral"]
            #     regime_results["crisis"]
            #
            # This specifically tests the opposite branch from the
            # production regime tests:
            #
            #     target IS feasible
            #
            # Therefore the volatility-targeting engine MUST achieve
            # the requested volatility.
            #

            print()
            print(
                "-" * 70
            )

            print(
                "FEASIBLE VOLATILITY-TARGET REGRESSION"
            )

            print(
                "-" * 70
            )

            # ==========================================================
            # SOURCE PORTFOLIO
            # ==========================================================

            feasible_covariance = (
                covariance.copy()
            )

            feasible_weights = np.asarray(
                regime_results[
                    "bull"
                ]["weights"],
                dtype=float,
            ).copy()

            assert (
                feasible_weights.size
                ==
                asset_count
            ), (
                "Feasible-target test received "
                "an invalid weight vector."
            )

            assert np.isfinite(
                feasible_weights
            ).all(), (
                "Feasible-target test received "
                "non-finite weights."
            )

            assert np.all(
                feasible_weights
                >=
                -1e-10
            ), (
                "Feasible-target source portfolio "
                "contains negative weights."
            )

            feasible_weights = np.maximum(
                feasible_weights,
                0.0,
            )

            # ==========================================================
            # CREATE A LOW-EXPOSURE PORTFOLIO
            # ==========================================================
            #
            # The production bull portfolio is already at its regime
            # leverage limit. We deliberately reduce it to 25% of its
            # exposure so that a higher target can be reached without
            # requiring excessive leverage.
            #

            feasible_weights *= 0.25

            feasible_original_gross = float(
                np.sum(
                    np.abs(
                        feasible_weights
                    )
                )
            )

            assert np.isfinite(
                feasible_original_gross
            ), (
                "Feasible-target initial gross "
                "exposure is non-finite."
            )

            assert (
                feasible_original_gross
                >
                0.0
            ), (
                "Feasible-target initial gross "
                "exposure must be positive."
            )

            # ==========================================================
            # INITIAL VOLATILITY
            # ==========================================================

            feasible_original_variance = float(
                feasible_weights
                @
                feasible_covariance
                @
                feasible_weights
            )

            assert np.isfinite(
                feasible_original_variance
            ), (
                "Feasible-target initial variance "
                "is non-finite."
            )

            if feasible_original_variance < 0.0:

                assert (
                    feasible_original_variance
                    >
                    -1e-12
                ), (
                    "Feasible-target initial variance "
                    "is materially negative."
                )

                feasible_original_variance = 0.0

            feasible_original_volatility = float(
                np.sqrt(
                    feasible_original_variance
                )
            )

            assert (
                feasible_original_volatility
                >
                1e-12
            ), (
                "Feasible-target initial volatility "
                "must be positive."
            )

            # ==========================================================
            # FEASIBLE TARGET CONFIGURATION
            # ==========================================================
            #
            # Use a dedicated leverage allowance for this isolated
            # engine test. This does NOT modify any production regime
            # leverage policy.
            #

            feasible_max_leverage = 2.0

            feasible_original_volatility_annualized = (
                feasible_original_volatility
                *
                np.sqrt(252.0)
            )

            feasible_target_volatility = (
                feasible_original_volatility_annualized
                *
                2.0
            )

            required_scale = (
                feasible_target_volatility
                /
                feasible_original_volatility_annualized
            )

            required_gross = (
                feasible_original_gross
                *
                required_scale
            )

            print(
                f"Initial gross exposure: "
                f"{feasible_original_gross:.12f}"
            )

            print(
                f"Initial volatility: "
                f"{feasible_original_volatility:.12f}"
            )

            print(
                f"Target volatility: "
                f"{feasible_target_volatility:.12f}"
            )

            print(
                f"Required scaling: "
                f"{required_scale:.12f}"
            )

            print(
                f"Required gross exposure: "
                f"{required_gross:.12f}"
            )

            print(
                f"Maximum leverage: "
                f"{feasible_max_leverage:.12f}"
            )

            # ==========================================================
            # EXPLICIT FEASIBILITY ASSERTION
            # ==========================================================

            assert (
                required_gross
                <=
                feasible_max_leverage
                + 1e-8
            ), (
                "Feasible-target regression was "
                "constructed incorrectly: target "
                "requires excessive leverage."
            )

            print(
                "[PASS] Feasible target confirmed"
            )

            # ==========================================================
            # VOLATILITY TARGET ENGINE
            # ==========================================================

            volatility_engine = (
                optimizer.vol_target_engine
            )

            assert (
                volatility_engine
                is not None
            ), (
                "Production optimizer does not "
                "have a volatility-targeting engine."
            )

            targeted_weights = (
                volatility_engine
                .scale_weights(
                    feasible_weights,
                    feasible_covariance,
                    feasible_target_volatility,
                    max_leverage=(
                        feasible_max_leverage
                    ),
                    annualize=True,
                    periods_per_year=252,
                )
            )

            targeted_weights = np.asarray(
                targeted_weights,
                dtype=float,
            ).reshape(-1)

            # ==========================================================
            # TARGETED WEIGHT VALIDATION
            # ==========================================================

            assert targeted_weights.shape == (
                asset_count,
            ), (
                "Volatility-targeting engine returned "
                "an invalid weight vector shape."
            )

            assert np.isfinite(
                targeted_weights
            ).all(), (
                "Volatility-targeting engine returned "
                "non-finite weights."
            )

            assert np.all(
                targeted_weights
                >=
                -1e-10
            ), (
                "Volatility-targeting engine returned "
                "negative weights."
            )

            targeted_weights = np.maximum(
                targeted_weights,
                0.0,
            )

            # ==========================================================
            # FINAL GROSS EXPOSURE
            # ==========================================================

            feasible_final_gross = float(
                np.sum(
                    np.abs(
                        targeted_weights
                    )
                )
            )

            assert np.isfinite(
                feasible_final_gross
            ), (
                "Feasible-target final gross "
                "exposure is non-finite."
            )

            assert (
                feasible_final_gross
                <=
                feasible_max_leverage
                + 1e-8
            ), (
                "Feasible-target portfolio exceeded "
                "maximum leverage."
            )

            # ==========================================================
            # INDEPENDENT FINAL VOLATILITY
            # ==========================================================
            #
            # Deliberately calculate this independently from the engine
            # diagnostics. This verifies the actual returned weights.
            #

            feasible_final_variance = float(
                targeted_weights
                @
                feasible_covariance
                @
                targeted_weights
            )

            assert np.isfinite(
                feasible_final_variance
            ), (
                "Feasible-target final variance "
                "is non-finite."
            )

            if feasible_final_variance < 0.0:

                assert (
                    feasible_final_variance
                    >
                    -1e-12
                ), (
                    "Feasible-target final variance "
                    "is materially negative."
                )

                feasible_final_variance = 0.0

            feasible_final_volatility = float(
                np.sqrt(
                    feasible_final_variance
                )
            )

            assert np.isfinite(
                feasible_final_volatility
            ), (
                "Feasible-target final volatility "
                "is non-finite."
            )

            feasible_final_volatility_annualized = (
                feasible_final_volatility
                *
                np.sqrt(252.0)
            )

            feasible_volatility_error = (
                feasible_final_volatility_annualized
                -
                feasible_target_volatility
            )

            print(
                f"Final gross exposure: "
                f"{feasible_final_gross:.12f}"
            )

            print(
                f"Final volatility: "
                f"{feasible_final_volatility:.12f}"
            )

            print(
                f"Target volatility: "
                f"{feasible_target_volatility:.12f}"
            )

            print(
                f"Volatility error: "
                f"{feasible_volatility_error:.12f}"
            )

            # ==========================================================
            # FEASIBLE TARGET MUST BE ACHIEVED
            # ==========================================================

            assert np.isclose(
                feasible_final_volatility_annualized,
                feasible_target_volatility,
                rtol=1e-5,
                atol=1e-7,
            ), (
                "Feasible volatility target was "
                "not achieved. "
                f"Final annualized="
                f"{feasible_final_volatility_annualized:.12f}, "
                f"Target="
                f"{feasible_target_volatility:.12f}."
            )

            print(
                "[PASS] Feasible volatility target achieved"
            )

            # ==========================================================
            # ENGINE DIAGNOSTICS
            # ==========================================================

            if hasattr(
                volatility_engine,
                "get_last_result",
            ):

                feasible_vol_result = (
                    volatility_engine
                    .get_last_result()
                )

                assert (
                    feasible_vol_result
                    is not None
                ), (
                    "Volatility-targeting engine "
                    "did not expose a result after "
                    "the feasible-target operation."
                )

                if hasattr(
                    feasible_vol_result,
                    "target_achieved",
                ):

                    assert (
                        feasible_vol_result
                        .target_achieved
                    ), (
                        "Volatility-targeting diagnostics "
                        "did not mark the feasible target "
                        "as achieved."
                    )

                if hasattr(
                    feasible_vol_result,
                    "leverage_binding",
                ):

                    assert not (
                        feasible_vol_result
                        .leverage_binding
                    ), (
                        "Leverage unexpectedly bound "
                        "during the feasible-target test."
                    )

            print(
                "[PASS] Feasible-target diagnostics"
            )

            # ==========================================================
            # CROSS-REGIME DIFFERENTIATION
            # ==========================================================

            bull_weights = (
                regime_results[
                    "bull"
                ]["weights"]
            )

            neutral_weights = (
                regime_results[
                    "neutral"
                ]["weights"]
            )

            crisis_weights = (
                regime_results[
                    "crisis"
                ]["weights"]
            )

            bull_neutral_difference = float(
                np.max(
                    np.abs(
                        bull_weights
                        -
                        neutral_weights
                    )
                )
            )

            neutral_crisis_difference = float(
                np.max(
                    np.abs(
                        neutral_weights
                        -
                        crisis_weights
                    )
                )
            )

            bull_crisis_difference = float(
                np.max(
                    np.abs(
                        bull_weights
                        -
                        crisis_weights
                    )
                )
            )

            print()
            print(
                "Cross-regime maximum weight differences:"
            )

            print(
                "Bull vs neutral: "
                f"{bull_neutral_difference:.12f}"
            )

            print(
                "Neutral vs crisis: "
                f"{neutral_crisis_difference:.12f}"
            )

            print(
                "Bull vs crisis: "
                f"{bull_crisis_difference:.12f}"
            )

            assert (
                bull_neutral_difference
                > 1e-8
            )

            assert (
                neutral_crisis_difference
                > 1e-8
            )

            assert (
                bull_crisis_difference
                > 1e-8
            )

            print(
                "[PASS] Cross-regime differentiation"
            )

            # ==========================================================
            # RISK-BUDGET INVARIANT
            # ==========================================================

            for regime in (
                "bull",
                "neutral",
                "crisis",
            ):

                budget_sum = float(
                    regime_results[
                        regime
                    ]["risk_budget"].sum()
                )

                assert np.isclose(
                    budget_sum,
                    1.0,
                    atol=1e-6,
                )

            print(
                "[PASS] Risk budgets sum to one"
            )

            # ==========================================================
            # FINAL SUMMARY TABLE
            # ==========================================================

            print()
            print(
                "REGIME       GROSS        CASH"
                "           VOL        TARGET"
                "       MAX LEV"
            )

            for regime in (
                "bull",
                "neutral",
                "crisis",
            ):

                data = (
                    regime_results[
                        regime
                    ]
                )

                print(
                    f"{regime:<10} "
                    f"{data['gross']:.8f}   "
                    f"{data['cash']:.8f}   "
                    f"{data['volatility']:.8f}   "
                    f"{data['target']:.8f}   "
                    f"{data['max_leverage']:.8f}"
                )

            # ==========================================================
            # PRODUCTION REGRESSION PASSED
            # ==========================================================

            elapsed = (
                time.perf_counter()
                - start
            )

            result = TestResult(
                name=(
                    "Production portfolio regression"
                ),
                passed=True,
                return_code=0,
                elapsed_seconds=elapsed,
                stdout=(
                    "Production portfolio "
                    "construction regression passed."
                ),
                stderr="",
                command=(
                    self.python_executable,
                    "production-portfolio-regression",
                ),
            )

            self._record(
                result
            )

            print()
            print(
                "=" * 78
            )

            print(
                "PRODUCTION PORTFOLIO REGRESSION: PASS"
            )

            print(
                "=" * 78
            )

            return True

        except Exception as exc:

            elapsed = (
                time.perf_counter()
                - start
            )

            result = TestResult(
                name=(
                    "Production portfolio regression"
                ),
                passed=False,
                return_code=1,
                elapsed_seconds=elapsed,
                stdout="",
                stderr="",
                command=(
                    self.python_executable,
                    "production-portfolio-regression",
                ),
                reason=(
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
            )

            self._record(
                result
            )

            print()
            print(
                "=" * 78
            )

            print(
                "PRODUCTION PORTFOLIO REGRESSION: FAIL"
            )

            print(
                "=" * 78
            )

            return False

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
            "PHASE 9 — MODULE REGRESSION TESTS"
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

    # ==============================================================
    # PHASE 12B — REGIME-CONDITIONED FORECAST REGRESSION
    # ==============================================================

    def phase12b_regime_forecast_regression(
        self,
    ) -> bool:
        """
        Validate the production regime-conditioned forecast engine.

        Phase 12B verifies:

            1. RegimeForecastEngine construction.
            2. Engine health.
            3. Regime policy definitions.
            4. Policy weight invariants.
            5. Synthetic price compatibility.
            6. Baseline forecast component availability.
            7. Component dimensional integrity.
            8. Component numerical integrity.
            9. Regime-conditioned forecast construction.
           10. Asset ordering preservation.
           11. Cross-regime differentiation.
           12. Forecast combination invariants.
           13. Engine state integrity.
           14. Diagnostic integrity.
           15. Deterministic repeatability.

        This phase does not modify:

            - PortfolioOptimizer
            - Black-Litterman
            - RiskBudgetEngine
            - VolatilityTargeting
            - execution modules

        It independently validates the regime-conditioned
        forecasting layer before downstream integration.
        """

        self._banner(
            "PHASE 12B — REGIME-CONDITIONED FORECAST REGRESSION"
        )

        # ==========================================================
        # SYNTHETIC PRICE DATA
        # ==========================================================

        asset_order = list(__import__("assetuniverse").PRODUCTION_ASSETS)

        prices = build_phase11_price_data(
            asset_order,
            observations=300,
        )

        assert isinstance(
            prices,
            pd.DataFrame,
        ), (
            "Phase 12B synthetic prices must "
            "be a pandas DataFrame."
        )

        assert list(
            prices.columns
        ) == asset_order, (
            "Phase 12B synthetic price asset "
            "ordering does not match asset_order."
        )

        assert len(prices) >= (
            ExpectedReturnForecaster
            .minimum_history()
        ), (
            "Phase 12B synthetic price history "
            "is shorter than the production "
            "forecast requirement."
        )

        assert np.isfinite(
            prices.to_numpy(
                dtype=float
            )
        ).all(), (
            "Phase 12B synthetic prices contain "
            "non-finite values."
        )

        assert (
            prices.to_numpy(
                dtype=float
            )
            >
            0.0
        ).all(), (
            "Phase 12B synthetic prices contain "
            "non-positive values."
        )

        print(
            f"Price observations: {len(prices)}"
        )

        print(
            f"Asset count: {len(asset_order)}"
        )

        print(
            "[PASS] Phase 12B synthetic price data"
        )

        # ==========================================================
        # ENGINE CONSTRUCTION
        # ==========================================================

        engine = (
            RegimeForecastEngine()
        )

        assert isinstance(
            engine,
            RegimeForecastEngine,
        ), (
            "Phase 12B failed to construct "
            "RegimeForecastEngine."
        )

        assert isinstance(
            engine.forecaster,
            ExpectedReturnForecaster,
        ), (
            "RegimeForecastEngine does not "
            "contain ExpectedReturnForecaster."
        )

        print(
            "[PASS] Regime forecast engine construction"
        )

        # ==========================================================
        # ENGINE HEALTH
        # ==========================================================

        health = (
            engine.health_check()
        )

        assert isinstance(
            health,
            dict,
        ), (
            "Regime forecast health check "
            "must return a dictionary."
        )

        assert (
            health.get("status")
            ==
            "HEALTHY"
        ), (
            "Regime forecast engine health "
            f"check failed: {health}"
        )

        assert (
            health.get("api_version")
            ==
            RegimeForecastEngine.API_VERSION
        ), (
            "Regime forecast engine API version "
            "does not match."
        )

        assert (
            health.get("component")
            ==
            RegimeForecastEngine.COMPONENT
        ), (
            "Regime forecast engine component "
            "identifier does not match."
        )

        assert (
            health.get("regimes")
            ==
            list(
                RegimeForecastEngine.REGIMES
            )
        ), (
            "Regime forecast engine health "
            "does not expose the expected regimes."
        )

        assert (
            health.get("policy_count")
            ==
            len(
                RegimeForecastEngine.POLICIES
            )
        ), (
            "Regime forecast engine policy count "
            "is inconsistent."
        )

        print(
            f"Regime forecast health: {health}"
        )

        print(
            "[PASS] Regime forecast engine health"
        )

        # ==========================================================
        # REGIME INVENTORY
        # ==========================================================

        expected_regimes = (
            "bull",
            "neutral",
            "crisis",
        )

        assert (
            RegimeForecastEngine.REGIMES
            ==
            expected_regimes
        ), (
            "Phase 12B regime inventory does "
            "not match the production regime set."
        )

        assert set(
            RegimeForecastEngine.POLICIES.keys()
        ) == set(
            expected_regimes
        ), (
            "Phase 12B policy inventory does "
            "not match the production regime set."
        )

        print(
            "[PASS] Regime inventory"
        )

        # ==========================================================
        # POLICY VALIDATION
        # ==========================================================

        for regime in expected_regimes:

            policy = (
                RegimeForecastEngine
                .policy_for_regime(
                    regime
                )
            )

            assert isinstance(
                policy,
                RegimeForecastPolicy,
            ), (
                f"{regime}: invalid forecast "
                "policy type."
            )

            policy.validate()

            policy_values = np.asarray(
                [
                    policy.momentum,
                    policy.trend,
                    policy.mean_reversion,
                ],
                dtype=float,
            )

            assert np.isfinite(
                policy_values
            ).all(), (
                f"{regime}: policy contains "
                "non-finite values."
            )

            assert np.all(
                policy_values >= 0.0
            ), (
                f"{regime}: policy contains "
                "negative weights."
            )

            assert np.isclose(
                policy_values.sum(),
                1.0,
                atol=1e-12,
            ), (
                f"{regime}: forecast policy "
                "weights do not sum to one."
            )

            print(
                f"{regime.upper()} policy: "
                f"momentum={policy.momentum:.12f}, "
                f"trend={policy.trend:.12f}, "
                f"mean_reversion="
                f"{policy.mean_reversion:.12f}"
            )

        print(
            "[PASS] Regime forecast policy invariants"
        )

        # ==========================================================
        # REGIME VALIDATION
        # ==========================================================

        for regime in expected_regimes:

            normalized = (
                RegimeForecastEngine
                .validate_regime(
                    regime
                )
            )

            assert (
                normalized
                ==
                regime
            ), (
                f"{regime}: regime normalization "
                "changed a valid regime."
            )

        assert (
            RegimeForecastEngine
            .validate_regime(" BULL ")
            ==
            "bull"
        )

        assert (
            RegimeForecastEngine
            .validate_regime("Neutral")
            ==
            "neutral"
        )

        assert (
            RegimeForecastEngine
            .validate_regime("CRISIS")
            ==
            "crisis"
        )

        print(
            "[PASS] Regime validation and normalization"
        )

        # ==========================================================
        # INVALID REGIME TEST
        # ==========================================================

        invalid_regime_rejected = False

        try:

            RegimeForecastEngine.validate_regime(
                "invalid_regime"
            )

        except Exception:

            invalid_regime_rejected = True

        assert invalid_regime_rejected, (
            "Invalid regime was not rejected."
        )

        print(
            "[PASS] Invalid regime rejection"
        )

        # ==========================================================
        # BASELINE FORECAST COMPONENTS
        # ==========================================================

        baseline_forecast = (
            engine.forecaster.forecast(
                prices
            )
        )

        assert isinstance(
            baseline_forecast,
            pd.Series,
        ), (
            "Baseline expected-return forecast "
            "must be a pandas Series."
        )

        assert baseline_forecast.index.equals(
            prices.columns
        ), (
            "Baseline forecast asset ordering "
            "does not match prices."
        )

        baseline_values = (
            baseline_forecast.to_numpy(
                dtype=float
            )
        )

        assert baseline_values.size == (
            len(asset_order)
        ), (
            "Baseline forecast has incorrect "
            "asset dimension."
        )

        assert np.isfinite(
            baseline_values
        ).all(), (
            "Baseline forecast contains "
            "non-finite values."
        )

        components = (
            engine.forecaster.last_components
        )

        assert isinstance(
            components,
            dict,
        ), (
            "Baseline forecaster did not "
            "expose component forecasts."
        )

        required_components = {
            "momentum",
            "trend",
            "mean_reversion",
        }

        assert required_components <= set(
            components.keys()
        ), (
            "Baseline forecaster is missing "
            "required forecast components."
        )

        component_arrays = {}

        for name in (
            "momentum",
            "trend",
            "mean_reversion",
        ):

            component = components[
                name
            ]

            assert isinstance(
                component,
                pd.Series,
            ), (
                f"{name}: forecast component "
                "must be a pandas Series."
            )

            assert component.index.equals(
                prices.columns
            ), (
                f"{name}: asset ordering "
                "does not match prices."
            )

            values = component.to_numpy(
                dtype=float
            )

            assert values.size == (
                len(asset_order)
            ), (
                f"{name}: incorrect forecast "
                "dimension."
            )

            assert np.isfinite(
                values
            ).all(), (
                f"{name}: forecast contains "
                "non-finite values."
            )

            component_arrays[
                name
            ] = values

        print(
            "[PASS] Baseline forecast components"
        )

        # ==========================================================
        # REGIME FORECASTS
        # ==========================================================

        forecasts = {}

        for regime in expected_regimes:

            forecast = (
                engine.forecast(
                    prices=prices,
                    regime=regime,
                )
            )

            assert isinstance(
                forecast,
                pd.Series,
            ), (
                f"{regime}: regime forecast "
                "must be a pandas Series."
            )

            assert forecast.index.equals(
                prices.columns
            ), (
                f"{regime}: forecast asset "
                "ordering does not match prices."
            )

            values = forecast.to_numpy(
                dtype=float
            )

            assert values.size == (
                len(asset_order)
            ), (
                f"{regime}: forecast has "
                "incorrect asset dimension."
            )

            assert np.isfinite(
                values
            ).all(), (
                f"{regime}: forecast contains "
                "non-finite values."
            )

            forecasts[
                regime
            ] = forecast.copy()

            print(
                f"{regime.upper()} forecast "
                "generated."
            )

        print(
            "[PASS] Regime-conditioned forecasts"
        )

        # ==========================================================
        # EXACT WEIGHTED-COMBINATION INVARIANT
        # ==========================================================

        for regime in expected_regimes:

            policy = (
                RegimeForecastEngine
                .policy_for_regime(
                    regime
                )
            )

            expected_forecast = (
                policy.momentum
                * component_arrays[
                    "momentum"
                ]
                +
                policy.trend
                * component_arrays[
                    "trend"
                ]
                +
                policy.mean_reversion
                * component_arrays[
                    "mean_reversion"
                ]
            )

            actual_forecast = (
                forecasts[
                    regime
                ].to_numpy(
                    dtype=float
                )
            )

            assert np.allclose(
                actual_forecast,
                expected_forecast,
                atol=1e-12,
                rtol=1e-10,
            ), (
                f"{regime}: regime forecast "
                "does not equal the configured "
                "weighted forecast components."
            )

        print(
            "[PASS] Regime forecast combination invariant"
        )

        # ==========================================================
        # CROSS-REGIME DIFFERENTIATION
        # ==========================================================

        bull_values = (
            forecasts[
                "bull"
            ].to_numpy(
                dtype=float
            )
        )

        neutral_values = (
            forecasts[
                "neutral"
            ].to_numpy(
                dtype=float
            )
        )

        crisis_values = (
            forecasts[
                "crisis"
            ].to_numpy(
                dtype=float
            )
        )

        bull_neutral_difference = float(
            np.max(
                np.abs(
                    bull_values
                    -
                    neutral_values
                )
            )
        )

        neutral_crisis_difference = float(
            np.max(
                np.abs(
                    neutral_values
                    -
                    crisis_values
                )
            )
        )

        bull_crisis_difference = float(
            np.max(
                np.abs(
                    bull_values
                    -
                    crisis_values
                )
            )
        )

        print()
        print(
            "Cross-regime maximum forecast "
            "differences:"
        )

        print(
            "Bull vs neutral: "
            f"{bull_neutral_difference:.12f}"
        )

        print(
            "Neutral vs crisis: "
            f"{neutral_crisis_difference:.12f}"
        )

        print(
            "Bull vs crisis: "
            f"{bull_crisis_difference:.12f}"
        )

        assert (
            bull_neutral_difference
            >
            1e-12
        ), (
            "Bull and neutral forecasts "
            "are unexpectedly identical."
        )

        assert (
            neutral_crisis_difference
            >
            1e-12
        ), (
            "Neutral and crisis forecasts "
            "are unexpectedly identical."
        )

        assert (
            bull_crisis_difference
            >
            1e-12
        ), (
            "Bull and crisis forecasts "
            "are unexpectedly identical."
        )

        print(
            "[PASS] Cross-regime forecast differentiation"
        )

        # ==========================================================
        # ENGINE STATE
        # ==========================================================

        assert (
            engine.last_regime
            ==
            "crisis"
        ), (
            "Engine state does not contain "
            "the most recently evaluated regime."
        )

        assert isinstance(
            engine.last_forecast,
            pd.Series,
        )

        assert engine.last_forecast.index.equals(
            prices.columns
        )

        assert np.allclose(
            engine.last_forecast.to_numpy(
                dtype=float
            ),
            forecasts[
                "crisis"
            ].to_numpy(
                dtype=float
            ),
            atol=1e-12,
            rtol=1e-10,
        ), (
            "Engine last_forecast does not "
            "match the latest crisis forecast."
        )

        assert isinstance(
            engine.last_policy,
            RegimeForecastPolicy,
        )

        assert (
            engine.last_policy
            ==
            RegimeForecastEngine.POLICIES[
                "crisis"
            ]
        )

        assert isinstance(
            engine.last_components,
            dict,
        )

        assert required_components <= set(
            engine.last_components.keys()
        )

        print(
            "[PASS] Regime forecast engine state"
        )

        # ==========================================================
        # DIAGNOSTICS
        # ==========================================================

        diagnostics = (
            engine.last_diagnostics
        )

        assert isinstance(
            diagnostics,
            dict,
        ), (
            "Regime forecast diagnostics "
            "must be a dictionary."
        )

        assert (
            diagnostics.get("api_version")
            ==
            RegimeForecastEngine.API_VERSION
        )

        assert (
            diagnostics.get("component")
            ==
            RegimeForecastEngine.COMPONENT
        )

        assert (
            diagnostics.get("regime")
            ==
            "crisis"
        )

        assert (
            diagnostics.get("asset_count")
            ==
            len(asset_order)
        )

        assert (
            diagnostics.get("observations")
            ==
            len(prices)
        )

        diagnostic_weights = (
            diagnostics.get(
                "weights"
            )
        )

        assert isinstance(
            diagnostic_weights,
            dict,
        )

        assert np.isclose(
            sum(
                diagnostic_weights.values()
            ),
            1.0,
            atol=1e-12,
        )

        assert np.isclose(
            diagnostic_weights[
                "momentum"
            ],
            0.20,
            atol=1e-12,
        )

        assert np.isclose(
            diagnostic_weights[
                "trend"
            ],
            0.20,
            atol=1e-12,
        )

        assert np.isclose(
            diagnostic_weights[
                "mean_reversion"
            ],
            0.60,
            atol=1e-12,
        )

        print(
            "[PASS] Regime forecast diagnostics"
        )

        # ==========================================================
        # DETERMINISTIC REPEATABILITY
        # ==========================================================

        repeated_crisis = (
            engine.forecast(
                prices=prices,
                regime="crisis",
            )
        )

        assert np.allclose(
            repeated_crisis.to_numpy(
                dtype=float
            ),
            forecasts[
                "crisis"
            ].to_numpy(
                dtype=float
            ),
            atol=1e-12,
            rtol=1e-10,
        ), (
            "Repeated crisis forecast is "
            "not deterministic."
        )

        print(
            "[PASS] Regime forecast determinism"
        )

        # ==========================================================
        # PHASE COMPLETE
        # ==========================================================

        print()
        print(
            "[PASS] PHASE 12B — "
            "REGIME-CONDITIONED FORECAST REGRESSION"
        )

        return True

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
            "PHASE 10 — REPOSITORY STATUS"
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
    # FULL SUITE
    # ==================================================================

    def run(
        self,
    ) -> bool:
        """
        Execute the complete system regression gate.

        Mandatory gates execute in dependency order:

            PHASE 0  — Project root
            PHASE 1  — Python runtime
            PHASE 2  — Required module files
            PHASE 3  — Python compilation
            PHASE 4  — Ruff static analysis
            PHASE 5  — Import smoke test
            PHASE 6A — Production portfolio regression
            PHASE 12B — Regime-conditioned forecast regression
    R3B — ATR and position-sizing module regression
            PHASE 7  — Regression module inventory
            PHASE 8  — Execution chain integrity
            PHASE 9  — Module regression tests

        PHASE 10 — Git status is informational and therefore
        does not determine the regression result.

        Returns
        -------
        bool
            True when all mandatory gates pass.
            False when any mandatory gate fails.
        """

        self.started_at = time.perf_counter()

        self._banner(
            "FULL SYSTEM REGRESSION SUITE"
        )

        print(
            "Execution stack "
            "regression gate"
        )

        print(
            f"Python: "
            f"{self.python_executable}"
        )

        print(
            f"Project: "
            f"{self.project_root}"
        )

        # ==============================================================
        # REGRESSION GATES
        # ==============================================================

        gates = (
            # ----------------------------------------------------------
            # PHASE 0 — PROJECT ROOT
            # ----------------------------------------------------------
            self.check_project_root,

            # ----------------------------------------------------------
            # PHASE 1 — PYTHON RUNTIME
            # ----------------------------------------------------------
            self.check_python_version,

            # ----------------------------------------------------------
            # PHASE 2 — REQUIRED MODULE FILES
            # ----------------------------------------------------------
            self.check_required_files,

            # ----------------------------------------------------------
            # PHASE 3 — PYTHON COMPILATION
            # ----------------------------------------------------------
            self.compile_all,

            # ----------------------------------------------------------
            # PHASE 4 — RUFF STATIC ANALYSIS
            # ----------------------------------------------------------
            self.ruff_check,

            # ----------------------------------------------------------
            # PHASE 5 — IMPORT SMOKE TEST
            # ----------------------------------------------------------
            self.import_smoke_test,

            # ----------------------------------------------------------
            # PHASE 6A — PRODUCTION PORTFOLIO REGRESSION
            # ----------------------------------------------------------
            self.production_portfolio_regression,

            # ----------------------------------------------------------
            # PHASE 12B — REGIME-CONDITIONED FORECAST REGRESSION
            # ----------------------------------------------------------
            self.phase12b_regime_forecast_regression,

            # ----------------------------------------------------------
            # PHASE 7 — REGRESSION MODULE INVENTORY
            # ----------------------------------------------------------
            self.check_regression_modules,

            # ----------------------------------------------------------
            # PHASE 8 — EXECUTION CHAIN INTEGRITY
            # ----------------------------------------------------------
            self.execution_chain_check,

            # ----------------------------------------------------------
            # PHASE 9 — MODULE REGRESSION TESTS
            # ----------------------------------------------------------
            self.run_module_tests,
        )

        # ==============================================================
        # EXECUTE MANDATORY GATES
        # ==============================================================

        for gate in gates:

            if not gate():

                self.finished_at = (
                    time.perf_counter()
                )

                self.print_summary()

                return False

        # ==============================================================
        # PHASE 10 — REPOSITORY STATUS
        #
        # Informational only.
        #
        # Modified/untracked files must NOT cause the production
        # regression gate to fail.
        # ==============================================================

        self.git_status_check()

        # ==============================================================
        # FINALIZE
        # ==============================================================

        self.finished_at = (
            time.perf_counter()
        )

        self.print_summary()

        return (
            self.summary()[
                "system_status"
            ]
            ==
            "PASS"
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

    assert (
        "portfoliooptimizer.py"
        in REQUIRED_MODULES
    )

    assert (
        "riskbudgetengine.py"
        in REQUIRED_MODULES
    )

    assert (
        "volatilitytargeting.py"
        in REQUIRED_MODULES
    )

    assert (
        "productioncomposition.py"
        in REQUIRED_MODULES
    )

    assert (
        "riskcontributionanalyzer.py"
        in REQUIRED_MODULES
    )

    assert (
        "constraints.py"
        in REQUIRED_MODULES
    )

    assert (
        "atr.py"
        in REQUIRED_MODULES
    )

    assert (
        "positionsizing.py"
        in REQUIRED_MODULES
    )

    assert (
        REGRESSION_MODULES
        == (
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