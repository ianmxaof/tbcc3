"""Archive of Filth library mirror — topic map + gatekeeper hook."""

from __future__ import annotations

from unittest.mock import MagicMock


def test_library_topic_map_includes_goon_and_packs():
    from app.data.aof_library_forum_topic_map import library_forum_topic_for_network_key

    goon = library_forum_topic_for_network_key("goon")
    packs = library_forum_topic_for_network_key("packs")
    assert goon is not None
    assert packs is not None
    assert goon.message_thread_id == 168
    assert packs.message_thread_id == 166


def test_library_thread_for_storage_goon_lane():
    from app.data.aof_storage_hub_map import storage_map_by_key
    from app.services.aof_library_forum_mirror import library_thread_for_storage_thread

    goon_storage = storage_map_by_key()["goon"]
    assert library_thread_for_storage_thread(goon_storage.message_thread_id) == 168


def test_mirror_hub_message_skips_when_disabled(monkeypatch):
    import asyncio

    from app.services import aof_library_forum_mirror as mod

    monkeypatch.setattr(mod, "library_forum_mirror_enabled", lambda: False)
    storage = MagicMock()

    async def run():
        return await mod.mirror_hub_message_to_library_topic(
            storage, source_message_id=1, lane_key="goon",
        )

    out = asyncio.run(run())
    assert out["skipped"] is True
    assert out["reason"] == "disabled"


def test_enqueue_library_mirror_for_media(monkeypatch):
    from app.services.aof_library_forum_mirror import enqueue_library_mirror_for_media

    task = MagicMock()
    monkeypatch.setattr(
        "app.workers.gatekeeper_review_worker.library_mirror_media_task",
        task,
    )
    out = enqueue_library_mirror_for_media(42)
    assert out["ok"] is True
    assert out["queued"] is True
    task.delay.assert_called_once_with(42)
