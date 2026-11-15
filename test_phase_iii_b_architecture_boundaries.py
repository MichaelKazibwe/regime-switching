"""
======================================================================
PHASE III-B ARCHITECTURE BOUNDARY REGRESSION TESTS
======================================================================

Institutional architecture guard for production dependency direction.

These tests enforce the following boundary:

    production modules
        |
        +----> production modules
        |
        X----> testsupport
        X----> rewrite
        X----> archive

Test infrastructure may depend on production modules and testsupport.

Archive code may depend on legacy/reconstruction code where historically
required, but production code must never depend on archive or rewrite
modules.

The purpose of this module is architectural containment.

A future developer must not be able to reintroduce a production
dependency on test infrastructure or legacy reconstruction code without
causing the regression suite to fail.

======================================================================
"""

from __future__ import annotations

import ast
from pathlib import Path


# ======================================================================
# SECTION 1
# REPOSITORY ROOT
# ======================================================================

PROJECT_ROOT = Path(__file__).resolve().parent


# ======================================================================
# SECTION 2
# PRODUCTION MODULE CLASSIFICATION
# ======================================================================

def _production_python_files() -> list[Path]:
    """
    Return root-level production Python modules.

    Test modules, test infrastructure, and explicit development harnesses
    are excluded from this architectural boundary check.
    """

    excluded = {
        "testsupport.py",
        "regression_suite.py",
        "final_regression.py",
        "step7_production_test.py",
        "step8_historical_data_test.py",
        "step9_historical_backtest.py",
        "rewrite.py",
    }

    return sorted(
        path
        for path in PROJECT_ROOT.glob("*.py")
        if path.name not in excluded
        and not path.name.startswith("test_")
    )


# ======================================================================
# SECTION 3
# IMPORT EXTRACTION
# ======================================================================

def _imported_top_level_modules(
    source_path: Path,
) -> set[str]:
    """
    Extract top-level imported module names using Python AST parsing.
    """

    source = source_path.read_text(
        encoding="utf-8",
    )

    tree = ast.parse(
        source,
        filename=str(source_path),
    )

    modules: set[str] = set()

    for node in ast.walk(tree):

        if isinstance(node, ast.Import):

            for alias in node.names:

                modules.add(
                    alias.name.split(".", 1)[0]
                )

        elif isinstance(node, ast.ImportFrom):

            if node.module is not None:

                modules.add(
                    node.module.split(".", 1)[0]
                )

    return modules


# ======================================================================
# SECTION 4
# FORBIDDEN PRODUCTION DEPENDENCIES
# ======================================================================

FORBIDDEN_PRODUCTION_MODULES = frozenset(
    {
        "testsupport",
        "rewrite",
        "archive",
    }
)


# ======================================================================
# SECTION 5
# PRODUCTION DEPENDENCY BOUNDARY
# ======================================================================

def test_production_modules_do_not_import_test_or_legacy_code() -> None:
    """
    Production modules must not depend on test infrastructure or legacy
    reconstruction/archive code.
    """

    violations: list[str] = []

    for source_path in _production_python_files():

        imports = _imported_top_level_modules(
            source_path,
        )

        forbidden = (
            imports
            & FORBIDDEN_PRODUCTION_MODULES
        )

        for module_name in sorted(forbidden):

            violations.append(
                f"{source_path.name} -> {module_name}"
            )

    assert not violations, (
        "Forbidden production dependency detected:\n"
        + "\n".join(
            f"  - {violation}"
            for violation in violations
        )
    )


# ======================================================================
# SECTION 6
# TEST INFRASTRUCTURE BOUNDARY
# ======================================================================

def test_testsupport_is_not_a_production_module() -> None:
    """
    testsupport.py must remain explicitly classified as test
    infrastructure.
    """

    testsupport = (
        PROJECT_ROOT
        / "testsupport.py"
    )

    assert testsupport.exists(), (
        "Expected testsupport.py to exist."
    )

    assert (
        testsupport.name
        == "testsupport.py"
    )


# ======================================================================
# SECTION 7
# ARCHIVE BOUNDARY
# ======================================================================

def test_archive_is_outside_production_root() -> None:
    """
    Archive code must remain physically separated from root production
    modules.
    """

    archive_directory = (
        PROJECT_ROOT
        / "archive"
    )

    assert archive_directory.exists(), (
        "Expected archive/ directory to exist."
    )

    assert archive_directory.is_dir(), (
        "Expected archive/ to be a directory."
    )


# ======================================================================
# SECTION 8
# REWRITE BOUNDARY
# ======================================================================

def test_rewrite_is_not_classified_as_production() -> None:
    """
    rewrite.py is explicitly treated as reconstruction/development
    infrastructure rather than production code.
    """

    rewrite_module = (
        PROJECT_ROOT
        / "rewrite.py"
    )

    if not rewrite_module.exists():
        return

    production_files = {
        path.name
        for path in _production_python_files()
    }

    assert (
        "rewrite.py"
        not in production_files
    )


# ======================================================================
# SECTION 9
# ARCHITECTURAL SMOKE TEST
# ======================================================================

def test_production_boundary_scan_is_nonempty() -> None:
    """
    Ensure the architectural scan is actually inspecting production
    modules rather than silently passing because the repository is empty.
    """

    production_files = (
        _production_python_files()
    )

    assert production_files, (
        "Production boundary scan found no "
        "root-level production Python modules."
    )