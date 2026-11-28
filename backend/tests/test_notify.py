"""策略一 notifications: recording, day-over-day dedupe, Discord payloads (SKILL.md §9.5)."""

from datetime import datetime

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from market import notify, strategy_service
from market.db import init_db
from market.models import StrategySignal
from tests.test_strategy_1 import Prices


class FakeStore:
    def __init__(self, closes: dict[str, pd.Series]):
        self.closes = closes

    def close(self, symbol):
        return self.closes.get(symbol, pd.Series(dtype=float))

    def open(self, symbol):
        return pd.Series(dtype=float)


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setattr(strategy_service, "TARGETS", {"SPX": {"index": "^GSPC", "name": "S&P 500"}})
    # One shared connection: the API test client queries from another thread.
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    init_db(engine)
    with Session(engine) as s:
        yield s


def bundle(p: Prices) -> dict:
    return strategy_service.build_bundle(FakeStore({"^GSPC": p.series()}))


def run(session, p: Prices, webhook="https://discord.example/webhook", day=1):
    sent: list[dict] = []
    summary = notify.record_and_send(session, bundle(p), sent.append, webhook, datetime(2026, 1, day))
    session.commit()
    return summary, sent


def test_quiet_day_records_and_sends_nothing(session):
    summary, sent = run(session, Prices())
    assert sent == [] and summary == "0 alerts, nothing new"
    assert session.scalars(select(StrategySignal)).all() == []


def test_new_alert_is_sent_once_and_repeats_are_skipped(session):
    p = Prices().below(200, 3)  # BREAK_200 confirmed today
    summary, sent = run(session, p)
    assert len(sent) == 1 and summary.endswith("sent to Discord")
    emb = sent[0]["embeds"]
    assert any("S&P 500：跌破 200 日線" in e["title"] for e in emb)
    assert sent[0]["content"].startswith("策略一提示：")
    assert sent[0]["allowed_mentions"] == {"parse": []}

    # Same day again (job re-run): already sent, nothing goes out.
    _, sent = run(session, p)
    assert sent == []
    rows = session.scalars(select(StrategySignal)).all()
    assert rows and all(r.sent_at is not None for r in rows)


def test_alert_unchanged_from_previous_day_is_not_resent(session):
    p = Prices().below(200, 3 + 25)  # BEAR_200 for a while
    run(session, p)
    p.below(200)  # next day, still BEAR_200 with the same key
    _, sent = run(session, p, day=2)
    titles = [e["title"] for m in sent for e in m["embeds"]]
    assert not any("一個月沒站回 200" in t for t in titles)


def test_day_count_change_is_sent(session):
    p = Prices().below(200, 1)
    _, sent = run(session, p)
    assert "第 1 天" in sent[0]["embeds"][0]["title"]
    p.below(200)
    _, sent = run(session, p, day=2)
    assert "第 2 天" in sent[0]["embeds"][0]["title"]


def test_without_webhook_alerts_are_recorded_not_sent(session):
    summary, sent = run(session, Prices().below(200, 3), webhook="")
    assert sent == [] and "DISCORD_WEBHOOK_URL unset" in summary
    rows = session.scalars(select(StrategySignal)).all()
    assert rows and all(r.sent_at is None for r in rows)


def test_entry_alert_has_detail_lines_and_action_color(session):
    _, sent = run(session, Prices().below(200, 5).above(200, 3))
    e = sent[0]["embeds"][0]
    assert e["title"].startswith("🔴 S&P 500：波段倉進場")
    assert e["color"] == notify.LEVEL_COLOR["action"]
    assert "**出場規則**" in e["description"]


def test_messages_split_at_ten_embeds_action_first():
    items = [("SPX", {"level": "soon" if i else "action", "title": f"t{i}", "lines": [], "kind": str(i)}, "2026-01-01") for i in range(12)]
    out = notify.messages(items)
    assert [len(p["embeds"]) for p, _ in out] == [10, 2]
    assert out[0][0]["embeds"][0]["title"].startswith("🔴")
    assert "content" not in out[1][0]


def test_signal_log_endpoint(session, monkeypatch):
    from fastapi.testclient import TestClient

    from market.api import main

    p = Prices().below(200, 5).above(200, 3)
    run(session, p)
    p.add(200, 1.04, 300)  # a year and more passes

    store = FakeStore({"^GSPC": p.series()})
    store.session = session
    monkeypatch.setattr(main, "cached_strategy", lambda st: strategy_service.build_bundle(store))
    main.app.dependency_overrides[main.get_store] = lambda: store
    try:
        r = TestClient(main.app).get("/api/strategy/signals").json()
    finally:
        main.app.dependency_overrides.clear()
    sig = r["signals"][0]
    assert sig["kind"] == "ENTRY_200" and sig["level"] == "action" and sig["sent"]
    assert sig["returns"]["12m"] is not None and sig["returns"]["12m"] > 0
    assert sig["backtest"]["n"] >= 1
