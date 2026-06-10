"""Send scheduled posts (text, media, buttons) to Telegram channels."""
import io
import json
import logging
import os
import random
import re
from collections import defaultdict
from dataclasses import dataclass

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
    if bool(getattr(post, "pool_only_mode", False)) and _post_uses_pool(post):
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
        return _pick_collective_pool_id(db)
    return post.pool_id


def _load_pool_media_items(
    post: ScheduledTextPost,
    db: Session,
    album_order_mode: str,
) -> list[Media]:
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
    q = db.query(Media).filter(Media.pool_id == effective_pool_id, Media.status == "approved")
    # Randomize means random *selection* from the full approved pool.
    # Album order mode (static/shuffle/carousel) is applied later to the selected batch.
    if randomize:
        rows = q.all()
        random.shuffle(rows)
        return rows[:album_size]
    return q.order_by(Media.id.asc()).limit(album_size).all()


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


def _merge_scheduled_post_buttons(post: ScheduledTextPost, db: Session, buttons_data: list) -> list:
    """
    Append optional URL button → TBCC payment bot deep link (same Stars invoice flow as /subscribe).
    Native Stars UI opens in the user's private chat with the bot after they tap the button — not inside the channel post.
    """
    base = list(buttons_data) if buttons_data else []
    if not bool(getattr(post, "checkout_stars_enabled", False)):
        return base
    plan_id = getattr(post, "checkout_stars_plan_id", None)
    if not plan_id:
        logger.warning("scheduled post %s: checkout enabled but no checkout_stars_plan_id", getattr(post, "id", "?"))
        return base
    bot = (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "").strip().lstrip("@")
    if not bot:
        logger.warning(
            "scheduled post %s: Stars checkout enabled but TBCC_PAYMENT_BOT_USERNAME is unset",
            getattr(post, "id", "?"),
        )
        return base
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == int(plan_id)).first()
    if not plan or plan.is_active is False or int(plan.price_stars or 0) <= 0:
        logger.warning(
            "scheduled post %s: checkout plan %s missing, inactive, or has no Stars price",
            getattr(post, "id", "?"),
            plan_id,
        )
        return base
    ref = getattr(post, "checkout_referral_code", None)
    payload = _checkout_deep_link_payload(int(plan_id), ref)
    if not payload:
        logger.warning(
            "scheduled post %s: invalid checkout deep link (plan=%s ref=%r)",
            getattr(post, "id", "?"),
            plan_id,
            ref,
        )
        return base
    url = f"https://t.me/{bot}?start={payload}"
    label = (getattr(post, "checkout_button_label", None) or "").strip()
    if not label:
        stars = int(plan.price_stars or 0)
        name = (plan.name or "Subscribe").strip()[:36]
        label = f"{name} — {stars}⭐"
    if len(label) > 64:
        label = label[:63] + "…"
    return base + [{"text": label, "url": url}]


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


