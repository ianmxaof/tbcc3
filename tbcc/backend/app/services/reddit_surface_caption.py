"""Reddit-safe titles and bodies — respect per-sub link_policy."""

from __future__ import annotations

import os
import re

from app.models.reddit_subreddit_profile import RedditSubredditProfile
from app.services.aof_social_links import aof_public_cta_url
from app.services.utm_links import allmylinks_tracked_url

_URL_RE = re.compile(r"https?://\S+")


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
    hub_url = aof_public_cta_url()
    hub = hub_url.replace("https://", "").replace("http://", "")
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
                f"Loot entry: {hub}",
                f"Full map: {aml_disp}",
                "",
                "(Links in profile — not spamming direct gates in-body.)",
            ]
        )
    elif policy == "comment_only":
        lines.extend(["", "Link in first comment."])
        comment_link = aml or hub_url
    elif policy == "direct_ok":
        lines.extend(["", f"Loot entry: {hub_url}", f"Map: {aml or aml_disp}"])
        comment_link = None
    else:
        lines.append(f"Map: {aml_disp}")

    return "\n".join(lines).strip()[:40000], comment_link
