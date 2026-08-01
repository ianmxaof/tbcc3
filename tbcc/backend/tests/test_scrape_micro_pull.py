"""Tests for SCRP micro-pull planning."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.data.aof_scrape_inbound_map import match_folder_title_to_pool_key
from app.services.scrape_micro_pull import (
    MICRO_PULL_DEFAULT_LIMIT,
    MICRO_PULL_PILOT_LANE,
    micro_pull_lanes,
    micro_pull_limit,
    pick_micro_pull_lane_for_tick,
    plan_lane_micro_pull,
)


def test_match_folder_title_scp_full_maps_full_length():
    assert match_folder_title_to_pool_key("SCRP FULL") == "full_length"
    assert match_folder_title_to_pool_key("Full Length SCRP") == "full_length"


def test_match_folder_title_scp_bulk_maps_inbox():
    assert match_folder_title_to_pool_key("SCRP BULK") == "inbox"
    assert match_folder_title_to_pool_key("scrp bulk") == "inbox"


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


def test_plan_inbox_micro_pull_has_topic_22569():
    from app.data.aof_storage_hub_map import storage_map_by_key

    row = storage_map_by_key().get("inbox")
    assert row is not None
    assert row.message_thread_id == 22569
    assert row.topic_title == "AOF INBOX"

    db = MagicMock()
    plan = plan_lane_micro_pull(
        db,
        "inbox",
        folder_index={
            "SCRP BULK": [{"chat_id": -1001111222333, "title": "Some Bulk Channel"}],
        },
    )
    assert plan["ok"] is True
    assert plan["lane_key"] == "inbox"
    assert plan["message_thread_id"] == 22569


def test_micro_pull_firehose_lanes_inbox_only(monkeypatch):
    monkeypatch.setenv("TBCC_SCRAPE_MICRO_PULL_MODE", "firehose")
    from importlib import reload

    import app.services.scrape_micro_pull as smp

    reload(smp)
    assert smp.micro_pull_lanes() == ["inbox"]


def test_pick_micro_pull_lane_rotates(monkeypatch):
    monkeypatch.setenv("TBCC_SCRAPE_MICRO_PULL_LANES", "bop,blowjob")
    lanes = sorted(["bop", "blowjob"])

    class FakeRedis:
        def __init__(self):
            self.n = 0

        def incr(self, key):
            self.n += 1
            return self.n

    fake = FakeRedis()
    monkeypatch.setattr("app.services.scrape_micro_pull._redis_client", lambda: fake)
    assert pick_micro_pull_lane_for_tick() == lanes[0]
    assert pick_micro_pull_lane_for_tick() == lanes[1]
    assert pick_micro_pull_lane_for_tick() == lanes[0]
