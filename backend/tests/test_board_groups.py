import pandas as pd

from market.api import main
from market.config import TARGETS


class EmptyStore:
    session = None

    def close(self, symbol):
        return pd.Series(dtype=float)

    def metric(self, metric_id, target):
        return pd.Series(dtype=float)


def _board(group):
    board = main._build_dashboard(EmptyStore(), None, group)
    return {t["id"] for t in board["targets"]}, {m["id"] for m in board["metrics"]}


def test_home_board_has_only_market_assets_and_their_metrics():
    targets, metrics = _board("market")
    assert targets == {t for t, cfg in TARGETS.items() if cfg["group"] == "market"}
    assert {"cape", "rel_strength"} <= metrics
    assert not {"pb", "div_yield", "rel_twii"} & metrics


def test_stock_board_has_only_stocks_and_their_metrics():
    targets, metrics = _board("stock")
    assert targets == {"0050", "2330", "2454"}
    assert {"pe_ttm", "pb", "div_yield", "rel_twii", "ma200_dev"} <= metrics
    assert not {"cape", "buffett", "erp", "rel_strength"} & metrics
