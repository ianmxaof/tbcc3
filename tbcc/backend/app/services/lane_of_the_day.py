"""Shared UTC lane-of-the-day — mainhub spotlight + Loot Room liveness alignment."""

from __future__ import annotations

import html
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_network import network_channel_by_key
from app.services.gatekeeper_lane_picker import gatekeeper_lane_picker_keys

# Punchy hooks — shared by @aofmainhub daily spotlight + Loot Room liveness.
SPOTLIGHT_HOOKS: dict[str, str] = {
    "ai": "Into AI tools, deepfakes, and the weird pipeline? This lane is your lab.",
    "ass": "Heavy curves your thing? The ASS lane doesn't do filler.",
    "bop": "Rhythm and motion — BOP is curated drops, not tourist bait.",
    "big_tits": "Stacked and proud? BIG TITS lane filters tourists at the gate.",
    "blowjob": "Oral fixation? BLOWJOB lane is curated, zero apology.",
    "goon": "You know why you're here. GOON lane — edge until you act.",
    "milf": "Like mature curves? MILF / GILF lane exists for you.",
    "taboo": "The lane you don't mention at dinner. TABOO — you clicked anyway.",
    "voyeur": "Candid public energy? VOYEUR lane welcomes watchers.",
    "abg": "Niche taste, tight curation — ABG / LBFM doesn't dilute.",
    "full_length": "Feature films, not clip bait — FULL LENGTH lane is cinema rotation.",
}


def lane_of_day_align_enabled() -> bool:
    raw = (os.getenv("TBCC_LANE_OF_DAY_ALIGN") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def eligible_lane_keys() -> list[str]:
    """Content lanes in stable round-robin order (excludes inbox, packs, main)."""
    return gatekeeper_lane_picker_keys()


def utc_day_ordinal(when: datetime | None = None) -> int:
    dt = when or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.astimezone(timezone.utc).strftime("%Y%m%d"))


def lane_of_the_day_key(day_ordinal: int | None = None) -> str:
    """Deterministic lane key for a UTC day — each lane gets its own day in cycle."""
    keys = eligible_lane_keys()
    if not keys:
        return "ai"
    ordinal = utc_day_ordinal() if day_ordinal is None else int(day_ordinal)
    return keys[ordinal % len(keys)]


# Back-compat alias
spotlight_lane_for_day = lane_of_the_day_key
eligible_spotlight_lane_keys = eligible_lane_keys


def apply_lane_of_day_tease_media(db: Session, sched: Any, network_key: str) -> None:
    """Tease album from today's featured lane pool (not random collective)."""
    from app.models.content_pool import ContentPool
    from app.services.aof_feed_rhythm_v2 import apply_main_group_tease_media, main_group_album_size

    net_ch = network_channel_by_key(network_key)
    if not net_ch:
        apply_main_group_tease_media(sched)
        return
    pool = db.query(ContentPool).filter(ContentPool.name == net_ch.pool_name).first()
    if pool:
        sched.pool_id = pool.id
        sched.pool_collective_random = False
        sched.album_size = main_group_album_size()
        sched.pool_randomize = True
    else:
        apply_main_group_tease_media(sched)


def build_liveness_featured_spotlight(
    db: Session,
    lv: dict[str, str],
    footer: str,
    *,
    network_key: str | None = None,
    day_ordinal: int | None = None,
) -> str:
    """Loot Room lane spotlight line — aligned with @aofmainhub channel of the day."""
    from app.services.aof_growth_hub import build_checkout_caption_line, resolve_group_access_plan_id
    from app.services.aof_main_group_copy import spotlight_variation

    key = network_key or lane_of_the_day_key(day_ordinal)
    net_ch = network_channel_by_key(key)
    if not net_ch:
        return ""
    checkout = build_checkout_caption_line(resolve_group_access_plan_id(db))
    link = lv.get(key, net_ch.invite)
    hook = SPOTLIGHT_HOOKS.get(key, f"Today's featured lane: {net_ch.display_name}.")
    base = spotlight_variation(net_ch.display_name, link, checkout)
    featured = (
        f"⭐ <b>CHANNEL OF THE DAY</b> · <i>{html.escape(hook)}</i>\n"
        f"Also on <a href=\"https://telegram.me/aofmainhub\">@aofmainhub</a>.\n\n"
        f"{base}"
    )
    return featured + footer


