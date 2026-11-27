from datetime import date

import pandas as pd
import yfinance as yf


def fetch_history(symbol: str, start: date | None = None, adjusted: bool = False) -> pd.DataFrame:
    """Daily OHLCV. Full history when `start` is None. Index is naive dates.

    `adjusted=False`: split-adjusted only. `adjusted=True`: also adjusted for dividends.
    """
    ticker = yf.Ticker(symbol)
    if start is None:
        df = ticker.history(period="max", interval="1d", auto_adjust=adjusted)
    else:
        df = ticker.history(start=start.isoformat(), interval="1d", auto_adjust=adjusted)
    if df.empty:
        raise RuntimeError(f"Yahoo returned no price data for {symbol}")
    df.index = pd.DatetimeIndex(df.index.tz_localize(None).normalize())
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])


def is_tw_listed(symbol: str) -> bool:
    """TWSE-listed stocks/ETFs (e.g. 2330.TW). Their volume is reliable, unlike indices'."""
    return symbol.endswith(".TW")


def drop_non_trading_days(df: pd.DataFrame) -> pd.DataFrame:
    """Drop zero-volume rows. For listed TW securities Yahoo emits them on exchange holidays
    and trading halts (e.g. 2026-10-23, 0050's 2025 split) with a stale price, which would
    count as extra trading days in moving averages. Do not apply to indices: they report no volume."""
    return df[df["Volume"].fillna(0) > 0]


def fetch_trailing_pe(symbol: str) -> tuple[date, float]:
    """Today's trailing P/E for an ETF, dated to its latest trading day."""
    ticker = yf.Ticker(symbol)
    pe = ticker.info.get("trailingPE")
    if pe is None:
        raise RuntimeError(f"Yahoo has no trailingPE for {symbol}")
    last = ticker.history(period="5d")
    if last.empty:
        raise RuntimeError(f"Yahoo returned no recent prices for {symbol}")
    return last.index[-1].date(), float(pe)
