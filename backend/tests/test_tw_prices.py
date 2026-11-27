import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from market import tw_prices
from market.collectors import twse
from market.db import init_db, make_engine
from market.jobs import daily
from market.models import Price
from market.tw_prices import PriceCheckError


def _raw(rows, split_days=()):
    """rows: [(date, close)] → raw TWSE frame (open/high/low = close)."""
    idx = pd.DatetimeIndex([d for d, _ in rows])
    c = [v for _, v in rows]
    df = pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": 1e6}, index=idx)
    df["split"] = [1.0 if d in split_days else 0.0 for d, _ in rows]
    return df


def _events(rows):
    return pd.DataFrame(
        [(pd.Timestamp(d), p, r) for d, p, r in rows], columns=["date", "prev_close", "ref"]
    )


NO_EVENTS = _events([])
NO_LEGACY = pd.DataFrame(columns=["open", "high", "low", "close", "volume"], dtype=float)


def test_cash_dividend_is_removed_from_older_prices():
    raw = _raw([("2022-06-21", 807.0), ("2022-06-22", 807.0), ("2022-06-23", 690.0)])
    # 2454-style: 73 cash dividend → reference 733.99. The raw -14.5% drop is not a real loss.
    out = tw_prices.build(raw, _events([("2022-06-23", 807.0, 733.99)]), [], NO_LEGACY, "2454")
    f = 733.99 / 807.0
    assert out["close"].tolist() == pytest.approx([807 * f, 807 * f, 690.0])
    assert out["close"].iloc[-1] == 690.0  # latest price stays the real traded price


def test_events_on_the_same_and_later_days_compound():
    raw = _raw([("2020-01-02", 100.0), ("2020-03-02", 100.0), ("2020-06-01", 100.0), ("2020-06-02", 100.0)])
    ev = _events([("2020-03-02", 100.0, 98.0), ("2020-06-01", 100.0, 95.0)])
    out = tw_prices.build(raw, ev, [], NO_LEGACY, "X")
    assert out["close"].tolist() == pytest.approx([100 * 0.98 * 0.95, 100 * 0.95, 100.0, 100.0])


def test_split_listed_in_config_is_adjusted():
    raw = _raw([("2025-06-09", 183.70), ("2025-06-10", 188.65), ("2025-06-18", 47.57)], split_days={"2025-06-18"})
    out = tw_prices.build(raw, NO_EVENTS, [("2025-06-18", 4.0)], NO_LEGACY, "0050")
    assert out["close"].tolist() == pytest.approx([183.70 / 4, 188.65 / 4, 47.57])


def test_split_marked_by_twse_but_missing_from_config_fails():
    raw = _raw([("2025-06-10", 188.65), ("2025-06-18", 47.57)], split_days={"2025-06-18"})
    with pytest.raises(PriceCheckError, match="TW_SPLITS"):
        tw_prices.build(raw, NO_EVENTS, [], NO_LEGACY, "0050")


def test_unexplained_jump_beyond_price_limit_fails():
    raw = _raw([("2025-06-10", 188.65), ("2025-06-18", 47.57)])  # no "**", no event
    with pytest.raises(PriceCheckError, match="price limit"):
        tw_prices.build(raw, NO_EVENTS, [], NO_LEGACY, "0050")


def test_ex_rights_previous_close_must_match_stock_day():
    raw = _raw([("2022-06-22", 807.0), ("2022-06-23", 690.0)])
    with pytest.raises(PriceCheckError, match="previous close"):
        tw_prices.build(raw, _events([("2022-06-23", 800.0, 733.99)]), [], NO_LEGACY, "2454")


def test_price_limit_is_7_percent_before_2015_06_and_10_percent_after():
    before = pd.Series([100.0, 109.0], index=pd.DatetimeIndex(["2015-05-28", "2015-05-29"]))
    after = pd.Series([100.0, 109.0], index=pd.DatetimeIndex(["2015-06-01", "2015-06-02"]))
    assert len(tw_prices.limit_breaches(before)) == 1
    assert tw_prices.limit_breaches(after).empty


