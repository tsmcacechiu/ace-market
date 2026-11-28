"""策略一 alerts → `strategy_signals` table and Discord (plan/strategy-1/SKILL.md §9.5–9.6).

Run by the daily job as its last step. Every 🔴 / 🟡 alert of the latest trading day is
recorded; one goes out to Discord only when it was not already there on the previous trading
day with the same key (the key changes with the level or the day count), and only once.

    uv run python -m market.notify --dry-run   # print today's alerts, send / record nothing
    uv run python -m market.notify --test      # send one test message to the webhook
"""

import argparse
import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from market import strategy_service
from market.config import DISCORD_WEBHOOK_URL, SITE_URL, TARGETS
from market.models import StrategySignal
from market.store import DataStore

log = logging.getLogger("market.notify")

URGENT = ("action", "soon")
LEVEL_ICON = {"action": "🔴", "soon": "🟡", "holding": "⚪"}
LEVEL_COLOR = {"action": 0xD03B3B, "soon": 0xE0B400}
MAX_EMBEDS = 10  # Discord limit per message

Sender = Callable[[dict], None]


def post_discord(payload: dict, url: str | None = None, attempts: int = 3) -> None:
    """POST one webhook message; waits and retries when Discord rate-limits (429)."""
    url = url or DISCORD_WEBHOOK_URL
    body = json.dumps(payload, ensure_ascii=False).encode()
    for attempt in range(attempts):
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "market-dashboard/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20):
                return
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < attempts - 1:
                retry = float(json.loads(e.read() or b"{}").get("retry_after", 1))
                time.sleep(min(retry, 30))
                continue
            # Never log the URL: it contains the webhook token.
            raise RuntimeError(f"Discord webhook HTTP {e.code}") from None


def embed(tid: str, a: dict, day: str) -> dict:
    name = TARGETS[tid]["name"]
    e = {
        "title": f"{LEVEL_ICON[a['level']]} {name}：{a['title']}"[:256],
        "color": LEVEL_COLOR.get(a["level"], 0x898781),
        "footer": {"text": f"{day} 收盤 · {strategy_service.DISCLAIMER}"},
    }
    if a["lines"]:
        e["description"] = "\n".join(f"**{label}**　{text}" for label, text in a["lines"])[:4000]
    if SITE_URL:
        e["url"] = f"{SITE_URL}/index/{tid}"
    return e


def messages(items: list[tuple[str, dict, str]]) -> list[tuple[dict, list[tuple[str, dict, str]]]]:
    """(webhook payload, the alerts in it): 🔴 first, at most MAX_EMBEDS alerts per message."""
    items = sorted(items, key=lambda x: (x[1]["level"] != "action", x[0]))
    actions = sum(a["level"] == "action" for _, a, _ in items)
    out = []
    for i in range(0, len(items), MAX_EMBEDS):
        chunk = items[i : i + MAX_EMBEDS]
        payload = {
            "username": "策略一",
            "embeds": [embed(tid, a, day) for tid, a, day in chunk],
            "allowed_mentions": {"parse": []},
        }
        if i == 0:
            payload["content"] = f"策略一提示：{actions} 個要動作、{len(items) - actions} 個快觸發"
        out.append((payload, chunk))
    return out


def today_alerts(bundle: dict) -> dict[str, dict]:
    """target -> {date, prev_date, close, alerts (🔴 / 🟡 only)} for the latest trading day."""
    out = {}
    for tid, d in bundle["targets"].items():
        frame = d["regime"].frame
        if len(frame) < 2 or pd.isna(frame["state"].iloc[-1]):
            continue
        alerts = strategy_service.target_alerts(frame, d["params"], bundle, tid)
        out[tid] = {
            "date": frame.index[-1].date(),
            "prev_date": frame.index[-2].date(),
            "close": float(frame["close"].iloc[-1]),
            "alerts": [a for a in alerts if a["level"] in URGENT],
        }
    return out


def record_and_send(
    session: Session,
    bundle: dict | None = None,
    send: Sender | None = None,
    webhook: str | None = None,
    now: datetime | None = None,
) -> str:
    """Store today's alerts and send the new ones. Returns a one-line summary for the job log."""
    bundle = bundle or strategy_service.build_bundle(DataStore(session))
    webhook = DISCORD_WEBHOOK_URL if webhook is None else webhook
    send = send or (lambda payload: post_discord(payload, webhook))
    now = now or datetime.now()

    pending: list[tuple[str, dict, str, StrategySignal]] = []
    total = 0
    for tid, t in today_alerts(bundle).items():
        kinds = {a["kind"] for a in t["alerts"]}
        # A re-run after a data correction: drop today's unsent alerts that no longer apply.
        session.execute(
            delete(StrategySignal).where(
                StrategySignal.target == tid,
                StrategySignal.date == t["date"],
                StrategySignal.sent_at.is_(None),
                StrategySignal.kind.not_in(kinds) if kinds else StrategySignal.kind.is_not(None),
            )
        )
        prev_keys = set(
            session.scalars(
                select(StrategySignal.key).where(StrategySignal.target == tid, StrategySignal.date == t["prev_date"])
            )
        )
        for a in t["alerts"]:
            total += 1
            row = session.get(StrategySignal, (tid, t["date"], a["kind"]))
            if row is None:
                row = StrategySignal(target=tid, date=t["date"], kind=a["kind"])
                session.add(row)
            row.level, row.key, row.price, row.title = a["level"], a["key"], t["close"], a["title"]
            row.lines = json.dumps(a["lines"], ensure_ascii=False) if a["lines"] else None
            if row.sent_at is None and a["key"] not in prev_keys:
                pending.append((tid, a, t["date"].isoformat(), row))
    session.flush()

    if not webhook:
        return f"{total} alerts, {len(pending)} new, not sent (DISCORD_WEBHOOK_URL unset)"
    if not pending:
        return f"{total} alerts, nothing new (Discord ready)"
    rows = {(tid, a["kind"]): row for tid, a, _, row in pending}
    sent = 0
    for payload, chunk in messages([(tid, a, day) for tid, a, day, _ in pending]):
        send(payload)
        for tid, a, _ in chunk:
            rows[(tid, a["kind"])].sent_at = now
        session.commit()  # keep what already went out marked, even if a later message fails
        sent += len(chunk)
    return f"{total} alerts, {sent} sent to Discord"


def main() -> None:
    from market.db import SessionLocal, init_db

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print today's alerts only")
    ap.add_argument("--test", action="store_true", help="send a test message to DISCORD_WEBHOOK_URL")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.test:
        if not DISCORD_WEBHOOK_URL:
            raise SystemExit("DISCORD_WEBHOOK_URL is not set (backend/.env)")
        post_discord({"username": "策略一", "content": "✅ 測試訊息：Discord 通知設定成功", "allowed_mentions": {"parse": []}})
        print("sent")
        return

    init_db()
    with SessionLocal() as session:
        bundle = strategy_service.build_bundle(DataStore(session))
        if args.dry_run:
            for tid, t in today_alerts(bundle).items():
                for a in t["alerts"]:
                    print(f"{t['date']} {LEVEL_ICON[a['level']]} {TARGETS[tid]['name']}：{a['title']}  [{a['key']}]")
            return
        print(record_and_send(session, bundle))
        session.commit()


if __name__ == "__main__":
    main()
