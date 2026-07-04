"""Resolve per-platform caption text for Buffer / Discord mirrors."""

from __future__ import annotations

import json
import os

from sqlalchemy.orm import Session

from app.models.scheduled_text_post import ScheduledTextPost
from app.services.buffer_x_caption import fit_plaintext_for_x
from app.services.scheduled_buffer_mirror import build_buffer_plaintext_from_post, build_buffer_x_mirror_text
from app.services.telegram_html_plain import telegram_html_to_plain


def _slot_index(post: ScheduledTextPost) -> int:
    vars_ = post.get_content_variations()
    n = len(vars_)
    if n >= 2:
        k = post.caption_rotation_index or 0
        return (k - 1) % n
    return 0


def get_surface_copy_raw(post: ScheduledTextPost) -> dict:
    if not getattr(post, "surface_copy_json", None):
        return {}
    try:
        raw = json.loads(post.surface_copy_json)
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def get_surface_copy_variations(post: ScheduledTextPost) -> list[dict]:
    raw = get_surface_copy_raw(post)
    items = raw.get("variations")
    if isinstance(items, list):
        return [x for x in items if isinstance(x, dict)]
    return []


def set_surface_copy(post: ScheduledTextPost, data: dict | None) -> None:
    if not data:
        post.surface_copy_json = None
        return
    post.surface_copy_json = json.dumps(data)


def resolve_surface_texts(post: ScheduledTextPost, db: Session) -> dict[str, str]:
    """
    Keys: x, ig_threads, discord, long (fallback for non-X Buffer channels).
    Falls back to Telegram-derived plain text when overrides unset.
    """
    slot = _slot_index(post)
    variations = get_surface_copy_variations(post)
    slot_map: dict = variations[slot] if slot < len(variations) else {}

    flat = get_surface_copy_raw(post)
    if not slot_map and any(k in flat for k in ("x", "ig_threads", "discord", "long")):
        slot_map = flat

    cap_html = (getattr(post, "last_sent_caption_html", None) or "").strip()
    if not cap_html:
        vars_ = post.get_content_variations()
        if vars_:
            cap_html = vars_[slot % len(vars_)]
        else:
            cap_html = post.content or ""

    telegram_plain = telegram_html_to_plain(cap_html, max_len=2200)
    full_mirror = build_buffer_plaintext_from_post(post, db)
    x_default = build_buffer_x_mirror_text(post, db) or fit_plaintext_for_x(telegram_plain)

    x = str(slot_map.get("x") or flat.get("x") or "").strip() or x_default
    ig = str(slot_map.get("ig_threads") or slot_map.get("long") or flat.get("ig_threads") or flat.get("long") or "").strip()
    if not ig:
        from app.services.buffer_surface_caption import build_instagram_caption

        ig = build_instagram_caption(teaser=telegram_plain, utm_campaign="scheduled_mirror")
    discord = str(slot_map.get("discord") or flat.get("discord") or "").strip()
    if not discord:
        from app.services.buffer_surface_caption import build_discord_caption

        discord = build_discord_caption(teaser=telegram_plain, utm_campaign="scheduled_mirror")

    if len(x) > 500:
        x = fit_plaintext_for_x(x)

    return {"x": x, "ig_threads": ig, "long": ig, "discord": discord[:2000]}


def buffer_primary_channel_id() -> str | None:
    cid = (os.environ.get("TBCC_BUFFER_CHANNEL_ID_PRIMARY") or "").strip()
    return cid or None


def buffer_secondary_channel_ids() -> list[str]:
    from app.services.buffer_graphql import buffer_target_channel_ids

    primary = buffer_primary_channel_id()
    all_ids = buffer_target_channel_ids()
    return [c for c in all_ids if c != primary]
