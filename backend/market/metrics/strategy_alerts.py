"""策略一 alerts (plan/strategy-1/SKILL.md §9.2–9.4) for the latest day of a regime frame.

Levels: "action" 🔴 要動作 · "soon" 🟡 快觸發 · "holding" ⚪ 持有中. Days with nothing to do
return no alert (🟢 不用動). Position alerts use the strategy's virtual swing sleeve; the
browser's 倉位計算機 handles the user's own holdings.
"""

import math

import pandas as pd

from market.metrics.strategy import Params

LEVEL_ORDER = {"action": 0, "soon": 1, "holding": 2}
ENTRY_HISTORY = {
    "RECLAIM_200": "站回 200 日線",
    "RECLAIM_500": "站回 500 日線（每波第一次）",
    "NEAR_500": "靠近 500 日線（每波第一次）",
}
RECLAIM_500_WARNING = "歷史上大約 6 成會小賠出場（最多約 -18%），獲利主要來自少數幾次大反彈。照規則做，不要賠一次就停手。"


def _fmt(v: float | None) -> str:
    return "–" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:,.2f}"


def _pct(v: float) -> str:
    return f"{v:+.1f}%"


def history_line(kind: str, stats: dict | None, min_samples: int) -> str | None:
    """「站回 200 之後抱 12 個月：上漲 75%，中位數 +12.5%（指數 n=238）」; the target's own
    numbers, or its group's when it has fewer than `min_samples` events."""
    if not stats:
        return None
    for scope in ("target", "group"):
        s = (stats.get(scope) or {}).get(kind, {}).get("horizons", {}).get("12m")
        if s and s["n"] >= min_samples and s["win_pct"] is not None:
            who = f"{stats['group_name']}組合計，" if scope == "group" else ""
            return f"{ENTRY_HISTORY[kind]}之後抱 12 個月：上漲 {s['win_pct']:.0f}%，中位數 {_pct(s['median'])}（{who}n={s['n']}）"
    return "樣本不足，還沒有可信的歷史勝率"


