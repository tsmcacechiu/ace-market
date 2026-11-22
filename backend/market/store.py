"""Read stored data back as pandas Series."""

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from market.models import MetricValue, Observation, Price


def _to_series(rows, name: str) -> pd.Series:
    if not rows:
        return pd.Series(dtype=float, name=name)
    idx, vals = zip(*rows)
    return pd.Series(vals, index=pd.DatetimeIndex(idx), name=name, dtype=float).sort_index()


class DataStore:
    def __init__(self, session: Session):
        self.session = session

    def close(self, symbol: str) -> pd.Series:
        rows = self.session.execute(
            select(Price.date, Price.close).where(Price.symbol == symbol)
        ).all()
        return _to_series(rows, symbol)

    def observations(self, source: str, series_id: str) -> pd.Series:
        rows = self.session.execute(
            select(Observation.date, Observation.value).where(
                Observation.source == source, Observation.series_id == series_id
            )
        ).all()
        return _to_series(rows, series_id)

    def metric(self, metric_id: str, target: str) -> pd.Series:
        rows = self.session.execute(
            select(MetricValue.date, MetricValue.value).where(
                MetricValue.metric_id == metric_id, MetricValue.target == target
            )
        ).all()
        return _to_series(rows, f"{metric_id}:{target}")
