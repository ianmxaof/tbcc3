"""AOF growth hub — links bulletin, per-channel scheduler sync, storage deposits, broadcast actions."""

from __future__ import annotations

import html
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_network import (
    ADDLIST_RAW,
    AOF_NETWORK_CHANNELS,
    BULLETIN_CHANNEL_INVITES,
    BULLETIN_MARKER,
    CROSS_CHANNEL_SCHED_NAME,
    LINKS_HUB_SCHED_NAME,
    MAIN_GROUP_IDENT,
    STORAGE_HUB_IDENT,
    STORAGE_HUB_INVITE,
    network_channel_by_key,
)
from app.data.aof_storage_hub_map import AOF_STORAGE_TOPIC_MAP, CONTENT_LANE_NETWORK_KEYS
from app.models.channel import Channel
from app.models.content_pool import ContentPool
from app.models.loot import LootModifier
from app.models.scheduled_text_post import ScheduledTextPost
from app.models.subscription_plan import SubscriptionPlan
from app.services.link_gate_provider import wrap_gate_url, is_gate_host
from app.services.pool_schedule_sync import sync_pool_album_settings_to_schedules
from app.services.aof_gate_promo_copy import gate_fomo_post_bodies

logger = logging.getLogger(__name__)

FOOTER_MARKER = "Join the full AOF stack"


def network_album_size() -> int:
    from app.services.aof_feed_rhythm_v2 import network_album_size as _size

    return _size()


NETWORK_ALBUM_SIZE = 3  # default; sync uses network_album_size()
CHECKOUT_CAPTION_MARKER = "Start payment for group access"  # legacy alias
DEFAULT_GROUP_ACCESS_PLAN_ID = 6
DEFAULT_CHECKOUT_BUTTON_LABEL = "⭐ Group access — 500⭐"
PACKS_SEED_SCHED_NAMES = ("AOF PACKS — seed rotation",)


def _a_tag(url: str, anchor: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(anchor)}</a>'


def _stored_gate_url(url: str) -> bool:
    u = (url or "").strip().split()[0]
    if not u.startswith("http"):
        return False
    from app.data.aof_manual_gate_links import all_manual_gate_urls
    from app.services.link_gate_provider import is_linkvertise_host

    if u in all_manual_gate_urls():
        return True
    # Reject auto-generated /dynamic wraps; accept manual Post & earn slugs.
    if is_linkvertise_host(u):
        return "/dynamic" not in u.lower()
    return is_gate_host(u) and "work.ink" in u


def gate_urls(db: Session) -> dict[str, str]:
    """Manual Post & earn Linkvertise slugs (dashboard analytics per link)."""
    from app.data.aof_manual_gate_links import manual_gate_urls
    from app.services.aof_vip_checkout import resolve_vip_promo_url

    urls = manual_gate_urls()
    plan_id = resolve_group_access_plan_id(db)
    urls["vip"] = resolve_vip_promo_url(db, plan_id)
    return urls


def lv_urls(db: Session) -> dict[str, str]:
    """Backward-compatible alias for gate_urls."""
    return gate_urls(db)


def _gate_link(lv: dict[str, str], key: str, anchor: str) -> str:
    """Bulletin/footer href — always manual Post & earn LV slug when configured."""
    from app.data.aof_manual_gate_links import manual_gate_url

    url = (lv.get(key) or manual_gate_url(key) or "").strip()
    if not url:
        ch = network_channel_by_key(key)
        url = (ch.invite if ch else "").strip()
    if not url:
        return html.escape(anchor)
    return _a_tag(url, anchor)