def alerts(frame: pd.DataFrame, params: Params, stats: dict | None = None, min_samples: int = 10) -> list[dict]:
    if frame.empty or pd.isna(frame["state"].iloc[-1]):
        return []
    r = frame.iloc[-1]
    out: list[dict] = []

    def add(level: str, kind: str, title: str, lines: list[tuple[str, str]] | None = None, day: int | None = None):
        # `key` changes only when the level or the day count changes (push dedupe, §9.5).
        out.append({"level": level, "kind": kind, "title": title, "lines": [list(x) for x in lines or []],
                    "key": f"{kind}:{level}:{day if day is not None else ''}"})

    state, event, zone = r["state"], r["event"], r["zone"]
    close = r["close"]
    W = params.window
    cdays, cma, cdir, thr = int(r["confirm_days"]), int(r["confirm_ma"]), r["confirm_dir"], r["next_threshold"]
    pending = 0 < cdays < (params.reclaim_confirm if cdir == "up" else params.break_confirm)
    ma500, d500 = r["ma500"], r["dist_ma500"]
    entered_today = pd.notna(r["pos_kind"]) and r["pos_entry_date"] == frame.index[-1]

    # --- entries -----------------------------------------------------------------------------
    if event in ("RECLAIM_200", "RECLAIM_500"):
        n = 200 if event == "RECLAIM_200" else 500
        if entered_today:
            why = f"連 {params.reclaim_confirm} 天收盤站上 {n} 日線"
            if event == "RECLAIM_200":
                exits = f"連 {params.exit_confirm} 天跌破 50 日線（今天 {_fmt(r['ma50'])}）賣一半；連 {params.exit_confirm} 天跌破 200 日線賣剩下的"
                note = "剛站回的時候常常會回頭碰 50 日線，跌破 1、2 天不算數"
            else:
                exits = f"連 {params.exit_confirm} 天跌破 500 日線（今天 {_fmt(ma500)}）全部賣出"
                note = RECLAIM_500_WARNING
            lines = [("為什麼", why), ("價位", f"今天收盤 {_fmt(close)}；{n} 日線 {_fmt(r[f'ma{n}'])}")]
            hist = history_line(event, stats, min_samples)
            if hist:
                lines.append(("歷史", hist))
            lines += [("出場規則", exits), ("提醒", note)]
            add("action", f"ENTRY_{n}", "波段倉進場 30%", lines)
        elif event == "RECLAIM_500" and not r["first_500"]:
            add("holding", "RECLAIM_500_REPEAT", "站回 500 日線，但這一波已經在站回 500 時進場過，不重複進場")
        elif pd.notna(r["pos_kind"]):
            add("holding", f"RECLAIM_{n}_HELD", f"站回 {n} 日線；波段倉已經在手上（只有一份 30%），繼續抱著")

    # --- exits of the virtual sleeve -----------------------------------------------------------
    if r["exit_event"]:
        mas = [int(x.removeprefix("EXIT_")) for x in r["exit_event"].split("+")]
        rest = "全部賣出" if pd.isna(r["pos_kind"]) else f"賣一半（剩下的看 {int(r['pos_exit_ma'])} 日線）"
        add("action", "EXIT", f"連 {params.exit_confirm} 天跌破 {' / '.join(map(str, mas))} 日線 → 波段倉{rest}")

    if pd.notna(r["pos_kind"]) and not entered_today:
        k, days = int(r["pos_exit_ma"]), int(r["pos_exit_days"])
        ret = (close / r["pos_entry_price"] - 1) * 100
        sell = "賣一半" if r["pos_kind"] == "RECLAIM_200" and r["pos_share"] > 0.5 else "全部賣出"
        if 0 < days < params.exit_confirm:
            add("soon", "EXIT_PENDING", f"跌破 {k} 日線第 {days} 天，明天收盤還低於 {_fmt(r[f'thr_ma{k}'])}，就{sell}", day=days)
        elif days == 0:
            line = r[f"ma{k}"]
            add("holding", "HOLDING",
                f"波段倉 {_pct(ret)}，出場線 {k} 日線在 {_fmt(line)}（還有 {(close / line - 1) * 100:.1f}%）→ 不用動")

    # --- zone confirmations ----------------------------------------------------------------------
    if event == "BREAK_200":
        add("soon", "BREAK_200", f"跌破 200 日線，進入觀察期第 1 / {W} 天。只留底倉；手上的波段倉照出場規則走")
    elif event == "BREAK_500":
        add("soon", "BREAK_500", f"跌破 500 日線，觀察期第 1 / {W} 天。不要攤平")
    elif event == "CRISIS":
        add("action", "CRISIS", "系統性空頭：只守底倉，不攤平，等站回 500 日線")
    elif pending:
        if cdir == "down":
            add("soon", f"PENDING_BREAK_{cma}", f"跌破 {cma} 日線第 {cdays} 天，明天收盤低於 {_fmt(thr)} 就確認跌破", day=cdays)
        else:
            goal = "準備進場" if (cma == 200 or not r["episode_entered_500"]) and pd.isna(r["pos_kind"]) else "確認站回"
            add("soon", f"PENDING_RECLAIM_{cma}", f"站回 {cma} 日線第 {cdays} 天，明天收盤高於 {_fmt(thr)} 就確認 → {goal}", day=cdays)

    # --- ongoing states ----------------------------------------------------------------------------
    wl = r["window_left"]
    if not event and pd.notna(wl) and wl <= 5:
        left = int(wl)  # days after today still inside the window (same count as the badge)
        when = "今天是觀察期最後一天" if left == 0 else f"觀察期剩 {left} 天"
        if zone == "BELOW200":
            add("soon", "WINDOW_200", f"{when}，再不站回就是空頭延續，接下來看 500 日線（距離 {_pct(d500)}）", day=left)
        else:
            add("soon", "WINDOW_500", f"{when}，再不站回 500 日線就是系統性空頭", day=left)
    if state == "BEAR_200":
        add("soon", "BEAR_200", f"一個月沒站回 200，空頭延續。500 日線在 {_fmt(ma500)}（距離 {_pct(d500)}）")
    elif state == "NEAR_500":
        lines = []
        hist = history_line("NEAR_500", stats, min_samples)
        if hist:
            lines.append(("歷史", hist))
        add("soon", "NEAR_500", "接近 500 日線。底倉可以加到 40% 上限", lines)
    elif state == "CRISIS" and event != "CRISIS":
        add("soon", "CRISIS_ONGOING", "系統性空頭持續中：只守底倉，不攤平，等站回 500 日線")

    out.sort(key=lambda a: LEVEL_ORDER[a["level"]])
    return out
