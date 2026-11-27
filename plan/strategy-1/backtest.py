"""Strategy 1 backtest for the two open questions in SKILL.md §7.

Q1: stop rule for the swing sleeve entered on RECLAIM_500.
Q2: take-profit / exit scheme for the swing sleeve entered on RECLAIM_200.

Run from the repo root:
    uv run --directory backend python ../plan/strategy-1/backtest.py            # reads DATABASE_URL / SQLite
    uv run --directory backend python ../plan/strategy-1/backtest.py --csv DIR  # reads DIR/<target>.csv

Each trade is evaluated on its own (entry at the close of the confirming day, exits at the
close of the triggering day, no costs). Trades still open at the last date are marked to market.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

BREAK_CONFIRM = 3
RECLAIM_CONFIRM = 3
WINDOW = {"BTC": 30}
DEFAULT_WINDOW = 21
TARGET_IDS = ["SPX", "NDX", "SOX", "TWII", "GOLD", "BTC", "0050", "2330", "2454"]
INDEXES = {"SPX", "NDX", "SOX", "TWII"}


# Fixes for known problems in stored prices. Empty since 2026-11-28: 個股 prices are now rebuilt
# from TWSE (backend/market/tw_prices.py). Exports made before that need
# SPLIT_FIX = {"0050": ("2014-01-02", 4.0)} and TRIM_BEFORE = {"2454": "2007-01-01"}.
SPLIT_FIX: dict[str, tuple[str, float]] = {}
TRIM_BEFORE: dict[str, str] = {}


def clean(tid: str, obj):
    """Apply SPLIT_FIX / TRIM_BEFORE to a price Series or an open/close DataFrame."""
    if tid in SPLIT_FIX:
        day, ratio = SPLIT_FIX[tid]
        obj = obj.copy()
        obj.loc[obj.index < pd.Timestamp(day)] /= ratio
    if tid in TRIM_BEFORE:
        obj = obj[obj.index >= pd.Timestamp(TRIM_BEFORE[tid])]
    return obj


def load(csv_dir: str | None) -> dict[str, pd.Series]:
    if csv_dir:
        out = {}
        for tid in TARGET_IDS:
            df = pd.read_csv(Path(csv_dir) / f"{tid}.csv", index_col=0, parse_dates=True)
            out[tid] = clean(tid, df["close"] if "close" in df else df.iloc[:, 0]).dropna()
        return out
    from market.config import TARGETS
    from market.db import SessionLocal
    from market.store import DataStore

    with SessionLocal() as s:
        st = DataStore(s)
        return {tid: clean(tid, st.close(TARGETS[tid]["index"]).dropna()) for tid in TARGET_IDS}


@dataclass
class Event:
    kind: str  # RECLAIM_200 | RECLAIM_500
    i: int  # index of the confirming day (entry)
    quick: bool  # reclaimed inside the observation window (vs late / from BEAR_200 or CRISIS)
    episode: int  # increments every time the price breaks below MA200 from ABOVE


def regime_events(close: pd.Series, window: int) -> list[Event]:
    """Walk the SKILL.md state machine and return the entry events."""
    c = close.values
    ma200 = close.rolling(200).mean().values
    ma500 = close.rolling(500).mean().values
    start = 499
    state = "ABOVE" if c[start] > ma200[start] else "BELOW200"
    run_up200 = run_dn200 = run_up500 = run_dn500 = 0
    break200_i = break500_i = start
    events: list[Event] = []
    episode = 0
    for i in range(start, len(c)):
        run_up200 = run_up200 + 1 if c[i] > ma200[i] else 0
        run_dn200 = run_dn200 + 1 if c[i] < ma200[i] else 0
        run_up500 = run_up500 + 1 if c[i] > ma500[i] else 0
        run_dn500 = run_dn500 + 1 if c[i] < ma500[i] else 0
        if state == "ABOVE":
            if run_dn200 >= BREAK_CONFIRM:
                state, break200_i = "BELOW200", i
                episode += 1
        elif state == "BELOW200":
            if run_up200 >= RECLAIM_CONFIRM:
                events.append(Event("RECLAIM_200", i, i - break200_i <= window, episode))
                state = "ABOVE"
            elif run_dn500 >= BREAK_CONFIRM:
                state, break500_i = "BELOW500", i
        elif state == "BELOW500":
            if run_up500 >= RECLAIM_CONFIRM:
                events.append(Event("RECLAIM_500", i, i - break500_i <= window, episode))
                state, break200_i = "BELOW200", i  # back between the two averages
    return events


# --- exit rules -----------------------------------------------------------------------
# Each rule returns a list of (exit_index, weight) legs; weights sum to 1.


def _first(cond: np.ndarray, frm: int) -> int | None:
    hit = np.flatnonzero(cond[frm:])
    return int(frm + hit[0]) if len(hit) else None


def make_rules(close: pd.Series, confirm: int = 1) -> dict:
    c = close.values
    ma = {n: close.rolling(n).mean().values for n in (20, 50, 200, 500)}
    last = len(c) - 1
    # True on the day the close has been below MA(n) for `confirm` days in a row.
    under = {n: pd.Series(c < ma[n]).rolling(confirm).sum().eq(confirm).values for n in ma}

    def below(n, frm):
        j = _first(under[n], frm + confirm - 1)
        return last if j is None else j

    def all_out(n):
        return lambda e: [(below(n, e + 1), 1.0)]

    def split(n1, n2):
        def f(e):
            a = below(n1, e + 1)
            b = below(n2, a)  # second half can exit the same day
            return [(a, 0.5), (b, 0.5)]

        return f

    def targets_then(n, levels=(0.10, 0.20)):
        def f(e):
            stop = below(n, e + 1)
            legs, w = [], 1 / (len(levels) + 1)
            for lv in levels:
                j = _first(c >= c[e] * (1 + lv), e + 1)
                legs.append((j if j is not None and j < stop else stop, w))
            legs.append((stop, w))
            return legs

        return f

    def hybrid500(e):
        # MA500 stop until price closes back above MA200, then trail on MA50.
        j500 = below(500, e + 1)
        up = _first(c > ma[200], e + 1)
        if up is None or up >= j500:
            return [(j500, 1.0)]
        return [(below(50, up + 1), 1.0)]

    return {
        "q1": {
            "MA20": all_out(20),
            "MA50": all_out(50),
            "MA500": all_out(500),
            "MA500→站回200後改MA50": hybrid500,
        },
        "q2": {
            "MA20 全出": all_out(20),
            "MA50 全出": all_out(50),
            "MA20 出半、MA50 出半": split(20, 50),
            "+10%/+20% 各 1/3、剩下 MA50": targets_then(50),
            "MA50 出半、MA200 出半": split(50, 200),
        },
    }


def trade(close: np.ndarray, e: int, legs, last: int) -> dict:
    ret = sum(w * (close[j] / close[e] - 1) for j, w in legs)
    days = max(j for j, _ in legs) - e
    open_ = any(j == last for j, _ in legs)
    fwd12 = close[min(e + 252, last)] / close[e] - 1
    return {"ret": ret, "days": days, "open": open_, "bh12": fwd12}


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}
    r = np.array([x["ret"] for x in rows])
    return {
        "n": len(r),
        "win": (r > 0).mean() * 100,
        "mean": r.mean() * 100,
        "median": np.median(r) * 100,
        "worst": r.min() * 100,
        "best": r.max() * 100,
        "days": np.median([x["days"] for x in rows]),
        "bh12": np.mean([x["bh12"] for x in rows]) * 100,
        "open": sum(x["open"] for x in rows),
    }


def fmt(name: str, s: dict) -> str:
    if s["n"] == 0:
        return f"| {name} | 0 | – | – | – | – | – |"
    return (
        f"| {name} | {s['n']} | {s['win']:.0f}% | {s['mean']:+.1f}% | {s['median']:+.1f}% "
        f"| {s['worst']:+.1f}% | {s['days']:.0f} |"
    )


HEADER = "| 規則 | 次數 | 勝率 | 平均報酬 | 中位數 | 最差 | 持有天數（中位數） |\n|---|---|---|---|---|---|---|"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv")
    ap.add_argument("--confirm", type=int, default=1, help="closes below the MA in a row to exit")
    ap.add_argument("--first-only", action="store_true", help="only the first RECLAIM_500 per episode")
    ap.add_argument("--brief", action="store_true", help="skip the per-target tables")
    args = ap.parse_args()
    data = load(args.csv)

    trades = {"q1": {}, "q2": {}}  # question -> rule -> group -> rows
    per_target = {"q1": {}, "q2": {}}
    counts = {}
    for tid, close in data.items():
        if len(close) < 600:
            continue
        evs = regime_events(close, WINDOW.get(tid, DEFAULT_WINDOW))
        if args.first_only:
            seen, kept = set(), []
            for e in evs:
                if e.kind == "RECLAIM_500":
                    if e.episode in seen:
                        continue
                    seen.add(e.episode)
                kept.append(e)
            evs = kept
        counts[tid] = (sum(e.kind == "RECLAIM_200" for e in evs), sum(e.kind == "RECLAIM_500" for e in evs))
        rules = make_rules(close, args.confirm)
        c, last = close.values, len(close) - 1
        group = "指數" if tid in INDEXES else "其他"
        for q, kind in (("q1", "RECLAIM_500"), ("q2", "RECLAIM_200")):
            for name, rule in rules[q].items():
                for e in (e for e in evs if e.kind == kind and e.i < last):
                    row = trade(c, e.i, rule(e.i), last)
                    trades[q].setdefault(name, {}).setdefault(group, []).append(row)
                    trades[q][name].setdefault("全部", []).append(row)
                    per_target[q].setdefault(name, {}).setdefault(tid, []).append(row)

    print("## 事件次數（RECLAIM_200 / RECLAIM_500）\n")
    print(" · ".join(f"{t} {a}/{b}" for t, (a, b) in counts.items()), "\n")

    titles = {"q1": "Q1：站回 500 進場的停損", "q2": "Q2：站回 200 進場的出場方式"}
    for q in ("q1", "q2"):
        for group in ("全部", "指數", "其他"):
            print(f"### {titles[q]} — {group}\n")
            print(HEADER)
            for name, g in trades[q].items():
                print(fmt(name, summarize(g.get(group, []))))
            any_rows = next(iter(trades[q].values())).get(group, [])
            if any_rows:
                print(f"\n（同一批進場點直接抱 12 個月的平均報酬：{summarize(any_rows)['bh12']:+.1f}%）\n")
        if args.brief:
            continue
        print(f"### {titles[q]} — 各標的平均報酬\n")
        names = list(trades[q])
        print("| 標的 | " + " | ".join(names) + " |\n|---|" + "---|" * len(names))
        for tid in counts:
            cells = []
            for name in names:
                rows = per_target[q][name].get(tid, [])
                s = summarize(rows)
                cells.append("–" if s["n"] == 0 else f"{s['mean']:+.1f}% ({s['win']:.0f}%, n={s['n']})")
            print(f"| {tid} | " + " | ".join(cells) + " |")
        print()


if __name__ == "__main__":
    main()
