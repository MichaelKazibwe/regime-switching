#!/usr/bin/env python3
"""
================================================================
git_status_audit.py

Phase 1 — Repository Reconciliation
Read-only Git repository inspection.

This script DOES NOT:
    - modify files
    - stage files
    - commit files
    - checkout branches
    - pull
    - push
    - reset
    - clean
    - amend commits

It reports:
    1. Repository location
    2. Git availability
    3. Repository validity
    4. Current branch
    5. HEAD commit
    6. Remote configuration
    7. Working-tree status
    8. Staged changes
    9. Unstaged changes
    10. Untracked files
    11. Ignored files
    12. Ahead/behind status
    13. Recent commit history
    14. Repository statistics
    15. Potential sensitive files
    16. Dependency/configuration files
    17. GitHub readiness indicators

Exit codes:
    0 = repository is healthy enough for inspection
    1 = repository not found / invalid / command failure

================================================================
"""

from __future__ import annotations

import os
import shutil
import subprocess

from pathlib import Path
from typing import Sequence


# ==============================================================
# CONFIGURATION
# ==============================================================

PROJECT_ROOT = Path.cwd()

SENSITIVE_PATTERNS = (
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "credentials.json",
    "secrets.json",
    "secret.json",
    "service-account.json",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
)

IMPORTANT_PROJECT_FILES = (
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-test.txt",
    "setup.py",
    "setup.cfg",
    "Pipfile",
    "Pipfile.lock",
    "poetry.lock",
    "uv.lock",
    "environment.yml",
    "environment.yaml",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".gitignore",
    ".gitattributes",
    ".github",
    "README.md",
    "LICENSE",
)


# ==============================================================
# OUTPUT HELPERS
# ==============================================================


