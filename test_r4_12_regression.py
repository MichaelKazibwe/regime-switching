"""
======================================================================
R4.12 — OPTIONS RISK REGRESSION CERTIFICATION
======================================================================

Purpose
-------
Certification gate for the completed R4.2 -> R4.11 options-risk chain.

This regression deliberately tests the EXISTING module self-test contracts
rather than duplicating their internal quantitative logic.

Certified stages
----------------
R4.2  OptionContract / OptionPosition
R4.3  Black-Scholes valuation
R4.4  Analytical Greeks
R4.5  Portfolio Greeks aggregation
R4.6  Put/Call parity diagnostics
R4.7  Volatility-surface inputs
R4.8  Options stress
R4.9  Options tail risk
R4.10 Options risk governor
R4.11 Risk report integration

Boundaries
----------
- No production module is modified by this certification file.
- No pricing formula is duplicated here.
- No risk decision is created here.
- No execution is performed.
- The canonical ETF universe is not modified.
- Failures are propagated; there is no fail-open behavior.

The certification runner executes each completed R4 module through its
existing deterministic module-level self-test / regression entry point.
======================================================================
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


API_VERSION = "1.0.0"
COMPONENT = "R4OptionsRegressionCertification"
PHASE = "R4.12"

R4_MODULES = (
    "optionsrisk.py",
    "blackscholes.py",
    "analyticalgreeks.py",
    "portfoliogreeks.py",
    "putcallparity.py",
    "Volatility_Surface_Inputs.py",
    "Options_Stress.py",
    "optionstailrisk.py",
    "optionsriskgovernor.py",
    "riskreport.py",
)


def _project_directory() -> Path:
    """
    Return the directory containing this certification file.

    The certification must execute against the same source tree as the
    production modules under test.
    """
    return Path(__file__).resolve().parent


def _run_module(module_name: str) -> None:
    """
    Execute one production module's deterministic self-test entry point.

    A non-zero exit status is a certification failure.
    """
    module_path = _project_directory() / module_name

    if not module_path.is_file():
        raise AssertionError(
            f"R4.12 required module is missing: {module_name}"
        )

    completed = subprocess.run(
        [sys.executable, str(module_path)],
        cwd=_project_directory(),
        check=False,
        capture_output=True,
        text=True,
    )

    if completed.returncode != 0:
        raise AssertionError(
            "R4.12 module regression failed for "
            f"{module_name}\n"
            f"STDOUT:\n{completed.stdout}\n"
            f"STDERR:\n{completed.stderr}"
        )


def test_r4_module_inventory() -> None:
    """
    Every certified R4.2-R4.11 production module must exist.
    """
    project_directory = _project_directory()

    missing = [
        module
        for module in R4_MODULES
        if not (project_directory / module).is_file()
    ]

    assert not missing, (
        "R4.12 module inventory failure: "
        f"missing={missing}"
    )


def test_r4_module_self_tests() -> None:
    """
    Every completed R4 stage must pass its own deterministic regression.
    """
    for module_name in R4_MODULES:
        _run_module(module_name)


def test_r4_certification_scope_is_complete() -> None:
    """
    Verify that the certification explicitly covers every completed R4 stage.
    """
    expected = {
        "optionsrisk.py": "R4.2",
        "blackscholes.py": "R4.3",
        "analyticalgreeks.py": "R4.4",
        "portfoliogreeks.py": "R4.5",
        "putcallparity.py": "R4.6",
        "Volatility_Surface_Inputs.py": "R4.7",
        "Options_Stress.py": "R4.8",
        "optionstailrisk.py": "R4.9",
        "optionsriskgovernor.py": "R4.10",
        "riskreport.py": "R4.11",
    }

    assert tuple(expected) == R4_MODULES
    assert len(R4_MODULES) == 10


def run_regression_tests() -> None:
    """
    Execute the complete R4.12 certification gate.
    """
    test_r4_module_inventory()
    test_r4_module_self_tests()
    test_r4_certification_scope_is_complete()

    print("=" * 70)
    print("R4.12 OPTIONS RISK REGRESSION CERTIFICATION: PASS")
    print("=" * 70)
    print("Certified stages:")
    for module_name in R4_MODULES:
        print(f"  PASS  {module_name}")
    print("-" * 70)
    print(f"API VERSION: {API_VERSION}")
    print(f"COMPONENT:   {COMPONENT}")
    print(f"PHASE:       {PHASE}")
    print("R4.2 -> R4.11 regression chain: PASS")
    print("=" * 70)


if __name__ == "__main__":
    run_regression_tests()
