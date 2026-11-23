"""Project-wide settings. Edit here to add indices or change scoring rules."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# Secrets live in backend/.env (git-ignored). Real environment variables take precedence.
load_dotenv(BASE_DIR / ".env")

DB_PATH = Path(os.environ.get("MARKET_DB", BASE_DIR / "data" / "market.db"))
# Set DATABASE_URL (e.g. Supabase Postgres) to use it instead of the local SQLite file.
DATABASE_URL = os.environ.get("DATABASE_URL") or f"sqlite:///{DB_PATH}"

# Indices we evaluate. `etf` is the proxy used for P/E (Yahoo has no P/E for indices).
TARGETS: dict[str, dict[str, str]] = {
    "SPX": {"name": "S&P 500", "index": "^GSPC", "etf": "SPY"},
    "NDX": {"name": "Nasdaq 100", "index": "^NDX", "etf": "QQQ"},
    "SOX": {"name": "費城半導體", "index": "^SOX", "etf": "SOXX"},
}
BENCHMARK = "SPX"  # relative strength is measured against this target

# Wilshire 5000 is used to extend the quarterly Buffett indicator to today.
EXTRA_PRICE_SYMBOLS = ["^W5000"]

FRED_SERIES = {
    "GDP": "GDP",  # Nominal GDP, billions USD, SAAR, quarterly
    "EQUITY": "NCBEILQ027S",  # Nonfinancial corporate equities, millions USD, quarterly
    "DGS10": "DGS10",  # 10Y Treasury yield, %, daily
}

MULTPL_SERIES = {
    "cape": "shiller-pe",
    "pe": "s-p-500-pe-ratio",
}

# Percentiles compare the latest value with this many years of history.
PERCENTILE_YEARS = 30
# Below this many monthly observations a percentile is not reported (data still accumulating).
MIN_MONTHS_FOR_PERCENTILE = 12

# Weight of each metric kind in the composite temperature.
KIND_WEIGHTS = {"valuation": 2.0, "technical": 1.0}

# Days re-fetched on incremental price updates (covers late corrections from Yahoo).
PRICE_OVERLAP_DAYS = 7
