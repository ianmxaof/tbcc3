import io
import logging

from telethon import TelegramClient
from telethon.errors.rpcerrorlist import ImageProcessFailedError
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage
from sqlalchemy.orm import Session

from app.models.media import Media
from app.services.media_sniff import sniff_media_kind, telegram_media_type_from_sniff

logger = logging.getLogger(__name__)


TELEGRAM_ALBUM_MAX = 10


class TelegramStorage:
    """
    Uploads media to Saved Messages and returns file metadata.
    No media is stored locally — only file_id and file_unique_id go to the DB.
    """

    def __init__(self, client: TelegramClient):
        self.client = client

    def _prepare_file_for_send(self, data: bytes, media_type_hint: str):
        """
        Build BytesIO + send kwargs + album bucket (photo vs video for grouping).
        """
        kind, ext = sniff_media_kind(data)
        hint = (media_type_hint or "photo").lower()
        if hint not in ("photo", "video", "document"):
            hint = "photo"

        if kind != "document":
            media_type = telegram_media_type_from_sniff(kind)
        else:
            media_type = hint

        if ext == "bin":
            ext = "jpg" if media_type == "photo" else "mp4" if media_type == "video" else "dat"

        f = io.BytesIO(data)
        f.name = f"media.{ext}"
        kwargs: dict = {"force_document": False}
        if media_type == "video":
            kwargs["supports_streaming"] = True

        bucket = "video" if media_type == "video" else "photo"
        return f, kwargs, bucket

    async def _send_one_prepared(self, f: io.BytesIO, kwargs: dict):
        try:
            return await self.client.send_file("me", f, **kwargs)
        except ImageProcessFailedError:
            logger.warning("Telegram ImageProcessFailed for %s; retrying as document", getattr(f, "name", "?"))
            f2 = io.BytesIO(f.getvalue())
            f2.name = getattr(f, "name", "media.jpg")
            kw = {"force_document": True}
            if kwargs.get("caption"):
                kw["caption"] = kwargs["caption"]
            return await self.client.send_file("me", f2, **kw)

    async def _send_album_chunk(self, chunk: list[tuple[io.BytesIO, dict, str]], caption: str | None = None):
        """Send up to TELEGRAM_ALBUM_MAX items as one album (same bucket: photo or video)."""
        cap = (caption or "").strip() or None
        if not chunk:
            return
        if len(chunk) == 1:
            f, kwargs, _ = chunk[0]
            kw = dict(kwargs)
            if cap:
                kw["caption"] = cap
            return await self._send_one_prepared(f, kw)

        bucket = chunk[0][2]
        files = []
        send_kwargs: dict = {}
        for f, kwargs, b in chunk:
            if b != bucket:
                logger.warning("Album chunk had mixed buckets; sending individually")
                for idx, item in enumerate(chunk):
                    f0, kw0, _ = item
                    kw = dict(kw0)
                    if cap and idx == 0:
                        kw["caption"] = cap
                    await self._send_one_prepared(f0, kw)
                return
            files.append(f)
            if kwargs.get("supports_streaming"):
                send_kwargs["supports_streaming"] = True

        if cap:
            send_kwargs["caption"] = cap
        try:
            return await self.client.send_file("me", files, **send_kwargs)
        except ImageProcessFailedError:
            logger.warning("Album send failed; falling back to one-by-one")
            for idx, (f, kwargs, _) in enumerate(chunk):
                kw = dict(kwargs)
                if cap and idx == 0:
                    kw["caption"] = cap
                await self._send_one_prepared(f, kw)

    def _runs_contiguous_same_bucket(
        self, prepared: list[tuple[io.BytesIO, dict, str]]
    ) -> list[list[tuple[io.BytesIO, dict, str]]]:
        """Split into runs of consecutive photo vs video (Telegram album rule)."""
        runs: list[list[tuple[io.BytesIO, dict, str]]] = []
        cur: list[tuple[io.BytesIO, dict, str]] = []
        last_bucket: str | None = None

        for item in prepared:
            f, kwargs, bucket = item
            if last_bucket is None or bucket == last_bucket:
                cur.append(item)
            else:
                if cur:
                    runs.append(cur)
                cur = [item]
            last_bucket = bucket
        if cur:
            runs.append(cur)
        return runs

    async def save_batch_to_saved_only(self, items: list[tuple[bytes, str]], caption: str | None = None) -> bool:
        """
        Send many media to Saved Messages as Telegram albums (max 10 per album).
        Preserves order; splits into contiguous photo vs video runs, chunks each run by 10.
        The same caption is attached to each album chunk (and to single-media sends).
        """
        if not items:
            return True
        cap = (caption or "").strip() or None
        prepared: list[tuple[io.BytesIO, dict, str]] = []
        for data, hint in items:
            if not data:
                continue
            f, kwargs, bucket = self._prepare_file_for_send(data, hint)
            prepared.append((f, kwargs, bucket))

        runs = self._runs_contiguous_same_bucket(prepared)
        for run in runs:
            for i in range(0, len(run), TELEGRAM_ALBUM_MAX):
                chunk = run[i : i + TELEGRAM_ALBUM_MAX]
                await self._send_album_chunk(chunk, caption=cap)
        return True

    async def _send_bytes_to_me(self, data: bytes, media_type_hint: str, caption: str | None = None):
        """
        Upload bytes to Saved Messages with correct extension / streaming flags.
        Magic-byte sniff fixes wrong Content-Type (e.g. GIF guessed as video → .mp4).
        Retries as document if Telegram cannot process as inline photo/video.
        """
        f, kwargs, _bucket = self._prepare_file_for_send(data, media_type_hint)
        cap = (caption or "").strip() or None
        if cap:
            kwargs = {**kwargs, "caption": cap}
        try:
            return await self.client.send_file("me", f, **kwargs)
        except ImageProcessFailedError:
            logger.warning(
                "Telegram ImageProcessFailed for %s; retrying as document", getattr(f, "name", "?")
            )
            f2 = io.BytesIO(data)
            f2.name = getattr(f, "name", "media.jpg")
            kw2: dict = {"force_document": True}
            if cap:
                kw2["caption"] = cap
            return await self.client.send_file("me", f2, **kw2)

    async def store_from_bytes(self, data: bytes, media_type: str, source: str, pool_id: int, db: Session):
        msg = await self._send_bytes_to_me(data, media_type)
        return await self._index_message(msg, source, pool_id, db)

    async def save_to_saved_only(self, data: bytes, media_type: str, caption: str | None = None) -> bool:
        """Save to Saved Messages only (no pool, no Media record)."""
        await self._send_bytes_to_me(data, media_type, caption=caption)
        return True

    async def store_from_message(self, message, source: str, pool_id: int, db: Session):
        """
        Prefer forwarding the original message (no download). If the channel forbids
        forwarding (very common), fall back to download_media + upload to Saved Messages.
        """
        if not message.media:
            return None
        try:
            msg = await self.client.forward_messages("me", message)
            return await self._index_message(msg, source, pool_id, db)
        except Exception as e:
            logger.warning(
                "forward_messages to Saved Messages failed (%s): %s — trying download_media",
                type(e).__name__,
                e,
            )
        try:
            data = await self.client.download_media(message, bytes)
        except Exception as e2:
            logger.warning("download_media failed: %s", e2)
            return None
        if not data:
            logger.warning("download_media returned empty bytes")
            return None
        kind, _ext = sniff_media_kind(data)
        hint = (
            "photo"
            if kind == "photo"
            else "video"
            if kind == "video"
            else "document"
        )
        return await self.store_from_bytes(data, hint, source, pool_id, db)

    async def _index_message(self, msg, source: str, pool_id: int, db: Session):
        media = msg.media
        if media is None:
            return None
        if isinstance(media, MessageMediaPhoto):
            file_id = str(media.photo.id)
            file_unique_id = str(media.photo.id)
            media_type = "photo"
        elif isinstance(media, MessageMediaDocument):
            file_id = str(media.document.id)
            file_unique_id = str(media.document.id)
            mime = (media.document.mime_type or "").lower()
            if "video" in mime:
                media_type = "video"
            elif "image" in mime or mime in ("image/jpeg", "image/png", "image/webp", "image/gif"):
                media_type = "photo"
            else:
                media_type = "document"
        else:
            logger.debug("Skipping unsupported forwarded media type: %s", type(media).__name__)
            return None

        existing = db.query(Media).filter(
            Media.file_unique_id == file_unique_id, Media.pool_id == pool_id
        ).first()
        if existing:
            return None

        record = Media(
            telegram_message_id=msg.id,
            file_id=file_id,
            file_unique_id=file_unique_id,
            media_type=media_type,
            source_channel=source,
            pool_id=pool_id,
            status="pending",
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        try:
            from app.services.media_tagging import apply_auto_tags_for_new_media

            apply_auto_tags_for_new_media(db, record.id)
            from app.services.auto_tag_llm import enqueue_auto_tag_llm_if_enabled

            enqueue_auto_tag_llm_if_enabled(record.id)
        except Exception:
            logger.exception("auto-tag failed for media id=%s", getattr(record, "id", "?"))
        return record

    async def index_from_saved_messages(
        self,
        pool_id: int,
        source: str,
        db: Session,
        limit: int = 50,
    ) -> dict[str, int]:
        """
        Create Media rows for media already in Telegram Saved Messages ("me").
        Newest messages first (same order as iter_messages default). No re-upload.
        """
        indexed = 0
        skipped = 0
        scanned = 0
        async for message in self.client.iter_messages("me", limit=limit):
            scanned += 1
            if not message.media:
                continue
            if isinstance(message.media, MessageMediaWebPage):
                wp = message.media.webpage
                if wp is None or (
                    not getattr(wp, "photo", None) and not getattr(wp, "document", None)
                ):
                    continue
            rec = await self._index_message(message, source, pool_id, db)
            if rec is not None:
                indexed += 1
            else:
                skipped += 1
        return {
            "indexed": indexed,
            "skipped_duplicates_or_unsupported": skipped,
            "messages_scanned": scanned,
        }
