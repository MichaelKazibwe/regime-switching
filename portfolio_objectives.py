"""Current owner policy. Historical snapshots retain their original mandates."""

POLICY_VERSION = "GROWTH_RESILIENCE_V1"
FIXED_RETURN_TARGET = None
MAX_ACCOUNT_DRAWDOWN = None


def drawdown_factor(drawdown, start=None, lock=None, *, locked=False):
    if locked:
        return 0.0
    if start is None and lock is None:
        return 1.0
    import numpy as np

    if start is None or lock is None or not 0 < start < lock < 1:
        raise ValueError("Both explicit legacy drawdown thresholds required")
    return float(np.clip((lock + drawdown) / (lock - start), 0, 1))