def build_links_hub_bulletin(lv: dict[str, str], db: Session | None = None) -> str:
    """
    Pinned AOF public entry copy for the Loot Room commons.
    Posted via scheduler LINKS_HUB_SCHED_NAME.
    """
    from app.services.aof_social_links import donation_link_html
    from app.services.aof_social_links import aof_public_cta_url, loot_room_public_url
    from app.services.promo_affiliate_rotation import build_sponsor_link_html, list_candidates

    donate = donation_link_html(label="Buy me a coffee")
    loot_bot = _a_tag(aof_public_cta_url(), "@aof_lootgod_bot")
    loot_room = _a_tag(loot_room_public_url(), "Loot Room Group")
    donate_line = f"☕ Donate: {donate}\n" if donate else ""
    ai_tools_lines = ""
    partner_lines = ""
    if db is not None:
        ai_tools = list_candidates(db, "links_hub_ai")[:16]
        if not ai_tools:
            # Legacy rows may still use links_hub + ai network key only
            ai_tools = list_candidates(db, "links_hub", network_key="ai")[:16]
        if ai_tools:
            ai_tools_lines = (
                "━━━━━━━━━━━━━━━━━━\n"
                "🧠 <b>AI TOOLS</b>\n"
                "Undress · i2v · generators — curated affiliate bots (supports AOF).\n"
                + "\n".join(f"→ {build_sponsor_link_html(row)}" for row in ai_tools)
                + "\n"
            )
        partners = list_candidates(db, "links_hub")[:8]
        if partners:
            partner_lines = (
                "━━━━━━━━━━━━━━━━━━\n"
                "🤝 <b>PARTNERS</b>\n"
                + "\n".join(f"→ {build_sponsor_link_html(row)}" for row in partners)
                + "\n"
            )
    return (
        "📌 <b>AOF LINKS HUB</b>\n"
        "AOF network entry: Loot Bot first, Loot Room commons, niche lanes after.\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🔥 <b>PUBLIC ENTRY</b>\n"
        f"🎲 Loot Bot: {loot_bot}\n"
        f"🏛 Loot Room: {loot_room}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📂 <b>CONTENT</b>\n"
        f"📌 {_gate_link(lv, 'addlist', 'ADDLIST — all channels')}\n"
        f"👉 AOF AI: {_gate_link(lv, 'ai', 'AOF AI')}\n"
        f"🔥 AOF ASS: {_gate_link(lv, 'ass', 'AOF ASS')}\n"
        f"💋 AOF BLOWJOB: {_gate_link(lv, 'blowjob', 'AOF BLOWJOB')}\n"
        f"🌍 AOF BIG TITS: {_gate_link(lv, 'big_tits', 'AOF BIG TITS')}\n"
        f"🧔‍♀️ AOF MILF: {_gate_link(lv, 'milf', 'AOF MILF')}\n"
        f"🔞 AOF TABOO: {_gate_link(lv, 'taboo', 'AOF TABOO')}\n"
        f"👀 AOF PUBLIC VOYEUR: {_gate_link(lv, 'voyeur', 'AOF PUBLIC VOYEUR')}\n"
        f"👧 AOF ABG / LBFM: {_gate_link(lv, 'abg', 'AOF ABG / LBFM')}\n"
        f"📦 AOF PACKS: {_gate_link(lv, 'packs', 'AOF PACKS')}\n"
        f"🌀 AOF GOON: {_gate_link(lv, 'goon', 'AOF GOON')}\n"
        f"🎵 AOF BOP: {_gate_link(lv, 'bop', 'AOF BOP')}\n"
        f"🪙 AOF LOOT ROOM: {_gate_link(lv, 'loot', 'AOF LOOT ROOM')}\n"
        f"{ai_tools_lines}"
        "━━━━━━━━━━━━━━━━━━\n"
        "🤖 <b>OFFICIAL BOTS</b>\n"
        "🔓 Subscriptions &amp; Packs: @aofsubscriptions_bot\n"
        "📋 Secretary: @aof_secretary_bot\n"
        "💰 Loot God: @aof_lootgod_bot\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🚀 <b>SUPPORT AOF</b>\n"
        "💪 Boost: https://t.me/boost?c=3206350461\n"
        "🔥 Buy Premium Packs: @aofsubscriptions_bot\n"
        f"⭐ AOF VIP: @aofsubscriptions_bot — /subscribe\n"
        "📢 Referral Program: @aofsubscriptions_bot — /referral\n"
        f"{donate_line}"
        f"{partner_lines}"
        f"📌 {_gate_link(lv, 'addlist', 'ALL CHANNELS ADDLIST')}"
    )


def build_addlist_footer(lv: dict[str, str], *, sponsor_line_html: str | None = None) -> str:
    """Compact footer — pipe-separated links; VIP checkout is inline Pay ⭐ at send."""
    from app.services.aof_social_links import donation_link_html

    bot = (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "aofsubscriptions_bot").strip().lstrip("@")
    from app.services.aof_social_links import aof_public_cta_url, loot_room_public_url

    addlist = _gate_link(lv, "addlist", "addlist")
    loot_bot = _a_tag(aof_public_cta_url(), "loot bot")
    loot_room = _a_tag(loot_room_public_url(), "loot room")
    donate = donation_link_html(label="☕ support")
    donate_bit = f" | {donate}" if donate else ""
    sponsor_bit = f"{sponsor_line_html.strip()}\n" if sponsor_line_html and sponsor_line_html.strip() else ""
    return (
        "\n\n━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>{FOOTER_MARKER}</b>\n"
        f"{sponsor_bit}"
        f"🌐 {addlist} | 🎲 {loot_bot} | 🏛 {loot_room}{donate_bit}\n"
        f"🗝 @{bot} · /loot · /subscribe · /referral"
    )


def network_pool_names() -> frozenset[str]:
    return frozenset(ch.pool_name for ch in AOF_NETWORK_CHANNELS)


def resolve_group_access_plan_id(db: Session) -> int:
    """Primary subscription plan for main-group access (Stars checkout on channel posts)."""
    row = (
        db.query(SubscriptionPlan)
        .filter(
            SubscriptionPlan.is_active.is_(True),
            SubscriptionPlan.product_type == "subscription",
            SubscriptionPlan.bot_section == "main",
            SubscriptionPlan.price_stars > 0,
        )
        .order_by(SubscriptionPlan.id.asc())
        .first()
    )
    return int(row.id) if row else DEFAULT_GROUP_ACCESS_PLAN_ID


def checkout_button_label_for_plan(db: Session, plan_id: int) -> str:
    from app.services.aof_vip_checkout import stars_pay_button_label, use_invoice_link_checkout

    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == int(plan_id)).first()
    if not plan:
        return DEFAULT_CHECKOUT_BUTTON_LABEL
    if use_invoice_link_checkout():
        return stars_pay_button_label(plan)
    stars = int(plan.price_stars or 0)
    name = (plan.name or "Group access").strip()[:36]
    if stars > 0:
        return f"⭐ {name} — {stars}⭐"
    return DEFAULT_CHECKOUT_BUTTON_LABEL


