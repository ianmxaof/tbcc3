"""Scrolller agent-route market probe — metadata only (no raw media URLs)."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_USER_AGENT = "TBCC-MarketIntel/1.0 (research; contact ops)"
_BASE_URL = "https://scrolller.com/agent/subreddit"
_REDDIT_SOURCE_RE = re.compile(r"/r/([^/]+)/", re.I)


def scrolller_probe_enabled() -> bool:
    return (os.getenv("TBCC_SCROLLLER_PROBE_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def scrolller_probe_subreddits() -> list[str]:
    """Subs to probe for content rows — defaults to Reddit JSON probe list."""
    raw = (os.getenv("TBCC_SCROLLLER_PROBE_SUBREDDITS") or "").strip()
    if raw:
        out: list[str] = []
        for chunk in raw.split(","):
            name = chunk.strip().lower().removeprefix("r/")
            if name and name not in out:
                out.append(name)
        if out:
            return out
    from app.services.market_intel_probe import probe_subreddits

    return probe_subreddits()


def scrolller_seed_subreddits() -> list[str]:
    """Broader discovery list for registry suggestions (union with registry + probe lists)."""
    raw = (os.getenv("TBCC_SCROLLLER_PROBE_SEED_SUBREDDITS") or "").strip()
    defaults = (
        "nsfw,RealGirls,amateur,milf,gonewild,thick,curvy,fitgirls,latinas,asians,"
        "erome,amateur_milfs,GirlsShowering"
    )
    seeds: list[str] = []
    for chunk in (raw or defaults).split(","):
        name = chunk.strip().lower().removeprefix("r/")
        if name and name not in seeds:
            seeds.append(name)
    from app.data.aof_reddit_subreddit_registry import AOF_REDDIT_SUBREDDIT_REGISTRY

    for row in AOF_REDDIT_SUBREDDIT_REGISTRY:
        name = str(row.get("name") or "").strip().lower().removeprefix("r/")
        if name and name not in seeds:
            seeds.append(name)
    for name in scrolller_probe_subreddits():
        if name not in seeds:
            seeds.append(name)
    return seeds


def scrolller_request_interval_sec() -> float:
    raw = (os.getenv("TBCC_SCROLLLER_PROBE_INTERVAL_SEC") or "1.1").strip()
    try:
        return max(1.0, min(5.0, float(raw)))
    except ValueError:
        return 1.1


def _fetch_json(url: str, *, timeout: int = 25) -> dict[str, Any] | None:
    req = Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            return data if isinstance(data, dict) else None
    except HTTPError as e:
        if e.code == 429:
            logger.warning("scrolller rate limited %s", url[:80])
        elif e.code != 404:
            logger.warning("scrolller fetch HTTP %s %s", e.code, url[:80])
        return None
    except Exception as e:
        logger.warning("scrolller fetch failed %s: %s", url[:80], e)
        return None


def _format_bucket(content_type: str | None) -> str:
    ct = (content_type or "").strip().lower()
    if ct in ("video", "gif"):
        return "video"
    if ct in ("gallery", "album"):
        return "gallery"
    if ct in ("image", "picture", "photo"):
        return "image"
    if ct == "subreddit":
        return "subreddit"
    return ct or "unknown"


def _tags_for_item(subreddit: str, item: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    sub = subreddit.strip().lower()
    if sub:
        tags.append(sub)
    for t in item.get("tags") or []:
        s = str(t).strip().lower()
        if s and s not in tags:
            tags.append(s)
    source = str(item.get("source") or "")
    m = _REDDIT_SOURCE_RE.search(source)
    if m:
        src_sub = m.group(1).lower()
        if src_sub not in tags:
            tags.append(src_sub)
    return tags[:15]


def scrolller_subreddit_snapshot(
    subreddit: str,
    *,
    limit: int = 20,
) -> dict[str, Any] | None:
    slug = subreddit.strip().lower().removeprefix("r/")
    if not slug:
        return None
    lim = max(1, min(50, int(limit)))
    url = f"{_BASE_URL}/{slug}?limit={lim}"
    return _fetch_json(url)


def scrolller_subreddit_rows(
    payload: dict[str, Any],
    *,
    captured_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Map Scrolller subreddit agent JSON → unified market-intel rows."""
    now = captured_at or datetime.now(timezone.utc)
    slug = str(payload.get("slug") or "").strip().lower()
    if not slug:
        return []
    subscribers = int(payload.get("subscribers") or 0)
    item_count = int(payload.get("itemCount") or 0)
    sub_tags = [str(t).strip().lower() for t in (payload.get("tags") or []) if str(t).strip()]
    if slug not in sub_tags:
        sub_tags.insert(0, slug)

    rows: list[dict[str, Any]] = [
        {
            "platform": "scrolller",
            "captured_at": now.isoformat().replace("+00:00", "Z"),
            "entity_id": f"sub:{slug}",
            "entity_url": str(payload.get("embedUrl") or f"https://scrolller.com/r/{slug}"),
            "album_url": str(payload.get("embedUrl") or f"https://scrolller.com/r/{slug}"),
            "album_id": slug,
            "context": {
                "subreddit": slug,
                "subscribers": subscribers,
                "item_count": item_count,
                "content_rating": payload.get("contentRating"),
                "source": "scrolller_agent_subreddit",
            },
            "page_context": {"subreddit": slug, "probe": "scrolller"},
            "views": subscribers if subscribers > 0 else None,
            "likes": subscribers if subscribers > 0 else None,
            "title": (str(payload.get("title") or slug)[:200] or None),
            "tags": sub_tags[:15],
            "format_bucket": "subreddit",
            "uploader": None,
            "engagement_bps": int(min(5000, item_count // 10)) if item_count > 0 else 0,
        }
    ]

    items = payload.get("items") or []
    if not isinstance(items, list):
        return rows

    views_proxy = subscribers if subscribers > 0 else max(1, item_count)
    for item in items:
        if not isinstance(item, dict):
            continue
        content_id = str(item.get("contentId") or "").strip()
        if not content_id:
            continue
        embed_url = str(item.get("embedUrl") or "").strip()
        entity_url = embed_url or f"https://scrolller.com{content_id}"
        rows.append(
            {
                "platform": "scrolller",
                "captured_at": now.isoformat().replace("+00:00", "Z"),
                "entity_id": content_id.lstrip("/"),
                "entity_url": entity_url,
                "album_url": entity_url,
                "album_id": content_id.lstrip("/"),
                "context": {
                    "subreddit": slug,
                    "subscribers": subscribers,
                    "item_count": item_count,
                    "content_type": item.get("contentType"),
                    "content_rating": item.get("contentRating"),
                    "reddit_source": item.get("source"),
                    "source": "scrolller_agent_item",
                    "attribution": "scrolller",
                },
                "page_context": {"subreddit": slug, "probe": "scrolller"},
                "views": views_proxy,
                "likes": views_proxy,
                "title": (str(item.get("title") or "")[:200] or None),
                "tags": _tags_for_item(slug, item),
                "format_bucket": _format_bucket(str(item.get("contentType") or "")),
                "uploader": None,
                "engagement_bps": 0,
            }
        )
    return rows


def run_scrolller_probes(*, limit_per_sub: int = 20) -> dict[str, Any]:
    if not scrolller_probe_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}
    from app.services.erome_browse_intel import ingest_rows

    all_rows: list[dict[str, Any]] = []
    per_sub: dict[str, int] = {}
    errors: dict[str, str] = {}
    interval = scrolller_request_interval_sec()
    subs = scrolller_probe_subreddits()

    for i, sub in enumerate(subs):
        if i > 0:
            time.sleep(interval)
        payload = scrolller_subreddit_snapshot(sub, limit=limit_per_sub)
        if not payload:
            errors[sub] = "fetch_failed"
            per_sub[sub] = 0
            continue
        rows = scrolller_subreddit_rows(payload)
        per_sub[sub] = len(rows)
        all_rows.extend(rows)

    ingest = ingest_rows(all_rows) if all_rows else {"ok": True, "appended": 0, "scanned": 0}
    return {
        "ok": True,
        "subreddits": subs,
        "per_sub_counts": per_sub,
        "errors": errors,
        "ingest": ingest,
    }


def discover_scrolller_subreddit_candidates(
    *,
    limit_per_sub: int = 5,
    max_subs: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch Scrolller metadata for seed subs — used for registry suggestions."""
    interval = scrolller_request_interval_sec()
    seeds = scrolller_seed_subreddits()
    if max_subs is not None:
        seeds = seeds[: max(1, int(max_subs))]

    out: list[dict[str, Any]] = []
    for i, sub in enumerate(seeds):
        if i > 0:
            time.sleep(interval)
        payload = scrolller_subreddit_snapshot(sub, limit=limit_per_sub)
        if not payload:
            continue
        slug = str(payload.get("slug") or sub).strip().lower()
        subscribers = int(payload.get("subscribers") or 0)
        item_count = int(payload.get("itemCount") or 0)
        items = payload.get("items") or []
        content_types: list[str] = []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("contentType"):
                    content_types.append(str(item["contentType"]).lower())
        out.append(
            {
                "name": slug,
                "subscribers": subscribers,
                "item_count": item_count,
                "content_rating": str(payload.get("contentRating") or "").lower(),
                "embed_url": payload.get("embedUrl"),
                "dominant_content_type": _dominant_content_type(content_types),
                "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        )
    out.sort(key=lambda r: (int(r.get("subscribers") or 0), int(r.get("item_count") or 0)), reverse=True)
    return out


def _dominant_content_type(types: list[str]) -> str:
    if not types:
        return "image"
    counts: dict[str, int] = {}
    for t in types:
        counts[t] = counts.get(t, 0) + 1
    return max(counts, key=counts.get)
