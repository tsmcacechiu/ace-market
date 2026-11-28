from types import SimpleNamespace

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from market.api import main


class FakeStore:
    session = None

    def __init__(self, close: pd.Series):
        self._close = close

    def close(self, symbol: str) -> pd.Series:
        return self._close

    def open(self, symbol: str) -> pd.Series:
        return self._close.shift()


def _close() -> pd.Series:
    up = list(100 * 1.001 ** np.arange(600))
    c = up + [up[-1] * 0.88] * 40 + [up[-1] * 1.1] * 300  # break, BEAR_200, reclaim, rally
    return pd.Series(c, index=pd.bdate_range("2000-01-03", periods=len(c)))


def test_strategy_endpoint(monkeypatch):
    monkeypatch.setattr(main, "_latest_job", lambda session: SimpleNamespace(id=1, status="ok", finished_at="t"))
    monkeypatch.setattr(main, "_strategy_cache", {})
    main.app.dependency_overrides[main.get_store] = lambda: FakeStore(_close())
    try:
        client = TestClient(main.app)
        r = client.get("/api/strategy/1/BTC").json()
        assert client.get("/api/strategy/1/NOPE").status_code == 404
    finally:
        main.app.dependency_overrides.clear()

    assert r["target"]["group"] == "其他" and r["params"]["window"] == 30
    assert r["regime"]["state"] == "BULL"
    assert [m[1] for m in r["markers"]] == ["BREAK_200", "BEAR_200", "RECLAIM_200"]
    assert r["segments"][0][2] == "BULL" and r["segments"][-1][2] == "BULL"
    assert r["events"][0]["kind"] == "RECLAIM_200"  # newest first
    assert r["stats"]["target"]["RECLAIM_200"]["count"] == 1
    assert r["stats"]["group"]["RECLAIM_200"]["count"] == 5  # every 其他 target sees the same fake series
    assert r["trades"]["list"][0]["kind"] == "RECLAIM_200"
    assert r["disclaimer"]


def test_strategy_overview(monkeypatch):
    up = list(100 * 1.001 ** np.arange(600))
    c = pd.Series(up + [up[-1] * 0.88] * 40, index=pd.bdate_range("2000-01-03", periods=640))
    monkeypatch.setattr(main, "_latest_job", lambda session: SimpleNamespace(id=1, status="ok", finished_at="t"))
    monkeypatch.setattr(main, "_strategy_cache", {})
    main.app.dependency_overrides[main.get_store] = lambda: FakeStore(c)
    try:
        r = TestClient(main.app).get("/api/strategy/overview").json()
    finally:
        main.app.dependency_overrides.clear()

    assert r["days"] == 90
    assert {t["id"] for t in r["targets"]} == set(main.TARGETS)
    spx = next(t for t in r["targets"] if t["id"] == "SPX")
    assert spx["group"] == "market" and spx["regime"]["state"] == "BEAR_200"
    assert "alerts" in spx["regime"]
    kinds = [(e["kind"], e["target"]) for e in r["events"] if e["target"] in ("SPX", "BTC")]
    assert ("BREAK_200", "SPX") in kinds and ("BEAR_200", "SPX") in kinds
    assert ("BEAR_200", "BTC") in kinds  # 30-day window still inside the 40 days shown
    dates = [e["date"] for e in r["events"]]
    assert dates == sorted(dates, reverse=True)
    assert all(e["label"] for e in r["events"])