def test_legacy_is_rescaled_onto_twse_and_cut_after_its_last_bad_day():
    days = pd.bdate_range("2009-12-21", "2010-01-08")
    # Yahoo is on a different scale (×2) and has a bad tick on 2009-12-23.
    y = [200.0, 202, 150, 204, 206, 208, 210, 212, 214, 216, 218, 220, 222, 224, 226][: len(days)]
    legacy = pd.DataFrame({"open": y, "high": y, "low": y, "close": y, "volume": 1.0}, index=days)
    twse_days = days[days >= "2010-01-04"]
    raw = _raw([(d, legacy.loc[d, "close"] / 2) for d in twse_days])
    out = tw_prices.build(raw, NO_EVENTS, [], legacy, "X")
    # 2009-12-23 (-26%) and 2009-12-24 (+36%) are impossible: keep Yahoo from 2009-12-24 on.
    assert out.index[0] == pd.Timestamp("2009-12-24")
    assert out.loc["2009-12-31", "close"] == pytest.approx(legacy.loc["2009-12-31", "close"] / 2)
    assert (out.loc[twse_days, "close"] == raw["close"]).all()


def test_legacy_that_disagrees_with_twse_fails():
    days = pd.bdate_range("2009-12-28", "2010-01-08")
    legacy = pd.DataFrame({c: 100.0 for c in ["open", "high", "low", "close"]} | {"volume": 1.0}, index=days)
    twse_days = days[days >= "2010-01-04"]
    raw = _raw([(d, 50.0 if i % 2 else 52.0) for i, d in enumerate(twse_days)])
    with pytest.raises(PriceCheckError, match="disagree"):
        tw_prices.build(raw, NO_EVENTS, [], legacy, "X")


def test_parse_stock_day():
    payload = {
        "stat": "OK",
        "fields": ["日期", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌價差", "成交筆數", "註記"],
        "data": [
            [" 99/01/04", "4,636,571", "2,604,600,924", "558.00", "567.00", "557.00", "567.00", "+9.00", "3,218", ""],
            ["114/06/18", "252,639,825", "1", "47.50", "47.72", "47.14", "47.57", "+0.41", "1", "**"],
            ["114/06/19", "0", "0", "--", "--", "--", "--", " 0.00", "0", ""],
        ],
    }
    df = twse.parse_stock_day(payload)
    assert list(df.index) == [pd.Timestamp("2010-01-04"), pd.Timestamp("2025-06-18")]  # "--" row dropped
    assert df.loc["2010-01-04"].tolist() == [558.0, 567.0, 557.0, 567.0, 4636571.0, 0.0]
    assert df.loc["2025-06-18", "split"] == 1.0


def test_parse_twt49u():
    payload = {
        "stat": "OK",
        "fields": ["資料日期", "股票代號", "股票名稱", "除權息前收盤價", "除權息參考價", "權值", "息值"],
        "data": [["111年06月23日", "2454", "聯發科", "807.00", "733.99", "0.00", "73.00"]],
    }
    df = twse.parse_twt49u(payload)
    assert df.iloc[0].tolist() == [pd.Timestamp("2022-06-23"), "2454", 807.0, 733.99]


def test_update_tw_prices_rebuilds_adjusted_prices(tmp_path, monkeypatch):
    eng = make_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(eng)
    monkeypatch.setattr(daily, "TWSE_PRICES", {"2454.TW": "2454"})
    monkeypatch.setattr(daily, "TW_SPLITS", {})
    monkeypatch.setattr(daily.twse, "PRICE_START", pd.Timestamp("2022-06-01"))
    monkeypatch.setattr(daily, "_TW_LEGACY_END", pd.Timestamp("2022-06-01"))
    monkeypatch.setattr(daily, "_today", lambda: pd.Timestamp("2022-06-30"))
    raw = _raw([("2022-06-21", 807.0), ("2022-06-22", 807.0), ("2022-06-23", 690.0)])
    monkeypatch.setattr(daily.twse, "fetch_stock_day", lambda code, y, m: raw)
    monkeypatch.setattr(
        daily.twse, "fetch_ex_rights", lambda s, e: _events([("2022-06-23", 807.0, 733.99)]).assign(code="2454")
    )
    monkeypatch.setattr(daily.yahoo, "fetch_history", lambda sym, start, adjusted=False: pd.DataFrame(
        {"Open": [], "High": [], "Low": [], "Close": [], "Volume": []}, index=pd.DatetimeIndex([])
    ))

    with Session(eng) as session:
        daily.update_tw_prices(session, full=False)
        session.commit()
        rows = session.execute(select(Price.date, Price.close).where(Price.symbol == "2454.TW").order_by(Price.date)).all()

    f = 733.99 / 807.0
    assert [r.close for r in rows] == pytest.approx([807 * f, 807 * f, 690.0])
