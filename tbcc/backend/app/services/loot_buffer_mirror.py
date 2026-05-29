"""Mirror loot overseer daily AOF promo to Buffer → X (same timing as Telegram send)."""

from __future__ import annotations

import logging
import os

from sqlalchemy.orm import Session

from app.models.loot_bot_settings import LootBotSettings
from app.services.buffer_graphql import (
    buffer_api_key,
    buffer_target_channel_ids,
    create_posts_multi_channel,
    scheduled_buffer_share_mode,
)
from app.services.buffer_post_result import buffer_create_post_succeeded
from app.services.buffer_x_caption import fit_plaintext_for_x, should_fit_for_x
from app.services.loot_bot_settings_effective import ROW_ID, get_effective_loot_bot_settings
from app.services.loot_daily_promo import build_loot_daily_promo_html, loot_daily_promo_inline_keyboard
from app.services.telegram_html_plain import telegram_html_to_plain

logger = logging.getLogger(__name__)


def _loot_overflow_url(eff: dict) -> str:
    env = (os.getenv("TBCC_BUFFER_X_OVERFLOW_URL") or "").strip()
    if env:
        return env
    return (eff.get("primary_loot_room_invite_url") or "").strip()


def _keyboard_lines(eff: dict) -> list[str]:
    bot_user = str(eff.get("bot_username") or "aof_lootgod_bot").strip().lstrip("@")
    kb = loot_daily_promo_inline_keyboard(bot_user)
    lines: list[str] = []
    for row in kb.get("inline_keyboard") or []:
        for btn in row:
            if not isinstance(btn, dict):
                continue
            t = str(btn.get("text") or "").strip()
            u = str(btn.get("url") or "").strip()
            if t and u:
                lines.append(f"{t}: {u}")
            elif u:
                lines.append(u)
    return lines


def build_loot_promo_plaintext_for_x(db: Session) -> str:
    """Telegram promo copy as plain text (pre-X-fit)."""
    html = build_loot_daily_promo_html(db)
    lines = [telegram_html_to_plain(html, max_len=2200)]
    eff = get_effective_loot_bot_settings(db)
    lines.extend(_keyboard_lines(eff))
    return "\n\n".join(x for x in lines if x).strip()


def build_loot_promo_x_caption(db: Session, *, queue_item: dict | None = None) -> str:
    eff = get_effective_loot_bot_settings(db)
    if queue_item and str(queue_item.get("text") or "").strip():
        plain = telegram_html_to_plain(str(queue_item["text"]), max_len=2200)
    else:
        plain = build_loot_promo_plaintext_for_x(db)
    if should_fit_for_x():
        return fit_plaintext_for_x(plain, overflow_url=_loot_overflow_url(eff) or None)
    return plain[:2800]


def mirror_loot_daily_promo_to_buffer(db: Session) -> dict:
    """
    Post to Buffer X after a successful Telegram daily promo.
    Returns {ok, mode, channels, errors?}.
    """
    r = db.query(LootBotSettings).filter(LootBotSettings.id == ROW_ID).first()
    eff = get_effective_loot_bot_settings(db)
    if not eff.get("buffer_mirror_enabled"):
        return {"ok": False, "skipped": True, "reason": "buffer_mirror_disabled"}

    if not buffer_api_key():
        logger.warning("loot buffer mirror: TBCC_BUFFER_API_KEY not set")
        return {"ok": False, "skipped": True, "reason": "no_buffer_api_key"}

    chans = buffer_target_channel_ids(x_primary_only=True)
    if not chans:
        logger.warning("loot buffer mirror: no TBCC_BUFFER_CHANNEL_ID_PRIMARY")
        return {"ok": False, "skipped": True, "reason": "no_buffer_channels"}

    queue = r.get_buffer_x_queue() if r else []
    queue_item = queue[0] if queue else None
    plain = build_loot_promo_x_caption(db, queue_item=queue_item)
    if not plain:
        return {"ok": False, "skipped": True, "reason": "empty_caption"}

    img = None
    if queue_item:
        iu = str(queue_item.get("image_url") or "").strip()
        if iu.startswith("https://"):
            img = iu

    publish_now = bool(eff.get("buffer_publish_now"))
    share_mode = scheduled_buffer_share_mode(buffer_publish_now=publish_now)
    capped = int(os.environ.get("TBCC_BUFFER_MIRROR_MAX_CHANNELS", "6") or 6)
    chans = chans[: max(1, capped)]

    results = create_posts_multi_channel(plain, image_url=img, channel_ids=chans, mode=share_mode)
    ok = any(buffer_create_post_succeeded(r) for r in results)
    if ok and r and queue:
        r.set_buffer_x_queue(queue[1:])
        db.commit()

    logger.info(
        "loot buffer mirror: mode=%s ok=%s chars=%s channels=%s queue_remaining=%s",
        share_mode,
        ok,
        len(plain),
        len(chans),
        len(r.get_buffer_x_queue()) if r else 0,
    )
    return {
        "ok": ok,
        "mode": share_mode,
        "channels": len(chans),
        "chars": len(plain),
        "queue_remaining": len(r.get_buffer_x_queue()) if r else 0,
    }
