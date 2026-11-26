"""Daily pipeline: fetch → store → compute metrics.

    uv run python -m market.jobs.daily          # incremental
    uv run python -m market.jobs.daily --full   # re-download full price history

Safe to re-run: every write is an upsert, and metrics are recomputed from scratch.
Each step is isolated, so one failing source does not block the others.
"""

import argparse
import logging
import threading
import traceback
from collections.abc import Callable
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from market.collectors import fred, multpl, twse, yahoo
from market.config import EXTRA_PRICE_SYMBOLS, FRED_SERIES, MULTPL_SERIES, PRICE_OVERLAP_DAYS, TARGETS
from market.db import SessionLocal, init_db, upsert
from market.metrics import METRICS
from market.models import JobRun, MetricValue, Observation, Price
from market.store import DataStore

log = logging.getLogger("market.daily")


def _num(v) -> float | None:
    return None if pd.isna(v) else float(v)


def update_prices(session: Session, full: bool) -> str:
    # dict.fromkeys: unique, in order (0050.TW is both a stock and TWII's P/E proxy).
    symbols = list(dict.fromkeys([t["index"] for t in TARGETS.values()] + EXTRA_PRICE_SYMBOLS))
    parts = []
    for sym in symbols:
        last = session.scalar(select(func.max(Price.date)).where(Price.symbol == sym))
        start = None if full or last is None else last - timedelta(days=PRICE_OVERLAP_DAYS)
        df = yahoo.fetch_history(sym, start)
        if yahoo.is_tw_listed(sym):
            df = yahoo.drop_non_trading_days(df)
            # Also remove phantom holiday rows stored before this filter existed.
            session.execute(delete(Price).where(Price.symbol == sym, Price.volume == 0))
        n = upsert(
            session,
            Price,
            (
                {
                    "symbol": sym,
                    "date": ts.date(),
                    "open": _num(r.Open),
                    "high": _num(r.High),
                    "low": _num(r.Low),
                    "close": float(r.Close),
                    "volume": _num(r.Volume),
                }
                for ts, r in df.iterrows()
            ),
        )
        parts.append(f"{sym}:{n}")
    return " ".join(parts)


def _store_series(session: Session, source: str, series_id: str, s: pd.Series) -> int:
    now = datetime.now()
    return upsert(
        session,
        Observation,
        (
            {"source": source, "series_id": series_id, "date": ts.date(), "value": float(v), "fetched_at": now}
            for ts, v in s.items()
        ),
    )


def update_etf_pe(session: Session, full: bool) -> str:
    parts = []
    for etf in dict.fromkeys(t["etf"] for t in TARGETS.values() if t["etf"]):  # gold, bitcoin: none
        d, pe = yahoo.fetch_trailing_pe(etf)
        _store_series(session, "yahoo_etf_pe", etf, pd.Series([pe], index=[pd.Timestamp(d)]))
        parts.append(f"{etf}={pe:.2f}@{d}")
    return " ".join(parts)


def update_twse(session: Session, full: bool) -> str:
    """Daily P/E, P/B, dividend yield per stock from TWSE, one request per month.

    First run backfills from 2005-09 (~250 requests per stock, ~13 min at TWSE's pace);
    later runs re-fetch from the month of the latest stored day. Commits every year of
    months so an interrupted backfill resumes where it stopped.
    """
    parts = []
    today = pd.Timestamp.now().normalize()
    for code in [t["twse"] for t in TARGETS.values() if t.get("twse")]:
        last = session.scalar(
            select(func.max(Observation.date)).where(
                Observation.source == "twse", Observation.series_id == f"{code}:pe"
            )
        )
        start = twse.START if full or last is None else pd.Timestamp(last)
        months = twse.months_between(start, today)
        rows = 0
        for i, (year, month) in enumerate(months, 1):
            df = twse.fetch_month(code, year, month)
            for col in df.columns:
                rows += _store_series(session, "twse", f"{code}:{col}", df[col].dropna())
            if i % 12 == 0:
                session.commit()
                log.info("twse %s: %d/%d months", code, i, len(months))
        parts.append(f"{code}:{len(months)}m/{rows}")
    return " ".join(parts)


def update_fred(session: Session, full: bool) -> str:
    return " ".join(
        f"{sid}:{_store_series(session, 'fred', sid, fred.fetch_series(sid))}" for sid in FRED_SERIES.values()
    )


def update_multpl(session: Session, full: bool) -> str:
    return " ".join(
        f"{slug}:{_store_series(session, 'multpl', slug, multpl.fetch_series(slug))}"
        for slug in MULTPL_SERIES.values()
    )


def compute_metrics(session: Session, full: bool) -> str:
    store = DataStore(session)
    parts = []
    for m in METRICS:
        for target in m.targets:
            s = m.compute(store, target).dropna()
            session.execute(delete(MetricValue).where(MetricValue.metric_id == m.id, MetricValue.target == target))
            upsert(
                session,
                MetricValue,
                ({"metric_id": m.id, "target": target, "date": ts.date(), "value": float(v)} for ts, v in s.items()),
            )
            parts.append(f"{m.id}/{target}:{len(s)}")
    return " ".join(parts)


STEPS: list[tuple[str, Callable[[Session, bool], str]]] = [
    ("prices", update_prices),
    ("etf_pe", update_etf_pe),
    ("fred", update_fred),
    ("multpl", update_multpl),
    ("twse", update_twse),
    ("metrics", compute_metrics),  # last: uses whatever the steps above managed to store
]


def run(full: bool = False) -> JobRun:
    init_db()
    with SessionLocal() as session:
        job = JobRun(started_at=datetime.now(), status="running")
        session.add(job)
        session.commit()

        lines, failures = [], 0
        for name, step in STEPS:
            try:
                result = step(session, full)
                session.commit()
                lines.append(f"[ok] {name}: {result}")
                log.info("%s ok: %s", name, result)
            except Exception as e:  # keep going; record and report
                session.rollback()
                failures += 1
                lines.append(f"[fail] {name}: {e!r}")
                log.error("%s failed:\n%s", name, traceback.format_exc())

        job.finished_at = datetime.now()
        job.status = "ok" if failures == 0 else ("failed" if failures == len(STEPS) else "partial")
        job.detail = "\n".join(lines)
        session.commit()
        return job


_lock = threading.Lock()


def is_running() -> bool:
    return _lock.locked()


def run_exclusive(full: bool = False) -> JobRun | None:
    """run(), unless another run in this process is in progress (then returns None)."""
    if not _lock.acquire(blocking=False):
        return None
    try:
        return run(full=full)
    finally:
        _lock.release()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--full", action="store_true", help="re-download full price history")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    job = run(full=args.full)
    print(f"\nJob #{job.id} {job.status}\n{job.detail}")
    raise SystemExit(0 if job.status == "ok" else 1)


if __name__ == "__main__":
    main()
