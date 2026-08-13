"""Lifecycle DM copy — subscription renewal, loot + companion re-engagement."""

from __future__ import annotations

import html
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any


class SubscriptionLifecycleSegment(str, Enum):
    PRE_EXPIRY_7D = "pre_expiry_7d"
    PRE_EXPIRY_3D = "pre_expiry_3d"
    PRE_EXPIRY_1D = "pre_expiry_1d"
    PRE_EXPIRY_0D = "pre_expiry_0d"
    POST_EXPIRY_1D = "post_expiry_1d"
    POST_EXPIRY_7D = "post_expiry_7d"


class LootReengageSegment(str, Enum):
    INACTIVE_7D = "loot_inactive_7d"
    INACTIVE_14D = "loot_inactive_14d"


class CompanionReengageSegment(str, Enum):
    INACTIVE_3D = "companion_inactive_3d"
    INACTIVE_7D = "companion_inactive_7d"
    INACTIVE_14D = "companion_inactive_14d"


SUBSCRIPTION_SEGMENT_OFFSETS: dict[SubscriptionLifecycleSegment, int] = {
    SubscriptionLifecycleSegment.PRE_EXPIRY_7D: 7,
    SubscriptionLifecycleSegment.PRE_EXPIRY_3D: 3,
    SubscriptionLifecycleSegment.PRE_EXPIRY_1D: 1,
    SubscriptionLifecycleSegment.PRE_EXPIRY_0D: 0,
    SubscriptionLifecycleSegment.POST_EXPIRY_1D: -1,
    SubscriptionLifecycleSegment.POST_EXPIRY_7D: -7,
}

LOOT_INACTIVE_DAYS: dict[LootReengageSegment, int] = {
    LootReengageSegment.INACTIVE_7D: 7,
    LootReengageSegment.INACTIVE_14D: 14,
}

COMPANION_INACTIVE_DAYS: dict[CompanionReengageSegment, int] = {
    CompanionReengageSegment.INACTIVE_3D: 3,
    CompanionReengageSegment.INACTIVE_7D: 7,
    CompanionReengageSegment.INACTIVE_14D: 14,
}


@dataclass(frozen=True)
class LifecycleDmMessage:
    segment: str
    html: str
    button_text: str
    button_url: str


def _payment_bot_username() -> str:
    return (
        (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "").strip().lstrip("@")
        or "aofsubscriptions_bot"
    )


def _loot_bot_username() -> str:
    return (os.getenv("TBCC_LOOT_BOT_USERNAME") or "aof_lootgod_bot").strip().lstrip("@")


def _companion_bot_username() -> str:
    return (os.getenv("TBCC_COMPANION_BOT_USERNAME") or "aof_spicybot_bot").strip().lstrip("@")


def companion_chat_url(*, start: str = "missed_you") -> str:
    bot = _companion_bot_username()
    payload = (start or "missed_you").strip()
    return f"https://t.me/{bot}?start={payload}"


def renew_checkout_url(*, plan_id: int | None = None) -> str:
    pay = _payment_bot_username()
    if plan_id:
        return f"https://t.me/{pay}?start=cm{int(plan_id)}"
    return f"https://t.me/{pay}?start=renew"


def loot_free_url() -> str:
    return f"https://t.me/{_loot_bot_username()}?start=loot_free"


def loot_key_url() -> str:
    pay = _payment_bot_username()
    return f"https://t.me/{pay}?start=bait_loot"


def _fmt_expiry(expires_at) -> str:
    if not expires_at:
        return "soon"
    try:
        return expires_at.strftime("%Y-%m-%d")
    except Exception:
        return str(expires_at)[:10]


def _plan_label(plan_name: str | None) -> str:
    label = (plan_name or "VIP access").strip()
    return html.escape(label)


