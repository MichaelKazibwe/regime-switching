import pandas as pd
import pytest

from macrovintage import MacroVintageData


def test_vintage_selection_never_leaks_revision_or_same_day_release(tmp_path):
    data = MacroVintageData(pd.DataFrame([
        {"date": "2026-01-01", "realtime_start": "2026-02-06", "value": 4.0},
        {"date": "2026-01-01", "realtime_start": "2026-03-06", "value": 4.2},
    ]))
    assert data.as_of("2026-02-06T23:00:00-05:00").empty
    assert data.as_of("2026-02-07T00:00:00-05:00").iloc[-1] == 4.0
    assert data.as_of("2026-03-06T23:59:00-05:00").iloc[-1] == 4.0
    assert data.as_of("2026-03-07T00:00:00-05:00").iloc[-1] == 4.2
    manifest = data.freeze(tmp_path / "vintages.csv")
    restored = MacroVintageData.from_csv(tmp_path / "vintages.csv", expected_sha256=manifest["sha256"])
    assert restored.as_of("2026-03-07T00:00:00-05:00").iloc[-1] == 4.2
    with pytest.raises(ValueError, match="timezone-aware"):
        data.as_of("2026-03-07")
    with pytest.raises(ValueError, match="checksum"):
        MacroVintageData.from_csv(tmp_path / "vintages.csv", expected_sha256="0" * 64)


def test_vintage_rejects_duplicate_or_future_observation():
    row = {"date": "2026-01-01", "realtime_start": "2026-02-06", "value": 4}
    with pytest.raises(ValueError, match="Duplicate"):
        MacroVintageData(pd.DataFrame([row, row]))
    with pytest.raises(ValueError, match="cannot follow"):
        MacroVintageData(pd.DataFrame([{**row, "date": "2026-03-01"}]))
