"""Creator recruitment (/model) post copy — mechanical quote-block variations for Loot Room + lane blast."""

from __future__ import annotations

import html
import os
from datetime import datetime, timezone
from typing import Literal

CreatorVariant = Literal["G", "H", "I", "J", "V4_ORANGE", "V4_MATRIX", "V4_REVEAL", "V4_DARK"]

ALL_VARIANTS: tuple[CreatorVariant, ...] = (
    "G",
    "H",
    "I",
    "J",
    "V4_ORANGE",
    "V4_MATRIX",
    "V4_REVEAL",
    "V4_DARK",
)

_PLATFORMS_BLOCK = (
    "✓ OF · Fansly · ManyVids · Fanvue\n"
    "✓ Privacy · LoyalFans · SextPanther · SextingFinder\n"
    "✓ Linktree · allmylinks · Beacons · Telegram\n"
    "✓ Snapchat · Kik · MV · Patreon"
)


def loot_bot_username() -> str:
    return (os.getenv("TBCC_LOOT_BOT_USERNAME") or "aof_lootgod_bot").strip().lstrip("@")


def model_dm_url() -> str:
    return f"https://t.me/{loot_bot_username()}?start=model"


def creator_recruitment_keyboard() -> list[list[dict[str, str]]]:
    un = loot_bot_username()
    return [
        [{"text": "📦 Creator promo · DM", "url": f"https://t.me/{un}?start=model"}],
        [
            {"text": "🎲 Free rolls", "url": f"https://t.me/{un}?start=loot_free"},
            {"text": "🔗 Link hub", "url": "https://telegram.me/aofmainhub"},
        ],
    ]


def pick_variant_for_day(*, day: datetime | None = None) -> CreatorVariant:
    dt = day or datetime.now(timezone.utc)
    idx = int(dt.strftime("%j")) % len(ALL_VARIANTS)
    return ALL_VARIANTS[idx]


def build_x_recruitment_line(*, variant: CreatorVariant | None = None) -> str:
    """Short X-safe line — no HTML."""
    v = variant or pick_variant_for_day()
    un = loot_bot_username()
    hooks = {
        "G": f"Creators: tier 5+ Loot rolls can carry your link. DM @{un} → /model",
        "H": f"ABG/LBFM creators — get in the modifier pool. @{un} /model",
        "I": f"OF · Fansly · Fanvue — one clean URL, operator review. @{un} /model",
        "J": f"Creator slot open on high-tier LootAlbums. @{un} /model in DM",
        "V4_ORANGE": f"Modifier pool intake — @{un} /model · public profile only",
        "V4_MATRIX": f"Loot God creator lanes · @{un} /model",
        "V4_REVEAL": f"Rollers see your link on tier 5+. @{un} /model",
        "V4_DARK": f"Three bonus caption slots · @{un} /model",
    }
    return hooks.get(v, hooks["G"])


