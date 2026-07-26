"""Tests for SCRP micro-pull planning."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.scrape_micro_pull import (
    MICRO_PULL_DEFAULT_LIMIT,
    MICRO_PULL_PILOT_LANE,
    micro_pull_limit,
    plan_lane_micro_pull,
)


def test_plan_ass_micro_pull_has_topic():
    db = MagicMock()
    plan = plan_lane_micro_pull(
        db,
        MICRO_PULL_PILOT_LANE,
        folder_index={
            "ASS SCRP": [
                {"chat_id": -1003271959583, "title": "Hagarth's Big ass"},
            ],
        },
    )
    assert plan["ok"] is True
    assert plan["lane_key"] == "ass"
    assert plan["message_thread_id"] == 3779
    assert plan["topic_title"] == "AOF ASS STORAGE"
    assert plan["source_count"] >= 1
    assert plan["picked_source"]["chat_id"] == -1003271959583


def test_micro_pull_limit_default():
    assert micro_pull_limit() == MICRO_PULL_DEFAULT_LIMIT
