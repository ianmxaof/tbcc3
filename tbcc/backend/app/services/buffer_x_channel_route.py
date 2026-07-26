"""Route Buffer X mirrors to primary vs secondary X by Telegram channel.

Loot Room / default → TBCC_BUFFER_CHANNEL_ID_PRIMARY (e.g. wizardstick69).
AOF VIP → TBCC_BUFFER_CHANNEL_ID_X_SECONDARY (e.g. PowerCoreAi) when set.
Optional override map: TBCC_BUFFER_X_BY_TG_CHANNEL=-100aaa:bufId,-100bbb:bufId
"""

from __future__ import annotations

import os

from app.data.aof_network import AOF_VIP_IDENT


def buffer_x_secondary_channel_id() -> str | None:
    cid = (os.getenv("TBCC_BUFFER_CHANNEL_ID_X_SECONDARY") or "").strip()
    return cid or None


def _parse_tg_to_buffer_map() -> dict[str, str]:
    raw = (os.getenv("TBCC_BUFFER_X_BY_TG_CHANNEL") or "").strip()
    out: dict[str, str] = {}
    if not raw:
        return out
    for part in raw.replace(";", ",").split(","):
        piece = part.strip()
        if not piece or ":" not in piece:
            continue
        tg, buf = piece.split(":", 1)
        tg_id = tg.strip()
        buf_id = buf.strip()
        if tg_id and buf_id:
            out[tg_id] = buf_id
    return out


def buffer_x_channel_for_telegram_identifier(identifier: str | None) -> str | None:
    """Buffer twitter channel id for this Telegram channel (or primary default)."""
    from app.services.campaign_surface_copy import buffer_primary_channel_id

    primary = buffer_primary_channel_id()
    ident = (identifier or "").strip()
    mapped = _parse_tg_to_buffer_map()
    if ident and ident in mapped:
        return mapped[ident]
    secondary = buffer_x_secondary_channel_id()
    if ident == AOF_VIP_IDENT and secondary:
        return secondary
    return primary


def buffer_mirror_x_only_for_telegram_identifier(identifier: str | None) -> bool:
    """VIP secondary-X lane skips IG/Threads so the second X stays a clean promo lane."""
    ident = (identifier or "").strip()
    if not ident:
        return False
    if ident in _parse_tg_to_buffer_map():
        return True
    return ident == AOF_VIP_IDENT and bool(buffer_x_secondary_channel_id())
