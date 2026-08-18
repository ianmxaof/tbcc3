"""Admin inbox HTML formatting."""

from app.services.admin_inbox import (
    _format_event_body_html,
    clip_telegram_html,
    format_inbox_digest,
)


def test_revenue_brief_body_not_double_escaped():
    event = {
        "category": "system",
        "body": "<b>Daily revenue brief</b>\n1. <b>[now]</b> Ship loot CTAs",
        "meta": {"code": "revenue_brief"},
    }
    html = _format_event_body_html(event)
    assert "<b>Daily revenue brief</b>" in html
    assert "&lt;b&gt;" not in html


def test_format_instant_uses_styled_card():
    from app.services.admin_inbox import _format_instant

    event = {
        "category": "system",
        "severity": "important",
        "title": "Daily revenue brief",
        "body": "💰 <b>Daily revenue brief</b> · <u>operator read</u>",
        "meta": {"code": "revenue_brief"},
    }
    text = _format_instant(event)
    assert text.startswith("💰")
    assert "&lt;b&gt;" not in text
    # Don't stack the generic ⚙️ title above a card that already has a header.
    assert not text.startswith("⚙️")


def test_clip_telegram_html_closes_tags():
    blob = "<b>head</b>\n" + ("<i>lock storm</i>\n" * 400)
    out = clip_telegram_html(blob, 200)
    assert len(out) <= 200
    assert out.count("<i>") == out.count("</i>")


def test_critical_digest_collapses_lock_storms(monkeypatch):
    monkeypatch.setattr("app.services.admin_inbox.get_last_read_ts", lambda: 0)
    body = (
        "Many session-lock errors in a short window. "
        "Scheduled posts, imports, and Telegram sends are likely stalling.\n\n"
        "What to do:\nRun «Telegram relief focus» or «Trim duplicate workers» from the health banner."
    )
    events = [
        {
            "category": "ops",
            "severity": "critical",
            "title": "Telegram session lock storm",
            "body": body,
            "ts_unix": 1_000_000 - i * 3600,
            "meta": {"code": "session_lock_storm"},
        }
        for i in range(25)
    ]
    text = format_inbox_digest(events, title="Critical & important")
    assert len(text) <= 4096
    assert "Critical &amp; important" in text or "Critical" in text
    assert "×25" in text
    assert text.count("Telegram session lock storm") == 1
    assert not text.endswith("<i>")
    assert not text.endswith("<b>")
