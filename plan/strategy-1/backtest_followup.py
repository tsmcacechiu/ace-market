"""Follow-up backtests for SKILL.md §7, using the exit rules decided in §2.

A. Execution timing: the site sees a signal at 06:30 the next morning, so the earliest fill is
   the next session's open. Compare "fill at the signal day's close" with "fill at the next open".
B. Max-loss cap: also exit when a close is X% below the entry price, on top of the MA exits.

Rules: RECLAIM_500 (first per episode) → out on 3 closes below MA500.
       RECLAIM_200 → half out on 3 closes below MA50, the rest on 3 closes below MA200.

Run from backend/:  uv run python ../plan/strategy-1/backtest_followup.py --csv DIR
where DIR/<target>.csv has date,open,close (or omit --csv to read the database).
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from backtest import DEFAULT_WINDOW, clean, INDEXES, TARGET_IDS, WINDOW, make_rules, regime_events

CONFIRM = 3
CAPS = (None, 0.10, 0.15, 0.20, 0.25)
# Yahoo has no real opens for ^GSPC before 1962 (open == close).
OPEN_VALID_FROM = {"SPX": "1962-01-02"}
MAX_OPEN_GAP = 0.10


def load(csv_dir: str | None) -> dict[str, pd.DataFrame]:
    if csv_dir:
        frames = {
            tid: pd.read_csv(Path(csv_dir) / f"{tid}.csv", index_col=0, parse_dates=True) for tid in TARGET_IDS
        }
    else:
        from sqlalchemy import select

        from market.config import TARGETS
        from market.db import SessionLocal
        from market.models import Price

        frames = {}
        with SessionLocal() as s:
            for tid in TARGET_IDS:
                rows = s.execute(
                    select(Price.date, Price.open, Price.close).where(Price.symbol == TARGETS[tid]["index"])
                ).all()
                df = pd.DataFrame(rows, columns=["date", "open", "close"]).set_index("date").sort_index()
                df.index = pd.DatetimeIndex(df.index)
                frames[tid] = df
    out = {}
    for tid, df in frames.items():
        df = clean(tid, df.dropna(subset=["close"]))
        bad = df["open"].isna() | (df["open"] <= 0)
        if tid in OPEN_VALID_FROM:
            bad |= df.index < pd.Timestamp(OPEN_VALID_FROM[tid])
        # Opens more than 10% away from the previous close are Yahoo bad ticks (TW limit is 7–10%).
        bad |= (df["open"] / df["close"].shift() - 1).abs() > MAX_OPEN_GAP
        df = df.assign(open=df["open"].where(~bad))
        out[tid] = df
    return out


def legs_for(kind: str, rules: dict, e: int):
    return rules["q1"]["MA500"](e) if kind == "RECLAIM_500" else rules["q2"]["MA50 出半、MA200 出半"](e)


def apply_cap(legs, c: np.ndarray, e: int, cap: float | None, last: int):
    if cap is None:
        return legs
    hit = np.flatnonzero(c[e + 1 :] <= c[e] * (1 - cap))
    if not len(hit):
        return legs
    k = e + 1 + int(hit[0])
    return [(min(j, k), w) for j, w in legs]


def fill(o: np.ndarray, c: np.ndarray, j: int, mode: str, last: int) -> float | None:
    """Price we trade at for a signal confirmed at the close of day j."""
    if mode == "close" or j >= last:  # still open at the end → mark at the last close
        return c[min(j, last)]
    return o[j + 1] if not np.isnan(o[j + 1]) else None


def evaluate(data: dict, cap: float | None, mode: str, same_sample: bool):
    rows = []
    for tid, df in data.items():
        close = df["close"]
        if len(close) < 600:
            continue
        c, o, last = close.values, df["open"].values, len(close) - 1
        rules = make_rules(close, CONFIRM)
        seen = set()
        for ev in regime_events(close, WINDOW.get(tid, DEFAULT_WINDOW)):
            if ev.i >= last:
                continue
            if ev.kind == "RECLAIM_500":
                if ev.episode in seen:
                    continue
                seen.add(ev.episode)
            legs = apply_cap(legs_for(ev.kind, rules, ev.i), c, ev.i, cap, last)
            # Both modes are measured on events where every next-open fill exists.
            needed = [ev.i] + [j for j, _ in legs]
            if same_sample and any(j < last and np.isnan(o[j + 1]) for j in needed):
                continue
            p_in = fill(o, c, ev.i, mode, last)
            outs = [(fill(o, c, j, mode, last), w) for j, w in legs]
            if p_in is None or any(p is None for p, _ in outs):
                continue
            rows.append(
                {
                    "target": tid,
                    "group": "指數" if tid in INDEXES else "其他",
                    "kind": ev.kind,
                    "date": close.index[ev.i].date(),
                    "ret": sum(w * (p / p_in - 1) for p, w in outs),
                    "days": max(j for j, _ in legs) - ev.i,
                }
            )
    return pd.DataFrame(rows)


def stats(df: pd.DataFrame) -> str:
    if df.empty:
        return "| 0 | – | – | – | – | – |"
    r = df["ret"] * 100
    return (
        f"| {len(r)} | {(r > 0).mean() * 100:.0f}% | {r.mean():+.1f}% | {r.median():+.1f}% "
        f"| {r.min():+.1f}% | {df['days'].median():.0f} |"
    )


HEAD = "| 次數 | 勝率 | 平均 | 中位數 | 最差 | 持有天數 |"
KINDS = {"RECLAIM_500": "站回 500（MA500 停損）", "RECLAIM_200": "站回 200（MA50 半、MA200 半）"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv")
    args = ap.parse_args()
    data = load(args.csv)

    print("## A. 執行時間：確認當天收盤 vs 隔天開盤（同一批樣本）\n")
    print("| 進場點 | 組別 | 成交價 " + HEAD + "\n|---|---|---|---|---|---|---|---|---|")
    res = {m: evaluate(data, None, m, True) for m in ("close", "next_open")}
    for kind, label in KINDS.items():
        for g in ("指數", "其他"):
            for m, mlabel in (("close", "當天收盤"), ("next_open", "隔天開盤")):
                d = res[m]
                print(f"| {label} | {g} | {mlabel} " + stats(d[(d.kind == kind) & (d.group == g)]))
    print()

    print("## B. 加最大虧損上限（隔天開盤成交，同一批樣本）\n")
    print("| 進場點 | 組別 | 上限 " + HEAD + "\n|---|---|---|---|---|---|---|---|---|")
    capped = {cap: evaluate(data, cap, "next_open", True) for cap in CAPS}
    for kind, label in KINDS.items():
        for g in ("指數", "其他"):
            for cap, d in capped.items():
                name = "無" if cap is None else f"-{cap * 100:.0f}%"
                print(f"| {label} | {g} | {name} " + stats(d[(d.kind == kind) & (d.group == g)]))
    print()

    print("## 最差的 5 筆（無上限，隔天開盤）\n")
    d = capped[None].sort_values("ret").head(5)
    for _, r in d.iterrows():
        print(f"- {r.target} {r.date} {KINDS[r.kind]}：{r.ret * 100:+.1f}%，持有 {r.days} 天")


if __name__ == "__main__":
    main()
