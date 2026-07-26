"""Loot goblin channel announce via loot bot Bot API."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.channel import Channel
from app.models.goblin_drop import GoblinDrop
from app.models.listening_relay_settings import ListeningRelaySettings
from app.services.aof_social_links import loot_bot_username
from app.services.loot_bot_settings_effective import resolve_bot_token_raw
from app.services.telegram_bot_api import tg_post_with_token
from app.utils.telegram_peer import normalize_telethon_peer_identifier

logger = logging.getLogger(__name__)


def build_goblin_announce_html(*, claims_cap: int, ttl_seconds: int) -> str:
    cap = max(1, int(claims_cap))
    ttl = max(5, int(ttl_seconds))
    return (
        "👺 <b>Loot goblin!</b>\n"
        f"First <b>{cap}</b> tappers get a complimentary pull.\n"
        f"<i>Announce vanishes in ~{ttl}s — token stays valid until cap.</i>"
    )


def build_goblin_deep_link(token: str) -> str:
    user = loot_bot_username()
    return f"https://t.me/{user}?start=goblin_{token}"


def send_goblin_announce(
    db: Session,
    drop: GoblinDrop,
    *,
    settings: ListeningRelaySettings | None = None,
) -> dict[str, Any]:
    """Post goblin announce to relay channel; stores announce_message_id on drop."""
    if drop.status != "active":
        return {"ok": False, "error": "drop_not_active"}

    ch = db.query(Channel).filter(Channel.id == int(drop.channel_id or 0)).first()
    if not ch:
        return {"ok": False, "error": "channel_not_found"}

    token_raw = resolve_bot_token_raw(db)
    if not token_raw:
        return {"ok": False, "error": "loot_bot_token_unset"}

    settings = settings or db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == 1).first()
    ttl = int(getattr(settings, "goblin_announce_ttl_seconds", None) or 45) if settings else 45
    cap = int(drop.claims_cap or 5)
    chat_id = normalize_telethon_peer_identifier(ch.identifier)
    text = build_goblin_announce_html(claims_cap=cap, ttl_seconds=ttl)
    deep = build_goblin_deep_link(drop.token)
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": True,
        "reply_markup": {
            "inline_keyboard": [[{"text": "👺 Claim loot", "url": deep}]],
        },
    }
    if drop.message_thread_id:
        payload["message_thread_id"] = int(drop.message_thread_id)

    out = _tg_post_with_token("sendMessage", payload, token_raw)
    if not out.get("ok"):
        logger.warning("goblin announce failed drop=%s: %s", drop.id, out.get("error"))
        return out

    result = out.get("result") or {}
    mid = result.get("message_id")
    drop.announce_message_id = int(mid) if mid else None
    drop.announced_at = datetime.utcnow()
    db.flush()
    return {"ok": True, "message_id": drop.announce_message_id, "ttl_seconds": ttl}


def delete_goblin_announce(db: Session, drop: GoblinDrop) -> dict[str, Any]:
    if not drop.announce_message_id or not drop.channel_id:
        return {"ok": True, "skipped": "no_message"}
    ch = db.query(Channel).filter(Channel.id == int(drop.channel_id)).first()
    if not ch:
        return {"ok": False, "error": "channel_not_found"}
    token_raw = resolve_bot_token_raw(db)
    if not token_raw:
        return {"ok": False, "error": "loot_bot_token_unset"}
    chat_id = normalize_telethon_peer_identifier(ch.identifier)
    payload = {
        "chat_id": chat_id,
        "message_id": int(drop.announce_message_id),
    }
    return _tg_post_with_token("deleteMessage", payload, token_raw)
