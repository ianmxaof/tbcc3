"""Loot Goblin + prompt-drop promo copy for Telegram schedulers (Phase 6).

Doctrine:
- Goblin teasers: clearnet bot deep links only — no Linkvertise on goblin claim paths.
- Prompt drops: one LV destination per message; channel addlist footer suppressed.
- Milestone burst: one-shot campaign rows (Loot Room, mainhub, X buffer).
"""

from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_network import BULLETIN_MARKER, MAIN_GROUP_IDENT, MAINHUB_CHANNEL_IDENT, MAINHUB_RAW
from app.models.prompt_gate import PROMPT_GATE_STATUS_PROVISIONED, PromptGate
from app.models.scheduled_text_post import ScheduledTextPost

GOBLIN_TEASER_MARKER = "👺"
PROMPT_DROP_MARKER = "AOF PROMPT DROP"
LOOT_ROOM_GOBLIN_BULLETIN_NAME = "AOF LOOT ROOM — Goblin + LGG explainer (pinned)"
MILESTONE_CAMPAIGN_ID = "ms_20260726_goblin_relay"
MILESTONE_LOOT_ROOM_SCHED_NAME = "AOF LOOT ROOM — milestone burst (one-shot)"
MILESTONE_MAINHUB_SCHED_NAME = "AOF MAINHUB — milestone burst (one-shot)"

GOBLIN_FREE_DEEP_LINK = "https://telegram.me/aof_lootgod_bot?start=loot_free"

GOBLIN_TEASER_BODY = (
    "👺 <b>Loot Goblin</b> blinks into random AOF lanes on now-playing — "
    "first 5 taps get a free DM pull.\n"
    f'<a href="{GOBLIN_FREE_DEEP_LINK}">Claim on @aof_lootgod_bot</a>'
)

MILESTONE_X_TEMPLATE = (
    "shipped: relay Bot API + loot goblin + key-roll album fix on revenue island. "
    "TBCC keeps the firehose honest. {hub} · @aof_lootgod_bot"
)


def is_bulletin_variation(text: str) -> bool:
    return BULLETIN_MARKER in (text or "")


def is_goblin_teaser_variation(text: str) -> bool:
    body = (text or "").strip()
    return GOBLIN_TEASER_MARKER in body and "Loot Goblin" in body and GOBLIN_FREE_DEEP_LINK in body


def is_prompt_drop_variation(text: str) -> bool:
    return PROMPT_DROP_MARKER in (text or "")


def build_goblin_teaser_with_footer(footer: str) -> str:
    """Network scheduler slot — clearnet claim link + standard addlist footer."""
    foot = (footer or "").strip()
    if foot and not GOBLIN_TEASER_BODY.endswith(foot):
        return f"{GOBLIN_TEASER_BODY}\n\n{foot}".strip()
    return GOBLIN_TEASER_BODY.strip()


def build_loot_room_goblin_bulletin_html() -> str:
    """Pinned Loot Room commons explainer — once per apply."""
    return (
        "👺 <b>Loot Goblin + Loot God Game</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "When the listening relay posts <b>now playing</b>, a goblin can blink into the lane — "
        "~45s to tap <b>Claim loot</b>. First 5 taps get a free DM pull.\n\n"
        "<b>Loot God Game</b> — tier card reveal → spoiler album in DM.\n"
        "Five free rolls ever, then keys / Stars on <b>@aof_lootgod_bot</b>.\n\n"
        f'Free taste: <a href="{GOBLIN_FREE_DEEP_LINK}">@aof_lootgod_bot</a>\n'
        "<i>No Linkvertise on goblin drops — claim links stay clearnet.</i>"
    )


