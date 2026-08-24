"""AOF Library twin forum — registered ident/invite (Phase 1b, operator-pasted 2026-08-23).

VIP-style pattern: committed default, env override still wins (same as
AOF_VIP_IDENT / TBCC_AOF_VIP_CHANNEL_IDENT in aof_vip_checkout.py).

  TBCC_AOF_LIBRARY_FORUM_IDENT   — override the ident default below
  TBCC_AOF_LIBRARY_FORUM_INVITE  — override the invite default below

Not wired into aof_network.py, BULLETIN_CHANNEL_INVITES, any scheduler, or
any caller yet — Phase 2 (AI topic feed + remixer) is a separate directive.
No display name is registered here — operator said "no name for now"; the
invite preview title is not a product/brand lock (see Phase 1b report).

MAIN_GROUP_IDENT (Loot Room) is unaffected — the twin is a separate paid
destination, not a replacement for the free hangout. See
docs/AOF_PLACEMENT_DOCTRINE.md.
"""

from __future__ import annotations

import os

AOF_LIBRARY_FORUM_IDENT_DEFAULT = "-1003790667061"
AOF_LIBRARY_FORUM_INVITE_DEFAULT = "https://t.me/+dTExOHWqbMU5YWFl"


def aof_library_forum_ident() -> str:
    return (os.getenv("TBCC_AOF_LIBRARY_FORUM_IDENT") or AOF_LIBRARY_FORUM_IDENT_DEFAULT).strip()


def aof_library_forum_invite() -> str:
    return (os.getenv("TBCC_AOF_LIBRARY_FORUM_INVITE") or AOF_LIBRARY_FORUM_INVITE_DEFAULT).strip()


def aof_library_forum_registered() -> bool:
    """True now that the operator-pasted defaults are committed — always True unless
    both env and default are somehow blanked. Kept as a function (not a bare bool) so
    Phase 2 callers can gate on it without caring how the value resolved."""
    return bool(aof_library_forum_ident()) and bool(aof_library_forum_invite())
