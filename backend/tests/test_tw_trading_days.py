from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from market.collectors import yahoo
from market.db import init_db, make_engine, upsert
from market.jobs import daily
from market.models import Price


def _ohlcv(rows):
    idx = pd.DatetimeIndex([d for d, _, _ in rows])
    return pd.DataFrame(
        {"Open": [c for _, c, _ in rows], "High": [c for _, c, _ in rows], "Low": [c for _, c, _ in rows],
         "Close": [c for _, c, _ in rows], "Volume": [v for _, _, v in rows]},
        index=idx,
    )


def test_drop_non_trading_days_removes_zero_volume_rows():
    df = _ohlcv([("2026-10-22", 100.0, 5e6), ("2026-10-23", 100.0, 0.0), ("2026-10-26", 101.0, 4e6)])
    out = yahoo.drop_non_trading_days(df)
    assert [d.date().isoformat() for d in out.index] == ["2026-10-22", "2026-10-26"]


def test_update_prices_drops_tw_holidays_and_cleans_stored_ones(tmp_path, monkeypatch):
    eng = make_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(eng)
    monkeypatch.setattr(daily, "TARGETS", {"X": {"index": "2330.TW"}, "Y": {"index": "^TWII"}})
    monkeypatch.setattr(daily, "EXTRA_PRICE_SYMBOLS", [])
    monkeypatch.setattr(daily, "TWSE_PRICES", {})  # test the Yahoo path for a TW-listed symbol
    fetched = {
        "2330.TW": _ohlcv([("2026-10-22", 2400.0, 3e7), ("2026-10-23", 2400.0, 0.0), ("2026-10-26", 2390.0, 2e7)]),
        # Indices report no volume at all: zero volume must NOT be read as "closed" here.
        "^TWII": _ohlcv([("2026-10-22", 40000.0, 0.0), ("2026-10-26", 40100.0, 0.0)]),
    }
    monkeypatch.setattr(daily.yahoo, "fetch_history", lambda sym, start: fetched[sym])

    with Session(eng) as session:
        # A phantom holiday row stored by an earlier version must be cleaned up too.
        upsert(session, Price, [{"symbol": "2330.TW", "date": date(2026, 10, 9), "close": 2300.0, "volume": 0.0}])
        daily.update_prices(session, full=False)
        rows = session.execute(select(Price.symbol, Price.date).order_by(Price.symbol, Price.date)).all()

    by_symbol = {}
    for sym, d in rows:
        by_symbol.setdefault(sym, []).append(d.isoformat())
    assert by_symbol["2330.TW"] == ["2026-10-22", "2026-10-26"]
    assert by_symbol["^TWII"] == ["2026-10-22", "2026-10-26"]
