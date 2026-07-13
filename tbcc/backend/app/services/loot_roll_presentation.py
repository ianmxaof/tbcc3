"""Decorative roll framing: dividers, flavor copy banks, high-tier celebration."""

from __future__ import annotations

import html
import random
from typing import Any

# Between consecutive rolls only (not menus). Telegram HTML <pre> = monospace ASCII.
ROLL_DIVIDERS: list[str] = [
    "<pre>┌──── AOF LOOT ────┐\n│   next pull…     │\n└──────────────────┘</pre>",
    "<pre>═══ TIER GATE ═══\n   rolling…\n═══ · · · · ═══</pre>",
    "<pre>╱╱╱ DRAW ╱╱╱\n world ladder ticks\n╲╲╲ ······ ╲╲╲</pre>",
    "<pre>┌─ ROLL ─┐\n│ 1-1 ▸ … │\n└─────────┘</pre>",
    "<pre>┈┈┈ TIER GATE ┈┈┈\n    deal the cards\n┈┈┈ · · · · ┈┈┈</pre>",
    "<pre>╔══════════════╗\n║  loot table  ║\n╚══════════════╝</pre>",
    "<pre>· · · SHUFFLE · · ·\n  vault breathes\n· · · · · · · ·</pre>",
    "<pre>── DEALING ──\n cards face down\n── ······ ──</pre>",
    "<pre>« RARITY SPIN »\n   hold still…\n« · · · · · »</pre>",
    "<pre>⌈ LOOT ⌋\n assembling album\n⌊······⌉</pre>",
]

# Shown after tier banner / divider while media bytes load (can take a while).
ROLL_PREPARING_LINES: list[str] = [
    "Relax — the roll is being prepared.",
    "Hold up — vault's loading your album.",
    "Sit tight. Cards are coming off the table.",
    "Breathe. The blur's still cooking.",
    "One sec — packing your pull.",
    "Don't refresh. Media is on the way.",
    "Patience — spoilers are assembling.",
    "Still dealing. This can take a moment.",
    "Almost there — fetching the album stack.",
    "Stay with me. Loot God doesn't ghost mid-deal.",
    "Loading the reel… relax your thumb.",
    "Table's busy. Your pull is not forgotten.",
]

ROLL_STILL_WORKING_LINES: list[str] = [
    "Still working — big files take a beat.",
    "Not stuck. Still pulling media from the vault.",
    "Hang on — album transfer still in flight.",
    "Almost dealt. Don't tap Roll again yet.",
]

ROLL_DEAL_FAILED_LINES: list[str] = [
    "Deal failed after the table flash — no album landed. Tap <b>/roll</b> again.",
    "The tier banner showed, but media never arrived. Retry <b>/roll</b> — that pull didn't count as a win.",
    "Vault hiccup: draw called, album missing. Try once more.",
]

# Bot-side status before API returns (loot_bot).
ROLL_LOADING_STATUS_LINES: list[str] = [
    "Dealing your pull…",
    "Spinning the table…",
    "Asking the vault…",
    "Rarity dice in the air…",
    "Loot God is dealing…",
]

