"""
Explicit Storage & Bot Hangar forum topic → AOF network channel map.

Source group: Storage & Bot Hangar
  ID: -1003812457581
  Invite: https://t.me/+KT3qS_OfvNk4N2Mx

Topic deep link format: https://t.me/c/3812457581/{message_thread_id}
  (3812457581 = internal id without -100 prefix)

Refresh live topic list:
  cd tbcc/backend && py -3.13 scripts/sync_storage_hub_map.py --list
"""

from __future__ import annotations

from dataclasses import dataclass

STORAGE_HUB_IDENT = "-1003812457581"
STORAGE_HUB_INTERNAL_ID = "3812457581"

# Manual intake — forum subtopic + optional shortcut channel (bulk forward target).
INBOX_TOPIC_ID = 22569
INBOX_TOPIC_TITLE = "AOF INBOX"
INBOX_CHANNEL_IDENT = "-1003874330989"
INBOX_CHANNEL_TITLE = "AOF INBOX #CHANNEL"

# Operator quarantine review queue (forum subtopic). Set TBCC_GATEKEEPER_REVIEW_THREAD_ID if renamed.
GATEKEEPER_REVIEW_TOPIC_TITLE = "Q&A | APPROVE / DENY | INTAKE"


@dataclass(frozen=True)
class StorageTopicMap:
    message_thread_id: int
    topic_title: str
    network_key: str
    notes: str = ""


def topic_deep_link(message_thread_id: int) -> str:
    return f"https://t.me/c/{STORAGE_HUB_INTERNAL_ID}/{message_thread_id}"


# Operator quarantine review cards (forum subtopic). Create in hangar, then set env.
# Until set, review cards post to the hub root / General when TBCC_GATEKEEPER_REVIEW_THREAD_ID is unset.
GATEKEEPER_REVIEW_TOPIC_ID: int | None = 1

# AOF STORAGE lanes — synced from live group 2026-06-13
AOF_STORAGE_TOPIC_MAP: tuple[StorageTopicMap, ...] = (
    StorageTopicMap(5978, "AOF AI STORAGE", "ai"),
    StorageTopicMap(3779, "AOF ASS STORAGE", "ass"),
    StorageTopicMap(5752, "AOF BIG TITS STORAGE", "big_tits"),
    StorageTopicMap(9505, "AOF BLOWJOB STORAGE", "blowjob"),
    StorageTopicMap(9501, "AOF BOP STORAGE", "bop"),
    StorageTopicMap(2934, "AOF GOON STORAGE", "goon"),
    StorageTopicMap(5972, "AOF MILF/GILF STORAGE", "milf"),
    StorageTopicMap(5980, "AOF PACKS STORAGE", "packs"),
    StorageTopicMap(3058, "AOF PUBLIC / VOYEUR / SPY / UNAWARE STORAGE", "voyeur"),
    StorageTopicMap(2919, "AOF TABOO 18+ STORAGE", "taboo"),
    StorageTopicMap(3387, "AOF ABG/LBFM STORAGE", "abg"),
    StorageTopicMap(11281, "AOF FULL LENGTH STORAGE", "full_length"),
    StorageTopicMap(INBOX_TOPIC_ID, INBOX_TOPIC_TITLE, "inbox"),
)

# Telegram → watermark → Erome. Topic: Remote Upload Links (Storage & Bot Hangar).
EROME_STORAGE_TOPIC_MAP = StorageTopicMap(
    3090,
    "Remote Upload Links",
    "erome",
    notes="TBCC_EROME_STORAGE_TOPIC_ID=3090; t.me/c/3812457581/3090",
)

# Non-AOF / workshop lanes — not auto-deposited unless explicitly requested
STORAGE_OTHER_TOPICS: tuple[StorageTopicMap, ...] = (
    StorageTopicMap(1, "General", "", notes="skip"),
    StorageTopicMap(974, "BBW / CURVY / BIG ASS / BIG TITS / MOM / MATURE / BIMBO", "", notes="unmapped"),
    StorageTopicMap(5966, "BIMBO", "", notes="unmapped"),
    StorageTopicMap(5974, "EBONY", "", notes="unmapped"),
    StorageTopicMap(825, "Edits", "", notes="workshop"),
    StorageTopicMap(5982, "GIFS", "", notes="unmapped"),
    StorageTopicMap(5970, "OF GOATS", "", notes="unmapped"),
    StorageTopicMap(5968, "RANDOM", "", notes="unmapped"),
    StorageTopicMap(3090, "Remote Upload Links", "erome", notes="Erome upload lane — TBCC_EROME_STORAGE_TOPIC_ID"),
    StorageTopicMap(3054, "SSBBW", "", notes="unmapped"),
    StorageTopicMap(3243, "Spun", "", notes="unmapped"),
    StorageTopicMap(827, "Top Tier", "", notes="unmapped"),
    StorageTopicMap(5976, "WEBCAM / ETHOT", "", notes="unmapped"),
    StorageTopicMap(3092, "Workshop", "", notes="workshop"),
    StorageTopicMap(1382, "dickflash", "", notes="unmapped"),
    StorageTopicMap(1384, "sleep", "", notes="unmapped"),
)

_BY_THREAD: dict[int, StorageTopicMap] = {m.message_thread_id: m for m in AOF_STORAGE_TOPIC_MAP}


def network_key_for_storage_topic(message_thread_id: int, topic_title: str = "") -> str | None:
    """Resolve topic → network key: explicit map first, then fuzzy title match."""
    row = _BY_THREAD.get(int(message_thread_id))
    if row and row.network_key:
        return row.network_key
    from app.data.aof_network import match_topic_to_network_key

    return match_topic_to_network_key(topic_title)


def storage_map_by_key() -> dict[str, StorageTopicMap]:
    return {m.network_key: m for m in AOF_STORAGE_TOPIC_MAP}


# Content lanes with a live receive channel — excludes PACKS (mega/link parcels, not feed media).
CONTENT_LANE_NETWORK_KEYS: frozenset[str] = frozenset(
    m.network_key for m in AOF_STORAGE_TOPIC_MAP if m.network_key and m.network_key != "packs"
)


def content_lane_storage_topics() -> tuple[StorageTopicMap, ...]:
    return tuple(m for m in AOF_STORAGE_TOPIC_MAP if m.network_key in CONTENT_LANE_NETWORK_KEYS)


# SENT VAULT — permanent master archive after /deposit (forum subtopic). Never bulk-delete.
# Env keys keep TBCC_STORAGE_SENT_CACHE_* for backward compatibility.
SENT_VAULT_DISPLAY_NAME = "SENT VAULT"
SENT_CACHE_TOPIC = StorageTopicMap(
    12345,
    "SENT VAULT",
    "",
    notes="TBCC_STORAGE_SENT_CACHE_TOPIC_ID=12345; permanent AOF master media archive — t.me/c/3812457581/12345",
)

# Category emoji stamps (paired with ✅ when moved to SENT VAULT).
STORAGE_CATEGORY_EMOJI: dict[str, str] = {
    "ass": "🍑",
    "big_tits": "🍒",
    "blowjob": "💋",
    "bop": "🤠",
    "goon": "🤡",
    "ai": "🤖",
    "milf": "🧜‍♀️",
    "packs": "📦",
    "voyeur": "👀",
    "taboo": "🔞",
    "abg": "🥡",
    "full_length": "🎬",
    "inbox": "📥",
    "erome": "💗",
}


def category_emoji_for_network_key(network_key: str | None) -> str:
    key = (network_key or "").strip().lower()
    return STORAGE_CATEGORY_EMOJI.get(key, "📁")
