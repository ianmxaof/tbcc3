"""
Loot Room hub forum topic → AOF network key (API names kept as main_group_*).

Public hub chat: MAIN_GROUP_IDENT (Loot Room). Paired with Storage Hub via network_key.
Refresh live topics: py -3.13 scripts/sync_main_group_topic_map.py --list

Topic rows below are STALE until a live sync against Loot Room (-1003927742839).
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


# STALE — last live sync was banned Main (2026-06-19). Re-sync against Loot Room before use.
AOF_MAIN_GROUP_TOPIC_MAP: tuple[MainGroupTopicMap, ...] = (
    MainGroupTopicMap(17, "Ai", "ai"),
    MainGroupTopicMap(7, "ASS", "ass"),
    MainGroupTopicMap(5, "BIG TITS", "big_tits"),
    MainGroupTopicMap(25, "ABG's / LBFM's / AZN", "abg"),
    MainGroupTopicMap(182, "GOON", "goon"),
    MainGroupTopicMap(19, "MILF", "milf"),
    MainGroupTopicMap(9, "GILF", "milf"),
    MainGroupTopicMap(32, "PACKS", "packs"),
    MainGroupTopicMap(8011, "PUBLIC / VOYEUR / SPY / UNAWARE", "voyeur"),
    MainGroupTopicMap(8888, "NICEST TABOO 18+", "taboo"),
)

# Reception / Party Room — general liveness fallback (not a storage lane)
MAIN_GROUP_GENERAL_TOPIC_ID = 1
MAIN_GROUP_GENERAL_TOPIC_TITLE = "Reception / Party Room"


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
