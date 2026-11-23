"""In-process daily scheduler, started by the API server (see market.api.main lifespan).

Runs the daily job every day at SCHEDULE_TIME (SCHEDULE_TZ). If the server starts after
today's slot and no job has run since, it catches up once right away — handy when the
machine was asleep or the server was down at the scheduled time.
"""

import asyncio
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from market.config import SCHEDULE_TIME, SCHEDULE_TZ
from market.db import SessionLocal
from market.jobs import daily
from market.models import JobRun

log = logging.getLogger("market.scheduler")


def _slot_time() -> time:
    h, m = SCHEDULE_TIME.split(":")
    return time(int(h), int(m))


def next_run(now: datetime, slot: time) -> datetime:
    """Next occurrence of `slot` strictly after `now` (both in now's timezone)."""
    candidate = now.replace(hour=slot.hour, minute=slot.minute, second=0, microsecond=0)
    return candidate if candidate > now else candidate + timedelta(days=1)


def last_slot(now: datetime, slot: time) -> datetime:
    """Most recent occurrence of `slot` at or before `now`."""
    return next_run(now, slot) - timedelta(days=1)


def _missed_today(now: datetime, slot: time) -> bool:
    with SessionLocal() as session:
        last = session.scalar(select(func.max(JobRun.started_at)))
    if last is None:
        return True
    # JobRun.started_at is naive server-local time (datetime.now()); astimezone() treats it as such.
    return last.astimezone(now.tzinfo) < last_slot(now, slot)


async def _run_job() -> None:
    try:
        job = await asyncio.to_thread(daily.run_exclusive)
        if job is None:
            log.info("scheduled run skipped: a job is already running")
        else:
            log.info("scheduled job #%s finished: %s", job.id, job.status)
    except Exception:
        log.exception("scheduled job crashed")


async def run_forever() -> None:
    tz, slot = ZoneInfo(SCHEDULE_TZ), _slot_time()
    log.info("daily job scheduled at %s %s", SCHEDULE_TIME, SCHEDULE_TZ)

    if await asyncio.to_thread(_missed_today, datetime.now(tz), slot):
        log.info("no job since today's slot; catching up now")
        await _run_job()

    while True:
        target = next_run(datetime.now(tz), slot)
        log.info("next daily job at %s", target.isoformat())
        # Sleep in short steps against the wall clock: the monotonic clock asyncio uses
        # stops while a laptop sleeps, so one long sleep could fire hours late.
        while (remaining := (target - datetime.now(tz)).total_seconds()) > 0:
            await asyncio.sleep(min(remaining, 60))
        await _run_job()
