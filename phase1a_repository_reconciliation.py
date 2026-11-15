#!/usr/bin/env python3
"""
================================================================
REGIME SWITCHING SYSTEM
PHASE 1A — REPOSITORY RECONCILIATION AUDIT
================================================================

Purpose
-------
Perform a READ-ONLY reconciliation of the local repository.

This script does NOT:

    - modify files
    - stage files
    - delete files
    - rename files
    - commit
    - push
    - reset
    - checkout
    - alter Git configuration

It inventories:

    1. repository identity
    2. branch and HEAD
    3. remote synchronization
    4. tracked files
    5. modified tracked files
    6. untracked files
    7. ignored files
    8. Python source
    9. tests
   10. documentation
   11. backups
   12. patches
   13. regression artifacts
   14. duplicate/variant documentation
   15. potentially sensitive files
   16. exact working-tree diffs
   17. source additions/removals
   18. repository configuration
   19. recommended file disposition
   20. Phase 1A readiness assessment

Output
------
phase1a_repository_reconciliation.txt

The generated report is itself NOT automatically staged or committed.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

# ==============================================================
# CONFIGURATION
# ==============================================================

REPORT_NAME = "phase1a_repository_reconciliation.txt"

PROJECT_ROOT = Path.cwd().resolve()


# ==============================================================
# OUTPUT HELPERS
# ==============================================================


lines: list[str] = []


def emit(text: str = "") -> None:
    print(text)
    lines.append(text)


def section(title: str) -> None:
    emit()
    emit("=" * 76)
    emit(title)
    emit("=" * 76)


def subsection(title: str) -> None:
    emit()
    emit(f"--- {title} ---")


# ==============================================================
# COMMAND EXECUTION
# ==============================================================


def run_git(
    *args: str,
    check: bool = False,
) -> str:
    """
    Execute a read-only Git command.

    No mutating Git commands are used anywhere in this script.
    """

    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Git command failed: git {' '.join(args)}\n"
            f"{result.stderr.strip()}"
        )

    return result.stdout.strip()


def command_exists(command: str) -> bool:
    return (
        subprocess.run(
            ["bash", "-lc", f"command -v {command}"],
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


# ==============================================================
# FILE HELPERS
# ==============================================================


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()

        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)

        return digest.hexdigest()

    except OSError:
        return None


def file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def is_python(path: str) -> bool:
    return path.endswith(".py")


def is_test(path: str) -> bool:
    name = Path(path).name

    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name == "tests.py"
    )


def is_documentation(path: str) -> bool:
    suffix = Path(path).suffix.lower()

    return suffix in {
        ".md",
        ".txt",
        ".rst",
        ".pdf",
        ".docx",
    }


def classify_file(path: str) -> str:
    name = Path(path).name.lower()

    if name in {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
    }:
        return "SENSITIVE / ENVIRONMENT"

    if "backup" in name:
        return "BACKUP / RECOVERY ARTIFACT"

    if name.endswith(".patch"):
        return "PATCH / PROVENANCE ARTIFACT"

    if ".diff" in name:
        return "DIFF / PROVENANCE ARTIFACT"

    if "regression" in name:
        return "REGRESSION ARTIFACT"

    if "phase1_" in name:
        return "PHASE 1 WORKING ARTIFACT"

    if name.endswith(".zip"):
        return "ARCHIVE"

    if name.startswith("module_registry"):
        return "PROJECT REGISTRY"

    if "complete_project_source" in name:
        return "PROJECT SOURCE SNAPSHOT"

    if "system_inventory" in name:
        return "SYSTEM INVENTORY"

    if is_test(path):
        return "TEST"

    if is_python(path):
        return "PYTHON SOURCE"

    if is_documentation(path):
        return "DOCUMENTATION"

    if name in {
        ".gitignore",
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "setup.cfg",
        "tox.ini",
        "pytest.ini",
        "makefile",
    }:
        return "PROJECT CONFIGURATION"

    return "OTHER"


def walk_files() -> list[Path]:
    results: list[Path] = []

    for root, dirs, files in os.walk(PROJECT_ROOT):

        root_path = Path(root)

        # Do not inventory Git internals.
        dirs[:] = [
            d
            for d in dirs
            if d != ".git"
        ]

        for filename in files:
            path = root_path / filename

            if ".git" in path.parts:
                continue

            results.append(path)

    return sorted(
        results,
        key=lambda p: str(p).lower(),
    )


# ==============================================================
# GIT INVENTORY
# ==============================================================


def parse_porcelain_status() -> list[tuple[str, str]]:
    output = run_git(
        "status",
        "--porcelain=v1",
    )

    results = []

    for line in output.splitlines():

        if len(line) < 3:
            continue

        status = line[:2]
        path = line[3:]

        results.append(
            (
                status,
                path,
            )
        )

    return results


def get_tracked_files() -> list[str]:
    output = run_git(
        "ls-files",
    )

    return [
        line
        for line in output.splitlines()
        if line.strip()
    ]


def get_untracked_files() -> list[str]:
    output = run_git(
        "ls-files",
        "--others",
        "--exclude-standard",
    )

    return [
        line
        for line in output.splitlines()
        if line.strip()
    ]


def get_ignored_files() -> list[str]:
    output = run_git(
        "status",
        "--ignored",
        "--porcelain=v1",
    )

    ignored = []

    for line in output.splitlines():

        if line.startswith("!! "):
            ignored.append(line[3:])

    return ignored


# ==============================================================
# HEADER
# ==============================================================


section(
    "REGIME SWITCHING SYSTEM — PHASE 1A REPOSITORY RECONCILIATION"
)

emit(
    "READ-ONLY AUDIT — NO REPOSITORY MUTATION"
)

emit(
    f"Project root : {PROJECT_ROOT}"
)


# ==============================================================
# GIT VALIDITY
# ==============================================================


section("1. REPOSITORY IDENTITY")

if not command_exists("git"):

    emit("[FAIL] Git executable not found.")
    sys.exit(1)

emit(
    f"[PASS] Git executable found: "
    f"{run_git('--exec-path')}"
)

emit(
    f"Git version : "
    f"{run_git('--version')}"
)

git_root = run_git(
    "rev-parse",
    "--show-toplevel",
)

emit(
    f"Git root    : {git_root}"
)

bare = run_git(
    "rev-parse",
    "--is-bare-repository",
)

emit(
    f"Bare repo   : {bare}"
)


# ==============================================================
# BRANCH / HEAD
# ==============================================================


section("2. BRANCH AND HEAD")

branch = run_git(
    "branch",
    "--show-current",
)

head_short = run_git(
    "rev-parse",
    "--short",
    "HEAD",
)

head_full = run_git(
    "rev-parse",
    "HEAD",
)

head_subject = run_git(
    "log",
    "-1",
    "--format=%s",
)

head_author = run_git(
    "log",
    "-1",
    "--format=%an <%ae>",
)

head_date = run_git(
    "log",
    "-1",
    "--format=%aI",
)

emit(f"Branch       : {branch}")
emit(f"HEAD         : {head_short}")
emit(f"Full HEAD    : {head_full}")
emit(f"HEAD subject : {head_subject}")
emit(f"HEAD author  : {head_author}")
emit(f"HEAD date    : {head_date}")


# ==============================================================
# REMOTE
# ==============================================================


section("3. REMOTE SYNCHRONIZATION")

remote = run_git(
    "remote",
    "-v",
)

emit(remote or "[WARNING] No Git remotes configured.")

origin_url = run_git(
    "remote",
    "get-url",
    "origin",
)

emit(
    f"Origin URL : {origin_url or '[NONE]'}"
)

upstream = run_git(
    "rev-parse",
    "--abbrev-ref",
    "--symbolic-full-name",
    "@{u}",
)

emit(
    f"Upstream   : {upstream or '[NONE]'}"
)

if upstream:

    ahead_behind = run_git(
        "rev-list",
        "--left-right",
        "--count",
        f"HEAD...{upstream}",
    )

    emit(
        f"Ahead/behind : {ahead_behind}"
    )

    parts = ahead_behind.split()

    if len(parts) == 2:

        emit(
            f"Commits ahead  : {parts[0]}"
        )

        emit(
            f"Commits behind : {parts[1]}"
        )


# ==============================================================
# STATUS
# ==============================================================


section("4. WORKING TREE STATUS")

status_entries = parse_porcelain_status()

modified = [
    (status, path)
    for status, path
    in status_entries
    if status != "??"
]

untracked = [
    path
    for status, path
    in status_entries
    if status == "??"
]

staged = [
    (status, path)
    for status, path
    in status_entries
    if status[0] not in (" ", "?")
]

unstaged = [
    (status, path)
    for status, path
    in status_entries
    if status[1] not in (" ", "?")
]

emit(
    f"Total status entries : {len(status_entries)}"
)

emit(
    f"Staged changes       : {len(staged)}"
)

emit(
    f"Unstaged changes     : {len(unstaged)}"
)

emit(
    f"Modified tracked     : {len(modified)}"
)

emit(
    f"Untracked            : {len(untracked)}"
)

subsection("MODIFIED TRACKED FILES")

for status, path in modified:
    emit(f"{status} {path}")

subsection("UNTRACKED FILES")

for path in untracked:
    emit(path)


# ==============================================================
# TRACKED INVENTORY
# ==============================================================


section("5. TRACKED FILE INVENTORY")

tracked = get_tracked_files()

emit(
    f"Tracked files : {len(tracked)}"
)

tracked_python = [
    path
    for path in tracked
    if is_python(path)
]

tracked_tests = [
    path
    for path in tracked
    if is_test(path)
]

emit(
    f"Tracked Python files : {len(tracked_python)}"
)

emit(
    f"Tracked test files   : {len(tracked_tests)}"
)

subsection("TRACKED PYTHON SOURCE")

for path in tracked_python:

    if not is_test(path):
        emit(path)

subsection("TRACKED TEST FILES")

for path in tracked_tests:
    emit(path)


# ==============================================================
# UNTRACKED CLASSIFICATION
# ==============================================================


section("6. UNTRACKED FILE CLASSIFICATION")

classification: dict[str, list[str]] = {}

for path in untracked:

    category = classify_file(path)

    classification.setdefault(
        category,
        [],
    ).append(path)

for category in sorted(classification):

    subsection(category)

    for path in sorted(
        classification[category]
    ):

        emit(path)


# ==============================================================
# ALL FILE INVENTORY
# ==============================================================


section("7. COMPLETE LOCAL FILE INVENTORY")

all_files = walk_files()

counts = Counter(
    classify_file(
        relative(path)
    )
    for path in all_files
)

for category in sorted(counts):

    emit(
        f"{category:<36} {counts[category]}"
    )


# ==============================================================
# DOCUMENTATION VARIANTS
# ==============================================================


section("8. DOCUMENTATION / SNAPSHOT RECONCILIATION")

documentation_candidates = [
    path
    for path in all_files
    if (
        "MODULE_REGISTRY" in path.name.upper()
        or "COMPLETE_PROJECT_SOURCE" in path.name.upper()
        or "SYSTEM_INVENTORY" in path.name.upper()
    )
]

for path in documentation_candidates:

    size = file_size(path)
    digest = sha256(path)

    emit(
        f"{relative(path)}"
    )

    emit(
        f"  size   : {size} bytes"
    )

    emit(
        f"  sha256 : {digest}"
    )


# ==============================================================
# BACKUPS
# ==============================================================


section("9. BACKUP / RECOVERY ARTIFACTS")

backup_files = [
    relative(path)
    for path in all_files
    if (
        "backup" in path.name.lower()
        or path.name.endswith(".bak")
    )
]

if backup_files:

    for path in backup_files:
        emit(path)

else:
    emit("[PASS] No backup artifacts detected.")


# ==============================================================
# PATCHES / DIFFS
# ==============================================================


section("10. PATCH / DIFF / PROVENANCE ARTIFACTS")

provenance_files = [
    relative(path)
    for path in all_files
    if (
        path.name.endswith(".patch")
        or ".diff" in path.name.lower()
    )
]

if provenance_files:

    for path in provenance_files:
        emit(path)

else:

    emit(
        "[PASS] No patch/diff artifacts detected."
    )


# ==============================================================
# REGRESSION ARTIFACTS
# ==============================================================


section("11. REGRESSION ARTIFACTS")

regression_files = [
    relative(path)
    for path in all_files
    if (
        "regression" in path.name.lower()
        or "pass" in path.name.lower()
    )
    and path.suffix.lower() in {
        ".txt",
        ".log",
    }
]

if regression_files:

    for path in regression_files:
        emit(path)

else:

    emit(
        "[WARNING] No regression artifacts detected."
    )


# ==============================================================
# CONFIGURATION
# ==============================================================


section("12. PROJECT CONFIGURATION")

configuration_files = [
    ".gitignore",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "setup.py",
    "setup.cfg",
    "tox.ini",
    "pytest.ini",
    "Makefile",
]

for filename in configuration_files:

    path = PROJECT_ROOT / filename

    if path.exists():

        emit(
            f"[PRESENT] {filename}"
        )

    else:

        emit(
            f"[MISSING] {filename}"
        )


github_dir = PROJECT_ROOT / ".github"

if github_dir.exists():

    emit(
        "[PRESENT] .github/"
    )

    workflows = github_dir / "workflows"

    if workflows.exists():

        workflow_files = sorted(
            p
            for p in workflows.iterdir()
            if p.is_file()
        )

        emit(
            f"CI workflows : {len(workflow_files)}"
        )

        for path in workflow_files:
            emit(
                f"  {relative(path)}"
            )

    else:

        emit(
            "[WARNING] .github/workflows missing."
        )

else:

    emit(
        "[MISSING] .github/"
    )


# ==============================================================
# SENSITIVE FILES
# ==============================================================


section("13. POTENTIALLY SENSITIVE FILES")

sensitive_patterns = (
    ".env",
    ".pem",
    ".key",
    "credentials",
    "secret",
    "token",
    "password",
    "api_key",
    "apikey",
)

sensitive = []

for path in all_files:

    name = path.name.lower()

    if any(
        pattern in name
        for pattern in sensitive_patterns
    ):

        sensitive.append(
            relative(path)
        )

if sensitive:

    for path in sensitive:
        emit(
            f"[WARNING] {path}"
        )

else:

    emit(
        "[PASS] No obvious sensitive filenames detected."
    )


# ==============================================================
# GITIGNORE
# ==============================================================


section("14. GITIGNORE AUDIT")

gitignore = PROJECT_ROOT / ".gitignore"

if gitignore.exists():

    emit(
        "[PASS] .gitignore exists."
    )

    content = gitignore.read_text(
        encoding="utf-8",
        errors="replace",
    )

    important_patterns = (
        ".env",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
    )

    for pattern in important_patterns:

        if pattern in content:

            emit(
                f"[PASS] .gitignore contains {pattern}"
            )

        else:

            emit(
                f"[WARNING] .gitignore missing {pattern}"
            )

else:

    emit(
        "[FAIL] .gitignore is missing."
    )


# ==============================================================
# EXACT DIFF STATISTICS
# ==============================================================


section("15. WORKING TREE DIFF STATISTICS")

diff_stat = run_git(
    "diff",
    "--stat",
)

emit(
    diff_stat
    or "[No unstaged tracked-file diff.]"
)


# ==============================================================
# EXACT MODIFIED SOURCE DIFF
# ==============================================================


section("16. MODIFIED TRACKED SOURCE DIFF")

diff = run_git(
    "diff",
    "--",
)

if diff:

    emit(diff)

else:

    emit(
        "[No unstaged tracked-file diff.]"
    )


# ==============================================================
# UNTRACKED SOURCE METADATA
# ==============================================================


section("17. UNTRACKED SOURCE METADATA")

for path_string in untracked:

    path = PROJECT_ROOT / path_string

    if not path.exists():
        continue

    emit(
        f"{path_string}"
    )

    emit(
        f"  category : {classify_file(path_string)}"
    )

    emit(
        f"  size     : {file_size(path)} bytes"
    )

    emit(
        f"  sha256   : {sha256(path)}"
    )


# ==============================================================
# RECENT HISTORY
# ==============================================================


section("18. RECENT COMMIT HISTORY")

history = run_git(
    "log",
    "-15",
    "--date=short",
    "--format=%h | %ad | %an | %s",
)

emit(history)


# ==============================================================
# SOURCE SNAPSHOT / REGISTRY CHECKS
# ==============================================================


section("19. CANONICAL PROJECT SOURCE / REGISTRY PRESENCE")

required_reference_files = (
    "MODULE_REGISTRY.md",
    "complete_project_source.txt",
    "SYSTEM_INVENTORY_AND_DEPLOYMENT_READINESS.md",
)

for filename in required_reference_files:

    path = PROJECT_ROOT / filename

    if path.exists():

        emit(
            f"[PRESENT] {filename}"
        )

    else:

        emit(
            f"[MISSING] {filename}"
        )


# ==============================================================
# POTENTIAL DUPLICATES
# ==============================================================


section("20. POTENTIAL DUPLICATE / VARIANT FILES")

groups: dict[str, list[str]] = {}

for path in all_files:

    stem = path.stem.lower()

    normalized = re.sub(
        r"\(\d+\)$",
        "",
        stem,
    )

    normalized = re.sub(
        r"[_-](updated|final|backup|copy)$",
        "",
        normalized,
    )

    groups.setdefault(
        normalized,
        [],
    ).append(
        relative(path)
    )

duplicates = {
    key: values
    for key, values in groups.items()
    if len(values) > 1
}

if duplicates:

    for key in sorted(duplicates):

        emit(
            f"{key}:"
        )

        for value in sorted(
            duplicates[key]
        ):

            emit(
                f"  {value}"
            )

else:

    emit(
        "[PASS] No obvious duplicate groups detected."
    )


# ==============================================================
# DISPOSITION RECOMMENDATIONS
# ==============================================================


section("21. PRELIMINARY FILE DISPOSITION")

for path in sorted(untracked):

    category = classify_file(path)

    if category == "PYTHON SOURCE":

        recommendation = (
            "REVIEW FOR PRODUCTION / TEST INTEGRATION"
        )

    elif category == "TEST":

        recommendation = (
            "REVIEW FOR REGRESSION SUITE INCLUSION"
        )

    elif category in {
        "PROJECT REGISTRY",
        "SYSTEM INVENTORY",
        "PROJECT SOURCE SNAPSHOT",
    }:

        recommendation = (
            "RECONCILE WITH CANONICAL DOCUMENTATION"
        )

    elif category == "SENSITIVE / ENVIRONMENT":

        recommendation = (
            "DO NOT COMMIT — VERIFY IGNORE RULE"
        )

    elif category in {
        "BACKUP / RECOVERY ARTIFACT",
        "PATCH / PROVENANCE ARTIFACT",
        "DIFF / PROVENANCE ARTIFACT",
        "PHASE 1 WORKING ARTIFACT",
        "REGRESSION ARTIFACT",
        "ARCHIVE",
    }:

        recommendation = (
            "PROVENANCE REVIEW — DO NOT COMMIT BLINDLY"
        )

    else:

        recommendation = (
            "MANUAL REVIEW REQUIRED"
        )

    emit(
        f"{path:<60} | {recommendation}"
    )


# ==============================================================
# PHASE 1A ASSESSMENT
# ==============================================================


section("22. PHASE 1A PRELIMINARY ASSESSMENT")

conditions = {
    "Git repository valid":
        bool(git_root),

    "Origin configured":
        bool(origin_url),

    "Named branch":
        bool(branch),

    "Upstream configured":
        bool(upstream),

    "Working tree currently clean":
        not bool(status_entries),

    "No staged changes":
        not bool(staged),

    "Canonical registry present":
        (PROJECT_ROOT / "MODULE_REGISTRY.md").exists(),

    "System inventory present":
        (
            PROJECT_ROOT
            / "SYSTEM_INVENTORY_AND_DEPLOYMENT_READINESS.md"
        ).exists(),

    "Project source snapshot present":
        (
            PROJECT_ROOT
            / "complete_project_source.txt"
        ).exists(),

    "pyproject.toml present":
        (PROJECT_ROOT / "pyproject.toml").exists(),

    "requirements.txt present":
        (PROJECT_ROOT / "requirements.txt").exists(),

    "GitHub CI directory present":
        (PROJECT_ROOT / ".github").exists(),
}

for name, passed in conditions.items():

    emit(
        f"[{'PASS' if passed else 'PENDING'}] {name}"
    )


emit()
emit(
    "IMPORTANT:"
)
emit(
    "This audit is READ-ONLY."
)
emit(
    "No Git state was modified."
)
emit(
    "No files were staged, committed, deleted, renamed, "
    "reset, or pushed."
)


# ==============================================================
# NEXT ACTION
# ==============================================================


section("23. PHASE 1A NEXT ACTION")

emit(
    "Review this report before making repository changes."
)

emit(
    "The next reconciliation targets are:"
)

emit(
    "1. Modified tracked source files"
)

emit(
    "2. New authorized-execution modules"
)

emit(
    "3. Module registry variants"
)

emit(
    "4. Complete project source variants"
)

emit(
    "5. Backup and patch provenance"
)

emit(
    "6. System inventory"
)

emit(
    "7. Full-system regression evidence"
)

emit(
    "8. Git commit boundary"
)


# ==============================================================
# WRITE REPORT
# ==============================================================


report_path = PROJECT_ROOT / REPORT_NAME

report_path.write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8",
)

print()
print("=" * 76)
print(
    f"REPORT WRITTEN: {report_path}"
)
print("=" * 76)