"""AOF Library twin forum — env-only ident/invite, inert until the operator provides real values.

Phase 1a scaffold only (forum-as-library Week-1). Not wired into aof_network.py,
BULLETIN_CHANNEL_INVITES, any scheduler, or any caller yet — that's Phase 1b/2, a
separate directive, after the operator pastes a real chat_id + invite back.

  TBCC_AOF_LIBRARY_FORUM_IDENT   — Telegram chat id of the private twin forum (e.g. -100...)
  TBCC_AOF_LIBRARY_FORUM_INVITE  — primary invite link for the twin forum

MAIN_GROUP_IDENT (Loot Room) is unaffected — the twin is a separate paid destination,
not a replacement for the free hangout. See docs/AOF_PLACEMENT_DOCTRINE.md.
"""

from __future__ import annotations

import os


def aof_library_forum_ident() -> str | None:
    """Twin forum chat id, or None until the operator sets the env var."""
    raw = (os.getenv("TBCC_AOF_LIBRARY_FORUM_IDENT") or "").strip()
    return raw or None


def aof_library_forum_invite() -> str | None:
    """Twin forum primary invite link, or None until the operator sets the env var."""
    raw = (os.getenv("TBCC_AOF_LIBRARY_FORUM_INVITE") or "").strip()
    return raw or None


def aof_library_forum_registered() -> bool:
    """True once both ident and invite are set — gate for Phase 1b/2 wiring, unused until then."""
    return aof_library_forum_ident() is not None and aof_library_forum_invite() is not None
