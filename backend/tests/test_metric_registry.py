from market.config import TARGETS
from market.metrics import METRICS_BY_ID

NO_EARNINGS = [t for t, cfg in TARGETS.items() if not cfg["etf"]]


def test_assets_without_earnings_get_no_valuation_metrics():
    assert {"GOLD", "BTC"} <= set(NO_EARNINGS)
    for m in METRICS_BY_ID.values():
        if m.kind == "valuation":
            assert not set(NO_EARNINGS) & set(m.sources), m.id


def test_assets_without_earnings_still_get_technical_metrics():
    for metric_id in ("ma200_dev", "drawdown", "rel_strength"):
        assert set(NO_EARNINGS) <= set(METRICS_BY_ID[metric_id].sources), metric_id
