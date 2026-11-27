"""Dividend- and split-adjusted (還原權息) daily prices for TWSE-listed stocks and ETFs.

Yahoo's history for these is unreliable (0050's 2025 1:4 split is only applied from 2014,
MediaTek's stock dividends are applied on the wrong days), so prices are rebuilt from:

1. TWSE STOCK_DAY raw OHLCV (2010-01-04 on), adjusted backwards with
   - every TWT49U ex-rights / ex-dividend event: factor = reference price / previous close
   - every split in TW_SPLITS: factor = 1 / ratio
   The latest prices therefore equal the real traded prices.
2. Yahoo's adjusted history before 2010, rescaled to meet (1) and cut after its last day that
   moves more than the exchange's daily price limit (such a move cannot be real).

Everything is checked against the daily price limit before it is stored: a move beyond it means
an adjustment is missing or wrong, and the build fails instead of storing bad prices.
"""

import numpy as np
import pandas as pd

OHLC = ["open", "high", "low", "close"]
# TWSE daily price limit: ±7% until 2015-05-31, ±10% from 2015-06-01.
LIMIT_CHANGE_DAY = pd.Timestamp("2015-06-01")
# Rounding to ticks lets a limit-up/down day land slightly past the nominal percentage.
LIMIT_TOLERANCE = 0.003
# The ex-rights table's previous close must match STOCK_DAY's (prices have 2 decimals).
PREV_CLOSE_TOLERANCE = 0.006


class PriceCheckError(RuntimeError):
    pass


def price_limit(index: pd.DatetimeIndex) -> np.ndarray:
    return np.where(index >= LIMIT_CHANGE_DAY, 0.10, 0.07) + LIMIT_TOLERANCE


def limit_breaches(close: pd.Series) -> pd.Series:
    """Days whose close moved more than the daily price limit from the previous close."""
    move = (close / close.shift() - 1).abs()
    return close[move.values > price_limit(close.index)]


def adjustment_factors(
    raw: pd.DataFrame, events: pd.DataFrame, splits: list[tuple[str, float]], code: str
) -> pd.Series:
    """Factor per ex-date (prices before that date get multiplied by it).

    `events` are TWT49U rows for this code (date, prev_close, ref); `splits` are
    (first trading day after the split, ratio). Raises if TWSE's data does not line up.
    """
    factors: dict[pd.Timestamp, float] = {}
    closes = raw["close"]
    for ev in events.itertuples():
        d = pd.Timestamp(ev.date)
        if d <= closes.index[0] or d > closes.index[-1]:
            continue  # outside the stored range: does not change any stored row
        prev = closes[closes.index < d]
        if abs(prev.iloc[-1] / ev.prev_close - 1) > PREV_CLOSE_TOLERANCE:
            raise PriceCheckError(
                f"{code} ex-rights {d.date()}: TWT49U previous close {ev.prev_close} "
                f"!= STOCK_DAY close {prev.iloc[-1]} on {prev.index[-1].date()}"
            )
        factors[d] = factors.get(d, 1.0) * ev.ref / ev.prev_close
    split_days = {pd.Timestamp(d) for d, _ in splits}
    for d, ratio in splits:
        d = pd.Timestamp(d)
        if closes.index[0] < d <= closes.index[-1]:
            factors[d] = factors.get(d, 1.0) / ratio
    if "split" in raw:
        unknown = [d for d in raw.index[raw["split"] == 1] if d not in split_days]
        if unknown:
            days = ", ".join(str(d.date()) for d in unknown)
            raise PriceCheckError(f"{code}: TWSE marks a re-based price (split) on {days}; add it to TW_SPLITS")
    return pd.Series(factors, dtype=float).sort_index()


def apply_factors(raw: pd.DataFrame, factors: pd.Series) -> pd.DataFrame:
    """Backward-adjust OHLC: each row is multiplied by every factor dated after it."""
    cum = pd.Series(1.0, index=raw.index)
    for d, f in factors.items():
        cum[raw.index < d] *= f
    out = raw[[*OHLC, "volume"]].copy()
    out[OHLC] = out[OHLC].mul(cum, axis=0)
    return out


def stitch_legacy(legacy: pd.DataFrame, adjusted: pd.DataFrame, code: str) -> pd.DataFrame:
    """Prepend Yahoo's pre-TWSE history, rescaled to the TWSE series and cut after its last
    impossible move. `legacy` must overlap the first TWSE days (used to find the scale)."""
    if legacy.empty:
        return adjusted
    overlap = legacy.index.intersection(adjusted.index)[:5]
    if len(overlap) < 3:
        raise PriceCheckError(f"{code}: Yahoo history does not overlap TWSE's first days")
    ratio = adjusted.loc[overlap, "close"] / legacy.loc[overlap, "close"]
    if ratio.max() / ratio.min() - 1 > 0.005:
        raise PriceCheckError(f"{code}: Yahoo and TWSE disagree on {overlap[0].date()}…: ratios {ratio.round(4).tolist()}")
    old = legacy[legacy.index < adjusted.index[0]].copy()
    old[OHLC] = old[OHLC] * ratio.median()
    joined = pd.concat([old["close"], adjusted["close"].iloc[:1]])
    bad = limit_breaches(joined)
    if len(bad):
        old = old[old.index >= bad.index[-1]]  # the series is consistent from that day on
    return pd.concat([old[[*OHLC, "volume"]], adjusted])


def build(
    raw: pd.DataFrame,
    events: pd.DataFrame,
    splits: list[tuple[str, float]],
    legacy: pd.DataFrame,
    code: str,
) -> pd.DataFrame:
    """Adjusted OHLCV for one security; raises PriceCheckError instead of returning bad data."""
    if raw.empty:
        raise PriceCheckError(f"{code}: no TWSE prices")
    raw = raw.sort_index()
    adjusted = apply_factors(raw, adjustment_factors(raw, events, splits, code))
    out = stitch_legacy(legacy.sort_index(), adjusted, code)
    bad = limit_breaches(out["close"])
    if len(bad):
        days = ", ".join(f"{d.date()}" for d in bad.index[:5])
        raise PriceCheckError(f"{code}: moves beyond the daily price limit on {days}")
    return out