def build_checkout_caption_line(plan_id: int) -> str:
    """Caption deep link for group-access checkout (VIP subscription or bot fallback)."""
    from app.database.session import SessionLocal

    db = SessionLocal()
    try:
        from app.services.aof_vip_checkout import build_checkout_caption_line as _vip_line

        return _vip_line(db, plan_id)
    finally:
        db.close()


def _append_checkout_caption(text: str, checkout_line: str) -> str:
    from app.services.aof_vip_checkout import caption_has_checkout, strip_checkout_caption_lines

    body = strip_checkout_caption_lines((text or "").strip())
    if not body or not checkout_line:
        return body
    if caption_has_checkout(body):
        return body
    return body + checkout_line


def _extract_footer_sponsor_line(body: str) -> str | None:
    if FOOTER_MARKER not in (body or ""):
        return None
    idx = body.find(FOOTER_MARKER)
    rest = body[idx:]
    for line in rest.split("\n")[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("🌐"):
            break
        if stripped.startswith("💰") or stripped.startswith("🎨") or "href=" in stripped:
            return stripped
    return None


def _inject_sponsor_into_footer(clean_footer: str, sponsor_line: str | None) -> str:
    if not sponsor_line or not sponsor_line.strip():
        return clean_footer
    marker = f"📌 <b>{FOOTER_MARKER}</b>\n"
    pos = clean_footer.find(marker)
    if pos < 0:
        return clean_footer
    insert_at = pos + len(marker)
    return clean_footer[:insert_at] + sponsor_line.strip() + "\n" + clean_footer[insert_at:]


def _refresh_variation_footer(caption: str, clean_footer: str) -> str:
    """Strip bare VIP leaks and normalize addlist footer block."""
    from app.services.aof_vip_checkout import scrub_caption_for_network_post

    sponsor = _extract_footer_sponsor_line(caption)
    body = scrub_caption_for_network_post(caption)
    if FOOTER_MARKER not in (caption or ""):
        return body
    idx = body.find(FOOTER_MARKER)
    if idx < 0:
        merged = (body + clean_footer).strip() if body else clean_footer.strip()
        return _inject_sponsor_into_footer(merged, sponsor)
    split_at = body.rfind("\n\n", 0, idx)
    if split_at < 0:
        split_at = body.rfind("\n", 0, idx)
    prefix = body[:split_at].rstrip() if split_at > 0 else body[:idx].rstrip()
    merged = (prefix + clean_footer).strip() if prefix else clean_footer.strip()
    return _inject_sponsor_into_footer(merged, sponsor)


def _sanitize_variations(
    variations: list[str],
    *,
    clean_footer: str = "",
    skip_bulletin: bool = True,
) -> list[str]:
    """Scrub bare VIP links + legacy 💳 caption checkout from every rotation slot."""
    from app.services.aof_vip_checkout import scrub_caption_for_network_post

    out: list[str] = []
    for v in variations:
        if skip_bulletin and _is_bulletin_variation(v):
            out.append(scrub_caption_for_network_post(v))
            continue
        if clean_footer:
            out.append(_refresh_variation_footer(v, clean_footer))
        else:
            out.append(scrub_caption_for_network_post(v))
    return out


def _strip_variations_checkout(
    variations: list[str],
    *,
    clean_footer: str = "",
    skip_bulletin: bool = True,
) -> list[str]:
    """Backward-compatible alias — scrub VIP leaks and checkout caption lines."""
    return _sanitize_variations(variations, clean_footer=clean_footer, skip_bulletin=skip_bulletin)


def _apply_scheduler_album_checkout(
    sched: ScheduledTextPost,
    pool: ContentPool | None,
    db: Session,
    *,
    plan_id: int,
    button_label: str,
    preserve_album_size: bool = False,
) -> None:
    if not preserve_album_size:
        sched.album_size = network_album_size()
    sched.checkout_stars_enabled = True
    sched.checkout_stars_plan_id = int(plan_id)
    sched.checkout_button_label = button_label
    from app.services.aof_vip_checkout import merge_checkout_buttons

    checkout_btns = merge_checkout_buttons(
        [],
        db,
        checkout_stars_enabled=True,
        checkout_stars_plan_id=int(plan_id),
        checkout_button_label=button_label,
        allow_inline_checkout=True,
    )
    if checkout_btns:
        sched.buttons = json.dumps(checkout_btns)
    if pool:
        if not preserve_album_size:
            pool.album_size = network_album_size()
        if not sched.pool_id:
            sched.pool_id = pool.id
        if sched.pool_randomize is None:
            sched.pool_randomize = bool(pool.randomize_queue)


def sync_network_album_and_checkout(db: Session, *, execute: bool = True) -> dict[str, Any]:
    """
    Network-wide: album_size=1 on AOF pools + schedulers, Stars group-access checkout
    (inline Pay ⭐ button on single-image posts; bot deep link caption only for multi-album).
    """
    plan_id = resolve_group_access_plan_id(db)
    button_label = checkout_button_label_for_plan(db, plan_id)
    clean_footer = build_addlist_footer(lv_urls(db))
    pool_names = network_pool_names()
    pools_updated = 0
    schedulers_updated = 0
    rows: list[dict[str, Any]] = []

    for name in sorted(pool_names):
        pool = db.query(ContentPool).filter(ContentPool.name == name).first()
        entry: dict[str, Any] = {"kind": "pool", "name": name, "pool_id": pool.id if pool else None}
        if pool and execute:
            size = network_album_size()
            pool.album_size = size
            n = sync_pool_album_settings_to_schedules(db, pool.id, album_size=size)
            pools_updated += 1
            entry["schedules_synced"] = n
        rows.append(entry)

    def _touch_scheduler(
        sched: ScheduledTextPost,
        pool: ContentPool | None,
        *,
        key: str,
        skip_bulletin: bool = True,
        preserve_album_size: bool = False,
    ) -> None:
        nonlocal schedulers_updated
        entry = {
            "kind": "scheduler",
            "key": key,
            "scheduler_id": sched.id,
            "name": sched.name,
            "channel_id": sched.channel_id,
        }
        vars_ = sched.get_content_variations() or ([sched.content] if sched.content else [])
        new_vars = _strip_variations_checkout(
            vars_, clean_footer=clean_footer, skip_bulletin=skip_bulletin
        )
        entry["variations"] = len(new_vars)
        entry["checkout_enabled"] = True
        entry["plan_id"] = plan_id
        if execute:
            _apply_scheduler_album_checkout(
                sched,
                pool,
                db,
                plan_id=plan_id,
                button_label=button_label,
                preserve_album_size=preserve_album_size,
            )
            if new_vars:
                sched.content = new_vars[0]
                sched.content_variations = json.dumps(new_vars) if len(new_vars) > 1 else None
            schedulers_updated += 1
        rows.append(entry)

    for net_ch in AOF_NETWORK_CHANNELS:
        ch = db.query(Channel).filter(Channel.identifier == net_ch.identifier).first()
        if not ch:
            rows.append({"kind": "scheduler", "key": net_ch.key, "status": "channel_missing"})
            continue
        pool = db.query(ContentPool).filter(ContentPool.name == net_ch.pool_name).first()
        sched = (
            db.query(ScheduledTextPost)
            .filter(
                ScheduledTextPost.channel_id == ch.id,
                ScheduledTextPost.name == net_ch.scheduler_name,
            )
            .first()
        )
        if sched:
            _touch_scheduler(sched, pool, key=net_ch.key)
        else:
            rows.append({"kind": "scheduler", "key": net_ch.key, "status": "scheduler_missing"})

    for sched_name in PACKS_SEED_SCHED_NAMES:
        sched = (
            db.query(ScheduledTextPost)
            .filter(ScheduledTextPost.name == sched_name)
            .order_by(ScheduledTextPost.id.desc())
            .first()
        )
        if not sched:
            rows.append({"kind": "scheduler", "key": "packs_seed", "name": sched_name, "status": "missing"})
            continue
        pool = None
        if sched.pool_id:
            pool = db.query(ContentPool).filter(ContentPool.id == sched.pool_id).first()
        if not pool:
            pool = db.query(ContentPool).filter(ContentPool.name == "AOF PACKS — Promo").first()
        _touch_scheduler(sched, pool, key="packs_seed", skip_bulletin=False, preserve_album_size=True)

    for sched in db.query(ScheduledTextPost).filter(ScheduledTextPost.name == CROSS_CHANNEL_SCHED_NAME).all():
        ch = db.query(Channel).filter(Channel.id == sched.channel_id).first()
        pool = None
        if sched.pool_id:
            pool = db.query(ContentPool).filter(ContentPool.id == sched.pool_id).first()
        if not pool and ch:
            match = next((nc for nc in AOF_NETWORK_CHANNELS if nc.identifier == ch.identifier), None)
            if match:
                pool = db.query(ContentPool).filter(ContentPool.name == match.pool_name).first()
        _touch_scheduler(
            sched,
            pool,
            key=f"cross:{sched.channel_id}",
            skip_bulletin=True,
        )

    for pool in db.query(ContentPool).filter(ContentPool.name.in_(pool_names)).all():
        extra = (
            db.query(ScheduledTextPost)
            .filter(ScheduledTextPost.pool_id == pool.id)
            .all()
        )
        seen = {r.get("scheduler_id") for r in rows if r.get("scheduler_id")}
        for sched in extra:
            if sched.id in seen:
                continue
            _touch_scheduler(sched, pool, key=f"pool:{pool.name}", skip_bulletin=False)

    liveness_rows = sync_main_group_liveness_checkout(
        db,
        execute=execute,
        plan_id=plan_id,
        button_label=button_label,
        clean_footer=clean_footer,
    )
    rows.extend(liveness_rows)

    return {
        "execute": execute,
        "album_size": network_album_size(),
        "group_access_plan_id": plan_id,
        "checkout_button_label": button_label,
        "pools_updated": pools_updated,
        "schedulers_updated": schedulers_updated,
        "captions_scrubbed": _scrub_all_scheduler_captions(db, clean_footer=clean_footer, execute=execute),
        "rows": rows,
    }


def _scrub_all_scheduler_captions(
    db: Session,
    *,
    clean_footer: str,
    execute: bool,
) -> int:
    """Strip bare VIP invite anchors from every scheduler variation in DB."""
    updated = 0
    for sched in db.query(ScheduledTextPost).all():
        vars_ = sched.get_content_variations() or ([sched.content] if sched.content else [])
        if not vars_:
            continue
        new_vars = _sanitize_variations(vars_, clean_footer=clean_footer, skip_bulletin=True)
        if new_vars == vars_:
            continue
        updated += 1
        if execute:
            sched.content = new_vars[0]
            sched.content_variations = json.dumps(new_vars) if len(new_vars) > 1 else None
    return updated


def sync_main_group_liveness_checkout(
    db: Session,
    *,
    execute: bool,
    plan_id: int,
    button_label: str,
    clean_footer: str,
) -> list[dict[str, Any]]:
    """
    Main-group liveness schedulers (heartbeat, drop ticker, spotlight, drop signals):
    Stars Pay ⭐ inline button + refreshed footer + VIP promo copy in rotations.
    """
    from app.services.aof_network_liveness import (
        LIVENESS_PREFIX,
        apply_liveness_checkout_and_copy,
        liveness_message_thread_id,
    )

    main = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()
    if not main:
        return [{"kind": "liveness", "status": "main_group_missing"}]

    rows: list[dict[str, Any]] = []
    scheds = (
        db.query(ScheduledTextPost)
        .filter(
            ScheduledTextPost.channel_id == main.id,
            ScheduledTextPost.name.like(f"{LIVENESS_PREFIX}%"),
        )
        .all()
    )
    thread_id = liveness_message_thread_id()
    for sched in scheds:
        entry = apply_liveness_checkout_and_copy(
            sched,
            db,
            plan_id=plan_id,
            button_label=button_label,
            clean_footer=clean_footer,
            execute=execute,
            message_thread_id=thread_id,
        )
        rows.append(entry)
    return rows


def _is_bulletin_variation(text: str) -> bool:
    return BULLETIN_MARKER in (text or "")


def _merge_variations(bulletin: str, promo: str, existing: list[str]) -> list[str]:
    """Bulletin always slot 0; channel promo slot 1; keep other non-bulletin legacy variations."""
    kept: list[str] = []
    for v in existing:
        body = (v or "").strip()
        if not body or _is_bulletin_variation(body):
            continue
        if body == promo.strip():
            continue
        kept.append(body)
    out = [bulletin.strip()]
    promo_body = promo.strip()
    if promo_body:
        out.append(promo_body)
    out.extend(kept)
    return out


def _append_gate_fomo_variations(variations: list[str], footer: str) -> list[str]:
    """Add wrapped-link how-to / FOMO copy into scheduler rotation (skips bulletin slot)."""
    seen = {v.strip() for v in variations}
    out = list(variations)
    for body in gate_fomo_post_bodies():
        full = (body + footer).strip()
        if full in seen:
            continue
        seen.add(full)
        out.append(full)
    return out


def build_telegram_footer_variants(db: Session, lv: dict[str, str], *, network_key: str) -> list[str]:
    """One footer per telegram_footer affiliate eligible for this network channel."""
    from app.services.promo_affiliate_rotation import build_sponsor_link_html, list_candidates

    base = build_addlist_footer(lv)
    candidates = list_candidates(db, "telegram_footer", network_key=network_key)
    if not candidates:
        return [base]
    out: list[str] = []
    seen: set[str] = {base.strip()}
    out.append(base)
    for row in candidates:
        footer = build_addlist_footer(lv, sponsor_line_html=build_sponsor_link_html(row))
        key = footer.strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(footer)
    return out


def _strip_regenerated_promo_variations(existing: list[str], promo_html: str) -> list[str]:
    """Drop prior channel-promo + footer rows so affiliate sync can rebuild them."""
    prefix = (promo_html or "").strip()
    kept: list[str] = []
    for v in existing:
        body = (v or "").strip()
        if not body:
            continue
        if prefix and body.startswith(prefix) and FOOTER_MARKER in body:
            continue
        kept.append(v)
    return kept


def _append_sponsor_promo_variations(
    variations: list[str],
    promo_html: str,
    footer_variants: list[str],
) -> list[str]:
    """Add promo+footer slots for each sponsor footer (slot 1 already set)."""
    seen = {v.strip() for v in variations}
    out = list(variations)
    prefix = (promo_html or "").strip()
    for footer in footer_variants[1:]:
        full = (prefix + footer).strip()
        if not full or full in seen:
            continue
        seen.add(full)
        out.append(full)
    return out


def _ensure_channel_row(db: Session, net_ch) -> Channel | None:
    row = db.query(Channel).filter(Channel.identifier == net_ch.identifier).first()
    if row:
        if (row.invite_link or "").strip() != net_ch.invite:
            row.invite_link = net_ch.invite
        if row.name != net_ch.display_name:
            row.name = net_ch.display_name
        return row
    row = Channel(name=net_ch.display_name, identifier=net_ch.identifier, invite_link=net_ch.invite)
    db.add(row)
    db.flush()
    return row


def _ensure_pool_row(db: Session, net_ch, channel_id: int) -> ContentPool | None:
    pool = db.query(ContentPool).filter(ContentPool.name == net_ch.pool_name).first()
    if pool:
        if pool.channel_id != channel_id:
            pool.channel_id = channel_id
        return pool
    pool = ContentPool(
        name=net_ch.pool_name,
        channel_id=channel_id,
        album_size=1,
        interval_minutes=0,
        auto_post_enabled=False,
        randomize_queue=True,
    )
    db.add(pool)
    db.flush()
    return pool


def _find_or_create_scheduler(db: Session, net_ch, channel_id: int) -> ScheduledTextPost:
    sched = (
        db.query(ScheduledTextPost)
        .filter(
            ScheduledTextPost.channel_id == channel_id,
            ScheduledTextPost.name == net_ch.scheduler_name,
        )
        .first()
    )
    if sched:
        from app.services.scheduler_category import apply_scheduler_category

        apply_scheduler_category(sched, "main_lane")
        return sched
    sched = (
        db.query(ScheduledTextPost)
        .filter(
            ScheduledTextPost.channel_id == channel_id,
            ScheduledTextPost.name.like("%SCHEDULER%"),
            ScheduledTextPost.campaign_group_id.is_(None),
        )
        .order_by(ScheduledTextPost.id.asc())
        .first()
    )
    if sched:
        from app.services.scheduler_category import apply_scheduler_category

        sched.name = net_ch.scheduler_name
        apply_scheduler_category(sched, "main_lane")
        return sched
    sched = ScheduledTextPost(
        name=net_ch.scheduler_name,
        channel_id=channel_id,
        content="",
        interval_minutes=240,
        send_silent=False,
        pin_after_send=False,
        created_at=datetime.now(timezone.utc),
        last_posted_at=datetime.now(timezone.utc),
    )
    from app.services.scheduler_category import apply_scheduler_category

    apply_scheduler_category(sched, "main_lane")
    db.add(sched)
    db.flush()
    return sched


def sync_network_schedulers(db: Session, *, execute: bool = True) -> dict[str, Any]:
    """Ensure every network channel has bulletin + channel promo in content_variations."""
    lv = lv_urls(db)
    bulletin = build_links_hub_bulletin(lv, db)
    rows: list[dict] = []

    for net_ch in AOF_NETWORK_CHANNELS:
        if net_ch.key == "packs":
            continue  # PACKS uses dedicated drop scheduler (seed rotation)
        ch = _ensure_channel_row(db, net_ch) if execute else db.query(Channel).filter(
            Channel.identifier == net_ch.identifier
        ).first()
        entry: dict[str, Any] = {
            "key": net_ch.key,
            "display_name": net_ch.display_name,
            "scheduler_name": net_ch.scheduler_name,
        }
        if not ch:
            entry["status"] = "channel_missing"
            rows.append(entry)
            continue
        entry["channel_id"] = ch.id
        if execute:
            _ensure_pool_row(db, net_ch, ch.id)
        sched = _find_or_create_scheduler(db, net_ch, ch.id) if execute else (
            db.query(ScheduledTextPost)
            .filter(ScheduledTextPost.channel_id == ch.id, ScheduledTextPost.name == net_ch.scheduler_name)
            .first()
        )
        if not sched:
            entry["status"] = "scheduler_missing"
            rows.append(entry)
            continue
        existing = sched.get_content_variations() if sched else []
        if not existing and sched and sched.content:
            existing = [sched.content]
        existing = _strip_regenerated_promo_variations(existing, net_ch.promo_html)
        footer_variants = build_telegram_footer_variants(db, lv, network_key=net_ch.key)
        base_footer = footer_variants[0]
        promo = net_ch.promo_html + base_footer
        merged = _merge_variations(bulletin, promo, existing)
        if len(footer_variants) > 1:
            merged = _append_sponsor_promo_variations(merged, net_ch.promo_html, footer_variants)
        merged = _append_gate_fomo_variations(merged, base_footer)
        merged = _sanitize_variations(merged, clean_footer=base_footer, skip_bulletin=True)
        entry["variations"] = len(merged)
        entry["sponsor_footers"] = max(0, len(footer_variants) - 1)
        entry["scheduler_id"] = sched.id
        if execute:
            sched.content = merged[0]
            sched.content_variations = json.dumps(merged) if len(merged) > 1 else None
            sched.interval_minutes = sched.interval_minutes or 240
            if sched.last_posted_at is None and sched.interval_minutes:
                sched.last_posted_at = datetime.now(timezone.utc)
            if net_ch.key == "main":
                sched.pin_after_send = True
            entry["status"] = "updated"
        else:
            entry["status"] = "would_update"
        rows.append(entry)

    # Pinned links hub one-shot row on the configured commons channel
    main_ch = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()
    if main_ch:
        pinned = (
            db.query(ScheduledTextPost)
            .filter(ScheduledTextPost.channel_id == main_ch.id, ScheduledTextPost.name == LINKS_HUB_SCHED_NAME)
            .first()
        )
        if not pinned and execute:
            pinned = ScheduledTextPost(
                name=LINKS_HUB_SCHED_NAME,
                channel_id=main_ch.id,
                content=bulletin,
                pin_after_send=True,
                send_silent=False,
                created_at=datetime.now(timezone.utc),
                scheduler_category="promo_bulletin",
            )
            db.add(pinned)
            db.flush()
        elif pinned and execute:
            pinned.content = bulletin
            pinned.pin_after_send = True
            pinned.scheduler_category = pinned.scheduler_category or "promo_bulletin"
        rows.append(
            {
                "key": "pinned_bulletin",
                "scheduler_id": pinned.id if pinned else None,
                "status": "updated" if execute and pinned else "would_update",
            }
        )

    album_checkout: dict[str, Any] | None = None
    if execute:
        album_checkout = sync_network_album_and_checkout(db, execute=True)

    from app.services.promo_affiliate_rotation import affiliate_rotation_stats

    return {
        "bulletin_chars": len(bulletin),
        "bulletin_has_packs": "AOF PACKS" in bulletin,
        "bulletin_has_goon": "AOF GOON" in bulletin,
        "bulletin_has_partners": "PARTNERS" in bulletin,
        "bulletin_has_ai_tools": "AI TOOLS" in bulletin,
        "channels": rows,
        "album_checkout": album_checkout,
        "affiliate": affiliate_rotation_stats(db),
    }


def sync_affiliate_network(db: Session, *, execute: bool = True) -> dict[str, Any]:
    """Rebuild links hub partners + per-channel sponsor footer rotations."""
    return sync_network_schedulers(db, execute=execute)


def growth_hub_status(db: Session) -> dict[str, Any]:
    lv = lv_urls(db)
    bulletin = build_links_hub_bulletin(lv, db)
    sched_rows: list[dict] = []
    for net_ch in AOF_NETWORK_CHANNELS:
        if net_ch.key == "packs":
            continue
        ch = db.query(Channel).filter(Channel.identifier == net_ch.identifier).first()
        if not ch:
            sched_rows.append({"key": net_ch.key, "ok": False, "reason": "channel_missing"})
            continue
        sched = (
            db.query(ScheduledTextPost)
            .filter(ScheduledTextPost.channel_id == ch.id, ScheduledTextPost.name == net_ch.scheduler_name)
            .first()
        )
        if not sched:
            sched_rows.append({"key": net_ch.key, "channel_id": ch.id, "ok": False, "reason": "no_scheduler"})
            continue
        vars_ = sched.get_content_variations() or ([sched.content] if sched.content else [])
        has_bulletin = any(_is_bulletin_variation(v) for v in vars_)
        sched_rows.append(
            {
                "key": net_ch.key,
                "channel_id": ch.id,
                "scheduler_id": sched.id,
                "ok": has_bulletin,
                "variations": len(vars_),
                "interval_minutes": sched.interval_minutes,
                "pin_after_send": sched.pin_after_send,
            }
        )
    pinned = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.name == LINKS_HUB_SCHED_NAME)
        .order_by(ScheduledTextPost.id.desc())
        .first()
    )
    from app.services.aof_topic_mirror import topic_mirror_status
    from app.services.feed_rhythm import feed_rhythm_status
    from app.services.main_group_notifications import main_group_notify_status

    return {
        "bulletin_preview": bulletin[:1200],
        "bulletin_full_chars": len(bulletin),
        "content_links": [
            "AOF PACKS",
            "AOF GOON",
            "AOF BOP",
            "ABG / LBFM",
        ],
        "schedulers": sched_rows,
        "pinned_bulletin_id": pinned.id if pinned else None,
        "storage_hub": {
            "identifier": STORAGE_HUB_IDENT,
            "invite": STORAGE_HUB_INVITE,
        },
        "storage_topic_map": [
            {
                "network_key": m.network_key,
                "topic_id": m.message_thread_id,
                "topic_title": m.topic_title,
                "deep_link": f"https://t.me/c/3812457581/{m.message_thread_id}",
                "receive_channel": network_channel_by_key(m.network_key).identifier
                if network_channel_by_key(m.network_key)
                else None,
                "pool_name": network_channel_by_key(m.network_key).pool_name
                if network_channel_by_key(m.network_key)
                else None,
            }
            for m in AOF_STORAGE_TOPIC_MAP
        ],
        "topic_mirror": topic_mirror_status(),
        "feed_rhythm": feed_rhythm_status(),
        "main_group_notify": main_group_notify_status(),
    }


