"""Tests for Reddit global cap, beacons, and ledger."""

from datetime import datetime, timedelta, timezone

import pytest

from app.data.reddit_beacon_plan import (
    build_reddit_beacon_plan,
    reddit_beacon_slug,
    reddit_source_ref,
)
from app.services.click_beacon import _SLUG_RE
from app.services.reddit_global_state import (
    check_global_reddit_eligibility,
    record_global_reddit_post,
)
from app.services.reddit_post_ledger import append_reddit_post_ledger, read_reddit_post_ledger


def test_reddit_beacon_slugs_valid():
    for b in build_reddit_beacon_plan():
        assert _SLUG_RE.match(b.slug), b.slug
        assert b.source_ref.startswith("src_reddit_")


def test_telegram_nsfw_beacon_slug():
    assert reddit_beacon_slug("telegramNSFW1818") == "reddit-telegramnsfw1818"
    assert reddit_source_ref("telegramNSFW1818") == "src_reddit_telegramnsfw1818"


def test_global_cap_blocks_after_limit(monkeypatch, tmp_path):
    from app.services import reddit_global_state as rgs

    d = tmp_path / "reddit-promo"
    d.mkdir()
    monkeypatch.setattr(rgs, "_state_path", lambda: d / "global-state.json")
    monkeypatch.setenv("TBCC_REDDIT_GLOBAL_MAX_POSTS_PER_DAY", "2")
    monkeypatch.setenv("TBCC_REDDIT_GLOBAL_MIN_GAP_HOURS", "0")

    assert check_global_reddit_eligibility().ok
    record_global_reddit_post()
    record_global_reddit_post()
    el = check_global_reddit_eligibility()
    assert not el.ok
    assert el.reason == "global_daily_cap_2"


def test_global_gap_enforced(monkeypatch, tmp_path):
    from app.services import reddit_global_state as rgs

    d = tmp_path / "reddit-promo"
    d.mkdir()
    monkeypatch.setattr(rgs, "_state_path", lambda: d / "global-state.json")
    monkeypatch.setenv("TBCC_REDDIT_GLOBAL_MAX_POSTS_PER_DAY", "10")
    monkeypatch.setenv("TBCC_REDDIT_GLOBAL_MIN_GAP_HOURS", "4")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    state = {
        "utc_day": now.strftime("%Y-%m-%d"),
        "posts_today": 1,
        "last_post_at": now.isoformat(),
    }
    rgs._write_state(state)
    el = check_global_reddit_eligibility(now=now)
    assert not el.ok
    assert el.reason.startswith("global_gap_")


def test_pick_eligible_only_telegram_nsfw_slow_start(db):
    from app.models.reddit_subreddit_profile import RedditSubredditProfile
    from app.services.reddit_post_service import seed_registry_profiles
    from app.services.reddit_rules import pick_eligible_subreddits

    seed_registry_profiles(db, replace=True)
    picks = pick_eligible_subreddits(db, limit=3)
    assert len(picks) == 1
    prof, el = picks[0]
    assert prof.name.lower() == "telegramnsfw1818"
    assert el.ok

    paused = (
        db.query(RedditSubredditProfile)
        .filter(RedditSubredditProfile.status == "paused")
        .count()
    )
    assert paused >= 9


def test_post_ledger_append_and_read(monkeypatch, tmp_path):
    from app.services import reddit_post_ledger as rpl

    monkeypatch.setattr(rpl, "reddit_promo_dir", lambda: tmp_path)
    append_reddit_post_ledger({"subreddit": "telegramnsfw1818", "ok": True, "dry_run": True})
    rows = read_reddit_post_ledger(limit=5)
    assert len(rows) == 1
    assert rows[0]["subreddit"] == "telegramnsfw1818"
