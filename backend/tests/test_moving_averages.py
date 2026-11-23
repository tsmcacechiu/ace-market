import pandas as pd
import pytest

from market.api.main import _moving_averages


def test_moving_averages(monkeypatch):
    monkeypatch.setattr("market.api.main.MA_WINDOWS", (2, 4, 10))
    close = pd.Series([1.0, 2.0, 3.0, 6.0], index=pd.date_range("2026-01-01", periods=4))
    got = {m["window"]: m for m in _moving_averages(close)}

    assert got[2]["value"] == pytest.approx(4.5)  # mean(3, 6)
    assert got[2]["deviation_pct"] == pytest.approx((6 / 4.5 - 1) * 100)
    assert got[4]["value"] == pytest.approx(3.0)
    assert got[4]["deviation_pct"] == pytest.approx(100.0)
    assert got[10] == {"window": 10, "value": None, "deviation_pct": None}  # not enough history
