"""Send scheduled posts (text, media, buttons) to Telegram channels."""
import asyncio
import io
import json
import logging
import os
import random
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from telethon import TelegramClient
from telethon.errors.rpcerrorlist import ChatRestrictedError
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
from app.models.channel import Channel
from app.models.subscription_plan import SubscriptionPlan
from app.services.content_performance import ScheduledSendOutcome
from app.services.promo_storage import promo_path_from_public_url
from app.utils.telegram_peer import normalize_telethon_peer_identifier, resolve_poster_peer
from app.services.telegram_custom_emoji import telethon_message_kwargs

logger = logging.getLogger(__name__)


def _apply_telethon_html_to_kwargs(kwargs: dict, html: str | None, *, field: str) -> None:
    """
    Merge telethon_message_kwargs into send_message/send_file kwargs.
    field: 'message' | 'caption'
    """
    empty = "(no content)" if field == "message" else ""
    mk = telethon_message_kwargs(html, empty_fallback=empty)
    text = mk.get("message", "")
    if field == "caption":
        if not text:
            return
        kwargs["caption"] = text
    else:
        kwargs[field] = text or empty
    if mk.get("formatting_entities"):
        kwargs["formatting_entities"] = mk["formatting_entities"]
        kwargs.pop("parse_mode", None)
    elif mk.get("parse_mode"):
        kwargs["parse_mode"] = mk["parse_mode"]


def _log_chat_restricted_help(channel_identifier: str) -> None:
    """Operator hint when Telegram returns ChatRestrictedError (common misconfiguration)."""
    logger.error(
        "ChatRestrictedError posting to %r — Telegram blocked this account from sending media to that chat "
        "(SendMultiMediaRequest). Fix: (1) In Telegram, open the channel/group → Administrators → ensure the account "
        "for this worker's Telethon session (admin_poster.session / TBCC_POSTER_TELEGRAM_SESSION) is an admin with "
        "permission to post messages and send media. (2) For private channels, set the dashboard channel "
        "Identifier to the stable numeric id -100… (not only a t.me/+ invite). (3) If the channel was converted or "
        "the account was demoted, re-add the account as admin.",
        channel_identifier,
    )


@dataclass
class CampaignSendResult:
    sent_post_ids: list[int]
    failed_post_ids: list[int]
    first_error: Exception | None = None
    outcomes: dict[int, ScheduledSendOutcome] = field(default_factory=dict)


def _promo_buffers_from_urls(urls: list[str]) -> list[io.BytesIO]:
    """Load dashboard promo files (/static/promo/…) for Telethon send_file."""
    out: list[io.BytesIO] = []
    for u in urls[:10]:
        p = promo_path_from_public_url(u)
        if not p:
            logger.warning("Promo attachment not on disk (URL=%s)", u)
            continue
        data = p.read_bytes()
        f = io.BytesIO(data)
        f.name = p.name or "image.jpg"
        f.seek(0)
        out.append(f)
    return out


def _peek_caption_slot_index(post: ScheduledTextPost) -> int:
    """Caption/album variant index for this send (before resolve_scheduled_caption advances)."""
    variations = post.get_content_variations()
    n = len(variations)
    if n >= 2:
        return (post.caption_rotation_index or 0) % n
    return 0


def _resolve_variant_sources(post: ScheduledTextPost, slot: int) -> tuple[list[int], list[str], bool]:
    """
    Returns (media_ids, promo_urls, use_pool_if_still_empty).
    When album_variants_json is set (structured mode), empty variant slots do not fall back to legacy
    global media_ids — only the pool.
    """
    structured = False
    if post.album_variants_json:
        try:
            raw = json.loads(post.album_variants_json)
            structured = isinstance(raw, list) and len(raw) > 0
        except (json.JSONDecodeError, TypeError, ValueError):
            structured = False

    variants = post.get_album_variants()
    has_pinned_variants = bool(
        variants and any(v.get("media_ids") or v.get("attachment_urls") for v in variants)
    )
    if bool(getattr(post, "pool_only_mode", False)) and _post_uses_pool(post) and not has_pinned_variants:
        return [], [], True
    if not variants:
        mids = post.get_media_ids()
        promo = post._urls_from_attachment_urls_json_column()
        return mids, promo, True

    k = slot % len(variants)
    v = variants[k]
    mids = list(v.get("media_ids") or [])
    promo = list(v.get("attachment_urls") or [])

    if structured:
        if not mids and not promo:
            return [], [], _post_uses_pool(post)
        return mids, promo, _post_uses_pool(post) and not mids and not promo

    if not mids and not promo:
        mids = post.get_media_ids()
        promo = post._urls_from_attachment_urls_json_column()
        return mids, promo, True
    return mids, promo, _post_uses_pool(post) and not mids and not promo


def _effective_album_order_mode(post: ScheduledTextPost) -> str:
    m = (post.album_order_mode or "static").strip().lower()
    if m in ("shuffle", "carousel"):
        return m
    return "static"


def _album_order_mode_for_send(post: ScheduledTextPost, reshuffle_album: bool) -> str:
    """If reshuffle_album, randomize item order for this send only (overrides static/carousel)."""
    if reshuffle_album:
        return "shuffle"
    return _effective_album_order_mode(post)


