"""Send-time pack picker for AOF PACKS — random undropped modifier + template caption."""

from __future__ import annotations

import json
import logging
import os
import random
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.loot import LootModifier
from app.models.post_outbound_event import PostOutboundEvent
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.aof_packs_caption_templates import PACK_BODY_PLACEHOLDER
from app.services.aof_packs_post_copy import (
    build_pack_drop_caption,
    build_pack_post_album_variant,
    resolve_pack_gate_urls,
)
from app.services.loot_pack_pool import SCHED_NAME, _packs_footer, list_active_pack_pool_modifiers

logger = logging.getLogger(__name__)


@dataclass
class PacksSendContext:
    pack_modifier_id: int
    caption_html: str
    media_ids: list[int]
    buttons_json: str | None
    album_size: int


def is_packs_send_time_scheduler(post: ScheduledTextPost) -> bool:
    return (post.name or "").strip() == SCHED_NAME


def packs_send_lookback() -> int:
    raw = (os.getenv("TBCC_PACKS_SEND_LOOKBACK") or "30").strip()
    try:
        return max(5, min(200, int(raw)))
    except ValueError:
        return 30


def packs_send_prefer_lv() -> bool:
    return (os.getenv("TBCC_PACKS_SEND_PREFER_LV") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def recently_dropped_pack_modifier_ids(
    db: Session,
    *,
    scheduled_post_id: int,
    lookback: int | None = None,
) -> set[int]:
    """Pack modifier ids from recent successful sends on this scheduler."""
    n = lookback if lookback is not None else packs_send_lookback()
    rows = (
        db.query(PostOutboundEvent.extra_json)
        .filter(
            PostOutboundEvent.scheduled_post_id == int(scheduled_post_id),
            PostOutboundEvent.event_type == "scheduled_post_sent",
            PostOutboundEvent.ok.is_(True),
            PostOutboundEvent.extra_json.isnot(None),
        )
        .order_by(PostOutboundEvent.id.desc())
        .limit(n)
        .all()
    )
    out: set[int] = set()
    for (raw,) in rows:
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        pid = data.get("pack_modifier_id")
        if pid is not None:
            try:
                out.add(int(pid))
            except (TypeError, ValueError):
                pass
    return out


def _modifier_has_gate(mod: LootModifier) -> bool:
    gates = resolve_pack_gate_urls(mod)
    return bool(gates.gate_lv_url or gates.gate_adm_url or (mod.target_url or "").strip())


def pick_pack_modifier_for_send(
    db: Session,
    *,
    scheduled_post_id: int,
    exclude_ids: set[int] | None = None,
) -> LootModifier | None:
    mods = [m for m in list_active_pack_pool_modifiers(db) if _modifier_has_gate(m)]
    if not mods:
        return None

    excluded = set(exclude_ids or set())
    recent = recently_dropped_pack_modifier_ids(db, scheduled_post_id=scheduled_post_id)
    excluded |= recent

    pool = [m for m in mods if m.id not in excluded]
    if not pool:
        pool = list(mods)

    if packs_send_prefer_lv():
        with_lv = [m for m in pool if resolve_pack_gate_urls(m).gate_lv_url]
        if with_lv:
            pool = with_lv

    return random.choice(pool)


def _build_pack_buttons(mod: LootModifier) -> str:
    import json as _json

    from app.data.aof_manual_gate_links import manual_gate_url

    gates = resolve_pack_gate_urls(mod)
    primary_adm = (gates.gate_adm_url or mod.target_url or "").strip().split()
    primary_adm = primary_adm[0] if primary_adm else ""
    primary_lv = (gates.gate_lv_url or "").strip().split()
    primary_lv = primary_lv[0] if primary_lv else ""
    addlist_lv = manual_gate_url("addlist") or manual_gate_url("main_group") or ""

    button_row: list[dict[str, str]] = []
    if primary_lv:
        button_row.append({"text": "🔗 Linkvertise", "url": primary_lv})
    if primary_adm:
        button_row.append({"text": "🔗 AdMaven", "url": primary_adm})
    if not button_row:
        gate = primary_adm or primary_lv
        if gate:
            button_row = [{"text": "⬇ Download Pack", "url": gate}]

    return _json.dumps(
        [
            button_row or [{"text": "⬇ Download Pack", "url": primary_adm or primary_lv or "#"}],
            [
                {"text": "📌 Full stack addlist", "url": addlist_lv},
                {"text": "🗝 Loot Room", "url": "https://t.me/aofsubscriptions_bot?start=menu_loot"},
            ],
        ]
    )


def _inject_pack_body(template: str, body: str) -> str:
    tpl = (template or "").strip()
    if PACK_BODY_PLACEHOLDER in tpl:
        return tpl.replace(PACK_BODY_PLACEHOLDER, body.strip())
    if tpl:
        return f"{tpl}\n\n{body.strip()}"
    return body.strip()


def _peek_template_slot(post: ScheduledTextPost) -> tuple[int, str]:
    variations = post.get_content_variations()
    if variations:
        idx = (post.caption_rotation_index or 0) % len(variations)
        return idx, variations[idx]
    return 0, (post.content or "").strip()


def _advance_caption_rotation(post: ScheduledTextPost) -> None:
    variations = post.get_content_variations()
    n = len(variations)
    if n >= 2:
        idx = (post.caption_rotation_index or 0) % n
        post.caption_rotation_index = (idx + 1) % n


def build_packs_send_context(
    db: Session,
    post: ScheduledTextPost,
    *,
    pool_id: int,
    promo_ids: list[int],
) -> PacksSendContext | None:
    """Pick pack + template slot; build caption, album media, and per-pack buttons."""
    mod = pick_pack_modifier_for_send(db, scheduled_post_id=int(post.id))
    if mod is None:
        return None

    slot, template = _peek_template_slot(post)
    _advance_caption_rotation(post)

    from app.services.loot_pack_pool import _backfill_modifier_size_gb

    _backfill_modifier_size_gb(mod)
    gates = resolve_pack_gate_urls(mod)
    gate = (gates.gate_adm_url or gates.gate_lv_url or mod.target_url or "").strip().split()
    gate_url = gate[0] if gate else ""
    foot = _packs_footer()
    body = build_pack_drop_caption(mod, gate_url, foot, meta=gates)
    caption = _inject_pack_body(template, body)

    promo_mid = promo_ids[slot % len(promo_ids)] if promo_ids else None
    variant = build_pack_post_album_variant(
        db,
        mod,
        pool_id,
        promo_mid,
        previews_only_when_available=True,
    )
    media_ids = list(variant.get("media_ids") or [])
    album_size = min(10, max(1, len(media_ids) or 1))

    return PacksSendContext(
        pack_modifier_id=int(mod.id),
        caption_html=caption,
        media_ids=media_ids,
        buttons_json=_build_pack_buttons(mod),
        album_size=album_size,
    )


def resolve_packs_send_time_if_applicable(
    db: Session,
    post: ScheduledTextPost,
) -> PacksSendContext | None:
    if not is_packs_send_time_scheduler(post):
        return None
    if not post.pool_id:
        return None
    from app.services.loot_pack_pool import list_approved_packs_promo_media_ids

    promo_ids = list_approved_packs_promo_media_ids(db, int(post.pool_id))
    try:
        return build_packs_send_context(db, post, pool_id=int(post.pool_id), promo_ids=promo_ids)
    except Exception:
        logger.exception("packs send-time resolve failed post_id=%s", post.id)
        return None
