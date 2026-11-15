from pathlib import Path

import pytest

from product_build import stage
from paper_release import verify


def test_product_stage_has_import_closure_and_no_private_artifacts(tmp_path):
    destination = tmp_path / "context"
    manifest = stage(Path.cwd(), destination, allow_dirty=True)
    verify(destination, manifest)
    assert {
        "productstate.py",
        "product_smoke.py",
        "recommendation_api.py",
        "macro_feature_contract.py",
    } <= set(manifest["files"])
    assert not any(
        name.startswith(("var/", ".env", ".aws/", "test_"))
        for name in manifest["files"]
    )
    assert manifest["qualification"] == (
        "RELEASE_SOURCE" if manifest["clean_commit"] else "CANDIDATE"
    )
    (destination / "productstate.py").write_text("tampered")
    with pytest.raises(ValueError):
        verify(destination, manifest)
