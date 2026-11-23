"""uv run uvicorn market.api.main:app --reload"""

import asyncio
import contextlib
import logging
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import date

import pandas as pd
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from market.config import MIN_MONTHS_FOR_PERCENTILE, PERCENTILE_YEARS, SCHEDULE_ENABLED, TARGETS
from market.db import SessionLocal, init_db
from market.jobs import daily, scheduler
from market.metrics import METRICS, METRICS_BY_ID
from market.metrics.scoring import expensiveness, score, temperature
from market.models import JobRun
from market.store import DataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    task = asyncio.create_task(scheduler.run_forever()) if SCHEDULE_ENABLED else None
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Market Valuation API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def get_store() -> Iterator[DataStore]:
    with SessionLocal() as session:
        yield DataStore(session)


def _points(s: pd.Series) -> list[list]:
    return [[ts.date().isoformat(), round(float(v), 4)] for ts, v in s.items()]


def _job_dict(job: JobRun | None) -> dict | None:
    if job is None:
        return None
    return {
        "id": job.id,
        "status": job.status,
        "started_at": job.started_at.isoformat(),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "detail": job.detail,
    }


def _latest_job(session: Session) -> JobRun | None:
    return session.scalar(select(JobRun).order_by(JobRun.id.desc()).limit(1))


@app.get("/api/metrics")
def list_metrics() -> list[dict]:
    return [m.to_dict() for m in METRICS]


@app.get("/api/jobs/latest")
def latest_job(store: DataStore = Depends(get_store)) -> dict | None:
    return _job_dict(_latest_job(store.session))


@app.post("/api/jobs/run", status_code=202)
def run_job(background: BackgroundTasks, full: bool = False) -> dict:
    """Fetch the latest data now (same as the daily job). Poll /api/jobs/latest for the result."""
    if daily.is_running():
        raise HTTPException(409, "A job is already running")
    background.add_task(daily.run_exclusive, full)
    return {"status": "started", "full": full}


@app.get("/api/dashboard")
def dashboard(store: DataStore = Depends(get_store)) -> dict:
    targets = []
    for tid, t in TARGETS.items():
        close = store.close(t["index"]).dropna()
        quote = None
        if len(close) >= 2:
            quote = {
                "date": close.index[-1].date().isoformat(),
                "close": float(close.iloc[-1]),
                "change_pct": float((close.iloc[-1] / close.iloc[-2] - 1) * 100),
            }

        metrics, temp_items = {}, []
        for m in METRICS:
            if tid not in m.sources:
                continue
            sc = score(store.metric(m.id, tid))
            if sc is None:
                metrics[m.id] = None
                continue
            exp = expensiveness(sc.percentile, m.higher_is_expensive)
            temp_items.append((m.kind, exp))
            metrics[m.id] = {
                "value": sc.value,
                "date": sc.date.date().isoformat(),
                "percentile": sc.percentile,
                "expensiveness": exp,
                "history_months": sc.history_months,
            }

        targets.append(
            {
                "id": tid,
                "name": t["name"],
                "symbol": t["index"],
                "etf": t["etf"],
                "quote": quote,
                "temperature": temperature(temp_items),
                # How many metrics of each kind fed the temperature (UI warns when valuation is 0).
                "temperature_basis": {
                    kind: sum(1 for k, e in temp_items if k == kind and e is not None)
                    for kind in ("valuation", "technical")
                },
                "metrics": metrics,
            }
        )

    return {
        "settings": {"percentile_years": PERCENTILE_YEARS, "min_months": MIN_MONTHS_FOR_PERCENTILE},
        "job": _job_dict(_latest_job(store.session)),
        "metrics": [m.to_dict() for m in METRICS],
        "targets": targets,
    }


@app.get("/api/metrics/{metric_id}/{target}")
def metric_history(
    metric_id: str,
    target: str,
    start: date | None = Query(None, alias="from"),
    end: date | None = Query(None, alias="to"),
    store: DataStore = Depends(get_store),
) -> dict:
    m = METRICS_BY_ID.get(metric_id)
    if m is None:
        raise HTTPException(404, f"Unknown metric {metric_id}")
    if target not in m.sources:
        raise HTTPException(404, f"Metric {metric_id} is not available for {target}")

    s = store.metric(metric_id, target)
    sc = score(s)  # always scored on the full window, independent of the range shown
    close = store.close(TARGETS[target]["index"])
    if start:
        s, close = s[s.index >= pd.Timestamp(start)], close[close.index >= pd.Timestamp(start)]
    if end:
        s, close = s[s.index <= pd.Timestamp(end)], close[close.index <= pd.Timestamp(end)]

    return {
        "metric": m.to_dict(),
        "target": {"id": target, **TARGETS[target]},
        "score": None
        if sc is None
        else {
            "value": sc.value,
            "date": sc.date.date().isoformat(),
            "percentile": sc.percentile,
            "expensiveness": expensiveness(sc.percentile, m.higher_is_expensive),
            "history_months": sc.history_months,
            "bands": sc.bands,
        },
        "points": _points(s),
        "price": _points(close),
    }


@app.get("/api/prices/{symbol}")
def prices(
    symbol: str,
    start: date | None = Query(None, alias="from"),
    store: DataStore = Depends(get_store),
) -> list[list]:
    close = store.close(symbol)
    if close.empty:
        raise HTTPException(404, f"No prices for {symbol}")
    if start:
        close = close[close.index >= pd.Timestamp(start)]
    return _points(close)
