"""Plan Telegram send groups for loot media (album aesthetics)."""

from __future__ import annotations

from typing import Any

TELEGRAM_ALBUM_MAX = 10


def _bucket(media_type: str | None) -> str:
    return "video" if (media_type or "").lower() == "video" else "photo"


def plan_media_send_groups(
    payloads: list[tuple[Any, bytes, str]],
) -> list[dict[str, Any]]:
    """
    payloads: list of (Media row, bytes, filename)

    Returns ordered send plans:
      { "bucket": "photo"|"video", "items": [...], "role": "hero"|"album"|"solo" }
    """
    if not payloads:
        return []

    photos = [p for p in payloads if _bucket(p[0].media_type) == "photo"]
    videos = [p for p in payloads if _bucket(p[0].media_type) == "video"]

    plans: list[dict[str, Any]] = []

    # Prefer: one photo album (grid), video(s) as hero bookends.
    if len(videos) == 1 and len(photos) >= 1:
        plans.append({"bucket": "video", "items": videos[:1], "role": "hero"})
        for i in range(0, len(photos), TELEGRAM_ALBUM_MAX):
            chunk = photos[i : i + TELEGRAM_ALBUM_MAX]
            plans.append({"bucket": "photo", "items": chunk, "role": "album"})
        return plans

    if len(photos) >= 2:
        for i in range(0, len(photos), TELEGRAM_ALBUM_MAX):
            chunk = photos[i : i + TELEGRAM_ALBUM_MAX]
            plans.append(
                {
                    "bucket": "photo",
                    "items": chunk,
                    "role": "album" if len(chunk) > 1 else "solo",
                }
            )
        for v in videos:
            plans.append({"bucket": "video", "items": [v], "role": "solo"})
        return plans

    # Fallback: contiguous same-type runs (legacy-safe)
    plans = []
    cur: list = []
    last: str | None = None
    for item in payloads:
        b = _bucket(item[0].media_type)
        if last is None or b == last:
            cur.append(item)
        else:
            if cur:
                plans.append(
                    {
                        "bucket": last,
                        "items": cur,
                        "role": "album" if len(cur) > 1 else "solo",
                    }
                )
            cur = [item]
        last = b
    if cur and last:
        plans.append(
            {
                "bucket": last,
                "items": cur,
                "role": "album" if len(cur) > 1 else "solo",
            }
        )
    return plans
