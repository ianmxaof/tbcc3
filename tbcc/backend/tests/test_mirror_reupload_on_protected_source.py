"""Hub -> main/library mirroring re-uploads when the source refuses forwards.

The Storage Hub is content-protected. Before this was fixed, a ChatForwardsRestricted
error hit a `continue` that skipped past the download+re-upload fallback sitting right
below it, so every message was silently dropped and the caller still saw a success dict.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from telethon.tl.types import MessageMediaPhoto

from app.services.telegram_storage import TelegramStorage


class _Restricted(Exception):
    """Stands in for telethon ChatForwardsRestrictedError."""

    def __init__(self):
        super().__init__("You can't forward messages from a protected chat")


def _photo_message(msg_id: int):
    return SimpleNamespace(id=msg_id, media=MessageMediaPhoto(photo=SimpleNamespace()), message="")


def _storage(messages):
    client = AsyncMock()

    async def _iter(*_a, **_k):
        for m in messages:
            yield m

    client.iter_messages = _iter
    client.forward_messages = AsyncMock(side_effect=_Restricted())
    client.send_file = AsyncMock(return_value=MagicMock(id=1))
    client.download_media = AsyncMock(return_value=b"\xff\xd8\xffbytes")
    return TelegramStorage(client=client)  # type: ignore[arg-type]


def _run_mirror(storage, **kw):
    async def _go():
        with patch(
            "app.utils.telegram_peer.resolve_telethon_entity",
            new_callable=AsyncMock,
            return_value="PEER",
        ), patch("asyncio.sleep", new_callable=AsyncMock):
            return await storage.forward_storage_topic_to_main_topic(
                "hub", 111, "main", 222, limit=kw.pop("limit", 3), **kw
            )

    return asyncio.run(_go())


def test_protected_source_reuploads_instead_of_skipping():
    msgs = [_photo_message(1), _photo_message(2)]
    storage = _storage(msgs)

    stats = _run_mirror(storage)

    # The whole point: media is delivered, not silently dropped.
    assert stats["uploaded"] == 2
    assert stats["forwarded"] == 0
    assert stats["skipped_forward_restricted"] == 0
    assert stats["forward_restricted"] == 2
    assert storage.client.send_file.await_count == 2


def test_protected_source_marks_each_message_mirrored():
    """A dropped message used to stay unmarked, so the next run retried it forever."""
    msgs = [_photo_message(7), _photo_message(8)]
    storage = _storage(msgs)
    seen = []

    _run_mirror(storage, on_mirrored=lambda thread, mid: seen.append(mid))

    assert sorted(seen) == [7, 8]


def test_forward_attempts_stop_after_the_source_proves_protected():
    """One refusal is enough — later messages go straight to re-upload.

    On a single solo worker every wasted forward round trip is queue time other
    tasks do not get.
    """
    msgs = [_photo_message(i) for i in range(1, 5)]
    storage = _storage(msgs)

    _run_mirror(storage, limit=4)

    # One batch attempt + one per-message attempt, then the flag trips.
    assert storage.client.forward_messages.await_count <= 2
    assert storage.client.send_file.await_count == 4


def test_unrestricted_source_still_forwards():
    """The fix must not turn every mirror into a re-upload."""
    msgs = [_photo_message(1), _photo_message(2)]
    storage = _storage(msgs)
    storage.client.forward_messages = AsyncMock(return_value=None)

    stats = _run_mirror(storage)

    assert stats["forwarded"] == 2
    assert stats["uploaded"] == 0
    assert stats["forward_restricted"] == 0
    storage.client.send_file.assert_not_awaited()
