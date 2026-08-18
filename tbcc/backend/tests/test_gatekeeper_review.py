"""Tests for gatekeeper quarantine review actions."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.services.gatekeeper_review import (
    format_quarantine_review_html,
    operator_approve_media,
    operator_reject_media,
    parse_review_callback,
    resolve_media_lane_key,
    resolve_preview_copy_target,
    review_preview_copy_enabled,
)


def test_parse_review_callback():
    assert parse_review_callback("gk:a:42") == ("approve", 42)
    assert parse_review_callback("gk:r:99") == ("reject", 99)
    assert parse_review_callback("ac:preview") is None


def test_format_quarantine_includes_quality_score_hint():
    media = MagicMock()
    media.id = 7234
    media.pool_id = None
    media.media_type = "video"
    media.source_channel = "telegram:-1003812457581#topic:9501"
    media.classification_json = json.dumps(
        {"gatekeeper": {"quality_score": 55, "warnings": ["review"], "globs": {"lane_fit": {"expected": "voyeur"}}}}
    )
    db = MagicMock()
    html = format_quarantine_review_html(db, media)
    assert "quality <b>55</b>/100" in html
    assert "not ML confidence" in html
    assert "VOYEUR" in html
    assert "#tbcc:quarantine" in html
    assert "#tbcc:voyeur" in html


def test_format_quarantine_shows_proposed_lanes_when_present():
    media = MagicMock()
    media.id = 7235
    media.pool_id = None
    media.media_type = "photo"
    media.source_channel = "telegram:-1003874330989"
    media.classification_json = json.dumps(
        {
            "gatekeeper": {
                "quality_score": 60,
                "warnings": ["lane_fit:mismatch"],
                "globs": {"lane_fit": {"expected": "inbox", "proposed_lanes": ["ass", "big_tits"]}},
            }
        }
    )
    db = MagicMock()
    html = format_quarantine_review_html(db, media)
    assert "Proposed:" in html
    assert "ass" in html
    assert "big_tits" in html


def test_format_quarantine_omits_proposed_line_when_empty():
    media = MagicMock()
    media.id = 7236
    media.pool_id = None
    media.media_type = "photo"
    media.source_channel = "telegram:-1003812457581#topic:9501"
    media.classification_json = json.dumps(
        {"gatekeeper": {"quality_score": 55, "warnings": [], "globs": {"lane_fit": {"expected": "voyeur"}}}}
    )
    db = MagicMock()
    html = format_quarantine_review_html(db, media)
    assert "Proposed:" not in html


def test_resolve_preview_copy_target_topic_source():
    media = MagicMock()
    media.telegram_message_id = 8812
    media.source_channel = "telegram:-1003812457581#topic:9501"
    out = resolve_preview_copy_target(media)
    assert out == {
        "from_chat_id": "-1003812457581",
        "message_id": 8812,
        "source_message_thread_id": 9501,
    }


def test_resolve_preview_copy_target_missing_message_id():
    media = MagicMock()
    media.telegram_message_id = 0
    media.source_channel = "telegram:-1003812457581#topic:9501"
    assert resolve_preview_copy_target(media) is None


def test_review_preview_copy_enabled_default_on():
    with patch.dict("os.environ", {}, clear=True):
        assert review_preview_copy_enabled() is True


def test_resolve_media_lane_key_from_topic_source():
    media = MagicMock()
    media.source_channel = "telegram:-1003812457581#topic:9501"
    media.pool_id = None
    media.classification_json = None
    db = MagicMock()
    assert resolve_media_lane_key(db, media) == "bop"


def test_operator_approve_enqueues_micro_pull(monkeypatch):
    media = MagicMock()
    media.id = 10
    media.status = "pending"
    media.source_channel = "telegram:-1003812457581#topic:9501"
    media.pool_id = 23
    media.classification_json = json.dumps({"gatekeeper": {"verdict": "quarantine", "quality_score": 55}})

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = media

    queued: list[str] = []
    monkeypatch.setattr(
        "app.services.gatekeeper_review.enqueue_micro_pull_for_lane",
        lambda lane: queued.append(lane),
    )

    out = operator_approve_media(db, 10, operator_id=7787282561)
    assert out["ok"] is True
    assert out["micro_pull_lane"] == "bop"
    assert queued == ["bop"]


def test_operator_approve_sets_status():
    media = MagicMock()
    media.id = 10
    media.status = "pending"
    media.source_channel = "-1003271959583"
    media.pool_id = 8
    media.classification_json = json.dumps({"gatekeeper": {"verdict": "quarantine", "quality_score": 55}})

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = media

    with patch("app.services.gatekeeper_review.enqueue_micro_pull_for_lane"):
        out = operator_approve_media(db, 10, operator_id=7787282561)
    assert out["ok"] is True
    assert media.status == "approved"
    data = json.loads(media.classification_json)
    assert data["gatekeeper"]["operator_action"] == "approve"
    db.commit.assert_called()


def test_operator_reject_sets_status_and_demote_meta():
    media = MagicMock()
    media.id = 11
    media.status = "pending"
    media.source_channel = "-1008880001"
    media.pool_id = 8
    media.classification_json = json.dumps({"gatekeeper": {"verdict": "quarantine"}})

    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [media]
    db.query.return_value.filter.return_value.all.return_value = []

    out = operator_reject_media(db, 11, operator_id=7787282561)
    assert out["ok"] is True
    assert media.status == "rejected"
    data = json.loads(media.classification_json)
    assert data["gatekeeper"]["operator_action"] == "reject"
    assert "operator_extra" in data["gatekeeper"]
