"""AOF archive first, macro SEO fallback — routing helpers."""

from __future__ import annotations

import os
import re

_USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{2,64}$")


def macro_search_aof_first_enabled() -> bool:
    return (os.getenv("TBCC_MACRO_SEARCH_AOF_FIRST") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def normalize_macro_username(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("@"):
        s = s[1:]
    s = re.sub(r"^[^\w]+|[^\w.-]+$", "", s)
    if not _USERNAME_RE.fullmatch(s or ""):
        return ""
    return s


def macro_fallback_username(query: str) -> str:
    """Pick a model username for external macro SEO when archive search misses."""
    raw = (query or "").strip()
    if not raw:
        return ""
    direct = normalize_macro_username(raw)
    if direct:
        return direct
    for part in raw.split():
        hit = normalize_macro_username(part)
        if hit:
            return hit
    return ""


def pick_best_search_surface(access: dict) -> str:
    allowed = list(access.get("allowed_surfaces") or ["loot_room"])
    if "vip" in allowed:
        return "vip"
    if "library" in allowed:
        return "library"
    return str(allowed[0] if allowed else "loot_room")
