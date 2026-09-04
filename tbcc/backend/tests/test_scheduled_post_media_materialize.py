"""Scheduled pool media materialization — protected-chat forward guard."""

import asyncio
import io
from unittest.mock import AsyncMock, MagicMock

from app.services.scheduled_post_service import (
    _is_forward_restricted_send_error,
    _materialize_pool_media_for_send,
)


def test_forward_restricted_error_detection():
    assert _is_forward_restricted_send_error(
        Exception("You can't forward messages from a protected chat (caused by SendMediaRequest)")
    )
    assert not _is_forward_restricted_send_error(Exception("database is locked"))


def test_materialize_downloads_tl_media_to_bytesio():
    async def _run():
        client = AsyncMock()
        client.download_media = AsyncMock(return_value=b"\xff\xd8\xfffakejpeg")
        raw = MagicMock(name="MessageMediaDocument")
        db_media = MagicMock(id=42, media_type="photo")

        out = await _materialize_pool_media_for_send(client, raw, db_media)

        assert isinstance(out, io.BytesIO)
        assert out.name == "image.jpg"
        client.download_media.assert_awaited_once_with(raw, bytes)

    asyncio.run(_run())


def test_materialize_passes_through_bytesio():
    async def _run():
        client = AsyncMock()
        buf = io.BytesIO(b"already-local")
        buf.name = "local.jpg"
        db_media = MagicMock(id=1, media_type="photo")

        out = await _materialize_pool_media_for_send(client, buf, db_media)

        assert out is buf
        client.download_media.assert_not_called()

    asyncio.run(_run())
