"""AOF brand voice layers — hand-authored tone + tactics mined from swipe file."""

from __future__ import annotations

# Core AOF voice (Loot Room commons, edgy sharpen pass, X armory).
AOF_CORE_VOICE = (
    "Adult NSFW Telegram network. Audience: depraved, edgy, self-aware degenerates who hate corporate "
    "'bird speak'. Dense and arrogant when minimal; never sound like a SaaS landing page."
)

# Telegram-native intimate voice (inspired by high-performing bot promos in swipe file).
TELEGRAM_NATIVE_VOICE = (
    "Personal curator speaking directly to one reader inside Telegram. First-person builder energy: "
    "'I spent years…', 'I preserved…', 'I run several channels…'. Intimate, not corporate. "
    "Social proof via scale (file counts, daily updates, 10k+ MAU on the bot) — real AOF numbers only, "
    "never invent stats. Value anchoring OK ('less than Netflix', 'one night out') when pricing is real. "
    "Emoji bullet lists OK for pack drops and network promos. Soft urgency OK ('growing network', "
    "'promo window') — no fake countdown timers."
)

# Tactics extracted from swipe file — inject into LLM adapt prompts.
SWIPE_TACTICS: dict[str, str] = {
    "not_a_regular_channel": "Differentiate: this is NOT a regular/repost/spam channel.",
    "first_person_builder": "Curator built the library — creating, not copying.",
    "emoji_bullet_inventory": "What's inside: emoji + short line per asset class.",
    "price_comparison_anchor": "Stack price against everyday spend (streaming, dinner, night out).",
    "forever_access_framing": "Lifetime / unlimited access as the hero offer when applicable.",
    "nostalgia_hook": "Open on a shared cultural moment the reader misses.",
    "loss_framing": "Most of it is gone — deleted, blocked, lost.",
    "last_place_on_earth": "This is the last place the material still exists.",
    "imagine_having_framing": "'Imagine having X at your fingertips' — possession fantasy.",
    "repository_not_chat": "More than another chat — a true repository / library.",
    "tiered_subscription_table": "Clear tier lines: trial / months / lifetime with real prices.",
    "pack_discount_math": "Bundle all lanes — show the math vs buying one-by-one.",
    "growing_channel_promo_window": "Soft promo because network is growing — don't delay.",
    "start_cta": "End with /start or equivalent bot entry when format is bot welcome.",
    "pre_launch_early_access": "Private network access before public launch — insider frame.",
    "dropping_links_early": "Links dropped early to the room before the wider push.",
    "before_the_hype": "Get in before the hype starts — early adopter FOMO.",
    "multi_part_lane_directory": "Part 1 / Part 2 lane lists with emoji tier prefixes.",
    "emoji_tier_grouping": "Group lanes by emoji tier (public 💜, locked 🔐, themed 🍭/🍒).",
    "addlist_one_click_punch": "ALL CHANNELS. ONE CLICK. — caps-lock addlist energy.",
    "early_adopter_regret": "The ones getting in now will understand later.",
    "tools_hub_footer": "Must-have tools checklist + folder/hub dual CTA + subscribe closer.",
}

# Lane-specific adapt rules — which voice layer + format constraints apply.
LANE_ADAPT_RULES: dict[str, dict[str, str]] = {
    "packs_album": {
        "voice": "telegram_native",
        "format": "Telegram HTML. Header + optional emoji bullet body + pack gates. Keep {{PACK_BODY}} if present.",
        "length": "Medium — lists OK for inventory lines; keep under ~1200 chars.",
    },
    "main_group_pulse": {
        "voice": "core",
        "format": "Telegram HTML. ONE or TWO dense sentences. No bullet walls.",
        "length": "Short — under ~400 chars preferred.",
    },
    "vip_checkout": {
        "voice": "hybrid",
        "format": "Telegram HTML. Perks + price anchor + @bot CTA. Minimal bullets OK (2–4).",
        "length": "Medium — under ~800 chars.",
    },
    "gate_fomo": {
        "voice": "hybrid",
        "format": "Telegram HTML. Ritual / friction step framing. One gate link.",
        "length": "Short–medium.",
    },
    "network_promo": {
        "voice": "telegram_native",
        "format": "Telegram HTML. Multi-lane pitch + addlist. Emoji bullets OK.",
        "length": "Medium–long — full network overview OK.",
    },
    "x_mirror": {
        "voice": "core",
        "format": "Plain text, max 280 chars. No HTML.",
        "length": "280 chars hard cap.",
    },
    "system_update": {
        "voice": "hybrid",
        "format": "Telegram HTML. Announcement tone — still personal, not corporate changelog.",
        "length": "Short–medium.",
    },
}


def voice_prompt_for_lane(lane: str) -> str:
    """Compose system voice fragment for a target lane."""
    rules = LANE_ADAPT_RULES.get(lane) or LANE_ADAPT_RULES["network_promo"]
    layer = rules["voice"]
    if layer == "core":
        voice = AOF_CORE_VOICE
    elif layer == "telegram_native":
        voice = TELEGRAM_NATIVE_VOICE
    else:
        voice = f"{AOF_CORE_VOICE} Blend with: {TELEGRAM_NATIVE_VOICE}"
    return (
        f"{voice}\n\n"
        f"Format: {rules['format']}\n"
        f"Length: {rules['length']}"
    )


def tactics_prompt_block(tactic_ids: list[str] | None = None) -> str:
    """Bullet block of tactics to preserve when adapting a swipe."""
    if not tactic_ids:
        ids = list(SWIPE_TACTICS.keys())
    else:
        ids = [t for t in tactic_ids if t in SWIPE_TACTICS]
    if not ids:
        return ""
    lines = ["Preserve these persuasion moves (reword for AOF, do not copy competitor names/prices):"]
    for tid in ids:
        lines.append(f"- {SWIPE_TACTICS[tid]}")
    return "\n".join(lines)
