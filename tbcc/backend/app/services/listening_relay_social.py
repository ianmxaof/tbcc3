"""Optional Buffer + Discord fan-out for listening relay (separate pacing from Telegram)."""

from __future__ import annotations

import logging
import os
from datetime import datetime

from app.database.session import SessionLocal
from app.models.listening_relay_settings import ListeningRelaySettings
from app.services.buffer_graphql import buffer_target_channel_ids, create_post
from app.services.buffer_x_caption import (
    finalize_buffer_x_caption,
    resolve_overflow_url,
    should_fit_for_x,
)
from app.services.outbound_webhook import notify_discord_webhook_text
from app.services.telegram_html_plain import telegram_html_to_plain

logger = logging.getLogger(__name__)

ROW_ID = 1


def _ensure_row(db):
    r = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == ROW_ID).first()
    if r:
        return r
    r = ListeningRelaySettings(id=ROW_ID)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def run_listening_relay_social_fanout(
    html_body: str,
    copy_block_followup_html: str | None = None,
    *,
    relay_log_id: int | None = None,
) -> None:
    """Discord (if webhook env set): every event. Buffer: only if enabled + under throttle caps."""
    from app.services.listening_relay_send import followups_from_json

    parts = [(html_body or "").strip()]
    followups = followups_from_json(copy_block_followup_html)
    if followups:
        for fu in followups:
            chunk = (fu.html or "").strip()
            if chunk:
                parts.append(chunk)
            if fu.media_ids or fu.attachment_urls:
                parts.append("[copy panel: media attached]")
    else:
        follow = (copy_block_followup_html or "").strip()
        if follow:
            parts.append(follow)
    plain = telegram_html_to_plain("\n\n".join(parts), max_len=2000)
    if not plain:
        return
    hook = (os.environ.get("TBCC_DISCORD_LISTENING_RELAY_WEBHOOK_URL") or "").strip()

    db = SessionLocal()
    discord_marked = False
    try:
        if hook:
            from app.services.buffer_surface_caption import build_discord_caption

            notify_discord_webhook_text(hook, build_discord_caption(teaser=plain, utm_campaign="relay"))
            if relay_log_id:
                from app.services.listening_relay_history import mark_relay_discord_sent

                mark_relay_discord_sent(db, int(relay_log_id))
                discord_marked = True

        row = _ensure_row(db)
        if not getattr(row, "buffer_relay_enabled", False):
            if discord_marked:
                db.commit()
            return
        if not buffer_target_channel_ids():
            logger.warning("listening relay buffer: no channel ids in env")
            if discord_marked:
                db.commit()
            return
        now = datetime.utcnow()
        day = now.strftime("%Y-%m-%d")
        max_day = max(1, int(getattr(row, "buffer_relay_max_per_day_utc", None) or 5))
        min_gap_m = max(30, int(getattr(row, "buffer_relay_min_interval_minutes", None) or 360))

        if getattr(row, "buffer_relay_utc_day", None) != day:
            row.buffer_relay_utc_day = day
            row.buffer_relay_posts_today = 0

        if int(row.buffer_relay_posts_today or 0) >= max_day:
            logger.info("listening relay buffer: daily cap %s reached", max_day)
            if discord_marked:
                db.commit()
            return
        last = getattr(row, "buffer_relay_last_post_at", None)
        if last:
            delta_m = (now - last).total_seconds() / 60.0
            if delta_m < min_gap_m:
                logger.info(
                    "listening relay buffer: skipped (min interval %sm, %.1fm since last)",
                    min_gap_m,
                    delta_m,
                )
                if discord_marked:
                    db.commit()
                return

        queue = row.get_buffer_x_queue()
        used_queue = False
        img: str | None = None
        if queue:
            item = queue[0]
            plain = str(item.get("text") or "").strip()
            iu = str(item.get("image_url") or "").strip()
            img = iu if iu.startswith("https://") else None
            used_queue = bool(plain)
        elif should_fit_for_x():
            plain = finalize_buffer_x_caption(
                plain,
                db=db,
                overflow_url=resolve_overflow_url() or None,
                advance_link_cycle=True,
            )

        if not plain:
            if discord_marked:
                db.commit()
            return

        capped = int(os.environ.get("TBCC_BUFFER_RELAY_MAX_CHANNELS", "6") or 6)
        chans = buffer_target_channel_ids()[: max(1, capped)]
        share_mode = (os.getenv("TBCC_BUFFER_RELAY_SHARE_NOW") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        mode = "shareNow" if share_mode else "addToQueue"
        from app.services.campaign_surface_copy import buffer_primary_channel_id, buffer_secondary_channel_ids
        from app.services.buffer_ig_carousel import (
            ig_create_post_kwargs,
            ig_story_enabled,
            next_carousel_image_urls,
            post_instagram_story,
        )
        from app.services.buffer_surface_caption import build_instagram_caption

        primary = buffer_primary_channel_id()
        secondary = [c for c in buffer_secondary_channel_ids() if c in chans]
        ig_body = build_instagram_caption(teaser=plain, utm_campaign="relay_armory")

        if primary and primary in chans:
            create_post(primary, plain, mode=mode, image_url=img)
        for cid in secondary:
            create_post(cid, ig_body, mode=mode, **ig_create_post_kwargs())
            if ig_story_enabled():
                story_urls = next_carousel_image_urls(slides=1)
                story_img = story_urls[0] if story_urls else None
                post_instagram_story(
                    cid,
                    build_instagram_caption(teaser="Story → tap link sticker.", utm_campaign="relay_story"),
                    mode=mode,
                    image_url=story_img,
                )
        if used_queue:
            row.set_buffer_x_queue(queue[1:])
        row.buffer_relay_posts_today = int(row.buffer_relay_posts_today or 0) + 1
        row.buffer_relay_last_post_at = now
        if relay_log_id:
            from app.services.listening_relay_history import mark_relay_buffer_sent

            mark_relay_buffer_sent(db, int(relay_log_id))
        db.commit()
        logger.info(
            "listening relay buffer: mode=%s source=%s channels=%s queue_remaining=%s",
            mode,
            "tbcc_queue" if used_queue else "relay_mirror",
            len(chans),
            len(row.get_buffer_x_queue()),
        )
    except Exception:
        logger.exception("listening_relay_social_fanout failed")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()
