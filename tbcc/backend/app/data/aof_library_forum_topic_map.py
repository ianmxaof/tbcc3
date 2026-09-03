"""AOF Library ("Archive of Filth") twin forum — topic thread inventory
(Phase 1b operator paste 2026-08-23; Phase 2 scope split 2026-08-23).

Live: t.me/c/{ident}/{thread_id} once the twin invite (aof_library_forum.py) is joined.
Pasted directly by the operator — NOT synced via scripts/sync_main_group_topic_map.py,
which targets Loot Room, a different chat. Do not invent additional thread ids; if a new
topic gets created on the twin, it needs its own operator paste, same as this one did.

Two different scopes over the same 11 rows — do not conflate them:

- **Scheduled auto-feed** (recurring content posted by TBCC): AI (thread_id=57) ONLY.
  Every other row is inventory for later phases — opening a scheduler row for any of
  them needs its own ACK. Several (voyeur/bop/ass) show 0 approved backlog on the
  public lanes as of the CADENCE track; do not feed an empty topic.
- **Remixer oversight** (`/rebundle` via the album-composer bot): ALL rows. The bot
  works "in any chat it admins" (bots/remixer_rebundle.py docstring) — no per-topic
  registration needed, no allowlist to update. Operator confirmed all bots/accounts
  are already admin across the whole twin. Manual smoke: run `/rebundle` in the AI
  topic and at least one other (e.g. blowjob, 75) to confirm album grouping in both.

`webcams` (thread_id=77) has no corresponding AofNetworkChannel key in aof_network.py —
inventory only, not a product SKU. Do not add a "webcams" network channel from this
row alone; that needs its own doctrine ACK.

Not wired into any scheduler as a hard dependency — scripts/seed_library_forum_ai_feed.py
(Phase 2) reads AOF_LIBRARY_FORUM_WEEK1_FEED_THREAD_ID directly, dry-run by default.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.data.aof_library_forum import aof_library_forum_ident

AOF_LIBRARY_FORUM_WEEK1_FEED_THREAD_ID = 57  # AI — the only topic fed in Week-1


@dataclass(frozen=True)
class LibraryForumTopic:
    message_thread_id: int
    topic_title: str
    network_key: str


AOF_LIBRARY_FORUM_TOPIC_MAP: tuple[LibraryForumTopic, ...] = (
    LibraryForumTopic(57, "ai", "ai"),
    LibraryForumTopic(59, "ass", "ass"),
    LibraryForumTopic(61, "public / voyeur", "voyeur"),
    LibraryForumTopic(63, "bop", "bop"),
    LibraryForumTopic(65, "abg / azn", "abg"),
    LibraryForumTopic(67, "big tits", "big_tits"),
    LibraryForumTopic(69, "milf / gilf", "milf"),
    LibraryForumTopic(71, "nicest taboo", "taboo"),
    LibraryForumTopic(73, "full length", "full_length"),
    LibraryForumTopic(75, "blowjob", "blowjob"),
    LibraryForumTopic(77, "webcams", "webcams"),
    LibraryForumTopic(166, "packs", "packs"),  # t.me/c/3790667061/166
    LibraryForumTopic(168, "goon", "goon"),  # t.me/c/3790667061/168
)


def library_forum_topic_for_network_key(key: str) -> LibraryForumTopic | None:
    k = (key or "").strip().lower()
    for row in AOF_LIBRARY_FORUM_TOPIC_MAP:
        if row.network_key == k:
            return row
    return None


def library_forum_topic_deep_link(message_thread_id: int) -> str:
    """t.me/c/{internal_id}/{thread_id} — twin ident without the -100 prefix, forum style."""
    ident = aof_library_forum_ident().lstrip("-")
    internal_id = ident[3:] if ident.startswith("100") else ident
    return f"https://t.me/c/{internal_id}/{int(message_thread_id)}"


def library_forum_smoke_targets() -> list[tuple[str, int, str]]:
    """(title, thread_id, deep_link) for every twin topic — operator /rebundle smoke reference."""
    return [
        (row.topic_title, row.message_thread_id, library_forum_topic_deep_link(row.message_thread_id))
        for row in AOF_LIBRARY_FORUM_TOPIC_MAP
    ]