def _apply_order_mode_to_sequence(items: list, mode: str, post: ScheduledTextPost) -> list:
    """Reorder Media rows or url strings (shuffle / carousel). Static = unchanged."""
    if len(items) < 2:
        return items
    if mode == "shuffle":
        out = list(items)
        random.shuffle(out)
        return out
    if mode == "carousel":
        L = len(items)
        k = (post.album_carousel_index or 0) % L
        post.album_carousel_index = (post.album_carousel_index or 0) + 1
        return items[k:] + items[:k]
    return items


def _post_uses_pool(post: ScheduledTextPost) -> bool:
    return bool(post.pool_id) or bool(getattr(post, "pool_collective_random", False))


def _pick_collective_pool_id(db: Session) -> int | None:
    """Random pool that has at least one approved media row."""
    rows = (
        db.query(ContentPool.id)
        .join(Media, Media.pool_id == ContentPool.id)
        .filter(Media.status == "approved")
        .distinct()
        .all()
    )
    ids = [int(r[0]) for r in rows]
    if not ids:
        return None
    return random.choice(ids)


def _resolve_effective_pool_id(post: ScheduledTextPost, db: Session) -> int | None:
    if bool(getattr(post, "pool_collective_random", False)):
        from app.services.aof_feed_rhythm_v2 import is_network_tease_scheduler, pick_network_lane_pool_id

        if is_network_tease_scheduler(post):
            pid = pick_network_lane_pool_id(db)
            if pid:
                return pid
        return _pick_collective_pool_id(db)
    return post.pool_id


def _select_pool_media_rows(
    post: ScheduledTextPost,
    db: Session,
    *,
    effective_pool_id: int,
    pool,
    album_size: int,
    randomize: bool,
    skip_exclusive: bool,
) -> list[Media]:
    from app.services.media_album_dedupe import (
        filter_media_older_than_schedule_min_age,
        select_unique_pool_media,
    )
    from app.services.aof_vip_exclusive import filter_media_for_public_vip_exclusive

    def _apply_public_exclusive(rows: list) -> list:
        if skip_exclusive:
            return rows
        return filter_media_for_public_vip_exclusive(rows, pool=pool)

    q = db.query(Media).filter(Media.pool_id == effective_pool_id, Media.status == "approved")
    candidate_cap = min(500, max(album_size * 20, album_size))
    if randomize:
        rows = _apply_public_exclusive(filter_media_older_than_schedule_min_age(q.all()))
        return select_unique_pool_media(rows, album_size, randomize=True)
    try:
        from app.services.export_flywheel_service import rank_pool_media, rank_picks_enabled

        if rank_picks_enabled():
            ranked = rank_pool_media(db, effective_pool_id, candidate_cap, randomize=False)
            if ranked:
                ranked = _apply_public_exclusive(ranked)
                return select_unique_pool_media(ranked, album_size, randomize=False)
    except Exception:
        pass
    rows = _apply_public_exclusive(
        filter_media_older_than_schedule_min_age(
            q.order_by(Media.id.asc()).limit(candidate_cap).all()
        )
    )
    return select_unique_pool_media(rows, album_size, randomize=False)


def _load_pool_media_items(
    post: ScheduledTextPost,
    db: Session,
    album_order_mode: str,
) -> list[Media]:
    from app.services.media_album_dedupe import dedupe_media_for_album

    effective_pool_id = _resolve_effective_pool_id(post, db)
    if not effective_pool_id:
        return []
    pool = db.query(ContentPool).filter(ContentPool.id == effective_pool_id).first()
    default_album = min(10, max(1, int(pool.album_size) if pool and pool.album_size else 5))
    if bool(getattr(post, "pool_collective_random", False)):
        default_album = min(10, max(1, int(post.album_size) if post.album_size is not None else 5))
    album_size = (
        min(10, max(1, int(post.album_size)))
        if post.album_size is not None
        else default_album
    )
    if post.pool_randomize is not None:
        randomize = bool(post.pool_randomize)
    elif bool(getattr(post, "pool_collective_random", False)):
        randomize = True
    else:
        randomize = bool(pool and getattr(pool, "randomize_queue", False))
    from app.models.channel import Channel
    from app.data.aof_network import AOF_VIP_IDENT

    vip_channel = (
        db.query(Channel).filter(Channel.id == int(post.channel_id)).first()
        if post.channel_id
        else None
    )

    skip_exclusive = bool(
        vip_channel and str(getattr(vip_channel, "identifier", "")) == AOF_VIP_IDENT
    )

    items = _select_pool_media_rows(
        post,
        db,
        effective_pool_id=int(effective_pool_id),
        pool=pool,
        album_size=album_size,
        randomize=randomize,
        skip_exclusive=skip_exclusive,
    )
    if not items:
        from app.services.sent_vault_lane_refill import (
            refill_pool_from_sent_vault_on_demand_sync,
            sent_vault_dry_spell_refill_enabled,
        )

        if sent_vault_dry_spell_refill_enabled():
            restored = refill_pool_from_sent_vault_on_demand_sync(
                db, int(effective_pool_id), need=album_size
            )
            if restored > 0:
                items = _select_pool_media_rows(
                    post,
                    db,
                    effective_pool_id=int(effective_pool_id),
                    pool=pool,
                    album_size=album_size,
                    randomize=randomize,
                    skip_exclusive=skip_exclusive,
                )
    return items


