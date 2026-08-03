"""Resolve Telegram media references for album sends (Saved Messages vs Storage Hub)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telethon import TelegramClient

    from app.models.media import Media


def media_fetch_peer_label(m: Media) -> str:
    """
    Return ``hub`` when ``telegram_message_id`` refers to Storage Hub messages,
    otherwise ``me`` (Saved Messages).
    """
    from app.services.storage_deposit_auto_approve import is_storage_hub_source_label

    if is_storage_hub_source_label(getattr(m, "source_channel", None)):
        return "hub"
    return "me"


async def fetch_album_medias(client: TelegramClient, media_items: list[Media]) -> list:
    """
    Build Telethon send_file media list in ``media_items`` order.

    Returns an empty list when any non-local item cannot be resolved (partial albums are skipped).
    """
    if not media_items:
        return []

    from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT
    from app.services.local_media_storage import is_local_pool_media, telethon_file_from_media
    from app.utils.telegram_peer import resolve_telethon_entity

    by_peer: dict[str, list[tuple[int, Media]]] = {"hub": [], "me": []}
    local_files: dict[int, object] = {}

    for idx, m in enumerate(media_items):
        if is_local_pool_media(m):
            f = telethon_file_from_media(m)
            if f is None:
                return []
            local_files[idx] = f
            continue
        tid = int(getattr(m, "telegram_message_id", 0) or 0)
        if tid <= 0:
            return []
        by_peer[media_fetch_peer_label(m)].append((idx, m))

    resolved: dict[int, object] = {}
    hub_entity = None
    for peer, pairs in by_peer.items():
        if not pairs:
            continue
        ids = [int(m.telegram_message_id) for _, m in pairs]
        if peer == "hub":
            if hub_entity is None:
                hub_entity = await resolve_telethon_entity(client, STORAGE_HUB_IDENT)
            messages = await client.get_messages(hub_entity, ids=ids)
        else:
            messages = await client.get_messages("me", ids=ids)
        if not isinstance(messages, list):
            messages = [messages]
        msg_map = {int(m.id): m for m in messages if m}
        for idx, m in pairs:
            msg = msg_map.get(int(m.telegram_message_id))
            if not msg or not getattr(msg, "media", None):
                return []
            resolved[idx] = msg.media

    medias: list = []
    for idx in range(len(media_items)):
        if idx in local_files:
            medias.append(local_files[idx])
        elif idx in resolved:
            medias.append(resolved[idx])
        else:
            return []
    return medias
