import logging
import random
from collections import defaultdict

from telethon import TelegramClient
from app.models.media import Media
from sqlalchemy.orm import Session

from app.services.telegram_album_plan import (
    GALLERY_SEND_PROMO_SOURCE,
    TELEGRAM_ALBUM_MAX,
    chunk_sequence_with_promo_tail,
)

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
    send_silent: bool = False,
    reply_markup=None,
) -> list[int]:
    """
    Posts a Telegram album using media from Saved Messages (by telegram_message_id).
    Fetches messages from "me" and sends their media — no re-upload.
    Telegram requires all items in an album to be the same type (photos with photos, etc).
    reply_to: forum topic id (same as Bot API message_thread_id) for supergroups with topics.
    Returns Telegram message ids for the send (empty list on skip/failure).
    """
    if not media_items:
        return []
    from app.services.content_performance import message_ids_from_send
    from app.services.local_media_storage import is_local_pool_media, telethon_file_from_media

    saved_ids = [m.telegram_message_id for m in media_items if not is_local_pool_media(m)]
    msg_map: dict = {}
    if saved_ids:
        messages = await client.get_messages("me", ids=saved_ids)
        msg_map = {m.id: m for m in messages if m}
    medias = []
    for m in media_items:
        if is_local_pool_media(m):
            f = telethon_file_from_media(m)
            if f is not None:
                medias.append(f)
            continue
        msg = msg_map.get(m.telegram_message_id)
        if msg and msg.media:
            medias.append(msg.media)
    if len(medias) != len(media_items):
        logger.warning("Could not fetch all media; skipping album to avoid partial send")
        return []
    cap = caption.strip() if caption else None
    silent_kw = {"silent": True} if send_silent else {}
    from app.services.scheduled_post_service import _apply_telethon_html_to_kwargs

    file_kw: dict = {"reply_to": reply_to, **silent_kw}
    if reply_markup is not None:
        file_kw["buttons"] = reply_markup
    _apply_telethon_html_to_kwargs(file_kw, cap or "", field="caption")
    try:
        result = await client.send_file(channel, medias, **file_kw)
        return message_ids_from_send(result)
    except Exception as e:
        # Telegram sometimes rejects SendMultiMediaRequest (invalid mix, API quirks, forum edge cases).
        # Fall back to one message per item so valid items still post.
        logger.warning(
            "Album send failed (%s); sending items individually: %s",
            type(e).__name__,
            e,
        )
        msg_ids: list[int] = []
        for idx, single in enumerate(medias):
            kw: dict = {"reply_to": reply_to, **silent_kw}
            if idx == 0:
                if reply_markup is not None:
                    kw["buttons"] = reply_markup
                _apply_telethon_html_to_kwargs(kw, cap or "", field="caption")
            single_result = await client.send_file(channel, single, **kw)
            msg_ids.extend(message_ids_from_send(single_result))
        return msg_ids


async def post_pool_albums(
    client: TelegramClient,
    channel_identifier: str,
    pool_id: int,
    db: Session,
    album_size: int = 5,
    randomize: bool = False,
    *,
    mark_posted: bool = True,
) -> dict:
    from app.services.media_album_dedupe import dedupe_media_for_album

    approved = (
        db.query(Media)
        .filter(Media.pool_id == pool_id, Media.status == "approved")
        .order_by(Media.id.asc())
        .limit(500)
        .all()
    )
    try:
        from app.services.export_flywheel_service import rank_pool_media, rank_picks_enabled

        if rank_picks_enabled():
            ranked = rank_pool_media(db, pool_id, album_size, randomize=randomize)
            if ranked:
                approved = ranked + [m for m in approved if m.id not in {x.id for x in ranked}]
    except Exception:
        logger.debug("export flywheel rank skipped", exc_info=True)
    approved = dedupe_media_for_album(approved)
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
        return {"ok": False, "reason": "no_full_album", "media_ids": [], "telegram_message_ids": []}

    msg_ids = await post_album(client, channel_identifier, selected_album)
    if mark_posted:
        for m in selected_album:
            m.status = "posted"
        db.commit()
    return {
        "ok": bool(msg_ids),
        "media_ids": [int(m.id) for m in selected_album],
        "telegram_message_ids": msg_ids,
    }


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
    send_silent: bool = False,
    buttons: list[dict] | None = None,
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
    cap = caption.strip() if caption and caption.strip() else ""
    from app.services.scheduled_post_service import _build_reply_markup

    reply_markup = _build_reply_markup(buttons or [])
    buttons_attached = False

    promo_row: Media | None = None
    if rows and str(rows[-1].source or "").strip() == GALLERY_SEND_PROMO_SOURCE:
        promo_row = rows[-1]
        rows = rows[:-1]
        by_type = defaultdict(list)
        for m in rows:
            by_type[_media_type_bucket(m)].append(m)

    if not rows and promo_row:
        try:
            chunk_markup = reply_markup if not buttons_attached else None
            await post_album(
                client,
                channel_identifier,
                [promo_row],
                caption=cap,
                reply_to=message_thread_id,
                send_silent=send_silent,
                reply_markup=chunk_markup,
            )
            buttons_attached = buttons_attached or chunk_markup is not None
            sent += 1
            if mark_posted:
                promo_row.status = "posted"
                db.commit()
        except Exception as e:
            logger.exception("post_media_ids_to_forum_topic promo-only failed")
            errs.append(str(e))
            db.rollback()
        return {"ok": not errs, "sent_chunks": sent, "errors": errs}

    promo_bucket = _media_type_bucket(promo_row) if promo_row else None

    for _t, items in by_type.items():
        attach_promo = promo_row is not None and promo_bucket == _t
        if attach_promo:
            album_chunks = chunk_sequence_with_promo_tail(items, promo_row, TELEGRAM_ALBUM_MAX)
        else:
            album_chunks = [items[i : i + TELEGRAM_ALBUM_MAX] for i in range(0, len(items), TELEGRAM_ALBUM_MAX)]
        for chunk in album_chunks:
            try:
                chunk_markup = reply_markup if not buttons_attached else None
                await post_album(
                    client,
                    channel_identifier,
                    chunk,
                    caption=cap,
                    reply_to=message_thread_id,
                    send_silent=send_silent,
                    reply_markup=chunk_markup,
                )
                buttons_attached = buttons_attached or chunk_markup is not None
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