def _gather_media_items_for_send(
    post: ScheduledTextPost,
    db: Session,
    variant_mids: list[int],
    use_pool_fallback: bool,
    album_order_mode: str,
) -> list[Media]:
    media_items: list[Media] = []
    for mid_i in variant_mids:
        m = db.query(Media).filter(Media.id == int(mid_i)).first()
        if m:
            media_items.append(m)
    if _post_uses_pool(post) and not media_items and use_pool_fallback:
        media_items = _load_pool_media_items(post, db, album_order_mode)
    from app.services.media_album_dedupe import dedupe_media_for_album

    media_items = dedupe_media_for_album(media_items)
    return _apply_order_mode_to_sequence(media_items, album_order_mode, post)


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


def _is_forward_restricted_send_error(err: BaseException) -> bool:
    """True when Telethon tried to forward/copy media from a noforwards/protected source."""
    msg = str(err).lower()
    return "can't forward" in msg or "cannot forward" in msg or "protected chat" in msg


async def _materialize_pool_media_for_send(client: TelegramClient, raw, db_media: Media):
    """
    Download hub/Saved Messages media so scheduled sends upload bytes instead of forwarding.

    Passing MessageMedia from get_messages() makes SendMediaRequest act like a forward;
    protected/noforwards source chats reject that with ChatForwardsRestrictedError.

    Videos return PreparedSendFile (custom poster thumb) or a skip marker when no usable
    poster can be extracted. Photos/documents remain BytesIO (or raw TL fallback).
    """
    from app.services.video_poster import PreparedSendFile, prepare_video_send_file

    if isinstance(raw, PreparedSendFile):
        return raw
    if isinstance(raw, io.BytesIO):
        raw.seek(0)
        return raw

    data = await client.download_media(raw, bytes)
    if not data:
        logger.warning(
            "scheduled send: download_media empty media_id=%s — falling back to raw TL media",
            getattr(db_media, "id", None),
        )
        return raw

    media_type = (db_media.media_type or "document").lower()
    mid = int(getattr(db_media, "id", 0) or 0) or None
    if media_type == "photo" or _is_image_data(data):
        ext = _detect_image_ext(data)
        f = io.BytesIO(data)
        f.name = f"image.{ext}"
        logger.info(
            "Re-uploading pool media as photo: media_id=%s size=%s",
            mid,
            len(data),
        )
        return f
    if media_type in ("video", "gif"):
        prepared = prepare_video_send_file(data, media_id=mid, filename="video.mp4")
        if prepared.skip:
            logger.warning(
                "scheduled send: skip video media_id=%s reason=%s",
                mid,
                prepared.skip_reason,
            )
        else:
            logger.info(
                "Re-uploading pool media as video: media_id=%s size=%s thumb=%s",
                mid,
                len(data),
                bool(prepared.thumb),
            )
        return prepared
    f = io.BytesIO(data)
    f.name = "media.bin"
    logger.info(
        "Re-uploading pool media as document: media_id=%s size=%s",
        mid,
        len(data),
    )
    return f


def _send_file_kwargs_for_prepared(prepared, base_kw: dict) -> tuple[Any, dict]:
    """Unpack PreparedSendFile / BytesIO into (file, kwargs) for client.send_file."""
    from app.services.video_poster import PreparedSendFile

    kw = dict(base_kw)
    if isinstance(prepared, PreparedSendFile):
        f = prepared.file
        if hasattr(f, "seek"):
            f.seek(0)
        if prepared.thumb is not None:
            prepared.thumb.seek(0)
            kw["thumb"] = prepared.thumb
        if prepared.attributes:
            kw["attributes"] = list(prepared.attributes)
        if prepared.supports_streaming:
            kw["supports_streaming"] = True
        if prepared.mime_type:
            kw["mime_type"] = prepared.mime_type
        return f, kw
    if hasattr(prepared, "seek"):
        prepared.seek(0)
    return prepared, kw


def _filter_sendable_medias(prepared_list: list) -> list:
    """Drop videos marked skip (no usable poster)."""
    from app.services.video_poster import PreparedSendFile

    out = []
    for item in prepared_list:
        if isinstance(item, PreparedSendFile) and item.skip:
            continue
        out.append(item)
    return out


