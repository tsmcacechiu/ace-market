"""策略一 alerts (SKILL.md §9.4) on synthetic prices: one test per row of the table."""

from market.metrics.strategy import Params, ma_regime
from market.metrics.strategy_alerts import alerts, history_line
from tests.test_strategy_1 import Prices

STATS = {
    "target": {"RECLAIM_200": {"horizons": {"12m": {"n": 23, "win_pct": 78.0, "median": 12.5}}},
               "RECLAIM_500": {"horizons": {"12m": {"n": 3, "win_pct": 100.0, "median": 30.0}}}},
    "group": {"RECLAIM_500": {"horizons": {"12m": {"n": 92, "win_pct": 77.0, "median": 16.9}}}},
    "group_name": "指數",
}


def run(p: Prices, stats=None, params=None):
    params = params or Params()
    return alerts(p.frame(params), params, stats)


def kinds(a):
    return [(x["level"], x["kind"]) for x in a]


def test_quiet_bull_has_no_alerts():
    assert run(Prices()) == []


def test_break_pending_then_confirmed():
    a = run(Prices().below(200, 2))
    assert kinds(a) == [("soon", "PENDING_BREAK_200")]
    assert "跌破 200 日線第 2 天，明天收盤低於" in a[0]["title"] and a[0]["key"].endswith(":2")

    a = run(Prices().below(200, 3))
    assert ("soon", "BREAK_200") in kinds(a)
    assert "第 1 / 21 天" in next(x for x in a if x["kind"] == "BREAK_200")["title"]


def test_reclaim_pending_and_entry_with_history():
    a = run(Prices().below(200, 5).above(200, 2))
    assert kinds(a) == [("soon", "PENDING_RECLAIM_200")]
    assert "準備進場" in a[0]["title"]

    a = run(Prices().below(200, 5).above(200, 3), STATS)
    entry = a[0]
    assert (entry["level"], entry["kind"], entry["title"]) == ("action", "ENTRY_200", "波段倉進場 30%")
    lines = dict(entry["lines"])
    assert set(lines) == {"為什麼", "價位", "歷史", "出場規則", "提醒"}
    assert lines["歷史"] == "站回 200 日線之後抱 12 個月：上漲 78%，中位數 +12.5%（n=23）"
    assert "50 日線" in lines["出場規則"]


def test_window_running_out():
    a = run(Prices().below(200, 3).below(200, 15))  # day 16 of 21 → 5 days left after today
    w = next(x for x in a if x["kind"] == "WINDOW_200")
    assert w["level"] == "soon" and "觀察期剩 5 天" in w["title"]
    a = run(Prices().below(200, 3).below(200, 20))  # day 21: last day
    assert "今天是觀察期最後一天" in next(x for x in a if x["kind"] == "WINDOW_200")["title"]
    a = run(Prices().below(200, 3).below(200, 14))  # day 15: 6 left, no alert yet
    assert "WINDOW_200" not in [x["kind"] for x in a]


def test_bear_200_and_near_500():
    a = run(Prices().below(200, 3 + 25))
    assert ("soon", "BEAR_200") in kinds(a) or ("soon", "NEAR_500") in kinds(a)
    a = run(Prices().below(200, 3 + 25).add(500, 1.01), STATS)
    near = next(x for x in a if x["kind"] == "NEAR_500")
    assert "40% 上限" in near["title"]


def test_break_500_crisis_and_reclaim_500():
    p = Prices().below(200, 3).below(500, 3)
    assert ("soon", "BREAK_500") in kinds(run(p))
    p.below(500, 21)
    assert ("action", "CRISIS") in kinds(run(p))
    p.below(500)
    assert ("action", "CRISIS_ONGOING") in kinds(run(p))

    p.above(500, 2)
    assert ("soon", "PENDING_RECLAIM_500") in kinds(run(p))
    p.above(500)
    a = run(p, STATS)
    entry = a[0]
    assert (entry["level"], entry["kind"]) == ("action", "ENTRY_500")
    lines = dict(entry["lines"])
    assert "指數組合計，n=92" in lines["歷史"]  # own n=3 < 10 → group numbers
    assert "6 成會小賠" in lines["提醒"]

    p.below(500, 3)  # stopped out
    assert ("action", "EXIT") in kinds(run(p))
    p.above(500, 3)  # second reclaim in the same episode
    assert ("holding", "RECLAIM_500_REPEAT") in kinds(run(p))


def test_holding_exit_pending_and_exit():
    p = Prices().below(200, 3).above(200, 3).add(50, 1.02, 30)
    h = next(x for x in run(p) if x["kind"] == "HOLDING")
    assert h["level"] == "holding" and "出場線 50 日線" in h["title"] and "不用動" in h["title"]

    p.below(50, 2)
    e = next(x for x in run(p) if x["kind"] == "EXIT_PENDING")
    assert "跌破 50 日線第 2 天" in e["title"] and e["title"].endswith("就賣一半")

    p.below(50)
    e = next(x for x in run(p) if x["kind"] == "EXIT")
    assert e["level"] == "action" and "賣一半（剩下的看 200 日線）" in e["title"]


def test_alerts_sorted_action_first():
    p = Prices().below(200, 3).below(500, 3).below(500, 21)
    a = run(p)
    assert a[0]["level"] == "action"


def test_history_line_sample_size():
    assert history_line("NEAR_500", STATS, 10) == "樣本不足，還沒有可信的歷史勝率"
    assert history_line("RECLAIM_200", None, 10) is None
