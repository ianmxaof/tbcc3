"""Send scheduled posts (text, media, buttons) to Telegram channels."""
import io
import logging
import random
from collections import defaultdict

from telethon import TelegramClient
from telethon.tl.types import (
    MessageMediaDocument,
    ReplyInlineMarkup,
    KeyboardButtonRow,
    KeyboardButtonUrl,
    DocumentAttributeImageSize,
    DocumentAttributeFilename,
)
from sqlalchemy.orm import Session

from app.models.media import Media
from app.models.scheduled_text_post import ScheduledTextPost
from app.models.content_pool import ContentPool

logger = logging.getLogger(__name__)


def _is_image_data(data: bytes) -> bool:
    """Check if bytes look like image data (magic bytes)."""
    if len(data) < 12:
        return False
    if data[:3] == b"\xff\xd8\xff":
        return True
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return True
    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WEBP":
        return True
    return False


def _detect_image_ext(data: bytes) -> str:
    """Detect image format from magic bytes. Defaults to jpg."""
    if len(data) < 12:
        return "jpg"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "jpg"


def _is_image_document(media) -> bool:
    """Check if MessageMediaDocument is an image (should display as photo, not file)."""
    if not isinstance(media, MessageMediaDocument):
        return False
    mime = (media.document.mime_type or "").lower()
    if "image" in mime or mime in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        return True
    for attr in getattr(media.document, "attributes", []) or []:
        if isinstance(attr, DocumentAttributeImageSize):
            return True
    # Check filename extension
    for attr in getattr(media.document, "attributes", []) or []:
        if isinstance(attr, DocumentAttributeFilename):
            fn = (getattr(attr, "file_name", "") or "").lower()
            if fn.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
                return True
    return False


def _build_reply_markup(buttons_data: list):
    """Build ReplyInlineMarkup from [{text,url},...] or [[{text,url},...],...]. Returns None if no valid buttons."""
    if not buttons_data:
        return None
    rows = []
    for row in buttons_data:
        if isinstance(row, dict):
            row = [row]
        btns = []
        for btn in row if isinstance(row, list) else [row]:
            if isinstance(btn, dict):
                text = str(btn.get("text", "")).strip()
                url = str(btn.get("url", "")).strip()
                if text and url and url.startswith(("http://", "https://")):
                    btns.append(KeyboardButtonUrl(text=text, url=url))
        if btns:
            rows.append(KeyboardButtonRow(buttons=btns))
    if not rows:
        return None
    return ReplyInlineMarkup(rows=rows)


def resolve_scheduled_caption(post: ScheduledTextPost) -> str:
    """Caption for this send: rotates when content_variations has 2+ strings (1→2→1…)."""
    variations = post.get_content_variations()
    n = len(variations)
    if n >= 2:
        idx = (post.caption_rotation_index or 0) % n
        caption = variations[idx]
        post.caption_rotation_index = (idx + 1) % n
        return caption
    if n == 1:
        return variations[0]
    return post.content or ""


async def send_scheduled_post(
    client: TelegramClient,
    channel_identifier: str,
    post: ScheduledTextPost,
    db: Session,
) -> None:
    """Send a scheduled post (text, optional media, optional buttons)."""
    caption = resolve_scheduled_caption(post)
    reply_markup = _build_reply_markup(post.get_buttons())
    # Supergroups with topics: same as Bot API message_thread_id (extension gallery uses this too).
    reply_to = post.message_thread_id if getattr(post, "message_thread_id", None) else None

    # Gather media: explicit media_ids first, then pool
    media_items: list[Media] = []
    media_ids = post.get_media_ids()
    if media_ids:
        for mid in media_ids:
            m = db.query(Media).filter(Media.id == mid).first()
            if m:
                media_items.append(m)
    if post.pool_id and not media_items:
        pool = db.query(ContentPool).filter(ContentPool.id == post.pool_id).first()
        default_album = min(10, max(1, int(pool.album_size) if pool and pool.album_size else 5))
        album_size = (
            min(10, max(1, int(post.album_size)))
            if post.album_size is not None
            else default_album
        )
        if post.pool_randomize is not None:
            randomize = bool(post.pool_randomize)
        else:
            randomize = bool(pool and getattr(pool, "randomize_queue", False))
        q = db.query(Media).filter(Media.pool_id == post.pool_id, Media.status == "approved")
        if randomize:
            rows = q.all()
            random.shuffle(rows)
            media_items = rows[:album_size]
        else:
            media_items = q.order_by(Media.id.asc()).limit(album_size).all()

    if media_items:
        by_type = defaultdict(list)
        for m in media_items:
            t = (m.media_type or "document").lower()
            if t not in ("photo", "video", "document", "gif"):
                t = "document"
            by_type[t].append(m)
        first_type = (media_items[0].media_type or "document").lower()
        if first_type not in ("photo", "video", "document", "gif"):
            first_type = "document"
        items = by_type.get(first_type, media_items[:1])
        msg_ids = [m.telegram_message_id for m in items]
        messages = await client.get_messages("me", ids=msg_ids)
        msg_map = {m.id: m for m in messages if m}
        raw_medias = []
        for m in items:
            msg = msg_map.get(m.telegram_message_id)
            if msg and msg.media:
                raw_medias.append(msg.media)
        if raw_medias:
            # Documents that are images display as "unnamed" - download and re-upload as photo when confirmed
            send_medias = []
            for i, raw in enumerate(raw_medias):
                db_media = items[i]
                # MessageMediaPhoto: use as-is
                if not isinstance(raw, MessageMediaDocument):
                    send_medias.append(raw)
                    continue
                # MessageMediaDocument: check if likely image, then verify with magic bytes
                maybe_image = (
                    (db_media.media_type or "").lower() == "photo"
                    or _is_image_document(raw)
                )
                size = getattr(getattr(raw, "document", None), "size", 0) or 0
                if maybe_image or (size > 0 and size < 15 * 1024 * 1024):
                    data = await client.download_media(raw, bytes)
                    if data and _is_image_data(data):
                        ext = _detect_image_ext(data)
                        f = io.BytesIO(data)
                        f.name = f"image.{ext}"
                        send_medias.append(f)
                        logger.info("Re-uploading as photo: media_id=%s size=%s", db_media.id, len(data))
                    else:
                        send_medias.append(raw)
                else:
                    send_medias.append(raw)
            # Single file: use InputMediaUploadedPhoto when re-uploaded BytesIO (guaranteed photo)
            if len(send_medias) == 1 and isinstance(send_medias[0], io.BytesIO):
                # Explicit photo upload — use send_file so forum reply_to matches album_service / extension
                f = send_medias[0]
                f.seek(0)
                uploaded = await client.upload_file(f)
                await client.send_file(
                    channel_identifier,
                    uploaded,
                    caption=caption or None,
                    buttons=reply_markup,
                    reply_to=reply_to,
                    force_document=False,
                )
            elif len(send_medias) == 1:
                await client.send_file(
                    channel_identifier,
                    send_medias[0],
                    caption=caption or None,
                    buttons=reply_markup,
                    reply_to=reply_to,
                    force_document=False,
                )
            else:
                await client.send_file(
                    channel_identifier,
                    send_medias,
                    caption=caption or None,
                    force_document=False,
                    reply_to=reply_to,
                )
        else:
            await client.send_message(
                channel_identifier,
                caption or "(no content)",
                buttons=reply_markup,
                reply_to=reply_to,
            )
    else:
        await client.send_message(
            channel_identifier,
            caption or "(no content)",
            buttons=reply_markup,
            reply_to=reply_to,
        )
