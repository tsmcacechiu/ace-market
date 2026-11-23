from datetime import datetime, time
from zoneinfo import ZoneInfo

from market.jobs.scheduler import last_slot, next_run

TZ = ZoneInfo("Asia/Taipei")
SLOT = time(6, 30)


def test_next_run_before_slot_is_today():
    assert next_run(datetime(2026, 11, 23, 5, 0, tzinfo=TZ), SLOT) == datetime(2026, 11, 23, 6, 30, tzinfo=TZ)


def test_next_run_at_or_after_slot_is_tomorrow():
    assert next_run(datetime(2026, 11, 23, 6, 30, tzinfo=TZ), SLOT) == datetime(2026, 11, 24, 6, 30, tzinfo=TZ)
    assert next_run(datetime(2026, 11, 23, 22, 0, tzinfo=TZ), SLOT) == datetime(2026, 11, 24, 6, 30, tzinfo=TZ)


def test_last_slot():
    assert last_slot(datetime(2026, 11, 23, 5, 0, tzinfo=TZ), SLOT) == datetime(2026, 11, 22, 6, 30, tzinfo=TZ)
    assert last_slot(datetime(2026, 11, 23, 9, 0, tzinfo=TZ), SLOT) == datetime(2026, 11, 23, 6, 30, tzinfo=TZ)
