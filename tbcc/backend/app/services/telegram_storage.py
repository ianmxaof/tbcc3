import asyncio
import io
import logging
import os

from telethon import TelegramClient
from telethon.errors.rpcerrorlist import ImageProcessFailedError
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage, DocumentAttributeVideo
from sqlalchemy.orm import Session

from app.models.media import Media
from app.services.media_sniff import sniff_media_kind, telegram_media_type_from_sniff
from app.services.media_watermark import maybe_apply_media_watermark
from app.services.telegram_album_plan import TELEGRAM_ALBUM_MAX, chunk_sequence_with_promo_tail

logger = logging.getLogger(__name__)


def _channel_message_media_kind(message) -> str | None:
    media = message.media
    if not media:
        return None
    if isinstance(media, MessageMediaWebPage):
        wp = media.webpage
        if wp is None or (not getattr(wp, "photo", None) and not getattr(wp, "document", None)):
            return None
        if getattr(wp, "document", None):
            mime = (getattr(wp.document, "mime_type", None) or "").lower()
            return "video" if "video" in mime else "photo"
        return "photo"
    if isinstance(media, MessageMediaPhoto):
        return "photo"
    if isinstance(media, MessageMediaDocument):
        mime = (media.document.mime_type or "").lower()
        if "video" in mime:
            return "video"
        if "image" in mime or mime in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            return "photo"
        return "document"
    return "document"


def _channel_accepts_media_kind(kind: str | None, media_types: str) -> bool:
    from app.services.scrape_run_service import normalize_media_types

    if not kind:
        return False
    mt = normalize_media_types(media_types)
    if mt == "both":
        return kind in ("photo", "video")
    if mt == "photos":
        return kind == "photo"
    if mt == "videos":
        return kind == "video"
    return False


