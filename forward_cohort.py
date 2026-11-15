"""Explicit local cohort selection; historical ledgers are never rewritten."""

from pathlib import Path
from strategy_integrity import strict_json


def database(operations):
    root = Path(operations)
    pointer = root / "active-cohort.json"
    if not pointer.exists():
        return root / "prospective.sqlite3"
    record = strict_json(pointer)
    name = record["database"]
    if (not isinstance(name, str) or Path(name).name != name
            or not name.startswith("prospective-") or not name.endswith(".sqlite3")
            or record.get("execution_enabled") is not False
            or record.get("promotion_enabled") is not False):
        raise ValueError("Invalid forward cohort selection")
    return root / name
