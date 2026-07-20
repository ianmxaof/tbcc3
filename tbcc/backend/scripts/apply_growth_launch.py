"""
Growth launch: production growth settings, links hub bulletin, AOF PACKS copy,
addlist footers on all channel schedulers, and /loot · /subscribe · /referral rotation jobs.

  cd tbcc/backend
  py -3.13 scripts/apply_growth_launch.py              # preview
  py -3.13 scripts/apply_growth_launch.py --execute
  py -3.13 scripts/apply_growth_launch.py --execute --post-bulletin --post-commands
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.mega_scrape_channel_sources import AOF_PACKS_CHANNEL_ID
from app.database.session import SessionLocal
from app.models.channel import Channel
from app.models.content_pool import ContentPool
from app.models.growth_settings import GrowthSettings
from app.models.loot import LootModifier
from app.models.media import Media
from app.models.scheduled_text_post import ScheduledTextPost
from app.services.growth_settings_effective import ROW_ID
from app.data.aof_manual_gate_links import manual_gate_url, manual_gate_urls
from app.services.link_gate_provider import wrap_gate_url

MAIN_GROUP_IDENT = "-1003206350461"
MAIN_GROUP_INVITE = "https://t.me/+rk8ra7fPJ1QzZDMx"
ADDLIST_RAW = "https://t.me/addlist/r-7_7CGIkExhMDcx"
MAINHUB_RAW = "https://telegram.me/aofmainhub"

# Content channels listed in the links hub bulletin (raw invites → LV-wrapped at runtime).
BULLETIN_CHANNEL_INVITES: dict[str, tuple[str, str]] = {
    "ai": ("AOF AI", "https://t.me/+4umB83be5n41MmEx"),
    "ass": ("AOF ASS", "https://t.me/+gQaguoQE7eM4MzA5"),
    "blowjob": ("AOF BLOWJOB", "https://t.me/+3jeQNQhcOSU4ZTcx"),
    "big_tits": ("AOF BIG TITS", "https://t.me/+vPhWRgtpteI4NTdh"),
    "milf": ("AOF MILF", "https://t.me/+AY0zGwyeAy9jNDIx"),
    "taboo": ("AOF TABOO", "https://t.me/+w46b7uJK5eo0MDcx"),
    "voyeur": ("AOF PUBLIC VOYEUR", "https://t.me/+ag3BSf3fliwyYTgx"),
    "abg": ("AOF ABG / LBFM", "https://t.me/+4Hs9iMZpIDQ5NjMx"),
    "packs": ("AOF PACKS", "https://t.me/+xCtxqzQEuoRmZGZh"),
    "goon": ("AOF GOON", "https://t.me/+jKGzJMZAhCZjNjdh"),
    "bop": ("AOF BOP", "https://t.me/+woiIGJFd19NmZjkx"),
    "loot": ("AOF LOOT ROOM", "https://t.me/+97f4Crv3G1RkMGU5"),
}

NEW_CHANNELS: tuple[tuple[str, str, str, str], ...] = (
    ("AOF GOON", "-1003809663025", "https://t.me/+jKGzJMZAhCZjNjdh", "AOF GOON POOL"),
    ("AOF BOP", "-1003763051030", "https://t.me/+woiIGJFd19NmZjkx", "AOF BOP POOL"),
)

BULLETIN_SCHED_NAME = "AOF MAIN — Links Hub bulletin (pinned)"
PACKS_SCHED_NAME = "AOF PACKS — seed rotation"
COMMANDS_SCHED_PREFIX = "AOF — bot commands"
FOOTER_MARKER = "Join the full AOF stack"

CONTENT_SCHEDULER_NAMES = (
    "AOF MAIN GROUP + X SCHEDULER",
    "AOF AI SCHEDULER",
    "AOF BLOWJOB SCHEDULER",
    "AOF BIG TITS SCHEDULER",
    "AOF TABOO SCHEDULER",
    "AOF PUBLIC / VOYEUR SCHEDULER",
    "AOF MILF SCHEDULER",
    "AOF ASS SCHEDULER",
    "ABG / LBFM SCHEDULER",
)

PACKS_SEED_MEDIA_IDS = (2168, 2169, 2170)
EXTRA_DESTINATIONS = [
    ("Milf vault", "https://drive.newsophon.com/s2/z5Ek3AemLJ658PrvbWdM"),
    ("Blowjob pack", "https://drive.newsophon.com/s2/9WEbgLrmwejr8ev10YaK"),
]

COMMAND_VARIATIONS = ["/loot", "/subscribe", "/referral"]

# All AOF-facing channels (skip Storage hangar).
COMMAND_CHANNEL_IDS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14)  # extended after _ensure_new_channels


def _a_tag(url: str, anchor: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(anchor)}</a>'


def _lv_urls(db) -> dict[str, str]:
    return manual_gate_urls()


def build_links_hub_bulletin(lv: dict[str, str]) -> str:
    return (
        "📌 <b>AOF LINKS HUB</b>\n"
        "Central hub for AOF groups, channels, bots, &amp; resources.\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🔥 <b>MAIN COMMUNITY</b>\n"
        f"💬 Main Group: {_a_tag(lv['main_group'], 'join')}\n"
        f"🔗 Flagship hub: {_a_tag(lv['mainhub'], 'telegram.me/aofmainhub')}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📂 <b>CONTENT</b>\n"
        f"📌 {_a_tag(lv['addlist'], 'ADDLIST — all channels')}\n"
        f"👉 AOF AI: {_a_tag(lv['ai'], 'AOF AI')}\n"
        f"🔥 AOF ASS: {_a_tag(lv['ass'], 'AOF ASS')}\n"
        f"💋 AOF BLOWJOB: {_a_tag(lv['blowjob'], 'AOF BLOWJOB')}\n"
        f"🌍 AOF BIG TITS: {_a_tag(lv['big_tits'], 'AOF BIG TITS')}\n"
        f"🧔‍♀️ AOF MILF: {_a_tag(lv['milf'], 'AOF MILF')}\n"
        f"🔞 AOF TABOO: {_a_tag(lv['taboo'], 'AOF TABOO')}\n"
        f"👀 AOF PUBLIC VOYEUR: {_a_tag(lv['voyeur'], 'AOF PUBLIC VOYEUR')}\n"
        f"👧 AOF ABG / LBFM: {_a_tag(lv['abg'], 'AOF ABG / LBFM')}\n"
        f"📦 AOF PACKS: {_a_tag(lv['packs'], 'AOF PACKS')}\n"
        f"🌀 AOF GOON: {_a_tag(lv['goon'], 'AOF GOON')}\n"
        f"🎵 AOF BOP: {_a_tag(lv['bop'], 'AOF BOP')}\n"
        f"🪙 AOF LOOT ROOM: {_a_tag(lv['loot'], 'AOF LOOT ROOM')}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🤖 <b>OFFICIAL BOTS</b>\n"
        "🔓 Subscriptions &amp; Packs: @aofsubscriptions_bot\n"
        "📋 Secretary: @aof_secretary_bot\n"
        "💰 Loot God: @aof_lootgod_bot\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🚀 <b>SUPPORT AOF</b>\n"
        "💪 Boost: https://t.me/boost?c=3206350461\n"
        "🔥 Buy Premium Packs: @aofsubscriptions_bot\n"
        "📢 Referral Program: @aofsubscriptions_bot — /referral\n"
        f"📌 {_a_tag(lv['addlist'], 'ALL CHANNELS ADDLIST')}"
    )


def build_addlist_footer(lv: dict[str, str]) -> str:
    return (
        "\n\n━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>{FOOTER_MARKER}</b>\n"
        f"🌐 {_a_tag(lv['addlist'], 'addlist')} | 🔗 {_a_tag(lv['mainhub'], 'aofmainhub')}\n"
        "🗝 @aofsubscriptions_bot · /loot · /subscribe · /referral"
    )


def _append_footer(text: str, footer: str) -> str:
    body = (text or "").strip()
    if not body or FOOTER_MARKER in body:
        return body
    return body + footer


def _build_packs_captions(lv_urls: list[str], footer: str) -> list[str]:
    u = lv_urls
    anchors = ("vault", "unpack", "enter", "claim", "drop", "folder", "gate", "pull")
    bodies = [
        (
            "📦 <b>AOF PACK DROP</b>\n"
            "golden fans batch — terabox folder tagged &amp; cleared.\n"
            "you weren't invited. you clicked anyway. good."
        ),
        (
            "psy-slop parcel hour.\n"
            "another curated dump cleared the pipeline — milf lane, no filler.\n"
            "scarcity isn't cruelty. it's filtration."
        ),
        (
            "<b>PACK LIVE</b> — curated BJ lane drop, re-wrapped for AOF.\n"
            "one friction step between you and the folder. that's the seduction."
        ),
        (
            "<b>TERABOX BATCH</b> — fresh golden fans dump.\n"
            "LV gate keeps the tourists out. you already know the drill."
        ),
        (
            "milf vault hour.\n"
            "sophon folder cleared the pipeline — no filler, no apology.\n"
            "filtration is a feature."
        ),
        (
            "<b>BJ PACK</b> — curated lane drop.\n"
            "one ad step. one folder. zero regret."
        ),
        (
            "📦 <b>PIPELINE DROP</b>\n"
            "fresh lane batch — cleared, wrapped, ready.\n"
            "VIP skips the line → @aofsubscriptions_bot"
        ),
        (
            "<b>MAX PACE PACK</b>\n"
            "another folder hits the feed before you finish scrolling.\n"
            "that's the point."
        ),
    ]
    out: list[str] = []
    for i, body in enumerate(bodies):
        link = u[i % len(u)]
        anchor = anchors[i % len(anchors)]
        out.append(f"{body}\n\n{_a_tag(link, anchor)} · VIP skips the gate → @aofsubscriptions_bot{footer}")
    return out


def _ensure_growth_settings(db, execute: bool) -> dict:
    from app.services.aof_social_links import loot_public_cta_url

    loot_cta = loot_public_cta_url() or "https://telegram.me/aof_lootgod_bot"
    intro = (
        "🔥 AOF — referrals & milestones\n\n"
        "Entry: @aof_lootgod_bot (Loot Room) · Flagship hub: telegram.me/aofmainhub\n"
        "• Referrals: @aofsubscriptions_bot → /referral\n"
        "• Loot Room keys: /loot · Premium VIP: /subscribe"
    )
    patch = {
        "landing_bulletin_chat_id": MAIN_GROUP_IDENT,
        "milestone_progress_chat_id": MAIN_GROUP_IDENT,
        "landing_bulletin_hour_utc": 14,
        "landing_bulletin_bot_username": "aofsubscriptions_bot",
        "landing_bulletin_intro": intro,
        "referral_group_invite_link": loot_cta,
        "referral_group_name": "AOF Loot Room",
        "referral_reward_days": 7,
        "referral_mode": "community",
    }
    if not execute:
        return {"growth_settings": patch, "status": "preview"}
    row = db.query(GrowthSettings).filter(GrowthSettings.id == ROW_ID).first()
    if not row:
        row = GrowthSettings(id=ROW_ID)
        db.add(row)
    for k, v in patch.items():
        setattr(row, k, v)
    db.flush()
    return {"growth_settings": patch, "status": "updated"}


def _fix_main_group_invite(db, execute: bool) -> dict:
    ch = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()
    if not ch:
        return {"main_group_invite": "channel_not_found"}
    bad = (ch.invite_link or "").strip()
    if bad != MAIN_GROUP_INVITE:
        if execute:
            ch.invite_link = MAIN_GROUP_INVITE
        return {"main_group_invite": {"was": bad, "now": MAIN_GROUP_INVITE}}
    return {"main_group_invite": "ok"}


def _upsert_bulletin_sched(db, lv: dict[str, str], execute: bool) -> dict:
    bulletin = build_links_hub_bulletin(lv)
    ch = db.query(Channel).filter(Channel.identifier == MAIN_GROUP_IDENT).first()
    if not ch:
        return {"bulletin_sched": "main_group_not_found"}
    sched = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.channel_id == ch.id, ScheduledTextPost.name == BULLETIN_SCHED_NAME)
        .first()
    )
    report: dict = {"name": BULLETIN_SCHED_NAME, "channel_id": ch.id, "chars": len(bulletin)}
    if not sched:
        report["status"] = "would_create"
        if execute:
            sched = ScheduledTextPost(
                name=BULLETIN_SCHED_NAME,
                channel_id=ch.id,
                content=bulletin,
                send_silent=False,
                pin_after_send=True,
                created_at=datetime.now(timezone.utc),
                scheduler_category="promo_bulletin",
            )
            db.add(sched)
            db.flush()
            report["status"] = "created"
            report["id"] = sched.id
    else:
        report["id"] = sched.id
        report["status"] = "exists"
        if execute:
            sched.content = bulletin
            sched.pin_after_send = True
            sched.send_silent = False
            sched.interval_minutes = None
            sched.scheduler_category = sched.scheduler_category or "promo_bulletin"
            report["status"] = "updated"
    return report


def _update_packs_sched(db, lv: dict[str, str], execute: bool) -> dict:
    footer = build_addlist_footer(lv)
    pool = db.query(ContentPool).filter(ContentPool.name == "AOF PACKS — Promo").first()
    sched = (
        db.query(ScheduledTextPost)
        .filter(ScheduledTextPost.name == PACKS_SCHED_NAME)
        .order_by(ScheduledTextPost.id.desc())
        .first()
    )
    if not pool or not sched:
        return {"packs_sched": "missing_pool_or_sched"}

    mods = (
        db.query(LootModifier)
        .filter(LootModifier.kind == "mega_pack", LootModifier.active.is_(True))
        .order_by(LootModifier.id.asc())
        .all()
    )
    mod = next((m for m in mods if m.target_url and "**" not in (m.label or "")), None) or (mods[0] if mods else None)
    if not mod or not mod.target_url:
        return {"packs_sched": "no_mega_pack_modifier"}

    lv_terabox = mod.target_url.strip().split()[0]
    lv_extra = [wrap_gate_url(dest, seed=dest)[0] for _, dest in EXTRA_DESTINATIONS]
    lv_urls = [lv_terabox, lv_extra[0], lv_extra[1], lv_terabox, lv_extra[0], lv_extra[1], lv_terabox, lv_extra[0]]
    captions = _build_packs_captions(lv_urls, footer)

    from app.services.loot_pack_pool import (
        build_packs_album_variants,
        configure_packs_promo_pool,
        list_approved_packs_promo_media_ids,
    )

    promo_ids = list_approved_packs_promo_media_ids(db, pool.id)
    album_variants, pool_only = build_packs_album_variants(
        promo_ids,
        len(captions),
        link_slot_offset=len(mods),
    )

    from app.services.aof_growth_hub import checkout_button_label_for_plan, resolve_group_access_plan_id
    from app.services.aof_vip_checkout import bot_checkout_url

    vip_plan_id = resolve_group_access_plan_id(db)
    vip_url = bot_checkout_url(vip_plan_id, menu=True) or (
        f"https://t.me/aofsubscriptions_bot?start=cm{vip_plan_id}"
    )
    vip_label = checkout_button_label_for_plan(db, vip_plan_id)

    buttons = json.dumps(
        [
            [
                {"text": "⬇ Download Pack", "url": lv_terabox},
                {"text": vip_label[:64], "url": vip_url},
            ],
            [
                {"text": "📌 Full stack addlist", "url": lv["addlist"]},
                {"text": "🗝 Loot Room", "url": "https://t.me/aofsubscriptions_bot?start=menu_loot"},
            ],
        ]
    )

    report = {"id": sched.id, "variations": len(captions), "status": "preview"}
    if execute:
        configure_packs_promo_pool(pool)
        sched.content = captions[0]
        sched.content_variations = json.dumps(captions)
        sched.album_variants_json = json.dumps(album_variants) if album_variants else None
        sched.buttons = buttons
        sched.pool_id = pool.id
        sched.pool_only_mode = pool_only
        sched.pool_randomize = True
        sched.album_size = 1
        sched.interval_minutes = 480
        sched.pin_after_send = False
        sched.send_silent = False
        sched.scheduler_category = sched.scheduler_category or "promo_bulletin"
        report["status"] = "updated"
        report["promo_media_count"] = len(promo_ids)
    return report


def _append_footers_to_content_schedulers(db, footer: str, execute: bool) -> list[dict]:
    rows: list[dict] = []
    for name in CONTENT_SCHEDULER_NAMES:
        sched = db.query(ScheduledTextPost).filter(ScheduledTextPost.name == name).first()
        if not sched:
            rows.append({"name": name, "status": "not_found"})
            continue
        vars_ = sched.get_content_variations() or [sched.content or ""]
        new_vars = [_append_footer(v, footer) for v in vars_]
        changed = new_vars != vars_
        entry = {"name": name, "id": sched.id, "variations": len(new_vars), "changed": changed}
        if execute and changed:
            sched.content = new_vars[0]
            sched.content_variations = json.dumps(new_vars) if len(new_vars) > 1 else None
            sched.scheduler_category = sched.scheduler_category or "main_lane"
            entry["status"] = "updated"
        else:
            entry["status"] = "unchanged" if not changed else "would_update"
        rows.append(entry)
    return rows


def _ensure_new_channels_and_pools(db, execute: bool) -> list[dict]:
    """Register GOON/BOP channels + content pools; refresh ABG invite to current addlist link."""
    rows: list[dict] = []
    abg = db.query(Channel).filter(Channel.identifier == "-1003984584735").first()
    if abg:
        entry = {"channel": "ABG / LBFM", "id": abg.id}
        new_invite = BULLETIN_CHANNEL_INVITES["abg"][1]
        if (abg.invite_link or "").strip() != new_invite:
            entry["invite_was"] = abg.invite_link
            entry["invite_now"] = new_invite
            if execute:
                abg.invite_link = new_invite
                abg.name = "ABG / LBFM"
            entry["status"] = "invite_updated" if execute else "would_update_invite"
        else:
            entry["status"] = "ok"
        rows.append(entry)

    for name, ident, invite, pool_name in NEW_CHANNELS:
        ch = db.query(Channel).filter(Channel.identifier == ident).first()
        entry: dict = {"name": name, "identifier": ident, "pool_name": pool_name}
        if ch:
            entry["channel_id"] = ch.id
            entry["channel_status"] = "exists"
            if execute and (ch.invite_link or "").strip() != invite:
                ch.invite_link = invite
                entry["invite_updated"] = True
        else:
            entry["channel_status"] = "would_create"
            if execute:
                ch = Channel(name=name, identifier=ident, invite_link=invite)
                db.add(ch)
                db.flush()
                entry["channel_id"] = ch.id
                entry["channel_status"] = "created"

        if not ch:
            rows.append(entry)
            continue

        pool = db.query(ContentPool).filter(ContentPool.name == pool_name).first()
        if pool:
            entry["pool_id"] = pool.id
            entry["pool_status"] = "exists"
            if execute and pool.channel_id != ch.id:
                pool.channel_id = ch.id
        else:
            entry["pool_status"] = "would_create"
            if execute:
                pool = ContentPool(
                    name=pool_name,
                    channel_id=ch.id,
                    album_size=1,
                    interval_minutes=0,
                    auto_post_enabled=False,
                    randomize_queue=True,
                )
                db.add(pool)
                db.flush()
                entry["pool_id"] = pool.id
                entry["pool_status"] = "created"
        rows.append(entry)
    return rows


def _refresh_all_bulletin_schedulers(db, bulletin: str, execute: bool) -> list[dict]:
    rows: list[dict] = []
    for name in (BULLETIN_SCHED_NAME, "AOF CROSS-CHANNEL SCHEDULER"):
        scheds = (
            db.query(ScheduledTextPost)
            .filter(ScheduledTextPost.name == name)
            .order_by(ScheduledTextPost.id.asc())
            .all()
        )
        for sched in scheds:
            entry = {"id": sched.id, "name": name, "channel_id": sched.channel_id}
            if execute:
                sched.content = bulletin
                sched.pin_after_send = True
                sched.scheduler_category = sched.scheduler_category or "promo_bulletin"
                entry["status"] = "updated"
            else:
                entry["status"] = "would_update"
            rows.append(entry)
    return rows


def _upsert_command_schedulers(db, execute: bool) -> list[dict]:
    rows: list[dict] = []
    for cid in COMMAND_CHANNEL_IDS:
        ch = db.query(Channel).filter(Channel.id == cid).first()
        if not ch:
            rows.append({"channel_id": cid, "status": "channel_not_found"})
            continue
        name = f"{COMMANDS_SCHED_PREFIX} — {ch.name or cid}"
        sched = (
            db.query(ScheduledTextPost)
            .filter(ScheduledTextPost.channel_id == cid, ScheduledTextPost.name == name)
            .first()
        )
        entry = {"channel_id": cid, "channel": ch.name, "name": name}
        if sched:
            entry["id"] = sched.id
            entry["status"] = "exists"
            if execute:
                sched.content = COMMAND_VARIATIONS[0]
                sched.content_variations = json.dumps(COMMAND_VARIATIONS)
                sched.interval_minutes = 10080
                sched.send_silent = True
                sched.pin_after_send = False
                sched.scheduler_category = "bot_commands"
                entry["status"] = "updated"
        else:
            entry["status"] = "would_create"
            if execute:
                sched = ScheduledTextPost(
                    name=name,
                    channel_id=cid,
                    content=COMMAND_VARIATIONS[0],
                    content_variations=json.dumps(COMMAND_VARIATIONS),
                    interval_minutes=10080,
                    send_silent=True,
                    pin_after_send=False,
                    created_at=datetime.now(timezone.utc),
                    scheduler_category="bot_commands",
                )
                db.add(sched)
                db.flush()
                entry["id"] = sched.id
                entry["status"] = "created"
        rows.append(entry)
    return rows


def _trigger_post(post_id: int, *, sync: bool = False, countdown: int = 0) -> dict:
    from app.workers.poster_worker import post_scheduled_text

    try:
        if sync:
            post_scheduled_text(int(post_id), manual_trigger=True)
            return {"post_id": post_id, "ok": True, "mode": "sync"}
        result = post_scheduled_text.apply_async(
            args=[int(post_id)],
            kwargs={"manual_trigger": True},
            countdown=max(0, int(countdown)),
        )
        return {
            "post_id": post_id,
            "ok": True,
            "mode": "celery",
            "task_id": result.id,
            "countdown": max(0, int(countdown)),
        }
    except Exception as e:
        return {"post_id": post_id, "ok": False, "error": str(e)[:300]}


def apply(
    *,
    execute: bool,
    post_bulletin: bool,
    post_commands: bool,
    post_sync: bool = False,
    bulletin_only: bool = False,
) -> dict:
    db = SessionLocal()
    report: dict = {}
    try:
        lv = _lv_urls(db)
        bulletin_html = build_links_hub_bulletin(lv)
        report["channels_pools"] = _ensure_new_channels_and_pools(db, execute)
        report["bulletin_schedulers"] = _refresh_all_bulletin_schedulers(db, bulletin_html, execute)
        if bulletin_only:
            if execute:
                db.commit()
            else:
                db.rollback()
            if execute and post_bulletin:
                sched = (
                    db.query(ScheduledTextPost)
                    .filter(ScheduledTextPost.name == BULLETIN_SCHED_NAME)
                    .order_by(ScheduledTextPost.id.desc())
                    .first()
                )
                if sched:
                    report["bulletin_post"] = _trigger_post(int(sched.id), sync=post_sync)
            return report

        footer = build_addlist_footer(lv)
        report["growth"] = _ensure_growth_settings(db, execute)
        report["main_group_invite"] = _fix_main_group_invite(db, execute)
        report["bulletin"] = _upsert_bulletin_sched(db, lv, execute)
        report["packs"] = _update_packs_sched(db, lv, execute)
        report["content_footers"] = _append_footers_to_content_schedulers(db, footer, execute)
        report["command_schedulers"] = _upsert_command_schedulers(db, execute)
        if execute:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()

    if execute and post_bulletin and report.get("bulletin", {}).get("id"):
        report["bulletin_post"] = _trigger_post(int(report["bulletin"]["id"]), sync=post_sync)

    if execute and post_commands:
        triggered = []
        stagger = 12
        for i, row in enumerate(report.get("command_schedulers") or []):
            pid = row.get("id")
            if pid:
                triggered.append(_trigger_post(int(pid), sync=post_sync, countdown=i * stagger))
        report["command_posts"] = triggered

    return report


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--execute", action="store_true")
    p.add_argument("--post-bulletin", action="store_true", help="Send + pin main-group links hub bulletin now")
    p.add_argument("--post-sync", action="store_true", help="Post in-process (blocks; needs free poster session lock)")
    p.add_argument("--post-commands", action="store_true", help="Post /loot /subscribe /referral once per channel")
    p.add_argument("--bulletin-only", action="store_true", help="Only update bulletin + channels/pools (skip footers/commands)")
    args = p.parse_args()
    r = apply(
        execute=args.execute,
        post_bulletin=args.post_bulletin,
        post_commands=args.post_commands,
        post_sync=args.post_sync,
        bulletin_only=args.bulletin_only,
    )
    print(json.dumps(r, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
