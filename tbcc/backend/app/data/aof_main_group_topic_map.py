"""
Loot Room hub forum topic → AOF network key (API names kept as main_group_*).

Public hub chat: MAIN_GROUP_IDENT (Loot Room). Paired with Storage Hub via network_key.
Refresh live topics: py -3.13 scripts/sync_main_group_topic_map.py --list

Do not invent thread IDs — open a Loot Room subtopic only when the lane meets
ChannelReadinessSpec (see loot_lane_economy / docs/LOOT_LANE_ECONOMY.md).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.data.aof_network import MAIN_GROUP_IDENT

# Loot Room internal id (t.me/c/{id}/…) — was banned Main 3206350461.
MAIN_GROUP_INTERNAL_ID = "3927742839"
assert MAIN_GROUP_IDENT.endswith(MAIN_GROUP_INTERNAL_ID)


@dataclass(frozen=True)
class MainGroupTopicMap:
    message_thread_id: int
    topic_title: str
    network_key: str


# Live sync 2026-08-22 (scripts/sync_main_group_topic_map.py --list, run against Loot Room
# via the island api container). blowjob/bop added — live topics existed but were missing
# from this map. COMMONS / BULLETINS (695) has no network channel match; not a lane, omitted.
AOF_MAIN_GROUP_TOPIC_MAP: tuple[MainGroupTopicMap, ...] = (
    MainGroupTopicMap(562, "AOF AI 18+", "ai"),
    MainGroupTopicMap(405, "AOF ASS 18+", "ass"),
    MainGroupTopicMap(6, "AOF BIG TITS 18+", "big_tits"),
    MainGroupTopicMap(518, "AOF ABG / LBFM 18+", "abg"),
    MainGroupTopicMap(202, "AOF GOON 18+", "goon"),
    MainGroupTopicMap(523, "AOF MILF / GILF 18+", "milf"),
    MainGroupTopicMap(204, "AOF PACKS 18+", "packs"),
    MainGroupTopicMap(557, "AOF PUBLIC / VOYEUR 18+", "voyeur"),
    MainGroupTopicMap(525, "AOF NICEST TABOO 18+", "taboo"),
    MainGroupTopicMap(206, "AOF BLOWJOB 18+", "blowjob"),
    MainGroupTopicMap(200, "AOF BOP 18+", "bop"),
)

# Reception / Party Room — general liveness fallback (not a storage lane)
MAIN_GROUP_GENERAL_TOPIC_ID = 1
MAIN_GROUP_GENERAL_TOPIC_TITLE = "Reception / Party Room"

# Meta topic — weekly PATCH NOTES build log (not a content lane). Live: t.me/c/3927742839/2408
MAIN_GROUP_PATCH_NOTES_TOPIC_ID = 2408
MAIN_GROUP_PATCH_NOTES_TOPIC_TITLE = "PATCH NOTES"


def main_group_topic_deep_link(message_thread_id: int) -> str:
    return f"https://t.me/c/{MAIN_GROUP_INTERNAL_ID}/{int(message_thread_id)}"


def main_topic_by_network_key() -> dict[str, MainGroupTopicMap]:
    out: dict[str, MainGroupTopicMap] = {}
    for row in AOF_MAIN_GROUP_TOPIC_MAP:
        if row.network_key not in out:
            out[row.network_key] = row
    return out


def main_topic_for_network_key(key: str) -> MainGroupTopicMap | None:
    return main_topic_by_network_key().get((key or "").strip().lower())


def liveness_topic_pool() -> list[MainGroupTopicMap]:
    """Distinct lane topics for randomized liveness posts (excludes general)."""
    return list(main_topic_by_network_key().values())


def resolve_main_topic_from_live_title(topic_title: str, topic_id: int) -> str | None:
    from app.data.aof_network import match_topic_to_network_key

    return match_topic_to_network_key(topic_title)


_BY_THREAD: dict[int, MainGroupTopicMap] = {m.message_thread_id: m for m in AOF_MAIN_GROUP_TOPIC_MAP}