async def post_bot_messages_to_forum_topic(
    client: TelegramClient,
    bot_peer: str | int,
    channel_identifier: str,
    media_count: int,
    message_thread_id: int | None,
    caption: str = "",
    send_silent: bool = False,
    reply_markup=None,
    promo_item: tuple[bytes, str] | None = None,
    *,
    message_ids: list[int] | None = None,
    anchor_max_message_id: int | None = None,
    post_client: TelegramClient | None = None,
) -> dict:
    """
    Post media from the admin's DM with the album bot directly to a channel/topic.
    Uses Telethon message references (no Bot API download or pool import).

    ``post_client`` — Telethon client used for the destination (poster session).
    ``client`` — reads staged media from the album-composer DM (admin_album session).
    """
    from app.services.scheduled_post_service import _apply_telethon_html_to_kwargs
    from app.services.telegram_storage import TelegramStorage

    if media_count < 1:
        return {"ok": False, "error": "No media", "sent_chunks": 0}

    fetch_storage = TelegramStorage(client)
    post_storage = TelegramStorage(post_client or client)
    try:
        ordered = await fetch_storage._fetch_bot_media_for_batch(
            bot_peer,
            media_count,
            message_ids=message_ids,
            anchor_max_message_id=anchor_max_message_id,
        )
    except ValueError as e:
        return {"ok": False, "error": str(e), "sent_chunks": 0}

    cap = caption.strip() if caption and caption.strip() else ""
    silent_kw = {"silent": True} if send_silent else {}
    base_send_kw: dict = {"reply_to": message_thread_id, **silent_kw}
    if reply_markup is not None:
        base_send_kw["buttons"] = reply_markup
    _apply_telethon_html_to_kwargs(base_send_kw, cap or "", field="caption")

    promo_prepared = None
    promo_bucket = None
    if promo_item and promo_item[0]:
        promo_prepared = post_storage._prepare_file_for_send(promo_item[0], promo_item[1], skip_watermark=True)
        promo_bucket = promo_prepared[2]

    if not ordered and promo_prepared:
        await post_storage._send_album_chunk_refs(
            [promo_prepared], caption=cap or None, destination=channel_identifier, send_kwargs=base_send_kw
        )
        return {"ok": True, "sent_chunks": 1, "errors": []}

    runs = fetch_storage._runs_contiguous_message_buckets(ordered)
    promo_run_idx: int | None = None
    if promo_prepared and promo_bucket:
        for idx in range(len(runs) - 1, -1, -1):
            if runs[idx] and fetch_storage._message_media_bucket(runs[idx][0]) == promo_bucket:
                promo_run_idx = idx
                break

    chunk_total = 0
    for run_idx, run in enumerate(runs):
        if promo_prepared is not None and run_idx == promo_run_idx:
            chunk_total += len(chunk_sequence_with_promo_tail(run, promo_prepared, TELEGRAM_ALBUM_MAX))
        else:
            chunk_total += (len(run) + TELEGRAM_ALBUM_MAX - 1) // TELEGRAM_ALBUM_MAX

    try:
        await post_storage._dispatch_message_runs(
            runs,
            destination=channel_identifier,
            caption=cap or None,
            promo_prepared=promo_prepared,
            promo_bucket=promo_bucket,
            promo_run_idx=promo_run_idx,
            base_send_kw=base_send_kw,
            parallel_chunks=True,
        )
        return {"ok": True, "sent_chunks": chunk_total, "errors": []}
    except Exception as e:
        logger.exception("post_bot_messages_to_forum_topic failed")
        return {"ok": False, "error": str(e), "sent_chunks": 0, "errors": [str(e)]}
