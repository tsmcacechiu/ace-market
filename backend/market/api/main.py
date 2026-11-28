"""uv run uvicorn market.api.main:app --reload"""

import asyncio
import contextlib
import logging
import threading
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import date

import pandas as pd
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from market.config import (
    CORS_ORIGINS,
    GROUPS,
    MA_WINDOWS,
    MIN_MONTHS_FOR_PERCENTILE,
    PERCENTILE_YEARS,
    SCHEDULE_ENABLED,
    STRATEGY_1,
    TARGETS,
)
from market.db import SessionLocal, init_db
from market.jobs import daily, scheduler
from market.metrics import METRICS, METRICS_BY_ID
from market.metrics import strategy
from market.metrics.scoring import expensiveness, score, temperature
from market import strategy_service
from market.models import JobRun, StrategySignal
from market.store import DataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("market.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    warm = asyncio.create_task(asyncio.to_thread(_warm_dashboard))  # first page load is fast too
    task = asyncio.create_task(scheduler.run_forever(on_job_done=_warm_dashboard)) if SCHEDULE_ENABLED else None
    yield
    warm.cancel()
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Market Valuation API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
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


def _moving_averages(close: pd.Series) -> list[dict]:
    """Latest N-day simple moving averages and how far the last close sits from each (%)."""
    out = []
    for n in MA_WINDOWS:
        ma = float(close.tail(n).mean()) if len(close) >= n else None
        out.append(
            {
                "window": n,
                "value": ma,
                "deviation_pct": None if ma is None else float((close.iloc[-1] / ma - 1) * 100),
            }
        )
    return out


def _latest_job(session: Session) -> JobRun | None:
    return session.scalar(select(JobRun).order_by(JobRun.id.desc()).limit(1))


@app.get("/api/metrics")
def list_metrics() -> list[dict]:
    return [m.to_dict() for m in METRICS]


@app.get("/api/jobs/latest")
def latest_job(store: DataStore = Depends(get_store)) -> dict | None:
    return _job_dict(_latest_job(store.session))


def _run_job_and_warm(full: bool) -> None:
    if daily.run_exclusive(full) is not None:
        _warm_dashboard()


@app.post("/api/jobs/run", status_code=202)
def run_job(background: BackgroundTasks, full: bool = False) -> dict:
    """Fetch the latest data now (same as the daily job). Poll /api/jobs/latest for the result."""
    if daily.is_running():
        raise HTTPException(409, "A job is already running")
    background.add_task(_run_job_and_warm, full)
    return {"status": "started", "full": full}


# A board (home dashboard or 個股診斷) reads full histories (slow against a remote DB) but only
# changes when a job writes new data, so each group is cached and rebuilt when the latest
# job's state changes.
_dashboard_lock = threading.Lock()
_dashboard_cache: dict[str, dict] = {}


def _job_key(job: JobRun | None) -> tuple | None:
    return None if job is None else (job.id, job.status, job.finished_at)


def cached_dashboard(store: DataStore, group: str = "market") -> dict:
    with _dashboard_lock:  # concurrent requests wait for one build instead of each building
        job = _latest_job(store.session)
        key = _job_key(job)
        entry = _dashboard_cache.get(group)
        if entry is None or entry["key"] != key:
            entry = {"key": key, "data": _build_dashboard(store, job, group)}
            _dashboard_cache[group] = entry
        return entry["data"]


def _warm_dashboard() -> None:
    try:
        with SessionLocal() as session:
            for group in GROUPS:
                cached_dashboard(DataStore(session), group)
            cached_strategy(DataStore(session))
        log.info("dashboard cache warmed")
    except Exception:
        log.exception("dashboard cache warm-up failed")


@app.get("/api/dashboard")
def dashboard(store: DataStore = Depends(get_store)) -> dict:
    """Home page: market indices, gold, bitcoin."""
    return cached_dashboard(store, "market")


@app.get("/api/stocks")
def stocks(store: DataStore = Depends(get_store)) -> dict:
    """個股診斷 page: same shape as /api/dashboard, for the stock group."""
    return cached_dashboard(store, "stock")


def _build_dashboard(store: DataStore, job: JobRun | None, group: str = "market") -> dict:
    group_targets = {tid: t for tid, t in TARGETS.items() if t.get("group", "market") == group}
    bt = _backtest_or_none(store)
    targets = []
    for tid, t in group_targets.items():
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
            if m.in_temperature:
                temp_items.append((m.kind, exp))
            metrics[m.id] = {
                "value": sc.value,
                "date": sc.date.date().isoformat(),
                "percentile": sc.percentile,
                "expensiveness": exp,
                "history_months": sc.history_months,
            }

        params = strategy.Params.for_target(tid)
        regime = None
        if len(close):
            regime = strategy_service.regime_with_alerts(strategy.ma_regime(close, params), params, bt, tid)

        targets.append(
            {
                "id": tid,
                "name": t["name"],
                "symbol": t["index"],
                "etf": t["etf"],
                "quote": quote,
                "moving_averages": _moving_averages(close) if len(close) else [],
                "temperature": temperature(temp_items),
                # How many metrics of each kind fed the temperature (UI warns when valuation is 0).
                "temperature_basis": {
                    kind: sum(1 for k, e in temp_items if k == kind and e is not None)
                    for kind in ("valuation", "technical")
                },
                "metrics": metrics,
                "regime": regime,
            }
        )

    return {
        "settings": {"percentile_years": PERCENTILE_YEARS, "min_months": MIN_MONTHS_FOR_PERCENTILE},
        "job": _job_dict(job),
        # Only rows that apply to at least one asset on this page.
        "metrics": [m.to_dict() for m in METRICS if set(m.sources) & set(group_targets)],
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


# Above this many points the chart is sent as weekly closes (keeps "all history" responses small).
_CHART_MAX_DAILY_POINTS = 3000


@app.get("/api/indices/{target}/chart")
def index_chart(
    target: str,
    start: date | None = Query(None, alias="from"),
    store: DataStore = Depends(get_store),
) -> dict:
    """Index closes plus its moving averages (MA_WINDOWS), for the index detail page."""
    if target not in TARGETS:
        raise HTTPException(404, f"Unknown target {target}")
    t = TARGETS[target]
    close = store.close(t["index"]).dropna()
    # Averages use the full history, so the first days of the shown range already have values.
    frame = pd.DataFrame({"close": close, **{f"ma{n}": close.rolling(n).mean() for n in MA_WINDOWS}})
    if start:
        frame = frame[frame.index >= pd.Timestamp(start)]
    weekly = len(frame) > _CHART_MAX_DAILY_POINTS
    if weekly:
        # Last trading day of each week, keeping its real date (resample would label it Friday).
        frame = frame.groupby(frame.index.to_period("W-FRI")).tail(1)

    return {
        "target": {"id": target, **t},
        "interval": "weekly" if weekly else "daily",
        "price": _points(frame["close"]),
        "moving_averages": [{"window": n, "points": _points(frame[f"ma{n}"].dropna())} for n in MA_WINDOWS],
        "latest": _moving_averages(close) if len(close) else [],
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


# --- 策略一 (plan/strategy-1/SKILL.md) -------------------------------------------------------
# The backtest needs every target's full history (group stats pool them), so it is built once
# per finished job, like the dashboards.
_strategy_lock = threading.Lock()
_strategy_cache: dict = {}


def cached_strategy(store: DataStore) -> dict:
    with _strategy_lock:
        key = _job_key(_latest_job(store.session))
        if _strategy_cache.get("key", object()) != key or "data" not in _strategy_cache:
            _strategy_cache.update(key=key, data=strategy_service.build_bundle(store))
        return _strategy_cache["data"]


def _backtest_or_none(store: DataStore) -> dict | None:
    """The strategy bundle for alert history lines; alerts still work without it."""
    try:
        return cached_strategy(store)
    except Exception:
        log.exception("strategy backtest unavailable; alerts without history")
        return None


def _iso(ts) -> str | None:
    return None if ts is None or pd.isna(ts) else pd.Timestamp(ts).date().isoformat()


@app.get("/api/strategy/1/{target}")
def strategy_1(
    target: str,
    start: date | None = Query(None, alias="from"),
    store: DataStore = Depends(get_store),
) -> dict:
    """策略一 for one target: today's state, state history (chart backgrounds), events with
    forward returns, and backtest stats for the target and its group (指數 / 其他)."""
    if target not in TARGETS:
        raise HTTPException(404, f"Unknown target {target}")
    bundle = cached_strategy(store)
    d = bundle["targets"][target]
    frame, params = d["regime"].frame, d["params"]
    shown = frame if start is None else frame[frame.index >= pd.Timestamp(start)]
    group = strategy_service.group_of(target)

    marks = shown[shown["event"].ne("") & shown["event"].notna()]
    events = d["events"]
    trades = d["trades"]
    horizons = [f"{m}m" for m in strategy.HORIZONS_MONTHS]
    return {
        "target": {"id": target, "name": TARGETS[target]["name"], "group": group,
                   "is_stock": TARGETS[target].get("group") == "stock"},
        "params": {
            "window": params.window,
            "break_confirm": params.break_confirm,
            "reclaim_confirm": params.reclaim_confirm,
            "exit_confirm": params.exit_confirm,
            "touch_band_pct": params.touch_band_pct,
            "exit_200": [list(x) for x in params.exit_200],
            "exit_500": [list(x) for x in params.exit_500],
            "min_samples": STRATEGY_1["MIN_SAMPLES"],
            "horizons": horizons,
        },
        "states": {k: {"label": v[0], "color": v[1], "position": v[2]} for k, v in strategy.STATES.items()},
        "regime": strategy_service.regime_with_alerts(frame, params, bundle, target),
        "segments": strategy.state_segments(shown),
        "markers": [[_iso(ts), r["event"], round(float(r["close"]), 4)] for ts, r in marks.iterrows()],
        "events": [
            {
                "date": _iso(ts),
                "kind": r["kind"],
                "close": round(float(r["close"]), 4),
                "first_500": None if pd.isna(r["first_500"]) else bool(r["first_500"]),
                "returns": {h: strategy.rounded(r[f"ret_{h}"]) for h in horizons},
            }
            for ts, r in events.iloc[::-1].iterrows()
        ],
        "stats": {
            "target": strategy.event_stats(events),
            "group": bundle["groups"][group]["events"],
            "group_name": group,
            "group_members": bundle["groups"][group]["members"],
        },
        "trades": {
            "target": strategy.trade_stats(trades),
            "group": bundle["groups"][group]["trades"],
            "fill": "next_open",
            "list": [
                {
                    "kind": r["kind"],
                    "entry_date": _iso(r["entry_date"]),
                    "entry_price": round(float(r["entry_price"]), 4),
                    "exit_date": _iso(r["exit_date"]),
                    "ret": strategy.rounded(r["ret"]),
                    "days": int(r["days"]),
                    "open": bool(r["open"]),
                }
                for _, r in trades.iloc[::-1].iterrows()
            ],
        },
        "disclaimer": strategy_service.DISCLAIMER,
    }


# Alert kind -> the backtest event it corresponds to (for "回測怎麼說" next to real outcomes).
_SIGNAL_EVENT = {
    "ENTRY_200": "RECLAIM_200",
    "ENTRY_500": "RECLAIM_500",
    "NEAR_500": "NEAR_500",
    "BEAR_200": "BEAR_200",
    "CRISIS": "CRISIS",
}


@app.get("/api/strategy/signals")
def strategy_signals(
    level: str = Query("action", pattern="^(action|all)$"),
    store: DataStore = Depends(get_store),
) -> dict:
    """訊號紀錄 (SKILL.md §9.6): alerts the daily job recorded, newest first, with what the price
    did 1 / 3 / 6 / 12 months later (None until that much time has passed)."""
    q = select(StrategySignal).order_by(StrategySignal.date.desc(), StrategySignal.target)
    if level == "action":
        q = q.where(StrategySignal.level == "action")
    rows = store.session.scalars(q).all()
    closes = {tid: store.close(TARGETS[tid]["index"]).dropna() for tid in {r.target for r in rows} if tid in TARGETS}
    try:
        bundle = cached_strategy(store)
    except Exception:
        log.exception("strategy backtest unavailable for the signal log")
        bundle = None

    out = []
    for r in rows:
        close = closes.get(r.target)
        rets = {}
        for m in strategy.HORIZONS_MONTHS:
            j = None if close is None else close.index.searchsorted(pd.Timestamp(r.date) + pd.DateOffset(months=m))
            rets[f"{m}m"] = None if j is None or j >= len(close) else round(float((close.iloc[j] / r.price - 1) * 100), 1)
        ev = _SIGNAL_EVENT.get(r.kind)
        stats = strategy_service.alert_stats(bundle, r.target) if ev else None
        backtest = None
        if stats:
            own = stats["target"][ev]["horizons"]["12m"]
            use = own if own["n"] >= STRATEGY_1["MIN_SAMPLES"] else (stats["group"] or {}).get(ev, {}).get("horizons", {}).get("12m")
            if use and use["n"]:
                backtest = {"win_pct_12m": use["win_pct"], "median_12m": use["median"], "n": use["n"],
                            "pooled": use is not own, "group": stats["group_name"]}
        out.append(
            {
                "target": r.target,
                "name": TARGETS.get(r.target, {}).get("name", r.target),
                "date": r.date.isoformat(),
                "kind": r.kind,
                "level": r.level,
                "title": r.title,
                "price": r.price,
                "sent": r.sent_at is not None,
                "returns": rets,
                "backtest": backtest,
            }
        )
    return {"signals": out, "disclaimer": strategy_service.DISCLAIMER}
