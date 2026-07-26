"""Conditional X hashtags for Buffer captions (Erome only when URL present)."""

from __future__ import annotations

import re

_EROME_RE = re.compile(r"erome\.com", re.I)
_LANE_RE = re.compile(
    r"\bAOF\s+([A-Z][A-Z0-9 /]+?)(?:\s*[—\-·|]|\s+lane|\s+pool|$)",
    re.I,
)


def text_has_erome_link(text: str) -> bool:
    return bool(_EROME_RE.search(text or ""))


def infer_lane_slug(text: str) -> str | None:
    """Best-effort lane tag from caption (e.g. 'AOF BIG TITS' → bigtits)."""
    m = _LANE_RE.search(text or "")
    if not m:
        return None
    slug = re.sub(r"[^a-z0-9]", "", m.group(1).lower())
    if len(slug) < 3 or slug in ("nsfw", "telegram", "erome", "loot", "vip"):
        return None
    return slug[:24]


def build_x_hashtag_suffix(
    text: str,
    *,
    lane: str | None = None,
    max_tags: int = 3,
) -> str:
    """
    2–3 tags max. #erome only when erome.com appears in the caption.
    """
    tags: list[str] = []
    if text_has_erome_link(text):
        tags.append("#erome")
    slug = None
    if lane:
        slug = re.sub(r"[^a-z0-9]", "", lane.lower().replace("aof ", ""))
    if not slug:
        slug = infer_lane_slug(text)
    if slug and len(slug) >= 3 and slug not in ("nsfw", "telegram", "erome"):
        tags.append(f"#{slug}")
    if len(tags) < max_tags:
        tags.append("#nsfw")
    return " ".join(tags[:max_tags])


def append_x_hashtags(
    text: str,
    *,
    lane: str | None = None,
    max_chars: int = 280,
    max_tags: int = 3,
) -> str:
    """Append hashtag suffix without exceeding max_chars."""
    body = (text or "").strip()
    if not body:
        return body
    suffix = build_x_hashtag_suffix(body, lane=lane, max_tags=max_tags)
    if not suffix:
        return body
    tag_part = f" {suffix}"
    if len(body) + len(tag_part) <= max_chars:
        return f"{body}{tag_part}"
    room = max_chars - len(tag_part) - 1
    if room < 20:
        return body[: max_chars - 1].rstrip() + "…"
    trimmed = body[:room].rstrip()
    if " " in trimmed:
        trimmed = trimmed.rsplit(" ", 1)[0].rstrip()
    return f"{trimmed}…{tag_part}"
