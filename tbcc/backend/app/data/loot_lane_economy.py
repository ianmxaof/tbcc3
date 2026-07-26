"""Loot Room lane economy — product constants (scaffold; no payment wiring).

See ``docs/LOOT_LANE_ECONOMY.md`` for the full product bible.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.data.aof_network import AOF_NETWORK_CHANNELS


class WatermarkTier(str, Enum):
    """Robocopy fan-out: one master → three public surfaces."""

    PROMO_HEAVY = "promo_heavy"  # Loot Room glimpse — leak = free ad
    LANE_LIGHT = "lane_light"  # Paid channel — still attributable if screen-recorded
    VAULT_CLEAN = "vault_clean"  # VIP / internal only — never forwardable


@dataclass(frozen=True)
class GlimpseSpec:
    """Visible promo in Loot Room subtopic (not vanish-then-delete)."""

    shown_of_full: tuple[int, int] = (3, 7)  # "3 of 7 shown"
    watermark: WatermarkTier = WatermarkTier.PROMO_HEAVY
    leave_visible: bool = True
    forwards_enabled: bool = True  # intentional: leak becomes promo


@dataclass(frozen=True)
class LanePassSpec:
    """Cheap one-use 24h invite into a single lane channel."""

    price_usd: float = 3.0
    duration_hours: int = 24
    one_use: bool = True
    watermark: WatermarkTier = WatermarkTier.LANE_LIGHT
    content_protected: bool = True  # no clean+forwardable paid
    roll_eligibility: bool = True


@dataclass(frozen=True)
class PackDropSpec:
    """Operator-curated sealed pack (theme-led)."""

    soft_min_items: int = 250
    soft_max_items: int = 400
    curation_required: bool = True
    loot_flair_on_purchase: bool = True
    sku_name: str = "Curated Pack"
    price_usd: float = 12.0


@dataclass(frozen=True)
class MonthlyMegaPackSpec:
    """Month-end wrap of all curated packs in the period."""

    cadence: str = "monthly"
    wraps_curated_packs: bool = True
    sku_name: str = "Monthly MEGA PACK"
    price_usd: float = 25.0


@dataclass(frozen=True)
class LanePassSkuSpec:
    """Shop row for Lane Pass (mirrors LanePassSpec price)."""

    sku_name: str = "Lane Pass — 24h"
    price_usd: float = 3.0
    duration_days: int = 1
    bot_section: str = "loot"


LANE_PASS_SKU = LanePassSkuSpec()


@dataclass(frozen=True)
class ForwardWindowSpec:
    """During active pass: perks are rolls/odds, not clean portability."""

    duration_hours: int = 24
    clean_forwards: bool = False
    roll_perks: bool = True


@dataclass(frozen=True)
class ChannelReadinessSpec:
    """Gate before a lane earns a dedicated Loot Room forum subtopic."""

    min_images: int = 2_500
    min_videos: int = 2_500
    target_median_images: int = 5_000
    target_median_videos: int = 5_000
    aspirational_per_format: int = 10_000


@dataclass(frozen=True)
class RecoveryPolicy:
    seed_backup_channels: bool = True
    entitlement_ledger: bool = True
    real_ban_alerts_only: bool = True
    fake_abuse_banners: bool = False
    share_or_get_banned: bool = False
    positive_invite_for_roll: bool = True


GLIMPSE = GlimpseSpec()
LANE_PASS = LanePassSpec()
PACK_DROP = PackDropSpec()
MONTHLY_MEGA = MonthlyMegaPackSpec()
FORWARD_WINDOW = ForwardWindowSpec()
CHANNEL_READINESS = ChannelReadinessSpec()
RECOVERY = RecoveryPolicy()


def usd_to_stars(usd: float, *, stars_per_usd: float | None = None) -> int:
    """Convert USD list price to Telegram Stars (ceil to whole stars)."""
    import math
    import os

    rate = stars_per_usd
    if rate is None:
        rate = float(os.getenv("TBCC_STARS_USD_PER_STAR") or "0.012")
    if rate <= 0:
        rate = 0.012
    return max(1, int(math.ceil(float(usd) / rate)))

# Free-network content lanes that can earn a Loot Room promo subtopic.
# Hub key ``main`` is the Loot Room itself; ``packs`` is the pack surface.
LANE_TOPIC_ELIGIBLE_KEYS: frozenset[str] = frozenset(
    ch.key
    for ch in AOF_NETWORK_CHANNELS
    if ch.key not in ("main", "packs")
)


def lane_display_name(network_key: str) -> str:
    key = (network_key or "").strip().lower()
    for ch in AOF_NETWORK_CHANNELS:
        if ch.key == key:
            return ch.display_name
    return key.replace("_", " ").upper()


def lane_ready_for_loot_subtopic(*, images: int, videos: int) -> bool:
    """True when both formats meet the minimum readiness floor."""
    return int(images) >= CHANNEL_READINESS.min_images and int(videos) >= CHANNEL_READINESS.min_videos


def lane_at_target_median(*, images: int, videos: int) -> bool:
    return (
        int(images) >= CHANNEL_READINESS.target_median_images
        and int(videos) >= CHANNEL_READINESS.target_median_videos
    )


def pack_item_count_in_soft_band(n: int) -> bool:
    return PACK_DROP.soft_min_items <= int(n) <= PACK_DROP.soft_max_items
