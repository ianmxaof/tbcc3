import logging
import random
from collections import defaultdict

from telethon import TelegramClient
from app.models.media import Media
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def chunk_into_full_albums(media_list: list, size: int = 5) -> list:
    """Return only full-sized chunks (no partial albums). Items not in a full album are skipped."""
    full_count = (len(media_list) // size) * size
    if full_count == 0:
        return []
    return [media_list[i : i + size] for i in range(0, full_count, size)]


async def post_album(
    client: TelegramClient,
    channel,
    media_items: list,
    caption: str = "",
    reply_to: int | None = None,
):
    """
    Posts a Telegram album using media from Saved Messages (by telegram_message_id).
    Fetches messages from "me" and sends their media — no re-upload.
    Telegram requires all items in an album to be the same type (photos with photos, etc).
    reply_to: forum topic id (same as Bot API message_thread_id) for supergroups with topics.
    """
    if not media_items:
        return
    msg_ids = [m.telegram_message_id for m in media_items]
    messages = await client.get_messages("me", ids=msg_ids)
    msg_map = {m.id: m for m in messages if m}
    medias = []
    for m in media_items:
        msg = msg_map.get(m.telegram_message_id)
        if msg and msg.media:
            medias.append(msg.media)
    if len(medias) != len(media_items):
        logger.warning("Could not fetch all media; skipping album to avoid partial send")
        return
    cap = caption.strip() if caption else None
    try:
        await client.send_file(channel, medias, caption=cap, reply_to=reply_to)
    except Exception as e:
        # Telegram sometimes rejects SendMultiMediaRequest (invalid mix, API quirks, forum edge cases).
        # Fall back to one message per item so valid items still post.
        logger.warning(
            "Album send failed (%s); sending items individually: %s",
            type(e).__name__,
            e,
        )
        for idx, single in enumerate(medias):
            c = cap if idx == 0 else None
            await client.send_file(channel, single, caption=c, reply_to=reply_to)


async def post_pool_albums(
    client: TelegramClient,
    channel_identifier: str,
    pool_id: int,
    db: Session,
    album_size: int = 5,
    randomize: bool = False,
):
    approved = (
        db.query(Media)
        .filter(Media.pool_id == pool_id, Media.status == "approved")
        .order_by(Media.id.asc())
        .limit(500)
        .all()
    )
    # Group by media_type so each album has same type (Telegram requirement)
    by_type = defaultdict(list)
    for m in approved:
        t = (m.media_type or "document").lower()
        if t not in ("photo", "video", "document", "gif"):
            t = "document"
        by_type[t].append(m)

    # One invocation should publish at most one album.
    # This keeps "Post now" as a single send and lets interval scheduling pace delivery.
    selected_album = None
    for media_type in sorted(by_type.keys()):
        bucket = list(by_type[media_type])
        if randomize:
            random.shuffle(bucket)
        albums = chunk_into_full_albums(bucket, album_size)
        if albums:
            selected_album = albums[0]
            break

    if not selected_album:
        logger.info(
            "No full album available for pool %s (album_size=%s approved=%s)",
            pool_id,
            album_size,
            len(approved),
        )
        return

    await post_album(client, channel_identifier, selected_album)
    for m in selected_album:
        m.status = "posted"
    db.commit()


def _media_type_bucket(m: Media) -> str:
    t = (m.media_type or "document").lower()
    if t not in ("photo", "video", "document", "gif"):
        return "document"
    return t


async def post_media_ids_to_forum_topic(
    client: TelegramClient,
    channel_identifier: str,
    message_thread_id: int | None,
    media_ids: list[int],
    db: Session,
    caption: str = "",
    mark_posted: bool = True,
) -> dict:
    """
    Post selected DB media as one or more albums (≤10 items each) to a Telegram destination.

    If ``message_thread_id`` is set, posts into that forum topic (supergroups with topics).
    If ``None``, posts to the channel/group main chat (broadcast channels, ordinary groups).

    Preserves the order of media_ids. Splits by media type (Telegram album rule) and chunks by 10.
    The same caption is attached to every album chunk (each send_file multi-media group).
    """
    if not media_ids:
        return {"ok": False, "error": "No media_ids", "sent_chunks": 0}
    rows = db.query(Media).filter(Media.id.in_(media_ids)).all()
    order = {mid: i for i, mid in enumerate(media_ids)}
    rows.sort(key=lambda m: order.get(m.id, 999999))
    if len(rows) != len(media_ids):
        found = {m.id for m in rows}
        missing = [mid for mid in media_ids if mid not in found]
        return {"ok": False, "error": f"Unknown media ids: {missing[:10]}", "sent_chunks": 0}

    by_type: dict[str, list[Media]] = defaultdict(list)
    for m in rows:
        by_type[_media_type_bucket(m)].append(m)

    sent = 0
    errs: list[str] = []
    max_per = 10
    cap = caption.strip() if caption and caption.strip() else ""

    for _t, items in by_type.items():
        for i in range(0, len(items), max_per):
            chunk = items[i : i + max_per]
            try:
                await post_album(
                    client,
                    channel_identifier,
                    chunk,
                    caption=cap,
                    reply_to=message_thread_id,
                )
                sent += 1
                if mark_posted:
                    for mm in chunk:
                        mm.status = "posted"
                    db.commit()
            except Exception as e:
                logger.exception("post_media_ids_to_forum_topic chunk failed")
                errs.append(str(e))
                db.rollback()

    return {"ok": not errs, "sent_chunks": sent, "errors": errs}
