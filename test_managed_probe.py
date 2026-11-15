import json
import pytest
from managed_probe import capture
from test_ibkr_paper_probe import Reader


def config(tmp_path):
    p = tmp_path / "private.json"
    p.write_text(
        json.dumps(dict(tenant="TEST", paper_account="DU123", gateway_ca_file=None))
    )
    p.chmod(0o600)
    return p


def test_private_capture_is_hashed_but_never_observation_or_order_authority(tmp_path):
    p = config(tmp_path)
    receipt, root = capture(
        p, tmp_path / "captures", reader_factory=lambda **_: Reader()
    )
    assert receipt["status"] == "READ_ONLY_PAPER_CAPTURE_UNQUALIFIED"
    assert receipt["counts_as_performance_observation"] is False
    assert not receipt["execution_enabled"]
    assert (root / "account.json").stat().st_mode & 0o077 == 0


def test_connectivity_failure_does_not_become_account_capture(tmp_path):
    class Offline:
        def get(self, _):
            raise TimeoutError("TEST ONLY - DO NOT LOG PRIVATE DETAILS")

    receipt, root = capture(
        config(tmp_path), tmp_path / "captures", reader_factory=lambda **_: Offline()
    )
    assert receipt["status"] == "BLOCKED" and receipt["reason"] == "TimeoutError"
    assert not (root / "account.json").exists()
    assert "PRIVATE" not in (root / "receipt.json").read_text()


def test_world_readable_configuration_denied(tmp_path):
    p = config(tmp_path)
    p.chmod(0o644)
    with pytest.raises(PermissionError):
        capture(p, tmp_path / "captures")