async def _send_prepared_medias(client: TelegramClient, peer, prepared_list: list, base_kw: dict):
    """
    Send one or many prepared medias with per-video thumbs.

    Multi-item albums cannot share one Telethon thumb= — videos with custom posters
    are uploaded as InputMediaUploadedDocument so each keeps its own thumb.
    """
    from telethon.tl.types import InputMediaUploadedDocument

    from app.services.video_poster import PreparedSendFile

    items = _filter_sendable_medias(prepared_list)
    if not items:
        return None

    async def _as_input_media(prep: PreparedSendFile):
        prep.file.seek(0)
        uploaded = await client.upload_file(prep.file)
        thumb_up = None
        if prep.thumb is not None:
            prep.thumb.seek(0)
            thumb_up = await client.upload_file(prep.thumb)
        return InputMediaUploadedDocument(
            file=uploaded,
            mime_type=prep.mime_type or "video/mp4",
            attributes=list(prep.attributes or []),
            thumb=thumb_up,
            force_file=False,
        )

    if len(items) == 1:
        item = items[0]
        if isinstance(item, PreparedSendFile):
            if item.thumb is not None:
                media = await _as_input_media(item)
                return await client.send_file(peer, media, **base_kw)
            f, kw = _send_file_kwargs_for_prepared(item, base_kw)
            return await client.send_file(peer, f, **kw)
        f, kw = _send_file_kwargs_for_prepared(item, base_kw)
        return await client.send_file(peer, f, **kw)

    # Album / multi: promote any PreparedSendFile with thumb to InputMedia so posters stick.
    send_list: list[Any] = []
    for item in items:
        if isinstance(item, PreparedSendFile) and item.thumb is not None:
            send_list.append(await _as_input_media(item))
        elif isinstance(item, PreparedSendFile):
            f, _ = _send_file_kwargs_for_prepared(item, {})
            send_list.append(f)
        else:
            if hasattr(item, "seek"):
                item.seek(0)
            send_list.append(item)
    return await client.send_file(peer, send_list, **base_kw)


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


def _checkout_deep_link_payload(plan_id: int, referral_code: str | None) -> str | None:
    """Telegram /start payload must stay within 64 bytes (UTF-8)."""
    code = (referral_code or "").strip().upper()
    if code:
        if not re.match(r"^[A-Z0-9]{1,16}$", code):
            return None
        raw = f"c{int(plan_id)}_{code}"
    else:
        raw = f"c{int(plan_id)}"
    if len(raw.encode("utf-8")) > 64:
        return None
    return raw


def _merge_scheduled_post_buttons(
    post: ScheduledTextPost,
    db: Session,
    buttons_data: list,
    *,
    allow_inline_checkout: bool = True,
    checkout_enabled: bool | None = None,
) -> list:
    from app.services.aof_vip_checkout import merge_checkout_buttons

    stars_on = checkout_enabled if checkout_enabled is not None else bool(
        getattr(post, "checkout_stars_enabled", False)
    )
    return merge_checkout_buttons(
        buttons_data,
        db,
        checkout_stars_enabled=stars_on,
        checkout_stars_plan_id=getattr(post, "checkout_stars_plan_id", None),
        checkout_button_label=getattr(post, "checkout_button_label", None),
        checkout_referral_code=getattr(post, "checkout_referral_code", None),
        allow_inline_checkout=allow_inline_checkout,
    )


def _effective_album_media_count(media_items: list, promo_ordered: list[str]) -> int:
    if media_items:
        return len(media_items)
    return len(promo_ordered or [])


async def _deliver_checkout_after_scheduled_send(
    *,
    channel_identifier: str,
    db: Session,
    post: ScheduledTextPost,
    reply_to_message_id: int | None,
    message_thread_id: int | None = None,
) -> None:
    """Global Pay ⭐ delivery for all checkout-enabled schedulers (channels + main group)."""
    from app.services.aof_vip_checkout import (
        checkout_multi_album_followup_enabled,
        deliver_stars_checkout_bot_followup,
    )

    if not checkout_multi_album_followup_enabled():
        return
    if not getattr(post, "checkout_stars_enabled", False) or not post.checkout_stars_plan_id:
        return
    if not reply_to_message_id:
        return

    await deliver_stars_checkout_bot_followup(
        channel_identifier,
        db,
        plan_id=int(post.checkout_stars_plan_id),
        reply_to_message_id=int(reply_to_message_id),
        message_thread_id=message_thread_id,
        checkout_button_label=getattr(post, "checkout_button_label", None),
        checkout_referral_code=getattr(post, "checkout_referral_code", None),
        include_bot_fallback=True,
    )


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
                if text and url and url.startswith(("http://", "https://", "tg://")):
                    btns.append(KeyboardButtonUrl(text=text, url=url))
        if btns:
            rows.append(KeyboardButtonRow(buttons=btns))
    if not rows:
        return None
    return ReplyInlineMarkup(rows=rows)


def _send_options(
    post: ScheduledTextPost,
    *,
    channel_identifier: str | None = None,
    had_media: bool = False,
) -> dict:
    from app.services.main_group_notifications import resolve_main_group_send_silent

    silent = resolve_main_group_send_silent(
        channel_identifier=channel_identifier,
        post_send_silent=bool(getattr(post, "send_silent", False)),
        had_media=had_media,
    )
    if silent:
        return {"silent": True}
    return {}


async def _resolve_channel_peer(
    client: TelegramClient,
    channel_identifier: str,
    *,
    invite_fallback: str | None = None,
):
    """See app.utils.telegram_peer.resolve_poster_peer."""
    return await resolve_poster_peer(
        client, channel_identifier, invite_fallback=invite_fallback
    )


