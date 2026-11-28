"""策略一：200 / 500 日線多空判讀＋分層倉位 (plan/strategy-1/SKILL.md).

`run_regime` walks the state machine of SKILL.md §3 over a close series and also runs the
strategy's virtual swing sleeve (one 30% slot, exits per §2). `regime_events`,
`forward_returns`, `swing_trades` and `event_stats` turn that into the backtest of §4.

Everything works on closes only; day counts are rows (trading days).
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from market.config import RECLAIM_WINDOW_DAYS_OVERRIDE, STRATEGY_1

MA_SET = (20, 50, 200, 500)
HORIZONS_MONTHS = (1, 3, 6, 12)
EVENT_KINDS = ("RECLAIM_200", "BEAR_200", "NEAR_500", "RECLAIM_500", "CRISIS")
ENTRY_KINDS = ("RECLAIM_200", "RECLAIM_500")

# state -> (label, color key, suggested position text)
STATES: dict[str, tuple[str, str, str]] = {
    "BULL": ("多頭（站上 200 日線）", "green", "底倉 30–40% ＋ 波段 30%"),
    "BREAK_200": ("跌破 200 日線", "yellow", "只有底倉"),
    "RECLAIM_200": ("站回 200 日線", "lime", "底倉＋加波段 30%"),
    "BEAR_200": ("空頭延續（一個月沒站回 200）", "orange", "只有底倉"),
    "NEAR_500": ("靠近 500 日線", "blue", "底倉加到 40% 上限"),
    "BREAK_500": ("跌破 500 日線", "red", "只有底倉"),
    "RECLAIM_500": ("站回 500 日線", "cyan", "底倉＋加波段 30%"),
    "CRISIS": ("系統性空頭（一個月沒站回 500）", "darkred", "只有底倉，不攤平"),
}
SUGGESTED = {
    "BULL": {"base": [30, 40], "swing": 30},
    "BREAK_200": {"base": [30, 40], "swing": 0},
    "RECLAIM_200": {"base": [30, 40], "swing": 30},
    "BEAR_200": {"base": [30, 40], "swing": 0},
    "NEAR_500": {"base": [40, 40], "swing": 0},
    "BREAK_500": {"base": [30, 40], "swing": 0},
    "RECLAIM_500": {"base": [30, 40], "swing": 30},
    "CRISIS": {"base": [30, 40], "swing": 0},
}


@dataclass(frozen=True)
class Params:
    break_confirm: int = STRATEGY_1["BREAK_CONFIRM_DAYS"]
    reclaim_confirm: int = STRATEGY_1["RECLAIM_CONFIRM_DAYS"]
    window: int = STRATEGY_1["RECLAIM_WINDOW_DAYS"]
    touch_band_pct: float = STRATEGY_1["TOUCH_BAND_PCT"]
    exit_confirm: int = STRATEGY_1["EXIT_CONFIRM_DAYS"]
    exit_500: tuple = tuple(STRATEGY_1["EXIT_RECLAIM_500"])
    exit_200: tuple = tuple(STRATEGY_1["EXIT_RECLAIM_200"])
    first_only: bool = STRATEGY_1["RECLAIM_500_FIRST_ONLY"]
    hold_days: int = STRATEGY_1["RECLAIM_HOLD_DAYS"]

    @classmethod
    def for_target(cls, target: str) -> "Params":
        return cls(window=RECLAIM_WINDOW_DAYS_OVERRIDE.get(target, STRATEGY_1["RECLAIM_WINDOW_DAYS"]))


@dataclass
class Trade:
    kind: str  # RECLAIM_200 | RECLAIM_500
    entry_i: int
    legs: list[tuple[int, float]] = field(default_factory=list)  # (exit day index, share sold)

    @property
    def closed(self) -> bool:
        return sum(s for _, s in self.legs) >= 1 - 1e-9


@dataclass
class Regime:
    frame: pd.DataFrame  # one row per day, see run_regime
    trades: list[Trade]  # virtual swing sleeve, in order


def _runs(cond: np.ndarray) -> np.ndarray:
    """Length of the streak of True ending on each day."""
    out = np.zeros(len(cond), dtype=int)
    run = 0
    for i, v in enumerate(cond):
        run = run + 1 if v else 0
        out[i] = run
    return out


def run_regime(close: pd.Series, params: Params | None = None) -> Regime:
    """Daily state, events and virtual swing position.

    Frame columns: close, ma20/50/200/500, zone (ABOVE | BELOW200 | BELOW500), state,
    days_in_state, event (BREAK_200 | RECLAIM_200 | BEAR_200 | NEAR_500 | BREAK_500 |
    RECLAIM_500 | CRISIS | ""), first_500 (RECLAIM_500 is the episode's first), episode,
    episode_entered_500, near_500, window_day / window_left (observation period, else NaN),
    confirm_ma / confirm_dir / confirm_days / next_threshold (pending confirmation and the close
    needed tomorrow), dist_ma50/200/500 (%), pos_kind / pos_share / pos_entry_date /
    pos_entry_price / pos_exit_ma / pos_exit_days / pos_exit_threshold, exit_event / exit_share.
    Rows before MA500 exists have state None.
    """
    p = params or Params()
    close = close.dropna().astype(float).sort_index()
    c = close.to_numpy()
    n = len(c)
    ma = {k: close.rolling(k).mean().to_numpy() for k in MA_SET}
    # Tomorrow's close x moves MA(k) to (S + x) / k, S = sum of the last k-1 closes, so
    # x > MA(k) tomorrow ⇔ x > S / (k-1) = mean of the last k-1 closes.
    thr = {k: close.rolling(k - 1).mean().to_numpy() for k in MA_SET}
    with np.errstate(invalid="ignore"):
        up = {k: _runs(c > ma[k]) for k in (50, 200, 500)}
        dn = {k: _runs(c < ma[k]) for k in (50, 200, 500)}

    cols: dict[str, list] = {
        k: [None] * n
        for k in (
            "zone state days_in_state event first_500 episode episode_entered_500 near_500 window_day "
            "window_left confirm_ma confirm_dir confirm_days next_threshold pos_kind pos_share "
            "pos_entry_date pos_entry_price pos_exit_ma pos_exit_days pos_exit_threshold exit_event "
            "exit_share"
        ).split()
    }
    trades: list[Trade] = []
    start = 499
    if n > start:
        zone = "ABOVE" if c[start] > ma[200][start] else "BELOW200"
        window_start: int | None = None  # day a confirmed MA200 break opened the window
        break500: int = start
        episode, entered_500, near_seen = 0, False, False
        reclaim_kind, reclaim_until = None, -1
        pos: Trade | None = None
        remaining: list[tuple[int, float]] = []
        prev_state, days_in_state = None, 0

        for i in range(start, n):
            event, first_500 = "", None
            if zone == "ABOVE":
                if dn[200][i] >= p.break_confirm:
                    zone, window_start, event = "BELOW200", i, "BREAK_200"
                    episode, entered_500, near_seen = episode + 1, False, False
            elif zone == "BELOW200":
                if up[200][i] >= p.reclaim_confirm:
                    zone, event, window_start = "ABOVE", "RECLAIM_200", None
                    reclaim_kind, reclaim_until = "200", i + p.hold_days - 1
                elif dn[500][i] >= p.break_confirm:
                    zone, break500, event, window_start = "BELOW500", i, "BREAK_500", None
            elif zone == "BELOW500":
                if up[500][i] >= p.reclaim_confirm:
                    zone, event = "BELOW200", "RECLAIM_500"
                    first_500 = not entered_500
                    entered_500 = True
                    reclaim_kind, reclaim_until = "500", i + p.hold_days - 1

            # Observation windows: day 1 is the confirming day, the window ends after day W.
            window_day = None
            if zone == "BELOW200" and window_start is not None:
                if i - window_start < p.window:
                    window_day = i - window_start + 1
                else:
                    window_start = None
                    if not event:
                        event = "BEAR_200"
            if zone == "BELOW500":
                if i - break500 < p.window:
                    window_day = i - break500 + 1
                elif i - break500 == p.window and not event:
                    event = "CRISIS"

            near = bool(c[i] <= ma[500][i] * (1 + p.touch_band_pct / 100))
            # First touch of the episode (a day that already has another event fires it tomorrow).
            if zone == "BELOW200" and near and not near_seen and not event:
                event, near_seen = "NEAR_500", True

            if zone == "ABOVE":
                state = "RECLAIM_200" if reclaim_kind == "200" and i <= reclaim_until else "BULL"
            elif zone == "BELOW200":
                if reclaim_kind == "500" and i <= reclaim_until:
                    state = "RECLAIM_500"
                elif window_day is not None:
                    state = "BREAK_200"
                elif near:
                    state = "NEAR_500"
                else:
                    state = "BEAR_200"
            else:
                state = "BREAK_500" if window_day is not None else "CRISIS"
            days_in_state = days_in_state + 1 if state == prev_state else 1
            prev_state = state

            # Pending confirmation of the zone's next move and the close that confirms it tomorrow.
            if zone == "ABOVE":
                cma, cdir, cdays = 200, "down", dn[200][i]
            elif zone == "BELOW200":
                cma, cdir, cdays = 200, "up", up[200][i]
                if cdays == 0 and dn[500][i] > 0:
                    cma, cdir, cdays = 500, "down", dn[500][i]
            else:
                cma, cdir, cdays = 500, "up", up[500][i]

            # Virtual swing sleeve: exits first (a leg sells after exit_confirm closes below its
            # MA, all counted after the entry day), then a new entry if the slot is free.
            exit_event, exit_share = "", 0.0
            if pos is not None:
                still = []
                for k, share in remaining:
                    if min(dn[k][i], i - pos.entry_i) >= p.exit_confirm:
                        pos.legs.append((i, share))
                        exit_event = f"{exit_event}+EXIT_{k}" if exit_event else f"EXIT_{k}"
                        exit_share += share
                    else:
                        still.append((k, share))
                remaining = still
                if not remaining:
                    pos = None
            if pos is None and (
                event == "RECLAIM_200" or (event == "RECLAIM_500" and (first_500 or not p.first_only))
            ):
                pos = Trade(event, i)
                trades.append(pos)
                remaining = list(p.exit_200 if event == "RECLAIM_200" else p.exit_500)

            row = {
                "zone": zone,
                "state": state,
                "days_in_state": days_in_state,
                "event": event,
                "first_500": first_500,
                "episode": episode,
                "episode_entered_500": entered_500,
                "near_500": near,
                "window_day": window_day,
                "window_left": None if window_day is None else p.window - window_day,
                "confirm_ma": cma,
                "confirm_dir": cdir,
                "confirm_days": int(cdays),
                "next_threshold": float(thr[cma][i]),
                "exit_event": exit_event,
                "exit_share": exit_share,
            }
            if pos is not None:
                k = remaining[0][0]
                row |= {
                    "pos_kind": pos.kind,
                    "pos_share": sum(s for _, s in remaining),
                    "pos_entry_date": close.index[pos.entry_i],
                    "pos_entry_price": float(c[pos.entry_i]),
                    "pos_exit_ma": k,
                    "pos_exit_days": int(min(dn[k][i], i - pos.entry_i)),
                    "pos_exit_threshold": float(thr[k][i]),
                }
            for key, v in row.items():
                cols[key][i] = v

    frame = pd.DataFrame({"close": c, **{f"ma{k}": ma[k] for k in MA_SET}}, index=close.index)
    for key, v in cols.items():
        frame[key] = v
    for k in (50, 200, 500):
        frame[f"dist_ma{k}"] = (frame["close"] / frame[f"ma{k}"] - 1) * 100
        frame[f"below_ma{k}"] = dn[k]  # closes in a row below MA(k)
        frame[f"thr_ma{k}"] = thr[k]  # tomorrow's close that sits exactly on MA(k)
    return Regime(frame, trades)


def ma_regime(close: pd.Series, params: Params | None = None) -> pd.DataFrame:
    return run_regime(close, params).frame


def regime_events(frame: pd.DataFrame) -> pd.DataFrame:
    """Backtest events (§4): one row per RECLAIM_200 / BEAR_200 / NEAR_500 / RECLAIM_500 / CRISIS.

    NEAR_500 is already the first touch of its episode. RECLAIM_500 keeps `first_500`.
    """
    ev = frame[frame["event"].isin(EVENT_KINDS)]
    return pd.DataFrame(
        {"kind": ev["event"], "close": ev["close"], "first_500": ev["first_500"], "episode": ev["episode"]},
        index=ev.index,
    )


def forward_returns(close: pd.Series, events: pd.DataFrame, horizons=HORIZONS_MONTHS) -> pd.DataFrame:
    """Return from each event's close to the first close ≥ N calendar months later (%), and the
    deepest close below the event price within that span (`dip_{N}m`, %). NaN when the horizon
    has not passed yet."""
    close = close.dropna().sort_index()
    idx, c = close.index, close.to_numpy()
    out = events.copy()
    pos = idx.get_indexer(events.index)
    for m in horizons:
        rets, dips = [], []
        for e, d in zip(pos, events.index):
            j = idx.searchsorted(d + pd.DateOffset(months=m))
            if j >= len(c):
                rets.append(np.nan)
                dips.append(np.nan)
                continue
            rets.append((c[j] / c[e] - 1) * 100)
            dips.append(min(0.0, (c[e : j + 1].min() / c[e] - 1) * 100))
        out[f"ret_{m}m"] = rets
        out[f"dip_{m}m"] = dips
    return out


# Yahoo has no real opens for ^GSPC before 1962 (open == close); opens further than this from the
# previous close are bad ticks. Such days fill at the signal day's close instead.
OPEN_VALID_FROM = {"SPX": "1962-01-02"}
MAX_OPEN_GAP = 0.10


def clean_opens(close: pd.Series, open_: pd.Series | None, target: str | None = None) -> pd.Series | None:
    if open_ is None or open_.empty:
        return None
    o = open_.reindex(close.index)
    bad = o.isna() | (o <= 0) | ((o / close.shift() - 1).abs() > MAX_OPEN_GAP)
    if target in OPEN_VALID_FROM:
        bad |= close.index < pd.Timestamp(OPEN_VALID_FROM[target])
    return o.where(~bad)


def event_trades(frame: pd.DataFrame, params: Params | None = None) -> list[Trade]:
    """Backtest trades (§4): every RECLAIM_200 and every first-of-episode RECLAIM_500 is its own
    trade, evaluated alone with the §2 exit rules (unlike the virtual sleeve, which holds one
    slot and skips entries while it is full)."""
    p = params or Params()
    c = frame["close"].to_numpy()
    with np.errstate(invalid="ignore"):
        dn = {k: _runs(c < frame[f"ma{k}"].to_numpy()) for k in (50, 200, 500)}
    out = []
    entries = frame["event"].eq("RECLAIM_200") | (
        frame["event"].eq("RECLAIM_500") & (frame["first_500"].eq(True) | (not p.first_only))
    )
    for e in np.flatnonzero(entries.to_numpy()):
        kind = frame["event"].iloc[e]
        t = Trade(kind, int(e))
        for k, share in p.exit_200 if kind == "RECLAIM_200" else p.exit_500:
            # The streak must lie after the entry day, so the first possible exit is e + confirm.
            hit = np.flatnonzero(dn[k][e + p.exit_confirm :] >= p.exit_confirm)
            if len(hit):
                t.legs.append((int(e + p.exit_confirm + hit[0]), share))
        t.legs.sort()
        out.append(t)
    return out


def swing_trades(
    frame: pd.DataFrame | Regime, trades: list[Trade] | None = None, open_: pd.Series | None = None
) -> pd.DataFrame:
    """Priced trades. Fills at the next session's open (SKILL.md §8.2), or at the signal day's
    close where that open is missing / invalid. Open trades are marked to market.
    Pass a Regime alone for its virtual sleeve."""
    if isinstance(frame, Regime):
        frame, trades = frame.frame, frame.trades if trades is None else trades
    f = frame
    c = f["close"].to_numpy()
    o = None if open_ is None else open_.reindex(f.index).to_numpy()
    last = len(c) - 1

    def fill(i: int) -> float:
        if o is not None and i < last and not np.isnan(o[i + 1]):
            return float(o[i + 1])
        return float(c[i])

    rows = []
    for t in trades:
        entry = fill(t.entry_i)
        sold = sum(s for _, s in t.legs)
        ret = sum(s * (fill(j) / entry - 1) for j, s in t.legs) + (1 - sold) * (c[last] / entry - 1)
        exit_i = max((j for j, _ in t.legs), default=last) if t.closed else last
        rows.append(
            {
                "kind": t.kind,
                "entry_date": f.index[t.entry_i],
                "entry_price": entry,
                "exit_date": f.index[exit_i] if t.closed else None,
                "ret": ret * 100,
                "days": exit_i - t.entry_i,
                "open": not t.closed,
            }
        )
    return pd.DataFrame(rows, columns=["kind", "entry_date", "entry_price", "exit_date", "ret", "days", "open"])


def rounded(x, nd=1):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), nd)


def event_stats(events: pd.DataFrame, horizons=HORIZONS_MONTHS) -> dict:
    """Per event kind: count and, per horizon, n / win rate / median / worst return / worst dip."""
    out = {}
    for kind in EVENT_KINDS:
        ev = events[events["kind"] == kind]
        if kind == "RECLAIM_500":
            ev = ev[ev["first_500"] == True]  # noqa: E712 — object column
        per = {}
        for m in horizons:
            r = ev[f"ret_{m}m"].dropna()
            d = ev[f"dip_{m}m"].dropna()
            per[f"{m}m"] = {
                "n": int(len(r)),
                "win_pct": rounded((r > 0).mean() * 100) if len(r) else None,
                "median": rounded(r.median()) if len(r) else None,
                "worst": rounded(r.min()) if len(r) else None,
                "worst_dip": rounded(d.min()) if len(d) else None,
            }
        out[kind] = {"count": int(len(ev)), "horizons": per}
    return out


def trade_stats(trades: pd.DataFrame) -> dict:
    """Per entry kind: n / win rate / mean / median / worst return and median holding days.
    Open trades are excluded from the numbers (reported as `open`)."""
    out = {}
    for kind in ENTRY_KINDS:
        t = trades[trades["kind"] == kind]
        done = t[~t["open"].astype(bool)]
        r = done["ret"]
        out[kind] = {
            "n": int(len(done)),
            "open": int(len(t) - len(done)),
            "win_pct": rounded((r > 0).mean() * 100) if len(r) else None,
            "mean": rounded(r.mean()) if len(r) else None,
            "median": rounded(r.median()) if len(r) else None,
            "worst": rounded(r.min()) if len(r) else None,
            "days_median": rounded(done["days"].median(), 0) if len(r) else None,
        }
    return out


def state_label(state: str | None, window_day: int | None = None, window: int | None = None) -> str | None:
    if state is None or pd.isna(state):
        return None
    label = STATES[state][0]
    if state in ("BREAK_200", "BREAK_500") and window_day is not None and window:
        label += f"・觀察期第 {window_day} / {window} 天"
    return label


def _num(v, nd=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return round(float(v), nd)


def latest_regime(frame: pd.DataFrame, params: Params) -> dict | None:
    """The `regime` block of /api/dashboard for the last row."""
    if frame.empty or pd.isna(frame["state"].iloc[-1]):
        return None
    r = frame.iloc[-1]
    state = r["state"]
    wd = None if pd.isna(r["window_day"]) else int(r["window_day"])
    position = None
    if pd.notna(r["pos_kind"]):
        position = {
            "kind": r["pos_kind"],
            "share": _num(r["pos_share"]),
            "entry_date": r["pos_entry_date"].date().isoformat(),
            "entry_price": _num(r["pos_entry_price"]),
            "return_pct": _num((r["close"] / r["pos_entry_price"] - 1) * 100),
            "exit_ma": int(r["pos_exit_ma"]),
            "exit_days": int(r["pos_exit_days"]),
            "exit_threshold": _num(r["pos_exit_threshold"]),
            "exit_line": _num(r[f"ma{int(r['pos_exit_ma'])}"]),
        }
    return {
        "date": frame.index[-1].date().isoformat(),
        "close": _num(r["close"], 4),
        "state": state,
        "label": state_label(state, wd, params.window),
        "color": STATES[state][1],
        "days_in_state": int(r["days_in_state"]),
        "window_day": wd,
        "window_left": None if wd is None else int(r["window_left"]),
        "window": params.window,
        "event": r["event"] or None,
        "suggested_position": {**SUGGESTED[state], "text": STATES[state][2]},
        "near_500": bool(r["near_500"]),
        "episode_entered_500": bool(r["episode_entered_500"]),
        "confirm": {
            "ma": int(r["confirm_ma"]),
            "dir": r["confirm_dir"],
            "days": int(r["confirm_days"]),
            "needed": params.reclaim_confirm if r["confirm_dir"] == "up" else params.break_confirm,
            "next_threshold": _num(r["next_threshold"]),
        },
        "dist": {f"ma{k}": _num(r[f"dist_ma{k}"]) for k in (50, 200, 500)},
        # For a position the strategy doesn't know about (倉位計算機): streaks and tomorrow's lines.
        "below_days": {f"ma{k}": int(r[f"below_ma{k}"]) for k in (50, 200, 500)},
        "thresholds": {f"ma{k}": _num(r[f"thr_ma{k}"]) for k in (50, 200, 500)},
        "exit_confirm": params.exit_confirm,
        "ma": {f"ma{k}": _num(r[f"ma{k}"]) for k in MA_SET},
        "position": position,
    }


def state_segments(frame: pd.DataFrame) -> list[list]:
    """[[start, end, state], ...] runs of the same state, for chart backgrounds."""
    f = frame[frame["state"].notna()]
    if f.empty:
        return []
    s = f["state"]
    breaks = s.ne(s.shift())
    starts = list(np.flatnonzero(breaks.to_numpy()))
    out = []
    for a, b in zip(starts, starts[1:] + [len(s)]):
        out.append([f.index[a].date().isoformat(), f.index[b - 1].date().isoformat(), s.iloc[a]])
    return out
