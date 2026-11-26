from market.config import TARGETS
from market.metrics import METRICS_BY_ID

# No earnings proxy at all: neither a Yahoo ETF P/E nor TWSE valuation history.
NO_EARNINGS = [t for t, cfg in TARGETS.items() if not cfg["etf"] and not cfg.get("twse")]


def test_assets_without_earnings_get_no_valuation_metrics():
    assert {"GOLD", "BTC"} <= set(NO_EARNINGS)
    for m in METRICS_BY_ID.values():
        if m.kind == "valuation":
            assert not set(NO_EARNINGS) & set(m.sources), m.id


def test_assets_without_earnings_still_get_technical_metrics():
    for metric_id in ("ma200_dev", "drawdown", "rel_strength"):
        assert set(NO_EARNINGS) <= set(METRICS_BY_ID[metric_id].sources), metric_id


def test_extra_moving_average_deviations_are_reference_only():
    for window in (240, 500):
        m = METRICS_BY_ID[f"ma{window}_dev"]
        assert m.kind == "technical"
        assert m.in_temperature is False
        assert set(TARGETS) <= set(m.sources)
    assert METRICS_BY_ID["ma200_dev"].in_temperature is True


STOCKS = [t for t, cfg in TARGETS.items() if cfg["group"] == "stock"]


def test_stocks_compare_against_taiex_not_sp500():
    assert set(STOCKS) == set(METRICS_BY_ID["rel_twii"].sources)
    assert not set(STOCKS) & set(METRICS_BY_ID["rel_strength"].sources)


def test_twse_stocks_get_full_valuation_set():
    twse_stocks = [t for t in STOCKS if TARGETS[t].get("twse")]
    assert twse_stocks
    for metric_id in ("pe_ttm", "pb", "div_yield"):
        assert set(twse_stocks) <= set(METRICS_BY_ID[metric_id].sources), metric_id
    assert METRICS_BY_ID["div_yield"].higher_is_expensive is False  # higher yield = cheaper
