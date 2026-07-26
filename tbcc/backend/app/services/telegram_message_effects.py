"""Telegram message effects for loot reveal (private chats)."""

from __future__ import annotations

import logging
import os
import random

logger = logging.getLogger(__name__)

# Free Bot API effects (work without bot Premium).
FREE_EFFECT_PARTY = "5046509860389126442"  # 🎉 classic confetti
FREE_EFFECT_FIRE = "5104841245755180586"  # 🔥
FREE_EFFECT_HEART = "5159385139981059251"  # ❤

# Curated Premium / animated effects for key-roll reveal photos.
# Primary pick when a single default is needed: sparkles ✨
EFFECT_SPARKLES = "5089460564141278042"  # ✨
EFFECT_SPACE_INVADER = "4927184970142712981"  # 👾

LOOT_ROLL_EFFECT_POOL: tuple[str, ...] = (
    "5429503093584708815",  # 🩷
    "5296477528246983373",  # 😲
    "5211213609853534583",  # ❄
    "5436014903955561968",  # 🌹
    "5426962328371349800",  # 🍿
    "5386366834360467867",  # 💊
    "5298766204649872471",  # 🎉 (premium variant)
    "5089178556588622814",  # 🍑
    EFFECT_SPARKLES,  # ✨
    EFFECT_SPACE_INVADER,  # 👾
)

DEFAULT_LOOT_ROLL_EFFECT_ID = EFFECT_SPARKLES


def loot_roll_effect_id(*, rng: random.Random | None = None) -> str | None:
    """
    Preferred effect for the reveal card photo (private chats).

    Delivery cascades: this id → free 🎉 → bare photo, because bots often
    get Premium_account_required for sticker-pack effect ids.

    - Default: random from LOOT_ROLL_EFFECT_POOL
    - Override: TBCC_LOOT_ROLL_EFFECT_ID=<id>
    - Disable effects entirely: TBCC_LOOT_ROLL_EFFECT_ID=off
    """
    raw = os.getenv("TBCC_LOOT_ROLL_EFFECT_ID")
    if raw is not None:
        val = raw.strip()
        if not val or val.lower() in {"0", "none", "off", "false"}:
            return None
        return val
    picker = rng or random
    return picker.choice(LOOT_ROLL_EFFECT_POOL)
