import os
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from market.db import init_db, make_engine, upsert
from market.models import Price


def _check_upsert(session: Session) -> None:
    sym = "__TEST__"
    upsert(session, Price, [{"symbol": sym, "date": date(2020, 1, 1), "close": 1.0}])
    upsert(
        session,
        Price,
        [
            {"symbol": sym, "date": date(2020, 1, 1), "close": 2.0},  # existing key -> updated
            {"symbol": sym, "date": date(2020, 1, 2), "close": 3.0},  # new key -> inserted
        ],
    )
    rows = session.execute(select(Price.date, Price.close).where(Price.symbol == sym).order_by(Price.date)).all()
    assert [tuple(r) for r in rows] == [(date(2020, 1, 1), 2.0), (date(2020, 1, 2), 3.0)]


def test_upsert_sqlite(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(eng)
    with Session(eng) as session:
        _check_upsert(session)


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgres"), reason="DATABASE_URL is not Postgres"
)
def test_upsert_postgres():
    eng = make_engine(os.environ["DATABASE_URL"])
    init_db(eng)
    with Session(eng) as session:
        try:
            _check_upsert(session)
        finally:
            session.rollback()  # never leave test rows in the real database
