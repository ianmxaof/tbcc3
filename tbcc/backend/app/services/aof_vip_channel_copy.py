"""VIP channel copy — media-first pacing, no links-hub walls, lane button tree."""

from __future__ import annotations

import os
import re
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_network import ADDLIST_RAW, BULLETIN_MARKER, network_channel_by_key
from app.services.aof_growth_hub import FOOTER_MARKER, _is_bulletin_variation

VIP_PACING_ADMONITION = (
    "⭐ <b>VIP</b> — paid lane drop. Ad-free files · bigger batches.\n"
    "<i>Map &amp; tools live on the buttons — feed stays media-first.</i>"
)

_SECTION_CUT_MARKERS = (
    "━━━━━━━━━━━━━━━━━━",
    "📂 <b>CONTENT</b>",
    "🧠 <b>AI TOOLS</b>",
    "🤝 <b>PARTNERS</b>",
    "🤖 <b>OFFICIAL BOTS</b>",
    "🚀 <b>SUPPORT AOF</b>",
    "🔥 <b>ENTRY</b>",
)


def vip_navigation_buttons_enabled() -> bool:
    raw = (os.getenv("TBCC_VIP_NAV_BUTTONS") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def vip_skip_bulletin_mirror() -> bool:
    raw = (os.getenv("TBCC_VIP_SKIP_BULLETIN_MIRROR") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _strip_from_marker(body: str, marker: str) -> str:
    idx = body.find(marker)
    if idx < 0:
        return body
    return body[:idx].strip()


def strip_vip_affiliate_blocks(html: str) -> str:
    """Remove links-hub walls, sponsor footers, and directory sections."""
    body = (html or "").strip()
    if not body:
        return ""
    if _is_bulletin_variation(body) or BULLETIN_MARKER in body:
        return ""
    body = _strip_from_marker(body, f"📌 <b>{FOOTER_MARKER}</b>")
    body = _strip_from_marker(body, FOOTER_MARKER)
    for marker in _SECTION_CUT_MARKERS:
        body = _strip_from_marker(body, marker)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body


def pick_vip_mirror_caption(post: Any, db: Session) -> str:
    """Prefer lane promo copy; never mirror the full links-hub bulletin to VIP."""
    vars_ = []
    try:
        vars_ = list(post.get_content_variations() or [])
    except Exception:
        vars_ = []
    if not vars_ and getattr(post, "content", None):
        vars_ = [post.content]

    candidates: list[str] = []
    if vars_:
        idx = int(getattr(post, "caption_rotation_index", 0) or 0) % len(vars_)
        ordered = [vars_[idx]] + [v for i, v in enumerate(vars_) if i != idx]
        for cap in ordered:
            cleaned = strip_vip_affiliate_blocks(str(cap or ""))
            if cleaned:
                candidates.append(cleaned)
    else:
        cleaned = strip_vip_affiliate_blocks(str(getattr(post, "content", "") or ""))
        if cleaned:
            candidates.append(cleaned)

    if candidates:
        return candidates[0]
    return VIP_PACING_ADMONITION


def scrub_caption_for_vip_mirror(html: str, db: Session) -> str:
    from app.services.aof_vip_mirror import VIP_CAPTION_BADGE, transform_caption_for_vip

    body = strip_vip_affiliate_blocks(html)
    if not body:
        body = VIP_PACING_ADMONITION
    out = transform_caption_for_vip(body, db)
    if VIP_CAPTION_BADGE.split("·")[0].strip() not in out and body != VIP_PACING_ADMONITION:
        return out
    if body == VIP_PACING_ADMONITION:
        return body
    return out


def build_vip_navigation_buttons(db: Session) -> list[list[dict[str, str]]]:
    """Compact lane map — 2-wide rows + addlist (VIP subscribers already converted)."""
    if not vip_navigation_buttons_enabled():
        return []
    from app.services.aof_growth_hub import lv_urls

    lv = lv_urls(db)
    lane_keys = ("big_tits", "ass", "blowjob", "milf", "packs", "goon")
    row: list[dict[str, str]] = []
    rows: list[list[dict[str, str]]] = []
    for key in lane_keys:
        net = network_channel_by_key(key)
        if not net:
            continue
        url = (lv.get(key) or net.invite or "").strip()
        if not url.startswith("http"):
            continue
        label = net.display_name.replace("AOF ", "").strip()[:32]
        row.append({"text": label, "url": url[:512]})
        if len(row) >= 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    addlist = (lv.get("addlist") or ADDLIST_RAW).strip()
    if addlist.startswith("http"):
        rows.append([{"text": "📌 All lanes", "url": addlist[:512]}])
    return rows


def merge_vip_mirror_buttons(
    base_buttons: list[dict] | None,
    db: Session,
) -> list | None:
    """Flat URL buttons + optional 2-wide navigation tree for VIP mirror sends."""
    from app.services.aof_vip_mirror import transform_buttons_for_vip

    flat = transform_buttons_for_vip(base_buttons or [], db)
    nav = build_vip_navigation_buttons(db)
    if not flat and not nav:
        return None
    if not nav:
        return flat or None
    if not flat:
        return nav
    return [flat[i : i + 2] for i in range(0, len(flat), 2)] + nav
