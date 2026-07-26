"""Mirror a successfully sent scheduled Telegram post into Buffer (X / IG / Threads)."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.scheduled_text_post import ScheduledTextPost
from app.services.buffer_graphql import (
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
    """Legacy entry — delegates to surface-aware mirror."""
    mirror_scheduled_post_to_buffer_with_surfaces(post_id)


def mirror_scheduled_post_to_buffer_with_surfaces(post_id: int, *, require_mirror_enabled: bool = True) -> dict:
    """
    After Telegram send: post to Buffer with per-surface copy (X vs IG/Threads).
    Returns {ok, channels, x_chars, long_chars, error?, source?}.
    """
    from app.database.session import SessionLocal
    from app.services.buffer_graphql import (
        create_post,
        scheduled_buffer_share_mode,
    )
    from app.services.buffer_x_channel_route import (
        buffer_mirror_x_only_for_telegram_identifier,
        buffer_x_channel_for_telegram_identifier,
    )
    from app.services.campaign_surface_copy import buffer_secondary_channel_ids, resolve_surface_texts
    from app.models.channel import Channel

    db = SessionLocal()
    try:
        post = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == int(post_id)).first()
        if not post:
            return {"ok": False, "error": "post missing", "channels": 0}
        if require_mirror_enabled and not getattr(post, "buffer_mirror_enabled", False):
            return {"ok": False, "error": "buffer_mirror disabled or post missing", "channels": 0}

        ch = db.query(Channel).filter(Channel.id == int(post.channel_id)).first() if post.channel_id else None
        tg_ident = (ch.identifier if ch else None) or None
        x_channel = buffer_x_channel_for_telegram_identifier(tg_ident)
        if not x_channel:
            logger.warning("buffer mirror: no X channel id (PRIMARY / X_SECONDARY / map)")
            return {"ok": False, "error": "no buffer channel ids", "channels": 0}

        queue = post.get_buffer_x_queue()
        used_queue = False
        img: str | None = None
        texts = resolve_surface_texts(post, db)

        if queue:
            item = queue[0]
            plain_x = _plain_from_queue_item(item, post, db)
            iu = str(item.get("image_url") or "").strip()
            img = iu if _public_https_image_url(iu) else None
            used_queue = True
            plain_long = plain_x
        else:
            plain_x = texts.get("x") or build_buffer_x_mirror_text(post, db)
            plain_long = texts.get("ig_threads") or texts.get("long") or build_buffer_plaintext_from_post(post, db)
            img = first_public_promo_image_url(post, db)

        if not plain_x and not plain_long:
            return {"ok": False, "error": "empty buffer body", "channels": 0}

        if plain_x and not used_queue:
            from app.services.buffer_x_caption import finalize_buffer_x_caption, resolve_overflow_url
            from app.services.buffer_x_outbound_guard import (
                network_key_for_telegram_identifier,
                strict_mirror_network_keys,
            )

            net_key = network_key_for_telegram_identifier(tg_ident, db)
            strict = bool(net_key and net_key in strict_mirror_network_keys())
            try:
                plain_x = finalize_buffer_x_caption(
                    plain_x,
                    db=db,
                    overflow_url=resolve_overflow_url(post=post, db=db) or None,
                    advance_link_cycle=True,
                    network_key=net_key,
                    strict=strict,
                )
            except ValueError as e:
                logger.error("buffer mirror blocked (bare URL): post=%s %s", post_id, e)
                return {"ok": False, "error": str(e), "channels": 0}

        share_mode = scheduled_buffer_share_mode(
            buffer_publish_now=bool(getattr(post, "buffer_publish_now", False))
        )
        capped = int(os.environ.get("TBCC_BUFFER_MIRROR_MAX_CHANNELS", "6") or 6)

        x_only = buffer_mirror_x_only_for_telegram_identifier(tg_ident)
        secondary = [] if x_only else buffer_secondary_channel_ids()[: max(0, capped - 1)]
        results: list[dict] = []

        if x_channel and plain_x:
            try:
                results.append(create_post(x_channel, plain_x, mode=share_mode, image_url=img))
            except Exception as e:
                results.append({"error": str(e), "channelId": x_channel})

        for cid in secondary:
            body = plain_long or plain_x
            if not body:
                continue
            try:
                from app.services.buffer_ig_carousel import ig_create_post_kwargs, ig_story_enabled, post_instagram_story
                from app.services.buffer_surface_caption import build_instagram_caption

                ig_body = texts.get("ig_threads") or build_instagram_caption(
                    teaser=plain_long or plain_x,
                    utm_campaign="scheduled_mirror",
                )
                results.append(create_post(cid, ig_body, mode=share_mode, **ig_create_post_kwargs()))
                if ig_story_enabled():
                    results.append(
                        post_instagram_story(
                            cid,
                            build_instagram_caption(teaser="Story → tap link sticker.", utm_campaign="scheduled_story"),
                            mode=share_mode,
                        )
                    )
            except Exception as e:
                results.append({"error": str(e), "channelId": cid})

        ok = any(buffer_create_post_succeeded(r) for r in results)
        if ok and used_queue:
            post.set_buffer_x_queue(queue[1:])
        if ok:
            db.commit()

        try:
            from app.services.buffer_post_result import buffer_create_post_id, buffer_create_post_succeeded as buf_ok
            from app.services.content_performance import latest_telegram_delivery_for_scheduled_post, record_surface_delivery_metric

            parent = latest_telegram_delivery_for_scheduled_post(db, int(post_id))
            for r in results:
                if not buf_ok(r):
                    continue
                pid = buffer_create_post_id(r)
                if pid and parent:
                    record_surface_delivery_metric(
                        db,
                        parent=parent,
                        surface="buffer_x",
                        external_post_id=pid,
                        export_source="scheduler",
                    )
            if parent:
                db.commit()
        except Exception:
            logger.debug("buffer surface ledger skipped", exc_info=True)

        logger.info(
            "buffer mirror: scheduled_post_id=%s mode=%s source=%s ok=%s channels=%s",
            post_id,
            share_mode,
            "tbcc_queue" if used_queue else "surface_copy",
            ok,
            len(results),
        )
        return {
            "ok": ok,
            "channels": len(results),
            "x_chars": len(plain_x or ""),
            "long_chars": len(plain_long or ""),
            "source": "tbcc_queue" if used_queue else "surface_copy",
        }
    except Exception as e:
        logger.exception("buffer mirror failed for scheduled_post_id=%s", post_id)
        return {"ok": False, "error": str(e), "channels": 0}
    finally:
        db.close()


