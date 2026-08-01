"""Tests for gatekeeper review bulk-approve panel."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.services.gatekeeper_review import (
    CALLBACK_PANEL_APPROVE,
    CALLBACK_PANEL_APPROVE_CONFIRM,
    count_quarantine_waiting,
    format_review_panel_html,
    operator_approve_all_waiting,
    review_panel_confirm_keyboard,
    review_panel_keyboard,
)


def test_review_panel_keyboard_shows_approve_when_waiting():
    kb = review_panel_keyboard(waiting=12)
    rows = kb["inline_keyboard"]
    assert rows[0][0]["text"] == "✅ Approve all (12)"
    assert rows[0][0]["callback_data"] == CALLBACK_PANEL_APPROVE
    assert rows[-1][0]["callback_data"] == "gk:p:refresh"


def test_review_panel_keyboard_hides_approve_when_empty():
    kb = review_panel_keyboard(waiting=0)
    assert len(kb["inline_keyboard"]) == 1
    assert kb["inline_keyboard"][0][0]["callback_data"] == "gk:p:refresh"


def test_review_panel_confirm_keyboard():
    kb = review_panel_confirm_keyboard(waiting=7)
    assert kb["inline_keyboard"][0][0]["callback_data"] == CALLBACK_PANEL_APPROVE_CONFIRM
    assert "7" in kb["inline_keyboard"][0][0]["text"]


def test_format_review_panel_html_includes_waiting_count():
    db = MagicMock()
    with patch("app.services.gatekeeper_review.count_quarantine_waiting", return_value=42):
        with patch("app.services.gatekeeper_review.inbox_quarantine_buffer_count", return_value=0):
            html = format_review_panel_html(db)
    assert "42" in html
    assert "APPROVE / DENY" in html


def test_operator_approve_all_waiting():
    media = MagicMock()
    media.id = 99
    media.status = "pending"
    media.classification_json = json.dumps({"gatekeeper": {"verdict": "quarantine"}})

    db = MagicMock()
    with patch("app.services.gatekeeper_review.list_quarantine_waiting_ids", return_value=[99]):
        with patch(
            "app.services.gatekeeper_review.operator_approve_media",
            return_value={"ok": True, "media_id": 99},
        ) as approve:
            out = operator_approve_all_waiting(db, operator_id=1)
    assert out["approved"] == 1
    assert out["total"] == 1
    approve.assert_called_once_with(db, 99, operator_id=1)


def test_count_quarantine_waiting_uses_pending_filter():
    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.count.return_value = 5
    assert count_quarantine_waiting(db) == 5
