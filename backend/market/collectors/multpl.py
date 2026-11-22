import io

import pandas as pd

from market.collectors.http import get_text


def parse_table(html: str) -> pd.Series:
    table = pd.read_html(io.StringIO(html))[0]
    values = pd.to_numeric(
        table.iloc[:, 1].astype(str).str.extract(r"(-?\d+(?:\.\d+)?)")[0], errors="coerce"
    )
    dates = pd.to_datetime(table.iloc[:, 0], format="%b %d, %Y", errors="coerce")
    s = pd.Series(values.values, index=dates).dropna()
    s = s[s.index.notna()]
    # The first row is a live estimate; keep only the latest value per date.
    return s[~s.index.duplicated(keep="first")].sort_index()


def fetch_series(slug: str) -> pd.Series:
    """Monthly history from multpl.com, e.g. slug='shiller-pe'. Latest row is today's estimate."""
    s = parse_table(get_text(f"https://www.multpl.com/{slug}/table/by-month"))
    if s.empty:
        raise RuntimeError(f"multpl table {slug} parsed empty")
    return s
