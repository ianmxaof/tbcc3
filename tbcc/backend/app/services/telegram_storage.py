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


def _post_media_ingest(
    db: Session,
    record: Media,
    *,
    caption: str = "",
    message=None,
    source_label: str | None = None,
) -> None:
    """Run gatekeeper verdict then optional Storage Hub auto-approve."""
    try:
        from app.services.media_gatekeeper import (
            apply_gatekeeper_after_ingest,
            should_attempt_storage_auto_approve,
        )
        from app.services.storage_deposit_auto_approve import maybe_auto_approve_storage_deposit_media

        apply_gatekeeper_after_ingest(
            db,
            int(record.id),
            caption=caption,
            message=message,
            source_label=source_label,
        )
        db.refresh(record)
        if should_attempt_storage_auto_approve(db, int(record.id), source_label=source_label):
            maybe_auto_approve_storage_deposit_media(
                db,
                int(record.id),
                source_label=source_label,
            )
    except Exception:
        logger.exception("post_media_ingest failed media_id=%s", getattr(record, "id", "?"))


class ForwardRestrictedStorageError(Exception):
    """Channel forbids forwarding; scraper must skip (no download_media fallback)."""


def _document_video_attributes(document) -> list[DocumentAttributeVideo] | None:
    if not document:
        return None
    for attr in document.attributes or []:
        if isinstance(attr, DocumentAttributeVideo):
            return [
                DocumentAttributeVideo(
                    duration=max(0, int(getattr(attr, "duration", 0) or 0)),
                    w=max(0, int(getattr(attr, "w", 0) or 0)),
                    h=max(0, int(getattr(attr, "h", 0) or 0)),
                    supports_streaming=True,
                )
            ]
    mime = (getattr(document, "mime_type", None) or "").lower()
    if mime.startswith("video/"):
        return [DocumentAttributeVideo(duration=0, w=0, h=0, supports_streaming=True)]
    return None


def _video_attributes_from_message(message) -> list[DocumentAttributeVideo] | None:
    media = getattr(message, "media", None)
    if isinstance(media, MessageMediaDocument):
        return _document_video_attributes(media.document)
    if isinstance(media, MessageMediaWebPage):
        wp = media.webpage
        if wp is not None and getattr(wp, "document", None):
            return _document_video_attributes(wp.document)
    return None


def _channel_message_media_kind(message) -> str | None:
    media = message.media
    if not media:
        return None
    if isinstance(media, MessageMediaWebPage):
        wp = media.webpage
        if wp is None or (not getattr(wp, "photo", None) and not getattr(wp, "document", None)):
            return None
        if getattr(wp, "document", None):
            if _document_video_attributes(wp.document):
                return "video"
            mime = (getattr(wp.document, "mime_type", None) or "").lower()
            return "video" if "video" in mime else "photo"
        return "photo"
    if isinstance(media, MessageMediaPhoto):
        return "photo"
    if isinstance(media, MessageMediaDocument):
        if _document_video_attributes(media.document):
            return "video"
        mime = (media.document.mime_type or "").lower()
        if "video" in mime:
            return "video"
        if "image" in mime or mime in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            return "photo"
        return "document"
    return "document"


def _channel_import_max_scan(target_stored: int) -> int:
    raw = (os.getenv("TBCC_CHANNEL_IMPORT_MAX_SCAN") or "").strip()
    if raw:
        try:
            return max(target_stored, int(raw))
        except ValueError:
            pass
    return min(5000, max(400, target_stored * 40))


def _message_mirror_bucket(message) -> str:
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


