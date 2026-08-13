"""Loot Room growth menu — pinned interactive board (bare invite + 18+ in caption)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_network import MAIN_GROUP_IDENT, MAIN_GROUP_INVITE

LOOT_ROOM_GROWTH_MENU_SCHED_NAME = "AOF LOOT ROOM — growth menu (pinned)"


def loot_room_growth_menu_report(db: Session) -> dict[str, Any]:
    """Status helper for growth hub — menu is deployed via deploy_loot_room_link_menu.py."""
    from app.models.channel import Channel

    ch = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()
    return {
        "loot_room_channel_id": ch.id if ch else None,
        "bare_invite": MAIN_GROUP_INVITE,
        "deploy_script": "scripts/deploy_loot_room_link_menu.py",
        "variants": ("v5", "v6", "v7"),
        "pinned": True,
    }