def _growth_post_stagger_s() -> int:
    raw = (os.getenv("TBCC_GROWTH_BROADCAST_STAGGER_S") or "12").strip()
    try:
        return max(0, min(120, int(raw)))
    except ValueError:
        return 12


def _growth_import_stagger_s() -> int:
    raw = (os.getenv("TBCC_GROWTH_IMPORT_STAGGER_S") or "45").strip()
    try:
        return max(0, min(300, int(raw)))
    except ValueError:
        return 45


def queue_post_scheduler(post_id: int, *, countdown: int = 0) -> dict[str, Any]:
    from app.workers.poster_worker import post_scheduled_text

    try:
        result = post_scheduled_text.apply_async(
            args=[int(post_id)],
            kwargs={"manual_trigger": True},
            countdown=max(0, int(countdown)),
        )
        return {"post_id": post_id, "ok": True, "task_id": result.id, "countdown": max(0, int(countdown))}
    except Exception as e:
        return {"post_id": post_id, "ok": False, "error": str(e)[:300]}


def broadcast_bulletin_to_network(db: Session, *, pin_main: bool = True) -> dict[str, Any]:
    """Post variation slot 0 (links hub) to every network channel scheduler."""
    sync_network_schedulers(db, execute=True)
    db.commit()
    queued: list[dict] = []
    stagger = _growth_post_stagger_s()
    slot = 0
    for net_ch in AOF_NETWORK_CHANNELS:
        if net_ch.key == "packs":
            continue
        ch = db.query(Channel).filter(Channel.identifier == net_ch.identifier).first()
        if not ch:
            continue
        sched = (
            db.query(ScheduledTextPost)
            .filter(ScheduledTextPost.channel_id == ch.id, ScheduledTextPost.name == net_ch.scheduler_name)
            .first()
        )
        if not sched:
            continue
        sched.caption_rotation_index = 0
        if net_ch.key == "main" and pin_main:
            sched.pin_after_send = True
        db.flush()
        queued.append(
            {
                **queue_post_scheduler(sched.id, countdown=slot * stagger),
                "key": net_ch.key,
                "channel_id": ch.id,
            }
        )
        slot += 1
    db.commit()
    pinned = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.name == LINKS_HUB_SCHED_NAME)
        .order_by(ScheduledTextPost.id.desc())
        .first()
    )
    if pinned:
        queued.append(
            {**queue_post_scheduler(pinned.id, countdown=slot * stagger), "key": "pinned_bulletin"}
        )
    return {"queued": queued, "count": len(queued)}


