"""Click beacon plan for AOF Hub web CTAs (P8/P5/P6)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WebHubBeacon:
    slug: str
    label: str
    destination_url: str
    source_ref: str


LOOT_BOT = "https://telegram.me/aof_lootgod_bot"
VIP_BOT = "https://t.me/aofsubscriptions_bot"
SPICY_BOT = "https://t.me/aof_spicybot_bot"


def build_web_hub_beacon_plan() -> list[WebHubBeacon]:
    """Idempotent slugs referenced by aof-forum/lib/aof-cta.ts and data/live-embeds.json."""
    return [
        WebHubBeacon(
            slug="web-vip",
            label="AOF Hub → VIP ladder",
            destination_url=VIP_BOT,
            source_ref="src_web_hub_vip",
        ),
        WebHubBeacon(
            slug="web-spicy",
            label="AOF Hub → Spicy companion",
            destination_url=SPICY_BOT,
            source_ref="src_web_hub_spicy",
        ),
        WebHubBeacon(
            slug="web-loot-media",
            label="AOF Hub media → Loot Room",
            destination_url=f"{LOOT_BOT}?start=src_web_media",
            source_ref="src_web_media",
        ),
        WebHubBeacon(
            slug="web-loot-gallery",
            label="AOF Hub gallery → Loot Room",
            destination_url=f"{LOOT_BOT}?start=src_web_gallery",
            source_ref="src_web_gallery",
        ),
        WebHubBeacon(
            slug="web-loot-tag",
            label="AOF Hub tag → Loot Room",
            destination_url=f"{LOOT_BOT}?start=src_web_tag",
            source_ref="src_web_tag",
        ),
        WebHubBeacon(
            slug="web-loot-live",
            label="AOF Hub live → Loot Room",
            destination_url=f"{LOOT_BOT}?start=src_web_live",
            source_ref="src_web_live",
        ),
        WebHubBeacon(
            slug="web-live-girls",
            label="AOF Hub live girls (Awempire placeholder)",
            destination_url="https://www.awempire.com/",
            source_ref="src_web_live_girls",
        ),
        WebHubBeacon(
            slug="web-live-couples",
            label="AOF Hub live couples (Awempire placeholder)",
            destination_url="https://www.awempire.com/",
            source_ref="src_web_live_couples",
        ),
    ]
