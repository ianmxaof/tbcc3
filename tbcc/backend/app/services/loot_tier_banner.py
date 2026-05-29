"""Tier header: custom emoji preset (source_note loot_tier:N) or HTML fallback."""

from __future__ import annotations

import html
from typing import Any

from sqlalchemy.orm import Session

from app.models.custom_emoji_preset import CustomEmojiPreset
from app.services.loot_tier_catalog import tier_display_name, tier_meta
from app.services.telegram_custom_emoji import telethon_message_kwargs


def _preset_banner_html(db: Session, tier: int) -> str | None:
    note = f"loot_tier:{int(tier)}"
    row = (
        db.query(CustomEmojiPreset)
        .filter(CustomEmojiPreset.source_note == note)
        .order_by(CustomEmojiPreset.id.desc())
        .first()
    )
    if row and (row.html_fragment or "").strip():
        return row.html_fragment.strip()
    return None


def build_tier_opening_html(db: Session, preview: dict[str, Any]) -> str:
    """Opening message: custom emoji banner + tier name line."""
    tier = int(preview.get("rarity_tier") or 1)
    preset = _preset_banner_html(db, tier)
    meta = tier_meta(tier)
    title = html.escape(tier_display_name(tier))
    tag = html.escape(meta["tagline"])
    if preset:
        return f"{preset}\n\n<b>{title}</b>\n<i>{tag}</i>"
    # Tier 1 dull, tier 10 loud — until presets are wired per tier
    if tier <= 2:
        lead = "▫️"
    elif tier <= 5:
        lead = "✨"
    elif tier <= 8:
        lead = "💎"
    else:
        lead = "🎆🔥🎆"
    return f"{lead} <b>{title}</b>\n<i>{tag}</i>"


def build_tier_flavor_html(preview: dict[str, Any]) -> str:
    flavor = (preview.get("tier_flavor") or tier_meta(int(preview.get("rarity_tier") or 1))["flavor"]).strip()
    return html.escape(flavor)


def telethon_kwargs_for_tier_html(db: Session, preview: dict[str, Any]) -> dict[str, Any]:
    """If opening uses tg-emoji tags, return Telethon kwargs; else HTML parse_mode."""
    raw = build_tier_opening_html(db, preview)
    kw = telethon_message_kwargs(raw)
    if kw.get("formatting_entities"):
        return kw
    return {"message": raw, "parse_mode": "html"}