def build_prompt_drop_html(
    *,
    gate_url: str,
    title: str,
    teaser: str = "",
    tier_label: str | None = None,
) -> str:
    """Single LV destination — channel footer must not be appended."""
    url = (gate_url or "").strip()
    if not url:
        raise ValueError("gate_url required for prompt drop")
    head = f"🎴 <b>{PROMPT_DROP_MARKER}</b> — {html.escape(title)}"
    if tier_label:
        head += f" <i>({html.escape(tier_label)})</i>"
    body = (teaser or "").strip() or "Unlock the full prompt pack behind one ad gate."
    gate_link = f'<a href="{html.escape(url, quote=True)}">Unlock prompt</a>'
    out = f"{head}\n\n{body}\n\n{gate_link}"
    from app.services.prompt_gate_placement import validate_prompt_drop_html

    validate_prompt_drop_html(out)
    return out


def build_milestone_loot_room_html() -> str:
    return (
        "🚢 <b>Milestone ship</b>\n"
        "Listening relay on Bot API · Loot Goblin live · album delivery fixed on revenue island.\n"
        "The maze still earns — @aof_lootgod_bot · @aofsubscriptions_bot"
    )


def build_milestone_mainhub_html() -> str:
    return (
        "🚢 <b>TBCC milestone</b> — relay + goblin + island album fix.\n"
        f'Full network map: <a href="{MAINHUB_RAW}">@aofmainhub</a> · rolls @aof_lootgod_bot'
    )


def inject_goblin_teaser_variations(
    variations: list[str],
    teaser_bodies: list[str],
    *,
    every_nth: int = 6,
) -> list[str]:
    """Insert goblin teaser slots ~1 per `every_nth` non-bulletin rotations."""
    if every_nth < 2:
        every_nth = 6
    teasers = [t.strip() for t in teaser_bodies if (t or "").strip()]
    if not teasers:
        return list(variations)

    base: list[str] = []
    for v in variations:
        if is_goblin_teaser_variation(v):
            continue
        base.append(v)

    out: list[str] = []
    teaser_idx = 0
    rot_slot = 0
    for i, v in enumerate(base):
        out.append(v)
        if i == 0 and is_bulletin_variation(v):
            continue
        rot_slot += 1
        if rot_slot > 0 and rot_slot % every_nth == 0:
            teaser = teasers[teaser_idx % len(teasers)]
            teaser_idx += 1
            if teaser not in out:
                out.append(teaser)
    return out


def append_prompt_drop_variations(db: Session, variations: list[str]) -> list[str]:
    """Append provisioned prompt_gate rows as footer-free rotation slots (AI lane)."""
    seen = {v.strip() for v in variations}
    out = list(variations)
    rows = (
        db.query(PromptGate)
        .filter(
            PromptGate.status == PROMPT_GATE_STATUS_PROVISIONED,
            PromptGate.superseded_by_id.is_(None),
        )
        .order_by(PromptGate.key.asc())
        .all()
    )
    for row in rows:
        url = (row.lv_url or "").strip()
        if not url:
            continue
        title = (row.prompt_ref or row.key or "prompt").rsplit("/", 1)[-1].replace("_", " ")
        body = build_prompt_drop_html(gate_url=url, title=title, tier_label=row.tier)
        key = body.strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(body)
    return out


def strip_prompt_drop_footer(caption: str, clean_footer: str) -> str:
    """Return prompt-drop caption unchanged — never append channel footer."""
    from app.services.aof_vip_checkout import scrub_caption_for_network_post

    return scrub_caption_for_network_post(caption or "")


def upsert_loot_room_goblin_bulletin(
    db: Session,
    *,
    channel_id: int,
    execute: bool,
) -> dict[str, Any]:
    """Pinned Loot Room goblin + LGG explainer."""
    content = build_loot_room_goblin_bulletin_html()
    sched = (
        db.query(ScheduledTextPost)
        .filter(
            ScheduledTextPost.channel_id == channel_id,
            ScheduledTextPost.name == LOOT_ROOM_GOBLIN_BULLETIN_NAME,
        )
        .first()
    )
    entry: dict[str, Any] = {
        "name": LOOT_ROOM_GOBLIN_BULLETIN_NAME,
        "channel_id": channel_id,
        "chars": len(content),
    }
    if sched:
        entry["id"] = sched.id
        entry["status"] = "exists"
        if execute:
            sched.content = content
            sched.pin_after_send = True
            sched.send_silent = False
            sched.scheduler_category = sched.scheduler_category or "promo_bulletin"
            entry["status"] = "updated"
    else:
        entry["status"] = "would_create"
        if execute:
            sched = ScheduledTextPost(
                name=LOOT_ROOM_GOBLIN_BULLETIN_NAME,
                channel_id=channel_id,
                content=content,
                pin_after_send=True,
                send_silent=False,
                created_at=datetime.now(timezone.utc),
                scheduler_category="promo_bulletin",
            )
            db.add(sched)
            db.flush()
            entry["id"] = sched.id
            entry["status"] = "created"
    return entry


