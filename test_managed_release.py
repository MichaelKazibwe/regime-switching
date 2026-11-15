import os
from pathlib import Path
import subprocess
import sys
import pytest
from managed_release import stage
from paper_release import verify


def test_managed_candidate_is_complete_minimal_and_nonexecuting(tmp_path):
    root = Path(__file__).resolve().parent
    output = tmp_path / "candidate"
    manifest = stage(root, output, allow_dirty=True)
    verify(output, manifest)
    assert manifest["qualification"] == (
        "RELEASE_SOURCE" if manifest["clean_commit"] else "CANDIDATE"
    )
    for file in (
        "managed_positions.py",
        "managed_execution.py",
        "managed_api.py",
        "Dockerfile.managed-paper",
    ):
        assert file in manifest["files"]
    assert not any(p.startswith((".env", "var/", ".git/")) for p in manifest["files"])
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(output)}
    result = subprocess.run(
        [sys.executable, "-B", "managed_release.py", "inspect", "--root", str(output)],
        cwd=output,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert '"execution_enabled": false' in result.stdout
    subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "import managed_api, managed_execution, managed_positions, managed_transport, managed_evidence, live_p1_service, live_p1_runner",
        ],
        cwd=output,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    verify(output, manifest)
    (output / "managed_positions.py").write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        verify(output, manifest)
