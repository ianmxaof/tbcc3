"""Daily Loot Room promo — Telegram target + Buffer/X mirror via @aof_lootgod_bot."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

from app.data.aof_network import BANNED_MAIN_GROUP_IDENT
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)

# Banned AOF Main — do not attempt Telegram send; Buffer mirror still runs.
_BANNED_MAIN_GROUP_CHAT_ID = int(BANNED_MAIN_GROUP_IDENT)


def _mirror_to_buffer() -> None:
    try:
        from app.database.session import SessionLocal
        from app.services.loot_buffer_mirror import mirror_loot_daily_promo_to_buffer

        db2 = SessionLocal()
        try:
            mirror_loot_daily_promo_to_buffer(db2)
        finally:
            db2.close()
    except Exception:
        logger.exception("Loot daily promo Buffer mirror failed")


def _post_loot_promo(*, force: bool = False) -> None:
    from app.database.session import SessionLocal
    from app.services.loot_bot_settings_effective import get_effective_loot_bot_settings, resolve_bot_token_raw
    from app.services.loot_daily_promo import build_loot_daily_promo_html, loot_daily_promo_inline_keyboard

    db = SessionLocal()
    try:
        s = get_effective_loot_bot_settings(db)
        if not force and not bool(s.get("daily_promo_enabled")):
            logger.debug("Loot daily promo: disabled (enable in Dashboard → Bots → Loot overseer)")
            return

        chat_id = s.get("aof_group_chat_id")
        if chat_id is None:
            env_cid = (os.getenv("TBCC_LOOT_AOF_GROUP_CHAT_ID") or "").strip()
            if env_cid:
                try:
                    chat_id = int(env_cid)
                except ValueError:
                    chat_id = None

        hour_cfg = s.get("daily_promo_hour_utc")
        if hour_cfg is None:
            raw = (os.getenv("TBCC_LOOT_DAILY_PROMO_HOUR_UTC") or "18").strip()
            try:
                target_hour = int(raw)
            except ValueError:
                target_hour = 18
        else:
            target_hour = int(hour_cfg)
        target_hour = max(0, min(23, target_hour))

        now_h = datetime.now(timezone.utc).hour
        if not force and now_h != target_hour:
            logger.info(
                "Loot daily promo skipped: UTC hour %s != configured %s "
                "(Dashboard daily promo hour, or celery call with force=true)",
                now_h,
                target_hour,
            )
            return

        text = build_loot_daily_promo_html(db)
        bot_username = str(s.get("bot_username") or "aof_lootgod_bot")
        thread_id = s.get("aof_group_message_thread_id")
        token = resolve_bot_token_raw(db)
        buffer_only = bool(s.get("buffer_mirror_enabled"))
    finally:
        db.close()

    # Banned Main: skip Telegram, still mirror to Buffer/X when enabled.
    if chat_id is not None and int(chat_id) == _BANNED_MAIN_GROUP_CHAT_ID:
        logger.warning(
            "Loot daily promo: aof_group_chat_id=%s is banned AOF Main — "
            "Telegram send skipped; Buffer mirror only. Retarget Dashboard → Loot overseer "
            "or clear TBCC_LOOT_AOF_GROUP_CHAT_ID.",
            chat_id,
        )
        if buffer_only:
            _mirror_to_buffer()
        return

    if chat_id is None:
        if buffer_only:
            logger.info("Loot daily promo: no Telegram chat id — Buffer/X mirror only")
            _mirror_to_buffer()
            return
        logger.debug(
            "Loot daily promo: no aof_group_chat_id (Dashboard → Loot overseer, or TBCC_LOOT_AOF_GROUP_CHAT_ID)"
        )
        return

    if not token:
        logger.warning("Loot daily promo: loot bot token not configured (TBCC_LOOT_BOT_TOKEN or dashboard)")
        return

    payload: dict = {
        "chat_id": int(chat_id),
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
        "reply_markup": loot_daily_promo_inline_keyboard(bot_username),
    }
    if isinstance(thread_id, int) and thread_id > 0:
        payload["message_thread_id"] = thread_id

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=30) as client:
            r = client.post(url, json=payload)
            if r.status_code != 200:
                logger.warning("Loot daily promo failed: %s %s", r.status_code, r.text)
            else:
                logger.info("Loot daily promo sent to aof_group_chat_id=%s", chat_id)
                _mirror_to_buffer()
    except Exception as e:
        logger.exception("Loot daily promo error: %s", e)


@celery.task(name="app.workers.loot_promo_worker.send_loot_daily_promo")
def send_loot_daily_promo(force: bool = False):
    """
    Post loot game advertisement once per day (Telegram target and/or Buffer/X).

    Configure in Dashboard → Bots → Loot overseer (not Growth settings).
    Beat runs every hour UTC; only the configured hour sends unless force=True.
    """
    _post_loot_promo(force=force)
