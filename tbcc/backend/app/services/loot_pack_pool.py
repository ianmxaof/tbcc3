"""Shared AOF pack + loot modifier pool (loot_modifiers kind=mega_pack)."""

from __future__ import annotations

import html
import json
import logging
import os
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.data.aof_manual_gate_links import manual_gate_url
from app.models.loot import LootModifier
from app.services.aof_packs_post_copy import (
    merge_pack_source_note,
    resolve_pack_gate_urls,
)
from app.services.aof_packs_caption_templates import pack_caption_template_variations
from app.services.mega_link_extract import classify_url_host
from app.services.mega_link_pipeline import build_modifier_payload, resolve_to_file_host

logger = logging.getLogger(__name__)

PACK_QUEUE_MARKER = "pack_queue"

# Legacy + current source_note prefixes that count as pack-pool rows.
PACK_POOL_SOURCE_MARKERS: tuple[str, ...] = (
    PACK_QUEUE_MARKER,
    "url_list_batch",
    "master_archive",
    "mega_pipeline",
    "mega_scrape",
    "mega_paste_batch",
    "mega_clipboard",
    "mega_inventory",
)

PACK_CANDIDATE_HOST_KINDS = frozenset({"file_host", "paste", "obfuscated", "sophon"})

POOL_NAME = "AOF PACKS — Promo"
SCHED_NAME = "AOF PACKS — seed rotation"
# Legacy launch IDs — kept for scripts that still reference them; scheduler uses full promo pool.
SEED_MEDIA_IDS = (2168, 2169, 2170)
STARS_PLAN_ID = 6


def list_approved_packs_promo_media_ids(db: Session, pool_id: int) -> list[int]:
    """Approved promo images in AOF PACKS — Promo (oldest id first)."""
    from app.models.media import Media

    rows = (
        db.query(Media.id)
        .filter(Media.pool_id == pool_id, Media.status == "approved")
        .order_by(Media.id.asc())
        .all()
    )
    return [int(r[0]) for r in rows]


def build_packs_album_variants(
    promo_media_ids: list[int],
    caption_count: int,
    *,
    link_slot_offset: int = 0,
) -> tuple[list[dict[str, Any]], bool]:
    """
    Pair each caption rotation slot with a promo image (cycles through the full pool).
    Returns (album_variants, pool_only_fallback).
    """
    if caption_count <= 0:
        return [], True
    if not promo_media_ids:
        return [], True
    n = len(promo_media_ids)
    offset = int(link_slot_offset) % n
    variants: list[dict[str, Any]] = []
    for i in range(caption_count):
        mid = promo_media_ids[(i + offset) % n]
        variants.append({"media_ids": [mid], "attachment_urls": []})
    return variants, False


def configure_packs_promo_pool(pool) -> None:
    """Promo pool: randomize queue; no bare pool-interval dumps (scheduler owns posts)."""
    pool.album_size = 1
    pool.randomize_queue = True
    pool.auto_post_enabled = False
    pool.interval_minutes = 0


def _backfill_modifier_size_gb(mod: LootModifier) -> None:
    """Resolve destination size once when missing (caption needs GB line)."""
    from app.services.aof_packs_post_copy import merge_pack_source_note, parse_pack_source_note

    meta = parse_pack_source_note(mod.source_note)
    if meta.size_gb is not None and meta.size_gb > 0:
        return
    dest = (meta.destination_url or "").strip()
    if not dest.startswith(("http://", "https://")):
        return
    try:
        res = resolve_to_file_host(dest)
        if res.ok and res.size_gb_hint and res.size_gb_hint > 0:
            mod.source_note = merge_pack_source_note(
                mod.source_note or "",
                size_gb=res.size_gb_hint,
                destination_url=res.destination_url or dest,
            )
    except Exception:
        logger.debug("pack size backfill skipped mod=%s", mod.id, exc_info=True)


def is_pack_candidate_url(url: str) -> bool:
    """True when URL might resolve to a downloadable pack (direct or after unwrap)."""
    kind = classify_url_host((url or "").strip())
    return kind in PACK_CANDIDATE_HOST_KINDS


def pack_pool_modifier_exists(db: Session, destination: str, wrapped: str) -> bool:
    dest = (destination or "").strip()
    gate = (wrapped or "").strip()
    if not dest and not gate:
        return False
    if gate:
        row = db.query(LootModifier.id).filter(LootModifier.target_url == gate).first()
        if row:
            return True
    if dest:
        row = (
            db.query(LootModifier.id)
            .filter(LootModifier.source_note.isnot(None))
            .filter(LootModifier.source_note.contains(dest[:180]))
            .first()
        )
        if row:
            return True
    return False


def _pack_pool_query(db: Session):
    q = db.query(LootModifier).filter(
        LootModifier.kind == "mega_pack",
        LootModifier.active.is_(True),
    )
    clauses = [LootModifier.source_note.like(f"%{m}%") for m in PACK_POOL_SOURCE_MARKERS]
    from sqlalchemy import or_

    return q.filter(or_(*clauses))