def build_liveness_featured_drop_ticker(
    db: Session,
    footer: str,
    *,
    network_key: str | None = None,
    day_ordinal: int | None = None,
) -> str:
    """Drop ticker line naming today's featured lane."""
    key = network_key or lane_of_the_day_key(day_ordinal)
    net_ch = network_channel_by_key(key)
    if not net_ch:
        return ""
    name = html.escape(net_ch.display_name.strip() or key)
    return (
        f"🔔 <b>Today's lane: {name}</b> — window-shop on "
        f'<a href="https://telegram.me/aofmainhub">@aofmainhub</a>. '
        f"Pipeline drop incoming — stay in feed.{footer}"
    )


def refresh_lane_of_the_day_liveness(db: Session, *, execute: bool = True) -> dict[str, Any]:
    """
    Refresh Loot Room liveness spotlight + drop ticker for today's lane.
    Called from apply_network_liveness and after mainhub daily spotlight queues.
    """
    from app.data.aof_network import MAIN_GROUP_IDENT
    from app.models.channel import Channel
    from app.models.scheduled_text_post import ScheduledTextPost
    from app.services.aof_growth_hub import build_addlist_footer, gate_urls
    from app.services.aof_network_liveness import (
        DROP_TICKER_NAME,
        SPOTLIGHT_NAME,
        _build_drop_ticker_variations,
        _build_spotlight_variations,
        liveness_checkout_enabled,
    )
    from app.services.aof_growth_hub import checkout_button_label_for_plan, resolve_group_access_plan_id

    if not lane_of_day_align_enabled():
        return {"ok": True, "skipped": True, "reason": "align_disabled"}

    key = lane_of_the_day_key()
    lv = gate_urls(db)
    footer = build_addlist_footer(lv)
    main = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()
    if not main:
        return {"ok": False, "error": "main_group_not_found"}

    report: dict[str, Any] = {"ok": True, "network_key": key, "updated": []}
    plan_id = resolve_group_access_plan_id(db)
    button_label = checkout_button_label_for_plan(db, plan_id)

    spotlight_body = build_liveness_featured_spotlight(db, lv, footer, network_key=key)
    drop_body = build_liveness_featured_drop_ticker(db, footer, network_key=key)
    spotlight_vars = [spotlight_body] if spotlight_body else []
    drop_vars = [drop_body] + [v for v in _build_drop_ticker_variations(footer) if v != drop_body]

    if not spotlight_vars:
        spotlight_vars = _build_spotlight_variations(db, lv, footer)

    specs = (
        (SPOTLIGHT_NAME, spotlight_vars, True),
        (DROP_TICKER_NAME, drop_vars, False),
    )
    for name, variations, use_lane_pool in specs:
        sched = (
            db.query(ScheduledTextPost)
            .filter(ScheduledTextPost.channel_id == main.id, ScheduledTextPost.name == name)
            .first()
        )
        if not sched:
            report["updated"].append({"name": name, "status": "missing_scheduler"})
            continue
        if not execute:
            report["updated"].append({"name": name, "status": "would_update", "variations": len(variations)})
            continue
        sched.content = variations[0]
        sched.content_variations = __import__("json").dumps(variations) if len(variations) > 1 else None
        if use_lane_pool and liveness_checkout_enabled():
            from app.services.aof_growth_hub import _apply_scheduler_album_checkout

            _apply_scheduler_album_checkout(
                sched,
                None,
                db,
                plan_id=int(plan_id),
                button_label=button_label,
                preserve_album_size=True,
            )
            apply_lane_of_day_tease_media(db, sched, key)
        report["updated"].append(
            {
                "name": name,
                "status": "updated",
                "variations": len(variations),
                "lane_pool": use_lane_pool,
                "pool_id": sched.pool_id,
            }
        )

    if execute:
        db.flush()
    return report
