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
    parse_panel_callback,
    review_panel_confirm_keyboard,
    review_panel_keyboard,
)


def test_parse_panel_callback_lane_open():
    assert parse_panel_callback("gk:p:open:ai") == ("open", "ai")
    assert parse_panel_callback("gk:p:open") == ("open", None)
    assert parse_panel_callback("gk:p:approve:yes:ai") == ("approve_yes", "ai")
    assert parse_panel_callback("gk:p:approve:ai") == ("approve", "ai")


def test_review_panel_keyboard_shows_approve_when_waiting():
    kb = review_panel_keyboard(waiting=12)
    rows = kb["inline_keyboard"]
    assert rows[0][0]["text"] == "✅ Approve all (12)"
    assert rows[0][0]["callback_data"] == CALLBACK_PANEL_APPROVE
    assert rows[-1][0]["callback_data"] == "gk:p:refresh"


def test_review_panel_keyboard_lane_scoped():
    kb = review_panel_keyboard(waiting=42, lane_key="ai")
    rows = kb["inline_keyboard"]
    assert rows[0][0]["text"] == "✅ Approve all AI (42)"
    assert rows[0][0]["callback_data"] == "gk:p:approve:ai"
    assert rows[-1][0]["callback_data"] == "gk:p:open"


def test_review_panel_keyboard_hides_approve_when_empty():
    kb = review_panel_keyboard(waiting=0)
    assert len(kb["inline_keyboard"]) == 1
    assert kb["inline_keyboard"][0][0]["callback_data"] == "gk:p:refresh"


def test_review_panel_confirm_keyboard():
    kb = review_panel_confirm_keyboard(waiting=7)
    assert kb["inline_keyboard"][0][0]["callback_data"] == CALLBACK_PANEL_APPROVE_CONFIRM
    assert "7" in kb["inline_keyboard"][0][0]["text"]

    kb_lane = review_panel_confirm_keyboard(waiting=7, lane_key="ai")
    assert kb_lane["inline_keyboard"][0][0]["callback_data"] == "gk:p:approve:yes:ai"


def test_format_review_panel_html_includes_waiting_count():
    db = MagicMock()
    with patch("app.services.gatekeeper_review.count_quarantine_waiting", return_value=42):
        with patch("app.services.gatekeeper_review.inbox_quarantine_buffer_count", return_value=0):
            with patch(
                "app.services.gatekeeper_review.format_lane_pool_depth_html",
                return_value="Pool approved (flywheel <code>auto</code>, 🟠 backlog): bop <b>612</b>🟠",
            ):
                html = format_review_panel_html(db)
    assert "42" in html
    assert "APPROVE / DENY" in html
    assert "bop <b>612</b>" in html


def test_format_lane_pool_depth_html_backlog_marker():
    db = MagicMock()
    with patch(
        "app.services.export_flywheel_service.pool_depth_by_lane",
        return_value=[
            {"network_key": "bop", "approved_depth": 612, "backlog_pressure": True},
            {"network_key": "ass", "approved_depth": 30, "backlog_pressure": True},
            {"network_key": "taboo", "approved_depth": 0, "backlog_pressure": False},
        ],
    ):
        with patch("app.services.export_flywheel_service.flywheel_mode", return_value="auto"):
            from app.services.gatekeeper_review import format_lane_pool_depth_html

            html = format_lane_pool_depth_html(db)
    assert "bop <b>612</b>🟠" in html
    assert "ass <b>30</b>🟠" in html
    assert "taboo" not in html
    assert "flywheel <code>auto</code>" in html


def test_format_review_panel_html_lane_scoped():
    db = MagicMock()
    with patch("app.services.gatekeeper_review.count_quarantine_waiting", return_value=15):
        with patch(
            "app.services.export_flywheel_service.pool_depth_by_lane",
            return_value=[{"network_key": "ai", "approved_depth": 257, "backlog_pressure": True}],
        ):
            with patch("app.services.export_flywheel_service.flywheel_mode", return_value="auto"):
                with patch(
                    "app.services.quarantine_batch_review.lane_quarantine_buffer_count",
                    return_value=0,
                ):
                    html = format_review_panel_html(db, lane_key="ai")
    assert "ai" in html
    assert "15" in html
    assert "257" in html


def test_operator_approve_all_waiting_lane_scoped():
    db = MagicMock()
    with patch(
        "app.services.gatekeeper_review.list_quarantine_waiting_ids",
        return_value=[99],
    ) as list_ids:
        with patch(
            "app.services.gatekeeper_review.operator_approve_media",
            return_value={"ok": True, "media_id": 99},
        ) as approve:
            out = operator_approve_all_waiting(db, operator_id=1, lane_key="ai")
    list_ids.assert_called_once_with(db, limit=None, lane_key="ai")
    approve.assert_called_once_with(db, 99, operator_id=1, lane_keys=["ai"])
    assert out["lane_key"] == "ai"


def test_count_quarantine_waiting_uses_pending_filter():
    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.count.return_value = 5
    assert count_quarantine_waiting(db) == 5