def header(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def section(title: str) -> None:
    print()
    print(f"--- {title} ---")


def line(label: str, value: object) -> None:
    print(f"{label:<28}: {value}")


def warning(message: str) -> None:
    print(f"[WARNING] {message}")


def success(message: str) -> None:
    print(f"[PASS] {message}")


def failure(message: str) -> None:
    print(f"[FAIL] {message}")


# ==============================================================
# GIT COMMAND EXECUTION
# ==============================================================


def run_git(
    args: Sequence[str],
    *,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """
    Execute a Git command without modifying repository state.
    """

    return subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=check,
    )


def git_output(
    args: Sequence[str],
) -> str:
    """
    Return stripped Git command output.
    """

    result = run_git(args)

    if result.returncode != 0:
        return ""

    return result.stdout.strip()


# ==============================================================
# BASIC ENVIRONMENT
# ==============================================================


def inspect_environment() -> bool:
    header("PHASE 1 — GIT REPOSITORY AUDIT")

    line(
        "Project root",
        PROJECT_ROOT.resolve(),
    )

    git_path = shutil.which("git")

    if git_path is None:
        failure("Git executable was not found on PATH.")
        return False

    success(f"Git executable found: {git_path}")

    version = git_output(["--version"])

    line(
        "Git version",
        version or "UNKNOWN",
    )

    return True


# ==============================================================
# REPOSITORY VALIDITY
# ==============================================================


def inspect_repository() -> bool:
    section("REPOSITORY VALIDITY")

    result = run_git(
        [
            "rev-parse",
            "--show-toplevel",
        ]
    )

    if result.returncode != 0:
        failure(
            "Current directory is not a valid Git repository."
        )

        if result.stderr.strip():
            print(
                f"Git error: {result.stderr.strip()}"
            )

        return False

    repo_root = Path(
        result.stdout.strip()
    ).resolve()

    line(
        "Git repository root",
        repo_root,
    )

    git_dir = git_output(
        ["rev-parse", "--git-dir"]
    )

    line(
        "Git directory",
        git_dir or "UNKNOWN",
    )

    bare = git_output(
        ["rev-parse", "--is-bare-repository"]
    )

    line(
        "Bare repository",
        bare or "UNKNOWN",
    )

    if bare == "true":
        failure(
            "Repository is bare; working-tree inspection is unavailable."
        )
        return False

    success("Valid non-bare Git repository detected.")

    return True


# ==============================================================
# BRANCH
# ==============================================================


def inspect_branch() -> None:
    section("CURRENT BRANCH")

    branch = git_output(
        ["branch", "--show-current"]
    )

    if not branch:
        branch = "(DETACHED HEAD)"

    line(
        "Current branch",
        branch,
    )

    head = git_output(
        [
            "rev-parse",
            "--short",
            "HEAD",
        ]
    )

    line(
        "HEAD",
        head or "NO COMMITS",
    )

    symbolic = git_output(
        [
            "symbolic-ref",
            "--short",
            "-q",
            "HEAD",
        ]
    )

    line(
        "Symbolic HEAD",
        symbolic or "DETACHED",
    )


# ==============================================================
# HEAD COMMIT
# ==============================================================


def inspect_head() -> None:
    section("HEAD COMMIT")

    if not git_output(["rev-parse", "HEAD"]):
        warning("Repository contains no commits.")
        return

    commit_hash = git_output(
        [
            "rev-parse",
            "HEAD",
        ]
    )

    short_hash = git_output(
        [
            "rev-parse",
            "--short",
            "HEAD",
        ]
    )

    subject = git_output(
        [
            "log",
            "-1",
            "--pretty=%s",
        ]
    )

    author = git_output(
        [
            "log",
            "-1",
            "--pretty=%an <%ae>",
        ]
    )

    date = git_output(
        [
            "log",
            "-1",
            "--pretty=%aI",
        ]
    )

    line("Full commit", commit_hash or "UNKNOWN")
    line("Short commit", short_hash or "UNKNOWN")
    line("Subject", subject or "UNKNOWN")
    line("Author", author or "UNKNOWN")
    line("Author date", date or "UNKNOWN")


# ==============================================================
# REMOTES
# ==============================================================


def inspect_remotes() -> None:
    section("REMOTE CONFIGURATION")

    remotes = run_git(
        [
            "remote",
            "-v",
        ]
    )

    if remotes.returncode != 0:
        warning("Unable to inspect Git remotes.")
        return

    output = remotes.stdout.strip()

    if not output:
        warning(
            "No Git remotes are configured."
        )
        return

    print(output)

    origin = git_output(
        [
            "remote",
            "get-url",
            "origin",
        ]
    )

    if origin:
        line(
            "Origin URL",
            origin,
        )
        success("Git origin is configured.")
    else:
        warning(
            "No 'origin' remote is configured."
        )


# ==============================================================
# WORKING TREE STATUS
# ==============================================================


def inspect_status() -> None:
    section("WORKING TREE STATUS")

    result = run_git(
        [
            "status",
            "--short",
            "--branch",
        ]
    )

    if result.returncode != 0:
        failure(
            "Unable to obtain Git working-tree status."
        )
        return

    output = result.stdout.strip()

    if not output:
        success("Working tree is clean.")
        return

    print(output)


# ==============================================================
# STATUS COUNTS
# ==============================================================


def inspect_status_counts() -> None:
    section("STATUS COUNTS")

    result = run_git(
        [
            "status",
            "--porcelain",
        ]
    )

    if result.returncode != 0:
        warning(
            "Unable to calculate status counts."
        )
        return

    staged = 0
    unstaged = 0
    untracked = 0

    for raw_line in result.stdout.splitlines():

        if len(raw_line) < 2:
            continue

        x = raw_line[0]
        y = raw_line[1]

        if x == "?":
            untracked += 1
            continue

        if x != " ":
            staged += 1

        if y != " ":
            unstaged += 1

    line(
        "Staged changes",
        staged,
    )

    line(
        "Unstaged changes",
        unstaged,
    )

    line(
        "Untracked files",
        untracked,
    )


# ==============================================================
# AHEAD / BEHIND
# ==============================================================


def inspect_tracking() -> None:
    section("REMOTE TRACKING / AHEAD-BEHIND")

    upstream = git_output(
        [
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ]
    )

    if not upstream:
        warning(
            "Current branch has no configured upstream."
        )
        return

    line(
        "Upstream",
        upstream,
    )

    ahead = git_output(
        [
            "rev-list",
            "--count",
            f"{upstream}..HEAD",
        ]
    )

    behind = git_output(
        [
            "rev-list",
            "--count",
            f"HEAD..{upstream}",
        ]
    )

    line(
        "Commits ahead",
        ahead or "0",
    )

    line(
        "Commits behind",
        behind or "0",
    )

    if ahead == "0" and behind == "0":
        success(
            "Local branch is synchronized with upstream."
        )
    else:
        warning(
            "Local branch and upstream are not synchronized."
        )


# ==============================================================
# RECENT HISTORY
# ==============================================================


def inspect_history() -> None:
    section("RECENT COMMIT HISTORY")

    result = run_git(
        [
            "log",
            "-10",
            "--date=short",
            "--pretty=format:%h | %ad | %an | %s",
        ]
    )

    if result.returncode != 0:
        warning(
            "Unable to inspect commit history."
        )
        return

    output = result.stdout.strip()

    if output:
        print(output)
    else:
        warning(
            "No commit history found."
        )


# ==============================================================
# FILE INVENTORY
# ==============================================================


def inspect_tracked_files() -> None:
    section("TRACKED FILE INVENTORY")

    result = run_git(
        [
            "ls-files",
        ]
    )

    if result.returncode != 0:
        warning(
            "Unable to inspect tracked files."
        )
        return

    files = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]

    line(
        "Tracked files",
        len(files),
    )

    python_files = [
        path
        for path in files
        if path.endswith(".py")
    ]

    line(
        "Tracked Python files",
        len(python_files),
    )

    print()

    for path in python_files:
        print(path)


