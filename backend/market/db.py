from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from market.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


def make_engine(url: str = DATABASE_URL) -> Engine:
    u = make_url(url)
    if u.drivername in ("postgres", "postgresql"):  # plain Supabase URLs -> psycopg 3 driver
        u = u.set(drivername="postgresql+psycopg")

    if u.get_backend_name() == "sqlite":
        if u.database and u.database != ":memory:":
            Path(u.database).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(u)

        @event.listens_for(engine, "connect")
        def _pragmas(conn, _):
            conn.execute("PRAGMA journal_mode=WAL")  # API can read while the job writes

        return engine

    # Remote Postgres (Supabase): drop dead pooled connections; prepare_threshold=None keeps
    # it working behind Supabase's transaction pooler (port 6543) too.
    return create_engine(u, pool_pre_ping=True, connect_args={"prepare_threshold": None})


engine = make_engine()
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def init_db(eng=None) -> None:
    from market import models  # noqa: F401  (register tables)

    Base.metadata.create_all(eng or engine)


_INSERTS = {"sqlite": sqlite_insert, "postgresql": pg_insert}


def upsert(session: Session, model, rows: Iterable[dict], chunk: int = 2000) -> int:
    """Insert rows, replacing non-key columns when the primary key already exists."""
    rows = list(rows)
    if not rows:
        return 0
    insert = _INSERTS[session.get_bind().dialect.name]
    pk = [c.name for c in model.__table__.primary_key.columns]
    for i in range(0, len(rows), chunk):
        stmt = insert(model).values(rows[i : i + chunk])
        update_cols = {c: stmt.excluded[c] for c in rows[0] if c not in pk}
        if update_cols:
            stmt = stmt.on_conflict_do_update(index_elements=pk, set_=update_cols)
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=pk)
        session.execute(stmt)
    return len(rows)
