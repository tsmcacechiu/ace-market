from dataclasses import dataclass

import pandas as pd

from market.config import KIND_WEIGHTS, MIN_MONTHS_FOR_PERCENTILE, PERCENTILE_YEARS

BAND_QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)


@dataclass
class Score:
    value: float
    date: pd.Timestamp
    percentile: float | None  # where the latest value sits in its own history, 0–100
    history_months: int  # monthly observations used for the percentile
    bands: dict[str, float] | None  # p10 … p90 of the history window


def history_window(s: pd.Series, years: int = PERCENTILE_YEARS) -> pd.Series:
    """Month-end samples over the last `years` years.

    Resampling to monthly puts daily, monthly and quarterly series on equal footing,
    so a burst of recent daily points does not dominate the distribution.
    """
    s = s.dropna().sort_index()
    if s.empty:
        return s
    start = s.index[-1] - pd.DateOffset(years=years)
    return s[s.index >= start].resample("ME").last().dropna()


def score(s: pd.Series, years: int = PERCENTILE_YEARS, min_months: int = MIN_MONTHS_FOR_PERCENTILE) -> Score | None:
    s = s.dropna().sort_index()
    if s.empty:
        return None
    value = float(s.iloc[-1])
    hist = history_window(s, years)
    if len(hist) < min_months:
        return Score(value, s.index[-1], None, len(hist), None)
    # Mid-rank: ties count half, so a constant series scores 50.
    pct = float(((hist < value).sum() + 0.5 * (hist == value).sum()) / len(hist) * 100)
    bands = {f"p{int(q * 100)}": float(hist.quantile(q)) for q in BAND_QUANTILES}
    return Score(value, s.index[-1], pct, len(hist), bands)


def expensiveness(percentile: float | None, higher_is_expensive: bool) -> float | None:
    """Map a percentile to 0 = cheap … 100 = expensive."""
    if percentile is None:
        return None
    return percentile if higher_is_expensive else 100 - percentile


def temperature(items: list[tuple[str, float | None]]) -> float | None:
    """Weighted mean of expensiveness scores; items are (kind, expensiveness)."""
    pairs = [(KIND_WEIGHTS.get(kind, 1.0), e) for kind, e in items if e is not None]
    total = sum(w for w, _ in pairs)
    if not total:
        return None
    return sum(w * e for w, e in pairs) / total