def build_creator_recruitment_html(*, variant: CreatorVariant | None = None) -> str:
    v = variant or pick_variant_for_day()
    un = loot_bot_username()
    loot = f"https://telegram.me/{un}"
    hub = "https://telegram.me/aofmainhub"
    model_cmd = "/model"

    if v == "G":
        return (
            "<b>✨ CREATOR REVEAL BOARD</b> · <i>Loot Room modifier pool</i>\n\n"
            f"<b>UNDRESS · CREATOR FUNNEL</b> · TOP · <a href=\"{loot}\">LOOT</a> · "
            f"<a href=\"{hub}\">HUB</a>\n\n"
            f"<blockquote>{_PLATFORMS_BLOCK}</blockquote>\n\n"
            f"<b>Command</b>:\n<pre>{model_cmd}</pre>\n\n"
            "<blockquote expandable>⚠️ <b>Review queue</b> — paste your "
            "<i>public profile URL</i> in DM. Up to <b>3 bonus slots</b> on tier 5+ rolls.</blockquote>\n\n"
            "<tg-spoiler>High-tier rollers only · not spammed in-channel.</tg-spoiler>"
        )

    if v == "H":
        return (
            "<b>🌐 CREATOR SLOT MATRIX</b> · <i>tier 5+ caption pool</i>\n\n"
            f"<blockquote>▸ OF · Fansly · MV · Fanvue\n"
            "▸ Privacy · SextPanther · SextingFinder\n"
            "▸ Link hubs · Telegram · Snap · Kik</blockquote>\n\n"
            "⚡ <b>APPLY</b>\n"
            f"<pre>{model_cmd}</pre>\n\n"
            f"<blockquote expandable>💡 Three creator modifiers can attach under a LootAlbum. "
            f"DM <a href=\"{model_dm_url()}\">@{html.escape(un)}</a> after /model.</blockquote>"
        )

    if v == "I":
        panel = (
            "╭─ MODIFIER POOL ─────────────╮\n"
            "│ tier 5+ rolls · 3 link slots │\n"
            "│ operator review · clean URLs │\n"
            "╰─────────────────────────────╯"
        )
        return (
            "<b>🎁 CREATOR PROMO PANEL</b> · <i>AOF LOOT ROOM</i>\n\n"
            f"<pre>{html.escape(panel)}</pre>\n\n"
            f"Platforms: OF, Fansly, MV, Fanvue, Privacy, SextPanther, Linktree, TG, Snap, Kik.\n\n"
            f"<b>Start:</b> <code>{model_cmd}</code>\n\n"
            "<tg-spoiler>DM opens · paste URL · optional display name · approve/reject DM</tg-spoiler>\n\n"
            "<blockquote expandable>🔒 Max 3 submissions / 24h · 5 pending+active per account.</blockquote>"
        )

    if v == "J":
        return (
            "<b>Did you know?</b> 🤔 Creators with a public NSFW profile can join the "
            "<b>Loot modifier pool</b>:\n\n"
            f"<pre>{model_cmd}</pre>\n\n"
            "<blockquote expandable>Paste your URL in DM → review → live on tier <b>5+</b> captions. 🎁</blockquote>\n\n"
            "<tg-spoiler>No gate links · no redirects · one clean profile URL.</tg-spoiler>"
        )

    if v == "V4_ORANGE":
        frame = (
            "╭──────────────────────────────╮\n"
            "│   CREATOR · MODIFIER POOL    │\n"
            "╰──────────────────────────────╯\n"
            " MAIN · COMM · CREATOR INTAKE\n"
            f" LOOT  {loot}\n"
            f" HUB   {hub}\n"
            "\n"
            " ——— PLATFORMS ———\n"
            " OF · Fansly · MV · Fanvue\n"
            " Privacy · SextPanther · Finder\n"
            " Linktree · TG · Snap · Kik\n"
            "\n"
            f" ——— APPLY: {model_cmd} in DM ———"
        )
        return (
            "<b>📌 AOF CREATOR INTAKE</b> · <i>ORANGE PANEL</i>\n"
            f"<blockquote><pre>{html.escape(frame)}</pre></blockquote>\n"
            f"DM <a href=\"{model_dm_url()}\">@{html.escape(un)}</a> · private review queue"
        )

    if v == "V4_MATRIX":
        return (
            "<b>STORAGE HUB / CREATOR INTAKE</b>\n"
            "<blockquote>"
            "<b>AI · CREATOR · LANES</b>\n"
            "UNDRESS · GENERATOR · APPLY\n"
            f"&gt;&gt;&gt; {model_cmd} · <a href=\"{model_dm_url()}\">@{html.escape(un)}</a> DM\n"
            f"&gt;&gt;&gt; {_PLATFORMS_BLOCK.replace(chr(10), chr(10) + '&gt;&gt;&gt; ')}\n"
            "————| MAINBOTS |————\n"
            " SEC @aof_secretary_bot\n"
            " LOOT @aof_lootgod_bot\n"
            " SPICY @aof_spicybot_bot\n"
            "————| SUPPORT |————\n"
            "/loot · /subscribe · /refer\n"
            f"<a href=\"{hub}\">Link hub</a> · <a href=\"{loot}\">Free rolls</a>"
            "</blockquote>"
        )

    if v == "V4_REVEAL":
        dots = (
            f"···· UNDRESS · CREATOR · tap /model ····\n"
            f"✓ <a href=\"{model_dm_url()}\">@{html.escape(un)}</a> · DM review queue········\n"
            f"✓ Tier 5+ · up to 3 modifier links············\n"
            f"✓ OF · Fansly · Fanvue · Privacy·············\n"
            "···· MAINBOTS ·····\n"
            " Secretary · Loot God · Spicy\n"
            "···· SUPPORT ·····\n"
            f"/model · <a href=\"{hub}\">@aofmainhub</a>"
        )
        return (
            "<b>✅ CREATOR REVEAL BOARD</b> · <i>tap a lane</i>\n"
            f"<blockquote expandable>{dots}</blockquote>"
        )

    # V4_DARK — symmetric mechanical
    rows = (
        "▶ ⏺ ⏺  CREATOR POOL  ·  tier 5+ rolls  ◀ ◀\n"
        f"▶ ⏺ ⏺  CMD  {model_cmd}  ·  DM @{un}  ◀ ◀\n"
        "▶ ⏺ ⏺  OF · Fansly · MV · Fanvue  ◀ ◀\n"
        "▶ ⏺ ⏺  Privacy · Panther · Finder  ◀ ◀\n"
        "▶ ⏺ ⏺  Linktree · TG · Snap · Kik  ◀ ◀"
    )
    return (
        "<b>🧠 CREATOR · DARK PANEL</b> · <i>V4</i>\n"
        f"<blockquote><pre>{html.escape(rows)}</pre></blockquote>\n"
        f"<a href=\"{model_dm_url()}\">Open @{html.escape(un)}</a> · paste public profile URL"
    )
