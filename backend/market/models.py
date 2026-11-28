from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from market.db import Base


class Price(Base):
    """Daily OHLCV for indices."""

    __tablename__ = "prices"
    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)


class Observation(Base):
    """Raw values from external sources (FRED, multpl, ETF P/E snapshots)."""

    __tablename__ = "raw_observations"
    source: Mapped[str] = mapped_column(String, primary_key=True)  # fred | multpl | yahoo_etf_pe | twse
    series_id: Mapped[str] = mapped_column(String, primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    value: Mapped[float] = mapped_column(Float)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)


class MetricValue(Base):
    """Computed metric history, fully recomputed on every job run."""

    __tablename__ = "metric_values"
    metric_id: Mapped[str] = mapped_column(String, primary_key=True)
    target: Mapped[str] = mapped_column(String, primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    value: Mapped[float] = mapped_column(Float)


class JobRun(Base):
    __tablename__ = "job_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String)  # running | ok | partial | failed
    detail: Mapped[str | None] = mapped_column(Text)


class StrategySignal(Base):
    """策略一 🔴 / 🟡 alerts as the daily job saw them (SKILL.md §9.5–9.6).

    One row per target, trading day and alert kind. `sent_at` is set once the alert went out to
    Discord, so a re-run of the job on the same day never sends it twice.
    """

    __tablename__ = "strategy_signals"
    target: Mapped[str] = mapped_column(String, primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    kind: Mapped[str] = mapped_column(String, primary_key=True)
    level: Mapped[str] = mapped_column(String)  # action | soon
    key: Mapped[str] = mapped_column(String)  # changes only when the level or day count changes
    price: Mapped[float] = mapped_column(Float)  # close on `date`
    title: Mapped[str] = mapped_column(Text)
    lines: Mapped[str | None] = mapped_column(Text)  # JSON [[label, text], ...]
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
