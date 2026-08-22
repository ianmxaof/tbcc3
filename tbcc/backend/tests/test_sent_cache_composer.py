"""Tests for SENT CACHE album composer helpers."""

from unittest.mock import patch

from app.services.cache_album_caption import _snippet_lane_keys
from app.services.sent_cache_composer import _chunk_media_rows, cache_album_size, notify_composer_bot


class _FakeMedia:
    def __init__(self, mid: int, media_type: str = "video", tid: int = 0, fu: str = ""):
        self.id = mid
        self.media_type = media_type
        self.telegram_message_id = tid or mid
        self.file_unique_id = fu or f"fu-{mid}"


def test_cache_album_size_default():
    assert cache_album_size() >= 2


def test_chunk_media_rows_full_albums_only():
    rows = [_FakeMedia(i) for i in range(12)]
    albums = _chunk_media_rows(rows, 5)
    assert len(albums) == 2
    assert len(albums[0]) == 5
    assert len(albums[1]) == 5


def test_chunk_media_rows_dedupes_same_message_id():
    rows = [_FakeMedia(i) for i in range(1, 11)]
    for i, r in enumerate(rows):
        # Five rows share one Telegram message id (legacy sent-cache corruption pattern).
        r.telegram_message_id = 100 if i < 5 else 200 + i
        r.file_unique_id = f"fu-{r.telegram_message_id}-{i}"
    albums = _chunk_media_rows(rows, 5)
    assert len(albums) == 1
    assert len(albums[0]) == 5
    assert len({m.telegram_message_id for m in albums[0]}) == 5


def test_snippet_lane_keys_includes_network():
    keys = _snippet_lane_keys("big_tits")
    assert "big_tits" in keys
    assert "main_group_pulse" in keys


def _real_worker_loop_bridge(coro):
    """Actually run the coroutine — mirrors what _run_on_worker_loop does for
    the caller, so a regression that drops the await/bridge produces the real
    'coroutine' object has no attribute 'get' failure, not a mock false pass."""
    import asyncio

    return asyncio.run(coro)


def test_notify_composer_bot_awaits_panel_refresh_and_returns_panel_refreshed():
    """Regression: refresh_storage_deposit_panel_http is async; notify_composer_bot
    is sync. Calling it without a sync-to-async bridge crashed with
    AttributeError('coroutine' object has no attribute 'get') in production
    (2026-08-22, worker_telegram logs)."""

    async def fake_refresh(**kwargs):
        return {"ok": True, "action": "refreshed"}

    with patch("app.services.lane_composer_status.record_lane_composer_status"), \
         patch("app.data.aof_storage_hub_map.storage_map_by_key", return_value={}), \
         patch("app.services.storage_topic_deposit.storage_hub_chat_id_int", return_value=123), \
         patch("app.services.storage_deposit_panel_pins.refresh_storage_deposit_panel_http", side_effect=fake_refresh), \
         patch("app.services.import_job_runner._run_on_worker_loop", side_effect=_real_worker_loop_bridge):
        out = notify_composer_bot(storage_thread_id=1, network_key="voyeur", report={})

    assert out == {"ok": True, "action": "panel_refreshed", "panel": {"ok": True, "action": "refreshed"}}


def test_notify_composer_bot_falls_back_when_panel_refresh_not_ok(monkeypatch):
    monkeypatch.delenv("TBCC_SENT_CACHE_COMPOSER_LANE_NOTIFY", raising=False)

    async def fake_refresh(**kwargs):
        return {"ok": False, "error": "no panel pin"}

    with patch("app.services.lane_composer_status.record_lane_composer_status"), \
         patch("app.data.aof_storage_hub_map.storage_map_by_key", return_value={}), \
         patch("app.services.storage_topic_deposit.storage_hub_chat_id_int", return_value=123), \
         patch("app.services.storage_deposit_panel_pins.refresh_storage_deposit_panel_http", side_effect=fake_refresh), \
         patch("app.services.import_job_runner._run_on_worker_loop", side_effect=_real_worker_loop_bridge):
        out = notify_composer_bot(storage_thread_id=1, network_key="voyeur", report={})

    assert out["ok"] is True
    assert out["action"] == "status_recorded"
