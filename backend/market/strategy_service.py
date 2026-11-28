"""策略一 backtest bundle and alerts, shared by the API and the daily job's notifier."""

import pandas as pd

from market.config import STRATEGY_1, STRATEGY_1_INDEX_GROUP, TARGETS
from market.metrics import strategy
from market.metrics.strategy_alerts import alerts as strategy_alerts
from market.store import DataStore

DISCLAIMER = "依歷史均線規則推算，不構成投資建議"


def group_of(tid: str) -> str:
    return "指數" if tid in STRATEGY_1_INDEX_GROUP else "其他"


def build_bundle(store: DataStore) -> dict:
    """Every target's regime, events (with forward returns) and per-event trades, plus the
    pooled stats of each group (指數 / 其他) used when a target has too few samples."""
    per: dict[str, dict] = {}
    for tid, t in TARGETS.items():
        close = store.close(t["index"]).dropna()
        params = strategy.Params.for_target(tid)
        rg = strategy.run_regime(close, params)
        events = strategy.forward_returns(close, strategy.regime_events(rg.frame))
        opens = strategy.clean_opens(rg.frame["close"], store.open(t["index"]), tid)
        trades = strategy.swing_trades(rg.frame, strategy.event_trades(rg.frame, params), opens)
        per[tid] = {"params": params, "regime": rg, "events": events, "trades": trades}

    groups: dict[str, dict] = {}
    for g in ("指數", "其他"):
        members = [tid for tid in per if group_of(tid) == g]
        ev = pd.concat([per[tid]["events"] for tid in members]) if members else pd.DataFrame()
        tr = pd.concat([per[tid]["trades"] for tid in members]) if members else pd.DataFrame()
        groups[g] = {
            "members": members,
            "events": strategy.event_stats(ev) if len(ev) else None,
            "trades": strategy.trade_stats(tr) if len(tr) else None,
        }
    return {"targets": per, "groups": groups}


def alert_stats(bundle: dict | None, tid: str) -> dict | None:
    if bundle is None or tid not in bundle["targets"]:
        return None
    group = group_of(tid)
    return {
        "target": strategy.event_stats(bundle["targets"][tid]["events"]),
        "group": bundle["groups"][group]["events"],
        "group_name": group,
    }


def target_alerts(frame: pd.DataFrame, params, bundle: dict | None, tid: str) -> list[dict]:
    return strategy_alerts(frame, params, alert_stats(bundle, tid), STRATEGY_1["MIN_SAMPLES"])


def regime_with_alerts(frame: pd.DataFrame, params, bundle: dict | None, tid: str) -> dict | None:
    regime = strategy.latest_regime(frame, params)
    if regime is not None:
        regime["alerts"] = target_alerts(frame, params, bundle, tid)
    return regime
