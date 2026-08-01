"""Mirror network + packs posts into AOF VIP — early timing, ad-free links, larger albums."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from sqlalchemy.orm import Session
from telethon import TelegramClient

from app.data.aof_network import AOF_NETWORK_CHANNELS, AOF_VIP_IDENT
from app.models.channel import Channel
from app.models.content_pool import ContentPool
from app.services.aof_vip_pool import PACKS_POOL_NAME, is_vip_mirror_pool, vip_mirror_pool_names
from app.services.link_gate_provider import is_gate_host

logger = logging.getLogger(__name__)

VIP_CAPTION_BADGE = "⭐ <b>VIP</b> · ad-free · early"


def vip_mirror_enabled() -> bool:
    raw = (os.getenv("TBCC_AOF_VIP_MIRROR_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def vip_album_size(*, pool_id: int | None = None) -> int:
    from app.services.aof_feed_rhythm_v2 import resolve_vip_album_size

    return resolve_vip_album_size(pool_id=pool_id)


def vip_strip_checkout_on_mirror() -> bool:
    raw = (os.getenv("TBCC_AOF_VIP_STRIP_CHECKOUT_BUTTONS") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _network_channel_ids(db: Session) -> set[int]:
    idents = {ch.identifier for ch in AOF_NETWORK_CHANNELS}
    rows = db.query(Channel).filter(Channel.identifier.in_(idents)).all()
    return {int(r.id) for r in rows}


def should_mirror_scheduled_post(db: Session, post, channel) -> bool:
    if not vip_mirror_enabled():
        return False
    if not post or not channel:
        return False
    if str(getattr(channel, "identifier", "")) == AOF_VIP_IDENT:
        return False
    if int(getattr(post, "channel_id", 0) or 0) not in _network_channel_ids(db):
        # Packs seed scheduler lives on packs channel
        name = (getattr(post, "name", None) or "").lower()
        if "packs" not in name and getattr(post, "pool_id", None):
            pool = db.query(ContentPool).filter(ContentPool.id == post.pool_id).first()
            if not pool or str(pool.name) not in vip_mirror_pool_names():
                return False
        elif "packs" not in name:
            return False
    return True


def _gate_url_re() -> re.Pattern[str]:
    return re.compile(r'https?://[^\s<>"\']+', re.I)


def _is_gate_url(url: str) -> bool:
    u = (url or "").strip()
    if not u.startswith("http"):
        return False
    if is_gate_host(u):
        return True
    from app.services.link_gate_provider import is_linkvertise_host

    return is_linkvertise_host(u)


def vip_gate_live_resolve_enabled() -> bool:
    """
    Live bypass.vip / redirect chain during Telegram send.
    Off by default — resolve_to_file_host can take minutes per caption and holds the poster session lock.
  """
    raw = (os.getenv("TBCC_VIP_GATE_LIVE_RESOLVE") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def direct_url_for_gate(db: Session, gate_url: str) -> str | None:
    """Best-effort: map LV/gate button URL → direct file host for VIP subscribers."""
    from app.models.loot import LootModifier
    from app.services.k2s_vip_access import resolve_k2s_vip_download_url

    gate = (gate_url or "").strip().split()[0]
    if not gate:
        return None
    mod = (
        db.query(LootModifier)
        .filter(LootModifier.target_url == gate, LootModifier.active.is_(True))
        .order_by(LootModifier.id.desc())
        .first()
    )
    if mod:
        k2s_url, _err = resolve_k2s_vip_download_url(mod)
        if k2s_url:
            return k2s_url
    if mod and mod.bypass_vip:
        # Explicit direct routing flag on modifier pipeline
        for token in _gate_url_re().findall(mod.source_note or ""):
            if not _is_gate_url(token):
                return token
    if mod and vip_gate_live_resolve_enabled():
        from app.services.mega_link_pipeline import resolve_to_file_host

        pipeline = resolve_to_file_host(gate)
        if pipeline.ok and pipeline.destination_url and not _is_gate_url(pipeline.destination_url):
            return pipeline.destination_url
    return None


def transform_caption_for_vip(html: str, db: Session) -> str:
    body = (html or "").strip()
    if not body:
        return VIP_CAPTION_BADGE

    def _replace_anchor(m: re.Match[str]) -> str:
        full = m.group(0)
        href_m = re.search(r'href="([^"]+)"', full, re.I)
        if not href_m:
            return full
        href = href_m.group(1)
        if not _is_gate_url(href):
            return full
        direct = direct_url_for_gate(db, href)
        if direct:
            label_m = re.search(r">([^<]+)<", full)
            label = label_m.group(1) if label_m else "open"
            from app.services.aof_growth_hub import _a_tag

            return _a_tag(direct, f"{label} (direct)")
        # No bypass mapping — keep the Linkvertise gate (never strip channel links on VIP).
        return full

    cleaned = re.sub(r'<a\s+[^>]*href="[^"]+"[^>]*>[^<]*</a>', _replace_anchor, body, flags=re.I)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if VIP_CAPTION_BADGE.split("·")[0].strip() in cleaned:
        return cleaned
    return f"{VIP_CAPTION_BADGE}\n\n{cleaned}"


def transform_buttons_for_vip(buttons: list[dict], db: Session) -> list[dict]:
    out: list[dict] = []
    for btn in buttons:
        if not isinstance(btn, dict):
            continue
        text = str(btn.get("text") or "").strip()
        url = str(btn.get("url") or "").strip()
        if not text or not url:
            continue
        low = text.lower()
        if vip_strip_checkout_on_mirror() and (
            "subscribe" in low or "500" in low or "crypto" in low or "main group" in low
        ):
            continue
        if _is_gate_url(url):
            direct = direct_url_for_gate(db, url)
            if direct:
                out.append({"text": text.replace("LV", "direct")[:64], "url": direct})
                continue
            # Keep gate URL when no direct bypass file host is mapped yet.
            out.append({"text": text[:64], "url": url[:512]})
            continue
        out.append({"text": text[:64], "url": url[:512]})
    return out


async def mirror_scheduled_post_to_vip(
    client: TelegramClient,
    post,
    db: Session,
    *,
    reshuffle_album: bool = False,
) -> bool:
    """Send VIP copy (ad-free, no checkout) before the public lane send."""
    from app.models.scheduled_text_post import ScheduledTextPost
    from app.services.aof_vip_channel_copy import (
        pick_vip_mirror_caption,
        scrub_caption_for_vip_mirror,
        vip_skip_bulletin_mirror,
    )
    from app.services.aof_vip_early_drop import vip_channel_identifier
    from app.services.scheduled_post_service import (
        _gather_media_items_for_send,
        _peek_caption_slot_index,
        _resolve_variant_sources,
        send_scheduled_post,
    )

    vip_ident = vip_channel_identifier(db)
    if not vip_ident:
        logger.warning("vip mirror: channel not configured")
        return False

    slot = _peek_caption_slot_index(post)
    album_order_mode = "static"
    mids, _, use_pool = _resolve_variant_sources(post, slot)
    media_items = _gather_media_items_for_send(post, db, mids, use_pool, album_order_mode)
    if vip_skip_bulletin_mirror() and not media_items:
        from app.services.aof_growth_hub import _is_bulletin_variation

        vars_ = post.get_content_variations() or [post.content or ""]
        idx = (post.caption_rotation_index or 0) % max(1, len(vars_))
        if _is_bulletin_variation(str(vars_[idx] if vars_ else "")):
            logger.info("vip mirror: skip bulletin-only post %s", getattr(post, "id", "?"))
            return False

    vip_post = ScheduledTextPost()
    for col in post.__table__.columns.keys():
        if col in ("id", "sent_at", "last_posted_at", "caption_rotation_index", "album_carousel_index"):
            continue
        setattr(vip_post, col, getattr(post, col, None))

    vip_post.checkout_stars_enabled = False
    vip_post.checkout_stars_plan_id = None
    vip_post.checkout_button_label = None

    orig_caption = pick_vip_mirror_caption(post, db)
    vip_caption = scrub_caption_for_vip_mirror(orig_caption, db)
    vip_post.content = vip_caption
    from app.services.aof_vip_channel_copy import merge_vip_mirror_buttons, strip_vip_affiliate_blocks

    if vip_post.content_variations:
        try:
            raw = json.loads(vip_post.content_variations)
            if isinstance(raw, list):
                vip_post.content_variations = json.dumps(
                    [scrub_caption_for_vip_mirror(str(v), db) for v in raw if strip_vip_affiliate_blocks(str(v))]
                ) or None
        except (json.JSONDecodeError, TypeError):
            pass

    base_btns = vip_post.get_buttons() if hasattr(vip_post, "get_buttons") else []
    vip_btns = merge_vip_mirror_buttons(base_btns if isinstance(base_btns, list) else [], db)
    vip_post.buttons = json.dumps(vip_btns) if vip_btns else None

    source_pool_id = getattr(post, "pool_id", None)
    size = vip_album_size(pool_id=int(source_pool_id) if source_pool_id else None)
    if size > 1:
        vip_post.album_size = size

    # Detached clone has no PK — keep source id for send metrics / outcome builders.
    vip_post.id = getattr(post, "id", None)

    try:
        await send_scheduled_post(
            client,
            vip_ident,
            vip_post,
            db,
            reshuffle_album=reshuffle_album,
        )
        logger.info("vip mirror: scheduled post %s → VIP", getattr(post, "id", "?"))
        return True
    except Exception as e:
        logger.warning("vip mirror failed post=%s: %s", getattr(post, "id", "?"), e)
        return False
