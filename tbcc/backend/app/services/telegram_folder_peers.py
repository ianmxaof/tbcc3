"""Read Telegram chat folders (Dialog Filters) via Telethon — for SCRP batch ingest."""

from __future__ import annotations

import logging
from typing import Any

from telethon.utils import get_peer_id

logger = logging.getLogger(__name__)


async def list_telegram_folders(client) -> list[dict[str, Any]]:
    """
    Return Telegram folders with resolved peer ids and titles.
    Requires the logged-in account to have configured folders in Telegram clients.
    """
    from telethon.tl.functions.messages import GetDialogFiltersRequest
    from telethon.tl.types import DialogFilter, DialogFilterDefault

    result = await client(GetDialogFiltersRequest())
    out: list[dict[str, Any]] = []
    for f in result.filters or []:
        if isinstance(f, DialogFilterDefault):
            continue
        if not isinstance(f, DialogFilter):
            continue
        title_raw = f.title
        title = getattr(title_raw, "text", None) or str(title_raw or "").strip()
        peers: list[dict[str, Any]] = []
        for peer in f.include_peers or []:
            try:
                ent = await client.get_entity(peer)
                pid = int(get_peer_id(ent))
                peers.append(
                    {
                        "chat_id": pid,
                        "title": getattr(ent, "title", None)
                        or getattr(ent, "username", None)
                        or str(pid),
                        "username": getattr(ent, "username", None),
                    }
                )
            except Exception as e:
                logger.debug("folder peer resolve failed: %s", e)
        out.append({"folder_id": int(f.id), "title": title, "peers": peers, "peer_count": len(peers)})
    return out


async def peers_for_folder_title(client, *, title_contains: str) -> list[dict[str, Any]]:
    """Peers in the first folder whose title contains ``title_contains`` (case-insensitive)."""
    needle = (title_contains or "").strip().lower()
    if not needle:
        return []
    for folder in await list_telegram_folders(client):
        if needle in (folder.get("title") or "").lower():
            return list(folder.get("peers") or [])
    return []