def _primary_message_from_send(result):
    if result is None:
        return None
    if isinstance(result, list):
        return result[0] if result else None
    return result


async def _ensure_checkout_buttons_on_message(
    channel_identifier: str,
    sent_result,
    buttons_data: list,
) -> bool:
    """Telethon often drops URL buttons on re-uploaded pool photos — patch via payment bot."""
    if not buttons_data:
        return False
    msg = _primary_message_from_send(sent_result)
    mid = getattr(msg, "id", None) if msg else None
    if not mid:
        return False
    from app.services.telegram_bot_markup import attach_inline_keyboard

    peer = normalize_telethon_peer_identifier(channel_identifier)
    ok = await attach_inline_keyboard(peer, int(mid), buttons_data)
    if ok:
        logger.info("checkout buttons attached via Bot API channel=%s msg=%s", peer, mid)
        return True
    logger.info(
        "checkout buttons not attached on msg=%s (Telethon-sent posts need Bot API follow-up)",
        mid,
    )
    return False


async def _maybe_pin_after_send(
    client: TelegramClient,
    channel_identifier: str,
    post: ScheduledTextPost,
    sent_result,
) -> None:
    if not bool(getattr(post, "pin_after_send", False)):
        return
    msg = _primary_message_from_send(sent_result)
    if msg is None:
        logger.warning("pin_after_send: no message returned from Telegram for scheduled post id=%s", post.id)
        return
    try:
        await client.pin_message(channel_identifier, msg, notify=True)
    except Exception as e:
        logger.warning(
            "pin_after_send failed for scheduled post id=%s: %s",
            getattr(post, "id", None),
            e,
        )
        return

    delete_after = getattr(post, "delete_after_pin_seconds", None)
    if delete_after is not None and int(delete_after) > 0:
        delay = int(delete_after)

        async def _delete_later() -> None:
            await asyncio.sleep(delay)
            try:
                await client.delete_messages(channel_identifier, msg)
            except Exception as e:
                logger.warning(
                    "delete_after_pin failed for scheduled post id=%s: %s",
                    getattr(post, "id", None),
                    e,
                )

        asyncio.create_task(_delete_later())


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


async def _execute_telegram_scheduled_send(
    client: TelegramClient,
    channel_identifier: str,
    *,
    caption: str,
    media_items: list[Media],
    promo_ordered: list[str],
    reply_markup,
    silent_kw: dict,
    reply_to: int | None,
    allow_text_without_media: bool = True,
):
    """
    Low-level Telegram send using pre-resolved caption, media list, and promo URLs.
    promo_ordered is used only when media_items is empty.

    When ``allow_text_without_media`` is False (pool-only library feeds), unresolved
    or empty media returns None instead of posting a text-only flag caption.
    """
    sent_result = None

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
        from app.services.media_message_resolve import fetch_album_medias

        raw_medias = await fetch_album_medias(client, items)
        if not raw_medias or len(raw_medias) != len(items):
            raw_medias = []
        if raw_medias:
            send_medias = []
            for i, raw in enumerate(raw_medias):
                db_media = items[i]
                send_medias.append(
                    await _materialize_pool_media_for_send(client, raw, db_media)
                )
            file_kw: dict = {
                "buttons": reply_markup,
                "reply_to": reply_to,
                "force_document": False,
                **silent_kw,
            }
            _apply_telethon_html_to_kwargs(file_kw, caption, field="caption")
            try:
                sent_result = await _send_prepared_medias(
                    client, channel_identifier, send_medias, file_kw
                )
                if sent_result is None and send_medias:
                    logger.warning(
                        "scheduled send: all videos skipped (no usable poster) media_ids=%s",
                        [int(getattr(m, "id", 0) or 0) for m in items],
                    )
                    if not allow_text_without_media:
                        return None
            except Exception as send_err:
                if not _is_forward_restricted_send_error(send_err):
                    raise
                logger.warning(
                    "scheduled send forward-restricted — retrying with forced download: %s",
                    send_err,
                )
                send_medias = []
                for i, raw in enumerate(raw_medias):
                    db_media = items[i]
                    send_medias.append(
                        await _materialize_pool_media_for_send(client, raw, db_media)
                    )
                sent_result = await _send_prepared_medias(
                    client, channel_identifier, send_medias, file_kw
                )
                if sent_result is None and send_medias and not allow_text_without_media:
                    return None
        else:
            ids = [int(getattr(m, "id", 0) or 0) for m in media_items]
            logger.error(
                "Scheduled post media unresolved — skip text fallback=%s (media_ids=%s). "
                "Check Storage Hub message ids / tbcc/uploads/media-files.",
                not allow_text_without_media,
                ids,
            )
            if not allow_text_without_media:
                return None
            msg_kw: dict = {
                "buttons": reply_markup,
                "reply_to": reply_to,
                **silent_kw,
            }
            _apply_telethon_html_to_kwargs(msg_kw, caption, field="message")
            sent_result = await client.send_message(channel_identifier, **msg_kw)
    else:
        send_bufs = _promo_buffers_from_urls(promo_ordered)
        if send_bufs:
            promo_kw: dict = {
                "buttons": reply_markup,
                "reply_to": reply_to,
                "force_document": False,
                **silent_kw,
            }
            _apply_telethon_html_to_kwargs(promo_kw, caption, field="caption")
            if len(send_bufs) == 1:
                f = send_bufs[0]
                f.seek(0)
                uploaded = await client.upload_file(f)
                sent_result = await client.send_file(channel_identifier, uploaded, **promo_kw)
            else:
                for b in send_bufs:
                    b.seek(0)
                sent_result = await client.send_file(channel_identifier, send_bufs, **promo_kw)
        else:
            if not allow_text_without_media:
                logger.warning(
                    "pool-only scheduled send has no media/promo — skipping text-only caption"
                )
                return None
            msg_kw2: dict = {
                "buttons": reply_markup,
                "reply_to": reply_to,
                **silent_kw,
            }
            _apply_telethon_html_to_kwargs(msg_kw2, caption, field="message")
            sent_result = await client.send_message(channel_identifier, **msg_kw2)

    return sent_result


