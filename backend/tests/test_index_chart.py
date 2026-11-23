import pandas as pd
from fastapi.testclient import TestClient

from market.api import main


class FakeStore:
    def __init__(self, close: pd.Series):
        self._close = close

    def close(self, symbol: str) -> pd.Series:
        return self._close


def _client(monkeypatch, n_days: int) -> TestClient:
    monkeypatch.setattr(main, "MA_WINDOWS", (2, 3))
    close = pd.Series(range(1, n_days + 1), index=pd.bdate_range("2020-01-01", periods=n_days), dtype=float)
    main.app.dependency_overrides[main.get_store] = lambda: FakeStore(close)
    return TestClient(main.app)  # no `with`: skip lifespan (scheduler, DB)


def test_index_chart_averages_use_history_before_range(monkeypatch):
    try:
        r = _client(monkeypatch, 10).get("/api/indices/SPX/chart?from=2020-01-06").json()
    finally:
        main.app.dependency_overrides.clear()
    assert r["interval"] == "daily"
    assert r["price"][0] == ["2020-01-06", 4.0]
    ma2 = next(m for m in r["moving_averages"] if m["window"] == 2)
    assert ma2["points"][0] == ["2020-01-06", 3.5]  # mean(3, 4): uses the day before the range


def test_index_chart_long_range_is_weekly_and_keeps_real_last_date(monkeypatch):
    monkeypatch.setattr(main, "_CHART_MAX_DAILY_POINTS", 5)
    try:
        r = _client(monkeypatch, 13).get("/api/indices/SPX/chart").json()
    finally:
        main.app.dependency_overrides.clear()
    assert r["interval"] == "weekly"
    dates = [d for d, _ in r["price"]]
    assert dates[-1] == pd.bdate_range("2020-01-01", periods=13)[-1].date().isoformat()
    assert len(dates) == len(set(pd.to_datetime(dates).to_period("W-FRI")))  # one point per week


def test_index_chart_unknown_target():
    assert TestClient(main.app).get("/api/indices/NOPE/chart").status_code == 404
