"""Tests for Scrolller → Reddit subreddit registry suggestions."""

from __future__ import annotations

from unittest.mock import patch

from app.models.reddit_subreddit_profile import RedditSubredditProfile
from app.services.scrolller_reddit_registry import (
    infer_tier_from_subscribers,
    registry_row_from_candidate,
    suggest_reddit_registry_from_scrolller,
)


def test_infer_tier_from_subscribers():
    assert infer_tier_from_subscribers(600_000) == "hot"
    assert infer_tier_from_subscribers(150_000) == "warm"
    assert infer_tier_from_subscribers(20_000) == "cold"


def test_registry_row_from_candidate_probation_defaults():
    row = registry_row_from_candidate(
        {
            "name": "RealGirls",
            "subscribers": 2_000_000,
            "item_count": 12000,
            "content_rating": "explicit",
            "dominant_content_type": "gallery",
            "fetched_at": "2026-08-08T00:00:00Z",
        }
    )
    assert row["name"] == "realgirls"
    assert row["status"] == "probation"
    assert row["tier"] == "hot"
    assert row["post_kind"] == "gallery"
    assert row["link_policy"] == "comment_only"
    assert "Scrolller suggest" in row["notes"]


def test_suggest_reddit_registry_from_scrolller_filters_known(monkeypatch, db):
    monkeypatch.setenv("TBCC_SCROLLLER_REGISTRY_SUGGEST_ENABLED", "1")
    monkeypatch.setenv("TBCC_SCROLLLER_REGISTRY_MIN_SUBSCRIBERS", "100000")
    monkeypatch.setenv("TBCC_SCROLLLER_REGISTRY_AUTO_APPLY", "0")

    db.add(
        RedditSubredditProfile(
            name="erome",
            status="probation",
            tier="hot",
            link_policy="direct_ok",
            post_kind="link",
            nsfw_required=True,
        )
    )
    db.commit()

    fake_candidates = [
        {
            "name": "erome",
            "subscribers": 500_000,
            "item_count": 100,
            "content_rating": "explicit",
            "dominant_content_type": "link",
            "fetched_at": "2026-08-08T00:00:00Z",
        },
        {
            "name": "RealGirls",
            "subscribers": 2_500_000,
            "item_count": 50000,
            "content_rating": "explicit",
            "dominant_content_type": "image",
            "fetched_at": "2026-08-08T00:00:00Z",
        },
    ]

    with patch(
        "app.services.scrolller_reddit_registry.discover_scrolller_subreddit_candidates",
        return_value=fake_candidates,
    ):
        result = suggest_reddit_registry_from_scrolller(db)

    assert result["ok"] is True
    names = [s["name"] for s in result["suggestions"]]
    assert "erome" not in names
    assert "realgirls" in names
    assert result["applied"] == []


def test_suggest_reddit_registry_auto_apply(monkeypatch, db):
    monkeypatch.setenv("TBCC_SCROLLLER_REGISTRY_SUGGEST_ENABLED", "1")
    monkeypatch.setenv("TBCC_SCROLLLER_REGISTRY_MIN_SUBSCRIBERS", "100000")
    monkeypatch.setenv("TBCC_SCROLLLER_REGISTRY_AUTO_APPLY", "1")
    monkeypatch.setenv("TBCC_SCROLLLER_REGISTRY_MAX_NEW", "2")

    fake_candidates = [
        {
            "name": "latinas",
            "subscribers": 800_000,
            "item_count": 20000,
            "content_rating": "explicit",
            "dominant_content_type": "image",
            "fetched_at": "2026-08-08T00:00:00Z",
        }
    ]

    with patch(
        "app.services.scrolller_reddit_registry.discover_scrolller_subreddit_candidates",
        return_value=fake_candidates,
    ):
        result = suggest_reddit_registry_from_scrolller(db, apply=True)

    assert result["applied"] == ["latinas"]
    prof = db.query(RedditSubredditProfile).filter(RedditSubredditProfile.name == "latinas").first()
    assert prof is not None
    assert prof.status == "probation"
    assert prof.tier == "hot"
