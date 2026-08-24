"""AOF Library twin forum — "Archive of Filth" (Phase 2, operator name lock 2026-08-23).

VIP-style pattern: committed default, env override still wins (same as
AOF_VIP_IDENT / TBCC_AOF_VIP_CHANNEL_IDENT in aof_vip_checkout.py).

  TBCC_AOF_LIBRARY_FORUM_IDENT   — override the ident default below
  TBCC_AOF_LIBRARY_FORUM_INVITE  — override the invite default below

Not wired into aof_network.py, BULLETIN_CHANNEL_INVITES, or any public CTA
surface — the twin has no public invite path yet, only the AI-topic feed
scaffold from Phase 2 (see scripts/seed_library_forum_ai_feed.py).

Display name is locked as "Archive of Filth" — the invite's Telegram-side
preview title ("TheHoneyGoon") is not the product name and must not be used
in doctrine/copy. See docs/AOF_PLACEMENT_DOCTRINE.md.

MAIN_GROUP_IDENT (Loot Room) is unaffected — the twin is a separate paid
destination, not a replacement for the free hangout.
"""

from __future__ import annotations

import os

AOF_LIBRARY_FORUM_IDENT_DEFAULT = "-1003790667061"
AOF_LIBRARY_FORUM_INVITE_DEFAULT = "https://t.me/+dTExOHWqbMU5YWFl"
AOF_LIBRARY_FORUM_DISPLAY_NAME = "Archive of Filth"


def aof_library_forum_ident() -> str:
    return (os.getenv("TBCC_AOF_LIBRARY_FORUM_IDENT") or AOF_LIBRARY_FORUM_IDENT_DEFAULT).strip()


def aof_library_forum_invite() -> str:
    return (os.getenv("TBCC_AOF_LIBRARY_FORUM_INVITE") or AOF_LIBRARY_FORUM_INVITE_DEFAULT).strip()


def aof_library_forum_display_name() -> str:
    return (os.getenv("TBCC_AOF_LIBRARY_FORUM_DISPLAY_NAME") or AOF_LIBRARY_FORUM_DISPLAY_NAME).strip()


def aof_library_forum_registered() -> bool:
    """True now that the operator-pasted defaults are committed — always True unless
    both env and default are somehow blanked. Kept as a function (not a bare bool) so
    Phase 2 callers can gate on it without caring how the value resolved."""
    return bool(aof_library_forum_ident()) and bool(aof_library_forum_invite())
