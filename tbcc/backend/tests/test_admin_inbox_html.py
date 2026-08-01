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