def batch_messages_for_album_mirror(
    messages: list,
    *,
    max_size: int = TELEGRAM_ALBUM_MAX,
    bucket_fn=_message_mirror_bucket,
    require_full_albums: bool = False,
) -> list[list]:
    """Group storage-topic messages into Telegram album batches (≤10, same type).

    When require_full_albums is True, only emit full max_size albums until fewer than
    max_size items remain in a homogeneous run (final partial album allowed).
    """
    if not messages:
        return []
    used: set[int] = set()
    batches: list[list] = []
    idx = 0
    while idx < len(messages):
        msg = messages[idx]
        mid = int(getattr(msg, "id", 0) or 0)
        if not mid or mid in used:
            idx += 1
            continue
        grouped_id = getattr(msg, "grouped_id", None)
        if grouped_id:
            album_msgs = sorted(
                [m for m in messages if getattr(m, "grouped_id", None) == grouped_id],
                key=lambda m: int(getattr(m, "id", 0) or 0),
            )
            for start in range(0, len(album_msgs), max_size):
                chunk = album_msgs[start : start + max_size]
                if chunk:
                    batches.append(chunk)
                for m in chunk:
                    used.add(int(getattr(m, "id", 0) or 0))
            idx += 1
            continue
        run = [msg]
        used.add(mid)
        bucket = bucket_fn(msg)
        next_idx = idx + 1
        while next_idx < len(messages) and len(run) < max_size:
            nxt = messages[next_idx]
            nxt_id = int(getattr(nxt, "id", 0) or 0)
            if not nxt_id or nxt_id in used:
                next_idx += 1
                continue
            if getattr(nxt, "grouped_id", None):
                break
            if bucket_fn(nxt) != bucket:
                break
            run.append(nxt)
            used.add(nxt_id)
            next_idx += 1
        if require_full_albums:
            for start in range(0, len(run), max_size):
                chunk = run[start : start + max_size]
                if chunk:
                    batches.append(chunk)
        else:
            batches.append(run)
        idx = next_idx
    return batches


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

    def _prepare_file_for_send(
        self,
        data: bytes,
        media_type_hint: str,
        *,
        skip_watermark: bool = False,
        source_message=None,
    ):
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
            attrs = _video_attributes_from_message(source_message) if source_message else None
            if attrs:
                kwargs["attributes"] = attrs
            else:
                kwargs["attributes"] = [
                    DocumentAttributeVideo(duration=0, w=0, h=0, supports_streaming=True)
                ]

        bucket = "video" if media_type == "video" else "photo"
        return f, kwargs, bucket

    async def _send_one_prepared(
        self,
        f: io.BytesIO,
        kwargs: dict,
        *,
        destination: str | int = "me",
        allow_document_fallback: bool = True,
    ):
        try:
            return await self.client.send_file(destination, f, **kwargs)
        except ImageProcessFailedError:
            if not allow_document_fallback:
                raise
            logger.warning("Telegram ImageProcessFailed for %s; retrying as document", getattr(f, "name", "?"))
            f2 = io.BytesIO(f.getvalue())
            f2.name = getattr(f, "name", "media.jpg")
            kw = {"force_document": True}
            if kwargs.get("caption"):
                kw["caption"] = kwargs["caption"]
            return await self.client.send_file(destination, f2, **kw)

    async def _upload_mirror_media(
        self,
        dest_entity,
        message,
        *,
        dest_thread: int,
        silent_kw: dict,
    ) -> bool:
        """Re-upload one storage-topic message as inline photo/video (never as document)."""
        bucket = _message_mirror_bucket(message)
        if bucket not in ("photo", "video"):
            logger.warning(
                "mirror upload skipped non-album media msg_id=%s bucket=%s",
                getattr(message, "id", "?"),
                bucket,
            )
            return False
        data = await self.client.download_media(message, bytes)
        if not data:
            return False
        f, kwargs, _bucket = self._prepare_file_for_send(
            data,
            bucket,
            skip_watermark=True,
            source_message=message,
        )
        kwargs = {**kwargs, "reply_to": dest_thread, **silent_kw}
        await self._send_one_prepared(
            f,
            kwargs,
            destination=dest_entity,
            allow_document_fallback=False,
        )
        return True

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
        # Include all staged media at/below anchor (user uploads and bot re-posts in album batch UI).
        async for msg in self.client.iter_messages(entity, limit=scan_limit):
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

    async def save_to_saved_only(self, data: bytes, media_type: str, caption: str | None = None) -> int | None:
        """Save to Saved Messages only (no pool, no Media record). Returns Telegram message id."""
        msg = await self._send_bytes_to_me(data, media_type, caption=caption)
        try:
            return int(msg.id) if msg is not None else None
        except (TypeError, ValueError, AttributeError):
            return None

    async def store_from_message(
        self,
        message,
        source: str,
        pool_id: int,
        db: Session,
        *,
        forward_only: bool | None = None,
        apply_watermark: bool = False,
        prefer_local_pool: bool | None = None,
    ):
        """
        Index channel media into a pool.

        When TBCC_POOL_IMPORT_LOCAL=1 (default), download bytes to disk — no Saved Messages copy.
        Legacy path forwards to Saved Messages for telegram_message_id indexing.

        When apply_watermark is True, always download and re-upload with promo burn-in (no forward).
        """
        from app.services.scrape_channel_intel import is_forward_restricted_error, scraper_forward_only

        if not message.media:
            return None

        use_local = prefer_local_pool
        if use_local is None:
            from app.services.local_media_storage import pool_import_local_enabled

            use_local = pool_import_local_enabled()

        if use_local and not apply_watermark:
            try:
                data = await self.client.download_media(message, bytes)
            except Exception as e:
                logger.warning("download_media failed (local pool import): %s", e)
                return None
            if not data:
                logger.warning("download_media returned empty bytes (local pool import)")
                return None
            kind, _ext = sniff_media_kind(data)
            hint = (
                "photo"
                if kind == "photo"
                else "video"
                if kind == "video"
                else "document"
            )
            from app.services.local_media_storage import store_pool_media_from_bytes

            rec = store_pool_media_from_bytes(
                data, hint, source, pool_id, db, skip_watermark=True
            )
            if rec is not None:
                try:
                    cap = getattr(message, "message", None) or getattr(message, "text", None) or ""
                    _post_media_ingest(
                        db,
                        rec,
                        caption=str(cap),
                        message=message,
                        source_label=source,
                    )
                except Exception:
                    logger.debug("post_media_ingest skipped media_id=%s", rec.id, exc_info=True)
            return rec

        if apply_watermark:
            try:
                data = await self.client.download_media(message, bytes)
            except Exception as e2:
                logger.warning("download_media failed (watermark import): %s", e2)
                return None
            if not data:
                logger.warning("download_media returned empty bytes (watermark import)")
                return None
            kind, _ext = sniff_media_kind(data)
            hint = (
                "photo"
                if kind == "photo"
                else "video"
                if kind == "video"
                else "document"
            )
            return await self.store_from_bytes(data, hint, source, pool_id, db, skip_watermark=False)
        use_forward_only = scraper_forward_only() if forward_only is None else bool(forward_only)
        try:
            msg = await self.client.forward_messages("me", message)
            return await self._index_message(msg, source, pool_id, db)
        except Exception as e:
            if use_forward_only:
                if is_forward_restricted_error(e):
                    raise ForwardRestrictedStorageError(str(e)) from e
                logger.warning(
                    "forward_messages failed (%s): %s — forward_only; skipping message",
                    type(e).__name__,
                    e,
                )
                return None
            logger.warning(
                "forward_messages to Saved Messages failed (%s): %s — trying download_media",
                type(e).__name__,
                e,
            )
        if use_forward_only:
            return None
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
        return await self.store_from_bytes(data, hint, source, pool_id, db, skip_watermark=True)

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

    async def _index_channel_message(
        self,
        message,
        *,
        chat_identifier: str,
        source_label: str,
        pool_id: int,
        db: Session,
        skip_thumb: bool = False,
    ):
        """Fast pool index: reference in-chat Storage Hub message (lazy full download on preview)."""
        if self.is_duplicate_message(message, pool_id, db):
            return None
        media = message.media
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
            return None

        record = Media(
            telegram_message_id=int(message.id),
            file_id=file_id,
            file_unique_id=file_unique_id,
            media_type=media_type,
            source_channel=(
                str(source_label).strip()[:512]
                if "#topic:" in str(source_label or "").lower()
                else str(chat_identifier).strip()[:512]
            ),
            pool_id=pool_id,
            status="pending",
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        if not skip_thumb:
            try:
                from app.services.thumb_cache_service import cache_thumb_from_message

                await cache_thumb_from_message(self.client, message, int(record.id))
            except Exception:
                logger.debug("ingest thumb cache failed media_id=%s", record.id, exc_info=True)
        try:
            cap = getattr(message, "message", None) or getattr(message, "text", None) or ""
            _post_media_ingest(
                db,
                record,
                caption=str(cap),
                message=message,
                source_label=source_label,
            )
        except Exception:
            logger.debug("post_media_ingest skipped media_id=%s", record.id, exc_info=True)
        return record

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
            from app.services.thumb_cache_service import cache_thumb_from_message

            await cache_thumb_from_message(self.client, msg, int(record.id))
        except Exception:
            logger.debug("ingest thumb cache failed media_id=%s", getattr(record, "id", "?"), exc_info=True)
        try:
            from app.services.media_tagging import apply_auto_tags_for_new_media

            apply_auto_tags_for_new_media(db, record.id)
            cap = getattr(msg, "message", None) or getattr(msg, "text", None) or ""
            _post_media_ingest(
                db,
                record,
                caption=str(cap),
                message=msg,
                source_label=source,
            )
            from app.services.auto_tag_enrich import enqueue_auto_tag_enrich_if_enabled
            from app.services.auto_tag_enrich import enrich_pipeline_enabled
            from app.services.auto_tag_llm import enqueue_auto_tag_llm_if_enabled

            if not enrich_pipeline_enabled():
                enqueue_auto_tag_llm_if_enabled(record.id)
        except Exception:
            logger.exception("auto-tag failed for media id=%s", getattr(record, "id", "?"))
        return record

    async def _download_message_media_bytes(self, message, *, label: str = "message") -> bytes:
        """Download full media bytes with one refresh/retry (file refs in bot DMs can go stale)."""
        last_err: BaseException | None = None
        msg = message
        for attempt in range(2):
            try:
                data = await self.client.download_media(msg, bytes)
                if data:
                    return data
                last_err = ValueError(f"{label} {getattr(msg, 'id', '?')} returned empty bytes")
            except Exception as e:
                last_err = e
            if attempt == 0:
                try:
                    peer = getattr(msg, "peer_id", None) or getattr(msg, "chat_id", None)
                    mid = getattr(msg, "id", None)
                    if peer is not None and mid is not None:
                        fresh = await self.client.get_messages(peer, ids=mid)
                        if fresh and not isinstance(fresh, list):
                            msg = fresh
                        elif isinstance(fresh, list) and fresh:
                            msg = fresh[0]
                except Exception as e:
                    last_err = e
                await asyncio.sleep(0.35)
        detail = str(last_err).strip() if last_err else "empty file bytes"
        raise ValueError(f"Telegram download failed for {label} {getattr(message, 'id', '?')}: {detail}")

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
            data = await self._download_message_media_bytes(msg, label="album-bot message")
            bucket = self._message_media_bucket(msg)
            hint = "video" if bucket == "video" else "photo"
            out.append((data, hint))
        if len(out) < media_count:
            raise ValueError(
                f"Downloaded {len(out)}/{media_count} media item(s) from album bot chat. "
                "Re-send the batch to the bot, then post again."
            )
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
        *,
        apply_watermark: bool = False,
        index_only: bool = False,
        message_ids: list[int] | None = None,
    ) -> dict[str, int]:
        """
        Pull channel/group media into a pool (local disk by default when TBCC_POOL_IMPORT_LOCAL=1).
        Requires the Telethon account (admin session) to be able to read the chat.
        When message_thread_id is set, only messages from that forum topic are imported.

        `limit` = max NEW items to store (deduped). Scans newest-first, skipping items
        already in the pool, until `limit` fresh rows are indexed or the scan cap is hit.
        """
        from app.utils.telegram_peer import resolve_telethon_entity

        target_stored = max(1, int(limit))
        max_scan = _channel_import_max_scan(target_stored)
        stored = 0
        skipped_duplicate = 0
        skipped_media_type = 0
        skipped_no_media = 0
        scanned = 0
        stored_messages: list[dict[str, int]] = []
        entity = await resolve_telethon_entity(self.client, channel_identifier)
        iter_kw: dict = {}
        if message_thread_id is not None:
            iter_kw["reply_to"] = int(message_thread_id)

        async def _store_one(message) -> None:
            nonlocal stored, skipped_duplicate, skipped_media_type, skipped_no_media, scanned
            scanned += 1
            kind = _channel_message_media_kind(message)
            if not kind:
                skipped_no_media += 1
                return
            if not _channel_accepts_media_kind(kind, media_types):
                skipped_media_type += 1
                return
            if self.is_duplicate_message(message, pool_id, db):
                skipped_duplicate += 1
                await asyncio.sleep(0.02 if index_only else 0.05)
                return
            try:
                if index_only and not apply_watermark:
                    from app.services.storage_sent_cache import storage_sent_cache_enabled

                    rec = await self._index_channel_message(
                        message,
                        chat_identifier=channel_identifier,
                        source_label=source_label,
                        pool_id=pool_id,
                        db=db,
                        skip_thumb=storage_sent_cache_enabled(),
                    )
                else:
                    rec = await self.store_from_message(
                        message, source_label, pool_id, db, apply_watermark=apply_watermark
                    )
                if rec is not None:
                    stored += 1
                    stored_messages.append(
                        {"message_id": int(message.id), "media_id": int(rec.id)}
                    )
                else:
                    skipped_duplicate += 1
            except Exception:
                logger.exception(
                    "import_from_telegram_channel store failed pool_id=%s msg_id=%s",
                    pool_id,
                    getattr(message, "id", "?"),
                )
            await asyncio.sleep(0.05 if index_only else 0.35)

        explicit_ids = [int(x) for x in (message_ids or []) if int(x) > 0][:200]
        if explicit_ids:
            from app.services.storage_topic_deposit import forum_message_thread_id_from_telethon

            target_stored = len(explicit_ids)
            for mid in explicit_ids:
                if stored >= target_stored:
                    break
                messages = await self.client.get_messages(entity, ids=int(mid))
                msg = messages if not isinstance(messages, list) else (messages[0] if messages else None)
                if not msg:
                    skipped_no_media += 1
                    continue
                if message_thread_id is not None:
                    top = forum_message_thread_id_from_telethon(msg)
                    if top is not None and int(top) != int(message_thread_id):
                        skipped_media_type += 1
                        continue
                await _store_one(msg)
        else:
            async for message in self.client.iter_messages(entity, **iter_kw):
                scanned += 1
                if scanned > max_scan:
                    break
                kind = _channel_message_media_kind(message)
                if not kind:
                    skipped_no_media += 1
                    continue
                if not _channel_accepts_media_kind(kind, media_types):
                    skipped_media_type += 1
                    continue
                if self.is_duplicate_message(message, pool_id, db):
                    skipped_duplicate += 1
                    await asyncio.sleep(0.02 if index_only else 0.05)
                    continue
                try:
                    if index_only and not apply_watermark:
                        from app.services.storage_sent_cache import storage_sent_cache_enabled

                        rec = await self._index_channel_message(
                            message,
                            chat_identifier=channel_identifier,
                            source_label=source_label,
                            pool_id=pool_id,
                            db=db,
                            skip_thumb=storage_sent_cache_enabled(),
                        )
                    else:
                        rec = await self.store_from_message(
                            message, source_label, pool_id, db, apply_watermark=apply_watermark
                        )
                    if rec is not None:
                        stored += 1
                        stored_messages.append(
                            {"message_id": int(message.id), "media_id": int(rec.id)}
                        )
                    else:
                        skipped_duplicate += 1
                except Exception:
                    logger.exception(
                        "import_from_telegram_channel store failed pool_id=%s msg_id=%s",
                        pool_id,
                        getattr(message, "id", "?"),
                    )
                await asyncio.sleep(0.05 if index_only else 0.35)
                if stored >= target_stored:
                    break
        return {
            "stored": stored,
            "skipped_duplicate": skipped_duplicate,
            "skipped_media_type": skipped_media_type,
            "skipped_no_media": skipped_no_media,
            "messages_scanned": scanned,
            "message_thread_id": message_thread_id,
            "target_stored": target_stored,
            "scan_cap_reached": scanned >= max_scan and stored < target_stored,
            "stored_messages": stored_messages,
        }

    async def forward_channel_to_forum_topic(
        self,
        source_channel: str,
        dest_channel: str,
        message_thread_id: int,
        *,
        limit: int = 80,
        media_types: str = "both",
    ) -> dict[str, int]:
        """
        Scrape recent media from source_channel and forward (or re-upload) into a forum subtopic.
        Admin session must read the source and post in the destination group/topic.
        """
        from app.services.scrape_channel_intel import is_forward_restricted_error
        from app.utils.telegram_peer import resolve_telethon_entity

        forwarded = 0
        uploaded = 0
        skipped_media_type = 0
        skipped_no_media = 0
        skipped_forward_restricted = 0
        skipped_already_mirrored = 0
        errors = 0
        scanned = 0
        source_entity = await resolve_telethon_entity(self.client, source_channel)
        dest_entity = await resolve_telethon_entity(self.client, dest_channel)
        topic_id = int(message_thread_id)
        lim = max(1, min(int(limit), 500))
        from telethon.utils import get_peer_id

        from app.services.scrape_hub_forward_dedupe import (
            is_hub_forward_duplicate,
            mark_hub_forward_done,
        )

        source_chat_id = int(get_peer_id(source_entity))

        async for message in self.client.iter_messages(source_entity, limit=lim):
            scanned += 1
            kind = _channel_message_media_kind(message)
            if not kind:
                skipped_no_media += 1
                continue
            if not _channel_accepts_media_kind(kind, media_types):
                skipped_media_type += 1
                continue
            msg_id = int(getattr(message, "id", 0) or 0)
            if msg_id and is_hub_forward_duplicate(topic_id, source_chat_id, msg_id):
                skipped_already_mirrored += 1
                continue
            try:
                await self.client.forward_messages(
                    dest_entity,
                    message,
                    from_peer=source_entity,
                    reply_to=topic_id,
                )
                forwarded += 1
                if msg_id:
                    mark_hub_forward_done(topic_id, source_chat_id, msg_id)
            except Exception as e:
                if is_forward_restricted_error(e):
                    skipped_forward_restricted += 1
                    continue
                try:
                    data = await self.client.download_media(message, bytes)
                    if not data:
                        errors += 1
                        continue
                    f, kwargs, _bucket = self._prepare_file_for_send(data, kind)
                    kwargs = {**kwargs, "reply_to": topic_id}
                    await self.client.send_file(dest_entity, f, **kwargs)
                    uploaded += 1
                    if msg_id:
                        mark_hub_forward_done(topic_id, source_chat_id, msg_id)
                except Exception:
                    logger.exception(
                        "forward_channel_to_forum_topic failed msg_id=%s",
                        getattr(message, "id", "?"),
                    )
                    errors += 1
            await asyncio.sleep(0.45)

        return {
            "forwarded": forwarded,
            "uploaded": uploaded,
            "skipped_forward_restricted": skipped_forward_restricted,
            "skipped_media_type": skipped_media_type,
            "skipped_no_media": skipped_no_media,
            "skipped_already_mirrored": skipped_already_mirrored,
            "errors": errors,
            "messages_scanned": scanned,
            "source_channel": str(source_channel),
            "dest_channel": str(dest_channel),
            "message_thread_id": topic_id,
        }

    async def forward_storage_topic_to_main_topic(
        self,
        source_channel: str,
        source_thread_id: int,
        dest_channel: str,
        dest_thread_id: int,
        *,
        limit: int = 10,
        media_types: str = "both",
        is_already_mirrored=None,
        on_mirrored=None,
        send_silent: bool | None = None,
    ) -> dict[str, int]:
        """
        Forward media from a Storage Hub forum topic into a matching main-group topic.
        Skips messages already mirrored (Redis callback). Sends in albums (≤10) when possible.
        """
        from app.services.scrape_channel_intel import is_forward_restricted_error
        from app.utils.telegram_peer import resolve_telethon_entity

        if send_silent is None:
            send_silent = (os.getenv("TBCC_TOPIC_MIRROR_SILENT") or "1").strip().lower() not in (
                "0",
                "false",
                "no",
                "off",
            )
        silent_kw = {"silent": True} if send_silent else {}

        forwarded = 0
        uploaded = 0
        albums_sent = 0
        skipped_media_type = 0
        skipped_no_media = 0
        skipped_forward_restricted = 0
        skipped_already_mirrored = 0
        errors = 0
        scanned = 0
        source_entity = await resolve_telethon_entity(self.client, source_channel)
        dest_entity = await resolve_telethon_entity(self.client, dest_channel)
        src_thread = int(source_thread_id)
        dest_thread = int(dest_thread_id)
        target_forwards = max(1, min(int(limit), 80))
        max_scan = max(target_forwards * 40, 200)
        max_scan = min(max_scan, 2000)

        candidates: list = []
        async for message in self.client.iter_messages(
            source_entity, limit=max_scan, reply_to=src_thread
        ):
            scanned += 1
            if len(candidates) >= target_forwards:
                break
            msg_id = int(getattr(message, "id", 0) or 0)
            if msg_id and is_already_mirrored and is_already_mirrored(src_thread, msg_id):
                skipped_already_mirrored += 1
                continue
            kind = _channel_message_media_kind(message)
            if not kind:
                skipped_no_media += 1
                continue
            if not _channel_accepts_media_kind(kind, media_types):
                skipped_media_type += 1
                continue
            candidates.append(message)

        for batch in batch_messages_for_album_mirror(candidates, require_full_albums=True):
            if forwarded + uploaded >= target_forwards:
                break
            batch = batch[: max(0, target_forwards - (forwarded + uploaded))]
            if not batch:
                break
            try:
                await self.client.forward_messages(
                    dest_entity,
                    batch,
                    from_peer=source_entity,
                    reply_to=dest_thread,
                    **silent_kw,
                )
                forwarded += len(batch)
                albums_sent += 1
                for message in batch:
                    msg_id = int(getattr(message, "id", 0) or 0)
                    if msg_id and on_mirrored:
                        on_mirrored(src_thread, msg_id)
            except Exception:
                for message in batch:
                    if forwarded + uploaded >= target_forwards:
                        break
                    msg_id = int(getattr(message, "id", 0) or 0)
                    try:
                        await self.client.forward_messages(
                            dest_entity,
                            message,
                            from_peer=source_entity,
                            reply_to=dest_thread,
                            **silent_kw,
                        )
                        forwarded += 1
                        if msg_id and on_mirrored:
                            on_mirrored(src_thread, msg_id)
                    except Exception as e2:
                        if is_forward_restricted_error(e2):
                            skipped_forward_restricted += 1
                            continue
                        try:
                            if await self._upload_mirror_media(
                                dest_entity,
                                message,
                                dest_thread=dest_thread,
                                silent_kw=silent_kw,
                            ):
                                uploaded += 1
                                if msg_id and on_mirrored:
                                    on_mirrored(src_thread, msg_id)
                            else:
                                errors += 1
                        except Exception:
                            logger.exception(
                                "forward_storage_topic_to_main_topic failed msg_id=%s",
                                msg_id,
                            )
                            errors += 1
            await asyncio.sleep(0.45)

        return {
            "forwarded": forwarded,
            "uploaded": uploaded,
            "albums_sent": albums_sent,
            "skipped_forward_restricted": skipped_forward_restricted,
            "skipped_media_type": skipped_media_type,
            "skipped_no_media": skipped_no_media,
            "skipped_already_mirrored": skipped_already_mirrored,
            "errors": errors,
            "messages_scanned": scanned,
            "source_channel": str(source_channel),
            "source_thread_id": src_thread,
            "dest_channel": str(dest_channel),
            "dest_thread_id": dest_thread,
            "send_silent": bool(send_silent),
        }
