"""Compatibility entry point for the canonical regression suite.

R3B coverage (ATR/position sizing) is in REQUIRED_MODULES of regression_suite.
The canonical suite also retains the corrected annualized volatility check.
"""

import regression_suite as _canonical


def __getattr__(name):
    return getattr(_canonical, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_canonical)))


if __name__ == '__main__':
    raise SystemExit(_canonical.main())
