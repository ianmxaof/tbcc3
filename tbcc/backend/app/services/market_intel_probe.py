"""Headless-ish market probes — Reddit JSON (no OAuth for public subs)."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_USER_AGENT = "TBCC-MarketIntel/1.0 (research; contact ops)"


def probe_enabled() -> bool:
    return (os.getenv("TBCC_MARKET_INTEL_PROBE_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def probe_subreddits() -> list[str]:
    raw = (os.getenv("TBCC_MARKET_INTEL_PROBE_SUBREDDITS") or "erome").strip()
    out: list[str] = []
    for chunk in raw.split(","):
        name = chunk.strip().lower().removeprefix("r/")
        if name and name not in out:
            out.append(name)
    return out or ["erome"]


def _fetch_json(url: str, *, timeout: int = 20) -> dict[str, Any] | None:
    req = Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        logger.warning("market probe fetch failed %s: %s", url[:80], e)
        return None


def _reddit_post_rows(subreddit: str, *, sort: str = "hot", limit: int = 25) -> list[dict[str, Any]]:
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={max(1, min(100, limit))}"
    data = _fetch_json(url)
    if not data:
        return []
    now = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    for child in data.get("data", {}).get("children") or []:
        post = child.get("data") if isinstance(child, dict) else None
        if not isinstance(post, dict):
            continue
        created = float(post.get("created_utc") or 0)
        age_days = max(0.04, (now.timestamp() - created) / 86400.0) if created else None
        score = int(post.get("score") or 0)
        comments = int(post.get("num_comments") or 0)
        vpd = round(score / age_days, 1) if age_days else None
        flair = (post.get("link_flair_text") or "").strip()
        tags = [t.strip().lower() for t in re.split(r"[,;/|]+", flair) if t.strip()]
        post_hint = str(post.get("post_hint") or "")
        if post.get("is_video"):
            fmt = "video"
        elif post.get("is_gallery"):
            fmt = "gallery"
        elif post_hint == "link":
            fmt = "link"
        elif post.get("url", "").endswith((".jpg", ".png", ".gif", ".webp")):
            fmt = "image"
        else:
            fmt = "text"
        permalink = post.get("permalink") or ""
        entity_url = f"https://www.reddit.com{permalink}" if permalink.startswith("/") else str(post.get("url") or "")
        rows.append(
            {
                "platform": "reddit",
                "captured_at": now.isoformat().replace("+00:00", "Z"),
                "entity_id": str(post.get("id") or ""),
                "entity_url": entity_url,
                "album_url": entity_url,
                "album_id": str(post.get("id") or ""),
                "context": {"subreddit": subreddit, "sort": sort},
                "page_context": {"subreddit": subreddit, "sort": sort},
                "views": score,
                "likes": score,
                "score": score,
                "comments": comments,
                "title": (str(post.get("title") or "")[:200] or None),
                "tags": tags[:15],
                "format_bucket": fmt,
                "uploaded_at_approx_days_ago": round(age_days, 2) if age_days else None,
                "views_per_day_proxy": vpd,
                "uploader": (str(post.get("author") or "")[:80] or None),
                "engagement_bps": int(round(comments / score * 100_000)) if score > 0 else 0,
            }
        )
    return rows


def run_market_probes(*, limit_per_sub: int = 25) -> dict[str, Any]:
    if not probe_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}
    from app.services.erome_browse_intel import ingest_rows

    all_rows: list[dict[str, Any]] = []
    per_sub: dict[str, int] = {}
    for sub in probe_subreddits():
        rows = _reddit_post_rows(sub, limit=limit_per_sub)
        per_sub[sub] = len(rows)
        all_rows.extend(rows)
    ingest = ingest_rows(all_rows) if all_rows else {"ok": True, "appended": 0, "scanned": 0}
    return {
        "ok": True,
        "subreddits": probe_subreddits(),
        "per_sub_counts": per_sub,
        "ingest": ingest,
    }
