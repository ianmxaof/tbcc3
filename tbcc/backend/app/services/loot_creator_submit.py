"""Creator profile links → active loot modifier pool entries (self-serve)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.loot import LootModifier

_HANDLE_RE = re.compile(r"^[a-zA-Z0-9._-]{2,64}$")

# host suffix → (label prefix, canonical host for URL rebuild)
_CREATOR_PLATFORMS: dict[str, tuple[str, str]] = {
    "onlyfans.com": ("OF", "onlyfans.com"),
    "www.onlyfans.com": ("OF", "onlyfans.com"),
    "fansly.com": ("Fansly", "fansly.com"),
    "www.fansly.com": ("Fansly", "fansly.com"),
    "manyvids.com": ("MV", "manyvids.com"),
    "www.manyvids.com": ("MV", "manyvids.com"),
    "linktr.ee": ("Link", "linktr.ee"),
    "www.linktr.ee": ("Link", "linktr.ee"),
    "linktree.com": ("Link", "linktree.com"),
    "www.linktree.com": ("Link", "linktree.com"),
    "boosty.to": ("Boosty", "boosty.to"),
    "www.boosty.to": ("Boosty", "boosty.to"),
}

_CREATOR_RATE_LIMIT_PER_DAY = 3
_CREATOR_MAX_ACTIVE_PER_USER = 5


def _first_path_segment(path: str) -> str | None:
    seg = (path or "").strip("/").split("/")[0].strip()
    if not seg or not _HANDLE_RE.match(seg):
        return None
    return seg


def normalize_creator_url(raw: str) -> tuple[str, str, str] | None:
    """
    Return (normalized_url, platform_prefix, handle) or None if invalid.
    Accepts OnlyFans, Fansly, ManyVids, Linktree, Boosty profile links.
    """
    s = (raw or "").strip()
    if not s:
        return None
    if not s.startswith(("http://", "https://")):
        s = "https://" + s.lstrip("/")
    try:
        p = urlparse(s)
    except Exception:
        return None
    host = (p.hostname or "").lower()
    plat = _CREATOR_PLATFORMS.get(host)
    if not plat:
        return None
    prefix, canon_host = plat
    handle = _first_path_segment(p.path or "")
    if not handle:
        return None
    normalized = f"https://{canon_host}/{handle}"
    return normalized, prefix, handle


def label_from_creator_url(prefix: str, handle: str, handle_hint: str | None = None) -> str:
    h = (handle_hint or handle or "").strip()
    if h and _HANDLE_RE.match(h):
        return f"{prefix} · {h[:48]}"
    return "Creator promo"


def _creator_source_note(telegram_user_id: int | None) -> str:
    if telegram_user_id:
        return f"creator:tg:{int(telegram_user_id)}"
    return "creator:self-serve"


def _count_recent_creator_submits(db: Session, telegram_user_id: int) -> int:
    since = datetime.utcnow() - timedelta(hours=24)
    note = f"creator:tg:{int(telegram_user_id)}"
    return (
        db.query(LootModifier)
        .filter(
            LootModifier.source_note.like(f"{note}%"),
            LootModifier.created_at >= since,
        )
        .count()
    )


def _count_active_creator_mods(db: Session, telegram_user_id: int) -> int:
    note = f"creator:tg:{int(telegram_user_id)}"
    return (
        db.query(LootModifier)
        .filter(
            LootModifier.source_note.like(f"{note}%"),
            LootModifier.active.is_(True),
        )
        .count()
    )


def submit_creator_profile(
    db: Session,
    *,
    url: str,
    telegram_user_id: int | None = None,
    handle: str | None = None,
) -> dict:
    """
    Auto-approve: add an active modifier (rolls on tier 5+).
    Dedupes identical URLs; rate-limits submissions per Telegram user.
    """
    parsed = normalize_creator_url(url)
    if not parsed:
        raise ValueError(
            "Send a public profile link — OnlyFans, Fansly, ManyVids, Linktree, or Boosty "
            "(https://platform.com/yourhandle)."
        )

    normalized, prefix, path_handle = parsed
    if telegram_user_id:
        uid = int(telegram_user_id)
        if _count_recent_creator_submits(db, uid) >= _CREATOR_RATE_LIMIT_PER_DAY:
            raise ValueError(
                f"Rate limit: max {_CREATOR_RATE_LIMIT_PER_DAY} creator promos per 24 hours on this account."
            )
        if _count_active_creator_mods(db, uid) >= _CREATOR_MAX_ACTIVE_PER_USER:
            raise ValueError(
                f"You already have {_CREATOR_MAX_ACTIVE_PER_USER} active promos. "
                "Ask admin to retire an old one before adding more."
            )

    existing = (
        db.query(LootModifier)
        .filter(
            LootModifier.target_url == normalized,
            LootModifier.active.is_(True),
        )
        .first()
    )
    if existing:
        if telegram_user_id and f"creator:tg:{int(telegram_user_id)}" in (existing.source_note or ""):
            return {
                "ok": True,
                "already_registered": True,
                "modifier_id": int(existing.id),
                "label": existing.label,
                "target_url": existing.target_url,
                "message": "That link is already in your active promo pool.",
            }
        raise ValueError("That profile link is already in the loot modifier pool.")

    label = label_from_creator_url(prefix, path_handle, handle)
    note = _creator_source_note(telegram_user_id)

    m = LootModifier(
        kind="internal_route",
        label=label,
        target_url=normalized,
        weight_base=1.0,
        rarity_focus=5.0,
        min_rarity_tier=5,
        bypass_vip=False,
        active=True,
        source_note=note,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return {
        "ok": True,
        "modifier_id": int(m.id),
        "label": m.label,
        "target_url": m.target_url,
        "message": "Accepted — your link is live in the modifier pool on tier 5+ rolls.",
    }
