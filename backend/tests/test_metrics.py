import pandas as pd
import pytest

from market.collectors.multpl import parse_table
from market.metrics import calc
from market.metrics.scoring import expensiveness, score, temperature


def s(values, start="2020-01-01", freq="D"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq=freq), dtype=float)


def test_drawdown_is_zero_at_highs_and_negative_below():
    dd = calc.drawdown(s([100, 120, 90, 120, 130]))
    assert dd.tolist() == pytest.approx([0, 0, -25, 0, 0])


def test_ma_deviation():
    dev = calc.ma_deviation(s([10, 10, 10, 13]), window=4)
    assert dev.iloc[-1] == pytest.approx(13 / 10.75 * 100 - 100)
    assert len(dev) == 1


def test_relative_strength_flat_when_moving_together():
    a = s([100, 110, 121, 133.1])
    rel = calc.relative_strength_deviation(a, a * 2, window=2)
    assert rel.tolist() == pytest.approx([0, 0, 0])


def test_erp_pairs_pe_with_latest_prior_yield():
    pe = s([20, 25], start="2024-01-10", freq="MS")  # dated 2024-02-01, 2024-03-01
    y = pd.Series([4.0, 3.0], index=pd.to_datetime(["2024-01-31", "2024-02-20"]))
    erp = calc.earnings_yield_spread(pe, y)
    assert erp.tolist() == pytest.approx([5 - 4.0, 4 - 3.0])


def test_buffett_dates_at_quarter_end_and_extends_with_wilshire():
    q = pd.to_datetime(["2025-01-01", "2025-04-01"])
    equity_mil = pd.Series([40_000_000.0, 50_000_000.0], index=q)  # 40k / 50k billion
    gdp_bil = pd.Series([20_000.0, 25_000.0], index=q)
    wilshire = pd.Series([100.0, 110.0], index=pd.to_datetime(["2025-06-30", "2025-07-15"]))

    out = calc.buffett_indicator(equity_mil, gdp_bil, wilshire)
    assert out.index.tolist() == pd.to_datetime(["2025-03-31", "2025-06-30", "2025-07-15"]).tolist()
    assert out.tolist() == pytest.approx([200, 200, 220])


def test_score_percentile_and_bands():
    hist = s(list(range(1, 25)), freq="ME")  # 24 months: 1..24
    sc = score(hist, years=30, min_months=12)
    assert sc.value == 24
    assert sc.percentile == pytest.approx((23 + 0.5) / 24 * 100)
    assert sc.bands["p50"] == pytest.approx(12.5)


def test_score_withholds_percentile_until_enough_history():
    sc = score(s([1.0, 2.0, 3.0]), min_months=12)
    assert sc.value == 3 and sc.percentile is None and sc.bands is None


def test_expensiveness_and_temperature():
    assert expensiveness(80, True) == 80
    assert expensiveness(80, False) == 20
    assert expensiveness(None, True) is None
    # valuation weighs 2, technical 1: (2*90 + 1*30) / 3
    assert temperature([("valuation", 90), ("technical", 30), ("technical", None)]) == pytest.approx(70)
    assert temperature([("valuation", None)]) is None


def test_multpl_parser_handles_markers_and_duplicates():
    html = """<table><tr><th>Date</th><th>Value</th></tr>
    <tr><td>Nov 20, 2026</td><td>&#x2002;36.44</td></tr>
    <tr><td>Nov 1, 2026</td><td>39.82 †</td></tr>
    <tr><td>Oct 1, 2026</td><td>40.60</td></tr></table>"""
    out = parse_table(html)
    assert out.index.tolist() == pd.to_datetime(["2026-10-01", "2026-11-01", "2026-11-20"]).tolist()
    assert out.tolist() == pytest.approx([40.60, 39.82, 36.44])
