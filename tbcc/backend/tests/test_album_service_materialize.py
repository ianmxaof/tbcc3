"""Album sends materialize hub/Saved Messages refs before upload (noforwards guard)."""

import asyncio
import io
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.album_service import post_album


def test_post_album_materializes_before_send():
    async def _run():
        client = AsyncMock()
        client.send_file = AsyncMock(return_value=MagicMock(id=99))
        db_media = MagicMock(id=7, media_type="photo")
        raw = MagicMock(name="MessageMediaPhoto")

        with patch(
            "app.services.media_message_resolve.fetch_album_medias",
            new_callable=AsyncMock,
            return_value=[raw],
        ), patch(
            "app.services.scheduled_post_service._materialize_pool_media_for_send",
            new_callable=AsyncMock,
        ) as mat:
            buf = io.BytesIO(b"\xff\xd8\xff")
            buf.name = "image.jpg"
            mat.return_value = buf

            ids = await post_album(client, "channel", [db_media], caption="hi")

            mat.assert_awaited_once_with(client, raw, db_media)
            client.send_file.assert_awaited_once()
            sent = client.send_file.await_args.args[1]
            assert sent is buf
            assert ids == [99]

    asyncio.run(_run())
