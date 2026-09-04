"""Gatekeeper lane routing re-uploads instead of forwarding.

The Storage Hub is content-protected (noforwards), so ForwardMessages is refused even
hub->hub. These tests pin the re-upload path and guard against a regression back to a
forward-shaped send.
"""

import asyncio
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.gatekeeper_lane_route import route_media_to_lane_topics


def _storage(send_file=None):
    storage = MagicMock()
    storage.client = AsyncMock()
    storage.client.get_messages = AsyncMock(
        return_value=SimpleNamespace(id=555, media=MagicMock(), message="orig caption")
    )
    storage.client.download_media = AsyncMock(return_value=b"\xff\xd8\xffbytes")
    storage.client.send_file = send_file or AsyncMock(return_value=MagicMock(id=900))

    def _prepare(data, kind, *, skip_watermark=False, source_message=None):
        buf = io.BytesIO(data)
        buf.name = "media.jpg"
        return buf, {"force_document": False}, "photo"

    storage._prepare_file_for_send = MagicMock(side_effect=_prepare)
    return storage


def _lane_rows(*keys):
    return {k: SimpleNamespace(message_thread_id=1000 + i, topic_title=k.title()) for i, k in enumerate(keys)}


def test_route_downloads_once_and_uploads_per_lane():
    async def _run():
        storage = _storage()
        media = SimpleNamespace(id=7, telegram_message_id=555)

        with patch(
            "app.services.gatekeeper_lane_route.storage_map_by_key",
            return_value=_lane_rows("voyeur", "bop"),
        ), patch(
            "app.utils.telegram_peer.resolve_telethon_entity",
            new_callable=AsyncMock,
            return_value="HUB",
        ), patch(
            "app.services.aof_library_forum_mirror.mirror_hub_message_to_library_topic",
            new_callable=AsyncMock,
            return_value={"ok": True, "skipped": True},
        ):
            out = await route_media_to_lane_topics(storage, media, ["voyeur", "bop"])

        assert out["ok"] is True
        assert [r["lane"] for r in out["routed"]] == ["bop", "voyeur"]
        assert out["errors"] == []
        # One download shared by both lanes, one upload each.
        storage.client.download_media.assert_awaited_once()
        assert storage.client.send_file.await_count == 2

    asyncio.run(_run())


def test_route_never_calls_forward():
    """Regression guard: any ForwardMessages on hub media fails on a protected chat."""

    async def _run():
        storage = _storage()
        storage.client.forward_messages = AsyncMock(
            side_effect=AssertionError("must not forward from a protected chat")
        )
        media = SimpleNamespace(id=7, telegram_message_id=555)

        with patch(
            "app.services.gatekeeper_lane_route.storage_map_by_key",
            return_value=_lane_rows("voyeur"),
        ), patch(
            "app.utils.telegram_peer.resolve_telethon_entity",
            new_callable=AsyncMock,
            return_value="HUB",
        ), patch(
            "app.services.aof_library_forum_mirror.mirror_hub_message_to_library_topic",
            new_callable=AsyncMock,
            return_value={"ok": True, "skipped": True},
        ):
            out = await route_media_to_lane_topics(storage, media, ["voyeur"])

        assert out["ok"] is True
        storage.client.forward_messages.assert_not_awaited()
        # The old code did not use client.forward_messages — it built a
        # ForwardMessagesRequest and awaited the client directly. Pin that shape too,
        # otherwise this guard would miss the exact regression it exists to catch.
        assert storage.client.await_args_list == [], (
            "no raw request should be sent through the client; "
            f"got {storage.client.await_args_list}"
        )

    asyncio.run(_run())


def test_route_sends_into_lane_thread_with_stamped_caption():
    async def _run():
        storage = _storage()
        media = SimpleNamespace(id=7, telegram_message_id=555)

        with patch(
            "app.services.gatekeeper_lane_route.storage_map_by_key",
            return_value=_lane_rows("voyeur"),
        ), patch(
            "app.utils.telegram_peer.resolve_telethon_entity",
            new_callable=AsyncMock,
            return_value="HUB",
        ), patch(
            "app.services.aof_library_forum_mirror.mirror_hub_message_to_library_topic",
            new_callable=AsyncMock,
            return_value={"ok": True, "skipped": True},
        ), patch(
            "app.services.tbcc_caption_stamp.hub_intake_caption",
            return_value="orig caption #tbcc_voyeur",
        ):
            await route_media_to_lane_topics(storage, media, ["voyeur"])

        kwargs = storage.client.send_file.await_args.kwargs
        assert kwargs["reply_to"] == 1000
        assert kwargs["caption"] == "orig caption #tbcc_voyeur"
        # Hub media is already stamped at intake — a hub->hub copy must not re-watermark.
        assert storage._prepare_file_for_send.call_args.kwargs["skip_watermark"] is True

    asyncio.run(_run())


def test_route_reports_no_media_without_downloading():
    async def _run():
        storage = _storage()
        storage.client.get_messages = AsyncMock(return_value=SimpleNamespace(id=555, media=None))
        media = SimpleNamespace(id=7, telegram_message_id=555)

        with patch(
            "app.utils.telegram_peer.resolve_telethon_entity",
            new_callable=AsyncMock,
            return_value="HUB",
        ):
            out = await route_media_to_lane_topics(storage, media, ["voyeur"])

        assert out["ok"] is False
        assert out["reason"] == "no_media"
        storage.client.download_media.assert_not_awaited()

    asyncio.run(_run())


def test_route_one_bad_lane_does_not_sink_the_others():
    async def _run():
        calls = {"n": 0}

        async def _send(*_a, **_k):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("topic closed")
            return MagicMock(id=901)

        storage = _storage(send_file=AsyncMock(side_effect=_send))
        media = SimpleNamespace(id=7, telegram_message_id=555)

        with patch(
            "app.services.gatekeeper_lane_route.storage_map_by_key",
            return_value=_lane_rows("bop", "voyeur"),
        ), patch(
            "app.utils.telegram_peer.resolve_telethon_entity",
            new_callable=AsyncMock,
            return_value="HUB",
        ), patch(
            "app.services.aof_library_forum_mirror.mirror_hub_message_to_library_topic",
            new_callable=AsyncMock,
            return_value={"ok": True, "skipped": True},
        ):
            out = await route_media_to_lane_topics(storage, media, ["bop", "voyeur"])

        assert out["ok"] is True
        assert len(out["routed"]) == 1
        assert len(out["errors"]) == 1
        assert "topic closed" in out["errors"][0]["error"]

    asyncio.run(_run())