# ==============================================================
# UNTRACKED FILES
# ==============================================================


def inspect_untracked() -> None:
    section("UNTRACKED FILES")

    result = run_git(
        [
            "ls-files",
            "--others",
            "--exclude-standard",
        ]
    )

    if result.returncode != 0:
        warning(
            "Unable to inspect untracked files."
        )
        return

    files = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]

    line(
        "Untracked files",
        len(files),
    )

    if not files:
        success(
            "No untracked files detected."
        )
        return

    for path in files:
        print(f"  {path}")


# ==============================================================
# IGNORED FILES
# ==============================================================


def inspect_ignored() -> None:
    section("IGNORED FILES")

    result = run_git(
        [
            "status",
            "--ignored",
            "--short",
        ]
    )

    if result.returncode != 0:
        warning(
            "Unable to inspect ignored files."
        )
        return

    ignored = []

    for line_value in result.stdout.splitlines():

        if line_value.startswith("!! "):
            ignored.append(
                line_value[3:]
            )

    line(
        "Ignored files",
        len(ignored),
    )

    if len(ignored) > 0:
        for path in ignored[:100]:
            print(f"  {path}")

        if len(ignored) > 100:
            print(
                f"  ... and {len(ignored) - 100} more"
            )


# ==============================================================
# PROJECT CONFIGURATION
# ==============================================================


def inspect_project_configuration() -> None:
    section("PROJECT CONFIGURATION")

    for name in IMPORTANT_PROJECT_FILES:

        path = PROJECT_ROOT / name

        if path.exists():

            if path.is_dir():
                marker = "[DIR]"
            else:
                marker = "[FILE]"

            print(
                f"{marker:<7} {name}"
            )

    print()

    found = [
        name
        for name in IMPORTANT_PROJECT_FILES
        if (PROJECT_ROOT / name).exists()
    ]

    line(
        "Important configuration entries",
        len(found),
    )

    if "pyproject.toml" not in found:
        warning(
            "pyproject.toml is missing."
        )

    if "requirements.txt" not in found:
        warning(
            "requirements.txt is missing."
        )

    if ".gitignore" not in found:
        warning(
            ".gitignore is missing."
        )

    if ".github" not in found:
        warning(
            ".github CI/CD directory is missing."
        )


# ==============================================================
# SENSITIVE FILE SCAN
# ==============================================================


