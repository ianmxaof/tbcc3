"""Suggest Reddit subreddit registry entries from Scrolller agent metadata."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_reddit_subreddit_registry import AOF_REDDIT_SUBREDDIT_REGISTRY
from app.models.reddit_subreddit_profile import RedditSubredditProfile
from app.services.market_intel_scrolller_probe import discover_scrolller_subreddit_candidates
from app.services.reddit_rules import normalize_subreddit_name

logger = logging.getLogger(__name__)

_REGISTRY_SKIP = frozenset({"test"})


def scrolller_registry_suggest_enabled() -> bool:
    return (os.getenv("TBCC_SCROLLLER_REGISTRY_SUGGEST_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def scrolller_registry_auto_apply_enabled() -> bool:
    return (os.getenv("TBCC_SCROLLLER_REGISTRY_AUTO_APPLY") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def scrolller_registry_min_subscribers() -> int:
    raw = (os.getenv("TBCC_SCROLLLER_REGISTRY_MIN_SUBSCRIBERS") or "50000").strip()
    try:
        return max(1000, min(10_000_000, int(raw)))
    except ValueError:
        return 50_000


def scrolller_registry_max_new_per_run() -> int:
    raw = (os.getenv("TBCC_SCROLLLER_REGISTRY_MAX_NEW") or "5").strip()
    try:
        return max(1, min(25, int(raw)))
    except ValueError:
        return 5


def infer_tier_from_subscribers(subscribers: int) -> str:
    if subscribers >= 500_000:
        return "hot"
    if subscribers >= 100_000:
        return "warm"
    return "cold"


def infer_post_kind(dominant_content_type: str | None) -> str:
    ct = (dominant_content_type or "image").strip().lower()
    if ct in ("gallery", "album"):
        return "gallery"
    if ct == "video":
        return "image"
    if ct == "link":
        return "link"
    return "image"


def registry_row_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    name = normalize_subreddit_name(str(candidate.get("name") or ""))
    subscribers = int(candidate.get("subscribers") or 0)
    item_count = int(candidate.get("item_count") or 0)
    rating = str(candidate.get("content_rating") or "explicit").lower()
    fetched = str(candidate.get("fetched_at") or "")[:10]
    dominant = str(candidate.get("dominant_content_type") or "image")
    return {
        "name": name,
        "tier": infer_tier_from_subscribers(subscribers),
        "status": "probation",
        "link_policy": "comment_only",
        "post_kind": infer_post_kind(dominant),
        "nsfw_required": rating not in ("safe", "sfw", "general"),
        "cooldown_hours": 120.0,
        "max_posts_per_day": 0.0,
        "max_posts_per_week": 1.0,
        "notes": (
            f"Scrolller suggest {fetched}: {subscribers:,} subs, {item_count:,} items "
            f"(dominant={dominant}). Review sub rules before active."
        ),
    }


def _known_registry_names(db: Session | None = None) -> set[str]:
    names: set[str] = set()
    for row in AOF_REDDIT_SUBREDDIT_REGISTRY:
        n = normalize_subreddit_name(str(row.get("name") or ""))
        if n:
            names.add(n)
    if db is not None:
        for prof in db.query(RedditSubredditProfile.name).all():
            n = normalize_subreddit_name(str(prof[0] or ""))
            if n:
                names.add(n)
    return names


def suggest_reddit_registry_from_scrolller(
    db: Session | None = None,
    *,
    apply: bool = False,
    max_new: int | None = None,
) -> dict[str, Any]:
    """Rank Scrolller seed subs and propose probation registry rows for unknown names."""
    if not scrolller_registry_suggest_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}

    known = _known_registry_names(db)
    min_subs = scrolller_registry_min_subscribers()
    cap = max_new if max_new is not None else scrolller_registry_max_new_per_run()

    candidates = discover_scrolller_subreddit_candidates(limit_per_sub=5)
    suggestions: list[dict[str, Any]] = []
    for cand in candidates:
        name = normalize_subreddit_name(str(cand.get("name") or ""))
        if not name or name in _REGISTRY_SKIP or name in known:
            continue
        subscribers = int(cand.get("subscribers") or 0)
        if subscribers < min_subs:
            continue
        row = registry_row_from_candidate(cand)
        suggestions.append(
            {
                **row,
                "scrolller": {
                    "subscribers": subscribers,
                    "item_count": int(cand.get("item_count") or 0),
                    "content_rating": cand.get("content_rating"),
                    "embed_url": cand.get("embed_url"),
                },
            }
        )

    suggestions.sort(
        key=lambda r: int((r.get("scrolller") or {}).get("subscribers") or 0),
        reverse=True,
    )
    suggestions = suggestions[:cap]

    applied: list[str] = []
    if apply and scrolller_registry_auto_apply_enabled() and db is not None and suggestions:
        now = datetime.utcnow()
        for row in suggestions:
            name = normalize_subreddit_name(str(row.get("name") or ""))
            if not name:
                continue
            prof = RedditSubredditProfile(name=name)
            for key in (
                "status",
                "tier",
                "link_policy",
                "post_kind",
                "nsfw_required",
                "cooldown_hours",
                "max_posts_per_day",
                "max_posts_per_week",
                "notes",
            ):
                if key in row and row[key] is not None:
                    setattr(prof, key, row[key])
            prof.created_at = now
            prof.updated_at = now
            db.add(prof)
            known.add(name)
            applied.append(name)
        if applied:
            db.commit()
            logger.info("scrolller registry auto-apply: %s", applied)

    return {
        "ok": True,
        "min_subscribers": min_subs,
        "known_count": len(known),
        "candidates_scanned": len(candidates),
        "suggestions": suggestions,
        "applied": applied,
        "auto_apply_enabled": scrolller_registry_auto_apply_enabled(),
    }
