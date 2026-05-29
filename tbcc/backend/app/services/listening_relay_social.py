"""Optional Buffer + Discord fan-out for listening relay (separate pacing from Telegram)."""

from __future__ import annotations

import logging
import os
from datetime import datetime

from app.database.session import SessionLocal
from app.models.listening_relay_settings import ListeningRelaySettings
from app.services.buffer_graphql import buffer_target_channel_ids, create_posts_multi_channel
from app.services.buffer_x_caption import (
    fit_plaintext_for_x,
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
    if hook:
        notify_discord_webhook_text(hook, plain)

    db = SessionLocal()
    try:
        row = _ensure_row(db)
        if not getattr(row, "buffer_relay_enabled", False):
            return
        if not buffer_target_channel_ids():
            logger.warning("listening relay buffer: no channel ids in env")
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
                return

        if should_fit_for_x():
            plain = fit_plaintext_for_x(plain, overflow_url=resolve_overflow_url() or None)

        capped = int(os.environ.get("TBCC_BUFFER_RELAY_MAX_CHANNELS", "6") or 6)
        chans = buffer_target_channel_ids()[: max(1, capped)]
        create_posts_multi_channel(plain, image_url=None, channel_ids=chans)
        row.buffer_relay_posts_today = int(row.buffer_relay_posts_today or 0) + 1
        row.buffer_relay_last_post_at = now
        db.commit()
        logger.info("listening relay buffer: queued %s channel(s)", len(chans))
    except Exception:
        logger.exception("listening_relay_social_fanout failed")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()
