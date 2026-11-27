"""策略一 state machine (plan/strategy-1/SKILL.md §3) on synthetic prices."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from market.metrics.strategy import (
    event_trades,
    Params,
    forward_returns,
    latest_regime,
    ma_regime,
    regime_events,
    run_regime,
    state_segments,
    swing_trades,
)

BASE_DAYS = 600


class Prices:
    """Uptrend warm-up, then each step sets the close to mean(last k closes) × mult."""

    def __init__(self):
        self.c = list(100 * 1.001 ** np.arange(BASE_DAYS))

    def add(self, k: int, mult: float, times: int = 1) -> "Prices":
        for _ in range(times):
            self.c.append(float(np.mean(self.c[-k:])) * mult)
        return self

    def below(self, k, times=1):
        return self.add(k, 0.97, times)

    def above(self, k, times=1):
        return self.add(k, 1.03, times)

    @property
    def i(self) -> int:  # index of the last day added
        return len(self.c) - 1

    def series(self) -> pd.Series:
        return pd.Series(self.c, index=pd.bdate_range("2000-01-03", periods=len(self.c)))

    def frame(self, params: Params | None = None) -> pd.DataFrame:
        return ma_regime(self.series(), params)


def row(f: pd.DataFrame, i: int) -> pd.Series:
    return f.iloc[i]


def test_warm_up_has_no_state_and_uptrend_is_bull():
    f = Prices().frame()
    assert pd.isna(f["state"].iloc[498])
    assert f["state"].iloc[499] == "BULL"
    assert (f["state"].iloc[499:] == "BULL").all()


def test_break_needs_three_closes_below():
    p = Prices().below(200, 2)
    f = p.frame()
    assert row(f, p.i)["state"] == "BULL"
    assert row(f, p.i)["confirm_days"] == 2 and row(f, p.i)["confirm_dir"] == "down"

    p.above(200)  # streak broken
    p.below(200, 2)
    assert row(p.frame(), p.i)["state"] == "BULL"

    p.below(200)
    r = row(p.frame(), p.i)
    assert (r["state"], r["event"], r["window_day"], r["window_left"]) == ("BREAK_200", "BREAK_200", 1, 20)
    assert r["episode"] == 1


def test_reclaim_inside_window_enters_swing_sleeve():
    p = Prices().below(200, 3).below(200, 5).above(200, 2)
    assert row(p.frame(), p.i)["state"] == "BREAK_200"
    p.above(200)
    f = p.frame()
    r = row(f, p.i)
    assert (r["state"], r["event"], r["zone"]) == ("RECLAIM_200", "RECLAIM_200", "ABOVE")
    assert r["pos_kind"] == "RECLAIM_200" and r["pos_share"] == 1.0 and r["pos_exit_ma"] == 50
    # Shown as RECLAIM_200 for hold_days, then BULL.
    p.add(200, 1.05, 6)
    f = p.frame()
    assert list(f["state"].iloc[-7:]) == ["RECLAIM_200"] * 5 + ["BULL"] * 2


def test_reclaim_needs_three_closes_in_a_row():
    p = Prices().below(200, 3).above(200, 2).below(200).above(200, 2)
    f = p.frame()
    assert "RECLAIM_200" not in set(f["event"].iloc[BASE_DAYS:])


@pytest.mark.parametrize("target,window", [("SPX", 21), ("BTC", 30)])
def test_observation_window_boundary(target, window):
    params = Params.for_target(target)
    assert params.window == window
    p = Prices().below(200, 3)
    confirm = p.i
    p.below(200, window - 1)  # last day of the window
    f = p.frame(params)
    assert row(f, p.i)["state"] == "BREAK_200"
    assert row(f, p.i)["window_day"] == window and row(f, p.i)["window_left"] == 0
    assert p.i - confirm + 1 == window

    p.below(200)
    r = row(p.frame(params), p.i)
    assert r["state"] in ("BEAR_200", "NEAR_500") and r["event"] == "BEAR_200"
    assert pd.isna(r["window_day"])


def test_late_reclaim_from_bear_200():
    p = Prices().below(200, 3 + 25).above(200, 3)
    f = p.frame()
    assert row(f, p.i)["event"] == "RECLAIM_200"
    assert row(f, p.i)["pos_kind"] == "RECLAIM_200"


def test_near_break_crisis_and_reclaim_500_first_only():
    p = Prices().below(200, 3).add(500, 1.01)
    f = p.frame()
    near_day = f.index[p.i]
    assert row(f, p.i)["near_500"]
    assert row(f, p.i)["event"] == "NEAR_500"  # first touch of the episode, even inside the window

    p.below(500, 3)
    r = row(p.frame(), p.i)
    assert (r["state"], r["event"], r["window_day"]) == ("BREAK_500", "BREAK_500", 1)

    p.below(500, 20)
    assert row(p.frame(), p.i)["state"] == "BREAK_500"
    p.below(500)
    r = row(p.frame(), p.i)
    assert (r["state"], r["event"]) == ("CRISIS", "CRISIS")

    p.above(500, 3)
    r = row(p.frame(), p.i)
    assert (r["state"], r["event"], r["first_500"]) == ("RECLAIM_500", "RECLAIM_500", True)
    assert r["pos_kind"] == "RECLAIM_500" and r["pos_exit_ma"] == 500 and r["episode_entered_500"]

    p.below(500, 3)  # stop: 3 closes below MA500 → sell everything (and a new MA500 break)
    r = row(p.frame(), p.i)
    assert r["exit_event"] == "EXIT_500" and r["exit_share"] == 1.0 and pd.isna(r["pos_kind"])
    assert r["state"] == "BREAK_500"

    p.above(500, 3)  # second reclaim in the same episode: no new entry
    f = p.frame()
    r = row(f, p.i)
    assert (r["event"], r["first_500"], pd.isna(r["pos_kind"])) == ("RECLAIM_500", False, True)
    assert (f["event"] == "NEAR_500").sum() == 1
    assert f.index[f["event"] == "NEAR_500"][0] == near_day


def test_reclaim_500_leaves_window_and_returns_between_averages():
    p = Prices().below(200, 3).below(500, 3).above(500, 3)
    p.add(500, 1.05, 5)  # after hold_days: above MA500, below MA200, no window
    f = p.frame()
    assert row(f, p.i)["zone"] == "BELOW200"
    assert row(f, p.i)["state"] == "BEAR_200"


def test_exit_rules_for_reclaim_200_entry():
    p = Prices().below(200, 3).above(200, 3)
    entry = p.i
    p.add(50, 1.02, 30).below(50, 3)
    f = p.frame()
    r = row(f, p.i)
    assert r["exit_event"] == "EXIT_50" and r["exit_share"] == 0.5
    assert r["pos_share"] == 0.5 and r["pos_exit_ma"] == 200

    p.below(200, 3)
    rg = run_regime(p.series())
    r = rg.frame.iloc[-1]
    assert "EXIT_200" in r["exit_event"] and pd.isna(r["pos_kind"])
    t = rg.trades[0]
    assert t.entry_i == entry and t.closed and [s for _, s in t.legs] == [0.5, 0.5]


def test_exit_counts_only_closes_after_entry():
    # Entry day closes above MA50 anyway; the first exit check needs 3 later closes below.
    p = Prices().below(200, 3).above(200, 3).below(50, 2)
    r = row(p.frame(), p.i)
    assert r["pos_kind"] == "RECLAIM_200" and r["pos_exit_days"] == 2 and r["exit_event"] == ""


def test_next_threshold_is_the_close_that_flips_the_ma():
    p = Prices().below(200, 3).below(200, 4)
    thr = row(p.frame(), p.i)["next_threshold"]
    above = Prices()
    above.c = p.c + [thr * 1.0001]
    below = Prices()
    below.c = p.c + [thr * 0.9999]
    fa, fb = above.frame(), below.frame()
    assert fa["close"].iloc[-1] > fa["ma200"].iloc[-1]
    assert fb["close"].iloc[-1] < fb["ma200"].iloc[-1]


def test_events_forward_returns_and_trades():
    p = Prices().below(200, 3).above(200, 3).add(200, 1.04, 300)
    s = p.series()
    rg = run_regime(s)
    ev = forward_returns(s, regime_events(rg.frame))
    r = ev[ev["kind"] == "RECLAIM_200"].iloc[0]
    d = ev[ev["kind"] == "RECLAIM_200"].index[0]
    j = s.index.searchsorted(d + pd.DateOffset(months=1))
    assert r["ret_1m"] == pytest.approx((s.iloc[j] / s[d] - 1) * 100)
    assert r["ret_12m"] > 0 and r["dip_12m"] <= 0

    opens = s.shift() * 1.01  # every open 1% above the previous close
    tr = swing_trades(rg, open_=opens)
    assert len(tr) == 1 and tr["open"].iloc[0]
    entry_i = rg.trades[0].entry_i
    assert tr["entry_price"].iloc[0] == pytest.approx(opens.iloc[entry_i + 1])
    # Per-event backtest trades see the same single entry here.
    assert [t.entry_i for t in event_trades(rg.frame)] == [entry_i]


def test_event_trades_evaluate_each_entry_alone():
    # RECLAIM_500 entry, then a RECLAIM_200 while the sleeve still holds it: the sleeve skips
    # the second entry, the backtest counts both.
    p = Prices().below(200, 3).below(500, 3).above(500, 3).add(200, 1.05, 3)
    rg = run_regime(p.series())
    kinds = [t.kind for t in event_trades(rg.frame)]
    assert kinds == ["RECLAIM_500", "RECLAIM_200"]
    assert [t.kind for t in rg.trades] == ["RECLAIM_500"]


def test_latest_regime_and_segments():
    p = Prices().below(200, 3).below(200, 7)
    f = p.frame()
    reg = latest_regime(f, Params())
    assert reg["state"] == "BREAK_200"
    assert reg["label"] == "跌破 200 日線・觀察期第 8 / 21 天"
    assert reg["window_left"] == 13 and reg["suggested_position"]["swing"] == 0
    assert reg["confirm"] == {"ma": 200, "dir": "up", "days": 0, "needed": 3, "next_threshold": reg["confirm"]["next_threshold"]}
    seg = state_segments(f)
    assert [s[2] for s in seg] == ["BULL", "BREAK_200"]
    assert seg[-1][1] == f.index[-1].date().isoformat()


FIXTURE = Path(__file__).parent / "data" / "gspc_2004_2023.csv"


@pytest.mark.skipif(not FIXTURE.exists(), reason="no ^GSPC fixture")
def test_gspc_snapshots():
    close = pd.read_csv(FIXTURE, index_col=0, parse_dates=True)["close"]
    f = ma_regime(close)

    def states(a, b):
        return set(f.loc[a:b, "state"])

    # 2008: below MA500 from mid-2008, CRISIS until the MA500 reclaim in Nov 2009.
    assert states("2008-07-01", "2009-11-17") == {"CRISIS"}
    assert f.loc["2009-11-18", "event"] == "RECLAIM_500"
    assert f.loc["2009-11-19", "event"] == "RECLAIM_200"  # already above MA200 (MA200 < MA500)
    # 2020: fast crash below both averages, then back to BULL from June.
    assert "BREAK_500" in states("2020-03-13", "2020-04-13")
    assert "CRISIS" in states("2020-04-14", "2020-05-08")
    assert states("2020-06-05", "2021-12-31") == {"BULL"}
    # 2022: by the rules this is also systemic (below MA500 > 21 days), reclaimed in June 2023.
    assert "CRISIS" in states("2022-10-01", "2023-05-31")
    assert f.loc["2023-06-05", "event"] == "RECLAIM_500"
    # 2004–2007 bull market: never below MA500.
    assert not states("2005-01-01", "2007-07-31") & {"BREAK_500", "CRISIS", "NEAR_500"}