async def send_scheduled_post(
    client: TelegramClient,
    channel_identifier: str,
    post: ScheduledTextPost,
    db: Session,
    *,
    reshuffle_album: bool = False,
    invite_fallback: str | None = None,
) -> ScheduledSendOutcome | None:
    """Send a scheduled post (text, optional media, optional buttons)."""
    from app.services.content_performance import build_scheduled_send_outcome
    peer = await _resolve_channel_peer(
        client, channel_identifier, invite_fallback=invite_fallback
    )
    slot = _peek_caption_slot_index(post)
    album_order_mode = _album_order_mode_for_send(post, reshuffle_album)
    from app.services.caption_llm_rewrite import resolve_scheduled_caption_for_send
    from app.services.aof_vip_checkout import checkout_active_for_send
    from app.services.aof_packs_send_time import resolve_packs_send_time_if_applicable
    from app.services.aof_full_length_send_time import (
        mark_full_length_media_posted,
        resolve_full_length_send_time_if_applicable,
    )

    packs_ctx = resolve_packs_send_time_if_applicable(db, post)
    full_length_ctx = None if packs_ctx else resolve_full_length_send_time_if_applicable(db, post)
    pack_modifier_id: int | None = None
    full_length_media_ids: list[int] = []
    override_buttons: list | None = None

    checkout_this_send = checkout_active_for_send(
        post, str(channel_identifier), caption_slot_index=slot
    )

    if packs_ctx:
        pack_modifier_id = packs_ctx.pack_modifier_id
        caption = packs_ctx.caption_html
        post.last_sent_caption_html = caption
        from app.services.caption_llm_rewrite import apply_llm_rewrite_if_scheduled

        caption = apply_llm_rewrite_if_scheduled(post, caption, db)
        post.last_sent_caption_html = caption
        mids = packs_ctx.media_ids
        promo_urls: list[str] = []
        use_pool = False
        if packs_ctx.buttons_json:
            try:
                override_buttons = json.loads(packs_ctx.buttons_json)
            except (json.JSONDecodeError, TypeError):
                override_buttons = None
    elif full_length_ctx:
        caption = full_length_ctx.caption_html
        post.last_sent_caption_html = caption
        from app.services.caption_llm_rewrite import apply_llm_rewrite_if_scheduled

        caption = apply_llm_rewrite_if_scheduled(post, caption, db)
        post.last_sent_caption_html = caption
        mids = full_length_ctx.media_ids
        full_length_media_ids = list(mids)
        promo_urls = []
        use_pool = False
    else:
        caption = resolve_scheduled_caption_for_send(post, db)
        mids, promo_urls, use_pool = _resolve_variant_sources(post, slot)
    if checkout_this_send:
        from app.services.aof_vip_checkout import scrub_caption_for_network_post

        caption = scrub_caption_for_network_post(caption)
    media_items = _gather_media_items_for_send(post, db, mids, use_pool, album_order_mode)
    promo_ordered: list[str] = []
    if not media_items:
        promo_ordered = _apply_order_mode_to_sequence(promo_urls, album_order_mode, post)

    album_count = _effective_album_media_count(media_items, promo_ordered)
    multi_album = album_count > 1
    if checkout_this_send and post.checkout_stars_plan_id:
        from app.services.aof_vip_checkout import refresh_checkout_caption_for_send

        caption = refresh_checkout_caption_for_send(
            caption,
            db,
            int(post.checkout_stars_plan_id),
            multi_album_media=multi_album,
            referral_code=getattr(post, "checkout_referral_code", None),
        )

    use_inline_on_post = checkout_this_send and not multi_album
    base_buttons = override_buttons if override_buttons is not None else post.get_buttons()
    merged = _merge_scheduled_post_buttons(
        post,
        db,
        base_buttons,
        allow_inline_checkout=use_inline_on_post,
        checkout_enabled=checkout_this_send,
    )
    reply_markup = _build_reply_markup(merged)
    had_media = bool(media_items) or bool(promo_ordered)
    silent_kw = _send_options(post, channel_identifier=str(channel_identifier), had_media=had_media)
    from app.services.aof_topic_mirror import resolve_liveness_thread_for_send

    reply_to = resolve_liveness_thread_for_send(
        getattr(post, "name", None),
        scheduled_thread_id=getattr(post, "message_thread_id", None),
        rotation_index=getattr(post, "caption_rotation_index", None),
    )
    # Pool-only library / twin feeds must never spam a text "flag" when media resolve fails.
    allow_text_without_media = not bool(getattr(post, "pool_only_mode", False))

    try:
        from app.services.telegram_content_protection import telethon_protect_context

        async with telethon_protect_context(client):
            sent_result = await _execute_telegram_scheduled_send(
                client,
                peer,
                caption=caption,
                media_items=media_items,
                promo_ordered=promo_ordered,
                reply_markup=reply_markup,
                silent_kw=silent_kw,
                reply_to=reply_to,
                allow_text_without_media=allow_text_without_media,
            )
    except ChatRestrictedError:
        _log_chat_restricted_help(str(channel_identifier))
        raise

    if not sent_result:
        logger.warning(
            "scheduled post %s skipped (no Telegram send) pool_only=%s media=%s",
            getattr(post, "id", None),
            not allow_text_without_media,
            [int(getattr(m, "id", 0) or 0) for m in media_items],
        )
        return None

    if sent_result and media_items:
        from app.services.media_album_dedupe import mark_media_rows_posted

        mark_media_rows_posted(db, media_items)

    anchor_id = None
    if sent_result:
        msg = sent_result[0] if isinstance(sent_result, list) else sent_result
        anchor_id = getattr(msg, "id", None)

    if checkout_this_send and anchor_id:
        await _deliver_checkout_after_scheduled_send(
            channel_identifier=str(channel_identifier),
            db=db,
            post=post,
            reply_to_message_id=anchor_id,
            message_thread_id=reply_to,
        )

    await _maybe_pin_after_send(client, peer, post, sent_result)
    from app.services.main_channel_post_divider import maybe_send_main_channel_post_divider

    await maybe_send_main_channel_post_divider(
        client,
        peer,
        db,
        channel_identifier=channel_identifier,
        message_thread_id=reply_to,
        send_silent=bool(silent_kw.get("silent")),
    )
    if full_length_media_ids and sent_result:
        mark_full_length_media_posted(db, full_length_media_ids)
        db.commit()
    if had_media and media_items:
        try:
            from app.services.aof_feed_rhythm_v2 import maybe_queue_post_refill_after_scheduled_send

            maybe_queue_post_refill_after_scheduled_send(db, post=post, media_items=media_items)
        except Exception:
            logger.debug("scheduled post-refill skipped", exc_info=True)
    nk: str | None = None
    if post.pool_id:
        from app.services.export_flywheel_service import network_key_for_pool

        nk = network_key_for_pool(db, int(post.pool_id))
    if not nk and post.channel_id:
        from app.data.aof_network import AOF_NETWORK_CHANNELS
        from app.models.channel import Channel

        ch_row = db.query(Channel).filter(Channel.id == int(post.channel_id)).first()
        ident = (ch_row.identifier or "") if ch_row else ""
        for nc in AOF_NETWORK_CHANNELS:
            if nc.identifier == ident:
                nk = nc.key
                break
    mids = [int(m.id) for m in media_items] if media_items else None
    return build_scheduled_send_outcome(
        post,
        sent_result,
        slot_index=slot,
        pack_modifier_id=pack_modifier_id,
        media_ids=mids,
        network_key=nk,
    )