def _send_options(post: ScheduledTextPost) -> dict:
    if bool(getattr(post, "send_silent", False)):
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
        await client.pin_message(channel_identifier, msg, notify=False)
    except Exception as e:
        logger.warning(
            "pin_after_send failed for scheduled post id=%s: %s",
            getattr(post, "id", None),
            e,
        )


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
):
    """
    Low-level Telegram send using pre-resolved caption, media list, and promo URLs.
    promo_ordered is used only when media_items is empty.
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
        from app.services.local_media_storage import is_local_pool_media, telethon_file_from_media

        saved_ids = [m.telegram_message_id for m in items if not is_local_pool_media(m)]
        msg_map: dict = {}
        if saved_ids:
            messages = await client.get_messages("me", ids=saved_ids)
            msg_map = {m.id: m for m in messages if m}
        raw_medias = []
        for m in items:
            if is_local_pool_media(m):
                f = telethon_file_from_media(m)
                if f is not None:
                    raw_medias.append(f)
                continue
            msg = msg_map.get(m.telegram_message_id)
            if msg and msg.media:
                raw_medias.append(msg.media)
        if raw_medias:
            send_medias = []
            for i, raw in enumerate(raw_medias):
                db_media = items[i]
                if not isinstance(raw, MessageMediaDocument):
                    send_medias.append(raw)
                    continue
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
            file_kw: dict = {
                "buttons": reply_markup,
                "reply_to": reply_to,
                "force_document": False,
                **silent_kw,
            }
            _apply_telethon_html_to_kwargs(file_kw, caption, field="caption")
            if len(send_medias) == 1 and isinstance(send_medias[0], io.BytesIO):
                f = send_medias[0]
                f.seek(0)
                uploaded = await client.upload_file(f)
                sent_result = await client.send_file(channel_identifier, uploaded, **file_kw)
            elif len(send_medias) == 1:
                sent_result = await client.send_file(channel_identifier, send_medias[0], **file_kw)
            else:
                sent_result = await client.send_file(channel_identifier, send_medias, **file_kw)
        else:
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
) -> None:
    """Send a scheduled post (text, optional media, optional buttons)."""
    peer = await _resolve_channel_peer(
        client, channel_identifier, invite_fallback=invite_fallback
    )
    slot = _peek_caption_slot_index(post)
    album_order_mode = _album_order_mode_for_send(post, reshuffle_album)
    from app.services.caption_llm_rewrite import resolve_scheduled_caption_for_send

    caption = resolve_scheduled_caption_for_send(post, db)
    merged = _merge_scheduled_post_buttons(post, db, post.get_buttons())
    reply_markup = _build_reply_markup(merged)
    silent_kw = _send_options(post)
    reply_to = post.message_thread_id if getattr(post, "message_thread_id", None) else None

    mids, promo_urls, use_pool = _resolve_variant_sources(post, slot)
    media_items = _gather_media_items_for_send(post, db, mids, use_pool, album_order_mode)
    promo_ordered: list[str] = []
    if not media_items:
        promo_ordered = _apply_order_mode_to_sequence(promo_urls, album_order_mode, post)

    try:
        sent_result = await _execute_telegram_scheduled_send(
            client,
            peer,
            caption=caption,
            media_items=media_items,
            promo_ordered=promo_ordered,
            reply_markup=reply_markup,
            silent_kw=silent_kw,
            reply_to=reply_to,
        )
    except ChatRestrictedError:
        _log_chat_restricted_help(str(channel_identifier))
        raise

    await _maybe_pin_after_send(client, peer, post, sent_result)


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
    slot = _peek_caption_slot_index(leader)
    album_order_mode = _album_order_mode_for_send(leader, reshuffle_album)
    from app.services.caption_llm_rewrite import (
        note_llm_send_completed,
        resolve_scheduled_caption_for_send,
    )

    caption = resolve_scheduled_caption_for_send(leader, db)
    merged = _merge_scheduled_post_buttons(leader, db, leader.get_buttons())
    reply_markup = _build_reply_markup(merged)
    mids, promo_urls, use_pool = _resolve_variant_sources(leader, slot)
    media_items = _gather_media_items_for_send(leader, db, mids, use_pool, album_order_mode)
    promo_ordered: list[str] = []
    if not media_items:
        promo_ordered = _apply_order_mode_to_sequence(promo_urls, album_order_mode, leader)

    sent_post_ids: list[int] = []
    failed_post_ids: list[int] = []
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
        silent_kw = _send_options(p)
        reply_to = p.message_thread_id if getattr(p, "message_thread_id", None) else None
        try:
            peer = await _resolve_channel_peer(
                client,
                peer_raw,
                invite_fallback=getattr(channel, "invite_link", None),
            )
            sent_result = await _execute_telegram_scheduled_send(
                client,
                peer,
                caption=caption,
                media_items=media_items,
                promo_ordered=promo_ordered,
                reply_markup=reply_markup,
                silent_kw=silent_kw,
                reply_to=reply_to,
            )
            await _maybe_pin_after_send(client, peer, p, sent_result)
            sent_post_ids.append(int(p.id))
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
    )