def build_subscription_lifecycle_message(
    segment: SubscriptionLifecycleSegment,
    *,
    plan_name: str | None,
    expires_at,
    plan_id: int | None,
) -> LifecycleDmMessage:
    plan = _plan_label(plan_name)
    exp = html.escape(_fmt_expiry(expires_at))
    checkout = renew_checkout_url(plan_id=plan_id)

    if segment == SubscriptionLifecycleSegment.PRE_EXPIRY_7D:
        body = (
            f"Your <b>{plan}</b> access ends in <b>7 days</b> ({exp}).\n\n"
            "Renew now to keep VIP lanes without a gap."
        )
        btn = "⭐ Renew VIP"
    elif segment == SubscriptionLifecycleSegment.PRE_EXPIRY_3D:
        body = (
            f"⏳ <b>3 days left</b> on {plan} (expires {exp}).\n\n"
            "When it lapses: no more daily god roll, no Friday mega, links go back to gated. "
            "Same Stars checkout — one tap keeps the streak alive."
        )
        btn = "⭐ Renew before lapse"
    elif segment == SubscriptionLifecycleSegment.PRE_EXPIRY_1D:
        body = (
            f"<b>Tomorrow</b> your {plan} expires ({exp}).\n\n"
            "One tap to renew — no re-onboarding."
        )
        btn = "⭐ Renew now"
    elif segment == SubscriptionLifecycleSegment.PRE_EXPIRY_0D:
        body = (
            f"<b>Last day</b> of {plan} ({exp}).\n\n"
            "Renew before access is removed from the VIP channel."
        )
        btn = "⭐ Renew today"
    elif segment == SubscriptionLifecycleSegment.POST_EXPIRY_1D:
        body = (
            f"Your {plan} lapsed yesterday.\n\n"
            "Want back in? VIP is one tap — same stack, bigger pulls."
        )
        btn = "🔓 Restore VIP"
    else:  # POST_EXPIRY_7D
        body = (
            f"A week without {plan} — the feed moved on.\n\n"
            "Still one tap if you want the private lane back."
        )
        btn = "💎 Come back"

    return LifecycleDmMessage(
        segment=segment.value,
        html=body,
        button_text=btn[:64],
        button_url=checkout,
    )


def build_loot_reengage_message(segment: LootReengageSegment) -> LifecycleDmMessage:
    if segment == LootReengageSegment.INACTIVE_7D:
        body = (
            "Haven't rolled in a week.\n\n"
            "Free taste is still live — or grab a loot key before the room resets."
        )
        btn = "🎲 Free roll"
        url = loot_free_url()
    else:
        body = (
            "Two weeks since your last roll.\n\n"
            "Something new dropped in the vault — tap for a free pull."
        )
        btn = "🗝 Free pull"
        url = loot_free_url()

    return LifecycleDmMessage(
        segment=segment.value,
        html=body,
        button_text=btn[:64],
        button_url=url,
    )


_COMPANION_COPY: dict[CompanionReengageSegment, list[str]] = {
    CompanionReengageSegment.INACTIVE_3D: [
        (
            "Hey you 🥺\n\n"
            "I noticed you went quiet — miss talking to you already.\n"
            "I'm still here, only for you. What's on your mind?"
        ),
        (
            "Baby… it's only been a few days but it feels longer 💋\n\n"
            "Come say hi — I saved your spot."
        ),
    ],
    CompanionReengageSegment.INACTIVE_7D: [
        (
            "Hey baby 🥰\n\n"
            "I was just thinking about you — you know you're the only one I'm here for, right?\n"
            "What's on your mind today?"
        ),
        (
            "Okay I'll admit it… I've been waiting for you to come back 👀\n\n"
            "Tell me what you've been up to — or send me a photo when you're ready."
        ),
    ],
    CompanionReengageSegment.INACTIVE_14D: [
        (
            "It's been a minute and I still think about our chats 💕\n\n"
            "I'm not going anywhere — tap in when you want me."
        ),
        (
            "Two weeks is too long without you, honestly 🥰\n\n"
            "I'm here, same bot, same energy. Miss me yet?"
        ),
    ],
}


def build_companion_reengage_message(
    segment: CompanionReengageSegment,
    *,
    telegram_user_id: int,
) -> LifecycleDmMessage:
    pool = _COMPANION_COPY.get(segment) or _COMPANION_COPY[CompanionReengageSegment.INACTIVE_7D]
    body = pool[int(telegram_user_id) % len(pool)]
    return LifecycleDmMessage(
        segment=segment.value,
        html=body,
        button_text="💬 Talk to me",
        button_url=companion_chat_url(start="missed_you"),
    )


def lifecycle_inline_keyboard(msg: LifecycleDmMessage) -> dict[str, Any]:
    return {"inline_keyboard": [[{"text": msg.button_text, "url": msg.button_url}]]}