def upsert_milestone_burst_posts(
    db: Session,
    *,
    loot_room_channel_id: int,
    mainhub_channel_id: int | None,
    execute: bool,
    fire_in_minutes: int = 5,
) -> list[dict[str, Any]]:
    """One-shot milestone burst — Loot Room + mainhub (X via buffer mirror on loot room scheduler)."""
    when = datetime.now(timezone.utc) + timedelta(minutes=max(1, int(fire_in_minutes)))
    rows: list[dict[str, Any]] = []

    specs: list[tuple[str, int, str, bool]] = [
        (MILESTONE_LOOT_ROOM_SCHED_NAME, loot_room_channel_id, build_milestone_loot_room_html(), True),
    ]
    if mainhub_channel_id:
        specs.append(
            (MILESTONE_MAINHUB_SCHED_NAME, mainhub_channel_id, build_milestone_mainhub_html(), False)
        )
    for name, cid, content, buffer_mirror in specs:
        sched = (
            db.query(ScheduledTextPost)
            .filter(ScheduledTextPost.channel_id == cid, ScheduledTextPost.name == name)
            .first()
        )
        entry: dict[str, Any] = {"name": name, "channel_id": cid, "campaign": MILESTONE_CAMPAIGN_ID}
        if sched and sched.sent_at is not None:
            entry["id"] = sched.id
            entry["status"] = "already_sent"
            rows.append(entry)
            continue
        if sched:
            entry["id"] = sched.id
            entry["status"] = "exists"
            if execute:
                sched.content = content
                sched.scheduled_at = when
                sched.sent_at = None
                sched.campaign_group_id = MILESTONE_CAMPAIGN_ID
                sched.buffer_mirror_enabled = buffer_mirror
                sched.buffer_publish_now = False
                sched.scheduler_category = "manual"
                entry["status"] = "updated"
        else:
            entry["status"] = "would_create"
            if execute:
                sched = ScheduledTextPost(
                    name=name,
                    channel_id=cid,
                    content=content,
                    scheduled_at=when,
                    pin_after_send=False,
                    send_silent=False,
                    created_at=datetime.now(timezone.utc),
                    campaign_group_id=MILESTONE_CAMPAIGN_ID,
                    buffer_mirror_enabled=buffer_mirror,
                    buffer_publish_now=False,
                    scheduler_category="manual",
                )
                db.add(sched)
                db.flush()
                entry["id"] = sched.id
                entry["status"] = "created"
        rows.append(entry)
    return rows


def sync_goblin_teasers_on_scheduler(
    sched: ScheduledTextPost,
    *,
    footer: str,
    every_nth: int = 6,
) -> int:
    """Inject goblin teaser slots on an existing scheduler; returns new variation count."""
    existing = sched.get_content_variations() or ([sched.content] if sched.content else [])
    teaser = build_goblin_teaser_with_footer(footer)
    merged = inject_goblin_teaser_variations(existing, [teaser], every_nth=every_nth)
    sched.content = merged[0]
    sched.content_variations = __import__("json").dumps(merged) if len(merged) > 1 else None
    return len(merged)


def channel_id_for_ident(db: Session, ident: str) -> int | None:
    from app.models.channel import Channel

    row = db.query(Channel).filter(Channel.identifier == ident).first()
    return int(row.id) if row else None
