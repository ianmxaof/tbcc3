"""Model / creator OnlyFans links → active loot modifier pool entries."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.loot import LootModifier

_OF_HOSTS = ("onlyfans.com", "www.onlyfans.com")
_HANDLE_RE = re.compile(r"^[a-zA-Z0-9._-]{2,64}$")


def normalize_onlyfans_url(raw: str) -> str | None:
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
    if host not in _OF_HOSTS:
        return None
    path = (p.path or "").strip("/")
    if path and not _HANDLE_RE.match(path.split("/")[0]):
        return None
    return f"https://onlyfans.com/{path.split('/')[0]}" if path else "https://onlyfans.com/"


def label_from_onlyfans_url(url: str, handle_hint: str | None = None) -> str:
    if handle_hint and _HANDLE_RE.match(handle_hint.strip()):
        return f"OF · {handle_hint.strip()[:48]}"
    try:
        handle = urlparse(url).path.strip("/").split("/")[0]
        if handle:
            return f"OF · {handle[:48]}"
    except Exception:
        pass
    return "Creator promo"


def submit_creator_profile(
    db: Session,
    *,
    url: str,
    telegram_user_id: int | None = None,
    handle: str | None = None,
) -> dict:
    """
    Auto-approve: immediately add an active modifier (rolls on mid+ tiers).
    """
    normalized = normalize_onlyfans_url(url)
    if not normalized:
        raise ValueError("URL must be a valid OnlyFans profile link (https://onlyfans.com/handle)")

    label = label_from_onlyfans_url(normalized, handle)
    note = "creator:self-serve"
    if telegram_user_id:
        note = f"creator:tg:{int(telegram_user_id)}"

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
        "message": "Profile added to the loot modifier pool — eligible on tier 5+ rolls.",
    }
