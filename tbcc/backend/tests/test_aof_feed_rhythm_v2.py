"""Tests for AOF Feed Rhythm v2 — VIP roll, tease schedulers, refill hooks."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from app.models.scheduled_text_post import ScheduledTextPost
from app.services.aof_feed_rhythm_v2 import (
    apply_main_group_tease_media,
    is_network_tease_scheduler,
    network_album_size,
    resolve_vip_album_size,
    roll_vip_album_size,
    vip_album_roll_max,
    vip_album_roll_min,
)


def test_network_album_size_default():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("TBCC_NETWORK_ALBUM_SIZE", None)
        assert network_album_size() == 1


def test_network_album_size_env():
    with patch.dict(os.environ, {"TBCC_NETWORK_ALBUM_SIZE": "5"}):
        assert network_album_size() == 5


def test_roll_vip_album_size_in_range():
    with patch.dict(
        os.environ,
        {
            "TBCC_AOF_VIP_ALBUM_ROLL_MIN": "3",
            "TBCC_AOF_VIP_ALBUM_ROLL_MAX": "10",
        },
    ):
        for seed in range(20):
            size = roll_vip_album_size(seed=seed)
            assert vip_album_roll_min() <= size <= vip_album_roll_max()


def test_roll_vip_biased_toward_small():
    with patch.dict(
        os.environ,
        {
            "TBCC_AOF_VIP_ALBUM_ROLL_MIN": "3",
            "TBCC_AOF_VIP_ALBUM_ROLL_MAX": "10",
        },
    ):
        sizes = [roll_vip_album_size(seed=i) for i in range(500)]
        small = sum(1 for s in sizes if s <= 5)
        large = sum(1 for s in sizes if s >= 8)
        assert small > large


def test_resolve_vip_album_size_fixed_when_roll_disabled():
    with patch.dict(
        os.environ,
        {
            "TBCC_AOF_VIP_ALBUM_ROLL": "0",
            "TBCC_AOF_VIP_ALBUM_SIZE": "4",
        },
    ):
        assert resolve_vip_album_size() == 4


def test_is_network_tease_scheduler():
    post = ScheduledTextPost(
        name="AOF — network liveness — heartbeat",
        channel_id=1,
        content="x",
    )
    assert is_network_tease_scheduler(post)
    assert not is_network_tease_scheduler(
        ScheduledTextPost(name="AOF MILF SCHEDULER", channel_id=1, content="x")
    )


def test_apply_main_group_tease_media():
    sched = ScheduledTextPost(name="AOF — network liveness — heartbeat", channel_id=1, content="x")
    with patch.dict(os.environ, {"TBCC_MAIN_GROUP_ALBUM_SIZE": "3"}):
        apply_main_group_tease_media(sched)
    assert sched.pool_collective_random is True
    assert sched.pool_id is None
    assert sched.album_size == 3
    assert sched.pool_randomize is True


def test_maybe_queue_post_refill_skips_on_probability(monkeypatch):
    from app.services import aof_feed_rhythm_v2 as mod

    monkeypatch.setattr(mod.random, "random", lambda: 0.99)
    db = MagicMock()
    out = mod.maybe_queue_post_refill(db, pool_id=1)
    assert out.get("skipped") is True
    assert out.get("reason") == "probability"


def test_vip_social_proof_line_fallback():
    from app.services.aof_feed_rhythm_v2 import vip_social_proof_line

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    line = vip_social_proof_line(db)
    assert "VIP" in line
    assert "3–10" in line or "3-10" in line.replace("–", "-")