def list_active_pack_pool_modifiers(db: Session) -> list[LootModifier]:
    return _pack_pool_query(db).order_by(LootModifier.id.asc()).all()


def queue_url_to_pack_pool(
    db: Session,
    url: str,
    *,
    label: str | None = None,
    source_note: str = PACK_QUEUE_MARKER,
    weight_base: float = 1.0,
    rarity_focus: float | None = None,
    min_rarity_tier: int | None = None,
    active: bool = True,
    archive_tags: str | None = None,
    archive_entry_id: int | None = None,
    size_gb: float | None = None,
) -> dict[str, Any]:
    """
    Resolve URL → file host, gate-wrap, insert loot_modifiers (mega_pack).
    Single pool for loot room rolls and AOF PACKS scheduler.
    """
    raw = (url or "").strip()
    if not raw.startswith(("http://", "https://")):
        return {"ok": False, "error": "invalid_url"}

    pipeline = resolve_to_file_host(raw)
    if not pipeline.ok:
        return {"ok": False, "error": pipeline.error or "resolve_failed", "input_url": raw}

    note = source_note.strip() or PACK_QUEUE_MARKER
    if archive_entry_id is not None:
        note = f"{note}|archive_id={archive_entry_id}"

    try:
        payload = build_modifier_payload(
            pipeline,
            label=label,
            archive_tags=archive_tags,
            source_note=note,
        )
    except ValueError as e:
        return {"ok": False, "error": str(e), "input_url": raw}

    dest = pipeline.destination_url or ""
    gate = str(payload.get("target_url") or "")
    if pack_pool_modifier_exists(db, dest, gate):
        return {
            "ok": True,
            "duplicate": True,
            "destination_url": dest,
            "target_url": gate,
        }

    tier = int(payload.get("min_rarity_tier") or pipeline.min_rarity_tier or 3)
    if min_rarity_tier is not None:
        tier = int(min_rarity_tier)
    focus = float(rarity_focus if rarity_focus is not None else payload.get("rarity_focus") or max(tier, 5))

    merged_note = merge_pack_source_note(
        str(payload.get("source_note") or note),
        size_gb=size_gb if size_gb is not None else pipeline.size_gb_hint,
        destination_url=dest,
        gate_adm_url=payload.get("gate_adm_url"),
        gate_lv_url=payload.get("gate_lv_url"),
        theme=_infer_pack_theme(label, archive_tags),
        contents=_infer_pack_contents(label, archive_tags, None),
    )

    m = LootModifier(
        kind="mega_pack",
        label=str(payload.get("label") or label or urlparse(dest).hostname or "Pack")[:256],
        target_url=gate,
        weight_base=float(weight_base),
        rarity_focus=focus,
        min_rarity_tier=tier,
        bypass_vip=bool(payload.get("bypass_vip")),
        active=bool(active),
        source_note=merged_note[:2000],
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    try:
        from app.services.k2s_mirror_service import maybe_enqueue_k2s_mirror

        maybe_enqueue_k2s_mirror(
            int(m.id),
            label=str(payload.get("label") or m.label),
            source_note=str(payload.get("source_note") or m.source_note),
        )
    except Exception:
        pass
    return {
        "ok": True,
        "created": True,
        "modifier": {
            "id": m.id,
            "kind": m.kind,
            "label": m.label,
            "target_url": m.target_url,
            "min_rarity_tier": m.min_rarity_tier,
            "source_note": m.source_note,
        },
        "destination_url": dest,
        "pipeline_hops": pipeline.hops,
    }


def queue_archive_entry_to_pack_pool(
    db: Session,
    *,
    value: str,
    label: str | None = None,
    tags: str | None = None,
    description: str | None = None,
    archive_entry_id: int | None = None,
) -> dict[str, Any]:
    if not is_pack_candidate_url(value):
        return {"ok": False, "skipped": True, "reason": "not_pack_candidate"}
    lbl = label
    if not lbl and description:
        lbl = description[:256]
    elif not lbl and tags:
        lbl = tags.split(",")[0].strip()[:256]
    result = queue_url_to_pack_pool(
        db,
        value,
        label=lbl,
        source_note="master_archive",
        archive_tags=tags,
        archive_entry_id=archive_entry_id,
    )
    if result.get("created") and description:
        mod_id = (result.get("modifier") or {}).get("id")
        if mod_id:
            _maybe_enrich_archive_modifier(db, int(mod_id), description=description, tags=tags)
    return result


def _infer_pack_theme(label: str | None, archive_tags: str | None) -> str | None:
    from app.services.mega_pack_naming import extract_pack_theme

    for raw in (label, archive_tags):
        if not raw:
            continue
        theme = extract_pack_theme(str(raw).split(",")[0].strip())
        if theme and theme.lower() not in ("aof pack", "pack"):
            return theme
    return None


def _infer_pack_contents(
    label: str | None,
    archive_tags: str | None,
    description: str | None,
) -> list[str] | None:
    items: list[str] = []
    if description:
        for line in description.replace(",", "\n").splitlines():
            s = line.strip().lstrip("•-* ").strip()
            if s and len(s) > 2:
                items.append(s[:80])
    if not items and archive_tags:
        for part in archive_tags.split(","):
            s = part.strip()
            if s and not s.startswith("#"):
                items.append(s[:80])
    if not items and label:
        items.append(label.strip()[:80])
    return items[:12] if items else None


def _maybe_enrich_archive_modifier(
    db: Session,
    modifier_id: int,
    *,
    description: str | None,
    tags: str | None,
) -> None:
    row = db.query(LootModifier).filter(LootModifier.id == modifier_id).first()
    if not row:
        return
    contents = _infer_pack_contents(row.label, tags, description)
    theme = _infer_pack_theme(row.label, tags)
    if not contents and not theme:
        return
    row.source_note = merge_pack_source_note(
        row.source_note or "",
        theme=theme,
        contents=contents,
    )
    db.commit()


def _a_tag(lv_url: str, anchor: str) -> str:
    return f'<a href="{html.escape(lv_url, quote=True)}">{html.escape(anchor)}</a>'


def _packs_footer() -> str:
    addlist_lv = manual_gate_url("addlist") or manual_gate_url("main_group") or ""
    mainhub_lv = manual_gate_url("mainhub") or ""
    return (
        "\n\n━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>Join the full AOF stack</b> — one tap\n"
        f'{_a_tag(addlist_lv, "addlist all channels")} · '
        f'hub {_a_tag(mainhub_lv, "aofmainhub")}\n'
        "🗝 @aofsubscriptions_bot · /loot · /subscribe · /referral"
    )


def refresh_aof_packs_scheduler(db: Session) -> dict[str, Any]:
    """Wire AOF PACKS scheduler: ~50 caption templates + send-time pack picker (full pool)."""
    from app.models.content_pool import ContentPool
    from app.models.scheduled_text_post import ScheduledTextPost

    pool = db.query(ContentPool).filter(ContentPool.name == POOL_NAME).first()
    sched = db.query(ScheduledTextPost).filter(ScheduledTextPost.name == SCHED_NAME).first()
    if not pool or not sched:
        return {"ok": False, "error": "missing_pool_or_scheduler"}

    mods = list_active_pack_pool_modifiers(db)
    if not mods:
        return {"ok": False, "error": "no_pack_pool_modifiers", "modifier_count": 0}

    templates = pack_caption_template_variations()
    if not templates:
        return {"ok": False, "error": "no_caption_templates"}

    first_gates = resolve_pack_gate_urls(mods[0])
    primary_adm_parts = (first_gates.gate_adm_url or mods[0].target_url or "").strip().split()
    primary_adm = primary_adm_parts[0] if primary_adm_parts else ""
    primary_lv_parts = (first_gates.gate_lv_url or "").strip().split()
    primary_lv = primary_lv_parts[0] if primary_lv_parts else ""
    addlist_lv = manual_gate_url("addlist") or manual_gate_url("main_group") or ""
    button_row: list[dict[str, str]] = []
    if primary_lv:
        button_row.append({"text": "🔗 Linkvertise", "url": primary_lv})
    if primary_adm:
        button_row.append({"text": "🔗 AdMaven", "url": primary_adm})
    if not button_row and primary_adm:
        button_row = [{"text": "⬇ Download Pack", "url": primary_adm}]
    buttons = json.dumps(
        [
            button_row or [{"text": "⬇ Download Pack", "url": primary_adm or primary_lv}],
            [
                {"text": "📌 Full stack addlist", "url": addlist_lv},
                {"text": "🗝 Loot Room", "url": "https://t.me/aofsubscriptions_bot?start=menu_loot"},
            ],
        ]
    )

    configure_packs_promo_pool(pool)

    sched.content = templates[0]
    sched.content_variations = json.dumps(templates)
    sched.album_variants_json = None
    sched.buttons = buttons
    sched.pool_id = pool.id
    sched.pool_only_mode = False
    sched.pool_randomize = True
    sched.album_size = 5
    sched.checkout_stars_enabled = True
    sched.checkout_stars_plan_id = STARS_PLAN_ID
    sched.checkout_button_label = "⭐ VIP — skip ads (500⭐)"
    sched.interval_minutes = 480
    db.commit()

    promo_ids = list_approved_packs_promo_media_ids(db, pool.id)
    with_lv = sum(1 for m in mods if resolve_pack_gate_urls(m).gate_lv_url)

    return {
        "ok": True,
        "scheduler_id": sched.id,
        "modifier_count": len(mods),
        "caption_template_count": len(templates),
        "send_time_pack_picker": True,
        "promo_media_count": len(promo_ids),
        "modifiers_with_lv": with_lv,
        "pool_only_mode": False,
        "primary_gate_url": (primary_adm or primary_lv or "")[:200],
    }


def auto_wire_packs_enabled() -> bool:
    """Re-wire AOF PACKS scheduler after pack-pool inserts. Default off — run wire script or API flag."""
    return (os.getenv("TBCC_PACK_POOL_AUTO_WIRE") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
