"""AOF Library twin forum — topic thread inventory (Phase 1b, operator-pasted 2026-08-23).

Live: t.me/c/{ident}/{thread_id} once the twin invite (aof_library_forum.py) is joined.
Pasted directly by the operator — NOT synced via scripts/sync_main_group_topic_map.py,
which targets Loot Room, a different chat. Do not invent additional thread ids; if a new
topic gets created on the twin, it needs its own operator paste, same as this one did.

Week-1 feed target: AI (thread_id=57) is the ONLY topic scheduled/fed as of Phase 1b.
Every other row below is inventory for later phases — opening a scheduler row for any
of them needs its own ACK. Several (voyeur/bop/ass) show 0 approved backlog on the
public lanes as of the CADENCE track; do not feed an empty topic.

`webcams` (thread_id=77) has no corresponding AofNetworkChannel key in aof_network.py —
inventory only, not a product SKU. Do not add a "webcams" network channel from this
row alone; that needs its own doctrine ACK.

Not wired into any scheduler, remixer job, or caller yet — Phase 2 is a separate
directive.
"""

from __future__ import annotations

from dataclasses import dataclass

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
)


def library_forum_topic_for_network_key(key: str) -> LibraryForumTopic | None:
    k = (key or "").strip().lower()
    for row in AOF_LIBRARY_FORUM_TOPIC_MAP:
        if row.network_key == k:
            return row
    return None
