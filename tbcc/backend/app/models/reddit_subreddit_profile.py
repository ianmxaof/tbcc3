"""Curated subreddit targets — rules, cadence, ban-risk policy."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from .base import Base


class RedditSubredditProfile(Base):
    __tablename__ = "reddit_subreddit_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), unique=True, nullable=False, index=True)  # without r/

    status = Column(String(16), nullable=False, default="probation")  # active|probation|paused|banned
    tier = Column(String(16), nullable=True)  # hot|warm|cold

    link_policy = Column(String(24), nullable=False, default="bio_style")  # none|comment_only|bio_style|direct_ok
    post_kind = Column(String(16), nullable=False, default="image")  # text|link|image|gallery
    nsfw_required = Column(Boolean, nullable=False, default=True)
    required_flair = Column(String(128), nullable=True)

    min_karma = Column(Integer, nullable=True)
    min_account_age_days = Column(Integer, nullable=True)
    cooldown_hours = Column(Float, nullable=False, default=72.0)
    max_posts_per_day = Column(Float, nullable=False, default=1.0)
    max_posts_per_week = Column(Float, nullable=False, default=3.0)

    rules_snippet = Column(Text, nullable=True)
    rules_json = Column(Text, nullable=True)
    rules_fetched_at = Column(DateTime, nullable=True)
    skip_reason = Column(String(256), nullable=True)
    notes = Column(Text, nullable=True)

    last_post_at = Column(DateTime, nullable=True)
    last_post_ok = Column(Boolean, nullable=True)
    posts_today = Column(Integer, nullable=False, default=0)
    posts_week = Column(Integer, nullable=False, default=0)
    utc_day = Column(String(10), nullable=True)
    utc_week = Column(String(8), nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
