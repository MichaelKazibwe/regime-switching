"""Quiesce registered host research writers without changing their schedules."""

from contextlib import contextmanager, ExitStack
from pathlib import Path
import fcntl
import os
import time


WRITER_LOCKS = (
    "pilot-pipeline/pipeline.lock",
    "local-observation-scheduler/tick.lock",
    "live-observation-cycle/cycle.lock",
    "strategy-operations-integrated-v1/job.lock",
    "institutional-return-engines/cycle.lock",
    "dashboard-live/publication.lock",
    "daily-alpha-training/training.lock",
    "pilot-daily/publish.lock",
    "weekly-portfolios/worker.lock",
    "macro-alpha/monitor.lock",
)


@contextmanager
def quiesce(root, *, timeout=30):
    """Acquire every existing writer protocol before allowing a snapshot.

    Acquisition is nonblocking and releases partial sets before retrying. This
    avoids inversion with nested pipeline/job locks. These are the registered
    scheduler entry points, not a lock against arbitrary external file edits.
    """
    if not 0 <= timeout <= 120:
        raise ValueError("Bounded snapshot lock timeout required")
    root = Path(root).resolve()
    deadline = time.monotonic() + timeout
    while True:
        stack = ExitStack()
        try:
            for relative in sorted(WRITER_LOCKS):
                path = root / "var" / relative
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                stream = stack.enter_context(path.open("a"))
                os.fchmod(stream.fileno(), 0o600)
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            stack.close()
            if time.monotonic() >= deadline:
                raise TimeoutError("Registered research writer is active; snapshot not started") from None
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        except BaseException:
            stack.close()
            raise
        else:
            try:
                yield tuple(str(root / "var" / name) for name in WRITER_LOCKS)
            finally:
                stack.close()
            return
