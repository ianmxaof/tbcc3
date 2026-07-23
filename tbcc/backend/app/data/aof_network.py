"""AOF network channel map — schedulers, pools, storage-hub topic matching."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Public hub = Loot Room (old AOF MAIN GROUP is CHAT_RESTRICTED / banned).
BANNED_MAIN_GROUP_IDENT = "-1003206350461"
BANNED_MAIN_GROUP_INVITE = "https://t.me/+rk8ra7fPJ1QzZDMx"
MAIN_GROUP_IDENT = "-1003927742839"  # LOOT ROOM GROUP (channels.id=8)
MAIN_GROUP_INVITE = "https://t.me/+97f4Crv3G1RkMGU5"
ADDLIST_RAW = "https://t.me/addlist/r-7_7CGIkExhMDcx"
MAINHUB_RAW = "https://telegram.me/aofmainhub"
# Public link directory channel (@aofmainhub) — marketing landing, not a content scrape lane.
MAINHUB_CHANNEL_IDENT = "-1003970144685"
MAINHUB_SCHED_CTA_NAME = "AOF MAINHUB — VIP CTA (pinned)"
MAINHUB_SCHED_LIVENESS_NAME = "AOF MAINHUB — pin liveness"
SFW_X_PROMO_POOL_NAME = "AOF SFW X PROMO POOL"

STORAGE_HUB_IDENT = "-1003812457581"
STORAGE_HUB_INVITE = "https://t.me/+KT3qS_OfvNk4N2Mx"

# Paid broadcast channel — native Telegram Stars subscription (createChatSubscriptionInviteLink).
# Not part of the free addlist — separate paid conversion lane.
AOF_VIP_IDENT = "-1003982098745"
AOF_VIP_POOL_NAME = "AOF VIP POOL"
AOF_VIP_INVITE_PRIMARY = "https://t.me/+Zm7pKVfEgjI4ZDVh"  # unlimited
AOF_VIP_INVITE_ONE_DAY = "https://t.me/+yC3Cqg0Nc_ZkYmMx"  # 1 user / 1 day
AOF_VIP_INVITE_ONE_USE = "https://t.me/+Zke838LwllViMjAx"  # single-use

# Full-length feature-film lane
AOF_FULL_LENGTH_IDENT = "-1003979243630"
AOF_FULL_LENGTH_INVITE = "https://t.me/+D1zANbpc18Y0OTMx"
AOF_FULL_LENGTH_POOL_NAME = "AOF FULL LENGTH POOL"

BULLETIN_MARKER = "AOF LINKS HUB"
LINKS_HUB_SCHED_NAME = "AOF MAIN — Links Hub bulletin (pinned)"
CROSS_CHANNEL_SCHED_NAME = "AOF CROSS-CHANNEL SCHEDULER"


@dataclass(frozen=True)
class AofNetworkChannel:
    key: str
    identifier: str
    invite: str
    display_name: str
    scheduler_name: str
    pool_name: str
    topic_patterns: tuple[str, ...]
    promo_html: str


def _topic(*parts: str) -> tuple[str, ...]:
    return tuple(parts)


AOF_NETWORK_CHANNELS: tuple[AofNetworkChannel, ...] = (
    AofNetworkChannel(
        key="main",
        identifier=MAIN_GROUP_IDENT,
        invite=MAIN_GROUP_INVITE,
        display_name="AOF LOOT ROOM",
        scheduler_name="AOF MAIN GROUP + X SCHEDULER",
        pool_name="AOF MAIN GROUP POOL",
        topic_patterns=_topic("main", "hub", "community", "loot"),
        promo_html=(
            "🪙 <b>AOF LOOT ROOM</b> — the live hub (keys, drops, network feed). "
            "TBCC pipeline · LOOT · premium lanes — @aof_lootgod_bot · @aofsubscriptions_bot"
        ),
    ),
    AofNetworkChannel(
        key="ai",
        identifier="-1003997525573",
        invite="https://t.me/+4umB83be5n41MmEx",
        display_name="AOF AI",
        scheduler_name="AOF AI SCHEDULER",
        pool_name="AOF AI POOL",
        topic_patterns=_topic("ai", "aof ai"),
        promo_html=(
            "🧠 <b>AOF AI</b> — tools, prompts, deepfakes, the weird lane.\n"
            "Transform stills → motion. Stay for the pipeline drops.\n"
            "→ @aofsubscriptions_bot"
        ),
    ),
    AofNetworkChannel(
        key="blowjob",
        identifier="-1003584645781",
        invite="https://t.me/+3jeQNQhcOSU4ZTcx",
        display_name="AOF BLOWJOB",
        scheduler_name="AOF BLOWJOB SCHEDULER",
        pool_name="AOF BLOWJOB POOL",
        topic_patterns=_topic("blowjob", "bj"),
        promo_html=(
            "💋 <b>AOF BLOWJOB</b> — curated oral lane, no filler.\n"
            "One gate. One folder. Zero apology.\n"
            "→ @aofsubscriptions_bot"
        ),
    ),
    AofNetworkChannel(
        key="big_tits",
        identifier="-1003953321276",
        invite="https://t.me/+vPhWRgtpteI4NTdh",
        display_name="AOF BIG TITS",
        scheduler_name="AOF BIG TITS SCHEDULER",
        pool_name="AOF BIG TITS POOL",
        topic_patterns=_topic("big tits", "big titties", "bt"),
        promo_html=(
            "🌍 <b>AOF BIG TITS</b> — stacked lane, daily deposits.\n"
            "scarcity isn't cruelty. it's filtration.\n"
            "→ @aofsubscriptions_bot"
        ),
    ),
    AofNetworkChannel(
        key="taboo",
        identifier="-1003934742095",
        invite="https://t.me/+w46b7uJK5eo0MDcx",
        display_name="AOF TABOO",
        scheduler_name="AOF TABOO SCHEDULER",
        pool_name="AOF TABOO POOL",
        topic_patterns=_topic("taboo"),
        promo_html=(
            "🔞 <b>AOF TABOO</b> — the lane you don't mention at dinner.\n"
            "you weren't invited. you clicked anyway. good.\n"
            "→ @aofsubscriptions_bot"
        ),
    ),
    AofNetworkChannel(
        key="voyeur",
        identifier="-1003707918131",
        invite="https://t.me/+ag3BSf3fliwyYTgx",
        display_name="AOF PUBLIC VOYEUR",
        scheduler_name="AOF PUBLIC / VOYEUR SCHEDULER",
        pool_name="AOF PUBLIC / VOYEUR POOL",
        topic_patterns=_topic("voyeur", "public"),
        promo_html=(
            "👀 <b>AOF PUBLIC VOYEUR</b> — candid public lane.\n"
            "watchers welcome. tourists bounce at the gate.\n"
            "→ @aofsubscriptions_bot"
        ),
    ),
    AofNetworkChannel(
        key="milf",
        identifier="-1003719484399",
        invite="https://t.me/+AY0zGwyeAy9jNDIx",
        display_name="AOF MILF",
        scheduler_name="AOF MILF SCHEDULER",
        pool_name="AOF MILF POOL",
        topic_patterns=_topic("milf", "gilf", "milf/gilf"),
        promo_html=(
            "🧔‍♀️ <b>AOF MILF / GILF</b> — mature vault, curated not scraped blind.\n"
            "another drop cleared the pipeline — no filler.\n"
            "→ @aofsubscriptions_bot"
        ),
    ),
    AofNetworkChannel(
        key="ass",
        identifier="-1003920475403",
        invite="https://t.me/+gQaguoQE7eM4MzA5",
        display_name="AOF ASS",
        scheduler_name="AOF ASS SCHEDULER",
        pool_name="AOF ASS POOL",
        topic_patterns=_topic("ass", "aof ass"),
        promo_html=(
            "🔥 <b>AOF ASS</b> — heavy curve lane, daily rotation.\n"
            "psy-slop hour: upload → gasp → share.\n"
            "→ @aofsubscriptions_bot"
        ),
    ),
    AofNetworkChannel(
        key="abg",
        identifier="-1003984584735",
        invite="https://t.me/+4Hs9iMZpIDQ5NjMx",
        display_name="ABG / LBFM",
        scheduler_name="ABG / LBFM SCHEDULER",
        pool_name="ABG / LBFM POOL",
        topic_patterns=_topic("abg", "lbfm", "abg/lbfm"),
        promo_html=(
            "👧 <b>AOF ABG / LBFM</b> — niche lane, tight curation.\n"
            "filtration is a feature. you're still here.\n"
            "→ @aofsubscriptions_bot"
        ),
    ),
    AofNetworkChannel(
        key="packs",
        identifier="-1004247083739",
        invite="https://t.me/+xCtxqzQEuoRmZGZh",
        display_name="AOF PACKS",
        scheduler_name="AOF PACKS — channel promo",
        pool_name="AOF PACKS — Promo",
        topic_patterns=_topic("packs", "pack"),
        promo_html=(
            "📦 <b>AOF PACKS</b> — mega parcels, LV-wrapped drops.\n"
            "one friction step between you and the folder.\n"
            "→ @aofsubscriptions_bot · /packs"
        ),
    ),
    AofNetworkChannel(
        key="goon",
        identifier="-1003809663025",
        invite="https://t.me/+jKGzJMZAhCZjNjdh",
        display_name="AOF GOON",
        scheduler_name="AOF GOON SCHEDULER",
        pool_name="AOF GOON POOL",
        topic_patterns=_topic("goon"),
        promo_html=(
            "🌀 <b>AOF GOON</b> — edge lane. you know why you're here.\n"
            "another relay fired. act accordingly.\n"
            "→ @aofsubscriptions_bot"
        ),
    ),
    AofNetworkChannel(
        key="bop",
        identifier="-1003763051030",
        invite="https://t.me/+woiIGJFd19NmZjkx",
        display_name="AOF BOP",
        scheduler_name="AOF BOP SCHEDULER",
        pool_name="AOF BOP POOL",
        topic_patterns=_topic("bop"),
        promo_html=(
            "🎵 <b>AOF BOP</b> — rhythm &amp; motion lane.\n"
            "curated drops. no tourist energy.\n"
            "→ @aofsubscriptions_bot"
        ),
    ),
)

if AOF_FULL_LENGTH_IDENT.strip():
    AOF_NETWORK_CHANNELS = AOF_NETWORK_CHANNELS + (
        AofNetworkChannel(
            key="full_length",
            identifier=AOF_FULL_LENGTH_IDENT.strip(),
            invite=(AOF_FULL_LENGTH_INVITE or "").strip() or "https://telegram.me/aofmainhub",
            display_name="AOF FULL LENGTH",
            scheduler_name="AOF FULL LENGTH SCHEDULER",
            pool_name=AOF_FULL_LENGTH_POOL_NAME,
            topic_patterns=_topic(
                "full length",
                "full-length",
                "feature",
                "cinema",
                "movies",
                "movie",
                "marathon",
            ),
            promo_html=(
                "🎬 <b>AOF FULL LENGTH</b> — feature films on rotation, updated chronologically.\n"
                "search by hashtag · browse by tag · no clip bait.\n"
                "→ @aofsubscriptions_bot"
            ),
        ),
    )

BULLETIN_CHANNEL_INVITES: dict[str, tuple[str, str]] = {
    ch.key: (ch.display_name, ch.invite) for ch in AOF_NETWORK_CHANNELS if ch.key != "main"
}
BULLETIN_CHANNEL_INVITES["main_group"] = ("AOF Loot Room", MAIN_GROUP_INVITE)
BULLETIN_CHANNEL_INVITES["mainhub"] = ("aofmainhub", MAINHUB_RAW)
BULLETIN_CHANNEL_INVITES["addlist"] = ("ADDLIST", ADDLIST_RAW)
BULLETIN_CHANNEL_INVITES["vip"] = ("AOF VIP", AOF_VIP_INVITE_PRIMARY)


def network_channel_by_key(key: str) -> AofNetworkChannel | None:
    for ch in AOF_NETWORK_CHANNELS:
        if ch.key == key:
            return ch
    return None


def match_topic_to_network_key(topic_title: str) -> str | None:
    """Best-effort map storage-hub forum topic title → network channel key."""
    t = (topic_title or "").strip().lower()
    if not t:
        return None
    best: tuple[int, str] | None = None
    for ch in AOF_NETWORK_CHANNELS:
        if ch.key == "main":
            continue
        for pat in ch.topic_patterns:
            if pat in t or re.search(rf"\b{re.escape(pat)}\b", t):
                score = len(pat)
                if best is None or score > best[0]:
                    best = (score, ch.key)
    return best[1] if best else None
