"""Bounded child process tree: a timed-out worker cannot keep writing ledgers."""

import os
import signal
import subprocess


def install_cancellation():
    def cancel(*_):
        raise InterruptedError("Observation worker cancelled")

    signal.signal(signal.SIGTERM, cancel)


def run_bounded(command, *, cwd, stdout, stderr, timeout):
    with subprocess.Popen(
        command, cwd=cwd, stdout=stdout, stderr=stderr, start_new_session=True
    ) as child:
        try:
            code = child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
            raise
        except BaseException:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
            raise
    return subprocess.CompletedProcess(command, code)
