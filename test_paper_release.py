import json
from pathlib import Path
import subprocess
import os
import sys

import pytest

import paper_release
from lock_paper_dependencies import hash_lock


def test_real_staged_paper_context_imports_without_repository_data(tmp_path):
    root = Path(__file__).resolve().parent
    target = tmp_path / "paper"
    document = paper_release.stage(root, target, allow_dirty=True)
    assert "research/global_asset_registry.json" in document["files"]
    subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "import paper_service,paper_admin,paper_backup,paper_qualification,paper_dashboard_server,monthlyreport,monthlydelivery",
        ],
        cwd=target,
        env={**os.environ, "PYTHONPATH": str(target)},
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir()
    (root / "entry.py").write_text("import dependency\n")
    (root / "dependency.py").write_text("VALUE = 1\n")
    (root / "entry_backup.py").write_text("BROKEN = True\n")
    (root / "private.env").write_text("DO_NOT_SHIP=secret\n")
    (root / "deploy").mkdir()
    (root / "deploy" / "private.env").write_text("DO_NOT_SHIP=secret\n")
    monkeypatch.setattr(paper_release, "ENTRIES", ("entry",))
    monkeypatch.setattr(paper_release, "RESOURCES", ())
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Release Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "Fixture",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return root


def test_stage_import_closure_excludes_backups_and_secrets(source, tmp_path):
    target = tmp_path / "release"
    document = paper_release.stage(source, target)
    assert document["clean_commit"] is True
    assert set(document["files"]) == {"entry.py", "dependency.py"}
    paper_release.verify(target, document)
    with pytest.raises(ValueError, match="must not exist"):
        paper_release.stage(source, target)


def test_dirty_candidate_cannot_masquerade_as_clean_release(source, tmp_path):
    (source / "dependency.py").write_text("VALUE = 2\n")
    with pytest.raises(ValueError, match="clean reviewed commit"):
        paper_release.manifest(source)
    candidate = paper_release.stage(source, tmp_path / "candidate", allow_dirty=True)
    assert candidate["clean_commit"] is False
    assert candidate["qualification"] == "CANDIDATE"
    forged = {**candidate, "clean_commit": True}
    with pytest.raises(ValueError, match="identity mismatch"):
        paper_release.verify(tmp_path / "candidate", forged)
    from paper_qualification import assess

    assessment = assess(
        tmp_path / "candidate",
        tmp_path / "evidence",
        tmp_path / "reports",
        tmp_path / "missing.sqlite3",
    )
    assert assessment["checks"]["clean_release"] == "BLOCKED"
    assert assessment["paper_operations"] == "BLOCKED"


def test_release_rejects_tampering_extra_files_and_symlinks(source, tmp_path):
    target = tmp_path / "release"
    document = paper_release.stage(source, target)
    (target / "dependency.py").write_text("VALUE = 3\n")
    with pytest.raises(ValueError, match="changed"):
        paper_release.verify(target, document)
    (target / "dependency.py").write_bytes((source / "dependency.py").read_bytes())
    (target / "unexpected.env").write_text("unexpected")
    with pytest.raises(ValueError, match="unlisted"):
        paper_release.verify(target, document)
    (target / "unexpected.env").unlink()
    (target / "dependency.py").unlink()
    (target / "dependency.py").symlink_to(source / "dependency.py")
    with pytest.raises(ValueError):
        paper_release.verify(target, document)


def test_hashed_locks_match_exact_pins_and_require_all_hashes():
    root = Path(__file__).resolve().parent
    for name in ("paper", "dev"):
        plain = (root / f"requirements-{name}.lock").read_text()
        hashed = (root / f"requirements-{name}.hashed.lock").read_text()
        expected = {
            line.strip()
            for line in plain.splitlines()
            if line.strip() and not line.startswith(("#", "-r"))
        }
        actual = set()
        for line in hashed.replace("\\\n", " ").splitlines():
            if not line or line.startswith(("#", "-r")):
                continue
            tokens = line.split()
            actual.add(tokens[0])
            assert len(tokens) > 1
            assert all(
                token.startswith("--hash=sha256:") and len(token) == 78
                for token in tokens[1:]
            )
        assert actual == expected
    assert (
        "-r requirements-paper.hashed.lock"
        in (root / "requirements-dev.hashed.lock").read_text()
    )


def test_lock_generation_fails_closed_on_yanked_or_invalid_metadata(tmp_path):
    path = tmp_path / "requirements.lock"
    path.write_text("example==1.0\n")
    good = {"info": {"version": "1.0"}, "urls": [{"digests": {"sha256": "a" * 64}}]}
    assert "--hash=sha256:" + "a" * 64 in hash_lock(path, fetch=lambda *_: good)
    bad = json.loads(json.dumps(good))
    bad["urls"][0]["yanked"] = True
    with pytest.raises(ValueError, match="No valid"):
        hash_lock(path, fetch=lambda *_: bad)
