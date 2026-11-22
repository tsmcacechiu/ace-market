from collections.abc import Iterable

from sqlalchemy import create_engine, event
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from market.config import DB_PATH


class Base(DeclarativeBase):
    pass


def make_engine(path=DB_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def _pragmas(conn, _):
        conn.execute("PRAGMA journal_mode=WAL")  # API can read while the job writes

    return engine


engine = make_engine()
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def init_db(eng=None) -> None:
    from market import models  # noqa: F401  (register tables)

    Base.metadata.create_all(eng or engine)


def upsert(session: Session, model, rows: Iterable[dict], chunk: int = 2000) -> int:
    """Insert rows, replacing non-key columns when the primary key already exists."""
    rows = list(rows)
    if not rows:
        return 0
    pk = [c.name for c in model.__table__.primary_key.columns]
    for i in range(0, len(rows), chunk):
        stmt = sqlite_insert(model).values(rows[i : i + chunk])
        update_cols = {c: stmt.excluded[c] for c in rows[0] if c not in pk}
        if update_cols:
            stmt = stmt.on_conflict_do_update(index_elements=pk, set_=update_cols)
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=pk)
        session.execute(stmt)
    return len(rows)
