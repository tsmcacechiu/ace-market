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

# 個股 prices come from TWSE (adjusted for dividends and splits, see market/tw_prices.py), not
# Yahoo, whose split / stock-dividend adjustments are wrong for them. Yahoo symbol -> TWSE code.
TWSE_PRICES = {
    t["index"]: t["index"].removesuffix(".TW")
    for t in TARGETS.values()
    if t.get("group") == "stock" and t["index"].endswith(".TW")
}
# Splits are not in TWSE's ex-rights table: TWSE code -> [(first trading day after it, ratio)].
# The build fails if TWSE marks a re-based price ("**") on a day not listed here.
TW_SPLITS: dict[str, list[tuple[str, float]]] = {"0050": [("2025-06-18", 4.0)]}
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

# 策略一：200 / 500 日線多空判讀＋分層倉位 (plan/strategy-1/SKILL.md §2). Applies to every TARGET.
# Day counts are trading days (rows), so BTC's 30 days = 30 calendar days.
STRATEGY_1 = {
    "BREAK_CONFIRM_DAYS": 3,  # closes below an MA in a row to count as a break
    "RECLAIM_CONFIRM_DAYS": 3,  # closes above an MA in a row to count as a reclaim
    "RECLAIM_WINDOW_DAYS": 21,  # observation window after a confirmed break
    "TOUCH_BAND_PCT": 2.0,  # NEAR_500 when close <= MA500 × (1 + this / 100)
    "EXIT_CONFIRM_DAYS": 3,  # closes below an exit MA in a row to sell
    "EXIT_RECLAIM_500": [(500, 1.0)],  # (MA, share sold) for the swing sleeve entered on RECLAIM_500
    "EXIT_RECLAIM_200": [(50, 0.5), (200, 0.5)],  # ... and for one entered on RECLAIM_200
    "RECLAIM_500_FIRST_ONLY": True,  # only the first RECLAIM_500 of an episode is an entry
    "RECLAIM_HOLD_DAYS": 5,  # RECLAIM_200 / RECLAIM_500 stay the shown state this many days
    "MIN_SAMPLES": 10,  # fewer events than this → "樣本不足", fall back to the group's stats
}
RECLAIM_WINDOW_DAYS_OVERRIDE = {"BTC": 30}
# Backtest groups: indices are reported apart from gold, bitcoin and 個股.
STRATEGY_1_INDEX_GROUP = ("SPX", "NDX", "SOX", "TWII")