def storage_pool_seed_batch_size() -> int:
    """Default small batch per Storage Hub topic → channel pool import."""
    raw = (os.getenv("TBCC_STORAGE_POOL_SEED_BATCH") or "8").strip()
    try:
        return min(max(int(raw), 1), 50)
    except ValueError:
        return 8


def storage_pool_seed_enabled() -> bool:
    raw = (os.getenv("TBCC_STORAGE_POOL_SEED_ENABLED") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def list_storage_hub_import_lanes(db: Session) -> dict[str, Any]:
    """Content lanes from Storage Hub map with ensured channel/pool rows for the dashboard."""
    from app.data.aof_network import network_channel_by_key
    from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT, content_lane_storage_topics, topic_deep_link

    lanes: list[dict] = []
    for row in content_lane_storage_topics():
        net = network_channel_by_key(row.network_key)
        if not net:
            continue
        ch = _ensure_channel_row(db, net)
        if not ch:
            continue
        pool = _ensure_pool_row(db, net, int(ch.id))
        if not pool:
            continue
        lanes.append(
            {
                "network_key": row.network_key,
                "topic_title": row.topic_title,
                "message_thread_id": row.message_thread_id,
                "topic_deep_link": topic_deep_link(row.message_thread_id),
                "pool_id": int(pool.id),
                "pool_name": net.pool_name,
                "channel_name": net.display_name,
                "receive_channel": net.identifier,
                "channel_id": int(ch.id),
            }
        )
    if lanes:
        db.commit()
    lanes.sort(key=lambda x: (x.get("channel_name") or "", x.get("network_key") or ""))
    return {
        "storage_hub_ident": STORAGE_HUB_IDENT,
        "lanes": lanes,
        "default_batch_size": storage_pool_seed_batch_size(),
    }


def queue_storage_hub_deposits(
    db: Session,
    *,
    limit: int | None = None,
    topic_keys: list[str] | None = None,
    media_types: str = "both",
    exclude_keys: set[str] | frozenset[str] | None = None,
    content_lanes_only: bool = False,
    include_topic_mirror: bool = True,
    apply_watermark: bool = False,
) -> dict[str, Any]:
    """Match storage-hub forum topics → network pools; queue non-destructive imports."""
    from app.services.storage_topic_deposit import queue_storage_topic_deposit

    if limit is None:
        limit = storage_pool_seed_batch_size()
    limit = min(max(int(limit), 1), 200)
    jobs: list[dict] = []
    allow = {k.strip().lower() for k in (topic_keys or []) if k.strip()}
    skip = {k.strip().lower() for k in (exclude_keys or ()) if k.strip()}
    if content_lanes_only:
        allow = allow or set(CONTENT_LANE_NETWORK_KEYS)
        skip.add("packs")
    import_stagger = _growth_import_stagger_s()
    import_slot = 0

    for row in AOF_STORAGE_TOPIC_MAP:
        if allow and row.network_key not in allow:
            continue
        if row.network_key in skip:
            continue
        body = queue_storage_topic_deposit(
            db,
            message_thread_id=int(row.message_thread_id),
            limit=limit,
            topic_title=row.topic_title,
            media_types=media_types,
            include_topic_mirror=False,
            apply_watermark=apply_watermark,
            commit=False,
            countdown=import_slot * import_stagger,
        )
        if not body.get("ok"):
            body["topic_title"] = row.topic_title
            jobs.append(body)
            continue
        import_slot += 1
        jobs.append(body)

    mirror_report: dict[str, Any] | None = None
    if include_topic_mirror:
        try:
            from app.services.aof_topic_mirror import queue_topic_mirror_all

            mirror_limit = min(max(int(limit // 6), 3), 15)
            mirror_keys = topic_keys
            if content_lanes_only and not mirror_keys:
                mirror_keys = sorted(CONTENT_LANE_NETWORK_KEYS)
            elif allow:
                mirror_keys = sorted(allow)
            mirror_report = queue_topic_mirror_all(
                db,
                limit_per_pair=mirror_limit,
                topic_keys=mirror_keys,
                media_types=media_types,
            )
        except Exception as e:
            mirror_report = {"ok": False, "error": str(e)[:200]}

    db.commit()
    return {
        "ok": True,
        "limit_per_topic": limit,
        "jobs": jobs,
        "matched_count": len(jobs),
        "source": "aof_storage_hub_map",
        "topic_mirror": mirror_report,
    }
