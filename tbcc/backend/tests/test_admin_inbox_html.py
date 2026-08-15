"""Admin inbox HTML formatting."""

from app.services.admin_inbox import _format_event_body_html


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