TIER_FLAVOR_BANKS: dict[int, list[str]] = {
    1: [
        "The vault coughs up crumbs. Squint harder.",
        "Barely a taste. Still counts as a pull.",
        "Low heat. The room barely notices you.",
        "Crumb-tier — thin, but the reel spun.",
        "Fresh low draw — the ladder starts here sometimes.",
    ],
    2: [
        "Skirt lifts. Nothing promised.",
        "A shadow moved behind the spoiler blur.",
        "Peek-tier: enough to keep you curious.",
        "Thin pull — the door is only cracked.",
        "Independent draw: Peek can land after a hotter roll.",
    ],
    3: [
        "Someone left the door cracked.",
        "Amateur heat. Wet enough to keep scrolling.",
        "Leak-tier: modest, but the blur hides something.",
        "A single drip — the floor noticed you.",
    ],
    4: [
        "The room starts breathing with you.",
        "Rhythm picks up — spoilers earned.",
        "Throb-tier — mid-band heat on this draw.",
        "Mid-low heat; the album might surprise you.",
    ],
    5: [
        "Mid-heat. You're not leaving yet.",
        "More on the reel than you expected.",
        "Drip-tier — modifiers start whispering.",
        "Halfway band — hands already dirty.",
    ],
    6: [
        "Photos stack, video hits — feel the pull.",
        "Soak energy — mixed media flex.",
        "Density climbing. No soft lighting.",
        "The vault opens wider at this band.",
    ],
    7: [
        "Vault opens. Packs may follow.",
        "Filth-tier — rare enough that a bundle might follow.",
        "Heavy hitters live in this band.",
        "Seven deep — bonus routes get plausible.",
    ],
    8: [
        "Density spikes. No soft landing.",
        "Ruin-tier — this is why you paid attention.",
        "The room applauds. Open everything.",
        "Eight deep — confetti of sin starts here.",
    ],
    9: [
        "Near-mythic. Modifiers stack mean.",
        "Blackout-tier — the overseer grins.",
        "Screenshot the mess. Almost max.",
        "Nine bells — the table is yours tonight.",
    ],
    10: [
        "MAX TIER — screenshot the mess.",
        "Godroll. Peak filth. Tell your group chat.",
        "The vault throws a party. No survivors.",
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
    1: ("···· crumb ····", "···· ···· ····"),
    2: ("· > peek_ ·", "· · · · ·"),
    3: ("─ leak ─", "─ ▓▓▓ ─"),
    4: ("╭─ throb ─╮", "╰─ ▁▃▅ ─╯"),
    5: ("╔═ drip ═╗", "╚═ │││ ═╝"),
    6: ("▰ soak ▰", "▰ ▰ ▰ ▰"),
    7: ("◆══ filth ══◆", "◆══ ⌂⌂⌂ ══◆"),
    8: ("✦══ ruin ══✦", "✦══ ♛♛♛ ══✦"),
    9: ("★══ blackout ══★", "★══ ▓░█ ══★"),
    10: ("*** godroll ***", "*** TIER MAX ***"),
}


def tier_card_frame_lines(tier: int) -> tuple[str, str]:
    t = max(1, min(10, int(tier)))
    return TIER_CARD_FRAMES.get(t, TIER_CARD_FRAMES[1])


def wrap_tier_card_body(tier: int, body: str) -> str:
    top, bottom = tier_card_frame_lines(tier)
    return f"<code>{html.escape(top)}</code>\n{body}\n<code>{html.escape(bottom)}</code>"


def build_album_caption_html(
    preview: dict[str, Any],
    *,
    modifier_lines: list[str],
    item_count: int,
    affiliate_footer_html: str | None = None,
) -> str:
    """First album item caption: tier card + up to 3 modifier slots + optional affiliate footer."""
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

    foot = ""
    footer = (affiliate_footer_html or "").strip()
    if footer:
        foot = f"\n\n{footer}"

    body = header + mod_block + foot
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


def pick_preparing_line(rng: random.Random | None = None) -> str:
    r = rng or random.Random()
    return r.choice(ROLL_PREPARING_LINES)


def pick_still_working_line(rng: random.Random | None = None) -> str:
    r = rng or random.Random()
    return r.choice(ROLL_STILL_WORKING_LINES)


def pick_deal_failed_html(rng: random.Random | None = None) -> str:
    r = rng or random.Random()
    return r.choice(ROLL_DEAL_FAILED_LINES)


def pick_loading_status_line(rng: random.Random | None = None) -> str:
    r = rng or random.Random()
    return r.choice(ROLL_LOADING_STATUS_LINES)


def build_preparing_html(preview: dict[str, Any] | None = None) -> str:
    seed = (preview or {}).get("seed")
    rng = random.Random(seed) if seed is not None else random.Random()
    # Offset so preparing ≠ same RNG slot as divider when seed shared.
    rng2 = random.Random((int(seed) + 17) if seed is not None else None)
    line = html.escape(pick_preparing_line(rng2 if seed is not None else rng))
    return f"<i>{line}</i>"


def build_independent_draw_note_html() -> str:
    return "<i>Fresh draw — World labels are rarity bands, not a campaign you climb.</i>"


def tier_celebration_line(tier: int) -> str | None:
    return TIER_CELEBRATION.get(max(1, min(10, int(tier))))


def build_roll_divider_html(preview: dict[str, Any]) -> str:
    seed = preview.get("seed")
    rng = random.Random(seed) if seed is not None else random.Random()
    return pick_roll_divider_html(rng)


def copy_bank_inventory() -> dict[str, int]:
    """Counts for ops / docs — how much variation exists."""
    return {
        "roll_dividers": len(ROLL_DIVIDERS),
        "preparing_lines": len(ROLL_PREPARING_LINES),
        "still_working_lines": len(ROLL_STILL_WORKING_LINES),
        "deal_failed_lines": len(ROLL_DEAL_FAILED_LINES),
        "loading_status_lines": len(ROLL_LOADING_STATUS_LINES),
        "tier_flavor_total": sum(len(v) for v in TIER_FLAVOR_BANKS.values()),
        "tier_celebration": len(TIER_CELEBRATION),
        "tier_frames": len(TIER_CARD_FRAMES),
    }
