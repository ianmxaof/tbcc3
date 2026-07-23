"""Tests for gatekeeper quarantine review actions."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from app.services.gatekeeper_review import (
    operator_approve_media,
    operator_reject_media,
    parse_review_callback,
)


def test_parse_review_callback():
    assert parse_review_callback("gk:a:42") == ("approve", 42)
    assert parse_review_callback("gk:r:99") == ("reject", 99)
    assert parse_review_callback("ac:preview") is None


def test_operator_approve_sets_status():
    media = MagicMock()
    media.id = 10
    media.status = "pending"
    media.source_channel = "-1003271959583"
    media.pool_id = 8
    media.classification_json = json.dumps({"gatekeeper": {"verdict": "quarantine", "quality_score": 55}})

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = media

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
