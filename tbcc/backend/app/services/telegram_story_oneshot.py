"""Flood-safe one-shot Telegram user story (Track I Week 1).

Do not loop or schedule a story beat from here. One send, then stop.
Copied session files share one auth key — use the account lock.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

STORY_BEACON_DEFAULT = "https://api.powercore.app/r/story-loot-free"
LOOT_FREE_FALLBACK = "https://telegram.me/aof_lootgod_bot?start=loot_free"


def flood_wait_seconds(exc: BaseException) -> int | None:
    """Extract FloodWait seconds from Telethon FloodWaitError (or lookalike)."""
    name = type(exc).__name__
    if "FloodWait" not in name:
        return None
    seconds = getattr(exc, "seconds", None)
    if seconds is None:
        return None
    try:
        return max(0, int(seconds))
    except (TypeError, ValueError):
        return None


def story_link_area(*, beacon_url: str | None = None) -> str:
    """Single URL on the story: beacon → loot_free, never LV."""
    return (beacon_url or STORY_BEACON_DEFAULT).strip() or LOOT_FREE_FALLBACK


def account_lock_is_shared() -> bool:
    """Copied admin_poster / admin_import / admin_album = one flood pool."""
    from app.services.telethon_session_lock import telegram_account_lock_enabled

    return telegram_account_lock_enabled()


def identity_cadence_note(*, lock_contended: bool) -> str:
    if lock_contended or account_lock_is_shared():
        return "cadence=1/day total (same auth key / account lock)"
    return "cadence=per distinct phone"


async def can_send_story_dry(client: Any) -> dict[str, Any]:
    """Probe CanSendStory; never posts."""
    try:
        from telethon.tl.functions.stories import CanSendStoryRequest
        from telethon.tl.types import InputPeerSelf
    except Exception as e:
        return {"ok": False, "error": f"telethon_import:{e}"}
    try:
        result = await client(CanSendStoryRequest(peer=InputPeerSelf()))
        return {"ok": True, "can_send": bool(result), "raw": str(result)[:200]}
    except Exception as e:
        wait = flood_wait_seconds(e)
        if wait is not None:
            logger.error("story canSendStory FloodWait seconds=%s — stop", wait)
            return {"ok": False, "flood_wait": wait, "stop": True, "alert": True}
        return {"ok": False, "error": str(e)[:400]}


async def send_user_story_oneshot(
    client: Any,
    *,
    file_path: str,
    caption: str,
    beacon_url: str | None = None,
) -> dict[str, Any]:
    """Send exactly one user story, catch flood, stop and alert. No retry loop."""
    link = story_link_area(beacon_url=beacon_url)
    try:
        from telethon.tl.functions.stories import SendStoryRequest
        from telethon.tl.types import InputPeerSelf, TextWithEntities
    except Exception as e:
        return {"ok": False, "error": f"telethon_import:{e}"}

    try:
        uploaded = await client.upload_file(file_path)
        media = await client._file_to_media(uploaded)
        text = f"{caption}\n{link}".strip()
        await client(
            SendStoryRequest(
                peer=InputPeerSelf(),
                media=media,
                caption=TextWithEntities(text=text, entities=[]) if hasattr(TextWithEntities, "__call__") else text,
            )
        )
        return {"ok": True, "link": link, "cadence": identity_cadence_note(lock_contended=False)}
    except TypeError:
        # Telethon versions differ on SendStoryRequest fields — fail closed, no flood retry.
        return {"ok": False, "error": "send_story_api_mismatch", "hint": "run --dry-run canSendStory"}
    except Exception as e:
        wait = flood_wait_seconds(e)
        if wait is not None:
            logger.error("story send FloodWait seconds=%s — stop and alert, no retry", wait)
            return {
                "ok": False,
                "flood_wait": wait,
                "stop": True,
                "alert": True,
                "cadence": identity_cadence_note(lock_contended=True),
            }
        return {"ok": False, "error": str(e)[:400]}
