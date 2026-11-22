from datetime import date

import pandas as pd
import yfinance as yf


def fetch_history(symbol: str, start: date | None = None) -> pd.DataFrame:
    """Daily OHLCV. Full history when `start` is None. Index is naive dates."""
    ticker = yf.Ticker(symbol)
    if start is None:
        df = ticker.history(period="max", interval="1d", auto_adjust=False)
    else:
        df = ticker.history(start=start.isoformat(), interval="1d", auto_adjust=False)
    if df.empty:
        raise RuntimeError(f"Yahoo returned no price data for {symbol}")
    df.index = pd.DatetimeIndex(df.index.tz_localize(None).normalize())
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])


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
