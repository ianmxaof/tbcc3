"""Scrape priority for Loot Room lane readiness (photo-starved lanes first)."""

from __future__ import annotations

# Toward CHANNEL_READINESS (2.5k/2.5k min, 5k median). See docs/LANE_READINESS_AUDIT.md.
# Bias scrapers: photos → video-heavy lanes; videos → photo-heavy / thin-video lanes.

PHOTO_STARVED_LANE_KEYS: tuple[str, ...] = (
    "taboo",
    "blowjob",
    "big_tits",
    "milf",
)

THIN_VIDEO_LANE_KEYS: tuple[str, ...] = (
    "ai",
    "abg",
)

# Operator scrape queue order (highest gap first as of 2026-07-17 audit).
SCRAPE_PRIORITY_LANE_KEYS: tuple[str, ...] = (
    *PHOTO_STARVED_LANE_KEYS,
    *THIN_VIDEO_LANE_KEYS,
    "ass",
    "voyeur",
    "bop",
    "goon",
    "full_length",
)


def scrape_media_type_bias(network_key: str) -> str:
    """Return preferred media_types hint: photos | videos | both."""
    k = (network_key or "").strip().lower()
    if k in PHOTO_STARVED_LANE_KEYS:
        return "photos"
    if k in THIN_VIDEO_LANE_KEYS:
        return "videos"
    return "both"


def scrape_priority_rank(network_key: str) -> int:
    """Lower = scrape sooner. Unknown keys sort last."""
    k = (network_key or "").strip().lower()
    try:
        return SCRAPE_PRIORITY_LANE_KEYS.index(k)
    except ValueError:
        return 999
