"""Plan Telegram send groups for loot media (album aesthetics)."""

from __future__ import annotations

from typing import Any

TELEGRAM_ALBUM_MAX = 10


def _bucket(media_type: str | None) -> str:
    return "video" if (media_type or "").lower() == "video" else "photo"


def plan_loot_roll_albums(
    payloads: list[tuple[Any, bytes, str]],
) -> list[dict[str, Any]]:
    """
    Minimal album count: chunk in order up to 10 items per sendMediaGroup.
    Mixed photo+video in the same album (Telegram supports this).
    """
    if not payloads:
        return []
    plans: list[dict[str, Any]] = []
    for i in range(0, len(payloads), TELEGRAM_ALBUM_MAX):
        chunk = payloads[i : i + TELEGRAM_ALBUM_MAX]
        plans.append({"items": chunk, "mixed": True, "role": "album" if len(chunk) > 1 else "solo"})
    return plans


def plan_media_send_groups(
    payloads: list[tuple[Any, bytes, str]],
) -> list[dict[str, Any]]:
    """Legacy planner — loot delivery uses plan_loot_roll_albums instead."""
    return plan_loot_roll_albums(payloads)
