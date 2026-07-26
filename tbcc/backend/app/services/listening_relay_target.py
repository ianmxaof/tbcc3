"""Resolve listening-relay Telegram destination (fixed channel, random AOF lane, loot topics, VIP)."""

from __future__ import annotations

import logging
import random
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_main_group_topic_map import (
    AOF_MAIN_GROUP_TOPIC_MAP,
    MAIN_GROUP_GENERAL_TOPIC_ID,
    MAIN_GROUP_GENERAL_TOPIC_TITLE,
)
from app.data.aof_network import AOF_NETWORK_CHANNELS, AOF_VIP_IDENT, MAIN_GROUP_IDENT
from app.models.channel import Channel
from app.models.listening_relay_settings import ListeningRelaySettings

logger = logging.getLogger(__name__)


def aof_network_channel_rows(db: Session) -> list[Channel]:
    """TBCC Channel rows whose identifier is on the AOF network map."""
    idents = {ch.identifier for ch in AOF_NETWORK_CHANNELS}
    if not idents:
        return []
    return db.query(Channel).filter(Channel.identifier.in_(idents)).all()


def aof_network_channel_ids(db: Session) -> list[int]:
    return [int(r.id) for r in aof_network_channel_rows(db)]


def channel_id_for_identifier(db: Session, identifier: str) -> int | None:
    ident = (identifier or "").strip()
    if not ident:
        return None
    row = db.query(Channel).filter(Channel.identifier == ident).first()
    return int(row.id) if row else None


def pick_random_aof_network_channel_id(db: Session) -> int | None:
    ids = aof_network_channel_ids(db)
    if not ids:
        return None
    return int(random.choice(ids))


def loot_room_topics_for_api() -> list[dict[str, Any]]:
    """Static loot-room forum topics for dashboard (live sync may extend via channels API)."""
    out: list[dict[str, Any]] = [
        {
            "id": MAIN_GROUP_GENERAL_TOPIC_ID,
            "title": MAIN_GROUP_GENERAL_TOPIC_TITLE,
        }
    ]
    seen = {MAIN_GROUP_GENERAL_TOPIC_ID}
    for row in AOF_MAIN_GROUP_TOPIC_MAP:
        if row.message_thread_id in seen:
            continue
        seen.add(row.message_thread_id)
        out.append({"id": int(row.message_thread_id), "title": row.topic_title})
    return out


def relay_destinations_for_api(db: Session) -> dict[str, Any]:
    loot_id = channel_id_for_identifier(db, MAIN_GROUP_IDENT)
    vip_id = channel_id_for_identifier(db, AOF_VIP_IDENT)
    loot_row = db.query(Channel).filter(Channel.id == loot_id).first() if loot_id else None
    vip_row = db.query(Channel).filter(Channel.id == vip_id).first() if vip_id else None
    return {
        "loot_room": {
            "channel_id": loot_id,
            "identifier": MAIN_GROUP_IDENT,
            "name": (loot_row.name if loot_row else None) or "AOF LOOT ROOM",
            "topics": loot_room_topics_for_api(),
        },
        "vip": {
            "channel_id": vip_id,
            "identifier": AOF_VIP_IDENT,
            "name": (vip_row.name if vip_row else None) or "AOF VIP",
        },
        "network_channel_count": len(aof_network_channel_ids(db)),
    }


def relay_random_network_enabled(row: ListeningRelaySettings) -> bool:
    return bool(getattr(row, "relay_random_network_channel", False))


def resolve_listening_relay_send_target(
    db: Session,
    row: ListeningRelaySettings,
) -> tuple[int | None, int | None]:
    """
    Return (channel_id, message_thread_id) for one relay send.
    Random-network mode picks a new lane each call; fixed channel + thread otherwise.
    """
    if relay_random_network_enabled(row):
        picked = pick_random_aof_network_channel_id(db)
        if not picked:
            logger.warning("listening relay: random network enabled but no AOF channels in DB")
            return None, None
        return picked, None

    channel_id = int(row.channel_id) if row.channel_id else None
    thread_id = int(row.message_thread_id) if row.message_thread_id else None
    return channel_id, thread_id


def relay_has_send_target(row: ListeningRelaySettings) -> bool:
    if relay_random_network_enabled(row):
        return True
    return bool(row.channel_id)
