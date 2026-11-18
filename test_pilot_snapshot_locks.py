"""A coherent snapshot must exclude actual registered writer lock holders."""

import fcntl
import pytest
from pilot_snapshot_locks import WRITER_LOCKS, quiesce


def test_busy_writer_rejects_snapshot_and_releases_partial_locks(tmp_path):
    busy = tmp_path / "var" / WRITER_LOCKS[-1]
    busy.parent.mkdir(parents=True)
    with busy.open("a") as writer:
        fcntl.flock(writer, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(TimeoutError), quiesce(tmp_path, timeout=0):
            pytest.fail("Snapshot started with an active writer")
    with quiesce(tmp_path, timeout=0) as held:
        assert len(held) == len(WRITER_LOCKS)
        for path in held:
            with open(path, "a") as competing_writer:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(competing_writer, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_failure_releases_all_writers(tmp_path):
    with pytest.raises(RuntimeError), quiesce(tmp_path, timeout=0):
        raise RuntimeError("Export failed")
    with quiesce(tmp_path, timeout=0):
        pass


@pytest.mark.parametrize("timeout", [-1, 121])
def test_unbounded_lock_wait_rejected(tmp_path, timeout):
    with pytest.raises(ValueError), quiesce(tmp_path, timeout=timeout):
        pytest.fail("Invalid wait accepted")
