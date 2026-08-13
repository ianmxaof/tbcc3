"""Click-beacon slugs for Reddit comment / promo links → @aofmainhub."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.data.aof_network import MAINHUB_RAW
from app.services.utm_links import append_utm

_SUB_RE = re.compile(r"^[a-z0-9_]{2,24}$")


@dataclass(frozen=True)
class RedditBeacon:
    subreddit: str
    slug: str
    source_ref: str
    destination_url: str
    label: str


def normalize_subreddit_key(name: str) -> str:
    n = (name or "").strip().lower().removeprefix("r/")
    n = re.sub(r"[^a-z0-9_]+", "_", n).strip("_")
    return n[:24]


def reddit_beacon_slug(subreddit: str) -> str:
    key = normalize_subreddit_key(subreddit)
    if not key or not _SUB_RE.match(key):
        raise ValueError(f"invalid subreddit key: {subreddit!r}")
    slug = f"reddit-{key}"
    if len(slug) > 32:
        slug = f"reddit-{key[:32 - len('reddit-')]}"
    return slug


def reddit_source_ref(subreddit: str) -> str:
    key = normalize_subreddit_key(subreddit)
    return f"src_reddit_{key}"[:64]


def reddit_hub_destination(subreddit: str) -> str:
    key = normalize_subreddit_key(subreddit)
    return append_utm(
        MAINHUB_RAW,
        source="reddit",
        medium="comment",
        campaign=key or "hub",
        content="beacon",
    )


def build_reddit_beacon_plan() -> list[RedditBeacon]:
    """Starter subs (Erome paused — operator IP ban)."""
    subs = (
        "telegramnsfw1818",
        "ai_porn_gallery",
        "aipornhub",
        "amateur_milfs",
        "bunkrr",
        "kinkyclouds",
        "icynspicy",
        "goonforboobs",
        "girlsshowering",
    )
    out: list[RedditBeacon] = []
    for sub in subs:
        slug = reddit_beacon_slug(sub)
        out.append(
            RedditBeacon(
                subreddit=sub,
                slug=slug,
                source_ref=reddit_source_ref(sub),
                destination_url=reddit_hub_destination(sub),
                label=f"Reddit r/{sub} → mainhub",
            )
        )
    # Generic fallback when no sub-specific slug is wired in caption builder.
    out.append(
        RedditBeacon(
            subreddit="mainhub",
            slug="reddit-mainhub",
            source_ref="src_reddit_mainhub",
            destination_url=reddit_hub_destination("mainhub"),
            label="Reddit generic → mainhub",
        )
    )
    return out


def beacon_for_subreddit(subreddit: str) -> RedditBeacon | None:
    key = normalize_subreddit_key(subreddit)
    for b in build_reddit_beacon_plan():
        if normalize_subreddit_key(b.subreddit) == key:
            return b
    return None
