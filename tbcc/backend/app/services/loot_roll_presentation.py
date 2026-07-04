"""Decorative roll framing: dividers, flavor copy banks, high-tier celebration."""

from __future__ import annotations

import html
import random
from typing import Any

# Decorative separators between consecutive rolls in a chat (HTML).
ROLL_DIVIDERS: list[str] = [
    "━━━━━━━━━━━━━━━━\n🎰 <i>next pull</i> 🎰\n━━━━━━━━━━━━━━━━",
    "· · · ✦ · · ·\n<i>rolling…</i>\n· · · ✦ · · ·",
    "╭─────────────────╮\n│  🎲  <i>new draw</i>  🎲  │\n╰─────────────────╯",
    "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n✨ <i>loot table</i> ✨\n▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰",
    "┈┈┈ 🎁 ┈┈┈\n<i>fresh roll</i>\n┈┈┈ 🎁 ┈┈┈",
    "══════════════════\n🃏 <i>deal the cards</i> 🃏\n══════════════════",
]

TIER_FLAVOR_BANKS: dict[int, list[str]] = {
    1: [
        "The vault coughs up crumbs. Squint harder.",
        "A whisper of dust — barely worth the tap.",
        "Low stakes, low heat. Still counts as a pull.",
        "The room yawns. Something flickered anyway.",
    ],
    2: [
        "Not quite nothing. Not quite a drop.",
        "A shadow moved behind the spoiler blur.",
        "Thin pull — but the reel still spun.",
        "Glimpse-tier: enough to keep you curious.",
    ],
    3: [
        "Warm enough to keep scrolling.",
        "A single spark — the floor noticed you.",
        "Small flame, real enough to unwrap.",
        "Spark tier: modest, but the blur hides something.",
    ],
    4: [
        "Rhythm picks up — spoilers earned.",
        "The pulse tier hits different on a streak.",
        "Room energy shifts — you're on the board.",
        "Mid-low heat; the album might surprise you.",
    ],
    5: [
        "More on the reel than you expected.",
        "Surge tier — modifiers start whispering.",
        "The table leans in. Worth the unwrap.",
        "Halfway up the ladder — feel the pull.",
    ],
    6: [
        "Photos stack, video hits — feel the pull.",
        "Blaze energy — mixed media flex.",
        "Spotlight tier: density climbing.",
        "The vault opens wider at this band.",
    ],
    7: [
        "Rare enough that a bundle might follow.",
        "Vault-tier pull — packs may whisper.",
        "Heavy hitters live in this band.",
        "Seven deep — bonus routes get plausible.",
    ],
    8: [
        "This is why you paid attention.",
        "Crown tier — album density spikes.",
        "The room applauds. Open everything.",
        "Eight deep — confetti weather starts here.",
    ],
    9: [
        "The overseer grins. Open everything.",
        "Oracle tier — modifiers stack with intent.",
        "Near-mythic heat. Screenshot energy.",
        "Nine bells — the table is yours tonight.",
    ],
    10: [
        "🔥 Peak dopamine. Screenshot the receipts. 🔥",
        "MAX TIER — the vault throws a party.",
        "Ascension drop. Tell your group chat.",
        "Ten out of ten. This is the flex roll.",
    ],
}

TIER_CELEBRATION: dict[int, str] = {
    8: "💫 🎊 💫",
    9: "✨ 🎊 ✨ 🎊 ✨",
    10: "🎆 🌟 🎊 🌟 🎆",
}

# Per-tier decorative frames (opening banners + album caption chrome).
TIER_CARD_FRAMES: dict[int, tuple[str, str]] = {
    1: ("▫️ ▫️ ▫️", "▫️ ▫️ ▫️"),
    2: ("▫️ ✦ ▫️", "▫️ ✦ ▫️"),
    3: ("─ ✨ ─", "─ ✨ ─"),
    4: ("╭─ ⚡ ─╮", "╰─ ⚡ ─╯"),
    5: ("╔═ 🔥 ═╗", "╚═ 🔥 ═╝"),
    6: ("▰▰ 💎 ▰▰", "▰▰ 💎 ▰▰"),
    7: ("◆══ 🗝 ══◆", "◆══ 🗝 ══◆"),
    8: ("✦══ 👑 ══✦", "✦══ 👑 ══✦"),
    9: ("★══ 🔮 ══★", "★══ 🔮 ══★"),
    10: ("🎆══ ⭐ ══🎆", "🎆══ ⭐ ══🎆"),
}


def tier_card_frame_lines(tier: int) -> tuple[str, str]:
    t = max(1, min(10, int(tier)))
    return TIER_CARD_FRAMES.get(t, TIER_CARD_FRAMES[1])


def wrap_tier_card_body(tier: int, body: str) -> str:
    top, bottom = tier_card_frame_lines(tier)
    return f"{top}\n{body}\n{bottom}"


def build_album_caption_html(
    preview: dict[str, Any],
    *,
    modifier_lines: list[str],
    item_count: int,
) -> str:
    """First album item caption: tier card + up to 3 modifier slots inline."""
    from app.services.loot_tier_catalog import tier_display_name

    tier = int(preview.get("rarity_tier") or 1)
    title = html.escape(tier_display_name(tier))
    count = max(1, int(item_count))
    header = f"<b>{title}</b> · {count} item(s)"

    slot_count = int(preview.get("modifier_slot_count") or 0)
    mod_block = ""
    if slot_count > 0 and modifier_lines:
        shown = modifier_lines[: min(3, slot_count, len(modifier_lines))]
        bullets = "\n".join(shown)
        mod_block = f"\n\n<b>✦ Modifiers</b> ({len(shown)})\n{bullets}"
    elif slot_count > 0:
        mod_block = f"\n\n<b>✦ Modifiers</b>\n<i>— none matched this tier —</i>"

    body = header + mod_block
    return wrap_tier_card_body(tier, body)


def format_modifier_caption_lines(
    modifiers: list[dict[str, Any]],
) -> list[str]:
    """HTML lines for caption slots (links when HTTPS-safe for Telegram)."""
    from app.utils.telegram_promo_url import is_public_https_for_telegram

    lines: list[str] = []
    for m in modifiers:
        kind = (m.get("kind") or "").strip().lower()
        if kind == "local_zip_pack":
            label = html.escape((m.get("label") or "zip pack").strip())
            lines.append(f"📦 {label} <i>(file follows)</i>")
            continue
        label = html.escape((m.get("label") or m.get("kind") or "bonus").strip())
        url = (m.get("target_url") or "").strip()
        if url and is_public_https_for_telegram(url):
            lines.append(f"• {label} — <a href=\"{html.escape(url, quote=True)}\">open</a>")
        elif url:
            lines.append(f"• {label}")
        else:
            lines.append(f"• {label}")
    return lines


def pick_roll_divider_html(rng: random.Random | None = None) -> str:
    r = rng or random.Random()
    return r.choice(ROLL_DIVIDERS)


def pick_tier_flavor(tier: int, rng: random.Random | None = None) -> str:
    t = max(1, min(10, int(tier)))
    bank = TIER_FLAVOR_BANKS.get(t) or TIER_FLAVOR_BANKS[1]
    r = rng or random.Random()
    return r.choice(bank)


def tier_celebration_line(tier: int) -> str | None:
    return TIER_CELEBRATION.get(max(1, min(10, int(tier))))


def build_roll_divider_html(preview: dict[str, Any]) -> str:
    seed = preview.get("seed")
    rng = random.Random(seed) if seed is not None else random.Random()
    return pick_roll_divider_html(rng)
