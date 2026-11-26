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

# Browser origins allowed to call the API (comma-separated), e.g. the deployed frontend URL.
CORS_ORIGINS = [
    o.strip().rstrip("/")
    for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]

# Assets we evaluate. `index` is the Yahoo symbol whose closes we store.
# `etf` is the proxy used for P/E (Yahoo has no P/E for indices); None for assets without
# earnings (gold, bitcoin), which therefore get technical metrics only.
# `market` decides which US-only metrics apply (e.g. ERP uses the US 10Y yield).
# `group` picks the page: "market" = home dashboard, "stock" = 個股診斷.
# `twse` (stocks only) is the TWSE code for daily P/E, P/B and dividend-yield history.
TARGETS: dict[str, dict[str, str | None]] = {
    "SPX": {"name": "S&P 500", "index": "^GSPC", "etf": "SPY", "market": "US", "group": "market"},
    "NDX": {"name": "Nasdaq 100", "index": "^NDX", "etf": "QQQ", "market": "US", "group": "market"},
    "SOX": {"name": "費城半導體", "index": "^SOX", "etf": "SOXX", "market": "US", "group": "market"},
    "TWII": {"name": "台灣加權", "index": "^TWII", "etf": "0050.TW", "market": "TW", "group": "market"},
    # COMEX futures, USD/oz
    "GOLD": {"name": "黃金", "index": "GC=F", "etf": None, "market": "GLOBAL", "group": "market"},
    # trades 7 days a week
    "BTC": {"name": "比特幣", "index": "BTC-USD", "etf": None, "market": "GLOBAL", "group": "market"},
    # 個股診斷. 0050 is an ETF: TWSE has no P/E for it, so it uses Yahoo snapshots like TWII.
    "0050": {"name": "元大台灣50", "index": "0050.TW", "etf": "0050.TW", "market": "TW", "group": "stock"},
    "2330": {"name": "台積電", "index": "2330.TW", "etf": None, "twse": "2330", "market": "TW", "group": "stock"},
    "2454": {"name": "聯發科", "index": "2454.TW", "etf": None, "twse": "2454", "market": "TW", "group": "stock"},
}
GROUPS = ("market", "stock")
BENCHMARK = "SPX"  # relative strength on the home page is measured against this target
STOCK_BENCHMARK = "TWII"  # ... and on the 個股診斷 page against this one

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

# Simple moving averages (trading days) shown on each index card.
MA_WINDOWS = (50, 200, 500)

# Days re-fetched on incremental price updates (covers late corrections from Yahoo).
PRICE_OVERLAP_DAYS = 7

# In-process daily job, run by the API server (uvicorn). Set SCHEDULE_ENABLED=0 to turn it off,
# e.g. when using the launchd job instead. Default 06:30 Taipei = after the US close.
SCHEDULE_ENABLED = os.environ.get("SCHEDULE_ENABLED", "1").lower() not in ("0", "false", "no")
SCHEDULE_TIME = os.environ.get("SCHEDULE_TIME", "06:30")  # HH:MM
SCHEDULE_TZ = os.environ.get("SCHEDULE_TZ", "Asia/Taipei")
