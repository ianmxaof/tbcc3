"""Reddit posting eligibility — cadence, karma, link policy."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.reddit_subreddit_profile import RedditSubredditProfile


@dataclass
class RedditEligibility:
    ok: bool
    subreddit: str
    reason: str | None = None
    profile_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "subreddit": self.subreddit,
            "reason": self.reason,
            "profile_id": self.profile_id,
        }


def reddit_enabled() -> bool:
    return (os.getenv("TBCC_REDDIT_ENABLED") or "0").strip().lower() in ("1", "true", "yes")


def reddit_execute_enabled() -> bool:
    return (os.getenv("TBCC_REDDIT_EXECUTE") or "0").strip().lower() in ("1", "true", "yes")


def reddit_global_daily_cap() -> int:
    raw = (os.getenv("TBCC_REDDIT_GLOBAL_MAX_POSTS_PER_DAY") or "3").strip()
    try:
        return max(1, min(20, int(raw)))
    except ValueError:
        return 3


def reddit_global_min_gap_hours() -> float:
    raw = (os.getenv("TBCC_REDDIT_GLOBAL_MIN_GAP_HOURS") or "4").strip()
    try:
        return max(1.0, min(48.0, float(raw)))
    except ValueError:
        return 4.0


def normalize_subreddit_name(name: str) -> str:
    n = (name or "").strip().lower()
    if n.startswith("r/"):
        n = n[2:]
    return n[:128]


def _reset_cadence_counters(row: RedditSubredditProfile, now: datetime) -> None:
    day = now.strftime("%Y-%m-%d")
    week = now.strftime("%Y-W%W")
    if row.utc_day != day:
        row.utc_day = day
        row.posts_today = 0
    if row.utc_week != week:
        row.utc_week = week
        row.posts_week = 0


def check_subreddit_eligibility(
    row: RedditSubredditProfile,
    *,
    now: datetime | None = None,
    account_karma: int | None = None,
    account_age_days: int | None = None,
) -> RedditEligibility:
    name = normalize_subreddit_name(row.name)
    now = now or datetime.utcnow()

    if row.status == "banned":
        return RedditEligibility(False, name, row.skip_reason or "subreddit_banned", row.id)
    if row.status == "paused":
        return RedditEligibility(False, name, row.skip_reason or "subreddit_paused", row.id)

    _reset_cadence_counters(row, now)
    if int(row.posts_today or 0) >= max(1, int(row.max_posts_per_day or 1)):
        return RedditEligibility(False, name, "sub_daily_cap", row.id)
    if int(row.posts_week or 0) >= max(1, int(row.max_posts_per_week or 1)):
        return RedditEligibility(False, name, "sub_weekly_cap", row.id)

    if row.last_post_at:
        gap_h = (now - row.last_post_at).total_seconds() / 3600.0
        if gap_h < float(row.cooldown_hours or 72):
            return RedditEligibility(False, name, f"cooldown_{row.cooldown_hours}h", row.id)

    if row.min_karma is not None and account_karma is not None:
        if account_karma < int(row.min_karma):
            return RedditEligibility(False, name, f"min_karma_{row.min_karma}", row.id)
    if row.min_account_age_days is not None and account_age_days is not None:
        if account_age_days < int(row.min_account_age_days):
            return RedditEligibility(False, name, f"min_age_{row.min_account_age_days}d", row.id)

    return RedditEligibility(True, name, None, row.id)


def pick_eligible_subreddits(
    db: Session,
    *,
    limit: int = 1,
    tier: str | None = None,
    account_karma: int | None = None,
    account_age_days: int | None = None,
    erome_url: str | None = None,
    prefer_gallery: bool = False,
) -> list[tuple[RedditSubredditProfile, RedditEligibility]]:
    if erome_url:
        row = (
            db.query(RedditSubredditProfile)
            .filter(
                RedditSubredditProfile.name == "erome",
                RedditSubredditProfile.status.in_(("active", "probation")),
            )
            .first()
        )
        if row:
            el = check_subreddit_eligibility(row, account_karma=account_karma, account_age_days=account_age_days)
            if el.ok:
                return [(row, el)]

    q = db.query(RedditSubredditProfile).filter(RedditSubredditProfile.status.in_(("active", "probation")))
    if tier:
        q = q.filter(RedditSubredditProfile.tier == tier)
    if prefer_gallery:
        q = q.filter(RedditSubredditProfile.post_kind.in_(("gallery", "image")))
    from sqlalchemy import case

    tier_rank = case(
        (RedditSubredditProfile.tier == "hot", 0),
        (RedditSubredditProfile.tier == "warm", 1),
        else_=2,
    )
    rows = q.order_by(tier_rank, RedditSubredditProfile.name.asc()).all()
    out: list[tuple[RedditSubredditProfile, RedditEligibility]] = []
    for row in rows:
        el = check_subreddit_eligibility(
            row,
            account_karma=account_karma,
            account_age_days=account_age_days,
        )
        if el.ok:
            out.append((row, el))
        if len(out) >= limit:
            break
    return out


def record_subreddit_post_attempt(
    db: Session,
    row: RedditSubredditProfile,
    *,
    ok: bool,
    skip_reason: str | None = None,
) -> None:
    now = datetime.utcnow()
    _reset_cadence_counters(row, now)
    row.last_post_at = now
    row.last_post_ok = bool(ok)
    if ok:
        row.posts_today = int(row.posts_today or 0) + 1
        row.posts_week = int(row.posts_week or 0) + 1
        row.skip_reason = None
    elif skip_reason:
        row.skip_reason = skip_reason[:256]
    row.updated_at = now
    db.add(row)


def parse_rules_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}
