"""Mirror a successfully sent scheduled Telegram post into Buffer (X / IG / Threads)."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.scheduled_text_post import ScheduledTextPost
from app.services.buffer_graphql import (
    buffer_target_channel_ids,
    create_posts_multi_channel,
    scheduled_buffer_share_mode,
)
from app.services.buffer_post_result import buffer_create_post_succeeded
from app.services.scheduled_post_service import (
    _album_order_mode_for_send,
    _apply_order_mode_to_sequence,
    _gather_media_items_for_send,
    _merge_scheduled_post_buttons,
    _resolve_variant_sources,
)
from app.services.buffer_x_caption import fit_buffer_mirror_plaintext
from app.services.telegram_html_plain import telegram_html_to_plain

logger = logging.getLogger(__name__)


def _public_https_image_url(url: str) -> bool:
    u = (url or "").strip().lower()
    try:
        p = urlparse(u)
        return p.scheme == "https" and bool(p.netloc)
    except Exception:
        return False


def _sent_caption_html(post: ScheduledTextPost) -> str:
    """Caption that was just posted (snapshot or rotation index after send)."""
    snap = getattr(post, "last_sent_caption_html", None)
    if snap and str(snap).strip():
        return str(snap).strip()
    vars_ = post.get_content_variations()
    n = len(vars_)
    if n >= 2:
        k = post.caption_rotation_index or 0
        idx = (k - 1) % n
        return vars_[idx]
    if n == 1:
        return vars_[0]
    return post.content or ""


def _sent_slot_index(post: ScheduledTextPost) -> int:
    vars_ = post.get_content_variations()
    n = len(vars_)
    if n >= 2:
        k = post.caption_rotation_index or 0
        return (k - 1) % n
    return 0


def build_buffer_plaintext_from_post(post: ScheduledTextPost, db: Session) -> str:
    """Full mirror (caption + link buttons) — may exceed X limits; prefer build_buffer_x_mirror_text."""
    cap_html = _sent_caption_html(post)
    merged = _merge_scheduled_post_buttons(post, db, post.get_buttons())
    lines = [telegram_html_to_plain(cap_html, max_len=2200)]
    for b in merged:
        if not isinstance(b, dict):
            continue
        t = str(b.get("text") or "").strip()
        u = str(b.get("url") or "").strip()
        if t and u:
            lines.append(f"{t}: {u}")
        elif u:
            lines.append(u)
    return "\n\n".join(x for x in lines if x).strip()


def build_buffer_x_mirror_text(post: ScheduledTextPost, db: Session) -> str:
    """Telegram caption only, trimmed for X with overflow link to the channel invite."""
    cap_html = _sent_caption_html(post)
    plain = telegram_html_to_plain(cap_html, max_len=2200)
    return fit_buffer_mirror_plaintext(plain, post=post, db=db)


def first_public_promo_image_url(post: ScheduledTextPost, db: Session) -> str | None:
    """First https promo URL for this send slot (Buffer cannot use Telegram-only media)."""
    slot = _sent_slot_index(post)
    album_order_mode = _album_order_mode_for_send(post, reshuffle_album=False)
    mids, promo_urls, use_pool = _resolve_variant_sources(post, slot)
    media_items = _gather_media_items_for_send(post, db, mids, use_pool, album_order_mode)
    if media_items:
        return None
    ordered = _apply_order_mode_to_sequence(promo_urls, album_order_mode, post)
    for u in ordered:
        if _public_https_image_url(u):
            return u.strip()
    return None


def _plain_from_queue_item(item: dict, post: ScheduledTextPost, db: Session) -> str:
    """Pre-written X caption from TBCC queue (fitted for X length)."""
    cap = str(item.get("text") or "").strip()
    plain = telegram_html_to_plain(cap, max_len=2200)
    return fit_buffer_mirror_plaintext(plain, post=post, db=db)


def mirror_scheduled_post_to_buffer_sync(post_id: int) -> None:
    """
    Celery task body: after Telegram send, post to Buffer (shareNow or addToQueue per job).
    Uses the next TBCC-stored X caption if any; otherwise mirrors the Telegram caption.
    """
    from app.database.session import SessionLocal

    db = SessionLocal()
    try:
        post = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == int(post_id)).first()
        if not post or not getattr(post, "buffer_mirror_enabled", False):
            return
        if not buffer_target_channel_ids():
            logger.warning("buffer mirror: no TBCC_BUFFER_CHANNEL_ID_PRIMARY / TBCC_BUFFER_CHANNEL_IDS set")
            return

        queue = post.get_buffer_x_queue()
        used_queue = False
        if queue:
            item = queue[0]
            plain = _plain_from_queue_item(item, post, db)
            iu = str(item.get("image_url") or "").strip()
            img = iu if _public_https_image_url(iu) else None
            used_queue = True
        else:
            raw_full = build_buffer_plaintext_from_post(post, db)
            plain = build_buffer_x_mirror_text(post, db)
            img = first_public_promo_image_url(post, db)

        if not plain:
            logger.warning("buffer mirror: empty body for scheduled post %s", post_id)
            return

        if not used_queue and len(raw_full) > len(plain):
            logger.info(
                "buffer mirror: X caption post_id=%s %s→%s chars (overflow link)",
                post_id,
                len(raw_full),
                len(plain),
            )

        capped = int(os.environ.get("TBCC_BUFFER_MIRROR_MAX_CHANNELS", "6") or 6)
        chans = buffer_target_channel_ids()[: max(1, capped)]
        share_mode = scheduled_buffer_share_mode(
            buffer_publish_now=bool(getattr(post, "buffer_publish_now", False))
        )
        results = create_posts_multi_channel(
            plain, image_url=img, channel_ids=chans, mode=share_mode
        )
        ok = any(buffer_create_post_succeeded(r) for r in results)
        if ok and used_queue:
            post.set_buffer_x_queue(queue[1:])
            db.commit()
        logger.info(
            "buffer mirror: scheduled_post_id=%s mode=%s source=%s ok=%s channels=%s remaining_queue=%s",
            post_id,
            share_mode,
            "tbcc_queue" if used_queue else "telegram_mirror",
            ok,
            len(chans),
            len(post.get_buffer_x_queue()),
        )
    except Exception:
        logger.exception("buffer mirror failed for scheduled_post_id=%s", post_id)
    finally:
        db.close()
