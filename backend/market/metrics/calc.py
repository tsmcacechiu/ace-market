"""Pure metric formulas: pandas Series in, pandas Series out (DatetimeIndex, sorted)."""

import pandas as pd


def earnings_yield_spread(pe: pd.Series, yield_10y: pd.Series) -> pd.Series:
    """Equity risk premium proxy: 100/PE − 10Y yield, in percentage points.

    Each PE observation is paired with the most recent 10Y yield on or before its date.
    """
    pe = pe[pe > 0].sort_index()
    y = yield_10y.sort_index()
    if pe.empty or y.empty:
        return pd.Series(dtype=float)
    left = pd.DataFrame({"date": pe.index, "pe": pe.values})
    right = pd.DataFrame({"date": y.index, "y": y.values})
    merged = pd.merge_asof(left, right, on="date", direction="backward").dropna()
    return pd.Series(100.0 / merged["pe"].values - merged["y"].values, index=pd.DatetimeIndex(merged["date"]))


def buffett_indicator(equity_mil: pd.Series, gdp_bil: pd.Series, wilshire: pd.Series) -> pd.Series:
    """Corporate equity market value / GDP, in %.

    FRED dates both series at the quarter *start*; the equity level is measured at quarter
    end, so results are dated at quarter end. After the last quarter the ratio is carried
    forward daily with the Wilshire 5000's move, divided by the latest GDP.
    """
    if equity_mil.empty or gdp_bil.empty:
        return pd.Series(dtype=float)
    gdp = gdp_bil.reindex(gdp_bil.index.union(equity_mil.index)).sort_index().ffill()
    equity_bil = equity_mil / 1000.0
    quarterly = (equity_bil / gdp.reindex(equity_bil.index) * 100).dropna()
    quarterly.index = quarterly.index + pd.offsets.QuarterEnd(0)

    if wilshire.empty:
        return quarterly
    anchor = quarterly.index[-1]
    w = wilshire.sort_index()
    w_anchor = w.asof(anchor)
    after = w[w.index > anchor]
    if pd.isna(w_anchor) or after.empty:
        return quarterly
    latest_equity = equity_bil.iloc[-1]
    extension = latest_equity * (after / w_anchor) / gdp.iloc[-1] * 100
    return pd.concat([quarterly, extension])


def ma_deviation(close: pd.Series, window: int = 200) -> pd.Series:
    """% distance of price from its N-day simple moving average."""
    return (close / close.rolling(window).mean() - 1).dropna() * 100


def drawdown(close: pd.Series) -> pd.Series:
    """% below the running all-time high (0 = at a new high)."""
    return (close / close.cummax() - 1) * 100


def relative_strength_deviation(close: pd.Series, benchmark: pd.Series, window: int = 200) -> pd.Series:
    """How far the price ratio to a benchmark sits above its own N-day average, in %.

    Using the deviation instead of the raw ratio removes the long-run trend
    (tech has outperformed for decades, so the raw ratio is almost always "high").
    """
    joined = pd.concat([close, benchmark], axis=1, join="inner").dropna()
    if joined.empty:
        return pd.Series(dtype=float)
    ratio = joined.iloc[:, 0] / joined.iloc[:, 1]
    return ma_deviation(ratio, window)