def inspect_sensitive_files() -> None:
    section("POTENTIAL SENSITIVE FILES")

    candidates = []

    for root, dirs, files in os.walk(PROJECT_ROOT):

        # Do not inspect the Git internals.
        dirs[:] = [
            directory
            for directory in dirs
            if directory != ".git"
        ]

        for filename in files:

            relative = (
                Path(root)
                / filename
            ).relative_to(PROJECT_ROOT)

            lower = filename.lower()

            if (
                lower.startswith(".env")
                or lower.endswith(".pem")
                or lower.endswith(".key")
                or lower.endswith(".p12")
                or lower.endswith(".pfx")
                or lower in {
                    "credentials.json",
                    "secrets.json",
                    "secret.json",
                    "service-account.json",
                }
            ):
                candidates.append(
                    str(relative)
                )

    if not candidates:
        success(
            "No obvious sensitive filenames detected."
        )
        return

    warning(
        f"Potential sensitive files detected: {len(candidates)}"
    )

    for path in sorted(candidates):
        print(f"  {path}")


# ==============================================================
# GITHUB READINESS
# ==============================================================


def inspect_github_readiness() -> None:
    section("GITHUB READINESS INDICATORS")

    origin = git_output(
        [
            "remote",
            "get-url",
            "origin",
        ]
    )

    branch = git_output(
        [
            "branch",
            "--show-current",
        ]
    )

    gitignore = (
        PROJECT_ROOT / ".gitignore"
    ).exists()

    github_dir = (
        PROJECT_ROOT / ".github"
    ).exists()

    clean = not bool(
        git_output(
            [
                "status",
                "--porcelain",
            ]
        )
    )

    line(
        "Origin configured",
        bool(origin),
    )

    line(
        "Named branch",
        branch or "NO BRANCH",
    )

    line(
        ".gitignore present",
        gitignore,
    )

    line(
        ".github directory present",
        github_dir,
    )

    line(
        "Working tree clean",
        clean,
    )

    if origin and branch:
        success(
            "Basic GitHub repository identity exists."
        )
    else:
        warning(
            "Repository is not yet fully configured for GitHub release."
        )


# ==============================================================
# FINAL ASSESSMENT
# ==============================================================


def final_assessment() -> int:
    section("PHASE 1 PRELIMINARY ASSESSMENT")

    repo_check = run_git(
        [
            "rev-parse",
            "--is-inside-work-tree",
        ]
    )

    if repo_check.returncode != 0:
        failure(
            "NOT A VALID GIT WORKING TREE."
        )
        return 1

    origin = git_output(
        [
            "remote",
            "get-url",
            "origin",
        ]
    )

    branch = git_output(
        [
            "branch",
            "--show-current",
        ]
    )

    status = git_output(
        [
            "status",
            "--porcelain",
        ]
    )

    upstream = git_output(
        [
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ]
    )

    print()

    if not origin:
        warning(
            "ORIGIN REMOTE: NOT CONFIGURED"
        )
    else:
        success(
            "ORIGIN REMOTE: CONFIGURED"
        )

    if not branch:
        warning(
            "BRANCH: DETACHED HEAD"
        )
    else:
        success(
            f"BRANCH: {branch}"
        )

    if status:
        warning(
            "WORKING TREE: HAS CHANGES"
        )
    else:
        success(
            "WORKING TREE: CLEAN"
        )

    if upstream:
        success(
            f"UPSTREAM: {upstream}"
        )
    else:
        warning(
            "UPSTREAM: NOT CONFIGURED"
        )

    print()
    print(
        "IMPORTANT: This audit is READ-ONLY."
    )

    print(
        "No Git state was modified."
    )

    print()
    print(
        "Next Phase 1 action:"
    )

    print(
        "Compare this repository against the canonical "
        "project source snapshot and module registry."
    )

    return 0


# ==============================================================
# MAIN
# ==============================================================


def main() -> int:

    header(
        "REGIME SWITCHING SYSTEM — GIT STATUS AUDIT"
    )

    if not inspect_environment():
        return 1

    if not inspect_repository():
        return 1

    inspect_branch()
    inspect_head()
    inspect_remotes()
    inspect_status()
    inspect_status_counts()
    inspect_tracking()
    inspect_history()
    inspect_tracked_files()
    inspect_untracked()
    inspect_ignored()
    inspect_project_configuration()
    inspect_sensitive_files()
    inspect_github_readiness()

    return final_assessment()


if __name__ == "__main__":
    raise SystemExit(
        main()
    )