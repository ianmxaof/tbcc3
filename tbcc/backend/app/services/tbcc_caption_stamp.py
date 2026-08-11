"""Operator-visible #tbcc:* caption tags — AyuGram filters + gatekeeper lane hints."""

from __future__ import annotations

import re

from app.services.aof_lane_tag_map import normalize_lane_key

TBCC_TAG_PREFIX = "#tbcc:"
_TBCC_LANE_RE = re.compile(r"#tbcc:([\w]+)", re.IGNORECASE)
_QUARANTINE_TAG = f"{TBCC_TAG_PREFIX}quarantine"


def tbcc_lane_tag(network_key: str | None) -> str:
    key = normalize_lane_key(network_key)
    if not key:
        return ""
    return f"{TBCC_TAG_PREFIX}{key}"


def tbcc_quarantine_tag() -> str:
    return _QUARANTINE_TAG


def parse_tbcc_lane_from_caption(caption: str | None) -> str | None:
    """Read canonical lane key from ``#tbcc:big_tits`` in caption text."""
    m = _TBCC_LANE_RE.search(caption or "")
    if not m:
        return None
    raw = (m.group(1) or "").strip().lower()
    if raw == "quarantine":
        return None
    return normalize_lane_key(raw)


def append_tbcc_tags(caption: str | None, *tags: str) -> str:
    """Append unique ``#tbcc:*`` tags (skip duplicates already present)."""
    base = (caption or "").strip()
    existing = {m.group(0).lower() for m in _TBCC_LANE_RE.finditer(base)}
    to_add: list[str] = []
    for tag in tags:
        t = (tag or "").strip()
        if not t.startswith(TBCC_TAG_PREFIX):
            continue
        if t.lower() in existing:
            continue
        to_add.append(t)
        existing.add(t.lower())
    if not to_add:
        return base
    suffix = " ".join(to_add)
    return f"{base} {suffix}".strip() if base else suffix


def hub_intake_caption(network_key: str | None, existing: str | None = None) -> str:
    """Caption for media landing in a Storage Hub topic (extension / album intake)."""
    tag = tbcc_lane_tag(network_key)
    return append_tbcc_tags(existing, tag) if tag else (existing or "").strip()


def quarantine_review_caption_suffix(*, lane_key: str | None = None) -> str:
    """Plain-text footer for quarantine review cards (HTML body may include these tags)."""
    tags = [tbcc_quarantine_tag()]
    lane_tag = tbcc_lane_tag(lane_key)
    if lane_tag:
        tags.append(lane_tag)
    return " ".join(tags)


def merge_quarantine_review_html(html_body: str, *, lane_key: str | None = None) -> str:
    body = (html_body or "").rstrip()
    suffix = quarantine_review_caption_suffix(lane_key=lane_key)
    if not suffix:
        return body
    if suffix.lower() in body.lower():
        return body
    return f"{body}\n{suffix}"
