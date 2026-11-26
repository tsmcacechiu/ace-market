"""TWSE (證交所) daily P/E, dividend yield and P/B per listed stock (BWIBBU), one month per request.

History starts 2005-09. ETFs such as 0050 are not covered.
TWSE blocks clients that poll too fast, so requests are spaced by MIN_INTERVAL seconds.
"""

import json
import time

import pandas as pd

from market.collectors.http import get_text

START = pd.Timestamp("2005-09-01")  # earliest month BWIBBU serves
MIN_INTERVAL = 3.0  # seconds between requests

# Response field name -> our column. The column order changed in 2020, so map by name.
_FIELDS = {"本益比": "pe", "殖利率(%)": "yield", "股價淨值比": "pb"}
_NO_DATA = "沒有符合條件的資料"

_last_request = 0.0


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


def fetch_month(stock_no: str, year: int, month: int) -> pd.DataFrame:
    global _last_request
    wait = _last_request + MIN_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    url = (
        "https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU"
        f"?date={year}{month:02d}01&stockNo={stock_no}&response=json"
    )
    try:
        return parse_bwibbu(json.loads(get_text(url)))
    finally:
        _last_request = time.monotonic()


def months_between(start: pd.Timestamp, end: pd.Timestamp) -> list[tuple[int, int]]:
    """Every (year, month) from start's month to end's month, inclusive."""
    return [(p.year, p.month) for p in pd.period_range(start.to_period("M"), end.to_period("M"), freq="M")]
