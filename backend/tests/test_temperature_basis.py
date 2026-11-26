from dataclasses import replace

import pandas as pd

from market.api import main
from market.metrics import METRICS_BY_ID

DATES = pd.date_range("2020-01-31", periods=36, freq="ME")


class FakeStore:
    session = None

    def close(self, symbol):
        return pd.Series(range(1, 37), index=DATES, dtype=float)

    def metric(self, metric_id, target):
        # "high" ends at its all-time high (expensive); "low" ends at its low (cheap).
        values = range(36) if metric_id == "high" else range(36, 0, -1)
        return pd.Series(values, index=DATES, dtype=float)


def test_reference_only_metrics_do_not_move_the_temperature(monkeypatch):
    base = METRICS_BY_ID["ma200_dev"]
    counted = replace(base, id="high", sources={"SPX": "x"})
    reference = replace(base, id="low", sources={"SPX": "x"}, in_temperature=False)
    monkeypatch.setattr(main, "METRICS", [counted, reference])
    monkeypatch.setattr(main, "TARGETS", {"SPX": main.TARGETS["SPX"]})

    spx = main._build_dashboard(FakeStore(), None)["targets"][0]

    assert spx["metrics"]["low"] is not None  # still shown in the table
    assert spx["temperature"] == spx["metrics"]["high"]["expensiveness"]  # only "high" counts
    assert spx["temperature_basis"] == {"valuation": 0, "technical": 1}
