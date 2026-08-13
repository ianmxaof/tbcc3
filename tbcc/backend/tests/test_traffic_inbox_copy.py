"""Traffic inbox human-readable copy."""

from __future__ import annotations

from app.services.admin_inbox import format_inbox_digest, push_admin_inbox_event
from app.services.traffic_inbox_copy import (
    format_traffic_compact_line,
    format_traffic_detail,
    format_traffic_rollup,
    format_traffic_title,
)


def test_post_ok_title_and_detail():
    meta = {
        "pulse_event_type": "post_ok",
        "channel_name": "AOF AI",
        "scheduled_post_name": "AOF CROSS-CHANNEL SCHEDULER",
        "scheduled_post_id": 21,
        "interval_minutes": 480,
        "outbound_event_type": "scheduled_post_sent",
    }
    assert "AOF AI" in format_traffic_title(meta)
    assert "AOF CROSS-CHANNEL" in format_traffic_title(meta)
    detail = format_traffic_detail(meta)
    assert "480" in detail
    assert "#21" in detail


def test_affiliate_served_detail():
    meta = {
        "pulse_event_type": "affiliate_served",
        "label": "Undress AI bot",
        "placement": "telegram_footer",
        "url": "https://api.powercore.app/r/aff-undress-ai-bot-telegram-f",
        "slug": "aff-undress-ai-bot-telegram-f",
    }
    title = format_traffic_title(meta)
    assert "Undress AI" in title
    assert "footer" in title.lower()
    detail = format_traffic_detail(meta)
    assert "aff-undress" in detail


def test_traffic_rollup_collapses_many():
    events = []
    for i in range(6):
        events.append(
            {
                "category": "traffic",
                "ts_unix": 1000 + i,
                "meta": {
                    "pulse_event_type": "post_ok",
                    "scheduled_post_name": f"JOB {i % 2}",
                    "channel_name": "AOF AI",
                },
            }
        )
    rollup = format_traffic_rollup(events, ago_fn=lambda _ts: "1h")
    assert rollup is not None
    assert "6" in rollup
    assert "Scheduler posts" in rollup


def test_inbox_digest_uses_rollup(monkeypatch):
    monkeypatch.setenv("TBCC_INBOX_ENABLED", "1")
    events = []
    for i in range(5):
        events.append(
            {
                "category": "traffic",
                "title": "old",
                "body": "",
                "ts_unix": 2000 + i,
                "meta": {"pulse_event_type": "post_ok", "scheduled_post_name": f"S{i}", "channel_name": "AOF AI"},
            }
        )
    text = format_inbox_digest(events, title="TBCC Inbox")
    assert "Traffic pulse" in text
    assert "Scheduler posts" in text
    assert text.count("📡") <= 2


def test_secretary_online_dedup(monkeypatch):
    monkeypatch.setenv("TBCC_INBOX_ENABLED", "1")
    store: dict[str, str] = {}

    class FakeRedis:
        def get(self, key):
            return store.get(key)

        def set(self, key, val):
            store[key] = val

        def lpush(self, *_a, **_k):
            pass

        def ltrim(self, *_a, **_k):
            pass

    monkeypatch.setattr("app.services.admin_inbox._redis_client", lambda: FakeRedis())
    monkeypatch.setattr("app.services.admin_inbox._telegram_send_html", lambda *_a, **_k: None)

    first = push_admin_inbox_event(
        category="system",
        severity="info",
        title="Secretary bot online",
        body="test",
        instant=False,
    )
    second = push_admin_inbox_event(
        category="system",
        severity="info",
        title="Secretary bot online",
        body="test",
        instant=False,
    )
    assert first is not None
    assert second is None


def test_compact_line_one_block():
    ev = {
        "category": "traffic",
        "title": "ignored",
        "body": "",
        "meta": {
            "pulse_event_type": "beacon",
            "link_label": "DrawAI · x_buffer",
            "slug": "aff-drawai-x-buffer",
            "hit_count": 3,
            "placement": "x_buffer",
        },
    }
    line = format_traffic_compact_line(ev, ago="49m")
    assert "Beacon click" in line
    assert "DrawAI" in line
    assert "49m" in line
