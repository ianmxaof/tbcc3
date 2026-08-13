"""Loot album bytes: one Telethon lock per roll, not per item."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.media import Media


def _media_row(mid: int, tg_id: int) -> Media:
    row = MagicMock(spec=Media)
    row.id = mid
    row.telegram_message_id = tg_id
    row.file_id = f"tg:{tg_id}"
    row.media_type = "photo"
    return row


def test_batch_load_uses_single_import_io_for_many_rows():
    from app.services.loot_preview_delivery import _batch_load_media_bytes

    rows = [_media_row(1, 101), _media_row(2, 102)]
    fake = (b"\xff\xd8\xff" + b"x" * 80, "loot.jpg")

    async def _fake_many(need_rows):
        assert len(need_rows) == 2
        return {1: fake, 2: fake}, set()

    async def _run():
        with patch(
            "app.services.loot_preview_delivery._try_local_or_cached_bytes",
            return_value=None,
        ), patch(
            "app.services.loot_preview_delivery._download_many_saved_media_bytes",
            side_effect=_fake_many,
        ) as batch_mock:
            ordered, notes = await _batch_load_media_bytes(rows)
            assert batch_mock.await_count == 1

        assert len(ordered) == 2
        assert notes == []

    asyncio.run(_run())


def test_batch_load_prefers_local_without_telethon():
    from app.services.loot_preview_delivery import _batch_load_media_bytes

    row = _media_row(9, 0)
    fake = (b"\xff\xd8\xff" + b"y" * 80, "loot.jpg")

    async def _run():
        with patch(
            "app.services.loot_preview_delivery._try_local_or_cached_bytes",
            return_value=fake,
        ), patch(
            "app.services.loot_preview_delivery._download_many_saved_media_bytes",
            new_callable=AsyncMock,
        ) as batch_mock:
            ordered, notes = await _batch_load_media_bytes([row])
            batch_mock.assert_not_awaited()

        assert len(ordered) == 1
        assert ordered[0][1] == fake[0]
        assert notes == []

    asyncio.run(_run())


def test_infra_failure_does_not_quarantine():
    """Lock/timeout failures must never reject live media — only confirmed-missing does."""
    from app.services.loot_preview_delivery import _batch_load_media_bytes

    rows = [_media_row(4, 401), _media_row(5, 501)]

    async def _fake_many(need_rows):
        return {}, {5}

    async def _run():
        db = MagicMock()
        with patch(
            "app.services.loot_preview_delivery._try_local_or_cached_bytes",
            return_value=None,
        ), patch(
            "app.services.loot_preview_delivery._download_many_saved_media_bytes",
            side_effect=_fake_many,
        ), patch(
            "app.services.loot_preview_delivery.quarantine_stale_saved_message"
        ) as quarantine:
            ordered, notes = await _batch_load_media_bytes(rows, db=db)

        assert ordered == []
        assert quarantine.call_count == 1
        assert quarantine.call_args.args[1].id == 5
        assert any("infra" in n for n in notes)

    asyncio.run(_run())


def test_batch_keeps_partial_results_when_one_item_dies():
    from app.services.loot_preview_delivery import _download_many_saved_media_bytes

    rows = [_media_row(1, 101), _media_row(2, 102)]
    fake = (b"\xff\xd8\xff" + b"z" * 80, "loot.jpg")

    async def _fake_download(_storage, tg_id):
        if int(tg_id) == 102:
            raise ValueError(f"Saved message {tg_id} not found or has no media")
        return fake

    async def _run():
        async def _fake_import_io(fn):
            return await fn(MagicMock())

        with patch(
            "app.services.loot_preview_delivery._loot_telegram_io",
            side_effect=_fake_import_io,
        ), patch(
            "app.services.loot_preview_delivery._download_saved_media_from_storage",
            side_effect=_fake_download,
        ):
            got, missing = await _download_many_saved_media_bytes(rows)

        assert list(got) == [1]
        assert missing == {2}

    asyncio.run(_run())