async def send_scheduled_campaign(
    client: TelegramClient,
    leader: ScheduledTextPost,
    siblings: list[ScheduledTextPost],
    db: Session,
    *,
    target_post_ids: set[int] | None = None,
    reshuffle_album: bool = False,
) -> CampaignSendResult:
    """
    Send the same prepared payload to every sibling channel (shared caption rotation, pool batch, promos).
    siblings must include leader; all rows share one campaign_group_id.
    """
    from app.services.aof_topic_mirror import resolve_liveness_thread_for_send

    slot = _peek_caption_slot_index(leader)
    album_order_mode = _album_order_mode_for_send(leader, reshuffle_album)
    from app.services.caption_llm_rewrite import (
        note_llm_send_completed,
        resolve_scheduled_caption_for_send,
    )

    from app.services.aof_vip_checkout import checkout_active_for_send

    caption = resolve_scheduled_caption_for_send(leader, db)
    merged_leader = _merge_scheduled_post_buttons(leader, db, leader.get_buttons())
    reply_markup_leader = _build_reply_markup(merged_leader)
    mids, promo_urls, use_pool = _resolve_variant_sources(leader, slot)
    media_items = _gather_media_items_for_send(leader, db, mids, use_pool, album_order_mode)
    promo_ordered: list[str] = []
    if not media_items:
        promo_ordered = _apply_order_mode_to_sequence(promo_urls, album_order_mode, leader)

    from app.services.content_performance import build_scheduled_send_outcome

    sent_post_ids: list[int] = []
    failed_post_ids: list[int] = []
    outcomes: dict[int, ScheduledSendOutcome] = {}
    first_error: Exception | None = None
    for p in sorted(siblings, key=lambda x: x.id):
        if target_post_ids is not None and int(p.id) not in target_post_ids:
            continue
        channel = db.query(Channel).filter(Channel.id == p.channel_id).first()
        if not channel:
            logger.warning("Campaign skip: channel %s missing for scheduled post %s", p.channel_id, p.id)
            failed_post_ids.append(int(p.id))
            continue
        peer_raw = normalize_telethon_peer_identifier(channel.identifier)
        # Per-channel caption/buttons/media when siblings differ (links hub + channel promos).
        p_slot = _peek_caption_slot_index(p)
        caption_p = resolve_scheduled_caption_for_send(p, db)
        checkout_this_send = checkout_active_for_send(
            p, peer_raw, caption_slot_index=p_slot
        )
        mids_p, promo_urls_p, use_pool_p = _resolve_variant_sources(p, p_slot)
        media_items_p = _gather_media_items_for_send(p, db, mids_p, use_pool_p, album_order_mode)
        promo_p: list[str] = []
        if not media_items_p:
            promo_p = _apply_order_mode_to_sequence(promo_urls_p, album_order_mode, p)
        had_media_p = bool(media_items_p) or bool(promo_p)
        silent_kw = _send_options(p, channel_identifier=peer_raw, had_media=had_media_p)
        reply_to = resolve_liveness_thread_for_send(
            getattr(p, "name", None),
            scheduled_thread_id=getattr(p, "message_thread_id", None),
            rotation_index=getattr(p, "caption_rotation_index", None),
        )
        if checkout_this_send:
            from app.services.aof_vip_checkout import scrub_caption_for_network_post

            caption_p = scrub_caption_for_network_post(caption_p)
        album_count_p = _effective_album_media_count(media_items_p, promo_p)
        multi_album_p = album_count_p > 1
        if checkout_this_send and p.checkout_stars_plan_id:
            from app.services.aof_vip_checkout import refresh_checkout_caption_for_send

            caption_p = refresh_checkout_caption_for_send(
                caption_p,
                db,
                int(p.checkout_stars_plan_id),
                multi_album_media=multi_album_p,
                referral_code=getattr(p, "checkout_referral_code", None),
            )
        use_inline_on_post = checkout_this_send and not multi_album_p
        merged_p = _merge_scheduled_post_buttons(
            p,
            db,
            p.get_buttons() or leader.get_buttons(),
            allow_inline_checkout=use_inline_on_post,
            checkout_enabled=checkout_this_send,
        )
        reply_markup_p = _build_reply_markup(merged_p)
        if not media_items_p and not promo_p:
            media_items_p = media_items
            promo_p = promo_ordered
            reply_markup_p = reply_markup_leader
            caption_p = caption_p or caption
        try:
            peer = await _resolve_channel_peer(
                client,
                peer_raw,
                invite_fallback=getattr(channel, "invite_link", None),
            )
            from app.services.telegram_content_protection import telethon_protect_context

            async with telethon_protect_context(client):
                sent_result = await _execute_telegram_scheduled_send(
                    client,
                    peer,
                    caption=caption_p,
                    media_items=media_items_p,
                    promo_ordered=promo_p,
                    reply_markup=reply_markup_p,
                    silent_kw=silent_kw,
                    reply_to=reply_to,
                )
            anchor_id = None
            if sent_result:
                msg = sent_result[0] if isinstance(sent_result, list) else sent_result
                anchor_id = getattr(msg, "id", None)
            if checkout_this_send and anchor_id:
                await _deliver_checkout_after_scheduled_send(
                    channel_identifier=peer_raw,
                    db=db,
                    post=p,
                    reply_to_message_id=anchor_id,
                    message_thread_id=reply_to,
                )
            await _maybe_pin_after_send(client, peer, p, sent_result)
            from app.services.main_channel_post_divider import maybe_send_main_channel_post_divider

            await maybe_send_main_channel_post_divider(
                client,
                peer,
                db,
                channel_identifier=peer_raw,
                message_thread_id=reply_to,
                send_silent=bool(silent_kw.get("silent")),
            )
            if sent_result and media_items_p:
                from app.services.media_album_dedupe import mark_media_rows_posted

                mark_media_rows_posted(db, media_items_p)
            sent_post_ids.append(int(p.id))
            outcomes[int(p.id)] = build_scheduled_send_outcome(p, sent_result, slot_index=p_slot)
        except ChatRestrictedError as e:
            _log_chat_restricted_help(peer_raw)
            failed_post_ids.append(int(p.id))
            if first_error is None:
                first_error = e
        except Exception as e:
            logger.exception(
                "Campaign send failed for scheduled post %s channel=%s: %s",
                p.id,
                peer,
                e,
            )
            failed_post_ids.append(int(p.id))
            if first_error is None:
                first_error = e
    return CampaignSendResult(
        sent_post_ids=sent_post_ids,
        failed_post_ids=failed_post_ids,
        first_error=first_error,
        outcomes=outcomes,
    )
