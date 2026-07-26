"""Canonical AOF Telegram clearnet destinations (post-2026 telegram.me linking).

Use these as *destinations* behind Linkvertise / AdMaven / Work.ink wraps,
and as watermark / filename brand text. Prefer telegram.me over t.me.

Note (2026-07-14): t.me was placed on .me registry serverHold — browsers cannot
resolve it. Burn-in and CTA copy must use telegram.me.
"""

from __future__ import annotations

import re

# Public bulletin / LV affiliate crossing (not the banned Main group)
AOF_MAINHUB = "https://telegram.me/aofmainhub"
AOF_MAINHUB_SHORT = "telegram.me/aofmainhub"

# Loot God bot — only public bot CTA (no ?start=)
AOF_LOOTGOD_BOT = "https://telegram.me/aof_lootgod_bot"
AOF_LOOTGOD_BOT_SHORT = "telegram.me/aof_lootgod_bot"

# Live Loot Room invite
AOF_LOOT_ROOM = "https://telegram.me/+97f4Crv3G1RkMGU5"
AOF_LOOT_ROOM_SHORT = "telegram.me/+97f4Crv3G1RkMGU5"

# Filename / zip brand token (no spaces; readable on Windows)
AOF_BRAND_FILENAME = "telegram.me_aofmainhub"

# Default burn-in watermark (env TBCC_WATERMARK_TEXT overrides)
AOF_WATERMARK_DEFAULT = AOF_MAINHUB_SHORT

# Intended clear destinations for each manual LV gate key (operator retarget checklist).
GATE_CLEAR_DESTINATIONS: dict[str, str] = {
    "mainhub": AOF_MAINHUB,
    "main_group": AOF_LOOTGOD_BOT,  # Main group banned — funnel to lootgod
    "main": AOF_LOOTGOD_BOT,
    "loot": AOF_LOOT_ROOM,
    "lootgod": AOF_LOOTGOD_BOT,
    # Lane invites: keep existing Telegram invite targets when retargeting LV posts
    # (fill from Dashboard / .env lane invites when you edit each Post & earn link).
}

# Bare t.me/ → telegram.me/ (avoids rewriting the "t.me" substring inside telegram.me)
_BARE_TME_RE = re.compile(r"(?<![\w.])t\.me/", re.IGNORECASE)


def normalize_telegram_me_brand(text: str) -> str:
    """Rewrite stale t.me brand / CTA strings to telegram.me for browser reachability."""
    s = (text or "").strip()
    if not s:
        return ""
    s = s.replace("https://t.me/", "https://telegram.me/")
    s = s.replace("http://t.me/", "http://telegram.me/")
    s = _BARE_TME_RE.sub("telegram.me/", s)
    return s
