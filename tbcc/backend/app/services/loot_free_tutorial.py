"""Step-by-step copy for the 5 complimentary loot pulls (instructional onboarding)."""

from __future__ import annotations

import html

FREE_PULL_COUNT = 5

# pull_number 1..5 — shown before the spoiler card on that pull
STEP_INTRO: dict[int, str] = {
    1: (
        "<b>Welcome — Pull 1 of 5</b>\n\n"
        "This is a <b>Loot Room draw</b>: curated media from the vault, dealt to your DM.\n"
        "Every pull rolls a <b>rarity tier</b> (1–10). Higher tier → more items + better bonuses on paid runs.\n\n"
        "<i>Complimentary pulls are nerfed: tier capped, one spoiler card, no real modifiers.</i>\n"
        "Tap <b>Roll</b> anytime — your lesson continues each pull."
    ),
    2: (
        "<b>Pull 2 of 5 — Tiers & quantity</b>\n\n"
        "The number after your tier is how big a <b>paid</b> drop can get "
        "(tier 7 → up to 7 items in one pull).\n"
        "Free pulls stay at <b>one</b> blurred card so you get the unwrap feeling without the full album."
    ),
    3: (
        "<b>Pull 3 of 5 — Modifiers (paid only)</b>\n\n"
        "Full rolls attach <b>0–3 bonus modifiers</b> in the album caption — bonus packs, private invites, mega links.\n"
        "Below you'll see <s>crossed-out examples</s>: that's the paid table teasing what's locked on free pulls."
    ),
    4: (
        "<b>Pull 4 of 5 — The high table</b>\n\n"
        "Tiers <b>6–10</b> (Vault → Ascension) unlock on paid 24h room runs — bigger albums, "
        "real <b>packs</b>, stacked modifiers.\n"
        "You're still on the training table (tiers 1–5 only)."
    ),
    5: (
        "<b>Pull 5 of 5 — Last free taste</b>\n\n"
        "After this, complimentary pulls are spent — but the full tier ladder, multi-item albums, "
        "and real modifier drops open with a <b>24h Loot Room key</b>.\n"
        "Make this unwrap count."
    ),
}

STEP_AFTER_CARD: dict[int, str] = {
    1: "Step 1 done — you unwrapped a training-tier card. Four lessons left, then the real table.",
    2: "Step 2 done — same blur mechanic, bigger payloads wait on paid tiers.",
    3: "Step 3 done — strikethrough lines are previews, not bugs. Paid runs deliver those for real.",
    4: "Step 4 done — one free pull left, then upgrade for tiers 6–10 and real modifiers.",
    5: "Last free pull used — you're ready for the full run.",
}

GUIDE_SUMMARY = (
    "<b>Loot Room — quick guide</b>\n\n"
    "<b>Complimentary pulls (5 lifetime)</b>\n"
    "• Nerfed on purpose: tiers 1–5 only, <b>one</b> spoiler item, no real modifiers\n"
    "• Tap the blur to unwrap each card\n"
    "• Crossed-out lines = paid-table previews (bonus packs, invites, megas)\n\n"
    "<b>Paid 24h room</b>\n"
    "• Tiers 1–10 — album size scales with tier\n"
    "• 0–3 real modifier slots per pull\n"
    "• Private Loot Room group for the run window\n\n"
    "<b>Your 5-lesson path</b>\n"
    "1 Welcome + what a draw is\n"
    "2 Tier → quantity on paid runs\n"
    "3 Modifier slots (tease only on free)\n"
    "4 High tiers 6–10 on paid\n"
    "5 Last taste → upgrade hook\n\n"
    "Tap <b>Roll now</b> to continue."
)


def pull_number_from_preview(preview: dict) -> int:
    """1..5 for current complimentary pull; 0 if unknown."""
    n = preview.get("free_pull_number")
    if n is not None:
        return max(1, min(FREE_PULL_COUNT, int(n)))
    rem_before = int(preview.get("free_pulls_remaining_before") or 0)
    limit = int(preview.get("free_pull_limit") or FREE_PULL_COUNT)
    if rem_before <= 0:
        return FREE_PULL_COUNT
    return max(1, min(FREE_PULL_COUNT, limit - rem_before + 1))


def build_step_intro_html(preview: dict) -> str:
    step = pull_number_from_preview(preview)
    return STEP_INTRO.get(step, STEP_INTRO[1])


def build_guide_summary_html() -> str:
    return GUIDE_SUMMARY


def step_progress_label(preview: dict) -> str:
    step = pull_number_from_preview(preview)
    return f"Lesson {step}/{FREE_PULL_COUNT}"


def exhausted_hook_html(*, payment_bot_username: str | None) -> str:
    pay = (payment_bot_username or "").strip().lstrip("@")
    pay_block = (
        f'<a href="https://t.me/{html.escape(pay)}?start=loot">@{html.escape(pay)}</a> → /loot'
        if pay
        else "payment bot → /loot"
    )
    return (
        "<b>Complimentary pulls finished.</b>\n\n"
        "You felt the blur unwrap — paid runs deal <b>full albums</b> (tier = item count), "
        "<b>real modifiers</b>, and tiers through <b>Ascension</b>.\n\n"
        f"🗝 <b>24h Loot Room key</b> — {pay_block}\n"
        "Refer friends with /referral for bonus free pulls if you need one more taste."
    )
