"""Reddit-safe titles and bodies — respect per-sub link_policy."""

from __future__ import annotations

import os
import re

from app.data.aof_network import MAINHUB_RAW
from app.data.reddit_beacon_plan import beacon_for_subreddit
from app.models.reddit_subreddit_profile import RedditSubredditProfile
from app.services.click_beacon import public_beacon_base
from app.services.utm_links import allmylinks_tracked_url

_URL_RE = re.compile(r"https?://\S+")


def reddit_use_beacon_links() -> bool:
    return (os.getenv("TBCC_REDDIT_USE_BEACON") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def reddit_comment_link_for_sub(subreddit: str, *, utm_campaign: str) -> str:
    """Beacon URL when seeded; else tracked AllMyLinks or mainhub."""
    if reddit_use_beacon_links():
        beacon = beacon_for_subreddit(subreddit)
        if beacon:
            base = public_beacon_base()
            if base and "127.0.0.1" not in base:
                return f"{base.rstrip('/')}/r/{beacon.slug}"
    aml = allmylinks_tracked_url(source="reddit", medium="post", campaign=utm_campaign)
    return aml or MAINHUB_RAW


def build_reddit_title(*, teaser: str | None = None, max_len: int = 280) -> str:
    base = (teaser or os.getenv("TBCC_REDDIT_DEFAULT_TITLE") or "AOF Network drop").strip()
    base = _URL_RE.sub("", base).strip()
    if not base:
        base = "AOF Network"
    return base[:max_len]


def build_reddit_body(
    profile: RedditSubredditProfile,
    *,
    teaser: str | None = None,
    utm_campaign: str = "reddit",
) -> tuple[str, str | None]:
    """
    Returns (selftext, comment_link).
    comment_link is set when link_policy=comment_only (post body stays clean; link goes in first comment).
    """
    policy = (profile.link_policy or "bio_style").strip().lower()
    hub = MAINHUB_RAW.replace("https://", "").replace("http://", "")
    tracked_link = reddit_comment_link_for_sub(profile.name, utm_campaign=utm_campaign)
    aml = allmylinks_tracked_url(source="reddit", medium="post", campaign=utm_campaign)
    aml_disp = aml.replace("https://", "").replace("http://", "") if aml else "allmylinks.com/aof69"

    hook = _URL_RE.sub("", (teaser or "").strip())
    hook = re.sub(r"\s+", " ", hook).strip()[:400]

    lines = ["AOF Network — curated Telegram network."]
    if hook:
        lines.append(hook)

    comment_link: str | None = None

    if policy == "none":
        lines.append("Hub and full map in profile / bio.")
    elif policy == "bio_style":
        lines.extend(
            [
                "",
                f"Hub: {hub}",
                f"Full map: {aml_disp}",
                "",
                "(Links in profile — not spamming direct gates in-body.)",
            ]
        )
    elif policy == "comment_only":
        lines.extend(["", "Link in first comment."])
        comment_link = tracked_link
    elif policy == "direct_ok":
        lines.extend(["", f"Hub: {MAINHUB_RAW}", f"Map: {aml or aml_disp}"])
        comment_link = tracked_link if reddit_use_beacon_links() else None
    else:
        lines.append(f"Map: {aml_disp}")

    return "\n".join(lines).strip()[:40000], comment_link
