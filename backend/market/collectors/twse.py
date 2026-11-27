"""TWSE (證交所) data for listed stocks and ETFs.

- BWIBBU: daily P/E, dividend yield and P/B per stock, one month per request. From 2005-09;
  ETFs such as 0050 are not covered.
- STOCK_DAY: raw (unadjusted) daily OHLCV per stock or ETF, one month per request. From 2010-01-04.
- TWT49U: ex-rights / ex-dividend events of all securities over a date range. From 2003-05-05.

TWSE blocks clients that poll too fast, so requests are spaced by MIN_INTERVAL seconds.
"""

import json
import logging
import time

import pandas as pd

from market.collectors.http import get_text

START = pd.Timestamp("2005-09-01")  # earliest month BWIBBU serves
PRICE_START = pd.Timestamp("2010-01-04")  # earliest day STOCK_DAY serves
MIN_INTERVAL = 3.0  # seconds between requests

# Response field name -> our column. The column order changed in 2020, so map by name.
_FIELDS = {"本益比": "pe", "殖利率(%)": "yield", "股價淨值比": "pb"}
_NO_DATA = "沒有符合條件的資料"

_last_request = 0.0
log = logging.getLogger(__name__)


def _roc_date(s: str) -> pd.Timestamp:
    """'115年11月26日' -> 2026-11-26 (ROC year + 1911)."""
    y, rest = s.split("年")
    m, rest = rest.split("月")
    return pd.Timestamp(int(y) + 1911, int(m), int(rest.rstrip("日")))


def parse_bwibbu(payload: dict) -> pd.DataFrame:
    """Daily rows indexed by date with columns pe, yield, pb ('-' becomes NaN)."""
    stat = payload.get("stat", "")
    if stat != "OK":
        if _NO_DATA in stat:
            return pd.DataFrame(columns=list(_FIELDS.values()), dtype=float)
        raise RuntimeError(f"TWSE BWIBBU: {stat}")
    fields = payload["fields"]
    cols = {name: fields.index(name) for name in _FIELDS}
    rows = {
        _roc_date(r[0]): [pd.to_numeric(str(r[i]).replace(",", ""), errors="coerce") for i in cols.values()]
        for r in payload["data"]
    }
    return pd.DataFrame.from_dict(rows, orient="index", columns=list(_FIELDS.values())).sort_index()


RETRY_WAITS = (10.0, 30.0, 60.0)  # seconds before each retry of a failed request


def _get_json(url: str) -> dict:
    """GET with pacing; retries timeouts and other transient errors (TWSE often stalls)."""
    global _last_request
    for attempt in range(len(RETRY_WAITS) + 1):
        wait = _last_request + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            return json.loads(get_text(url))
        except Exception as e:  # network error, HTTP error, or a non-JSON block page
            if attempt == len(RETRY_WAITS):
                raise
            log.warning("TWSE request failed (%r), retrying in %.0fs: %s", e, RETRY_WAITS[attempt], url)
            time.sleep(RETRY_WAITS[attempt])
        finally:
            _last_request = time.monotonic()
    raise AssertionError("unreachable")


def fetch_month(stock_no: str, year: int, month: int) -> pd.DataFrame:
    url = (
        "https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU"
        f"?date={year}{month:02d}01&stockNo={stock_no}&response=json"
    )
    return parse_bwibbu(_get_json(url))


def _num(v) -> float:
    return pd.to_numeric(str(v).replace(",", "").strip(), errors="coerce")


def _roc_slash_date(s: str) -> pd.Timestamp:
    """' 99/01/04' -> 2010-01-04 (ROC year + 1911)."""
    y, m, d = s.strip().split("/")
    return pd.Timestamp(int(y) + 1911, int(m), int(d))


_DAY_FIELDS = {"開盤價": "open", "最高價": "high", "最低價": "low", "收盤價": "close", "成交股數": "volume"}
DAY_COLUMNS = [*_DAY_FIELDS.values(), "split"]


def parse_stock_day(payload: dict) -> pd.DataFrame:
    """Raw daily OHLCV indexed by date, plus `split` = 1.0 on days TWSE marks "**".

    "**" means the price was re-based after a split / reverse split / par-value change, so it
    no longer compares with the previous close. Days without trades ("--") are dropped.
    """
    stat = payload.get("stat", "")
    if stat != "OK":
        if _NO_DATA in stat:
            return pd.DataFrame(columns=DAY_COLUMNS, dtype=float)
        raise RuntimeError(f"TWSE STOCK_DAY: {stat}")
    fields = payload["fields"]
    cols = {name: fields.index(name) for name in _DAY_FIELDS}
    note = fields.index("註記") if "註記" in fields else None
    rows = {}
    for r in payload["data"]:
        vals = [_num(r[i]) for i in cols.values()]
        flag = 1.0 if note is not None and "**" in str(r[note]) else 0.0
        rows[_roc_slash_date(r[0])] = [*vals, flag]
    df = pd.DataFrame.from_dict(rows, orient="index", columns=DAY_COLUMNS).sort_index()
    return df.dropna(subset=["close"])


def fetch_stock_day(stock_no: str, year: int, month: int) -> pd.DataFrame:
    url = (
        "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
        f"?date={year}{month:02d}01&stockNo={stock_no}&response=json"
    )
    return parse_stock_day(_get_json(url))


def parse_twt49u(payload: dict) -> pd.DataFrame:
    """Ex-rights / ex-dividend events: columns date, code, prev_close, ref (reference price)."""
    stat = payload.get("stat", "")
    cols = ["date", "code", "prev_close", "ref"]
    if stat != "OK":
        if _NO_DATA in stat:
            return pd.DataFrame(columns=cols)
        raise RuntimeError(f"TWSE TWT49U: {stat}")
    f = payload["fields"]
    i_date, i_code = f.index("資料日期"), f.index("股票代號")
    i_prev, i_ref = f.index("除權息前收盤價"), f.index("除權息參考價")
    rows = [
        (_roc_date(r[i_date]), str(r[i_code]).strip(), _num(r[i_prev]), _num(r[i_ref]))
        for r in payload.get("data") or []
    ]
    return pd.DataFrame(rows, columns=cols)


def fetch_ex_rights(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """All ex-rights / ex-dividend events between two dates, one request per calendar year."""
    frames = []
    for year in range(start.year, end.year + 1):
        lo, hi = max(start, pd.Timestamp(year, 1, 1)), min(end, pd.Timestamp(year, 12, 31))
        url = (
            "https://www.twse.com.tw/rwd/zh/exRight/TWT49U"
            f"?startDate={lo:%Y%m%d}&endDate={hi:%Y%m%d}&response=json"
        )
        frames.append(parse_twt49u(_get_json(url)))
    return pd.concat(frames, ignore_index=True)


def months_between(start: pd.Timestamp, end: pd.Timestamp) -> list[tuple[int, int]]:
    """Every (year, month) from start's month to end's month, inclusive."""
    return [(p.year, p.month) for p in pd.period_range(start.to_period("M"), end.to_period("M"), freq="M")]
