"""Collapse duplicate pool rows before Telegram album sends."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.media import Media


def dedupe_media_for_album(rows: list) -> list:
    """
    One slot per underlying Telegram file.

    Pools can index the same Saved Message or file more than once (legacy imports,
    thin-lane re-deposits). Album send loops resolve each row independently — without
    this pass, identical tiles appear in one media group.
    """
    seen_msg: set[int] = set()
    seen_fu: set[str] = set()
    seen_id: set[int] = set()
    out: list = []
    for m in rows:
        tid = int(getattr(m, "telegram_message_id", 0) or 0)
        fu = (getattr(m, "file_unique_id", None) or "").strip()
        if tid > 0:
            if tid in seen_msg:
                continue
            seen_msg.add(tid)
        if fu:
            if fu in seen_fu:
                continue
            seen_fu.add(fu)
        if tid <= 0 and not fu:
            mid = int(getattr(m, "id", 0) or 0)
            if mid in seen_id:
                continue
            seen_id.add(mid)
        out.append(m)
    return out


def select_unique_pool_media(rows: list, album_size: int, *, randomize: bool) -> list:
    """Return up to ``album_size`` unique media rows (may be fewer when pool is thin)."""
    import random as rnd

    lim = max(1, int(album_size or 1))
    unique = dedupe_media_for_album(list(rows))
    if randomize:
        rnd.shuffle(unique)
    return unique[:lim]


def mark_media_rows_posted(db, media_items: list) -> int:
    """Consume pool rows after a successful Telegram send (scheduler + pool paths)."""
    if not media_items:
        return 0
    n = 0
    for m in media_items:
        if (getattr(m, "status", None) or "").strip().lower() == "approved":
            m.status = "posted"
            n += 1
    if n:
        db.commit()
    return n