class TelegramStorage:
    """
    Uploads media to Saved Messages and returns file metadata.
    No media is stored locally — only file_id and file_unique_id go to the DB.
    """

    def __init__(self, client: TelegramClient):
        self.client = client

    def _prepare_file_for_send(self, data: bytes, media_type_hint: str, *, skip_watermark: bool = False):
        """
        Build BytesIO + send kwargs + album bucket (photo vs video for grouping).
        """
        if not skip_watermark:
            data = maybe_apply_media_watermark(data, media_type_hint, force_skip=skip_watermark)
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

    async def save_batch_to_saved_only(
        self,
        items: list[tuple[bytes, str]],
        caption: str | None = None,
        *,
        promo_item: tuple[bytes, str] | None = None,
    ) -> bool:
        """
        Send many media to Saved Messages as Telegram albums (max 10 per album).
        Preserves order; splits into contiguous photo vs video runs, chunks each run by 10.
        The same caption is attached to each album chunk (and to single-media sends).

        When promo_item is set, it is included in the last album of the matching media-type run
        (not as a separate trailing album).
        """
        cap = (caption or "").strip() or None
        prepared: list[tuple[io.BytesIO, dict, str]] = []
        for data, hint in items:
            if not data:
                continue
            f, kwargs, bucket = self._prepare_file_for_send(data, hint)
            prepared.append((f, kwargs, bucket))

        promo_prepared: tuple[io.BytesIO, dict, str] | None = None
        promo_bucket: str | None = None
        if promo_item and promo_item[0]:
            f, kwargs, bucket = self._prepare_file_for_send(promo_item[0], promo_item[1], skip_watermark=True)
            promo_prepared = (f, kwargs, bucket)
            promo_bucket = bucket

        if not prepared and promo_prepared:
            await self._send_album_chunk([promo_prepared], caption=cap)
            return True
        if not prepared:
            return True

        runs = self._runs_contiguous_same_bucket(prepared)
        promo_run_idx: int | None = None
        if promo_prepared and promo_bucket:
            for idx in range(len(runs) - 1, -1, -1):
                if runs[idx] and runs[idx][0][2] == promo_bucket:
                    promo_run_idx = idx
                    break

        for run_idx, run in enumerate(runs):
            if promo_prepared is not None and run_idx == promo_run_idx:
                for chunk in chunk_sequence_with_promo_tail(run, promo_prepared, TELEGRAM_ALBUM_MAX):
                    await self._send_album_chunk(chunk, caption=cap)
            else:
                for i in range(0, len(run), TELEGRAM_ALBUM_MAX):
                    chunk = run[i : i + TELEGRAM_ALBUM_MAX]
                    await self._send_album_chunk(chunk, caption=cap)
        return True

    @staticmethod
    def _message_media_bucket(message) -> str:
        media = message.media
        if isinstance(media, MessageMediaPhoto):
            return "photo"
        if isinstance(media, MessageMediaDocument):
            doc = media.document
            if doc:
                for attr in doc.attributes or []:
                    if isinstance(attr, DocumentAttributeVideo):
                        return "video"
                mime = (doc.mime_type or "").lower()
                if mime.startswith("video/"):
                    return "video"
                if mime.startswith("image/"):
                    return "photo"
        return "photo"

    async def _resolve_album_bot_entity(self, bot_peer: str | int):
        """Resolve bot DM peer (numeric id, @username, or env token user id)."""
        candidates: list[str | int] = []
        token_uid = None
        token = (os.getenv("TBCC_ALBUM_COMPOSER_BOT_TOKEN") or "").strip()
        if token and ":" in token:
            try:
                token_uid = int(token.split(":", 1)[0])
            except ValueError:
                token_uid = None
        if token_uid:
            candidates.append(token_uid)
        if bot_peer is not None:
            candidates.append(bot_peer)
        if isinstance(bot_peer, str) and bot_peer.lstrip("@").isdigit():
            candidates.append(int(bot_peer.lstrip("@")))
        seen: set[str] = set()
        last_err: Exception | None = None
        for peer in candidates:
            key = str(peer)
            if key in seen:
                continue
            seen.add(key)
            try:
                return await self.client.get_entity(peer)
            except Exception as e:
                last_err = e
        if last_err:
            raise last_err
        raise ValueError("Could not resolve album bot peer")

    async def _fetch_bot_media_for_batch(
        self,
        bot_peer: str | int,
        media_count: int,
        message_ids: list[int] | None = None,
        *,
        anchor_max_message_id: int | None = None,
    ) -> list:
        """
        Resolve staged bot DM media without Bot API download.
        User uploads are outgoing (from_user=me); bot replies are incoming text.
        """
        if media_count < 1:
            raise ValueError("media_count must be >= 1")
        entity = await self._resolve_album_bot_entity(bot_peer)
        ids = [int(i) for i in (message_ids or []) if i]
        anchor_max = anchor_max_message_id or (max(ids) if ids else None)

        if ids:
            raw = await self.client.get_messages(entity, ids=ids)
            if not isinstance(raw, list):
                raw = [raw] if raw else []
            by_id = {m.id: m for m in raw if m and m.media}
            ordered = [by_id[i] for i in ids if i in by_id]
            if len(ordered) >= media_count:
                return ordered[:media_count]

        candidates: list = []
        scan_limit = min(500, max(media_count * 15 + 50, 80))
        async for msg in self.client.iter_messages(entity, limit=scan_limit, from_user="me"):
            if anchor_max and msg.id > anchor_max:
                continue
            if not msg.media:
                continue
            candidates.append(msg)

        if ids:
            by_id = {m.id: m for m in candidates}
            ordered = [by_id[i] for i in ids if i in by_id]
            if len(ordered) >= media_count:
                return ordered[:media_count]

        if len(candidates) >= media_count:
            batch = candidates[:media_count]
            batch.reverse()
            return batch

        raise ValueError(
            f"Found {len(candidates)}/{media_count} media in bot chat. "
            "Re-send the batch to the bot (avoid old chat history), then try again."
        )

    async def _dispatch_message_runs(
        self,
        runs: list[list],
        *,
        destination: str | int = "me",
        caption: str | None = None,
        promo_prepared: tuple[io.BytesIO, dict, str] | None = None,
        promo_bucket: str | None = None,
        promo_run_idx: int | None = None,
        base_send_kw: dict | None = None,
        parallel_chunks: bool = True,
    ) -> None:
        cap = (caption or "").strip() or None
        caption_used = False
        jobs: list = []

        async def _send(chunk, chunk_cap, kw):
            nonlocal buttons_used
            send_kw = dict(kw)
            if buttons_used and "buttons" in send_kw:
                send_kw.pop("buttons", None)
            await self._send_album_chunk_refs(
                chunk, caption=chunk_cap, destination=destination, send_kwargs=send_kw
            )
            if send_kw.get("buttons"):
                buttons_used = True

        buttons_used = False
        for run_idx, run in enumerate(runs):
            if promo_prepared is not None and run_idx == promo_run_idx:
                chunks = chunk_sequence_with_promo_tail(run, promo_prepared, TELEGRAM_ALBUM_MAX)
            else:
                chunks = [run[i : i + TELEGRAM_ALBUM_MAX] for i in range(0, len(run), TELEGRAM_ALBUM_MAX)]
            for chunk in chunks:
                kw = dict(base_send_kw or {})
                chunk_cap = cap if not caption_used else None
                if chunk_cap:
                    caption_used = True
                jobs.append(_send(chunk, chunk_cap, kw))

        if parallel_chunks and len(jobs) > 1:
            await asyncio.gather(*jobs)
        else:
            for job in jobs:
                await job()

    async def _fetch_bot_messages_ordered(self, bot_peer: str | int, message_ids: list[int]):
        return await self._fetch_bot_media_for_batch(
            bot_peer, len(message_ids), message_ids=message_ids
        )

    async def _send_album_chunk_refs(
        self,
        chunk: list,
        caption: str | None = None,
        *,
        destination: str | int = "me",
        send_kwargs: dict | None = None,
    ):
        """Send album chunk from Telethon Message refs and/or prepared byte tuples."""
        cap = (caption or "").strip() or None
        if not chunk:
            return
        base_kw = dict(send_kwargs or {})
        files: list = []
        for item in chunk:
            if isinstance(item, tuple):
                f, kwargs, _bucket = item
                files.append(f)
                if kwargs.get("supports_streaming"):
                    base_kw["supports_streaming"] = True
            else:
                files.append(item)
        if len(files) == 1:
            kw = dict(base_kw)
            if cap:
                kw["caption"] = cap
            return await self.client.send_file(destination, files[0], **kw)
        kw = dict(base_kw)
        if cap:
            kw["caption"] = cap
        try:
            return await self.client.send_file(destination, files, **kw)
        except ImageProcessFailedError:
            logger.warning("Album ref send failed; falling back to one-by-one")
            for idx, single in enumerate(files):
                one_kw = dict(base_kw)
                if cap and idx == 0:
                    one_kw["caption"] = cap
                await self.client.send_file(destination, single, **one_kw)

    def _runs_contiguous_message_buckets(self, messages: list) -> list[list]:
        runs: list[list] = []
        cur: list = []
        last_bucket: str | None = None
        for msg in messages:
            bucket = self._message_media_bucket(msg)
            if last_bucket is None or bucket == last_bucket:
                cur.append(msg)
            else:
                if cur:
                    runs.append(cur)
                cur = [msg]
            last_bucket = bucket
        if cur:
            runs.append(cur)
        return runs

    async def save_bot_messages_to_saved_only(
        self,
        bot_peer: str | int,
        media_count: int,
        caption: str | None = None,
        *,
        message_ids: list[int] | None = None,
        anchor_max_message_id: int | None = None,
        promo_item: tuple[bytes, str] | None = None,
    ) -> bool:
        """
        Copy media from the admin DM with the album bot to Saved Messages (Telethon refs only).
        """
        ordered = await self._fetch_bot_media_for_batch(
            bot_peer,
            media_count,
            message_ids=message_ids,
            anchor_max_message_id=anchor_max_message_id,
        )
        cap = (caption or "").strip() or None

        promo_prepared: tuple[io.BytesIO, dict, str] | None = None
        promo_bucket: str | None = None
        if promo_item and promo_item[0]:
            promo_prepared = self._prepare_file_for_send(promo_item[0], promo_item[1], skip_watermark=True)
            promo_bucket = promo_prepared[2]

        if not ordered and promo_prepared:
            await self._send_album_chunk_refs([promo_prepared], caption=cap)
            return True
        if not ordered:
            return True

        runs = self._runs_contiguous_message_buckets(ordered)
        promo_run_idx: int | None = None
        if promo_prepared and promo_bucket:
            for idx in range(len(runs) - 1, -1, -1):
                if runs[idx] and self._message_media_bucket(runs[idx][0]) == promo_bucket:
                    promo_run_idx = idx
                    break

        await self._dispatch_message_runs(
            runs,
            destination="me",
            caption=cap,
            promo_prepared=promo_prepared,
            promo_bucket=promo_bucket,
            promo_run_idx=promo_run_idx,
            parallel_chunks=True,
        )
        return True

    async def post_bytes_to_channel(
        self,
        channel: str | int,
        items: list[tuple[bytes, str]],
        message_thread_id: int | None,
        caption: str | None = None,
        *,
        send_silent: bool = False,
        reply_markup=None,
        promo_item: tuple[bytes, str] | None = None,
        skip_watermark: bool = False,
    ) -> dict:
        """Post downloaded bot media bytes to a channel/topic (album chunks ≤10)."""
        from app.services.scheduled_post_service import _apply_telethon_html_to_kwargs

        cap = (caption or "").strip() or None
        silent_kw = {"silent": True} if send_silent else {}
        base_send_kw: dict = {"reply_to": message_thread_id, **silent_kw}

        prepared: list[tuple[io.BytesIO, dict, str]] = []
        for data, hint in items:
            if not data:
                continue
            prepared.append(self._prepare_file_for_send(data, hint, skip_watermark=skip_watermark))

        promo_prepared: tuple[io.BytesIO, dict, str] | None = None
        promo_bucket: str | None = None
        if promo_item and promo_item[0]:
            promo_prepared = self._prepare_file_for_send(promo_item[0], promo_item[1], skip_watermark=True)
            promo_bucket = promo_prepared[2]

        if not prepared and promo_prepared:
            kw = dict(base_send_kw)
            if reply_markup is not None:
                kw["buttons"] = reply_markup
            _apply_telethon_html_to_kwargs(kw, cap or "", field="caption")
            await self._send_album_chunk_refs(
                [promo_prepared], caption=cap, destination=channel, send_kwargs=kw
            )
            return {"ok": True, "sent_chunks": 1, "errors": []}

        runs = self._runs_contiguous_same_bucket(prepared)
        promo_run_idx: int | None = None
        if promo_prepared and promo_bucket:
            for idx in range(len(runs) - 1, -1, -1):
                if runs[idx] and runs[idx][0][2] == promo_bucket:
                    promo_run_idx = idx
                    break

        sent = 0
        errs: list[str] = []
        buttons_attached = False
        for run_idx, run in enumerate(runs):
            if promo_prepared is not None and run_idx == promo_run_idx:
                chunks = chunk_sequence_with_promo_tail(run, promo_prepared, TELEGRAM_ALBUM_MAX)
            else:
                chunks = [run[i : i + TELEGRAM_ALBUM_MAX] for i in range(0, len(run), TELEGRAM_ALBUM_MAX)]
            for chunk in chunks:
                try:
                    kw = dict(base_send_kw)
                    chunk_markup = reply_markup if not buttons_attached else None
                    if chunk_markup is not None:
                        kw["buttons"] = chunk_markup
                    _apply_telethon_html_to_kwargs(kw, cap or "", field="caption")
                    await self._send_album_chunk_refs(
                        chunk, caption=cap, destination=channel, send_kwargs=kw
                    )
                    buttons_attached = buttons_attached or chunk_markup is not None
                    sent += 1
                except Exception as e:
                    errs.append(str(e))
        return {"ok": not errs, "sent_chunks": sent, "errors": errs}

    async def _send_bytes_to_me(
        self,
        data: bytes,
        media_type_hint: str,
        caption: str | None = None,
        *,
        skip_watermark: bool = False,
    ):
        """
        Upload bytes to Saved Messages with correct extension / streaming flags.
        Magic-byte sniff fixes wrong Content-Type (e.g. GIF guessed as video → .mp4).
        Retries as document if Telegram cannot process as inline photo/video.
        """
        f, kwargs, _bucket = self._prepare_file_for_send(
            data, media_type_hint, skip_watermark=skip_watermark
        )
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

    async def store_from_bytes(
        self,
        data: bytes,
        media_type: str,
        source: str,
        pool_id: int,
        db: Session,
        *,
        skip_watermark: bool = False,
    ):
        msg = await self._send_bytes_to_me(data, media_type, skip_watermark=skip_watermark)
        return await self._index_message(msg, source, pool_id, db)

    async def store_from_bytes_preprocessed(self, data: bytes, media_type: str, source: str, pool_id: int, db: Session):
        """Upload bytes that already had crop/watermark applied (no second burn-in)."""
        return await self.store_from_bytes(data, media_type, source, pool_id, db, skip_watermark=True)

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

    def is_duplicate_message(self, message, pool_id: int, db: Session) -> bool:
        """True if this message media is already indexed in the pool."""
        media = message.media
        if media is None:
            return False
        file_unique_id = None
        if isinstance(media, MessageMediaPhoto):
            file_unique_id = str(media.photo.id)
        elif isinstance(media, MessageMediaDocument):
            file_unique_id = str(media.document.id)
        elif isinstance(media, MessageMediaWebPage):
            wp = media.webpage
            if wp and getattr(wp, "photo", None):
                file_unique_id = str(wp.photo.id)
            elif wp and getattr(wp, "document", None):
                file_unique_id = str(wp.document.id)
        if not file_unique_id:
            return False
        existing = db.query(Media).filter(
            Media.file_unique_id == file_unique_id, Media.pool_id == pool_id
        ).first()
        return existing is not None

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
            from app.services.auto_tag_enrich import enqueue_auto_tag_enrich_if_enabled

            enqueue_auto_tag_enrich_if_enabled(record.id)
        except Exception:
            logger.exception("auto-tag failed for media id=%s", getattr(record, "id", "?"))
        return record

    async def download_bot_batch_bytes(
        self,
        bot_peer: str | int,
        media_count: int,
        *,
        message_ids: list[int] | None = None,
        anchor_max_message_id: int | None = None,
    ) -> list[tuple[bytes, str]]:
        ordered = await self._fetch_bot_media_for_batch(
            bot_peer,
            media_count,
            message_ids=message_ids,
            anchor_max_message_id=anchor_max_message_id,
        )
        out: list[tuple[bytes, str]] = []
        for msg in ordered:
            data = await self.client.download_media(msg, bytes)
            if not data:
                continue
            bucket = self._message_media_bucket(msg)
            hint = "video" if bucket == "video" else "photo"
            out.append((data, hint))
        return out

    async def index_from_saved_messages_watermarked(
        self,
        pool_id: int,
        source: str,
        db: Session,
        limit: int = 50,
        *,
        wm=None,
    ) -> dict[str, int]:
        from app.services.media_watermark import maybe_apply_media_watermark, watermark_config_context
        from app.services.watermark_settings_effective import build_apply_config

        cfg = build_apply_config(db, override=wm)
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
            if self.is_duplicate_message(message, pool_id, db):
                skipped += 1
                continue
            try:
                data = await self.client.download_media(message, bytes)
            except Exception:
                logger.warning("watermarked saved import: download failed msg=%s", getattr(message, "id", "?"))
                skipped += 1
                continue
            if not data:
                skipped += 1
                continue
            bucket = self._message_media_bucket(message)
            hint = "video" if bucket == "video" else "photo"
            with watermark_config_context(cfg):
                data = maybe_apply_media_watermark(data, hint, config=cfg)
            rec = await self.store_from_bytes_preprocessed(data, hint, source, pool_id, db)
            if rec is not None:
                indexed += 1
            else:
                skipped += 1
        return {
            "indexed": indexed,
            "skipped_duplicates_or_unsupported": skipped,
            "messages_scanned": scanned,
            "watermarked": True,
        }

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

    async def list_forum_topics(self, channel_identifier: str) -> list[dict]:
        from telethon import functions

        from app.services.forum_topics import parse_forum_topics_response
        from app.utils.telegram_peer import resolve_telethon_entity

        entity = await resolve_telethon_entity(self.client, channel_identifier)
        resp = await self.client(
            functions.messages.GetForumTopicsRequest(
                peer=entity,
                offset_date=None,
                offset_id=0,
                offset_topic=0,
                limit=200,
                q=None,
            )
        )
        return parse_forum_topics_response(resp)

    async def import_from_telegram_channel(
        self,
        channel_identifier: str,
        pool_id: int,
        source_label: str,
        db: Session,
        limit: int = 50,
        media_types: str = "both",
        message_thread_id: int | None = None,
    ) -> dict[str, int]:
        """
        Pull recent channel/group media into a pool via Saved Messages (forward or download).
        Requires the Telethon account (admin session) to be able to read the chat.
        When message_thread_id is set, only messages from that forum topic are imported.
        """
        from app.utils.telegram_peer import resolve_telethon_entity

        stored = 0
        skipped_duplicate = 0
        skipped_media_type = 0
        skipped_no_media = 0
        scanned = 0
        entity = await resolve_telethon_entity(self.client, channel_identifier)
        iter_kw: dict = {"limit": limit}
        if message_thread_id is not None:
            iter_kw["reply_to"] = int(message_thread_id)
        async for message in self.client.iter_messages(entity, **iter_kw):
            scanned += 1
            kind = _channel_message_media_kind(message)
            if not kind:
                skipped_no_media += 1
                continue
            if not _channel_accepts_media_kind(kind, media_types):
                skipped_media_type += 1
                continue
            if self.is_duplicate_message(message, pool_id, db):
                skipped_duplicate += 1
                await asyncio.sleep(0.05)
                continue
            try:
                rec = await self.store_from_message(message, source_label, pool_id, db)
                if rec is not None:
                    stored += 1
                else:
                    skipped_duplicate += 1
            except Exception:
                logger.exception(
                    "import_from_telegram_channel store failed pool_id=%s msg_id=%s",
                    pool_id,
                    getattr(message, "id", "?"),
                )
            await asyncio.sleep(0.35)
        return {
            "stored": stored,
            "skipped_duplicate": skipped_duplicate,
            "skipped_media_type": skipped_media_type,
            "skipped_no_media": skipped_no_media,
            "messages_scanned": scanned,
            "message_thread_id": message_thread_id,
        }
