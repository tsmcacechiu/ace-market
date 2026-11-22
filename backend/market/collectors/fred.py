import io

import pandas as pd

from market.collectors.http import get_text


def fetch_series(series_id: str) -> pd.Series:
    """Full history of a FRED series (no API key needed)."""
    text = get_text(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}")
    df = pd.read_csv(io.StringIO(text))
    if df.shape[1] < 2:
        raise RuntimeError(f"Unexpected FRED CSV for {series_id}: {df.columns.tolist()}")
    s = pd.Series(
        pd.to_numeric(df.iloc[:, 1], errors="coerce").values,
        index=pd.to_datetime(df.iloc[:, 0]),
        name=series_id,
    ).dropna()
    if s.empty:
        raise RuntimeError(f"FRED series {series_id} has no data")
    return s
